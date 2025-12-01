Param(
    [int]$RetentionCount = 3,
    [string]$BackupsPath = "models/backups",
    [string]$LogPath = "reports/rotate_backups.log"
)

Set-StrictMode -Version Latest
$ErrorActionPreference = "Stop"

function Write-Log {
    param([string]$Message)
    $timestamp = Get-Date -Format "yyyy-MM-dd HH:mm:ss"
    "$timestamp`t$Message" | Tee-Object -FilePath $LogPath -Append
}

New-Item -ItemType Directory -Force -Path (Split-Path -Parent $LogPath) | Out-Null

if (-not (Test-Path -LiteralPath $BackupsPath)) {
    Write-Log "Backups path '$BackupsPath' not found. Nothing to rotate."
    Write-Warning "Backups path missing."
    return
}

$backups = Get-ChildItem -LiteralPath $BackupsPath -File -ErrorAction SilentlyContinue |
    Sort-Object LastWriteTime -Descending

if ($backups.Count -le $RetentionCount) {
    Write-Log "Backups count ($($backups.Count)) <= retention ($RetentionCount). No deletion required."
    Write-Host "Nothing to delete."
    return
}

$toDelete = $backups | Select-Object -Skip $RetentionCount
Write-Log "Prepared to delete $($toDelete.Count) backup(s) older than latest $RetentionCount."

Write-Host "Backups scheduled for deletion:"
foreach ($file in $toDelete) {
    Write-Host ("  {0} ({1:N2} GB) - LastWrite {2}" -f $file.Name, ($file.Length / 1GB), $file.LastWriteTime)
}

$first = Read-Host "Confirm deletion of the above backups by typing YES"
if ($first -ne "YES") {
    Write-Log "First confirmation failed. Aborting rotation."
    Write-Host "Deletion cancelled."
    return
}

$second = Read-Host "Double-confirm by typing DELETE"
if ($second -ne "DELETE") {
    Write-Log "Second confirmation failed. Aborting rotation."
    Write-Host "Deletion cancelled."
    return
}

foreach ($file in $toDelete) {
    Remove-Item -LiteralPath $file.FullName -Force
    Write-Log "Deleted backup $($file.FullName) ($([math]::Round($file.Length / 1GB, 2)) GB)."
}

Write-Host "Backup rotation completed."
