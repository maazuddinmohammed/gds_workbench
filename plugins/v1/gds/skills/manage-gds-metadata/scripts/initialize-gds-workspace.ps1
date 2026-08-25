param(
    [string]$Root = (Join-Path (Get-Location).Path "GDS")
)

$ErrorActionPreference = "Stop"

function Write-Failure {
    param([string]$Message)
    [Console]::Error.WriteLine("ok=false")
    [Console]::Error.WriteLine("error=$Message")
    exit 2
}

try {
    if ($PSVersionTable.PSVersion.Major -lt 5) {
        Write-Failure "PowerShell 5.1 or newer is required."
    }

    $FullRoot = [System.IO.Path]::GetFullPath($Root)
    $TrimCharacters = [char[]]@(
        [System.IO.Path]::DirectorySeparatorChar,
        [System.IO.Path]::AltDirectorySeparatorChar
    )
    $TrimmedRoot = $FullRoot.TrimEnd($TrimCharacters)
    if ([System.IO.Path]::GetFileName($TrimmedRoot) -cne "GDS") {
        Write-Failure "Workspace directory must be named GDS."
    }

    $Parent = [System.IO.Directory]::GetParent($TrimmedRoot)
    if ($null -eq $Parent -or -not $Parent.Exists) {
        Write-Failure "Workspace parent directory does not exist."
    }
    $ParentItem = Get-Item -LiteralPath $Parent.FullName
    if (($ParentItem.Attributes -band [System.IO.FileAttributes]::ReparsePoint) -ne 0) {
        Write-Failure "Workspace parent cannot be a reparse point."
    }

    $Created = $false
    if (Test-Path -LiteralPath $TrimmedRoot) {
        $RootItem = Get-Item -LiteralPath $TrimmedRoot
        if (-not $RootItem.PSIsContainer) {
            Write-Failure "Workspace path exists but is not a directory."
        }
        if (($RootItem.Attributes -band [System.IO.FileAttributes]::ReparsePoint) -ne 0) {
            Write-Failure "Workspace directory cannot be a reparse point."
        }
    }
    else {
        New-Item -ItemType Directory -Path $TrimmedRoot | Out-Null
        $Created = $true
    }

    $IgnorePath = Join-Path $TrimmedRoot ".gitignore"
    $ExpectedIgnore = "*`n!.gitignore`n"
    if (Test-Path -LiteralPath $IgnorePath) {
        $IgnoreItem = Get-Item -LiteralPath $IgnorePath
        if ($IgnoreItem.PSIsContainer -or (($IgnoreItem.Attributes -band [System.IO.FileAttributes]::ReparsePoint) -ne 0)) {
            Write-Failure "Workspace .gitignore must be a regular file."
        }
        $CurrentIgnore = [System.IO.File]::ReadAllText($IgnorePath).Replace("`r`n", "`n")
        if ($CurrentIgnore -cne $ExpectedIgnore) {
            Write-Failure "Workspace .gitignore has unexpected content."
        }
    }
    else {
        $Utf8NoBom = New-Object System.Text.UTF8Encoding($false)
        [System.IO.File]::WriteAllText($IgnorePath, $ExpectedIgnore, $Utf8NoBom)
    }

    $SnapshotPath = Join-Path $TrimmedRoot "metadata-snapshot"
    $ChangeSetPath = Join-Path $TrimmedRoot "change-set"
    foreach ($ManagedPath in @($SnapshotPath, $ChangeSetPath)) {
        if (Test-Path -LiteralPath $ManagedPath) {
            $ManagedItem = Get-Item -LiteralPath $ManagedPath
            if (-not $ManagedItem.PSIsContainer) {
                Write-Failure "A managed workspace path exists but is not a directory."
            }
            if (($ManagedItem.Attributes -band [System.IO.FileAttributes]::ReparsePoint) -ne 0) {
                Write-Failure "Managed workspace directories cannot be reparse points."
            }
        }
    }

    [Console]::Out.WriteLine("ok=true")
    [Console]::Out.WriteLine("workspace=$TrimmedRoot")
    [Console]::Out.WriteLine("created=$($Created.ToString().ToLowerInvariant())")
    [Console]::Out.WriteLine("metadata_snapshot_exists=$((Test-Path -LiteralPath $SnapshotPath).ToString().ToLowerInvariant())")
    [Console]::Out.WriteLine("change_set_exists=$((Test-Path -LiteralPath $ChangeSetPath).ToString().ToLowerInvariant())")
    exit 0
}
catch {
    Write-Failure "Workspace initialization failed."
}
