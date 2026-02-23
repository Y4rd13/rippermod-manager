# Build backend as standalone executable via PyInstaller
# Called by Tauri's beforeBuildCommand for release builds

$ErrorActionPreference = "Stop"

Write-Host "Building backend with PyInstaller..."
Push-Location "$PSScriptRoot\..\backend"

try {
    uv sync --extra build
    uv run pyinstaller rmm-backend.spec --clean --noconfirm

    $dest = "$PSScriptRoot\..\frontend\src-tauri\binaries"
    New-Item -ItemType Directory -Force -Path $dest | Out-Null
    Copy-Item "dist\rmm-backend.exe" "$dest\rmm-backend-x86_64-pc-windows-msvc.exe" -Force

    Write-Host "Backend binary copied to $dest"
} finally {
    Pop-Location
}
