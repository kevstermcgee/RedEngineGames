$ErrorActionPreference = 'Stop'
$games = @('skyhook-sprint', 'domino-dynamo', 'storm-cell')

foreach ($game in $games) {
    $installer = Join-Path $PSScriptRoot "projects\$game\Install-Desktop-Shortcut.ps1"
    Write-Host "Installing $game..." -ForegroundColor Cyan
    & $installer
}

Write-Host 'All three RedEngine game shortcuts are ready on your Desktop.' -ForegroundColor Green
