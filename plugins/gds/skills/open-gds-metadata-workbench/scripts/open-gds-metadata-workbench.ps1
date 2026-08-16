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
    $WorkbenchPath = [System.IO.Path]::GetFullPath(
        (Join-Path $PSScriptRoot "..\assets\workbench\index.html")
    )
    if (-not (Test-Path -LiteralPath $WorkbenchPath -PathType Leaf)) {
        Write-Failure "Bundled Data Workbench is missing."
    }
    $WorkbenchItem = Get-Item -LiteralPath $WorkbenchPath
    if (($WorkbenchItem.Attributes -band [System.IO.FileAttributes]::ReparsePoint) -ne 0) {
        Write-Failure "Bundled Data Workbench is unsafe."
    }
    Start-Process -FilePath $WorkbenchPath
    [Console]::Out.WriteLine("ok=true")
    [Console]::Out.WriteLine("opened=true")
    [Console]::Out.WriteLine("target=default-browser")
    exit 0
}
catch {
    Write-Failure "Data Workbench could not be opened."
}
