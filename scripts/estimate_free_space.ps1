Param(
    [string]$ModelsPath = "models",
    [string]$OriginalModelPath = "models/gpt-oss-20b/original/model.safetensors",
    [string]$ReportJson = "reports/space_estimate.json",
    [string]$ReportText = "reports/space_estimate.txt"
)

Set-StrictMode -Version Latest
$ErrorActionPreference = "Stop"

function Get-DirectorySizeBytes {
    param(
        [Parameter(Mandatory = $true)][string]$Path
    )

    if (-not (Test-Path -LiteralPath $Path)) {
        return 0
    }

    $result = Get-ChildItem -LiteralPath $Path -Recurse -Force -ErrorAction SilentlyContinue |
        Measure-Object -Property Length -Sum
    return [int64]($result.Sum)
}

function Format-GB {
    param([double]$Bytes)
    return "{0:N2} GB" -f ($Bytes / 1GB)
}

New-Item -ItemType Directory -Force -Path (Split-Path -Parent $ReportJson) | Out-Null
New-Item -ItemType Directory -Force -Path (Split-Path -Parent $ReportText) | Out-Null

$modelsSize = Get-DirectorySizeBytes -Path $ModelsPath
$originalDir = Split-Path -Parent $OriginalModelPath
$originalSize = Get-DirectorySizeBytes -Path $originalDir

$driveInfo = Get-PSDrive -PSProvider FileSystem | ForEach-Object {
    $used = $_.Used
    if ($null -eq $used) {
        $used = 0
    }

    [ordered]@{
        name        = $_.Name
        root        = $_.Root
        free_bytes  = [int64]$_.Free
        used_bytes  = [int64]$used
        total_bytes = [int64]($used + $_.Free)
    }
}

$report = [ordered]@{
    timestamp          = (Get-Date).ToString("s")
    drives             = @($driveInfo)
    paths              = [ordered]@{
        models           = [ordered]@{
            path       = $ModelsPath
            size_bytes = $modelsSize
        }
        original_model   = [ordered]@{
            path       = $originalDir
            size_bytes = $originalSize
        }
    }
    reclaimable_bytes  = $originalSize
}

$report | ConvertTo-Json -Depth 6 | Out-File -FilePath $ReportJson -Encoding utf8

$text = @()
$text += "Space estimate report ($(Get-Date -Format u))"
$text += "Models directory: $ModelsPath -> $(Format-GB $modelsSize)"
$text += "Original safetensors directory: $originalDir -> $(Format-GB $originalSize)"
$text += "Estimated reclaimable by archiving: $(Format-GB $originalSize)"
$text += ""
$text += "Drive summary:"
foreach ($drive in $driveInfo) {
    $text += ("  {0} ({1}) Free: {2} / Total: {3}" -f $drive.name, $drive.root, (Format-GB $drive.free_bytes), (Format-GB $drive.total_bytes))
}

$text | Out-File -FilePath $ReportText -Encoding utf8

Write-Host "Wrote space estimate to $ReportJson and $ReportText"
