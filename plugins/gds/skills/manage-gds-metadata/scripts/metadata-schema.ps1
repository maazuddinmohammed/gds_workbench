function Get-GdsProperty {
    param(
        [object]$Object,
        [string]$Name
    )
    if ($null -eq $Object -or $Object -isnot [PSCustomObject]) {
        return $null
    }
    return $Object.PSObject.Properties[$Name]
}

function Test-GdsScalarEqual {
    param(
        [object]$Left,
        [object]$Right
    )
    if ($null -eq $Left -or $null -eq $Right) {
        return $null -eq $Left -and $null -eq $Right
    }
    if ($Left.GetType() -ne $Right.GetType()) {
        return $false
    }
    return $Left.Equals($Right)
}

function Test-GdsInteger {
    param([object]$Value)
    return (
        $Value -is [byte] -or $Value -is [sbyte] -or
        $Value -is [int16] -or $Value -is [uint16] -or
        $Value -is [int32] -or $Value -is [uint32] -or
        $Value -is [int64] -or $Value -is [uint64]
    )
}

function Test-GdsSchemaValue {
    param(
        [AllowNull()]
        [object]$Value,
        [object]$Rule
    )
    if ($Rule -isnot [PSCustomObject]) {
        return $false
    }
    $AnyOfProperty = Get-GdsProperty $Rule "anyOf"
    if ($null -ne $AnyOfProperty) {
        foreach ($Branch in @($AnyOfProperty.Value)) {
            if (Test-GdsSchemaValue $Value $Branch) {
                return $true
            }
        }
        return $false
    }

    $TypeProperty = Get-GdsProperty $Rule "type"
    if ($null -eq $TypeProperty) {
        return $false
    }
    $ExpectedType = [string]$TypeProperty.Value
    $TypeMatches = switch ($ExpectedType) {
        "null" { $null -eq $Value; break }
        "string" { $Value -is [string]; break }
        "boolean" { $Value -is [bool]; break }
        "integer" { Test-GdsInteger $Value; break }
        "number" { (Test-GdsInteger $Value) -or $Value -is [single] -or $Value -is [double] -or $Value -is [decimal]; break }
        "object" { $Value -is [PSCustomObject]; break }
        default { $false }
    }
    if (-not $TypeMatches) {
        return $false
    }

    if ($Value -is [string]) {
        $MinLength = Get-GdsProperty $Rule "minLength"
        $MaxLength = Get-GdsProperty $Rule "maxLength"
        $Pattern = Get-GdsProperty $Rule "pattern"
        $Format = Get-GdsProperty $Rule "format"
        if ($null -ne $MinLength -and $Value.Length -lt [int]$MinLength.Value) {
            return $false
        }
        if ($null -ne $MaxLength -and $Value.Length -gt [int]$MaxLength.Value) {
            return $false
        }
        if ($null -ne $Pattern -and -not [regex]::IsMatch($Value, [string]$Pattern.Value)) {
            return $false
        }
        if ($null -ne $Format -and [string]$Format.Value -ceq "date") {
            [datetime]$ParsedDate = [datetime]::MinValue
            if (-not [datetime]::TryParseExact(
                $Value,
                "yyyy-MM-dd",
                [Globalization.CultureInfo]::InvariantCulture,
                [Globalization.DateTimeStyles]::None,
                [ref]$ParsedDate
            )) {
                return $false
            }
        }
        if ($null -ne $Format -and [string]$Format.Value -ceq "date-time") {
            if ($Value -cnotmatch '^\d{4}-\d{2}-\d{2}T\d{2}:\d{2}:\d{2}(?:\.\d+)?(?:Z|[+-]\d{2}:\d{2})$') {
                return $false
            }
            [DateTimeOffset]$ParsedDateTime = [DateTimeOffset]::MinValue
            if (-not [DateTimeOffset]::TryParse(
                $Value,
                [Globalization.CultureInfo]::InvariantCulture,
                [Globalization.DateTimeStyles]::None,
                [ref]$ParsedDateTime
            )) {
                return $false
            }
        }
    }

    if ((Test-GdsInteger $Value) -or $Value -is [single] -or $Value -is [double] -or $Value -is [decimal]) {
        $Minimum = Get-GdsProperty $Rule "minimum"
        $Maximum = Get-GdsProperty $Rule "maximum"
        $ExclusiveMinimum = Get-GdsProperty $Rule "exclusiveMinimum"
        $ExclusiveMaximum = Get-GdsProperty $Rule "exclusiveMaximum"
        if ($null -ne $Minimum -and [decimal]$Value -lt [decimal]$Minimum.Value) {
            return $false
        }
        if ($null -ne $Maximum -and [decimal]$Value -gt [decimal]$Maximum.Value) {
            return $false
        }
        if ($null -ne $ExclusiveMinimum -and [decimal]$Value -le [decimal]$ExclusiveMinimum.Value) {
            return $false
        }
        if ($null -ne $ExclusiveMaximum -and [decimal]$Value -ge [decimal]$ExclusiveMaximum.Value) {
            return $false
        }
    }

    $EnumProperty = Get-GdsProperty $Rule "enum"
    if ($null -ne $EnumProperty) {
        $Found = $false
        foreach ($Allowed in @($EnumProperty.Value)) {
            if (Test-GdsScalarEqual $Value $Allowed) {
                $Found = $true
                break
            }
        }
        if (-not $Found) {
            return $false
        }
    }
    $ConstProperty = Get-GdsProperty $Rule "const"
    if ($null -ne $ConstProperty -and -not (Test-GdsScalarEqual $Value $ConstProperty.Value)) {
        return $false
    }
    return $true
}

