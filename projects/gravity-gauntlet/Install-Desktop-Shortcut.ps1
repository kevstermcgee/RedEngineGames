$ErrorActionPreference = 'Stop'
$desktop = [Environment]::GetFolderPath('Desktop')
$launcher = Join-Path $PSScriptRoot 'Play-Gravity-Gauntlet.cmd'
$shortcutPath = Join-Path $desktop 'Gravity Gauntlet (RedEngine).lnk'
$shortcut = (New-Object -ComObject WScript.Shell).CreateShortcut($shortcutPath)
$shortcut.TargetPath = $launcher
$shortcut.WorkingDirectory = $PSScriptRoot
$shortcut.Description = 'Play Gravity Gauntlet, the high-octane RedEngine 3D physics gauntlet.'
$shortcut.IconLocation = "$env:SystemRoot\System32\SHELL32.dll,137"
$shortcut.Save()
Write-Host "Created $shortcutPath" -ForegroundColor Green
