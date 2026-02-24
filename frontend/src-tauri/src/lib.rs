use serde::Serialize;
use std::process::Command;
use std::sync::Mutex;
use tauri::{Emitter, Manager};

#[derive(Debug, Serialize, Clone)]
pub struct DetectedGame {
    pub path: String,
    pub source: String,
}

struct BackendProcess {
    child: Option<tauri_plugin_shell::process::CommandChild>,
}

#[tauri::command]
fn detect_game_paths() -> Vec<DetectedGame> {
    let mut results = Vec::new();

    #[cfg(target_os = "windows")]
    {
        results.extend(detect_steam());
        results.extend(detect_gog());
        results.extend(detect_epic());
    }

    results.extend(detect_common_paths());

    // Deduplicate by normalized path
    let mut seen = std::collections::HashSet::new();
    results.retain(|g| {
        let normalized = g.path.replace('/', "\\").to_lowercase();
        seen.insert(normalized)
    });

    results
}

#[cfg(target_os = "windows")]
fn detect_steam() -> Vec<DetectedGame> {
    use winreg::enums::*;
    use winreg::RegKey;

    let mut results = Vec::new();

    // Read Steam install path from registry
    let hkcu = RegKey::predef(HKEY_CURRENT_USER);
    let steam_key = match hkcu.open_subkey(r"Software\Valve\Steam") {
        Ok(k) => k,
        Err(_) => return results,
    };

    let steam_path: String = match steam_key.get_value("SteamPath") {
        Ok(p) => p,
        Err(_) => return results,
    };

    // Parse libraryfolders.vdf for multi-library setups
    let vdf_path = std::path::Path::new(&steam_path)
        .join("steamapps")
        .join("libraryfolders.vdf");

    let mut library_paths = vec![steam_path.clone()];

    if let Ok(content) = std::fs::read_to_string(&vdf_path) {
        // Simple VDF parser: look for "path" entries
        for line in content.lines() {
            let trimmed = line.trim();
            if trimmed.starts_with("\"path\"") {
                if let Some(path_value) = extract_vdf_value(trimmed) {
                    let clean = path_value.replace("\\\\", "\\");
                    if !library_paths
                        .iter()
                        .any(|p| p.to_lowercase() == clean.to_lowercase())
                    {
                        library_paths.push(clean);
                    }
                }
            }
        }
    }

    // Check each library for Cyberpunk 2077
    for lib_path in library_paths {
        let game_path = std::path::Path::new(&lib_path)
            .join("steamapps")
            .join("common")
            .join("Cyberpunk 2077");

        if is_valid_cyberpunk_path(&game_path) {
            results.push(DetectedGame {
                path: game_path.to_string_lossy().to_string(),
                source: "Steam".to_string(),
            });
        }
    }

    results
}

#[cfg(target_os = "windows")]
fn detect_gog() -> Vec<DetectedGame> {
    use winreg::enums::*;
    use winreg::RegKey;

    let mut results = Vec::new();

    // Check both 64-bit and 32-bit registry views via subkey paths
    {
        let reg = RegKey::predef(HKEY_LOCAL_MACHINE);
        for subkey_path in [
            r"SOFTWARE\Microsoft\Windows\CurrentVersion\Uninstall",
            r"SOFTWARE\WOW6432Node\Microsoft\Windows\CurrentVersion\Uninstall",
        ] {
            let uninstall = match reg.open_subkey(subkey_path) {
                Ok(k) => k,
                Err(_) => continue,
            };

            for name in uninstall.enum_keys().filter_map(|k| k.ok()) {
                let subkey = match uninstall.open_subkey(&name) {
                    Ok(k) => k,
                    Err(_) => continue,
                };

                let display_name: String = match subkey.get_value("DisplayName") {
                    Ok(n) => n,
                    Err(_) => continue,
                };

                let lower = display_name.to_lowercase();
                if lower.contains("cyberpunk") && lower.contains("2077") {
                    if let Ok(install_loc) = subkey.get_value::<String, _>("InstallLocation") {
                        let path = std::path::Path::new(&install_loc);
                        if is_valid_cyberpunk_path(path) {
                            results.push(DetectedGame {
                                path: install_loc,
                                source: "GOG".to_string(),
                            });
                        }
                    }
                }
            }
        }
    }

    results
}

