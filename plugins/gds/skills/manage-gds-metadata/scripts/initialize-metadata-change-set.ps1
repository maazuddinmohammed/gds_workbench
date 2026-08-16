param(
    [string]$WorkspacePath = (Join-Path (Get-Location).Path "GDS"),
    [Parameter(Mandatory = $true)]
    [long]$TenantId,
    [Parameter(Mandatory = $true)]
    [string]$TenantCode,
    [Parameter(Mandatory = $true)]
    [string]$SnapshotId,
    [Parameter(Mandatory = $true)]
    [string]$SnapshotUsage,
    [Parameter(Mandatory = $true)]
    [string]$MetadataChangeSetId,
    [Parameter(Mandatory = $true)]
    [string]$ServerStatus,
    [Parameter(Mandatory = $true)]
    [long]$DraftRevision,
    [switch]$AcknowledgeOutdatedSnapshot
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
    if ($TenantId -le 0 -or [string]::IsNullOrWhiteSpace($TenantCode)) {
        Write-Failure "Tenant ID and Tenant code are required."
    }
    if ($DraftRevision -le 0) {
        Write-Failure "Draft revision must be positive."
    }
    [guid]$ParsedSnapshotId = [guid]::Empty
    [guid]$ParsedChangeSetId = [guid]::Empty
    if (-not [guid]::TryParse($SnapshotId, [ref]$ParsedSnapshotId)) {
        Write-Failure "Snapshot ID must be a UUID."
    }
    if (-not [guid]::TryParse($MetadataChangeSetId, [ref]$ParsedChangeSetId)) {
        Write-Failure "Metadata Change Set ID must be a UUID."
    }
    if ($SnapshotUsage -cnotin @("fresh", "reused")) {
        Write-Failure "Snapshot usage must be fresh or reused."
    }
    if ($ServerStatus -cnotin @("active", "validated")) {
        Write-Failure "Server status must be active or validated."
    }
    if ($SnapshotUsage -ceq "reused" -and -not $AcknowledgeOutdatedSnapshot) {
        Write-Failure "Reused Snapshot requires explicit outdated-Snapshot acknowledgement."
    }
    if ($SnapshotUsage -ceq "fresh" -and $AcknowledgeOutdatedSnapshot) {
        Write-Failure "Fresh Snapshot cannot be marked as outdated."
    }

    $Workspace = [System.IO.Path]::GetFullPath($WorkspacePath)
    $TrimCharacters = [char[]]@(
        [System.IO.Path]::DirectorySeparatorChar,
        [System.IO.Path]::AltDirectorySeparatorChar
    )
    $Workspace = $Workspace.TrimEnd($TrimCharacters)
    if ([System.IO.Path]::GetFileName($Workspace) -cne "GDS") {
        Write-Failure "Workspace directory must be named GDS."
    }
    if (-not (Test-Path -LiteralPath $Workspace -PathType Container)) {
        Write-Failure "Workspace directory does not exist."
    }
    $WorkspaceItem = Get-Item -LiteralPath $Workspace
    if (($WorkspaceItem.Attributes -band [System.IO.FileAttributes]::ReparsePoint) -ne 0) {
        Write-Failure "Workspace directory cannot be a reparse point."
    }

    $SnapshotPath = Join-Path $Workspace "metadata-snapshot"
    $ManifestPath = Join-Path $SnapshotPath "manifest.json"
    if (-not (Test-Path -LiteralPath $ManifestPath -PathType Leaf)) {
        Write-Failure "Validated metadata-snapshot is required."
    }
    try {
        $Manifest = [System.IO.File]::ReadAllText($ManifestPath) | ConvertFrom-Json
    }
    catch {
        Write-Failure "Snapshot manifest is not valid JSON."
    }
    if (([string]$Manifest.tenant_code) -cne $TenantCode) {
        Write-Failure "Snapshot Tenant does not match the Change Set Tenant."
    }
    if (([string]$Manifest.snapshot_id) -cne $SnapshotId) {
        Write-Failure "Snapshot ID does not match the selected Snapshot."
    }

    $ChangeSetPath = Join-Path $Workspace "change-set"
    $AdoptedLocalDraft = $false
    if (Test-Path -LiteralPath $ChangeSetPath) {
        $ChangeSetItem = Get-Item -LiteralPath $ChangeSetPath
        if (-not $ChangeSetItem.PSIsContainer -or ($ChangeSetItem.Attributes -band [System.IO.FileAttributes]::ReparsePoint) -ne 0) {
            Write-Failure "Local change-set is unsafe."
        }
        $StatePath = Join-Path $ChangeSetPath "change-set.json"
        $DatasetsPath = Join-Path $ChangeSetPath "datasets"
        if (-not (Test-Path -LiteralPath $StatePath -PathType Leaf) -or -not (Test-Path -LiteralPath $DatasetsPath -PathType Container)) {
            Write-Failure "Existing local draft structure is incomplete."
        }
        foreach ($Entry in @(Get-ChildItem -LiteralPath $ChangeSetPath -Force -Recurse)) {
            if (($Entry.Attributes -band [System.IO.FileAttributes]::ReparsePoint) -ne 0) {
                Write-Failure "Existing local draft cannot contain reparse points."
            }
        }
        foreach ($RootEntry in @(Get-ChildItem -LiteralPath $ChangeSetPath -Force)) {
            if ($RootEntry.Name -cnotin @("change-set.json", "datasets")) {
                Write-Failure "Existing local draft contains an unexpected root entry."
            }
        }
        try {
            $LocalState = [System.IO.File]::ReadAllText($StatePath) | ConvertFrom-Json
        }
        catch {
            Write-Failure "Existing local draft state is not valid JSON."
        }
        if (([string]$LocalState.format_version) -cne "1.0") {
            Write-Failure "Existing local draft format is invalid."
        }
        if (([string]$LocalState.tenant.tenant_code) -cne $TenantCode) {
            Write-Failure "Existing local draft Tenant does not match."
        }
        if (([string]$LocalState.snapshot.snapshot_id) -cne $SnapshotId -or ([string]$LocalState.snapshot.path) -cne "../metadata-snapshot") {
            Write-Failure "Existing local draft Snapshot does not match."
        }
        if (([string]$LocalState.server_change_set.status) -cne "local") {
            Write-Failure "Local change-set already exists; stop and ask whether to reuse it."
        }
        if (([string]$LocalState.snapshot.usage) -cne "local" -or $LocalState.snapshot.outdated_snapshot_warning_acknowledged -cne $false) {
            Write-Failure "Existing local draft Snapshot state is invalid."
        }
        if ($null -eq $LocalState.datasets -or $LocalState.datasets -isnot [PSCustomObject] -or @($LocalState.datasets.PSObject.Properties).Count -ne 0) {
            Write-Failure "Existing local draft contains server Stage state."
        }
        $AllowedDatasets = @(
            "source_object", "source_attribute", "bronze_object", "bronze_attribute",
            "silver_object", "silver_attribute", "gold_object", "gold_attribute",
            "ingestion_object_mapping", "ingestion_attribute_mapping", "copy_group",
            "member_group", "copy_group_control", "copy", "process_group", "process"
        )
        foreach ($DatasetFile in @(Get-ChildItem -LiteralPath $DatasetsPath -Force)) {
            if ($DatasetFile.PSIsContainer -or $DatasetFile.Extension -cne ".json" -or $AllowedDatasets -cnotcontains $DatasetFile.BaseName) {
                Write-Failure "Existing local draft contains an ineligible dataset."
            }
        }
        $AdoptedLocalDraft = $true
    }
    else {
        New-Item -ItemType Directory -Path $ChangeSetPath | Out-Null
        New-Item -ItemType Directory -Path (Join-Path $ChangeSetPath "datasets") | Out-Null
    }

    $State = [ordered]@{
        format_version = "1.0"
        tenant = [ordered]@{
            tenant_id = $TenantId
            tenant_code = $TenantCode
        }
        snapshot = [ordered]@{
            snapshot_id = $SnapshotId
            path = "../metadata-snapshot"
            usage = $SnapshotUsage
            outdated_snapshot_warning_acknowledged = [bool]$AcknowledgeOutdatedSnapshot
        }
        server_change_set = [ordered]@{
            metadata_change_set_id = $MetadataChangeSetId
            draft_revision = $DraftRevision
            status = $ServerStatus
        }
        datasets = [ordered]@{}
    }
    $StatePath = Join-Path $ChangeSetPath "change-set.json"
    $TemporaryStatePath = Join-Path $ChangeSetPath "change-set.json.tmp"
    $StateJson = $State | ConvertTo-Json -Depth 5
    $Utf8NoBom = New-Object System.Text.UTF8Encoding($false)
    [System.IO.File]::WriteAllText($TemporaryStatePath, $StateJson + "`n", $Utf8NoBom)
    Move-Item -LiteralPath $TemporaryStatePath -Destination $StatePath -Force

    [Console]::Out.WriteLine("ok=true")
    [Console]::Out.WriteLine("change_set=$ChangeSetPath")
    [Console]::Out.WriteLine("tenant_id=$TenantId")
    [Console]::Out.WriteLine("tenant_code=$TenantCode")
    [Console]::Out.WriteLine("snapshot_id=$SnapshotId")
    [Console]::Out.WriteLine("snapshot_usage=$SnapshotUsage")
    [Console]::Out.WriteLine("metadata_change_set_id=$MetadataChangeSetId")
    [Console]::Out.WriteLine("draft_revision=$DraftRevision")
    [Console]::Out.WriteLine("server_status=$ServerStatus")
    [Console]::Out.WriteLine("adopted_local_draft=$($AdoptedLocalDraft.ToString().ToLowerInvariant())")
    exit 0
}
catch {
    Write-Failure "Local Change Set initialization failed."
}
