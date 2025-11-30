#!/usr/bin/env pwsh
[CmdletBinding()]
param(
    [Parameter(Mandatory = $true)]
    [string]$QType,
    [string]$OutputPath,
    [switch]$Force
)

$ErrorActionPreference = 'Stop'
$root = Split-Path -Parent $PSScriptRoot
$modelPath = Join-Path $root 'models/gpt-oss-20b.gguf'
if (-not $OutputPath) {
    $OutputPath = Join-Path $root ("models/gpt-oss-20b-{0}.gguf" -f $QType)
}
$logPath = Join-Path $root ("reports/quantize_{0}.log" -f $QType)
$backupDir = Join-Path $root 'models/backups'

New-Item -ItemType Directory -Force -Path (Split-Path $logPath) | Out-Null
New-Item -ItemType Directory -Force -Path (Split-Path $OutputPath) | Out-Null
New-Item -ItemType Directory -Force -Path $backupDir | Out-Null

$timestamp = Get-Date -Format 'yyyyMMddHHmmss'
if (Test-Path $logPath) {
    Copy-Item $logPath "$logPath.bak.$timestamp"
    Remove-Item $logPath
}

New-Item -ItemType File -Force -Path $logPath | Out-Null
function Write-Log {
    param([string]$Message)
    $line = "[{0}] {1}" -f (Get-Date -Format o), $Message
    Write-Host $line
    Add-Content -Path $logPath -Value $line
}

$exitCode = 0
try {
    Write-Log "[run_quantize.ps1] qtype=$QType output=$OutputPath"
    Write-Log "Root: $root"

    if (-not (Test-Path $modelPath)) {
        throw "Model not found at $modelPath"
    }

    if (Test-Path $OutputPath) {
        if (-not $Force.IsPresent) {
            Write-Log "Output $OutputPath already exists; skipping quantization."
            exit 0
        }
        $existingBackup = Join-Path $backupDir ("$(Split-Path -Leaf $OutputPath).bak.$timestamp")
        Move-Item $OutputPath $existingBackup
        Write-Log "Moved existing output to $existingBackup for backup"
    }

    $existingModelBackup = Get-ChildItem $backupDir -Filter 'gpt-oss-20b.gguf.bak.*' -ErrorAction SilentlyContinue | Select-Object -First 1
    if ($null -eq $existingModelBackup) {
        $backupPath = Join-Path $backupDir ("gpt-oss-20b.gguf.bak.$timestamp")
        Copy-Item $modelPath $backupPath
        Write-Log "Backed up original model to $backupPath"
    } else {
        Write-Log "Original backup already present: $($existingModelBackup.FullName)"
    }

    $tool = $null
    $toolType = $null
    if (Test-Path "/tmp/llama.cpp/quantize") {
        $tool = "/tmp/llama.cpp/quantize"
        $toolType = "llama.cpp binary (/tmp)"
    } elseif (Test-Path (Join-Path $root 'quantize')) {
        $tool = Join-Path $root 'quantize'
        $toolType = "llama.cpp binary (repo root)"
    } else {
        $ggufTools = Get-Command gguf-tools -ErrorAction SilentlyContinue
        if ($ggufTools) {
            $tool = $ggufTools.Source
            $toolType = "gguf-tools"
        }
    }

    if ($tool) {
        Write-Log "Using quantize tool: $toolType -> $tool"
        & $tool $modelPath $OutputPath $QType 2>&1 | Tee-Object -FilePath $logPath -Append
        $exitCode = $LASTEXITCODE
    } else {
        Write-Log "No external quantize binary detected; using python llama_cpp.llama_model_quantize"
        $env:MODEL_PATH = $modelPath
        $env:OUTPUT_PATH = $OutputPath
        $env:QTYPE = $QType
        @'
import os
import sys
import time
import importlib
from pathlib import Path

model_path = Path(os.environ["MODEL_PATH"])
output_path = Path(os.environ["OUTPUT_PATH"])
qtype_raw = os.environ.get("QTYPE", "").strip()

qtype_key = qtype_raw
if qtype_key.lower() == "q4_k_m":
    qtype_key = "q4_K_M"

try:
    llama_cpp = importlib.import_module("llama_cpp.llama_cpp")
except Exception as exc:  # pragma: no cover
    print(f"Failed to import llama_cpp: {exc}", file=sys.stderr)
    sys.exit(1)

qtype_map = {
    "q4_0": llama_cpp.LLAMA_FTYPE_MOSTLY_Q4_0,
    "q4_K_M": llama_cpp.LLAMA_FTYPE_MOSTLY_Q4_K_M,
    "q2": llama_cpp.LLAMA_FTYPE_MOSTLY_Q2_K,
    "q8_0": llama_cpp.LLAMA_FTYPE_MOSTLY_Q8_0,
}

if qtype_key not in qtype_map:
    print(f"Unsupported qtype: {qtype_raw}", file=sys.stderr)
    sys.exit(1)

params = llama_cpp.llama_model_quantize_default_params()
params.ftype = qtype_map[qtype_key]
params.nthread = max(os.cpu_count() or 1, 1)
params.allow_requantize = True
params.only_copy = False

output_path.parent.mkdir(parents=True, exist_ok=True)
start = time.time()
print(f"Starting python quantization via llama_cpp: qtype={qtype_key}, threads={params.nthread}")
ret = llama_cpp.llama_model_quantize(
    str(model_path).encode("utf-8"),
    str(output_path).encode("utf-8"),
    params,
)
elapsed = time.time() - start
print(f"llama_model_quantize returned {ret} in {elapsed:.2f}s")
sys.exit(0 if ret == 0 else (ret if isinstance(ret, int) else 1))
'@ | python - 2>&1 | Tee-Object -FilePath $logPath -Append
        $exitCode = $LASTEXITCODE
    }
}
catch {
    Write-Log $_
    $exitCode = 1
}

exit $exitCode
