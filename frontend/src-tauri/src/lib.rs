use serde::Serialize;

#[derive(Debug, Serialize, Clone)]
pub struct DetectedGame {
    pub path: String,
    pub source: String,
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

    // Check both 64-bit and 32-bit registry views
    for root in [HKEY_LOCAL_MACHINE, HKEY_LOCAL_MACHINE] {
        let reg = RegKey::predef(root);
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

#[cfg_attr(mobile, tauri::mobile_entry_point)]
pub fn run() {
    tauri::Builder::default()
        .plugin(tauri_plugin_dialog::init())
        .invoke_handler(tauri::generate_handler![detect_game_paths])
        .setup(|app| {
            if cfg!(debug_assertions) {
                app.handle().plugin(
                    tauri_plugin_log::Builder::default()
                        .level(log::LevelFilter::Info)
                        .build(),
                )?;
            }
            Ok(())
        })
        .run(tauri::generate_context!())
        .expect("error while running tauri application");
}
