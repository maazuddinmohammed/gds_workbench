$ErrorActionPreference = "Stop"

$RepositoryRoot = [System.IO.Path]::GetFullPath((Join-Path $PSScriptRoot "..\.."))
$PluginRoot = Join-Path $RepositoryRoot "plugins\gds"
$PowerShellFiles = Get-ChildItem -LiteralPath $PluginRoot -Filter "*.ps1" -File -Recurse
if ($PowerShellFiles.Count -eq 0) {
    throw "No plugin PowerShell scripts were found."
}

foreach ($File in $PowerShellFiles) {
    $Tokens = $null
    $Errors = $null
    [void][System.Management.Automation.Language.Parser]::ParseFile(
        $File.FullName,
        [ref]$Tokens,
        [ref]$Errors
    )
    if ($Errors.Count -ne 0) {
        throw "PowerShell parse failed: $($File.FullName): $($Errors[0].Message)"
    }
}

$TestParent = Join-Path $env:RUNNER_TEMP "gds-plugin-$([Guid]::NewGuid())"
[void](New-Item -ItemType Directory -Path $TestParent)
$Workspace = Join-Path $TestParent "GDS"
$Initializer = Join-Path $PluginRoot "skills\manage-gds-metadata\scripts\initialize-gds-workspace.ps1"

$First = & powershell.exe -NoProfile -File $Initializer -Root $Workspace
if ($LASTEXITCODE -ne 0 -or $First -notcontains "ok=true" -or $First -notcontains "created=true") {
    throw "First Windows workspace initialization failed."
}
$Second = & powershell.exe -NoProfile -File $Initializer -Root $Workspace
if ($LASTEXITCODE -ne 0 -or $Second -notcontains "ok=true" -or $Second -notcontains "created=false") {
    throw "Idempotent Windows workspace initialization failed."
}
$ExpectedIgnore = "*`n!.gitignore`n"
$ActualIgnore = [System.IO.File]::ReadAllText((Join-Path $Workspace ".gitignore")).Replace("`r`n", "`n")
if ($ActualIgnore -cne $ExpectedIgnore) {
    throw "Windows workspace .gitignore is incorrect."
}

[Console]::Out.WriteLine("Windows plugin smoke tests passed")