function Assert-GdsSchema {
    param(
        [object]$Schema,
        [string]$ExpectedDataset
    )
    if (
        $Schema -isnot [PSCustomObject] -or
        [string]$Schema.type -cne "object" -or
        $Schema.additionalProperties -cne $false -or
        $Schema.properties -isnot [PSCustomObject] -or
        $null -eq $Schema.required -or
        [string]$Schema.'x-gds-dataset' -cne $ExpectedDataset -or
        $Schema.'x-gds-change-set-eligible' -cne $true -or
        $null -eq $Schema.'x-gds-canonical-key' -or
        $null -eq $Schema.'x-gds-unique-constraints'
    ) {
        throw "Snapshot dataset schema contract is invalid."
    }
}

function Assert-GdsRecord {
    param(
        [object]$Record,
        [object]$Schema
    )
    if ($Record -isnot [PSCustomObject]) {
        throw "Every dataset item must be a JSON object."
    }
    foreach ($Property in $Record.PSObject.Properties) {
        $NormalizedName = $Property.Name.ToLowerInvariant()
        if ($NormalizedName -ceq "id" -or $NormalizedName.EndsWith("_id")) {
            throw "Database ID fields are forbidden."
        }
        $FieldRule = $Schema.properties.PSObject.Properties[$Property.Name]
        if ($null -eq $FieldRule) {
            throw "Record contains an unknown schema field: $($Property.Name)."
        }
        if (-not (Test-GdsSchemaValue $Property.Value $FieldRule.Value)) {
            throw "Record field does not match the schema: $($Property.Name)."
        }
    }
    foreach ($RequiredField in @($Schema.required)) {
        if ($null -eq $Record.PSObject.Properties[[string]$RequiredField]) {
            throw "Record is missing a required schema field: $RequiredField."
        }
    }
}

function Get-GdsNormalizedKey {
    param(
        [object]$Record,
        [object[]]$Columns
    )
    $Builder = New-Object System.Text.StringBuilder
    foreach ($ColumnValue in $Columns) {
        $Column = [string]$ColumnValue
        $Property = $Record.PSObject.Properties[$Column]
        if ($null -eq $Property) {
            throw "Record is missing a key field: $Column."
        }
        $Value = $Property.Value
        if ($null -eq $Value) {
            [void]$Builder.Append("N;")
        }
        elseif ($Value -is [string]) {
            $Normalized = $Value.Trim().ToLowerInvariant()
            [void]$Builder.Append("S$($Normalized.Length):$Normalized;")
        }
        elseif ($Value -is [bool]) {
            [void]$Builder.Append($(if ($Value) { "B1;" } else { "B0;" }))
        }
        elseif (Test-GdsInteger $Value) {
            [void]$Builder.Append("I$Value;")
        }
        else {
            throw "Key field must be a scalar: $Column."
        }
    }
    return $Builder.ToString()
}

function Assert-GdsDataset {
    param(
        [object[]]$Records,
        [object]$Schema
    )
    if ($Records.Count -gt 50000) {
        throw "Dataset file exceeds 50000 records."
    }
    foreach ($Record in $Records) {
        Assert-GdsRecord $Record $Schema
    }
    foreach ($ConstraintValue in @($Schema.'x-gds-unique-constraints')) {
        $Columns = @($ConstraintValue)
        if ($Columns.Count -eq 0) {
            throw "Snapshot unique constraint is invalid."
        }
        $Seen = New-Object 'System.Collections.Generic.HashSet[string]'
        foreach ($Record in $Records) {
            $Key = Get-GdsNormalizedKey $Record $Columns
            if (-not $Seen.Add($Key)) {
                throw "Dataset contains a duplicate unique constraint."
            }
        }
    }
}

