[CmdletBinding()]
param(
    [string]$ModelPath = "models/gpt-oss-20b/original/model.safetensors",
    [string]$OutputPath = "models/gpt-oss-20b.gguf",
    [string]$LogPath = "reports/convert_conversion.log"
)

$ErrorActionPreference = "Stop"

function Resolve-RepoPath {
    param([string]$Path)

    if ([string]::IsNullOrWhiteSpace($Path)) {
        return $null
    }

    if (Test-Path -LiteralPath $Path) {
        return (Resolve-Path -LiteralPath $Path).Path
    }

    $repoRoot = Resolve-Path (Join-Path $PSScriptRoot "..")
    $candidate = Join-Path $repoRoot $Path
    if (Test-Path -LiteralPath $candidate) {
        return (Resolve-Path -LiteralPath $candidate).Path
    }

    return $null
}

$repoRoot = Resolve-Path (Join-Path $PSScriptRoot "..")
$resolvedLogPath = if (Split-Path -IsAbsolute $LogPath) { $LogPath } else { Join-Path $repoRoot $LogPath }
$logDir = Split-Path -Parent $resolvedLogPath
if (-not (Test-Path $logDir)) {
    New-Item -ItemType Directory -Force -Path $logDir | Out-Null
}
Set-Content -Path $resolvedLogPath -Value ("== convert_safetensors_to_gguf start {0}" -f (Get-Date -Format o)) -Encoding utf8

function Write-Log {
    param([string]$Message)

    $stamp = Get-Date -Format "yyyy-MM-ddTHH:mm:ssK"
    Add-Content -Path $resolvedLogPath -Value ("[{0}] {1}" -f $stamp, $Message) -Encoding utf8
}

function Run-Command {
    param([string[]]$CommandParts)

    Write-Log ("Running: {0}" -f ($CommandParts -join " "))
    try {
        $output = & @CommandParts 2>&1
        if ($output) {
            foreach ($line in ($output -split [Environment]::NewLine)) {
                if ($line -ne "") { Write-Log ("  {0}" -f $line) }
            }
        }
        return $LASTEXITCODE
    } catch {
        Write-Log ("Command failed to start: {0}" -f $_.Exception.Message)
        return 127
    }
}

function Test-PythonModule {
    param([string]$ModuleName)

    $exit = Run-Command @("python", "-c", "import importlib.util, sys; sys.exit(0) if importlib.util.find_spec('$ModuleName') else sys.exit(1)")
    return ($exit -eq 0)
}

$resolvedModelPath = Resolve-RepoPath $ModelPath
if (-not $resolvedModelPath) {
    Write-Log "Model weights not found; expected at $ModelPath"
    exit 1
}

$resolvedOutputPath = if (Split-Path -IsAbsolute $OutputPath) { $OutputPath } else { Join-Path $repoRoot $OutputPath }
$outputDir = Split-Path -Parent $resolvedOutputPath
if (-not (Test-Path $outputDir)) {
    New-Item -ItemType Directory -Force -Path $outputDir | Out-Null
}

Write-Log ("Using model path: {0}" -f $resolvedModelPath)
Write-Log ("Output will be written to: {0}" -f $resolvedOutputPath)

# Backup original safetensors into timestamped directory.
try {
    $modelInfo = Get-Item -LiteralPath $resolvedModelPath
} catch {
    Write-Log ("Unable to stat model file: {0}" -f $_.Exception.Message)
    exit 1
}

try {
    $driveInfo = Get-PSDrive -Name $modelInfo.PSDrive.Name
    if ($driveInfo.Free -lt $modelInfo.Length) {
        Write-Log ("Not enough disk space to back up model ({0} bytes needed, {1} bytes free)." -f $modelInfo.Length, $driveInfo.Free)
        exit 2
    }
} catch {
    Write-Log ("Skipping free-space precheck: {0}" -f $_.Exception.Message)
}

$timestamp = Get-Date -Format "yyyyMMdd_HHmmss"
$backupDir = Join-Path $repoRoot ("models/backups/{0}" -f $timestamp)
if (-not (Test-Path $backupDir)) {
    New-Item -ItemType Directory -Force -Path $backupDir | Out-Null
}
$backupPath = Join-Path $backupDir (Split-Path -Leaf $resolvedModelPath)

Write-Log "Backing up original weights to $backupPath"
try {
    Copy-Item -LiteralPath $resolvedModelPath -Destination $backupPath -Force
} catch {
    Write-Log ("Backup failed: {0}" -f $_.Exception.Message)
    exit 2
}

$modelDir = Split-Path -Parent $resolvedModelPath

# Attempt A: llama_cpp python module converter.
$llamaCppAvailable = Test-PythonModule "llama_cpp"
if ($llamaCppAvailable) {
    Write-Log "Attempt A: python -m llama_cpp.convert_hf_to_gguf"
    $exitA = Run-Command @("python", "-m", "llama_cpp.convert_hf_to_gguf", "--model", $modelDir, "--outfile", $resolvedOutputPath)
    if ($exitA -eq 0 -and (Test-Path -LiteralPath $resolvedOutputPath)) {
        Write-Log "Conversion succeeded via llama_cpp.convert_hf_to_gguf"
        exit 0
    }
    Write-Log ("Attempt A failed with exit code {0}" -f $exitA)
} else {
    Write-Log "Attempt A skipped; llama_cpp python module not available."
}

# Attempt B: locate local convert script in the repo.
Write-Log "Attempt B: searching for convert-*gguf* scripts under repo"
$converterScripts = Get-ChildItem -Path $repoRoot -Recurse -File -Include "*convert*gguf*.py" -ErrorAction SilentlyContinue
$selectedScript = $converterScripts | Select-Object -First 1

if ($selectedScript) {
    Write-Log ("Attempting converter script: {0}" -f $selectedScript.FullName)
    $exitB = Run-Command @("python", $selectedScript.FullName, "--model", $modelDir, "--outfile", $resolvedOutputPath)
    if ($exitB -eq 0 -and (Test-Path -LiteralPath $resolvedOutputPath)) {
        Write-Log ("Conversion succeeded via {0}" -f $selectedScript.FullName)
        exit 0
    }
    Write-Log ("Attempt B failed with exit code {0}" -f $exitB)
} else {
    Write-Log "No local convert-*gguf*.py script found in repository."
}

# Attempt C: instructions only; non-fatal exit.
$instructions = @(
    "No GGUF converter executed. Install llama-cpp-python (`pip install llama-cpp-python`) and rerun,",
    "or clone llama.cpp and run its convert-hf-to-gguf.py script from the repo root.",
    "Once a converter is available, rerun this script to produce models/gpt-oss-20b.gguf."
)
foreach ($line in $instructions) {
    Write-Log $line
    Write-Output $line
}

exit 0
