# Ensure a dummy sidecar binary exists for Tauri dev builds.
# Tauri validates externalBin paths at compile time even in dev mode.
# In dev, the backend is run manually (uvicorn), so this is just a placeholder.

$binDir = "$PSScriptRoot\..\frontend\src-tauri\binaries"
$target = "$binDir\rmm-backend-x86_64-pc-windows-msvc.exe"

if (-not (Test-Path $target)) {
    New-Item -ItemType Directory -Force -Path $binDir | Out-Null
    Copy-Item "$env:windir\System32\where.exe" $target
    Write-Host "Created dev sidecar placeholder at $target"
}
