param(
    [string]$ChangeSetPath = (Join-Path (Get-Location).Path "GDS\change-set"),
    [Parameter(Mandatory = $true)]
    [string]$Dataset,
    [Parameter(Mandatory = $true)]
    [string]$KeyPath
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
    $AllowedDatasets = @(
        "source_object", "source_attribute", "bronze_object", "bronze_attribute",
        "silver_object", "silver_attribute", "gold_object", "gold_attribute",
        "ingestion_object_mapping", "ingestion_attribute_mapping", "copy_group",
        "member_group", "copy_group_control", "copy", "process_group", "process"
    )
    if ($AllowedDatasets -cnotcontains $Dataset) {
        Write-Failure "Dataset is not Change Set eligible."
    }
    $ScriptDirectory = Split-Path -Parent $MyInvocation.MyCommand.Path
    $SchemaHelper = Join-Path $ScriptDirectory "metadata-schema.ps1"
    if (-not (Test-Path -LiteralPath $SchemaHelper -PathType Leaf)) {
        Write-Failure "Bundled schema helper is missing."
    }
    . $SchemaHelper

    $Root = [System.IO.Path]::GetFullPath($ChangeSetPath)
    $TrimCharacters = [char[]]@(
        [System.IO.Path]::DirectorySeparatorChar,
        [System.IO.Path]::AltDirectorySeparatorChar
    )
    $Root = $Root.TrimEnd($TrimCharacters)
    if ([System.IO.Path]::GetFileName($Root) -cne "change-set") {
        Write-Failure "Local directory must be named change-set."
    }
    $Workspace = [System.IO.Directory]::GetParent($Root)
    if ($null -eq $Workspace -or [System.IO.Path]::GetFileName($Workspace.FullName) -cne "GDS") {
        Write-Failure "Local change-set must be directly under GDS."
    }
    if (-not (Test-Path -LiteralPath $Root -PathType Container)) {
        Write-Failure "Local change-set does not exist."
    }
    foreach ($Entry in @(Get-ChildItem -LiteralPath $Root -Force -Recurse)) {
        if (($Entry.Attributes -band [System.IO.FileAttributes]::ReparsePoint) -ne 0) {
            Write-Failure "Local change-set cannot contain reparse points."
        }
    }

    $StatePath = Join-Path $Root "change-set.json"
    $DatasetPath = Join-Path $Root "datasets\$Dataset.json"
    $SnapshotPath = Join-Path $Workspace.FullName "metadata-snapshot"
    $ManifestPath = Join-Path $SnapshotPath "manifest.json"
    $SchemaPath = Join-Path $SnapshotPath "schemas\$Dataset.schema.json"
    if (
        -not (Test-Path -LiteralPath $StatePath -PathType Leaf) -or
        -not (Test-Path -LiteralPath $DatasetPath -PathType Leaf) -or
        -not (Test-Path -LiteralPath $ManifestPath -PathType Leaf) -or
        -not (Test-Path -LiteralPath $SchemaPath -PathType Leaf)
    ) {
        Write-Failure "Local pending dataset or its control files are missing."
    }
    try {
        $State = [System.IO.File]::ReadAllText($StatePath) | ConvertFrom-Json
        $Manifest = [System.IO.File]::ReadAllText($ManifestPath) | ConvertFrom-Json
        $Schema = [System.IO.File]::ReadAllText($SchemaPath) | ConvertFrom-Json
    }
    catch {
        Write-Failure "Local state, Snapshot manifest, or schema is not valid JSON."
    }
    if (([string]$State.snapshot.path) -cne "../metadata-snapshot") {
        Write-Failure "Snapshot path must be ../metadata-snapshot."
    }
    if (
        ([string]$Manifest.tenant_code) -cne ([string]$State.tenant.tenant_code) -or
        ([string]$Manifest.snapshot_id) -cne ([string]$State.snapshot.snapshot_id)
    ) {
        Write-Failure "Snapshot identity does not match local Change Set."
    }
    try {
        Assert-GdsSchema $Schema $Dataset
    }
    catch {
        Write-Failure "Snapshot dataset schema contract is invalid."
    }

    $FullKeyPath = [System.IO.Path]::GetFullPath($KeyPath)
    if (-not (Test-Path -LiteralPath $FullKeyPath -PathType Leaf)) {
        Write-Failure "Canonical key must be a regular JSON file."
    }
    $KeyItem = Get-Item -LiteralPath $FullKeyPath
    if (($KeyItem.Attributes -band [System.IO.FileAttributes]::ReparsePoint) -ne 0) {
        Write-Failure "Canonical key cannot be a reparse point."
    }
    if ($KeyItem.Length -gt 1048576) {
        Write-Failure "Canonical key file exceeds 1 MiB."
    }
    $KeyText = [System.IO.File]::ReadAllText($FullKeyPath)
    if (-not $KeyText.TrimStart().StartsWith("{")) {
        Write-Failure "Canonical key file must contain one JSON object."
    }
    try {
        $KeyRecord = $KeyText | ConvertFrom-Json
    }
    catch {
        Write-Failure "Canonical key file is not valid JSON."
    }

    $DatasetItem = Get-Item -LiteralPath $DatasetPath
    if (($DatasetItem.Attributes -band [System.IO.FileAttributes]::ReparsePoint) -ne 0) {
        Write-Failure "Local pending dataset cannot be a reparse point."
    }
    $DatasetText = [System.IO.File]::ReadAllText($DatasetPath)
    if (-not $DatasetText.TrimStart().StartsWith("[")) {
        Write-Failure "Local pending dataset must contain one JSON array."
    }
    try {
        $Records = @($DatasetText | ConvertFrom-Json)
        $Result = Remove-GdsRecord $Records $KeyRecord $Schema
    }
    catch {
        Write-Failure "Canonical key or accumulated dataset does not match the Snapshot schema: $Dataset."
    }
    if ($Result.Action -ceq "not_found") {
        Write-Failure "Canonical key is not present in the local pending dataset."
    }

    $DatasetJson = ConvertTo-Json -InputObject ([object[]]$Result.Records) -Depth 20
    $Utf8NoBom = New-Object System.Text.UTF8Encoding($false)
    $DatasetBytes = $Utf8NoBom.GetBytes($DatasetJson + "`n")
    $TemporaryPath = "$DatasetPath.remove.$([guid]::NewGuid().ToString('N')).tmp"
    [System.IO.File]::WriteAllBytes($TemporaryPath, $DatasetBytes)
    [System.IO.File]::Replace($TemporaryPath, $DatasetPath, $null)
    $DatasetHash = (Get-FileHash -LiteralPath $DatasetPath -Algorithm SHA256).Hash.ToLowerInvariant()
    $DatasetEmpty = $Result.Records.Count -eq 0

    [Console]::Out.WriteLine("ok=true")
    [Console]::Out.WriteLine("dataset=$Dataset")
    [Console]::Out.WriteLine("action=removed")
    [Console]::Out.WriteLine("record_count=$($Result.Records.Count)")
    [Console]::Out.WriteLine("dataset_empty=$($DatasetEmpty.ToString().ToLowerInvariant())")
    [Console]::Out.WriteLine("bytes=$($DatasetBytes.Length)")
    [Console]::Out.WriteLine("sha256=$DatasetHash")
    exit 0
}
catch {
    Write-Failure "Local pending record removal failed."
}
