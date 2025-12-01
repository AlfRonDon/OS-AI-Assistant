param(
    [string]$SandboxPath = (Join-Path (Split-Path $PSScriptRoot -Parent) "sandbox")
)

$resolvedPath = $SandboxPath
try {
    $resolvedPath = (Resolve-Path -LiteralPath $SandboxPath -ErrorAction SilentlyContinue)
    if ($null -ne $resolvedPath) {
        $resolvedPath = $resolvedPath.Path
    } else {
        $resolvedPath = (Resolve-Path -LiteralPath (Join-Path $PWD $SandboxPath)).Path
    }
} catch {
    $resolvedPath = (Join-Path $PWD $SandboxPath)
}

if (-not (Test-Path -LiteralPath $resolvedPath)) {
    New-Item -ItemType Directory -Path $resolvedPath -Force | Out-Null
}

# Grant the current user full control inside the sandbox to avoid permission surprises.
try {
    $user = "$($env:USERNAME)"
    icacls $resolvedPath /inheritance:r /grant "$user:(OI)(CI)F" /T | Out-Null
} catch {
    Write-Warning "Failed to set ACLs on $resolvedPath. Continuing with defaults. $_"
}

Write-Host "Sandbox ready at $resolvedPath"
