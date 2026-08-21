param(
    [int]$Port = 3002,
    [switch]$WatchBackend
)

$ErrorActionPreference = 'Stop'

$repoRoot = Split-Path -Parent $PSScriptRoot
$frontendDir = Join-Path $repoRoot 'frontend'
$backendGuardScript = Join-Path $PSScriptRoot 'ensure-backend-8001.ps1'

if (-not (Test-Path $frontendDir)) {
    throw "Frontend directory not found: $frontendDir"
}

if (-not (Test-Path $backendGuardScript)) {
    throw "Backend guard script not found: $backendGuardScript"
}

if ($WatchBackend) {
    Start-Process powershell `
        -ArgumentList @('-ExecutionPolicy', 'Bypass', '-NoExit', '-File', $backendGuardScript) `
        -WindowStyle Normal | Out-Null

    Write-Host '[launcher] Started backend watchdog window.'
} else {
    & $backendGuardScript -SingleRun | Out-Null
    Write-Host '[launcher] Backend is healthy on 8001.'
}

$edgeProfileDir = Join-Path $repoRoot (".edge-profile-{0}" -f $Port)
if (-not (Test-Path $edgeProfileDir)) {
    New-Item -Path $edgeProfileDir -ItemType Directory | Out-Null
}

Push-Location $frontendDir
try {
    flutter run -d edge --web-port $Port --web-browser-flag "--user-data-dir=$edgeProfileDir"
} finally {
    Pop-Location
}
