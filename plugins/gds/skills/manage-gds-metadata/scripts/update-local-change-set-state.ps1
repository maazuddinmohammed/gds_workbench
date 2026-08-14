param(
    [string]$ChangeSetPath = (Join-Path (Get-Location).Path "gds-workspace\change-set"),
    [Parameter(Mandatory = $true)]
    [string]$MetadataChangeSetId,
    [Parameter(Mandatory = $true)]
    [long]$ExpectedCurrentRevision,
    [Parameter(Mandatory = $true)]
    [long]$ServerRevision,
    [Parameter(Mandatory = $true)]
    [string]$ServerStatus,
    [string]$StagedDataset = "",
    [string]$StagedSha256 = ""
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
    if ($ExpectedCurrentRevision -le 0 -or $ServerRevision -le 0) {
        Write-Failure "Expected and server revisions must be positive."
    }
    if ($ServerRevision -lt $ExpectedCurrentRevision) {
        Write-Failure "Server revision cannot move backwards."
    }
    if ($ServerStatus -cnotin @("active", "validated")) {
        Write-Failure "Server status must be active or validated."
    }
    if ([string]::IsNullOrWhiteSpace($MetadataChangeSetId)) {
        Write-Failure "Metadata Change Set ID is required."
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
    $TemporaryStatePath = Join-Path $Root "change-set.state.tmp.json"
    if (-not (Test-Path -LiteralPath $StatePath -PathType Leaf)) {
        Write-Failure "change-set.json is missing."
    }
    if (Test-Path -LiteralPath $TemporaryStatePath) {
        Write-Failure "A previous state update is incomplete; do not overwrite it."
    }
    try {
        $State = [System.IO.File]::ReadAllText($StatePath) | ConvertFrom-Json
    }
    catch {
        Write-Failure "change-set.json is not valid JSON."
    }
    if (([string]$State.server_change_set.metadata_change_set_id) -cne $MetadataChangeSetId) {
        Write-Failure "Metadata Change Set ID does not match local state."
    }
    if ([long]$State.server_change_set.draft_revision -ne $ExpectedCurrentRevision) {
        Write-Failure "Expected revision does not match local state."
    }
    if ($null -eq $State.datasets -or $State.datasets -isnot [PSCustomObject]) {
        Write-Failure "Local dataset state is invalid."
    }

    $HasDataset = -not [string]::IsNullOrWhiteSpace($StagedDataset)
    $HasSha = -not [string]::IsNullOrWhiteSpace($StagedSha256)
    if ($HasDataset -ne $HasSha) {
        Write-Failure "Staged dataset and SHA-256 must be supplied together."
    }
    $StageRecorded = $false
    $RecordCount = 0
    $ActualSha256 = ""
    if ($HasDataset) {
        $AllowedDatasets = @(
            "source_object", "source_attribute", "bronze_object", "bronze_attribute",
            "silver_object", "silver_attribute", "gold_object", "gold_attribute",
            "ingestion_object_mapping", "ingestion_attribute_mapping", "copy_group",
            "member_group", "copy_group_control", "copy", "process_group", "process"
        )
        if ($AllowedDatasets -cnotcontains $StagedDataset) {
            Write-Failure "Staged dataset is not Change Set eligible."
        }
        if ($StagedSha256 -cnotmatch '^[0-9A-Fa-f]{64}$') {
            Write-Failure "Staged SHA-256 is invalid."
        }
        if ($ServerStatus -cne "active") {
            Write-Failure "A Stage result must return active status."
        }
        if ($ServerRevision -ne ($ExpectedCurrentRevision + 1)) {
            Write-Failure "A Stage result must increment revision by exactly one."
        }

        $DatasetPath = Join-Path $Root "datasets\$StagedDataset.json"
        if (-not (Test-Path -LiteralPath $DatasetPath -PathType Leaf)) {
            Write-Failure "Staged local dataset file is missing."
        }
        $DatasetItem = Get-Item -LiteralPath $DatasetPath
        if (($DatasetItem.Attributes -band [System.IO.FileAttributes]::ReparsePoint) -ne 0) {
            Write-Failure "Staged local dataset file cannot be a reparse point."
        }
        if ($DatasetItem.Length -gt 16777216) {
            Write-Failure "Staged dataset exceeds the 16 MiB Stage limit."
        }
        $DatasetText = [System.IO.File]::ReadAllText($DatasetPath)
        if (-not $DatasetText.TrimStart().StartsWith("[")) {
            Write-Failure "Staged dataset must contain one JSON array."
        }
        try {
            $Records = @($DatasetText | ConvertFrom-Json)
        }
        catch {
            Write-Failure "Staged dataset is not valid JSON."
        }
        $SchemaPath = Join-Path $Workspace.FullName "metadata-snapshot\schemas\$StagedDataset.schema.json"
        if (-not (Test-Path -LiteralPath $SchemaPath -PathType Leaf)) {
            Write-Failure "Snapshot dataset schema is missing."
        }
        try {
            $Schema = [System.IO.File]::ReadAllText($SchemaPath) | ConvertFrom-Json
            Assert-GdsSchema $Schema $StagedDataset
            Assert-GdsDataset $Records $Schema
        }
        catch {
            Write-Failure "Staged local dataset does not match its schema or uniqueness rules."
        }
        $RecordCount = $Records.Count
        $ActualSha256 = (Get-FileHash -LiteralPath $DatasetPath -Algorithm SHA256).Hash.ToLowerInvariant()
        if ($ActualSha256 -cne $StagedSha256.ToLowerInvariant()) {
            Write-Failure "Dataset changed after the reviewed SHA-256 was produced."
        }

        $State.datasets.PSObject.Properties.Remove($StagedDataset)
        $DatasetState = [PSCustomObject][ordered]@{
            file = "datasets/$StagedDataset.json"
            record_count = $RecordCount
            staged_sha256 = $ActualSha256
            staged_revision = $ServerRevision
        }
        Add-Member -InputObject $State.datasets -MemberType NoteProperty -Name $StagedDataset -Value $DatasetState
        $StageRecorded = $true
    }
    elseif ($ServerRevision -gt $ExpectedCurrentRevision) {
        $State.datasets = [PSCustomObject]@{}
    }

    $State.server_change_set.draft_revision = $ServerRevision
    $State.server_change_set.status = $ServerStatus
    $StateJson = $State | ConvertTo-Json -Depth 8
    $Utf8NoBom = New-Object System.Text.UTF8Encoding($false)
    [System.IO.File]::WriteAllText($TemporaryStatePath, $StateJson + "`n", $Utf8NoBom)
    Move-Item -LiteralPath $TemporaryStatePath -Destination $StatePath -Force

    [Console]::Out.WriteLine("ok=true")
    [Console]::Out.WriteLine("change_set=$Root")
    [Console]::Out.WriteLine("metadata_change_set_id=$MetadataChangeSetId")
    [Console]::Out.WriteLine("previous_revision=$ExpectedCurrentRevision")
    [Console]::Out.WriteLine("draft_revision=$ServerRevision")
    [Console]::Out.WriteLine("server_status=$ServerStatus")
    [Console]::Out.WriteLine("stage_recorded=$($StageRecorded.ToString().ToLowerInvariant())")
    if ($StageRecorded) {
        [Console]::Out.WriteLine("dataset=$StagedDataset")
        [Console]::Out.WriteLine("record_count=$RecordCount")
        [Console]::Out.WriteLine("staged_sha256=$ActualSha256")
    }
    exit 0
}
catch {
    Write-Failure "Local Change Set state update failed."
}
