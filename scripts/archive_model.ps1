Param(
    [string]$SourcePath = "models/gpt-oss-20b/original/model.safetensors",
    [string]$ArchiveRoot = "",
    [string]$LogPath = "reports/archive_model.log"
)

Set-StrictMode -Version Latest
$ErrorActionPreference = "Stop"

function Write-Log {
    param([string]$Message)
    $timestamp = Get-Date -Format "yyyy-MM-dd HH:mm:ss"
    "$timestamp`t$Message" | Tee-Object -FilePath $LogPath -Append
}

function Confirm-Action {
    param([string]$Prompt)
    $response = Read-Host $Prompt
    return $response -in @("y", "Y", "yes", "YES")
}

New-Item -ItemType Directory -Force -Path (Split-Path -Parent $LogPath) | Out-Null

try {
    if (-not (Test-Path -LiteralPath $SourcePath)) {
        Write-Log "Source file not found at $SourcePath. Aborting."
        Write-Warning "Source file not found."
        return
    }

    $sourceItem = Get-Item -LiteralPath $SourcePath
    $sourceSize = [int64]$sourceItem.Length
    $sourceDir = Split-Path -Parent $SourcePath

    Write-Log "Preparing to archive $SourcePath ($([math]::Round($sourceSize / 1GB, 2)) GB)."

    if (-not $ArchiveRoot) {
        $ArchiveRoot = Read-Host "Enter archive destination path (e.g., D:\\model_archives)"
    }

    if (-not $ArchiveRoot) {
        Write-Log "No archive destination provided. Exiting."
        return
    }

    $ArchiveRoot = [System.IO.Path]::GetFullPath($ArchiveRoot.Trim('"'))
    $archiveFolderName = "gpt-oss-20b-{0}" -f (Get-Date -Format "yyyyMMdd_HHmmss")
    $archiveFolder = Join-Path -Path $ArchiveRoot -ChildPath $archiveFolderName
    $destFile = Join-Path -Path $archiveFolder -ChildPath $sourceItem.Name

    $destDriveRoot = [System.IO.Path]::GetPathRoot($archiveFolder)
    $destDrive = Get-PSDrive -PSProvider FileSystem | Where-Object { $_.Root -ieq $destDriveRoot }

    if ($null -ne $destDrive -and $destDrive.Free -lt $sourceSize) {
        Write-Log "Insufficient free space on $($destDrive.Root). Required: $([math]::Round($sourceSize / 1GB, 2)) GB, Available: $([math]::Round($destDrive.Free / 1GB, 2)) GB."
        Write-Warning "Not enough free space at $ArchiveRoot."
        return
    }

    if (-not (Confirm-Action -Prompt "Copy ~$([math]::Round($sourceSize / 1GB, 2)) GB to '$archiveFolder'? (y/n)")) {
        Write-Log "User declined copy operation."
        return
    }

    New-Item -ItemType Directory -Force -Path $archiveFolder | Out-Null
    Write-Log "Created archive folder $archiveFolder."

    Copy-Item -LiteralPath $SourcePath -Destination $archiveFolder -Force
    Write-Log "Copied model to $destFile."

    $sourceHash = (Get-FileHash -LiteralPath $SourcePath -Algorithm SHA256).Hash
    $destHash = (Get-FileHash -LiteralPath $destFile -Algorithm SHA256).Hash

    if ($sourceHash -ne $destHash) {
        Write-Log "Checksum mismatch after copy. Source: $sourceHash Dest: $destHash"
        Write-Warning "Checksum mismatch. Keeping original in place."
        return
    }

    Write-Log "Checksum verified (SHA256 $sourceHash)."
    Write-Host "Archive complete at $destFile"

    $postAction = Read-Host "Optional action: type 'symlink' to replace original with a symlink, 'delete' to delete original, or press Enter to leave original in place"

    switch ($postAction.ToLower()) {
        "symlink" {
            if (Confirm-Action -Prompt "Replace original with symlink to archived copy? (y/n)") {
                Write-Log "User chose to replace original with symlink."
                Remove-Item -LiteralPath $SourcePath -Force
                New-Item -ItemType SymbolicLink -Path $SourcePath -Target $destFile | Out-Null
                Write-Log "Created symlink at $SourcePath pointing to $destFile."
                Write-Host "Original replaced with symlink."
            }
            else {
                Write-Log "Symlink replacement declined."
            }
        }
        "delete" {
            $first = Read-Host "Type DELETE to confirm removing original file"
            $second = Read-Host "Type DELETE again to proceed"
            if ($first -eq "DELETE" -and $second -eq "DELETE") {
                Write-Log "User confirmed deletion of original file."
                Remove-Item -LiteralPath $SourcePath -Force
                Write-Log "Original file deleted after successful archive."
                Write-Host "Original deleted."
            }
            else {
                Write-Log "Deletion aborted by user."
                Write-Host "Deletion cancelled."
            }
        }
        default {
            Write-Log "No post-copy action selected. Original remains at $SourcePath."
        }
    }
}
catch {
    Write-Log "Error: $($_.Exception.Message)"
    throw
}
