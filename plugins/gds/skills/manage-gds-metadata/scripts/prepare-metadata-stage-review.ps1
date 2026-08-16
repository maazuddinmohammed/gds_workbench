param(
    [string]$ChangeSetPath = (Join-Path (Get-Location).Path "GDS\change-set"),
    [Parameter(Mandatory = $true)]
    [string]$MetadataChangeSetId,
    [Parameter(Mandatory = $true)]
    [long]$ExpectedDraftRevision
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
    if ($ExpectedDraftRevision -le 0 -or [string]::IsNullOrWhiteSpace($MetadataChangeSetId)) {
        Write-Failure "Metadata Change Set ID and positive revision are required."
    }
    $ScriptDirectory = Split-Path -Parent $MyInvocation.MyCommand.Path
    $SchemaHelper = Join-Path $ScriptDirectory "metadata-schema.ps1"
    if (-not (Test-Path -LiteralPath $SchemaHelper -PathType Leaf)) {
        Write-Failure "Bundled schema helper is missing."
    }
    . $SchemaHelper

    $AllowedDatasets = @(
        "source_object", "source_attribute", "bronze_object", "bronze_attribute",
        "silver_object", "silver_attribute", "gold_object", "gold_attribute",
        "ingestion_object_mapping", "ingestion_attribute_mapping", "copy_group",
        "member_group", "copy_group_control", "copy", "process_group", "process"
    )
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
    $DatasetsPath = Join-Path $Root "datasets"
    $SnapshotPath = Join-Path $Workspace.FullName "metadata-snapshot"
    $ManifestPath = Join-Path $SnapshotPath "manifest.json"
    $ReviewPath = Join-Path $Root "review.json"
    if (
        -not (Test-Path -LiteralPath $StatePath -PathType Leaf) -or
        -not (Test-Path -LiteralPath $DatasetsPath -PathType Container) -or
        -not (Test-Path -LiteralPath $ManifestPath -PathType Leaf)
    ) {
        Write-Failure "Local Change Set or referenced Snapshot is incomplete."
    }
    if (Test-Path -LiteralPath $ReviewPath) {
        $ReviewItem = Get-Item -LiteralPath $ReviewPath
        if ($ReviewItem.PSIsContainer -or ($ReviewItem.Attributes -band [System.IO.FileAttributes]::ReparsePoint) -ne 0) {
            Write-Failure "Existing Stage review is unsafe."
        }
    }
    try {
        $State = [System.IO.File]::ReadAllText($StatePath) | ConvertFrom-Json
        $Manifest = [System.IO.File]::ReadAllText($ManifestPath) | ConvertFrom-Json
    }
    catch {
        Write-Failure "Local state or Snapshot manifest is not valid JSON."
    }
    if (([string]$State.server_change_set.metadata_change_set_id) -cne $MetadataChangeSetId) {
        Write-Failure "Metadata Change Set ID does not match local state."
    }
    if ([long]$State.server_change_set.draft_revision -ne $ExpectedDraftRevision) {
        Write-Failure "Expected revision does not match local state."
    }
    if (([string]$Manifest.tenant_code) -cne ([string]$State.tenant.tenant_code)) {
        Write-Failure "Snapshot Tenant does not match local Change Set."
    }
    if (([string]$Manifest.snapshot_id) -cne ([string]$State.snapshot.snapshot_id)) {
        Write-Failure "Snapshot ID does not match local Change Set."
    }

    $DatasetFiles = @(Get-ChildItem -LiteralPath $DatasetsPath -Force | Sort-Object Name)
    if ($DatasetFiles.Count -eq 0) {
        Write-Failure "At least one local dataset is required for Stage review."
    }
    $ReviewDatasets = [ordered]@{}
    $Summaries = @()
    $Totals = [ordered]@{
        insert = 0
        update = 0
        deactivate = 0
        reactivate = 0
        no_change = 0
    }
    $RecordTotal = 0
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
        $SchemaPath = Join-Path $SnapshotPath "schemas\$DatasetName.schema.json"
        $RowsPath = Join-Path $SnapshotPath "data\operational\$DatasetName\rows.jsonl"
        if (-not (Test-Path -LiteralPath $SchemaPath -PathType Leaf) -or -not (Test-Path -LiteralPath $RowsPath -PathType Leaf)) {
            Write-Failure "Snapshot schema or rows are missing: $DatasetName."
        }
        try {
            $Schema = [System.IO.File]::ReadAllText($SchemaPath) | ConvertFrom-Json
            $DatasetText = [System.IO.File]::ReadAllText($DatasetFile.FullName)
            if (-not $DatasetText.TrimStart().StartsWith("[")) {
                throw "not an array"
            }
            $Records = @($DatasetText | ConvertFrom-Json)
            Assert-GdsSchema $Schema $DatasetName
            Assert-GdsDataset $Records $Schema
        }
        catch {
            Write-Failure "Dataset does not match its Snapshot schema or uniqueness rules: $DatasetName."
        }

        $CanonicalColumns = @($Schema.'x-gds-canonical-key')
        $WantedKeys = New-Object 'System.Collections.Generic.HashSet[string]'
        foreach ($Record in $Records) {
            [void]$WantedKeys.Add((Get-GdsNormalizedKey $Record $CanonicalColumns $Schema))
        }
        $Baseline = @{}
        try {
            foreach ($Line in (Get-Content -LiteralPath $RowsPath)) {
                if ([string]::IsNullOrWhiteSpace($Line)) {
                    continue
                }
                $SnapshotRecord = $Line | ConvertFrom-Json
                $SnapshotKey = Get-GdsNormalizedKey $SnapshotRecord $CanonicalColumns $Schema
                if ($WantedKeys.Contains($SnapshotKey)) {
                    if ($Baseline.ContainsKey($SnapshotKey)) {
                        throw "duplicate baseline key"
                    }
                    $Baseline[$SnapshotKey] = $SnapshotRecord
                }
            }
        }
        catch {
            Write-Failure "Snapshot baseline cannot be compared safely: $DatasetName."
        }

        $ActionCounts = [ordered]@{
            insert = 0
            update = 0
            deactivate = 0
            reactivate = 0
            no_change = 0
        }
        $WrappedRecords = @()
        foreach ($Record in $Records) {
            $NormalizedKey = Get-GdsNormalizedKey $Record $CanonicalColumns $Schema
            $Existing = $null
            if ($Baseline.ContainsKey($NormalizedKey)) {
                $Existing = $Baseline[$NormalizedKey]
            }
            $Action = Get-GdsRecordAction $Record $Existing $Schema
            $ActionCounts[$Action] = [int]$ActionCounts[$Action] + 1
            $Totals[$Action] = [int]$Totals[$Action] + 1
            $ReviewedRecord = [ordered]@{
                action = $Action
                canonical_key = Get-GdsCanonicalKeyObject $Record $CanonicalColumns
            }
            $ActiveProperty = $Record.PSObject.Properties["is_active"]
            if ($null -ne $ActiveProperty) {
                $ReviewedRecord["is_active"] = [bool]$ActiveProperty.Value
            }
            $WrappedRecords += [PSCustomObject]@{
                SortKey = $NormalizedKey
                Value = [PSCustomObject]$ReviewedRecord
            }
        }
        $ReviewRecords = @($WrappedRecords | Sort-Object SortKey | ForEach-Object { $_.Value })
        $DatasetHash = (Get-FileHash -LiteralPath $DatasetFile.FullName -Algorithm SHA256).Hash.ToLowerInvariant()
        $ReviewDatasets[$DatasetName] = [ordered]@{
            file = "datasets/$DatasetName.json"
            sha256 = $DatasetHash
            record_count = $Records.Count
            canonical_key = [object[]]$CanonicalColumns
            actions = $ActionCounts
            records = [object[]]$ReviewRecords
        }
        $Summaries += "dataset=$DatasetName|$($Records.Count)|$($ActionCounts.insert)|$($ActionCounts.update)|$($ActionCounts.deactivate)|$($ActionCounts.reactivate)|$($ActionCounts.no_change)|$DatasetHash"
        $RecordTotal += $Records.Count
    }

    $Review = [ordered]@{
        format_version = "1.0"
        tenant = [ordered]@{
            tenant_id = [long]$State.tenant.tenant_id
            tenant_code = [string]$State.tenant.tenant_code
        }
        snapshot_id = [string]$State.snapshot.snapshot_id
        server_change_set = [ordered]@{
            metadata_change_set_id = [string]$State.server_change_set.metadata_change_set_id
            draft_revision = [long]$State.server_change_set.draft_revision
        }
        datasets = $ReviewDatasets
    }
    $ReviewJson = ConvertTo-Json -InputObject $Review -Depth 20
    $Utf8NoBom = New-Object System.Text.UTF8Encoding($false)
    $ReviewBytes = $Utf8NoBom.GetBytes($ReviewJson + "`n")
    if ($ReviewBytes.Length -gt 33554432) {
        Write-Failure "Stage review exceeds 32 MiB."
    }
    $TemporaryReviewPath = "$ReviewPath.$([guid]::NewGuid().ToString('N')).tmp"
    [System.IO.File]::WriteAllBytes($TemporaryReviewPath, $ReviewBytes)
    if (Test-Path -LiteralPath $ReviewPath) {
        [System.IO.File]::Replace($TemporaryReviewPath, $ReviewPath, $null)
    }
    else {
        [System.IO.File]::Move($TemporaryReviewPath, $ReviewPath)
    }

    [Console]::Out.WriteLine("ok=true")
    [Console]::Out.WriteLine("review=$ReviewPath")
    [Console]::Out.WriteLine("metadata_change_set_id=$MetadataChangeSetId")
    [Console]::Out.WriteLine("draft_revision=$ExpectedDraftRevision")
    foreach ($Summary in $Summaries) {
        [Console]::Out.WriteLine($Summary)
    }
    [Console]::Out.WriteLine("dataset_count=$($DatasetFiles.Count)")
    [Console]::Out.WriteLine("record_count=$RecordTotal")
    [Console]::Out.WriteLine("insert_count=$($Totals.insert)")
    [Console]::Out.WriteLine("update_count=$($Totals.update)")
    [Console]::Out.WriteLine("deactivate_count=$($Totals.deactivate)")
    [Console]::Out.WriteLine("reactivate_count=$($Totals.reactivate)")
    [Console]::Out.WriteLine("no_change_count=$($Totals.no_change)")
    exit 0
}
catch {
    Write-Failure "Metadata Stage review failed."
}
