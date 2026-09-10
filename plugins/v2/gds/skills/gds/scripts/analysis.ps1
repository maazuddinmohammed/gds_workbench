# Aggregate planning only. Reuse the native profiling key and identifier helpers.
. (Join-Path $PSScriptRoot 'profiling.ps1')

function Assert-AnalysisFields($Value, [string[]]$Names, [string]$Label) {
    $actual = @(Get-PropertyNames $Value)
    if ($null -eq $Value -or $Value -is [Array] -or $actual.Count -ne $Names.Count -or
        @($Names | Where-Object { $actual -cnotcontains $_ }).Count) { Fail "$Label requires only its documented fields." }
}

function Resolve-AnalysisEndpoint($Metadata, $Scope, $Endpoint, $Masked) {
    Assert-AnalysisFields $Endpoint @('object','columns') 'Analysis endpoint'
    Assert-AnalysisFields $Endpoint.object $script:ProfileFields 'Object key'
    foreach ($field in $script:ProfileFields) {
        $value = Get-Property $Endpoint.object $field
        if ($value -isnot [string] -or [string]::IsNullOrWhiteSpace($value)) { Fail 'Object key requires registered nonblank names.' }
    }
    $names = $Endpoint.columns
    if ($names -isnot [Array] -or $names.Count -lt 1 -or $names.Count -gt 8) { Fail 'Select 1-8 distinct registered Attributes.' }
    $seen = @{}
    foreach ($name in $names) {
        if ($name -isnot [string] -or [string]::IsNullOrWhiteSpace($name)) { Fail 'Select 1-8 distinct registered Attributes.' }
        $normalized = Normalize-Value 'metadata' 'object_name' $name
        if ($seen.ContainsKey($normalized)) { Fail 'Select 1-8 distinct registered Attributes.' }
        $seen[$normalized] = $true
    }
    $identity = Get-ProfileKey $Endpoint.object
    if (-not @($Scope | Where-Object { ((Get-Active $_) -ne $false) -and (Get-ProfileKey $_) -ceq $identity }).Count) { Fail 'Object is outside active Model Input Scope.' }
    $objects = @(@($Metadata.source_object) + @($Metadata.bronze_object) | Where-Object { $null -ne $_ -and ((Get-Active $_) -ne $false) })
    $matches = @($objects | Where-Object { (Get-ProfileKey $_) -ceq $identity })
    if ($matches.Count -ne 1) { Fail 'Object is missing or ambiguous in Source/Bronze Metadata.' }
    $object = $matches[0]
    $source = (Normalize-Value 'metadata' 'object_name' $object.zone_code) -ceq 'source'
    if (-not $source -and (Normalize-Value 'metadata' 'object_name' $object.zone_code) -cne 'bronze') { Fail 'Analysis requires Source or Bronze Objects.' }
    $connections = @($Metadata.connection | Where-Object { ((Get-Active $_) -ne $false) -and
        (Get-ProfileKey $_ '' @('tenant_code','system_code','connection_code')) -ceq (Get-ProfileKey $object '' @('tenant_code','system_code','connection_code')) })
    $tenants = @($Metadata.tenant | Where-Object { ((Get-Active $_) -ne $false) -and
        (Normalize-Value 'metadata' 'object_name' $_.tenant_code) -ceq (Normalize-Value 'metadata' 'object_name' $object.tenant_code) })
    if ($connections.Count -ne 1 -or $tenants.Count -ne 1) { Fail 'Object placement is not uniquely active in Metadata.' }
    if ($source -and (Get-Property $connections[0] 'has_foreign_catalog') -eq $false) { Fail 'Source Object requires a registered foreign catalog.' }
    $coordinates = if ($source) { @($connections[0].foreign_catalog,$object.fc_object_schema,$object.fc_object_name) }
        else { @($tenants[0].tenant_catalog,$object.object_schema,$object.object_name) }
    $relation = ($coordinates | ForEach-Object { Quote-ProfileName $_ }) -join '.'
    $allAttributes = @($Metadata.source_attribute) + @($Metadata.bronze_attribute)
    $attributes = New-Object System.Collections.ArrayList
    foreach ($name in $names) {
        $candidates = @($allAttributes | Where-Object { $null -ne $_ -and ((Get-Active $_) -ne $false) -and
            (Get-ProfileKey $_) -ceq $identity -and (Normalize-Value 'metadata' 'object_name' $_.attribute_name) -ceq (Normalize-Value 'metadata' 'object_name' $name) })
        if ($candidates.Count -ne 1) { Fail 'Attribute is missing or ambiguous in active Metadata.' }
        $attribute = $candidates[0]
        if ($Masked.ContainsKey((Get-ProfileKey $attribute '' (@($script:ProfileFields) + @('attribute_name'))))) { Fail 'Masked Attributes cannot be used in Analysis probes.' }
        $type = ([string](Get-Property $attribute 'attribute_data_type')).ToUpperInvariant() -replace '\s+', ''
        if ($type -cnotmatch $script:ProfileStringType -and $type -cnotmatch $script:ProfileScalarType) { Fail 'Analysis probes require scalar registered Attribute types.' }
        $sqlName = if ($source) { Get-Property $attribute 'fc_attribute_name' } else { $attribute.attribute_name }
        [void]$attributes.Add([ordered]@{name=$attribute.attribute_name;sql=(Quote-ProfileName $sqlName);type=$type})
    }
    $sqlNames = @($attributes | ForEach-Object { Normalize-Value 'metadata' 'object_name' $_.sql } | Select-Object -Unique)
    if ($sqlNames.Count -ne $attributes.Count) { Fail 'Attribute SQL coordinates are ambiguous.' }
    $origins = New-Object System.Collections.ArrayList
    if ($source) { [void]$origins.Add($object) }
    else {
        foreach ($mapping in @($Metadata.ingestion_object_mapping)) {
            if ($null -eq $mapping -or (Get-Active $mapping) -eq $false -or (Get-ProfileKey $mapping 'target_') -cne $identity) { continue }
            foreach ($origin in $objects) {
                if ((Get-ProfileKey $origin) -ceq (Get-ProfileKey $mapping 'source_') -and
                    (Normalize-Value 'metadata' 'object_name' $origin.source_tenant_code) -ceq (Normalize-Value 'metadata' 'object_name' $object.source_tenant_code)) { [void]$origins.Add($origin) }
            }
        }
    }
    return [ordered]@{object=(Get-ProfileObjectKey $object);source_tenant_code=$object.source_tenant_code;
        source_system_codes=@($origins | ForEach-Object { Normalize-Value 'metadata' 'object_name' $_.system_code } | Select-Object -Unique);
        columns=@($attributes | ForEach-Object { $_.name });attributes=@($attributes);relation=$relation}
}

