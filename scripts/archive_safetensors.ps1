# AUTO-ARCHIVE DISABLED BY USER PREFERENCE
Throw "archive_safetensors.ps1 cannot run automatically. Run manually only."

Param(
    [Parameter(Mandatory = $true)]
    [string]$SourcePath,
    [Parameter(Mandatory = $true)]
    [string]$DestinationPath
)

# Example usage:
#   .\scripts\archive_safetensors.ps1 -SourcePath ".\models\gpt-oss-20b\original\model.safetensors" -DestinationPath "D:\model_archives\gpt-oss-20b\model.safetensors"

Write-Host "Source: $SourcePath"
Write-Host "Destination: $DestinationPath"

if (!(Test-Path $SourcePath)) {
    Write-Error "SourcePath does not exist: $SourcePath"
    exit 1
}

$destDir = Split-Path $DestinationPath -Parent
if (!(Test-Path $destDir)) {
    New-Item -ItemType Directory -Path $destDir -Force | Out-Null
}

Write-Host "Copying file..."
Copy-Item $SourcePath $DestinationPath -Force

Write-Host "Computing SHA256 hashes..."
$srcHash = Get-FileHash $SourcePath -Algorithm SHA256
$dstHash = Get-FileHash $DestinationPath -Algorithm SHA256

Write-Host "Source SHA256: $($srcHash.Hash)"
Write-Host "Dest   SHA256: $($dstHash.Hash)"

if ($srcHash.Hash -ne $dstHash.Hash) {
    Write-Error "Hash mismatch! Archive verification failed."
    exit 2
}

# Write a small report in reports/
$reportDir = Join-Path (Get-Location) "reports"
if (!(Test-Path $reportDir)) {
    New-Item -ItemType Directory -Path $reportDir -Force | Out-Null
}
$reportPath = Join-Path $reportDir "archive_safetensors_$(Get-Date -Format 'yyyyMMdd_HHmmss').txt"
"Source: $SourcePath" | Out-File $reportPath -Encoding UTF8
"Destination: $DestinationPath" | Out-File $reportPath -Encoding UTF8 -Append
"SHA256: $($srcHash.Hash)" | Out-File $reportPath -Encoding UTF8 -Append

Write-Host "Archive OK. Report: $reportPath"
