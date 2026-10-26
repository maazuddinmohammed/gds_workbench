# Technical-column projection, native Windows PowerShell 5.1 twin of workbench/policy-projection.js.
# Keep rules, ordering and messages aligned; tests/atlas/test_policy_projection.py pins the
# JavaScript port to the web backend and the native parity suite compares this file with Node.

function Get-AtlasCodePoints([string]$Value) {
    # Like JavaScript [...value]: pairs become one code point; lone surrogates stay single units.
    $points = New-Object 'System.Collections.Generic.List[int]'
    for ($index = 0; $index -lt $Value.Length; $index++) {
        if ([char]::IsHighSurrogate($Value[$index]) -and $index + 1 -lt $Value.Length -and [char]::IsLowSurrogate($Value[$index + 1])) {
            $points.Add([char]::ConvertToUtf32($Value[$index], $Value[$index + 1])); $index++
        }
        else { $points.Add([int]$Value[$index]) }
    }
    return ,$points
}

function Compare-AtlasCodePoints([string]$Left, [string]$Right) {
    # Python str ordering: Unicode code points, not UTF-16 code units.
    $a = Get-AtlasCodePoints $Left; $b = Get-AtlasCodePoints $Right
    for ($index = 0; $index -lt [Math]::Min($a.Count, $b.Count); $index++) {
        if ($a[$index] -ne $b[$index]) { return [Math]::Sign($a[$index] - $b[$index]) }
    }
    return [Math]::Sign($a.Count - $b.Count)
}

function Compare-AtlasKeyTuple([object[]]$Left, [object[]]$Right) {
    for ($index = 0; $index -lt [Math]::Min($Left.Count, $Right.Count); $index++) {
        $order = Compare-AtlasCodePoints ([string]$Left[$index]) ([string]$Right[$index])
        if ($order -ne 0) { return $order }
    }
    return [Math]::Sign($Left.Count - $Right.Count)
}

function Copy-AtlasJson($Value) { return ConvertFrom-GdsJson (ConvertTo-GdsJson $Value) }

function Get-AtlasEffectiveAuditTemplate($Template) {
    if ($null -ne $Template) { return Copy-AtlasJson $Template }
    $columns = New-Object Collections.ArrayList
    foreach ($row in @(
            @('SourceSystemID', 'BIGINT', 'Originating source System identifier.'), @('IsDataValid', 'BOOLEAN', 'Framework data validation flag.'),
            @('HashKey', 'STRING', 'Framework change-detection hash.'), @('IsActive', 'BOOLEAN', 'Framework active-record flag.'),
            @('GDSBatchID', 'BIGINT', 'Framework batch identifier.'), @('PipelineRunID', 'STRING', 'Framework pipeline run identifier.'),
            @('CreatedDate', 'TIMESTAMP', 'Framework record creation time.'), @('UpdatedDate', 'TIMESTAMP', 'Framework record update time.'),
            @('CreatedBy', 'STRING', 'Framework record creator.'), @('UpdatedBy', 'STRING', 'Framework record updater.'))) {
        [void]$columns.Add([ordered]@{semantic_name = $row[0]; data_type = $row[1]; nullable = $true; definition = $row[2]})
    }
    return [ordered]@{schema_version = '1.0'; columns = @($columns)}
}

function Get-AtlasEffectiveGoldTemplates($Technical, $Audit) {
    $keys = if ($null -ne $Technical) { Copy-AtlasJson $Technical } else {
        [ordered]@{schema_version = '1.0';
            dimension_surrogate_key = [ordered]@{semantic_name_template = '{entity_name}Key'; data_type = 'BIGINT'; nullable = $false; definition_template = 'Surrogate key for {entity_name}.'};
            fact_bridge_foreign_key = [ordered]@{with_role_semantic_name_template = '{role_name}Key'; without_role_semantic_name_template = '{entity_name}Key'; definition_template = 'Foreign key to {entity_name}.'};
            type_2 = [ordered]@{
                effective_from = [ordered]@{semantic_name = 'RecordStartTime'; data_type = 'TIMESTAMP'; nullable = $false; definition = 'Inclusive start of this dimension version.'};
                effective_to = [ordered]@{semantic_name = 'RecordEndTime'; data_type = 'TIMESTAMP'; nullable = $true; definition = 'Exclusive end of this dimension version.'};
                is_current = [ordered]@{semantic_name = 'IsCurrentRecord'; data_type = 'BOOLEAN'; nullable = $false; definition = 'Whether this is the current dimension version.'}}}
    }
    $columns = Get-AtlasEffectiveAuditTemplate $Audit
    foreach ($name in @('dimension_surrogate_key', 'fact_bridge_foreign_key', 'type_2')) {
        if (Test-Property $columns $name) {
            $value = Get-Property $columns $name
            Remove-Property $columns $name
            if ($null -ne $value) { Set-Property $keys $name $value }
        }
    }
    return @($keys, $columns)
}

