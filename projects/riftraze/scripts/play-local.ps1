$ErrorActionPreference = 'Stop'
$project = Split-Path -Parent $PSScriptRoot
$wrapper = Join-Path $PSScriptRoot 'red.ps1'
$env:RE2_CHARACTER = 'human'

$server = Start-Process -FilePath 'powershell.exe' -WindowStyle Hidden -PassThru -WorkingDirectory $project -ArgumentList @(
    '-NoProfile', '-ExecutionPolicy', 'Bypass', '-File', $wrapper, 'serve'
)
try {
    Start-Sleep -Seconds 1
    & $wrapper play '127.0.0.1:27016'
} finally {
    if ($server -and -not $server.HasExited) {
        # The wrapper waits on red_engine2, which waits on red_server. Stop the entire exact tree
        # so closing the game never leaves the UDP server or its executable lock behind.
        & taskkill.exe /PID $server.Id /T /F 2>$null | Out-Null
    }
}
