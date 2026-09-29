$ErrorActionPreference = 'Stop'
$desktop = [Environment]::GetFolderPath('Desktop')
$launcher = Join-Path $PSScriptRoot 'Play-Storm-Cell.cmd'
$shortcutPath = Join-Path $desktop 'Storm Cell (RedEngine).lnk'
$shortcut = (New-Object -ComObject WScript.Shell).CreateShortcut($shortcutPath)
$shortcut.TargetPath = $launcher
$shortcut.WorkingDirectory = $PSScriptRoot
$shortcut.Description = 'Play Storm Cell, the RedEngine impulse-survival game.'
$shortcut.IconLocation = "$env:SystemRoot\System32\SHELL32.dll,137"
$shortcut.Save()
Write-Host "Created $shortcutPath" -ForegroundColor Green