function Test-AtlasPolicyColumn($Column) {
    if (-not (Test-AtlasObject $Column)) { return $false }
    $name = Get-Property $Column 'semantic_name'; $type = Get-Property $Column 'data_type'; $definition = Get-Property $Column 'definition'
    return $name -is [string] -and -not [string]::IsNullOrWhiteSpace($name) -and $name.Length -le 255 -and
        $type -is [string] -and -not [string]::IsNullOrWhiteSpace($type) -and $type.Length -le 100 -and
        (Get-Property $Column 'nullable') -is [bool] -and
        ($null -eq $definition -or ($definition -is [string] -and -not [string]::IsNullOrWhiteSpace($definition) -and $definition.Length -le 2000))
}

function Get-AtlasAuditColumns($Template, [string]$Label) {
    $columns = Get-Property $Template 'columns'
    $names = @{}
    $valid = $columns -is [Array] -and $columns.Count -le 32
    if ($valid) {
        foreach ($column in $columns) {
            if (-not (Test-AtlasPolicyColumn $column)) { $valid = $false; break }
            $normalized = Normalize-Value 'project' 'value' $column.semantic_name
            if ($names.ContainsKey($normalized)) { $valid = $false; break }
            $names[$normalized] = $true
        }
    }
    $layer = if ($Label -ceq 'Silver') { 'logical' } else { 'dimensional' }
    if (-not $valid) { Fail "Policy projection rejected the $layer draft: The $Label audit-column template is invalid." }
    return ,@($columns)
}

function Get-AtlasLayerKey([string]$Layer, $Record, [bool]$Attribute) {
    $values = @((Normalize-Value 'project' 'value' (Get-Property $Record ($Layer + '_entity_schema_name'))),
        (Normalize-Value 'project' 'value' (Get-Property $Record ($Layer + '_entity_name'))))
    if ($Attribute) { $values += ,(Normalize-Value 'project' 'value' (Get-Property $Record ($Layer + '_attribute_name'))) }
    return ,$values
}

function Get-AtlasKeyText([object[]]$Key) { return ConvertTo-StableJson @($Key) }

function Test-AtlasSameRecord($Left, $Right) {
    return $null -ne $Left -and $null -ne $Right -and (ConvertTo-StableJson $Left) -ceq (ConvertTo-StableJson $Right)
}

function Copy-AtlasRecord($Record, [string]$Field, $Value) {
    $copy = [ordered]@{}
    foreach ($name in @(Get-PropertyNames $Record)) { $copy[$name] = Get-Property $Record $name }
    $copy[$Field] = $Value
    return $copy
}

function Get-AtlasChangedAttributes([string]$Layer, [object[]]$BaselineAttributes, [object[]]$CandidateAttributes, [object[]]$Projected) {
    $byKey = New-Object Collections.Specialized.OrderedDictionary ([StringComparer]::Ordinal)
    foreach ($record in @($CandidateAttributes) + @($Projected)) {
        if ($null -eq $record) { continue }
        $byKey[(Get-AtlasKeyText (Get-AtlasLayerKey $Layer $record $true))] = $record
    }
    $applied = @{}
    foreach ($record in @($BaselineAttributes)) { if ($null -ne $record) { $applied[(Get-AtlasKeyText (Get-AtlasLayerKey $Layer $record $true))] = $record } }
    $result = New-Object Collections.ArrayList
    foreach ($key in @($byKey.Keys)) {
        if (-not (Test-AtlasSameRecord $applied[$key] $byKey[$key])) { [void]$result.Add($byKey[$key]) }
    }
    return ,@($result)
}

function Get-AtlasSortedRecords([object[]]$Records, [scriptblock]$Comparer) {
    # Insertion sort keeps equal items stable and avoids culture-sensitive Sort-Object.
    $sorted = New-Object Collections.ArrayList
    foreach ($record in @($Records)) {
        if ($null -eq $record) { continue }
        $index = $sorted.Count
        while ($index -gt 0 -and (& $Comparer $sorted[$index - 1] $record) -gt 0) { $index-- }
        $sorted.Insert($index, $record)
    }
    return ,@($sorted)
}

