param(
    [string]$SnapshotPath = (Join-Path (Get-Location).Path "GDS\metadata-snapshot"),
    [string]$Dataset = ""
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
    if ($Dataset -and $Dataset -cnotmatch '^[a-z0-9_]+$') {
        Write-Failure "Dataset name is invalid."
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

    $CatalogPath = Join-Path $Root "catalog.json"
    if (-not (Test-Path -LiteralPath $CatalogPath -PathType Leaf)) {
        Write-Failure "catalog.json is missing."
    }
    $CatalogItem = Get-Item -LiteralPath $CatalogPath
    if (($CatalogItem.Attributes -band [System.IO.FileAttributes]::ReparsePoint) -ne 0) {
        Write-Failure "catalog.json cannot be a reparse point."
    }
    try {
        $Catalog = [System.IO.File]::ReadAllText($CatalogPath) | ConvertFrom-Json
    }
    catch {
        Write-Failure "catalog.json is not valid JSON."
    }
    if (
        ([string]$Catalog.schema_version) -cne "2.0" -or
        ([string]$Catalog.snapshot_kind) -cne "metadata" -or
        ($Catalog.database_ids_included -isnot [bool]) -or
        $Catalog.database_ids_included
    ) {
        Write-Failure "Catalog contract is invalid."
    }

    $Datasets = @(
        foreach ($Section in @($Catalog.sections)) {
            foreach ($Entry in @($Section.datasets)) {
                [PSCustomObject]@{
                    Section = [string]$Section.name
                    Entry = $Entry
                }
            }
        }
    )
    if ($Datasets.Count -ne 29) {
        Write-Failure "Catalog must contain 29 datasets."
    }

    if (-not $Dataset) {
        foreach ($Item in $Datasets) {
            [Console]::Out.WriteLine(
                "dataset=$($Item.Section)|$($Item.Entry.name)|$($Item.Entry.row_count)|$($Item.Entry.search_result_complete.ToString().ToLowerInvariant())"
            )
        }
        [Console]::Out.WriteLine("ok=true")
        [Console]::Out.WriteLine("dataset_count=$($Datasets.Count)")
        exit 0
    }

    $Matches = @($Datasets | Where-Object { ([string]$_.Entry.name) -ceq $Dataset })
    if ($Matches.Count -ne 1) {
        Write-Failure "Dataset is not uniquely present in catalog.json."
    }
    $Match = $Matches[0]
    $Entry = $Match.Entry
    [Console]::Out.WriteLine("ok=true")
    [Console]::Out.WriteLine("section=$($Match.Section)")
    [Console]::Out.WriteLine("dataset=$($Entry.name)")
    [Console]::Out.WriteLine("label=$($Entry.label)")
    [Console]::Out.WriteLine("record_type=$($Entry.record_type)")
    [Console]::Out.WriteLine("row_count=$($Entry.row_count)")
    [Console]::Out.WriteLine("search_result_complete=$($Entry.search_result_complete.ToString().ToLowerInvariant())")
    [Console]::Out.WriteLine("schema_file=$($Entry.schema_file)")
    [Console]::Out.WriteLine("search_file=$($Entry.search_file)")
    [Console]::Out.WriteLine("rows_file=$($Entry.rows_file)")
    [Console]::Out.WriteLine("canonical_key=$(@($Entry.canonical_key) -join ',')")
    [Console]::Out.WriteLine("search_fields=$(@($Entry.search_fields) -join ',')")
    exit 0
}
catch {
    Write-Failure "Catalog inspection failed."
}
