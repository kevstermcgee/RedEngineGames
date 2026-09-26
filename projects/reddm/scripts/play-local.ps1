$ErrorActionPreference = 'Stop'
$project = Split-Path -Parent $PSScriptRoot
$wrapper = Join-Path $PSScriptRoot 'red.ps1'

$server = Start-Process -FilePath 'powershell.exe' -WindowStyle Hidden -PassThru -WorkingDirectory $project -ArgumentList @(
    '-NoProfile', '-ExecutionPolicy', 'Bypass', '-File', $wrapper, 'serve'
)
try {
    Start-Sleep -Seconds 1
    & $wrapper play '127.0.0.1:27015'
} finally {
    if ($server -and -not $server.HasExited) {
        Stop-Process -Id $server.Id
    }
}
