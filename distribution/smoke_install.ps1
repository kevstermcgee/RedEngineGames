# Installs a built game the way a player would, updates it in place two ways (running the installer again, and the game's own update prompt answered automatically
# against a local server), starts it, and uninstalls it, checking at every step what a player would care about: shortcuts, the uninstall entry, saves that survive,
# stale files that do not. Runs on the release runner before anything is published.
param(
    [Parameter(Mandatory = $true)][string]$Installer,
    [Parameter(Mandatory = $true)][string]$Slug,
    [Parameter(Mandatory = $true)][string]$Name
)
$ErrorActionPreference = 'Stop'
$Installer = (Resolve-Path $Installer).Path
$app = Join-Path $env:RUNNER_TEMP "smoke-$Slug"
$saves = Join-Path $env:USERPROFILE "Saved Games\$Name"
function Check($ok, $what) { if (-not $ok) { throw "SMOKE FAILED: $what" } else { Write-Output "ok: $what" } }
function Install { param([string]$Exe) $p = Start-Process $Exe -ArgumentList "/VERYSILENT", "/SUPPRESSMSGBOXES", "/NORESTART", "/DIR=`"$app`"", "/TASKS=desktopicon" -Wait -PassThru; Check ($p.ExitCode -eq 0) "installer exit code $($p.ExitCode)" }
function StopGame { Get-Process -Name RedEngine -ErrorAction SilentlyContinue | Stop-Process -Force; Start-Sleep -Seconds 1 }

Remove-Item $app, $saves -Recurse -Force -ErrorAction SilentlyContinue

# 1. a fresh install
Install $Installer
foreach ($f in "Play-$Slug.exe", 'RedEngine.exe', 'play.cfg', 'launch.args', "content") { Check (Test-Path (Join-Path $app $f)) "installed: $f" }
Check ((Get-Content (Join-Path $app 'play.cfg') -Raw) -match 'mode=installed') 'play.cfg says installed'
$uninstallKey = Get-ChildItem 'HKCU:\Software\Microsoft\Windows\CurrentVersion\Uninstall' | Where-Object { (Get-ItemProperty $_.PSPath).DisplayName -eq $Name }
Check ($null -ne $uninstallKey) 'an uninstall entry is registered for the player'
$desktop = [Environment]::GetFolderPath('Desktop')
Check (Test-Path (Join-Path $desktop "$Name.lnk")) 'the desktop shortcut the installer offered exists'
Check (Test-Path (Join-Path ([Environment]::GetFolderPath('Programs')) "$Name.lnk")) 'the Start-menu entry exists'
StopGame

# 2. progress, and a file only the old version had
New-Item -ItemType Directory -Force $saves | Out-Null
Set-Content (Join-Path $saves 'progress.txt') 'day 12'
Set-Content (Join-Path $app 'content\stale.txt') 'from the old version'

# 3. the next installer over the top
Install $Installer
Check (-not (Test-Path (Join-Path $app 'content\stale.txt'))) 'an update removes files the new version no longer has'
Check ((Get-Content (Join-Path $saves 'progress.txt')) -eq 'day 12') 'the player''s saves survive an update'
StopGame

# 4. the game's own update prompt: a local server says a newer version exists, the answer is automatic
$current = [int]((Get-Content (Join-Path $app 'play.cfg') | Where-Object { $_ -like 'version=*' }) -replace 'version=', '')
$serve = Join-Path $env:RUNNER_TEMP "serve-$Slug"
New-Item -ItemType Directory -Force $serve | Out-Null
Copy-Item $Installer (Join-Path $serve 'newer-setup.exe')
$sha = (Get-FileHash -Algorithm SHA256 (Join-Path $serve 'newer-setup.exe')).Hash.ToLower()
$json = '{"slug":"' + $Slug + '","version":' + ($current + 1) + ',"installer":"http://127.0.0.1:8099/newer-setup.exe","sha256":"' + $sha + '","notes":"- test"}'
Set-Content (Join-Path $serve 'latest.json') $json
$server = Start-Process python -ArgumentList "-m", "http.server", "8099", "--bind", "127.0.0.1", "--directory", "`"$serve`"" -PassThru -WindowStyle Hidden
Start-Sleep -Seconds 2
Set-Content (Join-Path $app 'content\stale.txt') 'from the old version'
try {
    $env:RE2_UPDATE_URL = 'http://127.0.0.1:8099/latest.json'
    $env:RE2_UPDATE_ANSWER = 'update'
    Start-Process (Join-Path $app "Play-$Slug.exe") -WorkingDirectory $app
    $deadline = (Get-Date).AddSeconds(90)
    while ((Test-Path (Join-Path $app 'content\stale.txt')) -and (Get-Date) -lt $deadline) { Start-Sleep -Seconds 2 }
    Check (-not (Test-Path (Join-Path $app 'content\stale.txt'))) 'the game downloaded, verified and installed the newer version by itself'
    Check ((Get-Content (Join-Path $saves 'progress.txt')) -eq 'day 12') 'saves survive the in-game update too'
}
finally {
    Remove-Item Env:RE2_UPDATE_URL, Env:RE2_UPDATE_ANSWER -ErrorAction SilentlyContinue
    Stop-Process -Id $server.Id -Force -ErrorAction SilentlyContinue
}
Start-Sleep -Seconds 3
Check (-not (Test-Path (Join-Path $app 'launcher-error.txt'))) 'the launcher reported no error'
StopGame

# 5. uninstall leaves the saves (silent uninstall does not ask)
$unins = Get-ChildItem $app -Filter 'unins*.exe' | Select-Object -First 1
$p = Start-Process $unins.FullName -ArgumentList '/VERYSILENT', '/SUPPRESSMSGBOXES', '/NORESTART' -Wait -PassThru
Check ($p.ExitCode -eq 0) 'the uninstaller ran'
Start-Sleep -Seconds 2
Check (-not (Test-Path (Join-Path $app "Play-$Slug.exe"))) 'the game is gone after uninstall'
Check (Test-Path (Join-Path $saves 'progress.txt')) 'the saves are still there after uninstall'
Check (-not (Test-Path (Join-Path $desktop "$Name.lnk"))) 'the desktop shortcut is removed'
Remove-Item $saves -Recurse -Force -ErrorAction SilentlyContinue
Write-Output "smoke test passed for $Name"
