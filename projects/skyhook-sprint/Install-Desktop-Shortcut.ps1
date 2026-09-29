$ErrorActionPreference = 'Stop'
$desktop = [Environment]::GetFolderPath('Desktop')
$launcher = Join-Path $PSScriptRoot 'Play-Skyhook-Sprint.cmd'
$shortcutPath = Join-Path $desktop 'Skyhook Sprint (RedEngine).lnk'
$shortcut = (New-Object -ComObject WScript.Shell).CreateShortcut($shortcutPath)
$shortcut.TargetPath = $launcher
$shortcut.WorkingDirectory = $PSScriptRoot
$shortcut.Description = 'Play Skyhook Sprint, the RedEngine physics course.'
$shortcut.IconLocation = "$env:SystemRoot\System32\SHELL32.dll,137"
$shortcut.Save()
Write-Host "Created $shortcutPath" -ForegroundColor Green