function Merge-GdsRecord {
    param(
        [object[]]$Records,
        [object]$Record,
        [object]$Schema
    )
    Assert-GdsRecord $Record $Schema
    Assert-GdsDataset $Records $Schema
    $CanonicalColumns = @($Schema.'x-gds-canonical-key')
    $WantedKey = Get-GdsNormalizedKey $Record $CanonicalColumns
    $MatchedIndex = -1
    for ($Index = 0; $Index -lt $Records.Count; $Index += 1) {
        if ((Get-GdsNormalizedKey $Records[$Index] $CanonicalColumns) -ceq $WantedKey) {
            if ($MatchedIndex -ne -1) {
                throw "Dataset contains duplicate canonical keys."
            }
            $MatchedIndex = $Index
        }
    }
    $Action = "inserted"
    $Merged = @($Records)
    if ($MatchedIndex -eq -1) {
        $Merged += $Record
    }
    else {
        $Merged[$MatchedIndex] = $Record
        $Action = "replaced"
    }
    Assert-GdsDataset $Merged $Schema
    return [PSCustomObject]@{
        Action = $Action
        Records = [object[]]$Merged
    }
}

function Test-GdsRecordsEqual {
    param(
        [object]$Left,
        [object]$Right,
        [object]$Schema
    )
    foreach ($Field in $Schema.properties.PSObject.Properties.Name) {
        $LeftProperty = $Left.PSObject.Properties[$Field]
        $RightProperty = $Right.PSObject.Properties[$Field]
        if (
            $null -eq $LeftProperty -or $null -eq $RightProperty -or
            -not (Test-GdsScalarEqual $LeftProperty.Value $RightProperty.Value)
        ) {
            return $false
        }
    }
    return $true
}

function Get-GdsRecordAction {
    param(
        [object]$Record,
        [AllowNull()]
        [object]$Existing,
        [object]$Schema
    )
    if ($null -eq $Existing) {
        return "insert"
    }
    if (Test-GdsRecordsEqual $Record $Existing $Schema) {
        return "no_change"
    }
    $CurrentActive = $Existing.PSObject.Properties["is_active"]
    $IntendedActive = $Record.PSObject.Properties["is_active"]
    if ($null -ne $CurrentActive -and $null -ne $IntendedActive) {
        if ($CurrentActive.Value -ceq $true -and $IntendedActive.Value -ceq $false) {
            return "deactivate"
        }
        if ($CurrentActive.Value -ceq $false -and $IntendedActive.Value -ceq $true) {
            return "reactivate"
        }
    }
    return "update"
}

function Get-GdsCanonicalKeyObject {
    param(
        [object]$Record,
        [object[]]$Columns
    )
    $Key = [ordered]@{}
    foreach ($ColumnValue in $Columns) {
        $Column = [string]$ColumnValue
        $Property = $Record.PSObject.Properties[$Column]
        if ($null -eq $Property) {
            throw "Record is missing a canonical-key field."
        }
        $Key[$Column] = $Property.Value
    }
    return [PSCustomObject]$Key
}

function Assert-GdsCanonicalKey {
    param(
        [object]$KeyRecord,
        [object]$Schema
    )
    if ($KeyRecord -isnot [PSCustomObject]) {
        throw "Canonical key input must be one JSON object."
    }
    $Columns = @($Schema.'x-gds-canonical-key')
    if (@($KeyRecord.PSObject.Properties.Name).Count -ne $Columns.Count) {
        throw "Canonical key input must contain exactly its schema fields."
    }
    foreach ($ColumnValue in $Columns) {
        $Column = [string]$ColumnValue
        $Property = $KeyRecord.PSObject.Properties[$Column]
        $FieldRule = $Schema.properties.PSObject.Properties[$Column]
        if (
            $null -eq $Property -or $null -eq $FieldRule -or
            -not (Test-GdsSchemaValue $Property.Value $FieldRule.Value)
        ) {
            throw "Canonical key input does not match its schema."
        }
    }
    foreach ($Field in $KeyRecord.PSObject.Properties.Name) {
        if ($Columns -cnotcontains $Field) {
            throw "Canonical key input contains an unknown field."
        }
    }
}

function Remove-GdsRecord {
    param(
        [object[]]$Records,
        [object]$KeyRecord,
        [object]$Schema
    )
    Assert-GdsDataset $Records $Schema
    Assert-GdsCanonicalKey $KeyRecord $Schema
    $Columns = @($Schema.'x-gds-canonical-key')
    $WantedKey = Get-GdsNormalizedKey $KeyRecord $Columns
    $Found = $false
    $Remaining = @()
    foreach ($Record in $Records) {
        if ((Get-GdsNormalizedKey $Record $Columns) -ceq $WantedKey) {
            if ($Found) {
                throw "Dataset contains duplicate canonical keys."
            }
            $Found = $true
        }
        else {
            $Remaining += $Record
        }
    }
    if (-not $Found) {
        return [PSCustomObject]@{
            Action = "not_found"
            Records = [object[]]$Records
        }
    }
    Assert-GdsDataset $Remaining $Schema
    return [PSCustomObject]@{
        Action = "removed"
        Records = [object[]]$Remaining
    }
}
