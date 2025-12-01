param(
    [int]$Lines = 50,
    [switch]$DryRun
)

$ErrorActionPreference = 'Stop'
$repoRoot = Resolve-Path (Join-Path $PSScriptRoot '..')
$alertsPath = Join-Path $repoRoot 'reports/alerts.log'
$lastRunPath = Join-Path $repoRoot 'reports/notify_slack_last.txt'
$webhook = $env:SLACK_WEBHOOK_URL
$ts = Get-Date -Format 'yyyy-MM-ddTHH:mm:ssK'
$status = 'skipped'
$note = ''

if (-not (Test-Path $alertsPath)) {
    $note = 'alerts.log not found'
} elseif (-not $webhook) {
    $note = 'SLACK_WEBHOOK_URL not set'
} else {
    $logLines = Get-Content -Path $alertsPath -Tail $Lines -ErrorAction SilentlyContinue
    $payload = @{
        text = \"EdgeOS alerts @ $ts`n```````n$($logLines -join \"`n\")`n```````\"
    }
    if ($DryRun) {
        $status = 'dry-run'
    } else {
        try {
            Invoke-RestMethod -Uri $webhook -Method Post -ContentType 'application/json' -Body (ConvertTo-Json $payload -Depth 3) | Out-Null
            $status = 'sent'
        } catch {
            $status = 'error'
            $note = $_.Exception.Message
        }
    }
}

$logEntry = \"${ts} status=${status} lines=${Lines} note=${note}\"
Set-Content -Path $lastRunPath -Value $logEntry
Write-Output $logEntry
