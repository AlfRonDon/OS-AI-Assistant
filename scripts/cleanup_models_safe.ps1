#!/usr/bin/env pwsh
[CmdletBinding()]
param(
    [string]$CandidatesPath,
    [string]$LogPath
)

$ErrorActionPreference = 'Stop'
function Write-Log {
    param([string]$Message)
    $line = "[{0}] {1}" -f (Get-Date -Format o), $Message
    Write-Host $line
    Add-Content -Path $LogPath -Value $line
}

$rootDir = [System.IO.Path]::GetFullPath([System.IO.Path]::Combine($PSScriptRoot, '..'))
if (-not $CandidatesPath) {
    $CandidatesPath = [System.IO.Path]::Combine($rootDir, 'reports', 'model_cleanup_candidates.json')
}
if (-not $LogPath) {
    $LogPath = [System.IO.Path]::Combine($rootDir, 'reports', 'model_cleanup_log.txt')
}

if (-not (Test-Path $CandidatesPath)) {
    throw "Candidates JSON not found: $CandidatesPath"
}
New-Item -ItemType File -Force -Path $LogPath | Out-Null

$json = Get-Content -Raw -Path $CandidatesPath | ConvertFrom-Json
$entries = @($json.entries)

$deletedCount = 0
$freedBytes = 0

foreach ($entry in $entries) {
    $path = $entry.path
    $delete = $entry.delete
    if (-not $delete) { continue }
    if (-not (Test-Path $path)) {
        Write-Log "Skip missing (already gone): $path"
        continue
    }
    try {
        $size = (Get-Item $path).Length
    } catch { $size = 0 }
    try {
        Remove-Item -LiteralPath $path -Force
        $deletedCount++
        $freedBytes += [int64]$size
        Write-Log "Deleted $path (bytes=$size)"
    } catch {
        Write-Log "Failed to delete $path : $_"
    }
}

# Verify required models exist; attempt restore from latest backup if missing
$root = Split-Path -Parent $PSScriptRoot
$required = @(
    [System.IO.Path]::Combine($root, 'models', 'gpt-oss-20b.gguf'),
    [System.IO.Path]::Combine($root, 'models', 'gpt-oss-20b-q8_0.gguf'),
    [System.IO.Path]::Combine($root, 'models', 'gpt-oss-20b-q4_0.gguf'),
    [System.IO.Path]::Combine($root, 'models', 'gpt-oss-20b-q4_K_M.gguf')
)
$backupsDir = [System.IO.Path]::Combine($root, 'models', 'backups')

foreach ($req in $required) {
    if (-not (Test-Path $req)) {
        Write-Log "Required file missing: $req. Attempting restore from latest backup."
        $stem = Split-Path -Leaf $req
        $pattern = "$stem*"
        $backupCandidate = Get-ChildItem -Path $backupsDir -File -Filter $pattern -ErrorAction SilentlyContinue | Sort-Object LastWriteTime -Descending | Select-Object -First 1
        if ($backupCandidate) {
            Copy-Item -Path $backupCandidate.FullName -Destination $req -Force
            Write-Log "Restored $req from backup $($backupCandidate.FullName)"
        } else {
            Write-Log "No backup found for $req. Aborting."
            exit 1
        }
    }
}

Write-Log "Cleanup complete. Deleted=$deletedCount freed_bytes=$freedBytes"

exit 0
