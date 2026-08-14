param(
    [string]$ChangeSetPath = (Join-Path (Get-Location).Path "gds-workspace\change-set"),
    [Parameter(Mandatory = $true)]
    [string]$ExpectedMetadataChangeSetId,
    [Parameter(Mandatory = $true)]
    [long]$ExpectedDraftRevision,
    [switch]$RequireStaged
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
    if ($ExpectedDraftRevision -le 0) {
        Write-Failure "Expected draft revision must be positive."
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
    if ($null -eq $Workspace -or [System.IO.Path]::GetFileName($Workspace.FullName) -cne "gds-workspace") {
        Write-Failure "Local change-set must be directly under gds-workspace."
    }
    if (-not (Test-Path -LiteralPath $Root -PathType Container)) {
        Write-Failure "Local change-set does not exist."
    }

    $StatePath = Join-Path $Root "change-set.json"
    $DatasetsPath = Join-Path $Root "datasets"
    if (-not (Test-Path -LiteralPath $StatePath -PathType Leaf)) {
        Write-Failure "change-set.json is missing."
    }
    if (-not (Test-Path -LiteralPath $DatasetsPath -PathType Container)) {
        Write-Failure "datasets directory is missing."
    }
    $AllEntries = @(Get-ChildItem -LiteralPath $Root -Force -Recurse)
    foreach ($Entry in $AllEntries) {
        if (($Entry.Attributes -band [System.IO.FileAttributes]::ReparsePoint) -ne 0) {
            Write-Failure "Local change-set cannot contain reparse points."
        }
    }
    $RootEntries = @(Get-ChildItem -LiteralPath $Root -Force)
    foreach ($RootEntry in $RootEntries) {
        if ($RootEntry.Name -cnotin @("change-set.json", "datasets")) {
            Write-Failure "Local change-set contains an unexpected root entry."
        }
    }

    try {
        $State = [System.IO.File]::ReadAllText($StatePath) | ConvertFrom-Json
    }
    catch {
        Write-Failure "change-set.json is not valid JSON."
    }
    if (([string]$State.format_version) -cne "1.0") {
        Write-Failure "Unsupported local Change Set format."
    }
    if ([long]$State.tenant.tenant_id -le 0 -or [string]::IsNullOrWhiteSpace([string]$State.tenant.tenant_code)) {
        Write-Failure "Local Tenant identity is invalid."
    }
    if (([string]$State.snapshot.path) -cne "../metadata-snapshot") {
        Write-Failure "Snapshot path must be ../metadata-snapshot."
    }
    $SnapshotUsage = [string]$State.snapshot.usage
    $OutdatedAcknowledged = $State.snapshot.outdated_snapshot_warning_acknowledged
    if (
        ($SnapshotUsage -ceq "fresh" -and $OutdatedAcknowledged -cne $false) -or
        ($SnapshotUsage -ceq "reused" -and $OutdatedAcknowledged -cne $true) -or
        $SnapshotUsage -cnotin @("fresh", "reused")
    ) {
        Write-Failure "Snapshot usage and warning acknowledgement are inconsistent."
    }
    if (([string]$State.server_change_set.metadata_change_set_id) -cne $ExpectedMetadataChangeSetId) {
        Write-Failure "Metadata Change Set ID does not match the server draft."
    }
    if ([long]$State.server_change_set.draft_revision -ne $ExpectedDraftRevision) {
        Write-Failure "Draft revision does not match the server draft."
    }
    if (([string]$State.server_change_set.status) -cnotin @("active", "validated")) {
        Write-Failure "Local server status is invalid."
    }
    if ($null -eq $State.datasets -or $State.datasets -isnot [PSCustomObject]) {
        Write-Failure "Local dataset state must be a JSON object."
    }

    $ManifestPath = Join-Path $Workspace.FullName "metadata-snapshot\manifest.json"
    if (-not (Test-Path -LiteralPath $ManifestPath -PathType Leaf)) {
        Write-Failure "Referenced metadata-snapshot is missing."
    }
    try {
        $Manifest = [System.IO.File]::ReadAllText($ManifestPath) | ConvertFrom-Json
    }
    catch {
        Write-Failure "Snapshot manifest is not valid JSON."
    }
    if (([string]$Manifest.tenant_code) -cne ([string]$State.tenant.tenant_code)) {
        Write-Failure "Snapshot Tenant does not match local Change Set."
    }
    if (([string]$Manifest.snapshot_id) -cne ([string]$State.snapshot.snapshot_id)) {
        Write-Failure "Snapshot ID does not match local Change Set."
    }

    $AllowedDatasets = @(
        "source_object", "source_attribute", "bronze_object", "bronze_attribute",
        "silver_object", "silver_attribute", "gold_object", "gold_attribute",
        "ingestion_object_mapping", "ingestion_attribute_mapping", "copy_group",
        "member_group", "copy_group_control", "copy", "process_group", "process"
    )
    $StagedDatasetNames = @($State.datasets.PSObject.Properties.Name)
    foreach ($StagedDatasetName in $StagedDatasetNames) {
        if ($AllowedDatasets -cnotcontains $StagedDatasetName) {
            Write-Failure "Local state contains an unknown staged dataset."
        }
        $StagedDatasetPath = Join-Path $DatasetsPath "$StagedDatasetName.json"
        if (-not (Test-Path -LiteralPath $StagedDatasetPath -PathType Leaf)) {
            Write-Failure "A staged dataset file is missing."
        }
    }
    $DatasetFiles = @(Get-ChildItem -LiteralPath $DatasetsPath -Force)
    $Summaries = @()
    foreach ($DatasetFile in $DatasetFiles) {
        if ($DatasetFile.PSIsContainer -or $DatasetFile.Extension -cne ".json") {
            Write-Failure "datasets may contain only regular JSON files."
        }
        $DatasetName = $DatasetFile.BaseName
        if ($AllowedDatasets -cnotcontains $DatasetName) {
            Write-Failure "Dataset is not Change Set eligible: $DatasetName."
        }
        if ($DatasetFile.Length -gt 16777216) {
            Write-Failure "Dataset exceeds the 16 MiB Stage limit: $DatasetName."
        }
        $DatasetText = [System.IO.File]::ReadAllText($DatasetFile.FullName)
        if (-not $DatasetText.TrimStart().StartsWith("[")) {
            Write-Failure "Dataset file must contain one JSON array: $DatasetName."
        }
        try {
            $Records = @($DatasetText | ConvertFrom-Json)
        }
        catch {
            Write-Failure "Dataset file is not valid JSON: $DatasetName."
        }
        $SchemaPath = Join-Path $Workspace.FullName "metadata-snapshot\schemas\$DatasetName.schema.json"
        if (-not (Test-Path -LiteralPath $SchemaPath -PathType Leaf)) {
            Write-Failure "Snapshot dataset schema is missing: $DatasetName."
        }
        try {
            $Schema = [System.IO.File]::ReadAllText($SchemaPath) | ConvertFrom-Json
            Assert-GdsSchema $Schema $DatasetName
            Assert-GdsDataset $Records $Schema
        }
        catch {
            Write-Failure "Dataset does not match its schema or uniqueness rules: $DatasetName."
        }
        $DatasetHash = (Get-FileHash -LiteralPath $DatasetFile.FullName -Algorithm SHA256).Hash.ToLowerInvariant()
        $Staged = $false
        $StagedRevision = ""
        $StagedProperty = $State.datasets.PSObject.Properties[$DatasetName]
        if ($null -ne $StagedProperty) {
            $StagedState = $StagedProperty.Value
            if (([string]$StagedState.file) -cne "datasets/$DatasetName.json") {
                Write-Failure "Staged dataset path is invalid: $DatasetName."
            }
            if ([long]$StagedState.record_count -lt 0) {
                Write-Failure "Staged dataset record count is invalid: $DatasetName."
            }
            if (([string]$StagedState.staged_sha256) -cnotmatch '^[0-9a-f]{64}$') {
                Write-Failure "Staged dataset SHA-256 is invalid: $DatasetName."
            }
            if ([long]$StagedState.staged_revision -le 0 -or [long]$StagedState.staged_revision -gt $ExpectedDraftRevision) {
                Write-Failure "Staged dataset revision is invalid: $DatasetName."
            }
            $StagedRevision = [string]$StagedState.staged_revision
            if (
                [long]$StagedState.record_count -eq $Records.Count -and
                ([string]$StagedState.staged_sha256) -ceq $DatasetHash
            ) {
                $Staged = $true
            }
        }
        if ($RequireStaged -and -not $Staged) {
            Write-Failure "Dataset is not synchronized with a successful Stage: $DatasetName."
        }
        $StagedText = $Staged.ToString().ToLowerInvariant()
        $Summaries += "dataset=$DatasetName|$($Records.Count)|$($DatasetFile.Length)|$DatasetHash|$StagedText|$StagedRevision"
    }

    foreach ($Summary in $Summaries) {
        [Console]::Out.WriteLine($Summary)
    }
    [Console]::Out.WriteLine("ok=true")
    [Console]::Out.WriteLine("change_set=$Root")
    [Console]::Out.WriteLine("tenant_id=$($State.tenant.tenant_id)")
    [Console]::Out.WriteLine("tenant_code=$($State.tenant.tenant_code)")
    [Console]::Out.WriteLine("snapshot_id=$($State.snapshot.snapshot_id)")
    [Console]::Out.WriteLine("snapshot_usage=$SnapshotUsage")
    [Console]::Out.WriteLine("metadata_change_set_id=$($State.server_change_set.metadata_change_set_id)")
    [Console]::Out.WriteLine("draft_revision=$($State.server_change_set.draft_revision)")
    [Console]::Out.WriteLine("server_status=$($State.server_change_set.status)")
    [Console]::Out.WriteLine("dataset_count=$($DatasetFiles.Count)")
    exit 0
}
catch {
    Write-Failure "Local Change Set validation failed."
}
