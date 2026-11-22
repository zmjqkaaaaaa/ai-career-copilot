param([switch]$NoBrowser)

$ErrorActionPreference = 'Stop'
$project = Split-Path -Parent $PSScriptRoot
$logs = Join-Path $project 'work/desktop-launcher'
$homeUrl = 'http://127.0.0.1:5173/'
$apiUrl = 'http://127.0.0.1:8001/health'

function Test-Page($uri, $marker) {
    try {
        $response = Invoke-WebRequest -Uri $uri -UseBasicParsing -TimeoutSec 2
        return $response.StatusCode -eq 200 -and $response.Content -match $marker
    } catch {
        return $false
    }
}

function Test-DatabasePort {
    $connection = New-Object Net.Sockets.TcpClient
    try {
        return $connection.ConnectAsync('127.0.0.1', 3308).Wait(300) -and $connection.Connected
    } catch {
        return $false
    } finally {
        $connection.Dispose()
    }
}

function Wait-Service($name, [scriptblock]$probe) {
    $deadline = (Get-Date).AddSeconds(25)
    do {
        if (& $probe) { return }
        Start-Sleep -Milliseconds 350
    } while ((Get-Date) -lt $deadline)
    throw "$name did not start. Check the logs in $logs."
}

function Start-ServiceProcess($name, $file, $arguments, $directory) {
    New-Item -ItemType Directory -Path $logs -Force | Out-Null
    Start-Process -FilePath $file -ArgumentList $arguments -WorkingDirectory $directory -WindowStyle Hidden `
        -RedirectStandardOutput (Join-Path $logs "$name.out.log") `
        -RedirectStandardError (Join-Path $logs "$name.err.log")
}

try {
    if (-not (Test-DatabasePort)) {
        $python = Join-Path $project 'backend/.venv/Scripts/python.exe'
        Start-ServiceProcess 'mysql' $python 'scripts/start_local_mysql.py' $project
        Wait-Service 'MySQL' { Test-DatabasePort }
    }
    if (-not (Test-Page $apiUrl '"status"\s*:\s*"ok"')) {
        $python = Join-Path $project 'backend/.venv/Scripts/python.exe'
        Start-ServiceProcess 'api' $python '-m uvicorn app.main:create_app --factory --host 127.0.0.1 --port 8001' (Join-Path $project 'backend')
        Wait-Service 'API' { Test-Page $apiUrl '"status"\s*:\s*"ok"' }
    }
    if (-not (Test-Page $homeUrl 'AI Career Copilot')) {
        Start-ServiceProcess 'frontend' $env:ComSpec '/d /c npm.cmd run dev' (Join-Path $project 'frontend')
        Wait-Service 'Web page' { Test-Page $homeUrl 'AI Career Copilot' }
    }
    if ($NoBrowser) { return }

    $edge = @(${env:ProgramFiles(x86)}, $env:ProgramFiles) | Where-Object { $_ } |
        ForEach-Object { Join-Path $_ 'Microsoft/Edge/Application/msedge.exe' } |
        Where-Object { Test-Path -LiteralPath $_ } | Select-Object -First 1
    if ($edge) {
        Start-Process -FilePath $edge -ArgumentList "--app=$homeUrl"
    } else {
        Start-Process $homeUrl
    }
} catch {
    if ($NoBrowser) { throw }
    Add-Type -AssemblyName System.Windows.Forms
    [Windows.Forms.MessageBox]::Show($_.Exception.Message, 'AI Career Copilot') | Out-Null
    exit 1
}