function Invoke-AtlasLogicalProjection($Candidate, $Baseline, $Template) {
    $columns = Get-AtlasAuditColumns (Get-AtlasEffectiveAuditTemplate $Template) 'Silver'
    $entities = New-Object Collections.Specialized.OrderedDictionary ([StringComparer]::Ordinal)
    foreach ($record in @($Baseline.entities) + @($Candidate.entities)) { if ($null -ne $record) { $entities[(Get-AtlasKeyText (Get-AtlasLayerKey 'logical' $record $false))] = $record } }
    $attributes = New-Object Collections.Specialized.OrderedDictionary ([StringComparer]::Ordinal)
    foreach ($record in @($Baseline.attributes) + @($Candidate.attributes)) { if ($null -ne $record) { $attributes[(Get-AtlasKeyText (Get-AtlasLayerKey 'logical' $record $true))] = $record } }
    $appliedEntities = @{}
    foreach ($record in @($Baseline.entities)) { if ($null -ne $record) { $appliedEntities[(Get-AtlasKeyText (Get-AtlasLayerKey 'logical' $record $false))] = $true } }
    $projected = New-Object Collections.ArrayList
    $ordered = Get-AtlasSortedRecords @($entities.Values) { param($a, $b) Compare-AtlasKeyTuple (Get-AtlasLayerKey 'logical' $a $false) (Get-AtlasLayerKey 'logical' $b $false) }
    foreach ($entity in $ordered) {
        if ((Get-Property $entity 'logical_entity_is_active') -ne $true) { continue }
        $entityKey = Get-AtlasLayerKey 'logical' $entity $false
        $entityText = Get-AtlasKeyText $entityKey
        $owned = { $list = New-Object Collections.ArrayList; foreach ($record in @($attributes.Values)) { if ((Get-AtlasKeyText @((Get-AtlasLayerKey 'logical' $record $true)[0..1])) -ceq $entityText) { [void]$list.Add($record) } }; return ,@($list) }
        $entityAttributes = & $owned
        $hasKeyAtOne = $false
        foreach ($row in $entityAttributes) { if ((Get-Property $row 'logical_attribute_is_surrogate_key') -eq $true -and (Get-Property $row 'logical_attribute_ordinal_position') -eq 1) { $hasKeyAtOne = $true } }
        if (-not $appliedEntities.ContainsKey($entityText) -or $hasKeyAtOne) {
            $surrogates = @($entityAttributes | Where-Object { (Get-Property $_ 'logical_attribute_is_surrogate_key') -eq $true })
            if ($surrogates.Count -gt 1) { Fail 'Policy projection rejected the logical draft: A new Logical Entity needs one own surrogate key.' }
            if ($surrogates.Count -eq 1) {
                $surrogate = $surrogates[0]
                $sources = Get-Property $surrogate 'sources'
                if (($sources -is [Array] -and $sources.Count -gt 0) -or (Get-Property $surrogate 'logical_attribute_is_nullable') -eq $true) { Fail 'Policy projection rejected the logical draft: An own generated surrogate cannot have physical sources.' }
            }
            else {
                $name = [string]$entity.logical_entity_name + 'ID'
                if ($attributes.Contains((Get-AtlasKeyText @($entityKey[0], $entityKey[1], (Normalize-Value 'project' 'value' $name))))) { Fail 'Policy projection rejected the logical draft: The generated key name conflicts with a business Attribute.' }
                $surrogate = [ordered]@{logical_entity_schema_name = $entity.logical_entity_schema_name; logical_entity_name = $entity.logical_entity_name;
                    logical_attribute_name = $name; logical_attribute_definition = 'Generated identifier for ' + $entity.logical_entity_name + '.';
                    logical_attribute_data_type = 'BIGINT'; logical_attribute_is_nullable = $false; logical_attribute_is_natural_key = $false;
                    logical_attribute_is_surrogate_key = $true; logical_attribute_ordinal_position = 1; logical_attribute_is_audit_column = $false;
                    logical_attribute_is_active = $true; logical_attribute_is_locked = $false; sources = @()}
            }
            $surrogateText = Get-AtlasKeyText (Get-AtlasLayerKey 'logical' $surrogate $true)
            $rest = Get-AtlasSortedRecords @($entityAttributes | Where-Object { (Get-AtlasKeyText (Get-AtlasLayerKey 'logical' $_ $true)) -cne $surrogateText }) {
                param($a, $b)
                $order = [Math]::Sign([long](Get-Property $a 'logical_attribute_ordinal_position') - [long](Get-Property $b 'logical_attribute_ordinal_position'))
                if ($order -ne 0) { return $order }
                return Compare-AtlasKeyTuple (Get-AtlasLayerKey 'logical' $a $true) (Get-AtlasLayerKey 'logical' $b $true)
            }
            $entityAttributes = New-Object Collections.ArrayList
            $ordinal = 0
            foreach ($row in @(@($surrogate) + @($rest))) {
                $ordinal++
                $desired = Copy-AtlasRecord $row 'logical_attribute_ordinal_position' $ordinal
                $attributes[(Get-AtlasKeyText (Get-AtlasLayerKey 'logical' $desired $true))] = $desired
                [void]$projected.Add($desired); [void]$entityAttributes.Add($desired)
            }
            $entityAttributes = @($entityAttributes)
        }
        $maximum = 0
        foreach ($record in $entityAttributes) {
            if ((Get-Property $record 'logical_attribute_is_audit_column') -ne $true -and [long](Get-Property $record 'logical_attribute_ordinal_position') -gt $maximum) { $maximum = [long](Get-Property $record 'logical_attribute_ordinal_position') }
        }
        $offset = 0
        foreach ($column in $columns) {
            $key = Get-AtlasKeyText @($entityKey[0], $entityKey[1], (Normalize-Value 'project' 'value' $column.semantic_name))
            $existing = if ($attributes.Contains($key)) { $attributes[$key] } else { $null }
            $sources = Get-Property $existing 'sources'
            if ($null -ne $existing -and ((Get-Property $existing 'logical_attribute_is_audit_column') -ne $true -or
                (Normalize-Value 'project' 'value' (Get-Property $existing 'logical_attribute_data_type')) -cne (Normalize-Value 'project' 'value' $column.data_type) -or
                (Get-Property $existing 'logical_attribute_is_nullable') -ne $column.nullable -or
                ($sources -is [Array] -and $sources.Count -gt 0 -and (Normalize-Value 'project' 'value' $column.semantic_name) -cne 'sourcesystemid'))) {
                Fail 'Policy projection rejected the logical draft: A configured Logical audit column conflicts with an existing Attribute.'
            }
            $definition = Get-Property $column 'definition'; if (-not $definition) { $definition = $column.semantic_name }
            $desired = [ordered]@{logical_entity_schema_name = $entity.logical_entity_schema_name; logical_entity_name = $entity.logical_entity_name;
                logical_attribute_name = $column.semantic_name; logical_attribute_definition = $definition;
                logical_attribute_data_type = $column.data_type; logical_attribute_is_nullable = $column.nullable;
                logical_attribute_is_natural_key = $(if ($null -ne $existing) { Get-Property $existing 'logical_attribute_is_natural_key' } else { $false });
                logical_attribute_is_surrogate_key = $false; logical_attribute_ordinal_position = $maximum + 1 + $offset;
                logical_attribute_is_audit_column = $true; logical_attribute_is_active = $true;
                logical_attribute_is_locked = $(if ($null -ne $existing) { Get-Property $existing 'logical_attribute_is_locked' } else { $false });
                sources = $(if ($null -ne $existing) { ,$sources } else { ,@() })}
            if ($null -ne $existing -and (Get-Property $existing 'logical_attribute_is_locked') -eq $true -and -not (Test-AtlasSameRecord $existing $desired)) { Fail 'Policy projection rejected the logical draft: A locked Logical audit column cannot be projected.' }
            if (-not (Test-AtlasSameRecord $existing $desired)) { [void]$projected.Add($desired) }
            $attributes[$key] = $desired
            $offset++
        }
    }
    $changed = Get-AtlasChangedAttributes 'logical' @($Baseline.attributes) @($Candidate.attributes) @($projected)
    return Get-AtlasSortedRecords $changed { param($a, $b) Compare-AtlasKeyTuple (Get-AtlasLayerKey 'logical' $a $true) (Get-AtlasLayerKey 'logical' $b $true) }
}

