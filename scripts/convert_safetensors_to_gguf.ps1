Set-StrictMode -Version Latest
$ErrorActionPreference = 'Stop'

# Paths
$RepoRoot = Get-Location
$ModelDir = Join-Path $RepoRoot "models/gpt-oss-20b/original"
$WeightsPath = Join-Path $RepoRoot "models/gpt-oss-20b/original/model.safetensors"
$GgufPath = Join-Path $RepoRoot "models/gpt-oss-20b.gguf"
$ReportsDir = Join-Path $RepoRoot "reports"
$BackupsDir = Join-Path $RepoRoot "models/backups"
$LogPath = Join-Path $ReportsDir "convert_conversion.log"

function Initialize-Paths {
    if (-not (Test-Path $ReportsDir)) {
        New-Item -ItemType Directory -Path $ReportsDir | Out-Null
    }
    if (-not (Test-Path $BackupsDir)) {
        New-Item -ItemType Directory -Path $BackupsDir | Out-Null
    }
    "" | Set-Content -Path $LogPath -Encoding utf8
}

function Log {
    param(
        [Parameter(Mandatory = $true)][string] $Message
    )
    $timestamp = (Get-Date).ToString("s")
    $line = "$timestamp`t$Message"
    Add-Content -Path $LogPath -Value $line -Encoding utf8
    Write-Host $line
}

function Backup-Weights {
    if (-not (Test-Path $WeightsPath)) {
        Log "Weights not found at $WeightsPath. Conversion aborted."
        return $false
    }
    $stamp = Get-Date -Format "yyyyMMdd_HHmmss"
    $backupName = "model_$stamp.safetensors"
    $backupPath = Join-Path $BackupsDir $backupName
    Copy-Item -Path $WeightsPath -Destination $backupPath -Force
    Log "Created backup copy at $backupPath"
    return $true
}

function Run-Conversion {
    param(
        [Parameter(Mandatory = $true)][ScriptBlock] $Block,
        [Parameter(Mandatory = $true)][string] $Label
    )
    Log "Starting conversion attempt: $Label"
    try {
        & $Block
        $exitCode = $LASTEXITCODE
        if ($exitCode -ne 0) {
            Log "Attempt '$Label' exited with code $exitCode"
            return $false
        }
        if (Test-Path $GgufPath) {
            Log "Conversion succeeded via '$Label'"
            return $true
        }
        Log "Attempt '$Label' completed without creating gguf."
        return $false
    }
    catch {
        Log "Attempt '$Label' failed with exception: $($_.Exception.Message)"
        return $false
    }
}

function Try-MethodA {
    $block = {
        & python -m llama_cpp.convert_hf_to_gguf --model-weights $WeightsPath --output $GgufPath 2>&1 | ForEach-Object { Log $_ }
    }
    return Run-Conversion -Block $block -Label "llama_cpp.convert_hf_to_gguf (python -m)"
}

function Find-ConvertScript {
    $names = @("convert-hf-to-gguf.py", "convert_hf_to_gguf.py")
    foreach ($name in $names) {
        $candidate = Get-ChildItem -Path $RepoRoot -Filter $name -Recurse -ErrorAction SilentlyContinue | Select-Object -First 1
        if ($candidate) {
            return $candidate.FullName
        }
    }
    return $null
}

function Try-MethodB {
    $scriptPath = Find-ConvertScript
    if (-not $scriptPath) {
        Log "No convert-hf-to-gguf script located in repository."
        $quantizeCandidates = @(
            "/tmp/llama.cpp/quantize",
            (Join-Path $RepoRoot "quantize"),
            (Join-Path $RepoRoot "llama.cpp/quantize")
        )
    foreach ($qc in $quantizeCandidates) {
        if (Test-Path $qc) {
            Log "Found quantize binary at $qc (convert script still missing)."
        }
        }
        return $false
    }
    $block = {
        & python $scriptPath --outfile $GgufPath $ModelDir 2>&1 | ForEach-Object { Log $_ }
    }
    return Run-Conversion -Block $block -Label "convert-hf-to-gguf.py ($scriptPath)"
}

function Try-MethodC {
    $block = {
        $py = @"
import json
import os
import sys

from pathlib import Path

weights = Path(r"$WeightsPath").resolve()
out_path = Path(r"$GgufPath").resolve()
info = {"weights_exists": weights.exists(), "out_path": str(out_path)}

try:
    import transformers  # type: ignore
except Exception as exc:
    info["error"] = f"transformers missing: {exc}"
    print(json.dumps(info, indent=2))
    sys.exit(0)

print(json.dumps(info, indent=2))
sys.exit(0)
"@
        $py | python 2>&1 | ForEach-Object { Log $_ }
    }
    $result = Run-Conversion -Block $block -Label "transformers fallback (no-op placeholder)"
    if (-not $result) {
        Log "Fallback placeholder executed; actual conversion requires available gguf converter."
    }
    return $false
}

Initialize-Paths
Log "Starting safetensors -> gguf conversion helper."

if (-not (Backup-Weights)) {
    Log "Backup step failed or weights missing; stopping conversion attempts."
    exit 0
}

$methods = @(
    { Try-MethodA },
    { Try-MethodB },
    { Try-MethodC }
)

foreach ($m in $methods) {
    $success = & $m
    if ($success) {
        Log "Conversion finished successfully."
        exit 0
    }
}

Log "All conversion methods exhausted; gguf not produced. Install llama_cpp with convert helper or provide convert-hf-to-gguf.py."
exit 0
