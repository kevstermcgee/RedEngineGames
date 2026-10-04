# Signs the given files with the code-signing certificate in the repository secrets, when there is one. Without it the files are left unsigned and Windows SmartScreen
# will warn about them (see docs/DISTRIBUTION.md). Secrets: SIGN_PFX_BASE64 (the .pfx, base64) and SIGN_PFX_PASSWORD.
param([Parameter(Mandatory = $true, ValueFromRemainingArguments = $true)][string[]]$Files)

$ErrorActionPreference = 'Stop'
if (-not $env:SIGN_PFX_BASE64) {
    Write-Output 'No code-signing certificate configured: leaving the files unsigned.'
    exit 0
}
$signtool = Get-ChildItem 'C:\Program Files (x86)\Windows Kits\10\bin' -Recurse -Filter signtool.exe |
    Where-Object { $_.FullName -match '\\x64\\' } | Sort-Object FullName -Descending | Select-Object -First 1
if (-not $signtool) { throw 'signtool.exe was not found on this runner.' }
$pfx = Join-Path ([System.IO.Path]::GetTempPath()) 'codesign.pfx'
[IO.File]::WriteAllBytes($pfx, [Convert]::FromBase64String($env:SIGN_PFX_BASE64))
try {
    foreach ($file in $Files) {
        & $signtool.FullName sign /f $pfx /p $env:SIGN_PFX_PASSWORD /fd sha256 /tr http://timestamp.digicert.com /td sha256 $file
        if ($LASTEXITCODE -ne 0) { throw "signtool failed on $file" }
        & $signtool.FullName verify /pa $file | Out-Null
        if ($LASTEXITCODE -ne 0) { throw "the signature on $file does not verify" }
        Write-Output "signed $file"
    }
}
finally {
    Remove-Item -LiteralPath $pfx -Force -ErrorAction SilentlyContinue
}