function Build-AnalysisSql([string]$Kind, $Endpoints, [int]$DeterminantCount) {
    $ctes = New-Object 'System.Collections.Generic.List[string]'
    $metrics = New-Object System.Collections.ArrayList
    $metric = { param($Name,$Sql) [void]$metrics.Add([ordered]@{name=$Name;sql="CAST(($Sql) AS BIGINT) AS $Name"}) }
    $scoped = {
        param($Name,$Endpoint)
        $columns = @(for ($i=0; $i -lt $Endpoint.attributes.Count; $i++) { 'c' + $i })
        $projected = @(for ($i=0; $i -lt $Endpoint.attributes.Count; $i++) { $Endpoint.attributes[$i].sql + ' AS ' + $columns[$i] })
        $ctes.Add("$Name AS (`nSELECT " + ($projected -join ', ') + "`n  FROM " + $Endpoint.relation + "`n)")
        return ,$columns
    }
    $complete = { param($Columns) return ($Columns | ForEach-Object { $_ + ' IS NOT NULL' }) -join ' AND ' }
    $nulls = { param($Columns) return ($Columns | ForEach-Object { $_ + ' IS NULL' }) -join ' OR ' }
    $counts = {
        param($Name,$Source,$Columns)
        $ctes.Add("$Name AS (`nSELECT " + ($Columns -join ', ') + ", COUNT(*) AS key_rows`n  FROM $Source`n WHERE " + (& $complete $Columns) + "`n GROUP BY " + ($Columns -join ', ') + "`n)")
    }
    if ($Kind -ceq 'key') {
        $columns = & $scoped 'scoped' $Endpoints[0]
        & $counts 'key_counts' 'scoped' $columns
        & $metric 'row_count' 'SELECT COUNT(*) FROM scoped'
        & $metric 'null_key_row_count' ('SELECT COUNT(*) FROM scoped WHERE ' + (& $nulls $columns))
        & $metric 'distinct_complete_key_count' 'SELECT COUNT(*) FROM key_counts'
        & $metric 'duplicate_complete_key_row_count' 'SELECT COALESCE(SUM(key_rows - 1), 0) FROM key_counts'
    }
    elseif ($Kind -ceq 'dependency') {
        $columns = & $scoped 'scoped' $Endpoints[0]
        $determinants = @($columns | Select-Object -First $DeterminantCount)
        $ctes.Add("dependent_tuples AS (`nSELECT " + ($columns -join ', ') + "`n  FROM scoped`n WHERE " + (& $complete $determinants) + "`n GROUP BY " + ($columns -join ', ') + "`n)")
        $ctes.Add("determinant_variants AS (`nSELECT " + ($determinants -join ', ') + ", COUNT(*) AS dependent_tuple_count`n  FROM dependent_tuples`n GROUP BY " + ($determinants -join ', ') + "`n)")
        & $metric 'row_count' 'SELECT COUNT(*) FROM scoped'
        & $metric 'null_determinant_row_count' ('SELECT COUNT(*) FROM scoped WHERE ' + (& $nulls $determinants))
        & $metric 'complete_determinant_group_count' 'SELECT COUNT(*) FROM determinant_variants'
        & $metric 'conflicting_determinant_group_count' 'SELECT COUNT(*) FROM determinant_variants WHERE dependent_tuple_count > 1'
    }
    else {
        $columns = & $scoped 'source_rows' $Endpoints[0]
        $null = & $scoped 'target_rows' $Endpoints[1]
        & $counts 'source_counts' 'source_rows' $columns
        & $counts 'target_counts' 'target_rows' $columns
        $equality = ($columns | ForEach-Object { 's.' + $_ + ' = t.' + $_ }) -join ' AND '
        & $metric 'validation_source_non_null_count' 'SELECT COALESCE(SUM(key_rows), 0) FROM source_counts'
        & $metric 'validation_source_distinct_count' 'SELECT COUNT(*) FROM source_counts'
        & $metric 'validation_target_non_null_count' 'SELECT COALESCE(SUM(key_rows), 0) FROM target_counts'
        & $metric 'validation_target_distinct_count' 'SELECT COUNT(*) FROM target_counts'
        & $metric 'validation_source_missing_target_count' "SELECT COUNT(*) FROM source_counts s WHERE NOT EXISTS (SELECT 1 FROM target_counts t WHERE $equality)"
        & $metric 'validation_unused_target_count' "SELECT COUNT(*) FROM target_counts t WHERE NOT EXISTS (SELECT 1 FROM source_counts s WHERE $equality)"
        & $metric 'validation_duplicate_target_key_count' 'SELECT COALESCE(SUM(key_rows - 1), 0) FROM target_counts'
        & $metric 'source_null_key_row_count' ('SELECT COUNT(*) FROM source_rows WHERE ' + (& $nulls $columns))
        & $metric 'target_null_key_row_count' ('SELECT COUNT(*) FROM target_rows WHERE ' + (& $nulls $columns))
    }
    $names = @($metrics | ForEach-Object { $_.name })
    $sql = 'WITH ' + ($ctes -join ",`n") + "`n"
    $summary = "SELECT`n       " + (($metrics | ForEach-Object { $_.sql }) -join ",`n       ")
    if ($Kind -ceq 'join') {
        $sql += ", summary AS (`n$summary`n)`nSELECT " + ($names -join ', ') + ",`n       CASE WHEN validation_source_non_null_count = 0 OR validation_target_non_null_count = 0 THEN 'inconclusive'`n            WHEN validation_source_missing_target_count = 0 AND validation_duplicate_target_key_count = 0 THEN 'supported'`n            ELSE 'unsupported' END AS validation_result`n  FROM summary"
        $names += 'validation_result'
    }
    else { $sql += $summary }
    if ($sql.Length -gt 100000) { Fail 'Analysis query exceeds SQL limit.' }
    return [ordered]@{sql=$sql;result_columns=$names}
}