function Invoke-AtlasDimensionalProjection($Candidate, $Baseline, $Technical, $Audit, $ScdType) {
    $auditColumns = Get-AtlasAuditColumns $Audit 'Gold'
    $type2 = Get-Property $Technical 'type_2'
    if ($null -eq (Get-Property $Technical 'dimension_surrogate_key') -or $null -eq $type2 -or
        -not (Test-AtlasPolicyColumn (Get-Property $type2 'is_current')) -or -not (Test-AtlasPolicyColumn (Get-Property $type2 'effective_from')) -or
        -not (Test-AtlasPolicyColumn (Get-Property $type2 'effective_to'))) { Fail 'Policy projection rejected the dimensional draft: The Gold technical-column template is invalid.' }
    $entities = New-Object Collections.Specialized.OrderedDictionary ([StringComparer]::Ordinal)
    foreach ($record in @($Baseline.entities) + @($Candidate.entities)) { if ($null -ne $record) { $entities[(Get-AtlasKeyText (Get-AtlasLayerKey 'dimensional' $record $false))] = $record } }
    $attributes = New-Object Collections.Specialized.OrderedDictionary ([StringComparer]::Ordinal)
    foreach ($record in @($Baseline.attributes) + @($Candidate.attributes)) { if ($null -ne $record) { $attributes[(Get-AtlasKeyText (Get-AtlasLayerKey 'dimensional' $record $true))] = $record } }
    $appliedEntities = @{}
    foreach ($record in @($Baseline.entities)) { if ($null -ne $record) { $appliedEntities[(Get-AtlasKeyText (Get-AtlasLayerKey 'dimensional' $record $false))] = $true } }
    $projected = New-Object Collections.ArrayList
    $ordered = Get-AtlasSortedRecords @($entities.Values) { param($a, $b) Compare-AtlasKeyTuple (Get-AtlasLayerKey 'dimensional' $a $false) (Get-AtlasLayerKey 'dimensional' $b $false) }
    foreach ($entity in $ordered) {
        if ((Get-Property $entity 'dimensional_entity_is_active') -ne $true) { continue }
        $entityKey = Get-AtlasLayerKey 'dimensional' $entity $false
        $entityText = Get-AtlasKeyText $entityKey
        $owned = { $list = New-Object Collections.ArrayList; foreach ($record in @($attributes.Values)) { if ((Get-AtlasKeyText @((Get-AtlasLayerKey 'dimensional' $record $true)[0..1])) -ceq $entityText) { [void]$list.Add($record) } }; return ,@($list) }
        $entityAttributes = & $owned
        $isNew = -not $appliedEntities.ContainsKey($entityText)
        $hasKeyAtOne = $false
        foreach ($row in $entityAttributes) { if ((Get-Property $row 'dimensional_attribute_is_surrogate_key') -eq $true -and (Get-Property $row 'dimensional_attribute_ordinal_position') -eq 1) { $hasKeyAtOne = $true } }
        if ($isNew -or $hasKeyAtOne) {
            $business = Get-AtlasSortedRecords @($entityAttributes | Where-Object { (Get-Property $_ 'dimensional_attribute_is_surrogate_key') -ne $true }) {
                param($a, $b)
                $order = [Math]::Sign([long](Get-Property $a 'dimensional_attribute_ordinal_position') - [long](Get-Property $b 'dimensional_attribute_ordinal_position'))
                if ($order -ne 0) { return $order }
                return Compare-AtlasKeyTuple (Get-AtlasLayerKey 'dimensional' $a $true) (Get-AtlasLayerKey 'dimensional' $b $true)
            }
            $ordinal = 1
            foreach ($row in $business) {
                $ordinal++
                $desired = Copy-AtlasRecord $row 'dimensional_attribute_ordinal_position' $ordinal
                $attributes[(Get-AtlasKeyText (Get-AtlasLayerKey 'dimensional' $desired $true))] = $desired
                [void]$projected.Add($desired)
            }
            $entityAttributes = & $owned
        }
        $base = 0
        foreach ($record in $entityAttributes) {
            if ((Get-Property $record 'dimensional_attribute_is_audit_column') -ne $true -and (Get-Property $record 'dimensional_attribute_is_surrogate_key') -ne $true -and
                [long](Get-Property $record 'dimensional_attribute_ordinal_position') -gt $base) { $base = [long](Get-Property $record 'dimensional_attribute_ordinal_position') }
        }
        $specifications = New-Object Collections.ArrayList
        $history = New-Object Collections.ArrayList
        $kind = Get-Property $entity 'dimensional_entity_type'
        if ($kind -ceq 'dimension' -or $isNew) {
            $template = $Technical.dimension_surrogate_key
            $surrogate = [ordered]@{semantic_name = ([string]$template.semantic_name_template).Replace('{entity_name}', [string]$entity.dimensional_entity_name);
                data_type = $template.data_type; nullable = $false;
                definition = ([string]$template.definition_template).Replace('{entity_name}', [string]$entity.dimensional_entity_name)}
            if (-not (Test-AtlasPolicyColumn $surrogate)) { Fail 'Policy projection rejected the dimensional draft: The Gold surrogate-key template produced an invalid column. Shorten the Entity name so the configured key name fits 255 characters and its definition fits 2000 characters. Preserve the frozen policy.' }
            [void]$specifications.Add(@($surrogate, 'technical', 'surrogate'))
            if ($kind -ceq 'dimension' -and $ScdType -ceq 'type_2') { [void]$history.Add($type2.is_current); [void]$history.Add($type2.effective_from); [void]$history.Add($type2.effective_to) }
        }
        # History belongs to the audit group, immediately after SourceSystemID.
        $columns = New-Object Collections.ArrayList
        foreach ($column in $auditColumns) { [void]$columns.Add($column) }
        $anchor = -1
        for ($index = 0; $index -lt $columns.Count; $index++) { if ((Normalize-Value 'project' 'value' $columns[$index].semantic_name) -ceq 'sourcesystemid') { $anchor = $index; break } }
        $columns.InsertRange($anchor + 1, $history)
        foreach ($column in $columns) { [void]$specifications.Add(@($column, 'audit', 'none')) }
        $names = @{}
        foreach ($specification in $specifications) {
            $normalized = Normalize-Value 'project' 'value' $specification[0].semantic_name
            if ($names.ContainsKey($normalized)) { Fail 'Policy projection rejected the dimensional draft: Gold policy columns collide after normalization.' }
            $names[$normalized] = $true
        }
        $surrogateFirst = $specifications.Count -gt 0 -and $specifications[0][2] -ceq 'surrogate'
        for ($index = 0; $index -lt $specifications.Count; $index++) {
            $column = $specifications[$index][0]; $role = $specifications[$index][1]; $keyRole = $specifications[$index][2]
            $key = Get-AtlasKeyText @($entityKey[0], $entityKey[1], (Normalize-Value 'project' 'value' $column.semantic_name))
            $existing = if ($attributes.Contains($key)) { $attributes[$key] } else { $null }
            $sources = Get-Property $existing 'sources'
            if ($keyRole -ceq 'surrogate') {
                $ordinal = if ($isNew) { 1 } elseif ($null -ne $existing) { [long](Get-Property $existing 'dimensional_attribute_ordinal_position') } else { $base + 1 }
            }
            else { $ordinal = $base + $index + 1 - $(if ($surrogateFirst) { 1 } else { 0 }) }
            if ($null -ne $existing -and ((Get-Property $existing 'dimensional_attribute_is_audit_column') -ne ($role -ceq 'audit') -or
                (Get-Property $existing 'dimensional_attribute_is_natural_key') -eq $true -or
                (Normalize-Value 'project' 'value' (Get-Property $existing 'dimensional_attribute_data_type')) -cne (Normalize-Value 'project' 'value' $column.data_type) -or
                (Get-Property $existing 'dimensional_attribute_is_nullable') -ne $column.nullable -or
                (Get-Property $existing 'dimensional_attribute_is_surrogate_key') -ne ($keyRole -ceq 'surrogate') -or
                ($sources -is [Array] -and $sources.Count -gt 0 -and (Normalize-Value 'project' 'value' $column.semantic_name) -cne 'sourcesystemid'))) {
                Fail 'Policy projection rejected the dimensional draft: A configured Gold policy column conflicts with an existing Attribute.'
            }
            $definition = Get-Property $column 'definition'; if (-not $definition) { $definition = $column.semantic_name }
            $desired = [ordered]@{dimensional_entity_schema_name = $entity.dimensional_entity_schema_name; dimensional_entity_name = $entity.dimensional_entity_name;
                dimensional_attribute_name = $column.semantic_name; dimensional_attribute_definition = $definition;
                dimensional_attribute_data_type = $column.data_type; dimensional_attribute_is_nullable = $column.nullable;
                dimensional_attribute_ordinal_position = $ordinal; dimensional_attribute_is_natural_key = $false;
                dimensional_attribute_is_surrogate_key = ($keyRole -ceq 'surrogate'); dimensional_attribute_is_audit_column = ($role -ceq 'audit');
                dimensional_attribute_is_active = $true;
                dimensional_attribute_is_locked = $(if ($null -ne $existing) { Get-Property $existing 'dimensional_attribute_is_locked' } else { $false });
                sources = $(if ($null -ne $existing) { ,$sources } else { ,@() })}
            if ($null -ne $existing -and (Get-Property $existing 'dimensional_attribute_is_locked') -eq $true -and -not (Test-AtlasSameRecord $existing $desired)) { Fail 'Policy projection rejected the dimensional draft: A locked Gold policy column cannot be projected.' }
            if (-not (Test-AtlasSameRecord $existing $desired)) { [void]$projected.Add($desired) }
            $attributes[$key] = $desired
            if ($keyRole -ceq 'surrogate' -and $ordinal -gt $base) { $base = $ordinal }
        }
    }
    $changed = Get-AtlasChangedAttributes 'dimensional' @($Baseline.attributes) @($Candidate.attributes) @($projected)
    return Get-AtlasSortedRecords $changed {
        param($a, $b)
        $order = Compare-AtlasCodePoints (Normalize-Value 'project' 'value' $a.dimensional_entity_name) (Normalize-Value 'project' 'value' $b.dimensional_entity_name)
        if ($order -ne 0) { return $order }
        $order = [Math]::Sign([long]$a.dimensional_attribute_ordinal_position - [long]$b.dimensional_attribute_ordinal_position)
        if ($order -ne 0) { return $order }
        return Compare-AtlasCodePoints (Normalize-Value 'project' 'value' $a.dimensional_attribute_name) (Normalize-Value 'project' 'value' $b.dimensional_attribute_name)
    }
}

