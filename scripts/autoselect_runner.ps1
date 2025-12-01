#!/usr/bin/env pwsh
[CmdletBinding()]
param(
    [string]$PolicyPath
)

$ErrorActionPreference = 'Stop'
$scriptRoot = Split-Path -Parent $MyInvocation.MyCommand.Path
if (-not $PolicyPath) {
    $PolicyPath = Join-Path $scriptRoot "autoselect_policy.json"
}
$root = Split-Path -Parent $scriptRoot
$modelsDir = Join-Path $root "models"
$reportsDir = Join-Path $root "reports"
$logPath = Join-Path $reportsDir "autoselect.log"

New-Item -ItemType Directory -Force -Path $reportsDir | Out-Null
New-Item -ItemType Directory -Force -Path (Join-Path $modelsDir "backups") | Out-Null

function Write-Log([string]$Message) {
    $ts = Get-Date -Format "yyyy-MM-ddTHH:mm:ssK"
    Add-Content -Path $logPath -Value "$ts`t$Message"
}

if (-not (Test-Path $PolicyPath)) {
    throw "Policy file not found: $PolicyPath"
}

$policy = Get-Content -Path $PolicyPath -Raw | ConvertFrom-Json
$ramLow = [double]$policy.ram_low_gb
$ramMed = [double]$policy.ram_medium_gb
$preferred = [string]$policy.preferred_variant
$fallback = [string]$policy.fallback_variant

$osInfo = Get-CimInstance Win32_OperatingSystem
$freeGB = [math]::Round(($osInfo.FreePhysicalMemory / 1MB), 2)

$chosen = $fallback
$reason = "fallback"
if ($freeGB -ge $ramMed) {
    $chosen = $preferred
    $reason = "free>=ram_medium_gb"
} elseif ($freeGB -ge $ramLow) {
    $chosen = $preferred
    $reason = "free>=ram_low_gb"
}

$src = Join-Path $modelsDir ("gpt-oss-20b-{0}.gguf" -f $chosen)
$dest = Join-Path $modelsDir "gpt-oss-20b.gguf"
$backupDir = Join-Path $modelsDir "backups"
$backup = Join-Path $backupDir ("gpt-oss-20b.gguf.bak.{0}" -f (Get-Date -Format "yyyyMMdd_HHmmss"))

if (-not (Test-Path $src)) {
    throw "Chosen variant missing: $src"
}

$alreadyActive = $false
if (Test-Path $dest) {
    if ((Get-Item $dest).Length -eq (Get-Item $src).Length) {
        $alreadyActive = $true
    }
    if (-not $alreadyActive) {
        try {
            Copy-Item $dest $backup -Force
        } catch {
            Write-Log "backup_failed=$($_.Exception.Message)"
            $backup = $null
        }
    }
}

if (-not $alreadyActive) {
    $tempDest = "$dest.tmp.$([Guid]::NewGuid().ToString())"
    Copy-Item $src $tempDest -Force
    Move-Item $tempDest $dest -Force
}

Write-Log "free_gb=$freeGB; chosen=$chosen; reason=$reason; src=$src; dest=$dest; backup=$backup; already_active=$alreadyActive"
Write-Output "Chosen variant: $chosen (free_gb=$freeGB) already_active=$alreadyActive"