#[cfg(target_os = "windows")]
fn detect_epic() -> Vec<DetectedGame> {
    let mut results = Vec::new();

    // Epic manifests are stored in ProgramData
    let manifests_dir =
        std::path::Path::new(r"C:\ProgramData\Epic\EpicGamesLauncher\Data\Manifests");

    if !manifests_dir.exists() {
        return results;
    }

    let entries = match std::fs::read_dir(manifests_dir) {
        Ok(e) => e,
        Err(_) => return results,
    };

    for entry in entries.filter_map(|e| e.ok()) {
        let path = entry.path();
        if path.extension().and_then(|e| e.to_str()) != Some("item") {
            continue;
        }

        let content = match std::fs::read_to_string(&path) {
            Ok(c) => c,
            Err(_) => continue,
        };

        // Parse JSON manifest
        let json: serde_json::Value = match serde_json::from_str(&content) {
            Ok(v) => v,
            Err(_) => continue,
        };

        let display_name = json
            .get("DisplayName")
            .and_then(|v| v.as_str())
            .unwrap_or("");
        let lower = display_name.to_lowercase();

        if lower.contains("cyberpunk") && lower.contains("2077") {
            if let Some(install_loc) = json.get("InstallLocation").and_then(|v| v.as_str()) {
                let install_path = std::path::Path::new(install_loc);
                if is_valid_cyberpunk_path(install_path) {
                    results.push(DetectedGame {
                        path: install_loc.to_string(),
                        source: "Epic".to_string(),
                    });
                }
            }
        }
    }

    results
}

fn detect_common_paths() -> Vec<DetectedGame> {
    let mut results = Vec::new();

    let common_paths = [
        r"C:\Program Files (x86)\Steam\steamapps\common\Cyberpunk 2077",
        r"C:\Program Files\Steam\steamapps\common\Cyberpunk 2077",
        r"C:\GOG Games\Cyberpunk 2077",
        r"D:\SteamLibrary\steamapps\common\Cyberpunk 2077",
        r"D:\Games\Cyberpunk 2077",
        r"E:\SteamLibrary\steamapps\common\Cyberpunk 2077",
        r"E:\Games\Cyberpunk 2077",
        r"G:\SteamLibrary\steamapps\common\Cyberpunk 2077",
    ];

    for path_str in &common_paths {
        let path = std::path::Path::new(path_str);
        if is_valid_cyberpunk_path(path) {
            results.push(DetectedGame {
                path: path_str.to_string(),
                source: "Common Path".to_string(),
            });
        }
    }

    results
}

fn is_valid_cyberpunk_path(path: &std::path::Path) -> bool {
    path.join("bin")
        .join("x64")
        .join("Cyberpunk2077.exe")
        .exists()
}

#[cfg(target_os = "windows")]
fn extract_vdf_value(line: &str) -> Option<String> {
    // VDF format: "key"		"value"
    // Find all quote positions and extract the last quoted string
    let quotes: Vec<usize> = line
        .char_indices()
        .filter(|&(_, c)| c == '"')
        .map(|(i, _)| i)
        .collect();

    if quotes.len() >= 4 {
        let start = quotes[quotes.len() - 2] + 1;
        let end = quotes[quotes.len() - 1];
        if start < end {
            return Some(line[start..end].to_string());
        }
    }

    None
}

#[tauri::command]
fn launch_game(
    install_path: String,
    exe_relative_path: String,
    launch_args: Option<Vec<String>>,
) -> Result<(), String> {
    let exe_path = std::path::Path::new(&install_path).join(&exe_relative_path);

    if !exe_path.exists() {
        return Err(format!(
            "Game executable not found: {}",
            exe_path.display()
        ));
    }

    let mut cmd = Command::new(&exe_path);
    if let Some(args) = launch_args {
        cmd.args(args);
    }
    cmd.spawn()
        .map_err(|e| format!("Failed to launch game: {}", e))?;

    Ok(())
}

