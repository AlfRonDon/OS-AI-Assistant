Param(
    [int]$BackupRetention = 3,
    [int]$DeleteLogsOlderThanDays = 90,
    [string]$BackupsPath = "models/backups",
    [string]$LogsRoot = "logs",
    [string]$OriginalModelPath = "models/gpt-oss-20b/original/model.safetensors",
    [string]$ReportPath = "reports/cleanup_dryrun.txt"
)

Set-StrictMode -Version Latest
$ErrorActionPreference = "Stop"

function Format-Size {
    param([double]$Bytes)
    return "{0:N2} GB" -f ($Bytes / 1GB)
}

New-Item -ItemType Directory -Force -Path (Split-Path -Parent $ReportPath) | Out-Null

$lines = @()
$lines += "Free-space dry run ($(Get-Date -Format u))"
$lines += "No changes were made; this is a report of what would be removed or relocated."
$lines += ""

$totalReclaimable = 0

if (Test-Path -LiteralPath $OriginalModelPath) {
    $origSize = (Get-Item -LiteralPath $OriginalModelPath).Length
    $totalReclaimable += $origSize
    $lines += "Archive candidate: $OriginalModelPath -> $(Format-Size $origSize)"
}
else {
    $lines += "Archive candidate missing: $OriginalModelPath"
}

if (Test-Path -LiteralPath $BackupsPath) {
    $backups = @(Get-ChildItem -LiteralPath $BackupsPath -File -ErrorAction SilentlyContinue |
        Sort-Object LastWriteTime -Descending)
    $oldBackups = @($backups | Select-Object -Skip $BackupRetention)

    if ($oldBackups.Count -gt 0) {
        $oldSize = ($oldBackups | Measure-Object -Property Length -Sum).Sum
        $totalReclaimable += $oldSize
        $lines += ""
        $lines += "Backups eligible for deletion (keep newest $BackupRetention): $($oldBackups.Count) file(s), $(Format-Size $oldSize)"
        foreach ($file in $oldBackups) {
            $lines += "  $($file.Name) | $(Format-Size $file.Length) | LastWrite $($file.LastWriteTime)"
        }
    }
    else {
        $lines += ""
        $lines += "Backups eligible for deletion: none (<= retention)."
    }
}
else {
    $lines += ""
    $lines += "Backups path missing: $BackupsPath"
}

$logsFull = [System.IO.Path]::GetFullPath($LogsRoot)
$archiveDir = Join-Path -Path $logsFull -ChildPath "archive"
$logCandidates = @()
if (Test-Path -LiteralPath $logsFull) {
    $logCandidates = @(Get-ChildItem -LiteralPath $logsFull -Recurse -File -ErrorAction SilentlyContinue |
        Where-Object { $_.FullName -notlike "$archiveDir*" -and $_.LastWriteTime -lt (Get-Date).AddDays(-$DeleteLogsOlderThanDays) })
}

if ($logCandidates.Count -gt 0) {
    $logSize = ($logCandidates | Measure-Object -Property Length -Sum).Sum
    $totalReclaimable += $logSize
    $lines += ""
    $lines += "Logs eligible for deletion (older than $DeleteLogsOlderThanDays day(s)): $($logCandidates.Count) file(s), $(Format-Size $logSize)"
    foreach ($log in $logCandidates) {
        $lines += "  $($log.FullName) | $(Format-Size $log.Length) | LastWrite $($log.LastWriteTime)"
    }
}
else {
    $lines += ""
    $lines += "Logs eligible for deletion: none."
}

$lines += ""
$lines += "Total potential reclaimable space: $(Format-Size $totalReclaimable)"

$lines | Out-File -FilePath $ReportPath -Encoding utf8
Write-Host "Dry-run report written to $ReportPath"