function Invoke-PolicyApply([hashtable]$Options) {
    $layer = [string]$Options['layer']
    if (@('logical', 'dimensional') -cnotcontains $layer) { Fail '--layer must be logical or dimensional.' }
    if ($Options.ContainsKey('dry-run') -and $Options['dry-run'] -cne 'true') { Fail '--dry-run accepts true only.' }
    $contextOptions = $Options.Clone(); $contextOptions.area = 'project'
    $context = Get-ChangeContext $contextOptions
    Assert-Digest $Options $context
    $pending = Read-Pending $context
    $datasetName = $layer + '_attribute'
    if (-not $context.ByName.ContainsKey($datasetName) -or -not $context.ByName.ContainsKey($layer + '_entity')) { Fail "Project Snapshot has no $layer datasets." }
    $dataset = $context.ByName[$datasetName]
    $details = $null
    if ($pending.ContainsKey('project_details') -and @($pending['project_details']).Count -gt 0) { $details = @($pending['project_details'])[0] }
    elseif ($context.ByName.ContainsKey('project_details')) { $details = @(Read-SnapshotRecords $context $context.ByName['project_details'])[0] }
    $candidate = [pscustomobject]@{entities = @(if ($pending.ContainsKey($layer + '_entity')) { $pending[$layer + '_entity'] }); attributes = @(if ($pending.ContainsKey($datasetName)) { $pending[$datasetName] })}
    $baseline = [pscustomobject]@{entities = @(Read-SnapshotRecords $context $context.ByName[$layer + '_entity']); attributes = @(Read-SnapshotRecords $context $dataset)}
    if ($layer -ceq 'logical') { $records = Invoke-AtlasLogicalProjection $candidate $baseline (Get-Property $details 'silver_model_audit_columns_template') }
    else {
        $templates = Get-AtlasEffectiveGoldTemplates (Get-Property $details 'gold_model_technical_columns_template') (Get-Property $details 'gold_model_audit_columns_template')
        $records = Invoke-AtlasDimensionalProjection $candidate $baseline $templates[0] $templates[1] (Get-Property $details 'dimensional_entity_scd_type')
    }
    $records = @($records)
    $before = @{}
    foreach ($record in @($candidate.attributes)) { if ($null -ne $record) { $before[(Get-CanonicalKey 'project' $dataset $record)] = $record } }
    $after = @{}
    foreach ($record in $records) { $after[(Get-CanonicalKey 'project' $dataset $record)] = $true }
    $nameOf = { param($record) [string]$record.($layer + '_entity_schema_name') + '.' + [string]$record.($layer + '_entity_name') + '.' + [string]$record.($layer + '_attribute_name') }
    $added = New-Object Collections.ArrayList; $changed = New-Object Collections.ArrayList; $dropped = New-Object Collections.ArrayList
    foreach ($record in $records) {
        $key = Get-CanonicalKey 'project' $dataset $record
        if (-not $before.ContainsKey($key)) { [void]$added.Add((& $nameOf $record)) }
        elseif ((ConvertTo-StableJson $before[$key]) -cne (ConvertTo-StableJson $record)) { [void]$changed.Add((& $nameOf $record)) }
    }
    foreach ($record in @($candidate.attributes)) { if ($null -ne $record -and -not $after.ContainsKey((Get-CanonicalKey 'project' $dataset $record))) { [void]$dropped.Add((& $nameOf $record)) } }
    $summary = [ordered]@{layer = $layer; dataset = $datasetName; record_count = $records.Count; added = @($added); changed = @($changed); dropped_unchanged = @($dropped)}
    if ($Options['dry-run'] -ceq 'true') { $summary.dry_run = $true; $summary.digest = Get-WorkspaceDigest $context; return $summary }
    $schema = Get-EditableSchema $context $dataset
    $lockField = $layer + '_attribute_is_locked'
    $baselineByKey = @{}
    foreach ($record in @($baseline.attributes)) { if ($null -ne $record) { $baselineByKey[(Get-CanonicalKey 'project' $dataset $record)] = $record } }
    foreach ($record in $records) {
        $issues = @(Get-SchemaIssues $record $schema)
        if ($issues.Count -gt 0) { Fail "$datasetName projected record is invalid: $($issues[0])" }
    }
    foreach ($record in $records) {
        $original = $baselineByKey[(Get-CanonicalKey 'project' $dataset $record)]
        if ($null -ne $original -and (Get-Property $original $lockField) -eq $true -and (ConvertTo-StableJson $original) -cne (ConvertTo-StableJson $record)) { Fail 'Locked records cannot be changed locally.' }
    }
    Assert-Digest $Options $context
    $file = Join-Path $context.ChangeDirectory ($datasetName + '.json')
    if ($records.Count -gt 0) { Write-Pending $context $dataset $records }
    elseif (Test-Path -LiteralPath $file) { Write-JsonAtomic $file @() }
    $summary.dry_run = $false; $summary.digest = Get-WorkspaceDigest $context
    return $summary
}