fn spawn_sidecar(app: &tauri::AppHandle) -> Result<(), Box<dyn std::error::Error>> {
    use tauri_plugin_shell::ShellExt;

    log::info!("Spawning backend sidecar...");

    // Resolve RMM_DATA_DIR for the sidecar process
    let data_dir = app
        .path()
        .local_data_dir()
        .map(|d: std::path::PathBuf| d.join("RipperModManager"))
        .unwrap_or_else(|_| std::path::PathBuf::from("./data"));

    let sidecar_command = app
        .shell()
        .sidecar("binaries/rmm-backend")
        .map_err(|e| format!("Failed to create sidecar command: {e}"))?
        .env("RMM_DATA_DIR", data_dir.to_string_lossy().to_string());

    let (mut rx, child) = sidecar_command
        .spawn()
        .map_err(|e| format!("Failed to spawn sidecar: {e}"))?;

    // Store the child process handle for cleanup
    let state = app.state::<Mutex<BackendProcess>>();
    match state.lock() {
        Ok(mut bp) => {
            bp.child = Some(child);
        }
        Err(e) => {
            log::error!("Failed to lock BackendProcess for init: {}", e);
        }
    }

    // Forward sidecar stdout/stderr to Tauri logs
    let app_handle = app.clone();
    tauri::async_runtime::spawn(async move {
        use tauri_plugin_shell::process::CommandEvent;
        while let Some(event) = rx.recv().await {
            match event {
                CommandEvent::Stdout(line) => {
                    log::info!("[backend] {}", String::from_utf8_lossy(&line));
                }
                CommandEvent::Stderr(line) => {
                    let msg = String::from_utf8_lossy(&line);
                    log::info!("[backend] {}", msg);
                }
                CommandEvent::Terminated(payload) => {
                    log::warn!("Backend process terminated: {:?}", payload);
                    let _ = app_handle.emit("backend-crashed", ());
                    break;
                }
                CommandEvent::Error(err) => {
                    log::error!("Backend sidecar error: {}", err);
                    break;
                }
                _ => {}
            }
        }
    });

    // Health poll: wait for backend to be ready (blocking thread — no tokio dep needed)
    let app_handle = app.clone();
    std::thread::spawn(move || {
        let max_attempts = 60;
        let delay = std::time::Duration::from_millis(500);

        for attempt in 1..=max_attempts {
            // HTTP health check via single TCP connection
            if let Ok(mut stream) = std::net::TcpStream::connect("127.0.0.1:8425") {
                use std::io::{Read, Write};
                let _ = stream.set_read_timeout(Some(std::time::Duration::from_secs(2)));
                let request = "GET /health HTTP/1.1\r\nHost: 127.0.0.1:8425\r\nConnection: close\r\n\r\n";
                if stream.write_all(request.as_bytes()).is_ok() {
                    let mut response = String::new();
                    if stream.read_to_string(&mut response).is_ok()
                        && response.contains("200")
                        && response.contains("healthy")
                    {
                        log::info!(
                            "Backend ready after {} attempts ({:.1}s)",
                            attempt,
                            attempt as f64 * 0.5
                        );
                        let _ = app_handle.emit("backend-ready", ());
                        return;
                    }
                }
            }

            if attempt % 10 == 0 {
                log::info!(
                    "Waiting for backend... attempt {}/{}",
                    attempt,
                    max_attempts
                );
            }
            std::thread::sleep(delay);
        }

        log::error!("Backend failed to start within 30 seconds");
        let _ = app_handle.emit("backend-startup-failed", ());
    });

    Ok(())
}

fn kill_sidecar(app: &tauri::AppHandle) {
    let state = app.state::<Mutex<BackendProcess>>();
    match state.lock() {
        Ok(mut bp) => {
            if let Some(child) = bp.child.take() {
                log::info!("Killing backend sidecar...");
                let _ = child.kill();
            }
        }
        Err(e) => {
            log::error!("Failed to lock BackendProcess for cleanup: {}", e);
        }
    }; // Semicolon drops MutexGuard before `state`
}

#[cfg_attr(mobile, tauri::mobile_entry_point)]
pub fn run() {
    let mut builder = tauri::Builder::default()
        .plugin(tauri_plugin_dialog::init())
        .plugin(tauri_plugin_deep_link::init())
        .plugin(tauri_plugin_opener::init())
        .plugin(tauri_plugin_shell::init());

    #[cfg(desktop)]
    {
        builder = builder.plugin(tauri_plugin_single_instance::init(|app, argv, _cwd| {
            // When a second instance is spawned with an nxm:// URL, forward it to the existing window
            if let Some(url) = argv.iter().find(|a| a.starts_with("nxm://")) {
                let _ = app.emit("nxm-link", url);
            }
        }));
    }

    builder
        .manage(Mutex::new(BackendProcess { child: None }))
        .invoke_handler(tauri::generate_handler![detect_game_paths, launch_game])
        .setup(|app| {
            app.handle().plugin(
                tauri_plugin_log::Builder::default()
                    .level(log::LevelFilter::Info)
                    .build(),
            )?;

            // In release builds, spawn the backend sidecar
            if !cfg!(debug_assertions) {
                let handle = app.handle().clone();
                if let Err(e) = spawn_sidecar(app.handle()) {
                    log::error!("Failed to spawn backend sidecar: {}", e);
                    // Delay emission so frontend listeners have time to register
                    std::thread::spawn(move || {
                        std::thread::sleep(std::time::Duration::from_secs(2));
                        let _ = handle.emit("backend-startup-failed", ());
                    });
                }
            }

            Ok(())
        })
        .on_window_event(|window, event| {
            if let tauri::WindowEvent::Destroyed = event {
                if window.label() == "main" {
                    kill_sidecar(window.app_handle());
                }
            }
        })
        .run(tauri::generate_context!())
        .expect("error while running tauri application");
}
