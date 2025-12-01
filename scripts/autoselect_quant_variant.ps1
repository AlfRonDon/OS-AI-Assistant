
# Robust autoselect: Move first, robocopy fallback. Does NOT create automatic backups.

# Picks q8_0 unless freeGB < 4 then q4_K_M.

$os = Get-CimInstance Win32_OperatingSystem
$freeGB = [math]::Round(($os.FreePhysicalMemory / 1GB), 2)
if ($freeGB -lt 4) { $variant = "q4_K_M" } else { $variant = "q8_0" }

$modelsDir = Join-Path (Get-Location) "models"
$src = Join-Path $modelsDir "gpt-oss-20b-$variant.gguf"
$dest = Join-Path $modelsDir "gpt-oss-20b.gguf"
$log = Join-Path (Join-Path (Get-Location) "reports") "autoselect.log"
if (!(Test-Path $src)) {
"$((Get-Date).ToString('s')) Variant missing: $src" | Out-File -FilePath $log -Append
Write-Error "Variant missing: $src"
exit 1
}

"$((Get-Date).ToString('s')) Attempting to swap to $variant" | Out-File -FilePath $log -Append

# Attempt atomic move first

try {
Move-Item $src $dest -Force
"$((Get-Date).ToString('s')) Swapped to $variant via Move-Item" | Out-File -FilePath $log -Append
exit 0
} catch {
"$((Get-Date).ToString('s')) Move-Item failed: $($_.Exception.Message). Falling back to robocopy." | Out-File -FilePath $log -Append
}

# Cross-drive fallback: robocopy into _tmp_copy then move

$tmpDir = Join-Path $modelsDir "_tmp_copy"
if (!(Test-Path $tmpDir)) { New-Item -ItemType Directory -Path $tmpDir -Force | Out-Null }

$srcDir = Split-Path -Parent $src
$srcFile = Split-Path -Leaf $src
$cmd = "robocopy `"$srcDir`" `"$tmpDir`" `"$srcFile`" /MT:8 /R:3 /W:5"
"$((Get-Date).ToString('s')) Running: $cmd" | Out-File -FilePath $log -Append
$rc = cmd /c $cmd
if ($LASTEXITCODE -ge 8) {
"$((Get-Date).ToString('s')) robocopy failed with code $LASTEXITCODE" | Out-File -FilePath $log -Append
Write-Error "robocopy failed with code $LASTEXITCODE"
exit 2
}

Move-Item (Join-Path $tmpDir $srcFile) $dest -Force
Remove-Item -Recurse -Force $tmpDir
"$((Get-Date).ToString('s')) Swapped to $variant via robocopy" | Out-File -FilePath $log -Append
exit 0

