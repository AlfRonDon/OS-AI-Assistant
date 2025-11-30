$ErrorActionPreference = "Stop"

$repoRoot = Split-Path -Parent $PSScriptRoot
Set-Location $repoRoot

if (Test-Path ".venv/Scripts/Activate.ps1") {
    . ".venv/Scripts/Activate.ps1"
} elseif (Test-Path ".venv/bin/activate") {
    . ".venv/bin/activate"
}

New-Item -ItemType Directory -Force -Path "reports/tests" | Out-Null

python -m pip install --upgrade pip
python -m pip install pytest jsonschema psutil

$pytestArgs = @("-m", "pytest", "tests", "-q", "--junitxml", "reports/tests/junit.xml")
$psi = New-Object System.Diagnostics.ProcessStartInfo
$psi.FileName = "python"
$psi.Arguments = $pytestArgs -join " "
$psi.RedirectStandardOutput = $true
$psi.RedirectStandardError = $true
$psi.UseShellExecute = $false
$psi.CreateNoWindow = $true

$proc = New-Object System.Diagnostics.Process
$proc.StartInfo = $psi
$null = $proc.Start()
$stdout = $proc.StandardOutput.ReadToEnd()
$stderr = $proc.StandardError.ReadToEnd()
$proc.WaitForExit()

$logPath = "reports/tests/pytest_output.txt"
("$stdout`n$stderr").Trim() | Out-File -FilePath $logPath -Encoding UTF8 -Force

if ($proc.ExitCode -ne 0) {
    exit $proc.ExitCode
}
