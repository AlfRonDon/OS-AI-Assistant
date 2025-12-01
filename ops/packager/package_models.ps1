param(
    [string]$Version = "v1",
    [string]$ModelPath = "models/gpt-oss-20b.gguf"
)

$ErrorActionPreference = 'Stop'
$repoRoot = Resolve-Path (Join-Path $PSScriptRoot '..' '..')
$distDir = Join-Path $repoRoot 'dist'
New-Item -ItemType Directory -Force -Path $distDir | Out-Null

if (-not (Test-Path $ModelPath)) {
    throw "Model path not found: $ModelPath"
}
$modelFull = Resolve-Path $ModelPath
$modelDir = Split-Path -Parent $modelFull
$modelFile = Split-Path -Leaf $modelFull

$versionSafe = $Version -replace '[^A-Za-z0-9_.-]', '_'
$ts = Get-Date -Format 'yyyyMMdd_HHmmss'
$packageName = "models_${versionSafe}_${ts}.tar.gz"
$packagePath = Join-Path $distDir $packageName

tar -czf $packagePath -C $modelDir $modelFile

$modelHash = Get-FileHash -Algorithm SHA256 -Path $modelFull
$packageHash = Get-FileHash -Algorithm SHA256 -Path $packagePath
$checksumPath = Join-Path $distDir 'checksums.txt'
$checksumLines = @(
    "# generated $(Get-Date -Format 's')",
    "MODEL_SHA256 $($modelHash.Hash) $modelFile",
    "TAR_SHA256 $($packageHash.Hash) $packageName"
)
Set-Content -Path $checksumPath -Value $checksumLines

$installerTemplate = Join-Path $PSScriptRoot 'install_model.ps1'
if (Test-Path $installerTemplate) {
    Copy-Item -Path $installerTemplate -Destination (Join-Path $distDir 'install_model.ps1') -Force
}

Write-Output "Package created: $packagePath"
Write-Output "Checksums: $checksumPath"
