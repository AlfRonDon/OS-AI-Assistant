Param(
    [string]$LogsRoot = "logs",
    [int]$ArchiveOlderThanDays = 7,
    [int]$DeleteOlderThanDays = 90
)

Set-StrictMode -Version Latest
$ErrorActionPreference = "Stop"

$logsPath = [System.IO.Path]::GetFullPath($LogsRoot)
$archiveDir = Join-Path -Path $logsPath -ChildPath "archive"
New-Item -ItemType Directory -Force -Path $archiveDir | Out-Null

$archiveName = "{0}_logs.tar.gz" -f (Get-Date -Format "yyyyMMdd")
$archivePath = Join-Path -Path $archiveDir -ChildPath $archiveName

$archiveCutoff = (Get-Date).AddDays(-$ArchiveOlderThanDays)
$deleteCutoff = (Get-Date).AddDays(-$DeleteOlderThanDays)

$candidates = Get-ChildItem -LiteralPath $logsPath -Recurse -File -ErrorAction SilentlyContinue |
    Where-Object { $_.FullName -notlike "$archiveDir*" }

$filesToArchive = $candidates | Where-Object { $_.LastWriteTime -lt $archiveCutoff }

if ($filesToArchive.Count -gt 0) {
    $tar = Get-Command tar -ErrorAction SilentlyContinue
    if ($null -eq $tar) {
        Write-Warning "tar not available; skipping archive creation."
    }
    else {
        Push-Location $logsPath
        $relativeFiles = $filesToArchive | ForEach-Object { (Resolve-Path -LiteralPath $_.FullName -Relative) }
        tar -czf $archivePath -- $relativeFiles
        Pop-Location
        if ($LASTEXITCODE -eq 0) {
            Write-Host "Archived $($filesToArchive.Count) log file(s) to $archivePath"
        }
        else {
            Write-Warning "tar exited with code $LASTEXITCODE; archive may be incomplete."
        }
    }
}
else {
    Write-Host "No logs older than $ArchiveOlderThanDays day(s) to archive."
}

$filesToDelete = $candidates | Where-Object { $_.LastWriteTime -lt $deleteCutoff }
foreach ($file in $filesToDelete) {
    Remove-Item -LiteralPath $file.FullName -Force
}

if ($filesToDelete.Count -gt 0) {
    Write-Host "Deleted $($filesToDelete.Count) log file(s) older than $DeleteOlderThanDays day(s)."
}
else {
    Write-Host "No logs older than $DeleteOlderThanDays day(s) to delete."
}
