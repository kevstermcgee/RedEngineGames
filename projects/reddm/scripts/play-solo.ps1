$ErrorActionPreference = 'Stop'
$wrapper = Join-Path $PSScriptRoot 'red.ps1'
$env:RE2_CHARACTER = 'human'
& $wrapper play-local
exit $LASTEXITCODE