function Plan-Analysis($Metadata, $Scope, $Plan) {
    Assert-AnalysisFields $Plan @('scope','probes') 'Analysis plan'
    if ($Plan.scope -cne 'all_rows') { Fail 'Analysis scope must explicitly be all_rows.' }
    if ($Plan.probes -isnot [Array] -or $Plan.probes.Count -lt 1 -or $Plan.probes.Count -gt 50) { Fail 'Select 1-50 Analysis probes.' }
    $ids = New-Object 'System.Collections.Generic.Dictionary[string,bool]' ([StringComparer]::Ordinal)
    $queries = New-Object System.Collections.ArrayList
    $masked = Get-ProfileMaskingKeys $Metadata
    foreach ($probe in $Plan.probes) {
        $kind = Get-Property $probe 'kind'
        $names = if ($kind -ceq 'key') { @('id','kind','object','columns') }
            elseif ($kind -ceq 'dependency') { @('id','kind','object','determinants','dependents') }
            elseif ($kind -ceq 'join') { @('id','kind','from','to') } else { Fail 'Probe kind must be key, dependency, or join.' }
        Assert-AnalysisFields $probe $names 'Analysis probe'
        if ($probe.id -isnot [string] -or $probe.id -cnotmatch '^[A-Za-z][A-Za-z0-9_-]{0,63}$' -or $ids.ContainsKey($probe.id)) { Fail 'Probe IDs must be unique bounded identifiers.' }
        $ids[$probe.id] = $true
        $determinantCount = 0
        if ($kind -ceq 'dependency') {
            $determinants = Resolve-AnalysisEndpoint $Metadata $Scope @{object=$probe.object;columns=$probe.determinants} $masked
            $dependents = Resolve-AnalysisEndpoint $Metadata $Scope @{object=$probe.object;columns=$probe.dependents} $masked
            $determinantCount = $determinants.columns.Count
            $columns = @($determinants.columns) + @($dependents.columns)
            $unique = @($columns | ForEach-Object { Normalize-Value 'metadata' 'object_name' $_ } | Select-Object -Unique)
            if ($unique.Count -ne $columns.Count) { Fail 'Determinants and dependents must be different Attributes.' }
            $determinants.columns = $columns
            $determinants.attributes = @($determinants.attributes) + @($dependents.attributes)
            $endpoints = @($determinants)
        }
        elseif ($kind -ceq 'join') {
            $endpoints = @((Resolve-AnalysisEndpoint $Metadata $Scope $probe.from $masked),(Resolve-AnalysisEndpoint $Metadata $Scope $probe.to $masked))
            if ($endpoints[0].columns.Count -ne $endpoints[1].columns.Count) { Fail 'Join requires equal-length Attribute lists with matching registered types; casts are not inferred.' }
            $same = (Get-ProfileKey $endpoints[0].object) -ceq (Get-ProfileKey $endpoints[1].object)
            for ($i=0; $i -lt $endpoints[0].columns.Count; $i++) {
                if ($endpoints[0].attributes[$i].type -cne $endpoints[1].attributes[$i].type) { Fail 'Join requires equal-length Attribute lists with matching registered types; casts are not inferred.' }
                if ((Normalize-Value 'metadata' 'object_name' $endpoints[0].columns[$i]) -cne (Normalize-Value 'metadata' 'object_name' $endpoints[1].columns[$i])) { $same = $false }
            }
            if ($same) { Fail 'Join endpoints must differ.' }
        }
        else { $endpoints = @((Resolve-AnalysisEndpoint $Metadata $Scope @{object=$probe.object;columns=$probe.columns} $masked)) }
        $interpretation = if ($kind -ceq 'key') { 'A nonempty result with zero null-key rows and duplicate complete-key rows supports observed uniqueness only; confirm business identity and lifecycle.' }
            elseif ($kind -ceq 'dependency') { 'Conflicting determinant groups have multiple distinct dependent tuples. Null determinants are counted as rows and excluded; null dependents count as tuple values. Zero conflicts on empty evidence proves nothing.' }
            else { 'Supported means nonempty complete keys, no missing source keys, and unique target keys. Null-key rows are excluded and reported separately. Matching values do not prove shared business identity or future cardinality.' }
        $publicEndpoints = @(foreach ($endpoint in $endpoints) {
            [ordered]@{object=$endpoint.object;source_tenant_code=$endpoint.source_tenant_code;source_system_codes=$endpoint.source_system_codes;columns=$endpoint.columns}
        })
        $query = [ordered]@{id=$probe.id;kind=$kind;scope='all_rows';execution_state='not_run';scan_cost='unknown';max_result_rows=1;endpoints=$publicEndpoints}
        if ($kind -ceq 'dependency') { $query['determinant_count'] = $determinantCount }
        $query['interpretation'] = $interpretation
        $built = Build-AnalysisSql $kind $endpoints $determinantCount
        $query['sql'] = $built.sql; $query['result_columns'] = $built.result_columns
        [void]$queries.Add($query)
    }
    return $queries.ToArray()
}
