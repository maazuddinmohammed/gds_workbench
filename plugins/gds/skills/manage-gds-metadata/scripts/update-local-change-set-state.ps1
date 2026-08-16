param(
    [string]$ChangeSetPath = (Join-Path (Get-Location).Path "GDS\change-set"),
    [Parameter(Mandatory = $true)]
    [string]$MetadataChangeSetId,
    [Parameter(Mandatory = $true)]
    [long]$ExpectedCurrentRevision,
    [Parameter(Mandatory = $true)]
    [long]$ServerRevision,
    [Parameter(Mandatory = $true)]
    [string]$ServerStatus,
    [string]$StagedDataset = "",
    [string]$StagedSha256 = "",
    [string]$StagedPairs = ""
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
    if ($null -eq $Workspace -or [System.IO.Path]::GetFileName($Workspace.FullName) -cne "GDS") {
        Write-Failure "Local change-set must be directly under GDS."
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
    if ($HasDataset -and -not [string]::IsNullOrWhiteSpace($StagedPairs)) {
        Write-Failure "Use either the single staged dataset options or staged pairs."
    }

    $RawPairs = @()
    if ($HasDataset) {
        $RawPairs = @("$StagedDataset=$StagedSha256")
    }
    elseif (-not [string]::IsNullOrWhiteSpace($StagedPairs)) {
        $RawPairs = @($StagedPairs.Split([char]',', [System.StringSplitOptions]::RemoveEmptyEntries))
    }

    $StageRecorded = $false
    $ValidatedEntries = New-Object 'System.Collections.Generic.List[object]'
    if ($RawPairs.Count -gt 0) {
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
        if ($RawPairs.Count -gt 16) {
            Write-Failure "At most 16 staged datasets may be recorded."
        }
        $SeenDatasets = New-Object 'System.Collections.Generic.HashSet[string]'
        foreach ($RawPair in $RawPairs) {
            $SeparatorIndex = $RawPair.IndexOf([char]'=')
            if ($SeparatorIndex -le 0 -or $SeparatorIndex -ne $RawPair.LastIndexOf([char]'=')) {
                Write-Failure "Each staged pair must be dataset=sha256."
            }
            $PairDataset = $RawPair.Substring(0, $SeparatorIndex)
            $PairSha256 = $RawPair.Substring($SeparatorIndex + 1)
            if ($AllowedDatasets -cnotcontains $PairDataset) {
                Write-Failure "Staged dataset is not Change Set eligible."
            }
            if (-not $SeenDatasets.Add($PairDataset)) {
                Write-Failure "A staged dataset can be supplied only once."
            }
            if ($PairSha256 -cnotmatch '^[0-9A-Fa-f]{64}$') {
                Write-Failure "Staged SHA-256 is invalid."
            }

            $DatasetPath = Join-Path $Root "datasets\$PairDataset.json"
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
            $SchemaPath = Join-Path $Workspace.FullName "metadata-snapshot\schemas\$PairDataset.schema.json"
            if (-not (Test-Path -LiteralPath $SchemaPath -PathType Leaf)) {
                Write-Failure "Snapshot dataset schema is missing."
            }
            try {
                $Schema = [System.IO.File]::ReadAllText($SchemaPath) | ConvertFrom-Json
                Assert-GdsSchema $Schema $PairDataset
                Assert-GdsDataset $Records $Schema
            }
            catch {
                Write-Failure "Staged local dataset does not match its schema or uniqueness rules."
            }
            $ActualSha256 = (Get-FileHash -LiteralPath $DatasetPath -Algorithm SHA256).Hash.ToLowerInvariant()
            if ($ActualSha256 -cne $PairSha256.ToLowerInvariant()) {
                Write-Failure "Dataset changed after the reviewed SHA-256 was produced."
            }
            [void]$ValidatedEntries.Add([PSCustomObject]@{
                Dataset = $PairDataset
                RecordCount = $Records.Count
                Sha256 = $ActualSha256
            })
        }

        foreach ($Entry in $ValidatedEntries) {
            $State.datasets.PSObject.Properties.Remove($Entry.Dataset)
            $DatasetState = [PSCustomObject][ordered]@{
                file = "datasets/$($Entry.Dataset).json"
                record_count = $Entry.RecordCount
                staged_sha256 = $Entry.Sha256
                staged_revision = $ServerRevision
            }
            Add-Member -InputObject $State.datasets -MemberType NoteProperty -Name $Entry.Dataset -Value $DatasetState
        }
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
        [Console]::Out.WriteLine("staged_dataset_count=$($ValidatedEntries.Count)")
        foreach ($Entry in $ValidatedEntries) {
            [Console]::Out.WriteLine("staged_dataset=$($Entry.Dataset)|$($Entry.RecordCount)|$($Entry.Sha256)")
        }
        if ($ValidatedEntries.Count -eq 1) {
            [Console]::Out.WriteLine("dataset=$($ValidatedEntries[0].Dataset)")
            [Console]::Out.WriteLine("record_count=$($ValidatedEntries[0].RecordCount)")
            [Console]::Out.WriteLine("staged_sha256=$($ValidatedEntries[0].Sha256)")
        }
    }
    exit 0
}
catch {
    Write-Failure "Local Change Set state update failed."
}
