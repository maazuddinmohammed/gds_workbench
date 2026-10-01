# Native counterpart of workbench/validation/model-policy.js. Keep rule IDs aligned.
function Get-PolicyTuple($Values) {
    return ConvertTo-StableJson @($Values | ForEach-Object { Normalize-Value 'model' 'value' $_ })
}
function Get-PolicyPhysical($Record, [bool]$Attribute = $false) {
    $fields = @('tenant_code', 'system_code', 'connection_code', 'object_schema', 'object_name')
    if ($Attribute) { $fields += 'attribute_name' }
    $values = New-Object Collections.ArrayList
    foreach ($field in $fields) { [void]$values.Add((Get-Property $Record $field)) }
    return Get-PolicyTuple @($values)
}
function Add-PolicyIssue($Issues, [string]$Code, [string]$Dataset, [string]$Field, [string]$Message, [string]$Severity = 'error') {
    [void]$Issues.Add([ordered]@{severity = $Severity; dataset = $Dataset; record = $null; code = $Code; fields = @($Field); message = $Message})
}
function Get-AtlasModelPolicy($States, $MetadataStates, $Model) {
    $issues = New-Object Collections.ArrayList; $changed = @{}; $added = @{}; $rows = @{}; $originals = @{}
    foreach ($state in $States) {
        $name = [string]$state.Dataset.name; $baseline = @{}; $changeList = New-Object Collections.ArrayList; $addList = New-Object Collections.ArrayList
        foreach ($record in @($state.Baseline)) { $baseline[(Get-CanonicalKey 'model' $state.Dataset $record)] = $record }
        foreach ($record in @($state.Pending)) {
            $key = Get-CanonicalKey 'model' $state.Dataset $record
            if (-not $baseline.ContainsKey($key) -or (ConvertTo-StableJson $baseline[$key]) -cne (ConvertTo-StableJson $record)) { [void]$changeList.Add($record) }
            if (-not $baseline.ContainsKey($key)) { [void]$addList.Add($record) }
        }
        $changed[$name] = @($changeList); $added[$name] = @($addList); $rows[$name] = @($state.Effective); $originals[$name] = $baseline
    }
    $details = if ($rows.ContainsKey('model_details') -and $rows.model_details.Count -gt 0) { $rows.model_details[0] } else { $Model }
    foreach ($state in $States) {
        foreach ($field in @('logical_entity_scd_type', 'dimensional_entity_scd_type')) {
            if ($state.Dataset.name -ceq 'model_details' -and @($state.Baseline).Count -gt 0 -and @($state.Pending).Count -gt 0 -and
                (Get-Property $state.Baseline[0] $field) -cne (Get-Property $state.Pending[0] $field)) {
                Add-PolicyIssue $issues 'model_policy_read_only' 'model_details' $field 'SCD type must be changed through Model settings.'
            }
        }
    }
    foreach ($dataset in @('conceptual_object', 'conceptual_relationship', 'logical_submodel', 'logical_entity', 'logical_attribute', 'logical_relationship', 'dimensional_submodel', 'dimensional_entity', 'dimensional_attribute', 'dimensional_relationship')) {
        $override = Get-Property $details $(if ($dataset.StartsWith('dimensional')) {'gold_model_naming_instructions'} else {'silver_model_naming_instructions'})
        foreach ($record in @($added[$dataset])) {
            if ($null -eq $record) { continue }
            $field = $dataset + '_name'; $name = Get-Property $record $field
            if (-not $override -and ($name -isnot [string] -or $name -cnotmatch '^[A-Z][A-Za-z0-9]*$' -or $name -cmatch 'Id$')) {
                Add-PolicyIssue $issues 'model.naming-policy' $dataset $field 'New modeled names use PascalCase and uppercase ID for an identifier suffix. An approved Model naming override may specify another convention.'
            }
        }
        if ($override -and @($added[$dataset]).Count -gt 0 -and $null -ne $added[$dataset]) { Add-PolicyIssue $issues 'model.naming-review' $dataset ($dataset + '_name') "Review new names against the Model's explicit naming instructions." 'warning' }
    }
    foreach ($layer in @('logical', 'dimensional')) {
        $entityDataset = $layer + '_entity'; $attributeDataset = $layer + '_attribute'; $entityField = $entityDataset + '_name'; $schemaField = $entityDataset + '_schema_name'; $attributeField = $attributeDataset + '_name'
        $configuredSchemas = Get-Property $details ($layer + '_schemas')
        if ($null -eq $configuredSchemas -and $rows.ContainsKey('model_details')) { $configuredSchemas = @() }
        if ($configuredSchemas -is [Array]) {
            $allowed = @{}; foreach ($item in $configuredSchemas) { $allowed[(Normalize-Value 'model' 'value' $item.schema_name)] = $true }
            foreach ($entity in @($rows[$entityDataset])) { if ($null -ne $entity -and -not $allowed.ContainsKey((Normalize-Value 'model' 'value' (Get-Property $entity $schemaField)))) { Add-PolicyIssue $issues 'model.entity-schema' $entityDataset $schemaField 'Entity schema must be configured on its Model layer.' } }
        }
        $entities = @($rows[$entityDataset] | Where-Object { $null -ne $_ -and (Get-Active $_) -eq $true })
        $attributes = @($rows[$attributeDataset] | Where-Object { $null -ne $_ -and (Get-Active $_) -eq $true })
        $byEntity = @{}; $submodels = @{}; $newEntities = @{}; $touched = @{}
        foreach ($entity in $entities) { $byEntity[(Get-PolicyTuple @((Get-Property $entity $schemaField), (Get-Property $entity $entityField)))] = $entity }
        foreach ($record in @($rows[$layer + '_submodel'])) { if ($null -ne $record) { $submodels[(Normalize-Value 'model' 'value' (Get-Property $record ($layer + '_submodel_name')))] = $record } }
        foreach ($record in @($added[$entityDataset])) { if ($null -ne $record -and (Get-Active $record) -eq $true) { $newEntities[(Get-PolicyTuple @((Get-Property $record $schemaField), (Get-Property $record $entityField)))] = $true } }
        foreach ($record in @($changed[$entityDataset]) + @($changed[$attributeDataset])) { if ($null -ne $record) { $touched[(Get-PolicyTuple @((Get-Property $record $schemaField), (Get-Property $record $entityField)))] = $true } }
        foreach ($entity in @($changed[$entityDataset])) {
            if ($null -eq $entity) { continue }
            foreach ($membership in (Get-Property $entity 'submodels')) {
                if ($null -eq $membership) { continue }
                $submodel = $submodels[(Normalize-Value 'model' 'value' (Get-Property $membership 'submodel_name'))]
                if ((Get-Property $membership 'membership_status') -ceq 'active' -and ((Get-Active $entity) -ne $true -or (Get-Active $submodel) -ne $true)) { Add-PolicyIssue $issues 'model.membership-state' $entityDataset 'submodels' 'Active membership needs an active Entity and Submodel.' }
            }
        }
        foreach ($attribute in $attributes) {
            $parent = $byEntity[(Get-PolicyTuple @((Get-Property $attribute $schemaField), (Get-Property $attribute $entityField)))]
            if ($null -eq $parent) { continue }
            $parentSources = @{}
            foreach ($source in (Get-Property $parent 'sources')) {
                if ($null -ne $source -and (Get-Active $source) -ne $false -and (Get-Property $source 'source_object')) { $parentSources[(Get-PolicyPhysical $source.source_object)] = $true }
                if ($layer -ceq 'dimensional' -and $null -ne $source -and (Get-Active $source) -ne $false -and (Get-Property $source 'source_logical_entity')) { $logical = $source.source_logical_entity; $parentSources[(Get-PolicyTuple @($logical.logical_entity_schema_name, $logical.logical_entity_name))] = $true }
            }
            foreach ($source in (Get-Property $attribute 'sources')) {
                if ($layer -ceq 'dimensional' -and $null -ne $source -and (Get-Active $source) -ne $false -and (Get-Property $source 'support_source_type') -ceq 'logical_attribute') { $logical = $source.source_logical_attribute; if (-not $parentSources.ContainsKey((Get-PolicyTuple @($logical.logical_entity_schema_name, $logical.logical_entity_name)))) { Add-PolicyIssue $issues 'model.parent-source' $attributeDataset 'sources' 'A Dimensional Attribute''s Logical source requires matching Logical Entity support on its parent.' } }
                if ($null -ne $source -and (Get-Active $source) -ne $false -and (Get-Property $source 'support_source_type') -ceq 'attribute' -and -not $parentSources.ContainsKey((Get-PolicyPhysical (Get-Property $source 'source_attribute')))) { Add-PolicyIssue $issues 'model.parent-source' $attributeDataset 'sources' "An Attribute's physical source requires the matching Object source on its parent Entity." }
            }
        }
        foreach ($name in $byEntity.Keys) {
            if (-not $touched.ContainsKey($name)) { continue }
            $entity = $byEntity[$name]; $ordinalField = $attributeDataset + '_ordinal_position'
            $columns = @($attributes | Where-Object { (Get-PolicyTuple @((Get-Property $_ $schemaField), (Get-Property $_ $entityField))) -ceq $name } | Sort-Object -Property $ordinalField)
            $ordinals = @{}
            foreach ($column in $columns) { $ordinal = [string](Get-Property $column $ordinalField); if ($ordinals.ContainsKey($ordinal)) { Add-PolicyIssue $issues 'model.attribute-order' $attributeDataset $ordinalField 'Active Attributes within an Entity need distinct ordinal positions.'; break }; $ordinals[$ordinal] = $true }
            if (-not $newEntities.ContainsKey($name)) { continue }
            $surrogates = @($columns | Where-Object { if ($layer -ceq 'logical') { Get-Property $_ 'logical_attribute_is_surrogate_key' } else { (Get-Property $_ 'dimensional_attribute_key_role') -ceq 'surrogate' } })
            $surrogate = if ($surrogates.Count -gt 0) { $surrogates[0] } else { $null }
            if ($surrogates.Count -ne 1 -or (Get-Property $surrogate $ordinalField) -ne 1 -or (Get-Property $surrogate ($attributeDataset + '_is_nullable')) -ne $false -or
                (Normalize-Value 'model' 'value' (Get-Property $surrogate ($attributeDataset + '_data_type'))) -cne 'bigint' -or
                @((Get-Property $surrogate 'sources') | Where-Object { $null -ne $_ }).Count -gt 0 -or
                ($layer -ceq 'logical' -and ((Get-Property $surrogate 'logical_attribute_is_natural_key') -or (Get-Property $surrogate 'logical_attribute_is_audit_column')))) {
                Add-PolicyIssue $issues 'model.own-surrogate' $attributeDataset $attributeField 'Every new Entity, including facts and bridges, needs one generated non-null BIGINT own surrogate at ordinal 1 without physical sources.'
            }
            $prefix = if ($layer -ceq 'logical') {'silver'} else {'gold'}
            $naming = Get-Property $details ($prefix + '_model_naming_instructions'); $suffix = if ($layer -ceq 'logical') {'ID'} else {'Key'}
            if ($surrogate -and -not $naming -and -not ([string](Get-Property $surrogate $attributeField)).EndsWith($suffix, [StringComparison]::Ordinal)) { Add-PolicyIssue $issues 'model.key-suffix' $attributeDataset $attributeField "The own surrogate uses the $suffix suffix under the default policy." }
            $template = Get-Property $details ($prefix + '_model_audit_columns_template'); $configured = Get-Property $template 'columns'
            if ($configured -isnot [Array]) { $configured = @('SourceSystemID', 'IsDataValid', 'HashKey', 'IsActive', 'GDSBatchID', 'PipelineRunID', 'CreatedDate', 'UpdatedDate', 'CreatedBy', 'UpdatedBy') | ForEach-Object { [ordered]@{semantic_name = $_} } }
            $expected = @($configured | ForEach-Object { Normalize-Value 'model' 'value' $_.semantic_name })
            $byName = @{}; $actual = New-Object Collections.ArrayList
            foreach ($column in $columns) { $columnName = Normalize-Value 'model' 'value' (Get-Property $column $attributeField); $byName[$columnName] = $column; if ($expected -ccontains $columnName) { [void]$actual.Add($columnName) } }
            if ((ConvertTo-StableJson @($actual)) -cne (ConvertTo-StableJson $expected)) { Add-PolicyIssue $issues 'model.audit-order' $attributeDataset $attributeField 'New Entity audit columns must contain the complete configured audit block in order.' }
            foreach ($specification in $configured) {
                $semantic = Normalize-Value 'model' 'value' $specification.semantic_name; $column = $byName[$semantic]
                if ($null -eq $column) { continue }
                if ((Get-Property $column ($attributeDataset + '_is_audit_column')) -ne $true) { Add-PolicyIssue $issues 'model.audit-role' $attributeDataset $attributeField 'Configured audit columns must be marked as audit columns.' }
                if (((Get-Property $specification 'data_type') -and (Normalize-Value 'model' 'value' (Get-Property $column ($attributeDataset + '_data_type'))) -cne (Normalize-Value 'model' 'value' $specification.data_type)) -or
                    ((Test-Property $specification 'nullable') -and (Get-Property $column ($attributeDataset + '_is_nullable')) -ne $specification.nullable)) { Add-PolicyIssue $issues 'model.audit-template' $attributeDataset $attributeField 'Audit types and nullability must match the configured Model template.' }
                if ($semantic -cne 'sourcesystemid' -and @((Get-Property $column 'sources') | Where-Object { $null -ne $_ }).Count -gt 0) { Add-PolicyIssue $issues 'model.framework-source' $attributeDataset 'sources' 'Framework-populated audit columns have no fabricated physical source lineage.' }
            }
            if (-not $template) { Add-PolicyIssue $issues 'model.audit-template-review' $attributeDataset $attributeField 'The audit names are checked; exact types and nullability need the approved Model template.' 'warning' }
        }
        $byAttribute = @{}
        foreach ($attribute in $attributes) { $byAttribute[(Get-PolicyTuple @((Get-Property $attribute $schemaField), (Get-Property $attribute $entityField), (Get-Property $attribute $attributeField)))] = $attribute }
        foreach ($relation in @($changed[$layer + '_relationship'])) {
            if ($null -eq $relation -or (Get-Active $relation) -ne $true) { continue }
            $endpoints = @(@('from', 'to') | ForEach-Object { $byAttribute[(Get-PolicyTuple @((Get-Property $relation ($_ + '_' + $schemaField)), (Get-Property $relation ($_ + '_' + $entityField)), (Get-Property $relation ($_ + '_' + $attributeField))))] })
            if ($endpoints.Count -eq 2 -and $null -ne $endpoints[0] -and $null -ne $endpoints[1] -and
                (Normalize-Value 'model' 'value' (Get-Property $endpoints[0] ($attributeDataset + '_data_type'))) -cne (Normalize-Value 'model' 'value' (Get-Property $endpoints[1] ($attributeDataset + '_data_type')))) { Add-PolicyIssue $issues 'model.relationship-type' ($layer + '_relationship') ($layer + '_relationship_name') 'Relationship endpoint types differ; resolve an explicit compatible representation before defining the FK.' }
        }
    }
    $physicalObjects = @{}; $physicalAttributes = @{}; $mappingObjects = @{}
    foreach ($state in $MetadataStates) {
        foreach ($record in @($state.Baseline)) {
            if ($state.Dataset.name.EndsWith('_object')) { $physicalObjects[(Get-PolicyPhysical $record)] = $true }
            if ($state.Dataset.name.EndsWith('_attribute')) { $physicalAttributes[(Get-PolicyPhysical $record $true)] = $true }
        }
    }
    $sourceEntities = @{}; $sourceAttributes = @{}
    foreach ($layer in @('logical', 'dimensional')) {
        $sourceEntities[$layer] = @{}; $sourceAttributes[$layer] = @{}
        foreach ($record in @($rows[$layer + '_entity'])) { if ($null -ne $record -and (Get-Active $record) -eq $true) { $sourceEntities[$layer][(Get-PolicyTuple @((Get-Property $record ($layer + '_entity_schema_name')), (Get-Property $record ($layer + '_entity_name'))))] = $true } }
        foreach ($record in @($rows[$layer + '_attribute'])) { if ($null -ne $record -and (Get-Active $record) -eq $true) { $sourceAttributes[$layer][(Get-PolicyTuple @((Get-Property $record ($layer + '_entity_schema_name')), (Get-Property $record ($layer + '_entity_name')), (Get-Property $record ($layer + '_attribute_name'))))] = $true } }
    }
    foreach ($record in @($rows['mapping_object'])) { if ($null -ne $record -and (Get-Active $record) -eq $true) { $mappingObjects[(Get-PolicyTuple @($record.modeled_entity_type, $record.modeled_entity_schema_name, $record.modeled_entity_name, $record.source_system_code))] = $record } }
    foreach ($record in @($changed['mapping_object'])) {
        if ($null -eq $record -or (Get-Active $record) -ne $true -or ((Get-Property $record 'output_template_code') -and $record.output_template_code -cne 'mapping_object_default')) { continue }
        $document = Get-Property $record 'mapping_transformation_document'; if ($null -eq $document) { continue }; $steps = Get-Property $document 'steps'
        if ($steps -isnot [Array] -or -not $steps.Count -or @($steps | Where-Object { $_ -isnot [string] -or [string]::IsNullOrWhiteSpace($_) }).Count -gt 0) { Add-PolicyIssue $issues 'mapping.object-steps' 'mapping_object' 'mapping_transformation_document' 'An active Mapping branch needs concise ordered transformation steps.'; continue }
        $dimensional = $record.modeled_entity_type -ceq 'dimensional_entity'
        if ($dimensional -and $null -ne (Get-Property $document 'source_objects')) { Add-PolicyIssue $issues 'mapping.source-kind' 'mapping_object' 'mapping_transformation_document' 'Dimensional Mapping uses modeled source identities; physical source fields must be null or absent.' }
        if (-not $dimensional -and $null -ne (Get-Property $document 'source_dimensional_entities')) { Add-PolicyIssue $issues 'mapping.source-kind' 'mapping_object' 'mapping_transformation_document' 'Logical Mapping cannot use Dimensional source identities.' }
        $inputFields = if ($dimensional) { @('source_logical_entities', 'source_dimensional_entities') } else { @('source_objects', 'source_logical_entities') }
        $aliases = @{}
        foreach ($inputField in $inputFields) {
            $layer = if ($inputField -ceq 'source_objects') { $null } elseif ($inputField -ceq 'source_logical_entities') { 'logical' } else { 'dimensional' }
            $sourceFields = if ($layer) { @(($layer + '_entity_schema_name'), ($layer + '_entity_name')) } else { @('tenant_code', 'system_code', 'connection_code', 'object_schema', 'object_name') }
            $inputs = Get-Property $document $inputField; if ($null -eq $inputs) { $inputs = @() }
            if ($inputs -isnot [Array]) { Add-PolicyIssue $issues 'mapping.source-objects' 'mapping_object' 'mapping_transformation_document' 'Mapping Entity inputs must be an array or null.'; continue }
            foreach ($source in $inputs) {
                $alias = Get-Property $source 'alias'; $complete = $null -ne $source
                foreach ($field in $sourceFields) { $value = Get-Property $source $field; if ($value -isnot [string] -or [string]::IsNullOrWhiteSpace($value)) { $complete = $false } }
                $normalized = [string](Normalize-Value 'model' 'value' $alias)
                if (-not $complete -or $alias -isnot [string] -or [string]::IsNullOrWhiteSpace($alias) -or $aliases.ContainsKey($normalized)) { Add-PolicyIssue $issues 'mapping.source-alias' 'mapping_object' 'mapping_transformation_document' 'Query inputs need complete source identities and unique nonempty aliases.' }
                $aliases[$normalized] = $true
                $missingSource = if ($layer) { -not $sourceEntities[$layer].ContainsKey((Get-PolicyTuple @((Get-Property $source ($layer + '_entity_schema_name')), (Get-Property $source ($layer + '_entity_name'))))) } else { $MetadataStates.Count -gt 0 -and -not $physicalObjects.ContainsKey((Get-PolicyPhysical $source)) }
                if ($missingSource) { Add-PolicyIssue $issues 'mapping.source-exists' 'mapping_object' 'mapping_transformation_document' 'A Mapping input does not exist in the supplied applied source context.' }
            }
        }
    }
    foreach ($record in @($changed['mapping_attribute'])) {
        if ($null -eq $record -or (Get-Active $record) -ne $true -or ((Get-Property $record 'output_template_code') -and $record.output_template_code -cne 'mapping_attribute_default')) { continue }
        $document = Get-Property $record 'attribute_mapping_transformation_document'; if ($null -eq $document) { continue }; $rule = Get-Property $document 'transformation'
        if ($rule -isnot [string] -or [string]::IsNullOrWhiteSpace($rule)) { Add-PolicyIssue $issues 'mapping.attribute-rule' 'mapping_attribute' 'attribute_mapping_transformation_document' 'Every active mapped Attribute needs an explicit transformation or generated/framework population rule.'; continue }
        $object = $mappingObjects[(Get-PolicyTuple @($record.modeled_entity_type, $record.modeled_entity_schema_name, $record.modeled_entity_name, $record.source_system_code))]
        $dimensional = $record.modeled_entity_type -ceq 'dimensional_entity'
        if ($dimensional -and $null -ne (Get-Property $document 'source_attributes')) { Add-PolicyIssue $issues 'mapping.source-kind' 'mapping_attribute' 'attribute_mapping_transformation_document' 'Dimensional Mapping uses modeled source identities; physical source fields must be null or absent.' }
        if (-not $dimensional -and $null -ne (Get-Property $document 'source_dimensional_attributes')) { Add-PolicyIssue $issues 'mapping.source-kind' 'mapping_attribute' 'attribute_mapping_transformation_document' 'Logical Mapping cannot use Dimensional source identities.' }
        $sourceFields = if ($dimensional) { @('source_logical_attributes', 'source_dimensional_attributes') } else { @('source_attributes', 'source_logical_attributes') }
        foreach ($sourceField in $sourceFields) {
            $layer = if ($sourceField -ceq 'source_attributes') { $null } elseif ($sourceField -ceq 'source_logical_attributes') { 'logical' } else { 'dimensional' }
            $inputField = if ($layer) { 'source_' + $layer + '_entities' } else { 'source_objects' }
            $inputs = Get-Property (Get-Property $object 'mapping_transformation_document') $inputField
            $sources = Get-Property $document $sourceField; if ($null -eq $sources) { $sources = @() }
            if ($sources -isnot [Array]) { Add-PolicyIssue $issues 'mapping.source-attributes' 'mapping_attribute' 'attribute_mapping_transformation_document' 'Mapping Attribute inputs must be an array or null.'; continue }
            foreach ($source in $sources) {
                $missingSource = if ($layer) { -not $sourceAttributes[$layer].ContainsKey((Get-PolicyTuple @((Get-Property $source ($layer + '_entity_schema_name')), (Get-Property $source ($layer + '_entity_name')), (Get-Property $source ($layer + '_attribute_name'))))) } else { $MetadataStates.Count -gt 0 -and -not $physicalAttributes.ContainsKey((Get-PolicyPhysical $source $true)) }
                if ($missingSource) { Add-PolicyIssue $issues 'mapping.attribute-exists' 'mapping_attribute' 'attribute_mapping_transformation_document' 'A Mapping source Attribute does not exist in applied source context.' }
                if ($null -ne (Get-Property $object 'mapping_transformation_document') -and ($inputs -isnot [Array] -or @($inputs | Where-Object { if ($layer) { (Get-PolicyTuple @((Get-Property $_ ($layer + '_entity_schema_name')), (Get-Property $_ ($layer + '_entity_name')))) -ceq (Get-PolicyTuple @((Get-Property $source ($layer + '_entity_schema_name')), (Get-Property $source ($layer + '_entity_name')))) } else { (Get-PolicyPhysical $_) -ceq (Get-PolicyPhysical $source) } }).Count -eq 0)) { Add-PolicyIssue $issues 'mapping.parent-input' 'mapping_attribute' 'attribute_mapping_transformation_document' 'An Attribute source must belong to an Object-level query input in the same System branch.' }
            }
        }
    }
    return @($issues)
}
