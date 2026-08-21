param(
    [int]$Port = 8001,
    [int]$CheckIntervalSeconds = 8,
    [int]$StartupTimeoutSeconds = 25,
    [switch]$SingleRun
)

$ErrorActionPreference = 'Stop'

$mutexName = "Global\SmartCarpoolingApp.BackendGuard.$Port"
$mutexCreated = $false
$script:guardMutex = New-Object System.Threading.Mutex($true, $mutexName, [ref]$mutexCreated)
if (-not $mutexCreated) {
    Write-Host ("[backend-guard] another guard is already running for port {0}. Exiting." -f $Port)
    exit 0
}

$repoRoot = Split-Path -Parent $PSScriptRoot
$backendDir = Join-Path $repoRoot 'backend'
$logDir = Join-Path $repoRoot '.runtime-logs'

if (-not (Test-Path $backendDir)) {
    throw "Backend directory not found: $backendDir"
}

if (-not (Test-Path $logDir)) {
    New-Item -Path $logDir -ItemType Directory | Out-Null
}

function Get-PythonPath {
    $candidates = @(
        'd:/FYP/.venv/Scripts/python.exe',
        (Join-Path $repoRoot '.venv/Scripts/python.exe'),
        (Join-Path $backendDir '.venv/Scripts/python.exe')
    )

    foreach ($candidate in $candidates) {
        if (Test-Path $candidate) {
            return $candidate
        }
    }

    $python = Get-Command python -ErrorAction SilentlyContinue
    if ($python) {
        return $python.Source
    }

    throw 'No Python executable found. Install Python or create a project venv first.'
}

function Test-BackendHealth {
    param([int]$CheckPort)

    try {
        $response = Invoke-WebRequest -Uri ("http://localhost:{0}/healthz" -f $CheckPort) -UseBasicParsing -TimeoutSec 4
        return $response.StatusCode -eq 200
    } catch {
        return $false
    }
}

function Start-BackendProcess {
    param(
        [string]$PythonExe,
        [string]$WorkingDir,
        [string]$LogsDir,
        [int]$ApiPort
    )

    $stamp = Get-Date -Format 'yyyyMMdd-HHmmss'
    $stdoutLog = Join-Path $LogsDir ("backend-{0}-stdout.log" -f $stamp)
    $stderrLog = Join-Path $LogsDir ("backend-{0}-stderr.log" -f $stamp)

    $args = @(
        '-m',
        'uvicorn',
        'app.main:app',
        '--host',
        '0.0.0.0',
        '--port',
        "$ApiPort"
    )

    $proc = Start-Process `
        -FilePath $PythonExe `
        -ArgumentList $args `
        -WorkingDirectory $WorkingDir `
        -RedirectStandardOutput $stdoutLog `
        -RedirectStandardError $stderrLog `
        -PassThru

    Write-Host ("[backend-guard] started PID {0} on port {1}" -f $proc.Id, $ApiPort)
    Write-Host ("[backend-guard] logs: {0} | {1}" -f $stdoutLog, $stderrLog)

    return $proc
}

$pythonExe = Get-PythonPath
$backendProcess = $null

if ($SingleRun -and (Test-BackendHealth -CheckPort $Port)) {
    Write-Host ("[backend-guard] healthy at http://localhost:{0}/healthz" -f $Port)
    exit 0
}

while ($true) {
    $healthy = Test-BackendHealth -CheckPort $Port

    if (-not $healthy) {
        if ($backendProcess -and -not $backendProcess.HasExited) {
            try {
                Stop-Process -Id $backendProcess.Id -Force -ErrorAction SilentlyContinue
            } catch {
                # Ignore stale process cleanup errors.
            }
        }

        $backendProcess = Start-BackendProcess -PythonExe $pythonExe -WorkingDir $backendDir -LogsDir $logDir -ApiPort $Port

        $deadline = (Get-Date).AddSeconds($StartupTimeoutSeconds)
        do {
            if (Test-BackendHealth -CheckPort $Port) {
                Write-Host ("[backend-guard] backend is healthy on port {0}" -f $Port)
                break
            }
            Start-Sleep -Seconds 1
        } while ((Get-Date) -lt $deadline)

        if (-not (Test-BackendHealth -CheckPort $Port)) {
            Write-Warning ("[backend-guard] backend still unhealthy after {0}s" -f $StartupTimeoutSeconds)
            if ($SingleRun) {
                exit 1
            }
        } elseif ($SingleRun) {
            exit 0
        }
    } elseif ($SingleRun) {
        Write-Host ("[backend-guard] healthy at http://localhost:{0}/healthz" -f $Port)
        exit 0
    }

    Start-Sleep -Seconds $CheckIntervalSeconds
}
