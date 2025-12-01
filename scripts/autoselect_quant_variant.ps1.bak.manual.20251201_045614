# Auto-generated update by Codex agent on 2025-12-01T01:04:00Z
# Autoselect quantized variant based on policy in config/autoselect_policy.json

[CmdletBinding()]
param(
    [string]$PolicyPath = (Join-Path (Join-Path (Get-Location) "config") "autoselect_policy.json"),
    [switch]$DryRun
)

if ($env:AUTOSELECT_DRY_RUN -and $env:AUTOSELECT_DRY_RUN.ToString().ToLower() -in @("1", "true", "yes")) {
    $DryRun = $true
}

$repoRoot = Get-Location
$reportsDir = Join-Path $repoRoot "reports"
$logPath = Join-Path $reportsDir "autoselect.log"

if (-not (Test-Path $reportsDir)) {
    New-Item -ItemType Directory -Path $reportsDir -Force | Out-Null
}

function Write-AutoselectLog {
    param([string]$Message)
    $timestamp = Get-Date -Format "yyyy-MM-ddTHH:mm:ssK"
    Add-Content -Path $logPath -Value "$timestamp`t$Message"
}

function Load-Policy {
    param([string]$Path)
    if (-not (Test-Path $Path)) {
        throw "Policy file not found at $Path"
    }
    Get-Content -Path $Path -Raw | ConvertFrom-Json -ErrorAction Stop
}

try {
    $policy = Load-Policy -Path $PolicyPath
} catch {
    Write-Error $_.Exception.Message
    exit 1
}

$variants = @($policy.variants)
if (-not $variants) {
    Write-Error "variants list missing or empty in policy"
    exit 1
}

$os = Get-CimInstance Win32_OperatingSystem
$freeGB = [math]::Round(($os.FreePhysicalMemory / 1024 / 1024), 2)

$chosenVariant = $null
$reason = $null

if ($policy.force_variant) {
    $chosenVariant = $policy.force_variant
    $reason = "force_variant"
} elseif ($policy.rules) {
    $rules = @($policy.rules) | Sort-Object -Property min_free_gb -Descending
    foreach ($rule in $rules) {
        $min = [double]$rule.min_free_gb
        if ($freeGB -ge $min) {
            $chosenVariant = $rule.variant
            $reason = $rule.reason
            break
        }
    }
}

if (-not $chosenVariant) {
    $chosenVariant = $variants[-1]
    $reason = "fallback:last_variant"
}

if ($variants -notcontains $chosenVariant) {
    Write-Error "Chosen variant '$chosenVariant' not in variants allowlist."
    exit 1
}

$modelsDir = Join-Path $repoRoot "models"
$src = Join-Path $modelsDir "gpt-oss-20b-$chosenVariant.gguf"
$dest = Join-Path $modelsDir "gpt-oss-20b.gguf"
$backupPath = $null

if (-not $DryRun -and -not (Test-Path $src)) {
    Write-Error "Source variant not found: $src"
    exit 1
}

if (-not $DryRun) {
    $backupDir = Join-Path $modelsDir "backups"
    if (-not (Test-Path $backupDir)) {
        New-Item -ItemType Directory -Path $backupDir -Force | Out-Null
    }
    if (Test-Path $dest) {
        $timestamp = Get-Date -Format "yyyyMMdd_HHmmss"
        $backupPath = Join-Path $backupDir "gpt-oss-20b.gguf.bak.$timestamp"
        Copy-Item $dest $backupPath -Force
    }
    Copy-Item $src $dest -Force
    Write-Host "Swapped to variant: $chosenVariant (freeGB=$freeGB)"
} else {
    Write-Host "Dry-run: would swap to variant '$chosenVariant' (freeGB=$freeGB)"
}

Write-Host "Active model target: $dest"
Write-AutoselectLog "freeGB=$freeGB; chosen_variant=$chosenVariant; reason=$reason; dry_run=$DryRun; src=$src; dest=$dest; backup_path=$backupPath"
