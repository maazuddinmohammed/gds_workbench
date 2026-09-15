[CmdletBinding()]
param()

$ErrorActionPreference = 'Stop'
Set-StrictMode -Version 2.0
$scriptRoot = Split-Path -Parent $PSCommandPath
$indexPath = Join-Path (Split-Path -Parent $scriptRoot) 'workbench\index.html'
$indexItem = Get-Item -LiteralPath $indexPath -ErrorAction Stop
if ($indexItem.PSIsContainer -or ($indexItem.Attributes -band [IO.FileAttributes]::ReparsePoint)) {
    throw 'Bundled index.html is missing or unsafe.'
}

$browserPath = $null
foreach ($commandName in @('msedge.exe', 'chrome.exe')) {
    $browser = Get-Command $commandName -CommandType Application -ErrorAction SilentlyContinue
    if ($null -ne $browser) {
        $browserPath = $browser.Source
        break
    }
}
if ($null -eq $browserPath) {
    $candidates = New-Object System.Collections.Generic.List[string]
    if (-not [string]::IsNullOrWhiteSpace(${env:ProgramFiles(x86)})) {
        $candidates.Add((Join-Path ${env:ProgramFiles(x86)} 'Microsoft\Edge\Application\msedge.exe'))
        $candidates.Add((Join-Path ${env:ProgramFiles(x86)} 'Google\Chrome\Application\chrome.exe'))
    }
    if (-not [string]::IsNullOrWhiteSpace($env:ProgramFiles)) {
        $candidates.Add((Join-Path $env:ProgramFiles 'Microsoft\Edge\Application\msedge.exe'))
        $candidates.Add((Join-Path $env:ProgramFiles 'Google\Chrome\Application\chrome.exe'))
    }
    if (-not [string]::IsNullOrWhiteSpace($env:LOCALAPPDATA)) {
        $candidates.Add((Join-Path $env:LOCALAPPDATA 'Microsoft\Edge\Application\msedge.exe'))
        $candidates.Add((Join-Path $env:LOCALAPPDATA 'Google\Chrome\Application\chrome.exe'))
    }
    foreach ($candidate in $candidates) {
        if (Test-Path -LiteralPath $candidate -PathType Leaf) {
            $browserPath = $candidate
            break
        }
    }
}
if ($null -eq $browserPath) {
    throw 'Chrome or Edge is required for local session directory access.'
}
$browserItem = Get-Item -LiteralPath $browserPath -ErrorAction Stop
if ($browserItem.PSIsContainer -or ($browserItem.Attributes -band [IO.FileAttributes]::ReparsePoint)) {
    throw 'Chrome or Edge executable is unsafe.'
}

$indexUri = [Uri]$indexItem.FullName
Start-Process -FilePath $browserItem.FullName -ArgumentList @($indexUri.AbsoluteUri)
