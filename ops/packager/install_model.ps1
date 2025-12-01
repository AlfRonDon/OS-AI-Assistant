param(
    [string]$SourceModel = "",
    [string]$TargetPath = "models/gpt-oss-20b.gguf"
)

$ErrorActionPreference = 'Stop'
$scriptDir = Split-Path -Parent $MyInvocation.MyCommand.Definition
$candidateRoots = @(
    $scriptDir,
    (Resolve-Path (Join-Path $scriptDir '..') -ErrorAction SilentlyContinue),
    (Resolve-Path (Join-Path $scriptDir '..' '..') -ErrorAction SilentlyContinue)
)
$repoRoot = $candidateRoots | Where-Object { $_ -and (Test-Path (Join-Path $_ 'models')) } | Select-Object -First 1
if (-not $repoRoot) {
    throw "Unable to locate repo root (looked for a 'models' directory above $scriptDir)."
}

if (-not $SourceModel) {
    $SourceModel = Join-Path $scriptDir 'gpt-oss-20b.gguf'
}
if (-not (Test-Path $SourceModel)) {
    throw "Source model not found: $SourceModel"
}

$sourceResolved = Resolve-Path $SourceModel
$targetResolved = if ([IO.Path]::IsPathRooted($TargetPath)) { $TargetPath } else { Join-Path $repoRoot $TargetPath }
$targetDir = Split-Path -Parent $targetResolved
if (-not (Test-Path $targetDir)) {
    New-Item -ItemType Directory -Force -Path $targetDir | Out-Null
}

$ts = Get-Date -Format 'yyyyMMdd_HHmmss'
$backup = "$targetResolved.broken.$ts"
if (Test-Path $targetResolved) {
    Move-Item -Path $targetResolved -Destination $backup -Force
}
Copy-Item -Path $sourceResolved -Destination $targetResolved -Force

[Environment]::SetEnvironmentVariable('SKIP_AUTO_ARCHIVE', '1', 'User')
$env:SKIP_AUTO_ARCHIVE = '1'

python (Join-Path $repoRoot 'scripts/check_model_load.py') --model-path $targetResolved

Write-Output "Installed $targetResolved"
Write-Output "Backup (if prior file existed): $backup"
Write-Output "SKIP_AUTO_ARCHIVE persisted for current user"