function Get-AtlasCoverage([hashtable]$Options) {
    # Twin of coverageReport in atlas-local.js: the web workflow's coverage rule on the effective Project.
    $layer = [string]$Options['layer']
    if (@('logical', 'dimensional') -cnotcontains $layer) { Fail '--layer must be logical or dimensional.' }
    if ($Options.ContainsKey('select') -and $Options.ContainsKey('subject-area')) { Fail 'Use --select or --subject-area, not both.' }
    $snapshot = Find-Snapshot @{session = (Require-Option $Options 'session'); area = 'project'}
    $directory = [IO.Path]::Combine($snapshot.Session, 'project-change-set')
    $pending = @{}
    if (Test-Path -LiteralPath $directory -PathType Container) {
        $snapshot | Add-Member -NotePropertyName ChangeDirectory -NotePropertyValue $directory
        $pending = Read-Pending $snapshot
    }
    # Both stream rows; callers collect them with @(...).
    $applied = { param($name) if ($snapshot.ByName.ContainsKey($name)) { return @(Read-SnapshotRecords $snapshot $snapshot.ByName[$name]) } }
    $effective = {
        param($name)
        if (-not $snapshot.ByName.ContainsKey($name)) { return }
        $draft = if ($pending.ContainsKey($name)) { @($pending[$name]) } else { @() }
        return @(Get-EffectiveRecords $snapshot $snapshot.ByName[$name] $draft)
    }
    $details = @(& $effective 'project_details') | Select-Object -First 1
    $percent = Get-Property $details ($layer + '_coverage_threshold_percent')
    if ($null -eq $percent) { $percent = if ($layer -ceq 'logical') { 70 } else { 60 } }
    $physical = @('tenant_code', 'system_code', 'connection_code', 'object_schema', 'object_name')
    $logical = @('logical_entity_schema_name', 'logical_entity_name')
    $keyOf = { param($record, $fields) $values = @(); foreach ($field in $fields) { $values += ,(Normalize-Value 'project' $field (Get-Property $record $field)) }; return ConvertTo-StableJson @($values) }
    $labelOf = { param($record, $fields) $values = @(); foreach ($field in $fields) { $values += ,[string](Get-Property $record $field) }; return $values -join '.' }
    if ($layer -ceq 'logical') {
        $fields = $physical; $entityDataset = 'logical_entity'; $sourceType = 'object'; $sourceField = 'source_object'
        $inputs = @(@(& $applied 'project_input_scope') | Where-Object { (Get-Property $_ 'is_active') -eq $true })
    }
    else {
        $fields = $logical; $entityDataset = 'dimensional_entity'; $sourceType = 'logical_entity'; $sourceField = 'source_logical_entity'
        $inputs = @(@(& $applied 'logical_entity') | Where-Object { (Get-Property $_ 'logical_entity_is_active') -eq $true })
    }
    $selected = $inputs
    $area = $null
    if ($Options.ContainsKey('subject-area')) {
        # Selects like a web Build of one applied area: its active member Objects, or the active
        # Logical Entities with an active Object source among those members.
        $areaKey = Normalize-Value 'project' 'subject_area_name' $Options['subject-area']
        foreach ($row in @(& $applied 'subject_area')) {
            if ($null -ne $row -and (Get-Property $row 'subject_area_is_active') -eq $true -and
                (Normalize-Value 'project' 'subject_area_name' (Get-Property $row 'subject_area_name')) -ceq $areaKey) { $area = $row; break }
        }
        if ($null -eq $area) { Fail '--subject-area names no active applied Subject Area.' }
        $members = @{}
        foreach ($row in @(& $applied 'subject_area_table')) {
            if ($null -ne $row -and (Get-Property $row 'subject_area_table_is_active') -eq $true -and
                (Normalize-Value 'project' 'subject_area_name' (Get-Property $row 'subject_area_name')) -ceq $areaKey) { $members[(& $keyOf $row $physical)] = $true }
        }
        if ($layer -ceq 'logical') { $selected = @($inputs | Where-Object { $members.ContainsKey((& $keyOf $_ $physical)) }) }
        else {
            $selected = @($inputs | Where-Object {
                $inArea = $false
                foreach ($source in (Get-Property $_ 'sources')) {
                    if ($null -ne $source -and (Get-Property $source 'support_source_type') -ceq 'object' -and (Get-Property $source 'is_active') -eq $true -and
                        $members.ContainsKey((& $keyOf (Get-Property $source 'source_object') $physical))) { $inArea = $true; break }
                }
                $inArea
            })
        }
    }
    if ($Options.ContainsKey('select')) {
        try { $requested = ConvertFrom-GdsJson $Options['select'] } catch { Fail '--select must be a JSON array of input identities.' }
        if ($requested -isnot [Array] -or $requested.Count -eq 0) { Fail '--select must be a non-empty JSON array of input identity objects.' }
        $wanted = @{}
        foreach ($item in $requested) {
            if (-not (Test-AtlasObject $item)) { Fail '--select must be a non-empty JSON array of input identity objects.' }
            $wanted[(& $keyOf $item $fields)] = $true
        }
        $selected = @($inputs | Where-Object { $wanted.ContainsKey((& $keyOf $_ $fields)) })
        if ($selected.Count -ne $wanted.Count) { Fail '--select names an input outside the applied eligible inputs.' }
    }
    $covered = @{}
    foreach ($entity in @(& $effective $entityDataset)) {
        if ($null -eq $entity -or (Get-Property $entity ($entityDataset + '_is_active')) -ne $true) { continue }
        foreach ($source in (Get-Property $entity 'sources')) {
            if ($null -ne $source -and (Get-Property $source 'support_source_type') -ceq $sourceType -and (Get-Property $source 'is_active') -eq $true) {
                $covered[(& $keyOf (Get-Property $source $sourceField) $fields)] = $true
            }
        }
    }
    $missing = New-Object Collections.ArrayList
    foreach ($row in @($selected)) { if ($null -ne $row -and -not $covered.ContainsKey((& $keyOf $row $fields))) { [void]$missing.Add((& $labelOf $row $fields)) } }
    $total = @($selected | Where-Object { $null -ne $_ }).Count
    $coveredCount = $total - $missing.Count
    $required = [long][Math]::Floor(($total * [double]$percent + 99) / 100)
    $result = [ordered]@{layer = $layer}
    if ($null -ne $area) { $result.subject_area = Get-Property $area 'subject_area_name' }
    $result.threshold_percent = $percent; $result.enforced = ((Get-Property $details ($layer + '_enforce_coverage_threshold')) -eq $true)
    $result.total = $total; $result.covered = $coveredCount; $result.required = $required; $result.meets_target = ($coveredCount -ge $required)
    $result.missing_count = $missing.Count; $result.missing = @($missing | Select-Object -First 50)
    return $result
}
