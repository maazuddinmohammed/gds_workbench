[CmdletBinding(DefaultParameterSetName = "FullRecord")]
param(
    [string]$ChangeSetPath = (Join-Path (Get-Location).Path "GDS\change-set"),
    [Parameter(Mandatory = $true)]
    [string]$Dataset,
    [Parameter(Mandatory = $true, ParameterSetName = "FullRecord")]
    [string]$RecordPath,
    [Parameter(Mandatory = $true, ParameterSetName = "FieldEdit")]
    [string]$KeyPath,
    [Parameter(Mandatory = $true, ParameterSetName = "FieldEdit")]
    [string]$ChangesPath
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
    $StatePath = Join-Path $Root "change-set.json"
    $DatasetsPath = Join-Path $Root "datasets"
    if (-not (Test-Path -LiteralPath $StatePath -PathType Leaf) -or -not (Test-Path -LiteralPath $DatasetsPath -PathType Container)) {
        Write-Failure "Local Change Set structure is incomplete."
    }
    foreach ($Entry in @(Get-ChildItem -LiteralPath $Root -Force -Recurse)) {
        if (($Entry.Attributes -band [System.IO.FileAttributes]::ReparsePoint) -ne 0) {
            Write-Failure "Local change-set cannot contain reparse points."
        }
    }

    try {
        $State = [System.IO.File]::ReadAllText($StatePath) | ConvertFrom-Json
    }
    catch {
        Write-Failure "change-set.json is not valid JSON."
    }
    if (([string]$State.snapshot.path) -cne "../metadata-snapshot") {
        Write-Failure "Snapshot path must be ../metadata-snapshot."
    }
    $SnapshotPath = Join-Path $Workspace.FullName "metadata-snapshot"
    $ManifestPath = Join-Path $SnapshotPath "manifest.json"
    $SchemaPath = Join-Path $SnapshotPath "schemas\$Dataset.schema.json"
    if (-not (Test-Path -LiteralPath $ManifestPath -PathType Leaf) -or -not (Test-Path -LiteralPath $SchemaPath -PathType Leaf)) {
        Write-Failure "Referenced Snapshot manifest or dataset schema is missing."
    }
    foreach ($SnapshotFile in @(Get-Item -LiteralPath $ManifestPath, $SchemaPath)) {
        if (($SnapshotFile.Attributes -band [System.IO.FileAttributes]::ReparsePoint) -ne 0) {
            Write-Failure "Referenced Snapshot files cannot be reparse points."
        }
    }
    try {
        $Manifest = [System.IO.File]::ReadAllText($ManifestPath) | ConvertFrom-Json
        $Schema = [System.IO.File]::ReadAllText($SchemaPath) | ConvertFrom-Json
    }
    catch {
        Write-Failure "Snapshot manifest or dataset schema is not valid JSON."
    }
    if (([string]$Manifest.tenant_code) -cne ([string]$State.tenant.tenant_code)) {
        Write-Failure "Snapshot Tenant does not match local Change Set."
    }
    if (([string]$Manifest.snapshot_id) -cne ([string]$State.snapshot.snapshot_id)) {
        Write-Failure "Snapshot ID does not match local Change Set."
    }
    try {
        Assert-GdsSchema $Schema $Dataset
    }
    catch {
        Write-Failure "Snapshot dataset schema contract is invalid."
    }

    $DatasetPath = Join-Path $DatasetsPath "$Dataset.json"
    $Records = @()
    if (Test-Path -LiteralPath $DatasetPath) {
        $DatasetItem = Get-Item -LiteralPath $DatasetPath
        if ($DatasetItem.PSIsContainer -or ($DatasetItem.Attributes -band [System.IO.FileAttributes]::ReparsePoint) -ne 0) {
            Write-Failure "Existing dataset file is unsafe."
        }
        if ($DatasetItem.Length -gt 16777216) {
            Write-Failure "Existing dataset exceeds the 16 MiB Stage limit."
        }
        $DatasetText = [System.IO.File]::ReadAllText($DatasetPath)
        if (-not $DatasetText.TrimStart().StartsWith("[")) {
            Write-Failure "Existing dataset must contain one JSON array."
        }
        try {
            $Records = @($DatasetText | ConvertFrom-Json)
        }
        catch {
            Write-Failure "Existing dataset is not valid JSON."
        }
    }

    if ($PSCmdlet.ParameterSetName -ceq "FieldEdit") {
        $FullKeyPath = [System.IO.Path]::GetFullPath($KeyPath)
        $FullChangesPath = [System.IO.Path]::GetFullPath($ChangesPath)
        foreach ($InputPath in @($FullKeyPath, $FullChangesPath)) {
            if (-not (Test-Path -LiteralPath $InputPath -PathType Leaf)) {
                Write-Failure "Canonical key and field changes must be regular JSON files."
            }
            $InputItem = Get-Item -LiteralPath $InputPath
            if (($InputItem.Attributes -band [System.IO.FileAttributes]::ReparsePoint) -ne 0 -or $InputItem.Length -gt 16777216) {
                Write-Failure "Canonical key or field changes file is unsafe or too large."
            }
        }
        try {
            $KeyRecord = [System.IO.File]::ReadAllText($FullKeyPath) | ConvertFrom-Json
            $Changes = [System.IO.File]::ReadAllText($FullChangesPath) | ConvertFrom-Json
        }
        catch {
            Write-Failure "Canonical key or field changes file is not valid JSON."
        }
        $SnapshotRowsPath = Join-Path $SnapshotPath "data\operational\$Dataset\rows.jsonl"
        if (-not (Test-Path -LiteralPath $SnapshotRowsPath -PathType Leaf)) {
            Write-Failure "Snapshot dataset rows are missing."
        }
        $SnapshotRowsItem = Get-Item -LiteralPath $SnapshotRowsPath
        if (($SnapshotRowsItem.Attributes -band [System.IO.FileAttributes]::ReparsePoint) -ne 0) {
            Write-Failure "Snapshot dataset rows cannot be a reparse point."
        }
        try {
            $SnapshotRecords = @(
                [System.IO.File]::ReadLines($SnapshotRowsPath) |
                    Where-Object { -not [string]::IsNullOrWhiteSpace($_) } |
                    ForEach-Object { $_ | ConvertFrom-Json }
            )
            $Merged = Edit-GdsRecord $Records $SnapshotRecords $KeyRecord $Changes $Schema
        }
        catch {
            Write-Failure "Field edit does not match the Snapshot schema, key, or uniqueness rules: $Dataset."
        }
        $Mode = "field-edit"
    }
    else {
        $FullRecordPath = [System.IO.Path]::GetFullPath($RecordPath)
        if (-not (Test-Path -LiteralPath $FullRecordPath -PathType Leaf)) {
            Write-Failure "Input record must be a regular JSON file."
        }
        $RecordItem = Get-Item -LiteralPath $FullRecordPath
        if (($RecordItem.Attributes -band [System.IO.FileAttributes]::ReparsePoint) -ne 0) {
            Write-Failure "Input record cannot be a reparse point."
        }
        if ($RecordItem.Length -gt 16777216) {
            Write-Failure "Input record exceeds the 16 MiB Stage limit."
        }
        $RecordText = [System.IO.File]::ReadAllText($FullRecordPath)
        if (-not $RecordText.TrimStart().StartsWith("{")) {
            Write-Failure "Input record file must contain one full JSON object."
        }
        try {
            $Record = $RecordText | ConvertFrom-Json
            $Merged = Merge-GdsRecord $Records $Record $Schema
        }
        catch {
            Write-Failure "Record or accumulated dataset does not match the Snapshot schema or uniqueness rules: $Dataset."
        }
        $Mode = "full-record"
    }

    if ($Merged.Action -ceq "no_change") {
        $DatasetBytes = if (Test-Path -LiteralPath $DatasetPath) {
            [System.IO.File]::ReadAllBytes($DatasetPath)
        }
        else {
            [byte[]]@()
        }
        $DatasetHash = if (Test-Path -LiteralPath $DatasetPath) {
            (Get-FileHash -LiteralPath $DatasetPath -Algorithm SHA256).Hash.ToLowerInvariant()
        }
        else {
            "none"
        }
        [Console]::Out.WriteLine("ok=true")
        [Console]::Out.WriteLine("dataset=$Dataset")
        [Console]::Out.WriteLine("mode=$Mode")
        [Console]::Out.WriteLine("base=$($Merged.Base)")
        [Console]::Out.WriteLine("action=no_change")
        [Console]::Out.WriteLine("changed_field_count=$($Merged.ChangedFieldCount)")
        [Console]::Out.WriteLine("record_count=$($Merged.Records.Count)")
        [Console]::Out.WriteLine("bytes=$($DatasetBytes.Length)")
        [Console]::Out.WriteLine("sha256=$DatasetHash")
        [Console]::Out.WriteLine("review_stale=false")
        exit 0
    }
    $DatasetJson = ConvertTo-Json -InputObject ([object[]]$Merged.Records) -Depth 20
    $Utf8NoBom = New-Object System.Text.UTF8Encoding($false)
    $DatasetBytes = $Utf8NoBom.GetBytes($DatasetJson + "`n")
    if ($DatasetBytes.Length -gt 16777216) {
        Write-Failure "Result exceeds the 16 MiB Stage limit."
    }
    $TemporaryPath = "$DatasetPath.upsert.$([guid]::NewGuid().ToString('N')).tmp"
    [System.IO.File]::WriteAllBytes($TemporaryPath, $DatasetBytes)
    if (Test-Path -LiteralPath $DatasetPath) {
        [System.IO.File]::Replace($TemporaryPath, $DatasetPath, $null)
    }
    else {
        [System.IO.File]::Move($TemporaryPath, $DatasetPath)
    }
    $DatasetHash = (Get-FileHash -LiteralPath $DatasetPath -Algorithm SHA256).Hash.ToLowerInvariant()

    [Console]::Out.WriteLine("ok=true")
    [Console]::Out.WriteLine("dataset=$Dataset")
    [Console]::Out.WriteLine("mode=$Mode")
    if ($Mode -ceq "field-edit") {
        [Console]::Out.WriteLine("base=$($Merged.Base)")
        [Console]::Out.WriteLine("changed_field_count=$($Merged.ChangedFieldCount)")
    }
    [Console]::Out.WriteLine("action=$($Merged.Action)")
    [Console]::Out.WriteLine("record_count=$($Merged.Records.Count)")
    [Console]::Out.WriteLine("bytes=$($DatasetBytes.Length)")
    [Console]::Out.WriteLine("sha256=$DatasetHash")
    [Console]::Out.WriteLine("review_stale=true")
    exit 0
}
catch {
    Write-Failure "Local metadata record upsert failed."
}
