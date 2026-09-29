$ErrorActionPreference = 'Stop'
$desktop = [Environment]::GetFolderPath('Desktop')
$launcher = Join-Path $PSScriptRoot 'Play-Domino-Dynamo.cmd'
$shortcutPath = Join-Path $desktop 'Domino Dynamo (RedEngine).lnk'
$shortcut = (New-Object -ComObject WScript.Shell).CreateShortcut($shortcutPath)
$shortcut.TargetPath = $launcher
$shortcut.WorkingDirectory = $PSScriptRoot
$shortcut.Description = 'Play Domino Dynamo, the RedEngine chain-reaction game.'
$shortcut.IconLocation = "$env:SystemRoot\System32\SHELL32.dll,137"
$shortcut.Save()
Write-Host "Created $shortcutPath" -ForegroundColor Green
