param(
    [string]$SnapshotPath = (Join-Path (Get-Location).Path "gds-workspace\metadata-snapshot"),
    [Parameter(Mandatory = $true)]
    [string]$ExpectedTenantCode,
    [string]$ExpectedSnapshotId = ""
)

$ErrorActionPreference = "Stop"

function Write-Failure {
    param([string]$Message)
    [Console]::Error.WriteLine("ok=false")
    [Console]::Error.WriteLine("error=$Message")
    exit 2
}

function Read-NonnegativeInteger {
    param($Value, [string]$Name)
    [long]$Parsed = 0
    if (-not [long]::TryParse([string]$Value, [ref]$Parsed) -or $Parsed -lt 0) {
        Write-Failure "$Name must be a non-negative integer."
    }
    return $Parsed
}

try {
    if ($PSVersionTable.PSVersion.Major -lt 5) {
        Write-Failure "PowerShell 5.1 or newer is required."
    }
    if ([string]::IsNullOrWhiteSpace($ExpectedTenantCode)) {
        Write-Failure "Expected Tenant code is required."
    }

    $Root = [System.IO.Path]::GetFullPath($SnapshotPath)
    $TrimCharacters = [char[]]@(
        [System.IO.Path]::DirectorySeparatorChar,
        [System.IO.Path]::AltDirectorySeparatorChar
    )
    $Root = $Root.TrimEnd($TrimCharacters)
    if ([System.IO.Path]::GetFileName($Root) -cne "metadata-snapshot") {
        Write-Failure "Snapshot directory must be named metadata-snapshot."
    }
    if (-not (Test-Path -LiteralPath $Root -PathType Container)) {
        Write-Failure "Snapshot directory does not exist."
    }
    $RootItem = Get-Item -LiteralPath $Root
    if (($RootItem.Attributes -band [System.IO.FileAttributes]::ReparsePoint) -ne 0) {
        Write-Failure "Snapshot directory cannot be a reparse point."
    }

    $ManifestPath = Join-Path $Root "manifest.json"
    $CatalogPath = Join-Path $Root "catalog.json"
    $SchemasPath = Join-Path $Root "schemas"
    $DataPath = Join-Path $Root "data"
    foreach ($RequiredFile in @($ManifestPath, $CatalogPath)) {
        if (-not (Test-Path -LiteralPath $RequiredFile -PathType Leaf)) {
            Write-Failure "A required Snapshot file is missing."
        }
    }
    foreach ($RequiredDirectory in @($SchemasPath, $DataPath)) {
        if (-not (Test-Path -LiteralPath $RequiredDirectory -PathType Container)) {
            Write-Failure "A required Snapshot directory is missing."
        }
    }

    $AllEntries = @(Get-ChildItem -LiteralPath $Root -Force -Recurse)
    foreach ($Entry in $AllEntries) {
        if (($Entry.Attributes -band [System.IO.FileAttributes]::ReparsePoint) -ne 0) {
            Write-Failure "Snapshot cannot contain reparse points."
        }
    }

    try {
        $Manifest = [System.IO.File]::ReadAllText($ManifestPath) | ConvertFrom-Json
        $Catalog = [System.IO.File]::ReadAllText($CatalogPath) | ConvertFrom-Json
    }
    catch {
        Write-Failure "Snapshot manifest or catalog is not valid JSON."
    }

    if (([string]$Manifest.schema_version) -cne "2.0") {
        Write-Failure "Unsupported Snapshot schema version."
    }
    if (([string]$Manifest.snapshot_kind) -cne "metadata") {
        Write-Failure "Snapshot kind is not metadata."
    }
    if (($Manifest.database_ids_included -isnot [bool]) -or $Manifest.database_ids_included) {
        Write-Failure "Snapshot must be ID-free."
    }
    if (
        -not [string]::IsNullOrWhiteSpace($ExpectedSnapshotId) -and
        ([string]$Manifest.snapshot_id) -cne $ExpectedSnapshotId
    ) {
        Write-Failure "Snapshot ID does not match the MCP result."
    }
    if (([string]$Manifest.tenant_code) -cne $ExpectedTenantCode) {
        Write-Failure "Snapshot Tenant does not match the selected Tenant."
    }

    $LogicalDatasetCount = Read-NonnegativeInteger $Manifest.counts.logical_dataset_count "Logical dataset count"
    $FileCount = Read-NonnegativeInteger $Manifest.counts.file_count "File count"
    $DeclaredExpandedBytes = Read-NonnegativeInteger $Manifest.counts.expanded_bytes "Expanded bytes"
    $RowCount = Read-NonnegativeInteger $Manifest.counts.row_count "Row count"
    $SchemaCount = Read-NonnegativeInteger $Manifest.schemas.dataset_count "Schema count"
    $FoundationalCount = Read-NonnegativeInteger $Manifest.sections.foundational.dataset_count "Foundational dataset count"
    $ReferenceCount = Read-NonnegativeInteger $Manifest.sections.reference.dataset_count "Reference dataset count"
    $OperationalCount = Read-NonnegativeInteger $Manifest.sections.operational.dataset_count "Operational dataset count"
    if ($LogicalDatasetCount -ne 29 -or $SchemaCount -ne 29) {
        Write-Failure "Snapshot must contain 29 logical datasets and schemas."
    }
    if ($FoundationalCount -ne 5 -or $ReferenceCount -ne 8 -or $OperationalCount -ne 16) {
        Write-Failure "Snapshot section dataset counts are invalid."
    }
    if (([string]$Manifest.catalog.path) -cne "catalog.json") {
        Write-Failure "Manifest catalog path is invalid."
    }

    $Members = @($Manifest.members)
    if ($FileCount -ne ($Members.Count + 1)) {
        Write-Failure "Manifest file count is inconsistent."
    }
    $SeenPaths = @{}
    [long]$ActualExpandedBytes = (Get-Item -LiteralPath $ManifestPath).Length
    $RootPrefix = $Root + [System.IO.Path]::DirectorySeparatorChar
    foreach ($MemberRecord in $Members) {
        $MemberPath = [string]$MemberRecord.path
        if (
            [string]::IsNullOrWhiteSpace($MemberPath) -or
            $MemberPath -notmatch '^[A-Za-z0-9._/-]+$' -or
            [System.IO.Path]::IsPathRooted($MemberPath) -or
            $MemberPath.Contains("\")
        ) {
            Write-Failure "Manifest contains an unsafe member path."
        }
        $Segments = @($MemberPath.Split('/'))
        if ($Segments -contains "" -or $Segments -contains "." -or $Segments -contains "..") {
            Write-Failure "Manifest contains an unsafe member path."
        }
        if ($SeenPaths.ContainsKey($MemberPath)) {
            Write-Failure "Manifest contains a duplicate member path."
        }
        $SeenPaths[$MemberPath] = $true

        $WindowsMemberPath = $MemberPath.Replace([char]'/', [System.IO.Path]::DirectorySeparatorChar)
        $FullMemberPath = [System.IO.Path]::GetFullPath((Join-Path $Root $WindowsMemberPath))
        if (-not $FullMemberPath.StartsWith($RootPrefix, [System.StringComparison]::OrdinalIgnoreCase)) {
            Write-Failure "Manifest member escapes the Snapshot directory."
        }
        if (-not (Test-Path -LiteralPath $FullMemberPath -PathType Leaf)) {
            Write-Failure "A declared Snapshot member is missing."
        }
        $MemberItem = Get-Item -LiteralPath $FullMemberPath
        if (($MemberItem.Attributes -band [System.IO.FileAttributes]::ReparsePoint) -ne 0) {
            Write-Failure "Snapshot member cannot be a reparse point."
        }
        $MemberSize = Read-NonnegativeInteger $MemberRecord.size_bytes "Snapshot member size"
        if ($MemberItem.Length -ne $MemberSize) {
            Write-Failure "Snapshot member size mismatch: $MemberPath."
        }
        $ActualHash = (Get-FileHash -LiteralPath $FullMemberPath -Algorithm SHA256).Hash.ToLowerInvariant()
        if ($ActualHash -cne ([string]$MemberRecord.sha256).ToLowerInvariant()) {
            Write-Failure "Snapshot member hash mismatch: $MemberPath."
        }
        $ActualExpandedBytes += $MemberItem.Length
    }

    $ActualFileCount = @($AllEntries | Where-Object { -not $_.PSIsContainer }).Count
    if ($ActualFileCount -ne $FileCount) {
        Write-Failure "Snapshot contains missing or unexpected files."
    }
    if ($ActualExpandedBytes -ne $DeclaredExpandedBytes) {
        Write-Failure "Snapshot expanded-byte count is inconsistent."
    }
    $ActualCatalogHash = (Get-FileHash -LiteralPath $CatalogPath -Algorithm SHA256).Hash.ToLowerInvariant()
    if ($ActualCatalogHash -cne ([string]$Manifest.catalog.sha256).ToLowerInvariant()) {
        Write-Failure "Catalog hash does not match the manifest."
    }
    if (
        ([string]$Catalog.schema_version) -cne "2.0" -or
        ([string]$Catalog.snapshot_kind) -cne "metadata" -or
        ($Catalog.database_ids_included -isnot [bool]) -or
        $Catalog.database_ids_included
    ) {
        Write-Failure "Catalog contract is invalid."
    }

    [Console]::Out.WriteLine("ok=true")
    [Console]::Out.WriteLine("snapshot=$Root")
    [Console]::Out.WriteLine("snapshot_id=$($Manifest.snapshot_id)")
    [Console]::Out.WriteLine("tenant_code=$($Manifest.tenant_code)")
    [Console]::Out.WriteLine("member_count=$($Members.Count)")
    [Console]::Out.WriteLine("logical_dataset_count=$LogicalDatasetCount")
    [Console]::Out.WriteLine("row_count=$RowCount")
    [Console]::Out.WriteLine("expanded_bytes=$ActualExpandedBytes")
    exit 0
}
catch {
    Write-Failure "Snapshot validation failed."
}
