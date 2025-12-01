[CmdletBinding()]
param(
    [switch]$DryRun
)

$scriptRoot = Split-Path -Parent $MyInvocation.MyCommand.Path
$repoRoot = Split-Path $scriptRoot -Parent
$reportsDir = Join-Path $repoRoot "reports"
$modelsDir = Join-Path $repoRoot "models"
$logPath = Join-Path $reportsDir "autoselect.log"

if (-not (Test-Path $reportsDir)) {
    New-Item -ItemType Directory -Path $reportsDir -Force | Out-Null
}

function Write-AutoselectLog {
    param([string]$Message)
    $stamp = Get-Date -Format "yyyy-MM-ddTHH:mm:ssK"
    Add-Content -Path $logPath -Value "$stamp`t$Message"
}

try {
    $os = Get-CimInstance Win32_OperatingSystem -ErrorAction Stop
    $freeGB = [math]::Round(($os.FreePhysicalMemory / 1024 / 1024), 2)
} catch {
    Write-AutoselectLog "status=free_mem_failed; error=$($_.Exception.Message)"
    Write-Error "Failed to read free memory: $($_.Exception.Message)"
    exit 1
}

$variant = if ($freeGB -lt 4) { "q4_K_M" } else { "q8_0" }
$reason = if ($freeGB -lt 4) { "free_lt_4gb" } else { "default_q8_0" }

$src = Join-Path $modelsDir "gpt-oss-20b-$variant.gguf"
$dest = Join-Path $modelsDir "gpt-oss-20b.gguf"
$srcDir = Split-Path -Parent $src
$destDir = Split-Path -Parent $dest
$srcFile = Split-Path -Leaf $src
$tempCopy = Join-Path $destDir $srcFile

if (-not (Test-Path $src)) {
    Write-AutoselectLog "status=missing_src; variant=$variant; freeGB=$freeGB; src=$src"
    Write-Error "Source variant not found: $src"
    exit 1
}

if ($DryRun) {
    Write-AutoselectLog "status=dry_run; variant=$variant; freeGB=$freeGB; src=$src; dest=$dest"
    Write-Host "Dry-run: would activate $variant (freeGB=$freeGB)"
    exit 0
}

$moveOk = $false
try {
    Move-Item -Path $src -Destination $dest -Force -ErrorAction Stop
    $moveOk = $true
    Write-AutoselectLog "status=move_success; variant=$variant; freeGB=$freeGB; src=$src; dest=$dest"
} catch {
    Write-AutoselectLog "status=move_failed; variant=$variant; freeGB=$freeGB; src=$src; dest=$dest; error=$($_.Exception.Message)"
}

if (-not $moveOk) {
    $null = New-Item -ItemType Directory -Path $destDir -Force -ErrorAction SilentlyContinue
    $robolog = & robocopy $srcDir $destDir $srcFile /R:1 /W:1 /IS /NFL /NDL /NP /NJH /NJS
    $rc = $LASTEXITCODE
    Write-AutoselectLog "status=robocopy_exit_$rc; variant=$variant; freeGB=$freeGB; src=$src; destdir=$destDir"
    if ($rc -le 3 -and (Test-Path $tempCopy)) {
        try {
            if (Test-Path $dest) {
                Remove-Item -Path $dest -Force -ErrorAction SilentlyContinue
            }
            Move-Item -Path $tempCopy -Destination $dest -Force -ErrorAction Stop
            Write-AutoselectLog "status=robocopy_rename_success; variant=$variant; freeGB=$freeGB; dest=$dest"
            Write-Host "Activated $variant via robocopy (freeGB=$freeGB)"
            exit 0
        } catch {
            Write-AutoselectLog "status=robocopy_rename_failed; variant=$variant; freeGB=$freeGB; dest=$dest; error=$($_.Exception.Message)"
            Write-Error "Robocopy rename failed: $($_.Exception.Message)"
            exit 1
        }
    } else {
        Write-Error "Robocopy failed with exit code $rc"
        exit 1
    }
}

Write-Host "Activated $variant via move (freeGB=$freeGB)"
exit 0
