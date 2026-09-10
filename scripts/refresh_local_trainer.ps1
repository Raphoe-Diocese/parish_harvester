# Replace the Load unpacked Trainer folder from the live zip.
# Frank then only Reloads at chrome://extensions.
# Not Chrome Update. Work dir is %TEMP%, never a repo _tmp_* folder.

$ErrorActionPreference = "Stop"
$ZipUrl = "https://www.parishpress.ie/extension/parish_trainer.zip"
$Dest = Join-Path $PSScriptRoot "..\extension"
$Dest = [System.IO.Path]::GetFullPath($Dest)
$Work = Join-Path $env:TEMP "parish-trainer-refresh"

if (-not (Test-Path $Dest)) {
    throw "Trainer folder missing: $Dest"
}

if (Test-Path $Work) {
    Remove-Item -LiteralPath $Work -Recurse -Force
}
New-Item -ItemType Directory -Path $Work | Out-Null

$ZipPath = Join-Path $Work "parish_trainer.zip"
Write-Host "Downloading $ZipUrl"
Invoke-WebRequest -Uri $ZipUrl -OutFile $ZipPath -UseBasicParsing

$Extract = Join-Path $Work "extracted"
Expand-Archive -LiteralPath $ZipPath -DestinationPath $Extract -Force

$Manifest = Get-ChildItem -LiteralPath $Extract -Filter "manifest.json" -Recurse |
    Where-Object { $_.Name -eq "manifest.json" } |
    Select-Object -First 1
if (-not $Manifest) {
    throw "Zip has no manifest.json"
}
$Source = $Manifest.Directory.FullName

Get-ChildItem -LiteralPath $Dest -Force | ForEach-Object {
    Remove-Item -LiteralPath $_.FullName -Recurse -Force
}
Copy-Item -Path (Join-Path $Source "*") -Destination $Dest -Recurse -Force

$NewManifest = Join-Path $Dest "manifest.json"
if (-not (Test-Path $NewManifest)) {
    throw "Refresh left no manifest.json in $Dest (nested zip?)"
}

$Version = (Get-Content -LiteralPath $NewManifest -Raw | ConvertFrom-Json).version
Write-Host "Trainer folder refreshed to $Version"
Write-Host "Reload Parish Trainer at chrome://extensions"
