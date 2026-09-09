# Local aggregate planning. Loaded by gds-local.ps1; uses its JSON and snapshot helpers.
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
function Quote-ProfileName($Value) {
    if ($Value -isnot [string] -or [string]::IsNullOrWhiteSpace($Value) -or $Value.Contains([string][char]0)) { Fail 'Missing SQL coordinate.' }
    return '`' + $Value.Replace('`','``') + '`'
}
function Assert-ProfileBatch($Value) {
    if ($null -ne $Value -and ($Value -isnot [string] -or [string]::IsNullOrWhiteSpace($Value) -or $Value.Length -gt 4000 -or $Value.Contains([string][char]0))) {
        Fail 'Batch IDs must be nonblank strings or null for all rows.'
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
    if ($null -ne $Batch) {
        $hex = ([BitConverter]::ToString([Text.Encoding]::UTF8.GetBytes($Batch.value))).Replace('-','').ToLowerInvariant()
        $predicate = "`n WHERE " + (Quote-ProfileName $Batch.name) + " = CAST(CAST(X'$hex' AS STRING) AS " + $Batch.type + ')'
    }
    $names = @($Attributes | ForEach-Object { '       ' + (Quote-ProfileName $_.name) })
    return "WITH scoped AS (`nSELECT`n" + ($names -join ",`n") + "`n  FROM " + $Relation + $predicate + "`n),`nsummary AS (`nSELECT`n" + ($aggregates -join ",`n") + "`n  FROM scoped`n)`n" + ($projections -join "`nUNION ALL`n")
}
function Plan-Profiling($Metadata, $Scope, $Plan) {
    if ($null -eq $Plan -or $Plan -is [Array] -or -not (Test-Property $Plan 'default_batch_id') -or
        @((Get-PropertyNames $Plan) | Where-Object { @('default_batch_id','tenants','systems','objects','selected_objects') -cnotcontains $_ }).Count) { Fail 'Profiling plan requires default_batch_id and only documented fields.' }
    Assert-ProfileBatch $Plan.default_batch_id
    $assignments = @{}
    foreach ($level in @('tenants','systems','objects')) {
        $rows = Get-Property $Plan $level
        if ($null -eq $rows) { $rows = @() }
        if ($rows -isnot [Array] -or $rows.Count -gt 2000) { Fail 'Invalid batch assignments.' }
        $names = if ($level -ceq 'objects') { $script:ProfileFields } elseif ($level -ceq 'systems') { @('source_tenant_code','system_code') } else { @('source_tenant_code') }
        $assignments[$level] = @{}
        foreach ($row in $rows) {
            if ($null -eq $row -or @((Get-PropertyNames $row) | Where-Object { (@($names) + @('batch_id')) -cnotcontains $_ }).Count -or -not (Test-Property $row 'batch_id')) { Fail 'Invalid batch assignment key.' }
            foreach ($name in $names) { if ((Get-Property $row $name) -isnot [string] -or [string]::IsNullOrWhiteSpace((Get-Property $row $name))) { Fail 'Invalid batch assignment key.' } }
            $identity = Get-ProfileKey $row '' $names
            if ($assignments[$level].ContainsKey($identity)) { Fail 'Duplicate/conflicting batch assignment.' }
            Assert-ProfileBatch $row.batch_id
            $assignments[$level][$identity] = $row.batch_id
        }
    }
    $objects = @{}
    foreach ($row in @($Metadata.source_object) + @($Metadata.bronze_object)) { if ($null -ne $row -and (Get-Active $row)) { $objects[(Get-ProfileKey $row)] = $row } }
    $knownTenants = @{}; $knownSystems = @{}
    foreach ($row in $objects.Values) {
        $knownTenants[(Get-ProfileKey $row '' @('source_tenant_code'))] = $true
        if ((Normalize-Value 'metadata' 'zone_code' $row.zone_code) -ceq 'source') {
            $knownSystems[(Get-ProfileKey $row '' @('source_tenant_code','system_code'))] = $true
        }
    }
    foreach ($level in @('tenants','systems','objects')) {
        $known = if ($level -ceq 'tenants') { $knownTenants } elseif ($level -ceq 'systems') { $knownSystems } else { $objects }
        foreach ($identity in $assignments[$level].Keys) { if (-not $known.ContainsKey($identity)) { Fail 'Unknown batch assignment; use registered Source Tenant, System, and Object keys.' } }
    }
    $attributes = @(@($Metadata.source_attribute) + @($Metadata.bronze_attribute) | Where-Object { $null -ne $_ -and (Get-Active $_) })
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
    $scoped = @($Scope | Where-Object { (Get-Active $_) -and ($null -eq $selectedKeys -or $selectedKeys.ContainsKey((Get-ProfileKey $_))) })
    if ($scoped.Count -eq 0 -or $scoped.Count -gt 2000 -or ($null -ne $selectedKeys -and $selectedKeys.Count -ne $scoped.Count)) { Fail 'Selection must match active Model Input Scope.' }
    $queries = New-Object System.Collections.ArrayList
    foreach ($scopedObject in $scoped) {
        $objectKey = Get-ProfileKey $scopedObject; $object = $objects[$objectKey]
        if ($null -eq $object) { Fail 'Scoped Object is absent from authorized Source/Bronze Metadata.' }
        $source = (Normalize-Value 'metadata' 'zone_code' $object.zone_code) -ceq 'source'
        $connection = @($Metadata.connection | Where-Object { (Get-Active $_) -and (Get-ProfileKey $_ '' @('tenant_code','system_code','connection_code')) -ceq (Get-ProfileKey $object '' @('tenant_code','system_code','connection_code')) }) | Select-Object -First 1
        $tenant = @($Metadata.tenant | Where-Object { (Get-Active $_) -and (Get-ProfileKey $_ '' @('tenant_code')) -ceq (Get-ProfileKey $object '' @('tenant_code')) }) | Select-Object -First 1
        if ($null -eq $connection -or $null -eq $tenant) { Fail 'Object placement is not active in Metadata.' }
        $coords = if ($source) { @($connection.foreign_catalog,$object.fc_object_schema,$object.fc_object_name) } else { @($tenant.tenant_catalog,$object.object_schema,$object.object_name) }
        $relation = (@($coords | ForEach-Object { Quote-ProfileName $_ }) -join '.')
        $members = @($attributes | Where-Object { (Get-ProfileKey $_) -ceq $objectKey } | Sort-Object { [int](Get-Property $_ 'attribute_ordinal_position') }, { [string](Get-Property $_ 'attribute_name') })
        if ($members.Count -eq 0 -or $members.Count -gt 2000) { Fail 'Object requires 1-2000 active Attributes.' }
        $origins = @()
        if ($source) { $origins = @($object) } else {
            foreach ($mapping in @($Metadata.ingestion_object_mapping)) {
                if ($null -eq $mapping -or -not (Get-Active $mapping) -or (Get-ProfileKey $mapping 'target_') -cne $objectKey) { continue }
                $origin = $objects[(Get-ProfileKey $mapping 'source_')]
                if ($null -ne $origin -and (Normalize-Value 'metadata' 'tenant_code' $origin.source_tenant_code) -ceq (Normalize-Value 'metadata' 'tenant_code' $object.source_tenant_code)) { $origins += $origin }
            }
        }
        $originSystems = @($origins | ForEach-Object { Normalize-Value 'metadata' 'system_code' $_.system_code } | Select-Object -Unique)
        $batch = $Plan.default_batch_id
        $tenantKey = Get-ProfileKey $object '' @('source_tenant_code')
        if ($assignments.tenants.ContainsKey($tenantKey)) { $batch = $assignments.tenants[$tenantKey] }
        $matched = @($originSystems | ForEach-Object { Get-ProfileKey @{source_tenant_code=$object.source_tenant_code;system_code=$_} '' @('source_tenant_code','system_code') } | Where-Object { $assignments.systems.ContainsKey($_) })
        if ($object.batch_attribute_name -and -not $assignments.objects.ContainsKey($objectKey) -and $matched.Count -and ($originSystems.Count -ne 1 -or $matched.Count -ne 1)) { Fail 'Ambiguous originating System batch; resolve Object assignment explicitly.' }
        if ($matched.Count) { $batch = $assignments.systems[$matched[0]] }
        if ($object.batch_attribute_name -and -not $origins.Count -and $assignments.systems.Count -and -not $assignments.objects.ContainsKey($objectKey)) { Fail 'Resolve Bronze originating System through ingestion Mapping.' }
        if ($assignments.objects.ContainsKey($objectKey)) { $batch = $assignments.objects[$objectKey] }
        $filter = $null
        if ($null -ne $batch -and $object.batch_attribute_name) {
            $batchAttribute = @($members | Where-Object { (Normalize-Value 'metadata' 'attribute_name' $_.attribute_name) -ceq (Normalize-Value 'metadata' 'attribute_name' $object.batch_attribute_name) }) | Select-Object -First 1
            if ($null -eq $batchAttribute) { Fail 'Registered batch column is not an active Attribute.' }
            $type = $batchAttribute.attribute_data_type.ToUpperInvariant() -replace '\s+', ''
            if ($type -cnotmatch $script:ProfileStringType -and $type -cnotmatch $script:ProfileScalarType) { Fail 'Unsupported batch data type.' }
            $filter = @{name=$(if ($source) { $batchAttribute.fc_attribute_name } else { $batchAttribute.attribute_name });type=$type;value=$batch}
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
            [void]$queries.Add([ordered]@{object=(Get-ProfileObjectKey $object);source_tenant_code=$object.source_tenant_code;source_system_codes=$originSystems;batch_id=$(if ($null -ne $filter) { $batch } else { $null });attributes=$keys;sql=$sql})
            $offset += $count
        }
    }
    return $queries.ToArray()
}
function New-ProfilePlan([hashtable]$Options) {
    $modelOptions = @{} + $Options; $modelOptions['area'] = 'model'
    $context = Get-ChangeContext $modelOptions
    $metadata = Find-Snapshot @{session=$Options.session;area='metadata'}
    if (@(Get-Property $context.State 'stale') -contains 'metadata') { Fail 'Metadata Snapshot is stale.' }
    $plan = Read-Json (Require-Option $Options 'plan-file') 'Profiling selections'
    if (-not $context.ByName.ContainsKey('model_input_scope')) { Fail 'Model Input Scope is missing.' }
    $datasets = @{}
    foreach ($name in @('source_object','bronze_object','source_attribute','bronze_attribute','tenant','connection','ingestion_object_mapping')) {
        $datasets[$name] = if ($metadata.ByName.ContainsKey($name)) { @(Read-SnapshotRecords $metadata $metadata.ByName[$name]) } else { @() }
    }
    $queries = @(Plan-Profiling $datasets @(Read-SnapshotRecords $context $context.ByName['model_input_scope']) $plan)
    $directory = $context.Session
    foreach ($segment in @('working',$context.Current[0])) {
        $directory = Join-Path $directory $segment
        if (-not (Test-Path -LiteralPath $directory)) { [void](New-Item -ItemType Directory -Path $directory -ErrorAction Stop) }
        $directory = Resolve-RegularDirectory $directory 'Profiling output'
    }
    $directory = Join-Path $directory ('profiling-' + [Guid]::NewGuid().ToString('N'))
    [void](New-Item -ItemType Directory -Path $directory -ErrorAction Stop)
    $entries = New-Object System.Collections.ArrayList; $attributeCount = 0
    foreach ($query in $queries) {
        $file = '{0:D4}.sql' -f ($entries.Count+1)
        Write-TextAtomic (Join-Path $directory $file) $query.sql
        $entry = [ordered]@{}
        foreach ($name in @('object','source_tenant_code','source_system_codes','batch_id','attributes')) { $entry[$name] = $query[$name] }
        $entry['file']=$file; $entry['sha256']=Get-ByteDigest ([Text.Encoding]::UTF8.GetBytes($query.sql))
        [void]$entries.Add($entry); $attributeCount += $query.attributes.Count
    }
    $manifest = Join-Path $directory 'plan.json'
    Write-JsonAtomic $manifest ([ordered]@{schema_version='1.0';model_snapshot_id=$context.Manifest.snapshot_id;metadata_snapshot_id=$metadata.Manifest.snapshot_id;model_revision=$context.Manifest.model_revision;selections=$plan;queries=@($entries)})
    return [ordered]@{directory=$directory;manifest=$manifest;query_count=$entries.Count;attribute_count=$attributeCount}
}
