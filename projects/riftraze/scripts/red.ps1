# scripts/red.ps1: the Windows-native twin of scripts/red (same commands and env vars).
#   powershell -File scripts\red.ps1 doctor | check | build-all | info | serve | play [HOST:PORT] | status ... | <any red_engine2 command>
param([Parameter(Position = 0)][string]$Cmd = 'help', [Parameter(ValueFromRemainingArguments = $true)][string[]]$Rest)
$ErrorActionPreference = 'Stop'
$Root = Split-Path -Parent $PSScriptRoot
Set-Location $Root
$env:CARGO_TERM_COLOR = 'never'
$cargoBin = Join-Path $HOME '.cargo\bin'
if ((Test-Path $cargoBin) -and (($env:PATH -split ';') -notcontains $cargoBin)) { $env:PATH = "$cargoBin;$env:PATH" }
$game = Get-Content game.json -Raw | ConvertFrom-Json

$Engine = $env:RED_ENGINE
if (-not $Engine -and $game.engine.path) { $p = if ([IO.Path]::IsPathRooted($game.engine.path)) { $game.engine.path } else { Join-Path $Root $game.engine.path }; if (Test-Path $p) { $Engine = (Resolve-Path $p).Path } }
if (-not $Engine) {
    $Engine = Join-Path $Root '.red\engine'
    $ref = if ($game.engine.ref) { $game.engine.ref } else { 'master' }
    $update = $env:RED_UPDATE -eq '1'
    if (-not (Test-Path (Join-Path $Engine '.git'))) { Write-Host "red: cloning the engine ($($game.engine.git)) into .red\engine ..."; git clone --quiet $game.engine.git $Engine; $update = $true }
    if ($update) { git -C $Engine fetch --quiet --tags origin; git -C $Engine checkout --quiet --detach "origin/$ref" 2>$null; if ($LASTEXITCODE -ne 0) { git -C $Engine checkout --quiet --detach $ref } }
}
if (-not (Test-Path (Join-Path $Engine 'Cargo.toml'))) { Write-Error "red: no engine at '$Engine' (fix game.json engine or set RED_ENGINE)"; exit 2 }
$Profile_ = if ($env:RED_PROFILE) { $env:RED_PROFILE } else { 'debug' }
$PFlag = if ($Profile_ -eq 'release') { @('--release') } else { @() }
$Target = if ($env:CARGO_TARGET_DIR) { $env:CARGO_TARGET_DIR } else { Join-Path $Engine 'target' }
function Exe([string]$n) { Join-Path $Target "$Profile_\$n.exe" }

$rebuild = $env:RED_REBUILD -eq '1'
if ($Cmd -eq '--rebuild') {
    $rebuild = $true
    $Cmd = if ($Rest.Count -gt 0) { $Rest[0] } else { 'help' }
    $Rest = @($Rest | Select-Object -Skip 1)
}
if ($Cmd -in 'help', '-h', '--help') { Get-Content $PSCommandPath -TotalCount 2 | ForEach-Object { $_ -replace '^# ?', '' }; exit 0 }
if ($Cmd -eq 'doctor') {
    "project  $Root"; "engine   $Engine"
    if (Get-Command cargo -ErrorAction SilentlyContinue) { "cargo    $(cargo --version)" } else { 'cargo    NOT FOUND (install Rust: https://rustup.rs)' }
    foreach ($b in 'red_engine2', 'red_server', 're2') { if (Test-Path (Exe $b)) { "built    $b" } else { "missing  $b (built on first use)" } }
    exit 0
}
if (-not (Get-Command cargo -ErrorAction SilentlyContinue)) { Write-Error 'red: cargo not found (install Rust: https://rustup.rs)'; exit 127 }
if ($Rest.Count -gt 0 -and $Rest[0] -eq '--rebuild') { $rebuild = $true; $Rest = @($Rest | Select-Object -Skip 1) }
$mode = if ($env:RED_HEADLESS -eq '1') { 'headless' } else { 'default' }
$features = if ($mode -eq 'headless') { @('--no-default-features') } else { @() }
if ($mode -eq 'headless' -and $Cmd -eq 'play') { Write-Error 'red: play needs graphics; unset RED_HEADLESS'; exit 2 }
$required = @('red_engine2'); if ($Cmd -eq 'serve') { $required += 'red_server' }; if ($Cmd -eq 'play') { $required += 're2' }
function Needs-Build([string]$n) {
    $out = Exe $n; if ($rebuild -or -not (Test-Path $out)) { return $true }
    $stamp = Join-Path $Target "$Profile_\.red-wrapper-$n.mode"
    if (-not (Test-Path $stamp) -or (Get-Content $stamp -Raw) -ne $mode) { return $true }
    $inputs = @((Join-Path $Engine 'Cargo.toml'), (Join-Path $Engine 'Cargo.lock'), (Join-Path $Engine 'build.rs'))
    $inputs += Get-ChildItem (Join-Path $Engine 'src'), (Join-Path $Engine 'assets') -Recurse -File -ErrorAction SilentlyContinue | Select-Object -ExpandProperty FullName
    $built = (Get-Item $out).LastWriteTimeUtc
    return $null -ne ($inputs | Where-Object { (Test-Path $_) -and (Get-Item $_).LastWriteTimeUtc -gt $built } | Select-Object -First 1)
}
$build = $false; $bins = @()
foreach ($b in $required) { $bins += @('--bin', $b); if (Needs-Build $b) { $build = $true } }
if ($build) {
    Write-Host 'red: building required engine binaries ...'
    & cargo build --quiet @PFlag @features --manifest-path (Join-Path $Engine 'Cargo.toml') @bins
    if ($LASTEXITCODE -ne 0) { exit $LASTEXITCODE }
    foreach ($b in $required) { Set-Content -NoNewline -Path (Join-Path $Target "$Profile_\.red-wrapper-$b.mode") -Value $mode }
}

$cli = Exe 'red_engine2'
switch ($Cmd) {
    { $_ -in 'check', 'build-all', 'info', 'serve', 'play' } { & $cli game $Cmd @Rest }
    default { & $cli $Cmd @Rest }
}
exit $LASTEXITCODE
