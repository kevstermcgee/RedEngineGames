$ErrorActionPreference = 'Stop'
$games = @('gravity-gauntlet', 'skyhook-sprint', 'domino-dynamo', 'storm-cell')

foreach ($game in $games) {
    $installer = Join-Path $PSScriptRoot "projects\$game\Install-Desktop-Shortcut.ps1"
    Write-Host "Installing $game..." -ForegroundColor Cyan
    & $installer
}

Write-Host 'All RedEngine game shortcuts are ready on your Desktop.' -ForegroundColor Green
