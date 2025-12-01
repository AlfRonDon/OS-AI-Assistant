# Watchdog wrapper for Windows Task Scheduler
# Runs periodically, logs RSS of the model process, restarts it if RSS exceeds threshold.

Param(
    [string]$LogPath = "$(Get-Location)\reports\watchdog.log",
    [int]$RssThresholdMB = 14000
)

# TODO: set this to the actual process name used by your edge model runner.
$processName = "edge_model_runner"

# TODO: set this to the actual startup script/binary that launches the model service.
$startCommand = "C:\path\to\runner\start_edge_model.bat"

$logDir = Split-Path $LogPath -Parent
if (!(Test-Path $logDir)) {
    New-Item -ItemType Directory -Path $logDir -Force | Out-Null
}

function Write-Log([string]$msg) {
    $timestamp = (Get-Date).ToString("s")
    "$timestamp $msg" | Out-File -FilePath $LogPath -Append -Encoding UTF8
}

try {
    $proc = Get-Process -Name $processName -ErrorAction SilentlyContinue
} catch {
    $proc = $null
}

if ($null -ne $proc) {
    $rssMB = [math]::Round($proc.WorkingSet64 / 1MB, 0)
    Write-Log "Process '$processName' present. RSS=${rssMB}MB."

    if ($rssMB -gt $RssThresholdMB) {
        Write-Log "RSS threshold breached (${rssMB}MB > ${RssThresholdMB}MB). Restarting process."

        try {
            Stop-Process -Id $proc.Id -Force -ErrorAction Stop
            Start-Sleep -Seconds 2
        } catch {
            Write-Log "Error stopping process: $($_.Exception.Message)"
        }

        try {
            Start-Process -FilePath $startCommand -WindowStyle Hidden
            Write-Log "Started process using '$startCommand'."
        } catch {
            Write-Log "Error starting process: $($_.Exception.Message)"
        }
    }
} else {
    Write-Log "Process '$processName' is not running. Attempting to start."

    try {
        Start-Process -FilePath $startCommand -WindowStyle Hidden
        Write-Log "Started process using '$startCommand'."
    } catch {
        Write-Log "Error starting process: $($_.Exception.Message)"
    }
}
