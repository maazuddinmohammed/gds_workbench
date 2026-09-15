# Local aggregate planning. Loaded by atlas-local.ps1; uses its JSON and snapshot helpers.
$script:ProfileFields = @('tenant_code','system_code','connection_code','object_schema','object_name')
$script:ProfileStringType = '^(?:STRING|VARCHAR(?:\(\d+\))?|CHAR(?:\(\d+\))?)$'
$script:ProfileScalarType = '^(?:BOOLEAN|BYTE|TINYINT|SHORT|SMALLINT|INT|INTEGER|LONG|BIGINT|FLOAT|REAL|DOUBLE|DATE|TIMESTAMP(?:_NTZ|_LTZ)?|DECIMAL\(\d+,\d+\)|NUMERIC\(\d+,\d+\))$'
function Get-ProfileKey($Row, [string]$Prefix = '', $Fields = $script:ProfileFields) {
    $values = @($Fields | ForEach-Object { Normalize-Value 'metadata' 'object_name' (Get-Property $Row ($Prefix + $_)) })
    return ConvertTo-GdsJson $values
}
function Get-ProfileObjectKey($Row) {
    $key = [ordered]@{}
    foreach ($field in $script:ProfileFields) { $key[$field] = Get-Property $Row $field }
    return $key
}
function Get-ProfileMaskingKeys($Metadata) {
    $masked = @{}; $fields = @($script:ProfileFields) + @('attribute_name')
    # A mapped Source mask remains binding even when the Source Attribute is inactive.
    foreach ($row in @((Get-Property $Metadata 'source_attribute')) + @((Get-Property $Metadata 'bronze_attribute'))) {
        if ($null -ne $row -and (Get-Property $row 'is_masking_required') -eq $true) { $masked[(Get-ProfileKey $row '' $fields)] = 'masking_required' }
    }
    foreach ($mapping in @((Get-Property $Metadata 'ingestion_attribute_mapping'))) {
        if ($null -ne $mapping -and (Get-Active $mapping) -ne $false -and $masked.ContainsKey((Get-ProfileKey $mapping 'source_' $fields))) {
            $masked[(Get-ProfileKey $mapping 'target_' $fields)] = 'masking_required'
        }
    }
    # Advisory mappings cannot prove that custom expressions excluded protected input.
    $protectedObjects = @{}
    foreach ($attribute in @((Get-Property $Metadata 'source_attribute'))) {
        if ($null -ne $attribute -and (Get-Property $attribute 'is_masking_required') -eq $true) { $protectedObjects[(Get-ProfileKey $attribute)] = $true }
    }
    foreach ($object in @((Get-Property $Metadata 'bronze_object'))) {
        if ($null -eq $object) { continue }
        $objectKey = Get-ProfileKey $object
        $origins = @((Get-Property $Metadata 'ingestion_object_mapping') | Where-Object { $null -ne $_ -and (Get-ProfileKey $_ 'target_') -ceq $objectKey })
        $uncertain = @($origins | Where-Object { $protectedObjects.ContainsKey((Get-ProfileKey $_ 'source_')) }).Count -gt 0
        if (-not $origins.Count) {
            $uncertain = @((Get-Property $Metadata 'source_object') | Where-Object { $null -ne $_ -and
                (Normalize-Value 'metadata' 'tenant_code' $_.source_tenant_code) -ceq (Normalize-Value 'metadata' 'tenant_code' $object.source_tenant_code) -and
                $protectedObjects.ContainsKey((Get-ProfileKey $_)) }).Count -gt 0
        }
        if ($uncertain) {
            foreach ($attribute in @((Get-Property $Metadata 'bronze_attribute'))) {
                if ($null -eq $attribute -or (Get-ProfileKey $attribute) -cne $objectKey) { continue }
                $identity = Get-ProfileKey $attribute '' $fields
                if (-not $masked.ContainsKey($identity)) { $masked[$identity] = 'unproven_masking_lineage' }
            }
        }
    }
    return $masked
}
function Quote-ProfileName($Value) {
    if ($Value -isnot [string] -or [string]::IsNullOrWhiteSpace($Value) -or $Value.Contains([string][char]0)) { Fail 'Missing SQL coordinate.' }
    return '`' + $Value.Replace('`','``') + '`'
}
function Get-ProfileBatchValues($Value) {
    if ($Value -isnot [Array] -or $Value.Count -lt 1 -or $Value.Count -gt 2000) {
        Fail 'Batch IDs must be a nonempty list of nonblank strings.'
    }
    $seen = New-Object 'System.Collections.Generic.HashSet[string]' ([StringComparer]::Ordinal)
    $items = New-Object 'System.Collections.Generic.List[string]'
    foreach ($item in $Value) {
        if ($item -isnot [string] -or [string]::IsNullOrWhiteSpace($item) -or $item.Length -gt 4000 -or $item.Contains([string][char]0)) {
            Fail 'Batch IDs must be a nonempty list of nonblank strings.'
        }
        if ($seen.Add($item)) { $items.Add($item) }
    }
    $values = $items.ToArray()
    [Array]::Sort($values, [StringComparer]::Ordinal)
    return ,$values
}
function Get-ProfileBatchPredicate($Batch) {
    if ($null -eq $Batch) { return '' }
    Assert-ProfileBatchType $Batch.values $Batch.type
    $literals = @(foreach ($value in $Batch.values) {
        $hex = ([BitConverter]::ToString([Text.Encoding]::UTF8.GetBytes($value))).Replace('-','').ToLowerInvariant()
        "CAST(CAST(X'$hex' AS STRING) AS " + $Batch.type + ')'
    })
    return ' WHERE ' + (Quote-ProfileName $Batch.name) + ' IN (' + ($literals -join ', ') + ')'
}
function Assert-ProfileBatchType($Values, [string]$Type) {
    $bounds = @{BYTE=@('-128','127');TINYINT=@('-128','127');SHORT=@('-32768','32767');SMALLINT=@('-32768','32767');
        INT=@('-2147483648','2147483647');INTEGER=@('-2147483648','2147483647');
        LONG=@('-9223372036854775808','9223372036854775807');BIGINT=@('-9223372036854775808','9223372036854775807')}
    $culture = [Globalization.CultureInfo]::InvariantCulture
    $decimalType = [regex]::Match($Type, '^(?:DECIMAL|NUMERIC)\(([0-9]+),([0-9]+)\)$')
    $width = [regex]::Match($Type, '^(?:CHAR|VARCHAR)\(([0-9]+)\)$')
    foreach ($value in (Get-ProfileBatchValues $Values)) {
        $valid = $false
        if ($Type -cmatch $script:ProfileStringType) {
            # Count Unicode code points, matching JavaScript's string iterator.
            $length = [regex]::Matches($value, '[\uD800-\uDBFF][\uDC00-\uDFFF]|[^\uD800-\uDBFF]').Count
            $valid = -not $width.Success -or ([double]$width.Groups[1].Value -gt 0 -and $length -le [double]$width.Groups[1].Value)
        }
        elseif ($bounds.ContainsKey($Type)) {
            $integer = [decimal]0
            $valid = $value -cmatch '^[+-]?[0-9]+$' -and [decimal]::TryParse($value, [Globalization.NumberStyles]::AllowLeadingSign, $culture, [ref]$integer) -and
                $integer -ge [decimal]::Parse($bounds[$Type][0], $culture) -and $integer -le [decimal]::Parse($bounds[$Type][1], $culture)
        }
        elseif ($decimalType.Success) {
            $precision = [double]$decimalType.Groups[1].Value; $scale = [double]$decimalType.Groups[2].Value
            $number = [regex]::Match($value, '^[+-]?([0-9]+)(?:\.([0-9]+))?$')
            $valid = $precision -ge 1 -and $precision -le 38 -and $scale -le $precision -and $number.Success -and
                $number.Groups[1].Value.TrimStart('0').Length -le ($precision - $scale) -and $number.Groups[2].Value.TrimEnd('0').Length -le $scale
        }
        elseif ($Type -ceq 'BOOLEAN') { $valid = $value -match '^(?:true|false)$' }
        elseif ($Type -ceq 'DATE') {
            $date = [DateTime]::MinValue
            $valid = [DateTime]::TryParseExact($value, 'yyyy-MM-dd', $culture, [Globalization.DateTimeStyles]::None, [ref]$date)
        }
        elseif ($Type -cmatch '^TIMESTAMP(?:_NTZ|_LTZ)?$') {
            $timestamp = [regex]::Match($value, '^([0-9]{4}-[0-9]{2}-[0-9]{2})[ T]([0-9]{2}):([0-9]{2}):([0-9]{2})(?:\.([0-9]{1,6}))?(Z|[+-][0-9]{2}:[0-9]{2})?$')
            if ($timestamp.Success) {
                $date = [DateTime]::MinValue; $offset = $timestamp.Groups[6].Value
                $zoneValid = if ($Type -ceq 'TIMESTAMP_NTZ') { -not $offset } else { [bool]$offset }
                if ($offset -and $offset -cne 'Z') {
                    $hours = [int]$offset.Substring(1,2); $minutes = [int]$offset.Substring(4,2)
                    $zoneValid = $zoneValid -and $hours -le 18 -and $minutes -lt 60 -and ($hours -lt 18 -or $minutes -eq 0)
                }
                $valid = [DateTime]::TryParseExact($timestamp.Groups[1].Value, 'yyyy-MM-dd', $culture, [Globalization.DateTimeStyles]::None, [ref]$date) -and
                    [int]$timestamp.Groups[2].Value -lt 24 -and [int]$timestamp.Groups[3].Value -lt 60 -and [int]$timestamp.Groups[4].Value -lt 60 -and $zoneValid
            }
        }
        if (-not $valid) { Fail 'Batch ID cannot be converted exactly to its registered physical type.' }
    }
}
function Get-ProfilePercentage([string]$Numerator, [string]$Denominator) {
    return 'CAST(CASE WHEN ' + $Denominator + ' = 0 THEN 0.0 ELSE ROUND(CAST(100 AS DOUBLE) * (' + $Numerator + ') / ' + $Denominator + ', 4) END AS DOUBLE)'
}
function Build-ProfileQuery([string]$Relation, $Attributes, $Batch) {
    $aggregates = New-Object 'System.Collections.Generic.List[string]'
    $aggregates.Add('       COUNT(*) AS row_count')
    $projections = New-Object 'System.Collections.Generic.List[string]'
    $index = 0
    foreach ($attribute in $Attributes) {
        $identifier = Quote-ProfileName $attribute.name
        $type = ([string]$attribute.data_type).ToUpperInvariant() -replace '\s+', ''
        $string = $type -cmatch $script:ProfileStringType
        $distinct = $string -or $type -cmatch $script:ProfileScalarType
        $prefix = 'p' + $index; $nonNull = $prefix + '_non_null_count'; $nullCount = '(row_count - ' + $nonNull + ')'
        $distinctValue = $prefix + '_distinct_count'; $blankValue = $prefix + '_blank_count'
        $aggregates.Add("       COUNT($identifier) AS $nonNull")
        if ($distinct) { $aggregates.Add("       COUNT(DISTINCT $identifier) AS $distinctValue") }
        if ($string) {
            $aggregates.Add("       CAST(COALESCE(SUM(CASE WHEN $identifier IS NOT NULL AND TRIM($identifier) = '' THEN 1 ELSE 0 END), 0) AS BIGINT) AS $blankValue")
            $aggregates.Add("       MIN(LENGTH($identifier)) AS ${prefix}_min_data_length")
            $aggregates.Add("       MAX(LENGTH($identifier)) AS ${prefix}_max_data_length")
            $aggregates.Add("       AVG(CAST(LENGTH($identifier) AS DOUBLE)) AS ${prefix}_avg_data_length")
        }
        $blank = if ($string) { $blankValue } else { 'NULL' }
        $unique = if ($distinct) { $distinctValue } else { 'NULL' }
        $min = if ($string) { $prefix + '_min_data_length' } else { 'NULL' }
        $max = if ($string) { $prefix + '_max_data_length' } else { 'NULL' }
        $avg = if ($string) { 'ROUND(' + $prefix + '_avg_data_length, 6)' } else { 'NULL' }
        $duplicates = if ($distinct) { Get-ProfilePercentage "($nonNull - $distinctValue)" $nonNull } else { 'CAST(NULL AS DOUBLE)' }
        $percentBlank = if ($string) { Get-ProfilePercentage $blankValue $nonNull } else { 'CAST(NULL AS DOUBLE)' }
        $percentDistinct = if ($distinct) { Get-ProfilePercentage $distinctValue $nonNull } else { 'CAST(NULL AS DOUBLE)' }
        $values = @(
            "CAST($($attribute.index) AS BIGINT) AS attribute_index", 'CAST(row_count AS BIGINT) AS row_count',
            "CAST($nonNull AS BIGINT) AS non_null_count", "CAST($nullCount AS BIGINT) AS null_count",
            "CAST($blank AS BIGINT) AS blank_count", "CAST($unique AS BIGINT) AS distinct_count",
            "CAST($min AS INT) AS min_data_length", "CAST($max AS INT) AS max_data_length", "CAST($avg AS DOUBLE) AS avg_data_length",
            ((Get-ProfilePercentage $nonNull 'row_count') + ' AS percent_populated'), ($duplicates + ' AS percent_duplicates'),
            ((Get-ProfilePercentage $nullCount 'row_count') + ' AS percent_null'), ($percentBlank + ' AS percent_blank'), ($percentDistinct + ' AS percent_distinct')
        )
        $projections.Add("SELECT`n" + (($values | ForEach-Object { '       ' + $_ }) -join ",`n") + "`n  FROM summary")
        $index++
    }
    $predicate = ''
    if ($null -ne $Batch) { $predicate = "`n" + (Get-ProfileBatchPredicate $Batch).TrimStart() }
    $names = @($Attributes | ForEach-Object { '       ' + (Quote-ProfileName $_.name) })
    return "WITH scoped AS (`nSELECT`n" + ($names -join ",`n") + "`n  FROM " + $Relation + $predicate + "`n),`nsummary AS (`nSELECT`n" + ($aggregates -join ",`n") + "`n  FROM scoped`n)`n" + ($projections -join "`nUNION ALL`n")
}
function Plan-Profiling($Metadata, $Scope, $Plan) {
    if ($null -eq $Plan -or $Plan -is [Array] -or
        @((Get-PropertyNames $Plan) | Where-Object { @('systems','objects','selected_objects') -cnotcontains $_ }).Count) { Fail 'Profiling plan accepts systems, objects and selected_objects only.' }
    $assignments = @{}
    foreach ($level in @('systems','objects')) {
        $rows = Get-Property $Plan $level
        if ($null -eq $rows) { $rows = @() }
        if ($rows -isnot [Array] -or $rows.Count -gt 2000) { Fail 'Invalid batch assignments.' }
        $names = if ($level -ceq 'objects') { $script:ProfileFields } elseif ($level -ceq 'systems') { @('source_tenant_code','system_code') } else { @('source_tenant_code') }
        $assignments[$level] = @{}
        foreach ($row in $rows) {
            if ($null -eq $row -or @((Get-PropertyNames $row) | Where-Object { (@($names) + @('batch_ids')) -cnotcontains $_ }).Count -or -not (Test-Property $row 'batch_ids')) { Fail 'Invalid batch assignment key.' }
            foreach ($name in $names) { if ((Get-Property $row $name) -isnot [string] -or [string]::IsNullOrWhiteSpace((Get-Property $row $name))) { Fail 'Invalid batch assignment key.' } }
            $identity = Get-ProfileKey $row '' $names
            if ($assignments[$level].ContainsKey($identity)) { Fail 'Duplicate/conflicting batch assignment.' }
            $assignments[$level][$identity] = Get-ProfileBatchValues $row.batch_ids
        }
    }
    $objects = @{}
    foreach ($row in @((Get-Property $Metadata 'source_object')) + @((Get-Property $Metadata 'bronze_object'))) { if ($null -ne $row -and ((Get-Active $row) -ne $false)) { $objects[(Get-ProfileKey $row)] = $row } }
    $knownSystems = @{}
    foreach ($row in $objects.Values) {
        if ((Normalize-Value 'metadata' 'zone_code' $row.zone_code) -ceq 'source') {
            $knownSystems[(Get-ProfileKey $row '' @('source_tenant_code','system_code'))] = $true
        }
    }
    foreach ($level in @('systems','objects')) {
        $known = if ($level -ceq 'systems') { $knownSystems } else { $objects }
        foreach ($identity in $assignments[$level].Keys) { if (-not $known.ContainsKey($identity)) { Fail 'Unknown batch assignment; use registered Source Tenant, System, and Object keys.' } }
    }
    $attributes = @(@((Get-Property $Metadata 'source_attribute')) + @((Get-Property $Metadata 'bronze_attribute')) | Where-Object { $null -ne $_ -and ((Get-Active $_) -ne $false) })
    $selectedKeys = $null
    if (Test-Property $Plan 'selected_objects') {
        if ($Plan.selected_objects -isnot [Array] -or $Plan.selected_objects.Count -eq 0) { Fail 'selected_objects must be a nonempty list.' }
        $selectedKeys = @{}
        foreach ($row in $Plan.selected_objects) {
            if (@(Get-PropertyNames $row).Count -ne 5) { Fail 'Invalid selected Object key.' }
            foreach ($name in $script:ProfileFields) { if ((Get-Property $row $name) -isnot [string] -or [string]::IsNullOrWhiteSpace((Get-Property $row $name))) { Fail 'Invalid selected Object key.' } }
            $identity = Get-ProfileKey $row
            if ($selectedKeys.ContainsKey($identity)) { Fail 'Duplicate selected Object.' }
            $selectedKeys[$identity] = $true
        }
    }
    $scoped = @($Scope | Where-Object { ((Get-Active $_) -ne $false) -and ($null -eq $selectedKeys -or $selectedKeys.ContainsKey((Get-ProfileKey $_))) })
    $scopeRows = @{}; $scopeOrder = [string[]]@($scoped | ForEach-Object { $identity = Get-ProfileKey $_; $scopeRows[$identity] = $_; $identity })
    [Array]::Sort($scopeOrder, [StringComparer]::Ordinal)
    $scoped = @($scopeOrder | ForEach-Object { $scopeRows[$_] })
    if ($scoped.Count -eq 0 -or $scoped.Count -gt 2000 -or ($null -ne $selectedKeys -and $selectedKeys.Count -ne $scoped.Count)) { Fail 'Selection must match active Model Input Scope.' }
    $queries = New-Object System.Collections.ArrayList
    $coverage = New-Object System.Collections.ArrayList
    $masked = Get-ProfileMaskingKeys $Metadata
    $attributeFields = @($script:ProfileFields) + @('attribute_name')
    foreach ($scopedObject in $scoped) {
        $objectKey = Get-ProfileKey $scopedObject; $object = $objects[$objectKey]
        if ($null -eq $object) { Fail 'Scoped Object is absent from authorized Source/Bronze Metadata.' }
        $source = (Normalize-Value 'metadata' 'zone_code' $object.zone_code) -ceq 'source'
        $connection = @((Get-Property $Metadata 'connection') | Where-Object { ((Get-Active $_) -ne $false) -and (Get-ProfileKey $_ '' @('tenant_code','system_code','connection_code')) -ceq (Get-ProfileKey $object '' @('tenant_code','system_code','connection_code')) }) | Select-Object -First 1
        $tenant = @((Get-Property $Metadata 'tenant') | Where-Object { ((Get-Active $_) -ne $false) -and (Get-ProfileKey $_ '' @('tenant_code')) -ceq (Get-ProfileKey $object '' @('tenant_code')) }) | Select-Object -First 1
        if ($null -eq $connection -or $null -eq $tenant) { Fail 'Object placement is not active in Metadata.' }
        $catalogOwners = @((Get-Property $Metadata 'tenant') | Where-Object { ((Get-Active $_) -ne $false) -and
            (Normalize-Value 'metadata' 'tenant_code' $_.tenant_code) -ceq (Normalize-Value 'metadata' 'tenant_code' (Get-Property $object 'source_tenant_code')) })
        if (-not $source -and $catalogOwners.Count -ne 1) { Fail 'Object catalog owner is not uniquely active in Metadata.' }
        $coords = if ($source) { @($connection.foreign_catalog,$object.fc_object_schema,$object.fc_object_name) } else { @($catalogOwners[0].tenant_catalog,$object.object_schema,$object.object_name) }
        $relation = (@($coords | ForEach-Object { Quote-ProfileName $_ }) -join '.')
        $allMembers = @($attributes | Where-Object { (Get-ProfileKey $_) -ceq $objectKey } | Sort-Object { [int](Get-Property $_ 'attribute_ordinal_position') }, { [string](Get-Property $_ 'attribute_name') })
        if ($allMembers.Count -eq 0 -or $allMembers.Count -gt 2000) { Fail 'Object requires 1-2000 active Attributes.' }
        $members = @($allMembers | Where-Object { -not $masked.ContainsKey((Get-ProfileKey $_ '' $attributeFields)) })
        $excluded = @(foreach ($row in $allMembers) {
            if ($masked.ContainsKey((Get-ProfileKey $row '' $attributeFields))) {
                $entry = Get-ProfileObjectKey $object; $entry['attribute_name'] = $row.attribute_name; $entry['reason'] = $masked[(Get-ProfileKey $row '' $attributeFields)]; $entry
            }
        })
        [void]$coverage.Add([ordered]@{object=(Get-ProfileObjectKey $object);active_attribute_count=$allMembers.Count;planned_attribute_count=$members.Count;excluded=$excluded})
        if ($members.Count -eq 0) { continue }
        $origins = @()
        if ($source) { $origins = @($object) } else {
            foreach ($mapping in @((Get-Property $Metadata 'ingestion_object_mapping'))) {
                if ($null -eq $mapping -or (Get-Active $mapping) -eq $false -or (Get-ProfileKey $mapping 'target_') -cne $objectKey) { continue }
                $origin = $objects[(Get-ProfileKey $mapping 'source_')]
                if ($null -ne $origin -and (Normalize-Value 'metadata' 'tenant_code' $origin.source_tenant_code) -ceq (Normalize-Value 'metadata' 'tenant_code' $object.source_tenant_code)) { $origins += $origin }
            }
        }
        $originSystems = @($origins | ForEach-Object { Normalize-Value 'metadata' 'system_code' $_.system_code } | Select-Object -Unique)
        $batch = $null
        $matched = @($originSystems | ForEach-Object { Get-ProfileKey @{source_tenant_code=$object.source_tenant_code;system_code=$_} '' @('source_tenant_code','system_code') } | Where-Object { $assignments.systems.ContainsKey($_) })
        if ($object.batch_attribute_name -and -not $assignments.objects.ContainsKey($objectKey) -and $matched.Count -and ($originSystems.Count -ne 1 -or $matched.Count -ne 1)) { Fail 'Ambiguous originating System batch; resolve Object assignment explicitly.' }
        if ($matched.Count) { $batch = $assignments.systems[$matched[0]] }
        if ($object.batch_attribute_name -and -not $origins.Count -and $assignments.systems.Count -and -not $assignments.objects.ContainsKey($objectKey)) { Fail 'Resolve Bronze originating System through ingestion Mapping.' }
        if ($assignments.objects.ContainsKey($objectKey)) { $batch = $assignments.objects[$objectKey] }
        $filter = $null
        if ($object.batch_attribute_name) {
            if ($null -eq $batch) { Fail 'Batch IDs are required for every batched Object.' }
            $batchAttribute = @($allMembers | Where-Object { (Normalize-Value 'metadata' 'attribute_name' $_.attribute_name) -ceq (Normalize-Value 'metadata' 'attribute_name' $object.batch_attribute_name) }) | Select-Object -First 1
            if ($null -eq $batchAttribute) { Fail 'Registered batch column is not an active Attribute.' }
            if ($masked.ContainsKey((Get-ProfileKey $batchAttribute '' $attributeFields))) { Fail 'Masked batch Attribute cannot be used for Profiling.' }
            $type = $batchAttribute.attribute_data_type.ToUpperInvariant() -replace '\s+', ''
            if ($type -cnotmatch $script:ProfileStringType -and $type -cnotmatch $script:ProfileScalarType) { Fail 'Unsupported batch data type.' }
            $filter = @{name=$(if ($source) { $batchAttribute.fc_attribute_name } else { $batchAttribute.attribute_name });type=$type;values=$batch}
        }
        $projected = New-Object System.Collections.ArrayList; $namesSeen = @{}
        foreach ($row in $members) {
            $name = if ($source) { $row.fc_attribute_name } else { $row.attribute_name }
            $normalized = Normalize-Value 'metadata' 'attribute_name' $name
            if ($null -eq $normalized -or $namesSeen.ContainsKey($normalized)) { Fail 'Attribute SQL coordinates are ambiguous.' }
            $namesSeen[$normalized] = $true
            $key = Get-ProfileObjectKey $object; $key['attribute_name'] = $row.attribute_name
            [void]$projected.Add(@{index=($projected.Count+1);name=$name;data_type=$row.attribute_data_type;key=$key})
        }
        for ($offset=0; $offset -lt $projected.Count;) {
            $count = [Math]::Min(50,$projected.Count-$offset)
            do {
                $chunk = @($projected.GetRange($offset,$count)); $sql = Build-ProfileQuery $relation $chunk $filter
                if ($sql.Length -le 100000) { break }; $count--
            } while ($count -gt 0)
            if ($count -eq 0) { Fail 'Profiling query exceeds SQL limit.' }
            $keys = @($chunk | ForEach-Object { $key=Get-ProfileObjectKey $_.key; $key['attribute_name']=$_.key.attribute_name; $key['attribute_index']=$_.index; $key })
            [void]$queries.Add([ordered]@{object=(Get-ProfileObjectKey $object);source_tenant_code=$object.source_tenant_code;source_system_codes=$originSystems;batch_ids=$(if ($null -ne $filter) { ,$batch } else { $null });batch=$filter;relation=$relation;attributes=$keys;sql=$sql})
            $offset += $count
        }
    }
    return [ordered]@{queries=@($queries);coverage=@($coverage)}
}
function New-AggregatePlan([hashtable]$Options, [string]$Kind) {
    $modelOptions = @{} + $Options; $modelOptions['area'] = 'model'
    $context = Get-ChangeContext $modelOptions
    $supplied = Read-Json (Require-Option $Options 'plan-file') 'SQL planning input'
    $selections = Get-Property $supplied 'selections'
    $executionConnections = Get-Property $supplied 'execution_connections'
    if (-not (Test-AtlasObject $selections) -or $executionConnections -isnot [Array] -or -not $executionConnections.Count) { Fail 'Plan requires selections and verified execution_connections.' }
    $environment = Get-Property (Get-Property $context.State 'sql') 'environment'
    if (-not $environment -and (Get-Property (Get-Property $context.State 'sql') 'policy') -ceq 'never') { $environment = 'dev' }
    if (-not $environment) { Fail 'Resolve SQL policy/environment before preparing evidence queries.' }
    if (-not $context.ByName.ContainsKey('model_input_scope')) { Fail 'Model Input Scope is missing.' }
    $inputs = New-Object Collections.ArrayList
    [void]$inputs.Add((Get-SnapshotBinding $context))
    $owners = [ordered]@{}; $owners[[string]$context.State.tenant.id] = Get-AtlasOwner $context.State 'metadata'
    foreach ($id in @(Get-PropertyNames (Get-Property $context.State 'metadata_owners'))) { $owners[$id] = Get-AtlasOwner $context.State 'metadata' $id }
    $merged = @{}
    foreach ($owner in $owners.Values) {
        foreach ($marker in @(Get-Property $context.State 'refresh_required')) {
            if ($null -ne $marker -and $marker.area -ceq 'metadata' -and $marker.owner_tenant_id -eq $owner.id) { Fail 'Model work needs refreshed Metadata inputs.' }
        }
        try { $snapshot = Find-Snapshot @{session=$context.Session;area='metadata';owner=[string]$owner.id} }
        catch { if ($_.Exception.GetBaseException() -is [IO.FileNotFoundException]) { Fail 'Install every registered owner Metadata Snapshot before planning SQL.' }; throw }
        [void]$inputs.Add((Get-SnapshotBinding $snapshot))
        foreach ($dataset in @($snapshot.Datasets)) {
            $name = [string]$dataset.name
            if (-not $merged.ContainsKey($name)) { $merged[$name] = [ordered]@{} }
            foreach ($record in @(Read-SnapshotRecords $snapshot $dataset)) {
                $identity = Get-CanonicalKey 'metadata' $dataset $record
                if ($merged[$name].Contains($identity) -and (ConvertTo-StableJson $merged[$name][$identity]) -cne (ConvertTo-StableJson $record)) { Fail 'Owner Snapshots disagree on a shared record; refresh before proceeding.' }
                $merged[$name][$identity] = $record
            }
        }
    }
    $datasets = @{}
    foreach ($name in $merged.Keys) { $datasets[$name] = @($merged[$name].Values) }
    $scope = @(Read-SnapshotRecords $context $context.ByName['model_input_scope'])
    $planned = if ($Kind -ceq 'analysis') { @(Plan-Analysis $datasets $scope $selections) } else { Plan-Profiling $datasets $scope $selections }
    $queries = if ($Kind -ceq 'analysis') { @($planned) } else { $planned.queries }
    $relative = '.atlas/temp/' + $context.TaskId + '/' + $Kind + '/' + [Guid]::NewGuid().ToString()
    $directory = Split-Path -Parent (Resolve-WorkspacePath $context.Session ($relative + '/.check') $true)
    $entries = New-Object Collections.ArrayList
    foreach ($query in $queries) {
        $endpoints = if (Test-Property $query 'endpoints') { @($query.endpoints) } else { @($query) }
        $sourceTenants = @($endpoints | ForEach-Object { $_.source_tenant_code } | Select-Object -Unique)
        $choices = @(foreach ($connection in $executionConnections) {
            if (-not @($sourceTenants | Where-Object { @($connection.source_tenant_codes) -cnotcontains $_ }).Count) { $connection }
        })
        if ($choices.Count -ne 1 -or ($choices[0].connection_id -isnot [int] -and $choices[0].connection_id -isnot [long]) -or
            $choices[0].connection_id -lt 1 -or $choices[0].connection_id -gt 9007199254740991 -or
            $choices[0].is_global_data_store -isnot [bool] -or $choices[0].is_global_data_store -ne $false) { Fail 'Each query needs one verified non-GDS execution Connection covering its source owners.' }
        $file = '{0:D4}.sql' -f ($entries.Count+1)
        $bytes = [Text.Encoding]::UTF8.GetBytes($query.sql)
        $stream = [IO.File]::Open((Join-Path $directory $file), [IO.FileMode]::CreateNew, [IO.FileAccess]::Write, [IO.FileShare]::None)
        try { $stream.Write($bytes,0,$bytes.Length) } finally { $stream.Dispose() }
        $entry = [ordered]@{}
        foreach ($name in @(Get-PropertyNames $query)) { if ($name -cne 'sql') { $entry[$name] = Get-Property $query $name } }
        $entry['file']=$file; $entry['sha256']=Get-ByteDigest $bytes
        $entry['origin']='atlas-generator'; $entry['generator_version']='1.0'; $entry['environment']=$environment
        $entry['connection_id']=$choices[0].connection_id
        $entry['expected_row_count']=if ($Kind -ceq 'profiling') { $query.attributes.Count } else { 1 }
        [void]$entries.Add($entry)
    }
    $manifest = [ordered]@{schema_version='1.0';kind=$Kind;task=$context.TaskId;inputs=@($inputs);environment=$environment;selections=$selections;queries=@($entries)}
    if ($Kind -ceq 'profiling') { $manifest['coverage'] = $planned.coverage }
    foreach ($inputBinding in $inputs) {
        if ((Get-FileDigest (Resolve-WorkspacePath $context.Session $inputBinding.manifest_path)) -cne $inputBinding.manifest_sha256) { Fail 'Snapshot changed during planning; discard this plan and retry.' }
    }
    $manifestPath = Join-Path $directory 'plan.json'
    Write-JsonAtomic $manifestPath $manifest
    return [ordered]@{directory=$directory;manifest=$manifestPath;query_count=$entries.Count}
}
