# Native modeling evidence review. Authoring digests and structural validation stay independent.
# Pending changes to these datasets bind the optional decision file.
$script:ModelingQualityDatasets = @('logical_entity', 'logical_attribute', 'logical_relationship',
    'analysis_result', 'context_group', 'context_record')

function Read-ModelingEvidenceFile([string]$Session, [string]$Relative, [long]$Limit = 1048576) {
    if ([string]::IsNullOrEmpty($Relative) -or $Relative.Contains('\') -or [IO.Path]::IsPathRooted($Relative) -or
        @($Relative.Split('/') | Where-Object { $_ -ceq '' -or $_ -ceq '.' -or $_ -ceq '..' }).Count -gt 0) {
        Fail 'Modeling evidence path must be relative to the session.'
    }
    $current = $Session
    $parts = $Relative.Split('/')
    for ($index = 0; $index -lt $parts.Count; $index++) {
        $current = Join-Path $current $parts[$index]
        try { $item = Get-Item -LiteralPath $current -Force -ErrorAction Stop }
        catch {
            if ($_.CategoryInfo.Category -eq [Management.Automation.ErrorCategory]::ObjectNotFound) {
                throw [IO.FileNotFoundException]::new('Modeling evidence file is missing.')
            }
            throw
        }
        if (($item.Attributes -band [IO.FileAttributes]::ReparsePoint) -or
            ($index -lt $parts.Count - 1 -and -not $item.PSIsContainer) -or
            ($index -eq $parts.Count - 1 -and $item.PSIsContainer)) {
            Fail 'Modeling evidence must use regular session files.'
        }
        if ($index -eq $parts.Count - 1 -and $item.Length -gt $Limit) { Fail 'Modeling evidence exceeds its byte limit.' }
    }
    $bytes = [IO.File]::ReadAllBytes($current)
    if ($bytes.Length -gt $Limit) { Fail 'Modeling evidence exceeds its byte limit.' }
    $sha = [Security.Cryptography.SHA256]::Create()
    try { $digest = ([BitConverter]::ToString($sha.ComputeHash($bytes))).Replace('-', '').ToLowerInvariant() }
    finally { $sha.Dispose() }
    return [ordered]@{ path = $Relative; sha256 = $digest; bytes = $bytes }
}

function Read-ModelingDecisions([string]$Session, [string]$Task) {
    $relative = '.atlas/tasks/' + $Task + '.evidence/modeling-decisions.json'
    try { $file = Read-ModelingEvidenceFile $Session $relative }
    catch {
        if ($_.Exception.GetBaseException() -is [IO.FileNotFoundException]) {
            return [ordered]@{ decisions = $null; files = @([ordered]@{ path = $relative; sha256 = $null }); noteFiles = @{} }
        }
        throw
    }
    try { $decisions = ConvertFrom-GdsJson ([Text.Encoding]::UTF8.GetString($file.bytes)) }
    catch { Fail 'Modeling decisions must be valid JSON.' }
    $files = New-Object Collections.ArrayList
    [void]$files.Add([ordered]@{ path = $relative; sha256 = $file.sha256 })
    $noteFiles = New-Object 'Collections.Generic.Dictionary[string,object]' ([StringComparer]::Ordinal)
    foreach ($section in @('entities', 'relationships')) {
        $entries = Get-Property $decisions $section
        if ($entries -isnot [Array]) { continue }
        foreach ($entry in $entries) {
            $references = Get-Property $entry 'evidence'
            if ($references -isnot [Array]) { continue }
            foreach ($reference in $references) {
                $notePath = Get-Property $reference 'note'
                if ($notePath -isnot [string] -or $noteFiles.ContainsKey($notePath)) { continue }
                if ($notePath -cnotmatch '\.md$' -or $notePath.StartsWith('.atlas/temp/', [StringComparison]::Ordinal)) {
                    Fail 'Decision notes must be durable workspace Markdown outside .atlas/temp/.'
                }
                try {
                    $note = Read-ModelingEvidenceFile $Session $notePath 65536
                    if ([string]::IsNullOrWhiteSpace([Text.Encoding]::UTF8.GetString($note.bytes))) { Fail 'Decision evidence note is empty.' }
                    $noteFiles[$notePath] = [ordered]@{ sha256 = $note.sha256 }
                    [void]$files.Add([ordered]@{ path = $note.path; sha256 = $note.sha256 })
                }
                catch {
                    if ($_.Exception.GetBaseException() -isnot [IO.FileNotFoundException]) { throw }
                    [void]$files.Add([ordered]@{ path = $notePath; sha256 = $null })
                }
            }
        }
    }
    return [ordered]@{ decisions = $decisions; files = @($files); noteFiles = $noteFiles }
}

function Get-ModelingQuality($States, $Decisions, $NoteFiles = @{}, $MetadataStates = @()) {
    $objectFields = @('tenant_code', 'system_code', 'connection_code', 'object_schema', 'object_name')
    $qualityDatasets = @($script:ModelingQualityDatasets) + @('project_input_scope', 'subject_area', 'subject_area_table')
    $errors = New-Object Collections.ArrayList
    $warnings = New-Object Collections.ArrayList
    $notes = New-Object 'Collections.Generic.HashSet[string]' ([StringComparer]::Ordinal)
    $rows = [ordered]@{}
    $definitions = @{}
    $indexes = @{}
    $changes = @{}
    function Add-QIssue($List, $Code, $Dataset, $Key, $Message) {
        [void]$List.Add([ordered]@{ code = $Code; dataset = $Dataset; key = $Key; message = $Message })
    }
    function Get-QRows($Dataset) { if ($rows.Contains($Dataset)) { return $rows[$Dataset] } }
    function Get-QKey($Dataset, $Record) { return Get-CanonicalKey 'project' $definitions[$Dataset] $Record }
    function Get-QKeyObject($Dataset, $Record) {
        $result = [ordered]@{}
        foreach ($field in $definitions[$Dataset].canonical_key) { $result[$field] = Get-Property $Record $field }
        return $result
    }
    function Get-QTuple($Values) {
        $normalized = New-Object Collections.ArrayList
        foreach ($value in $Values) { [void]$normalized.Add((Normalize-Value 'project' 'value' $value)) }
        return ConvertTo-StableJson @($normalized)
    }
    function Get-QLogicalIdentity($Record, [string]$Prefix = '') {
        return Get-QTuple @((Get-Property $Record ($Prefix + 'logical_entity_schema_name')), (Get-Property $Record ($Prefix + 'logical_entity_name')))
    }
    function Get-QPhysical($Record, [bool]$Attribute = $false, [string]$Prefix = '') {
        $fields = @($objectFields)
        if ($Attribute) { $fields += 'attribute_name' }
        $values = foreach ($field in $fields) { Get-Property $Record ($Prefix + $field) }
        return Get-QTuple @($values)
    }
    function Get-QSupports($Record) {
        $set = New-Object 'Collections.Generic.HashSet[string]' ([StringComparer]::Ordinal)
        $sources = Get-Property $Record 'sources'
        foreach ($source in $sources) {
            if ((Get-Active $source) -eq $true -and (Get-Property $source 'support_source_type') -ceq 'object') {
                [void]$set.Add((Get-QPhysical (Get-Property $source 'source_object')))
            }
        }
        return ,$set
    }
    function Get-QLineage($Attribute) {
        $set = New-Object 'Collections.Generic.HashSet[string]' ([StringComparer]::Ordinal)
        $sources = Get-Property $Attribute 'sources'
        foreach ($source in $sources) {
            if ((Get-Active $source) -eq $true -and (Get-Property $source 'support_source_type') -ceq 'attribute') {
                [void]$set.Add((Get-QPhysical (Get-Property $source 'source_attribute') $true))
            }
        }
        return ,$set
    }
    function Test-QObject($Value) {
        return $null -ne $Value -and $Value -isnot [Array] -and $Value -isnot [string] -and $Value -isnot [ValueType]
    }
    function Test-QFields($Value, $Fields) {
        if (-not (Test-QObject $Value) -or @(Get-PropertyNames $Value).Count -ne $Fields.Count) { return $false }
        foreach ($field in $Fields) { if (-not (Test-Property $Value $field)) { return $false } }
        return $true
    }
    function Get-QSorted($Values) {
        [string[]]$sorted = @($Values)
        [Array]::Sort($sorted, [StringComparer]::Ordinal)
        return $sorted
    }
    function New-QInvalidInput($Dataset) {
        return [ordered]@{
            required = $true; status = 'needs_evidence'
            errors = @([ordered]@{ code = 'project_quality_input_invalid'; dataset = $Dataset; key = $null; message = 'Fix structural validation errors before reviewing quality: modeling records need complete, nonblank canonical keys and valid record arrays.' })
            warnings = @(); error_count = 1; warning_count = 0; truncated = $false; metrics = [ordered]@{}
            template = [ordered]@{ schema_version = '1.0'; entities = @(); relationships = @() }; note_paths = @()
        }
    }
    if ($null -eq $States) { return New-QInvalidInput 'project' }
    foreach ($state in $States) {
        $dataset = [string]$state.Dataset.name
        if ($qualityDatasets -cnotcontains $dataset) { continue }
        $fields = Get-Property $state.Dataset 'canonical_key'
        if ($fields -isnot [Array] -or $fields.Count -eq 0 -or @($fields | Where-Object { $_ -isnot [string] }).Count -gt 0) { return New-QInvalidInput $dataset }
        foreach ($member in @('Baseline', 'Pending', 'Effective')) {
            if (-not (Test-Property $state $member)) { continue }
            $records = Get-Property $state $member
            if ($records -isnot [Array]) { return New-QInvalidInput $dataset }
            foreach ($record in $records) {
                if (-not (Test-QObject $record)) { return New-QInvalidInput $dataset }
                foreach ($field in $fields) {
                    $value = Get-Property $record $field
                    if ($value -isnot [string] -or [string]::IsNullOrWhiteSpace($value)) { return New-QInvalidInput $dataset }
                }
                if (Test-Property $record 'sources') {
                    $sources = Get-Property $record 'sources'
                    if ($sources -isnot [Array] -or @($sources | Where-Object { -not (Test-QObject $_) }).Count -gt 0) { return New-QInvalidInput $dataset }
                }
            }
        }
        $effective = if (Test-Property $state 'Effective') { Get-Property $state 'Effective' } else { Get-Property $state 'Baseline' }
        $rows[$dataset] = @($effective)
        $definitions[$dataset] = $state.Dataset
        $baseline = @{}
        $baselineRecords = Get-Property $state 'Baseline'
        foreach ($record in $baselineRecords) { $baseline[(Get-QKey $dataset $record)] = $record }
        $indexes[$dataset] = @{}
        foreach ($record in $effective) { $indexes[$dataset][(Get-QKey $dataset $record)] = $record }
        $changed = New-Object Collections.ArrayList
        $pendingRecords = Get-Property $state 'Pending'
        foreach ($record in $pendingRecords) {
            $key = Get-QKey $dataset $record
            if (-not $baseline.ContainsKey($key) -or (ConvertTo-StableJson $baseline[$key]) -cne (ConvertTo-StableJson $record)) {
                [void]$changed.Add($record)
            }
        }
        $changes[$dataset] = @($changed)
    }
    foreach ($analysis in @(Get-QRows 'analysis_result' | Where-Object { (Get-Active $_) -eq $true })) {
        $inferred = Get-Property $analysis 'inferred_cardinality'
        if (@('one_to_one', 'one_to_many', 'many_to_one', 'many_to_many') -cnotcontains $inferred) { continue }
        $counts = @(@('source_non_null', 'source_distinct', 'target_non_null', 'target_distinct',
            'source_missing_target', 'unused_target', 'duplicate_target_key') | ForEach-Object { Get-Property $analysis ('validation_' + $_ + '_count') })
        $validCounts = $counts.Count -eq 7
        foreach ($count in $counts) { if (-not (Test-SafeJsonInteger $count $true)) { $validCounts = $false } }
        $policy = Get-Property $analysis 'validation_policy_version'
        if (-not $validCounts -or $policy -isnot [string] -or $policy -cnotmatch '^\d+\.\d+\.\d+$') { continue }
        $sourceCount, $sourceDistinct, $targetCount, $targetDistinct, $missing, $unused, $duplicates = $counts
        $expected = if ($missing -eq 0 -and $duplicates -eq 0) { 'supported' } else { 'unsupported' }
        if ($sourceCount -le 0 -or $targetCount -le 0 -or $sourceDistinct -le 0 -or $targetDistinct -le 0 -or
            $sourceDistinct -gt $sourceCount -or $targetDistinct -gt $targetCount -or $missing -gt $sourceDistinct -or $unused -gt $targetDistinct -or
            ($sourceDistinct - $missing) -ne ($targetDistinct - $unused) -or $duplicates -ne ($targetCount - $targetDistinct) -or
            (Get-Property $analysis 'validation_result') -cne $expected) { continue }
        $sourceMultiplicity = if ($sourceCount -gt $sourceDistinct) { 'many' } else { 'one' }
        $targetMultiplicity = if ($targetCount -gt $targetDistinct) { 'many' } else { 'one' }
        if ($inferred -cne ($sourceMultiplicity + '_to_' + $targetMultiplicity)) {
            Add-QIssue $warnings 'analysis_inferred_cardinality_mismatch' 'analysis_result' (Get-QKeyObject 'analysis_result' $analysis) 'Inferred cardinality differs from measured endpoint uniqueness. Review population scope and grain; preserve both conclusions.'
        }
    }
    $entities = @(Get-QRows 'logical_entity' | Where-Object { (Get-Active $_) -eq $true })
    $attributes = @(Get-QRows 'logical_attribute' | Where-Object { (Get-Active $_) -eq $true })
    $logical = @(Get-QRows 'logical_relationship' | Where-Object { (Get-Active $_) -eq $true })
    $entityNames = @{}
    $attributesByEntity = @{}
    $attributeIndex = @{}
    foreach ($record in $entities) {
        $name = Get-QLogicalIdentity $record
        $entityNames[$name] = $record
        $attributesByEntity[$name] = New-Object Collections.ArrayList
    }
    foreach ($record in $attributes) {
        $name = Get-QLogicalIdentity $record
        if ($attributesByEntity.ContainsKey($name)) { [void]$attributesByEntity[$name].Add($record) }
        $attributeIndex[(Get-QTuple @($record.logical_entity_schema_name, $record.logical_entity_name, $record.logical_attribute_name))] = $record
    }
    function Get-QEntityAttributes($Record, [string]$Prefix = '') {
        $normalized = Get-QLogicalIdentity $Record $Prefix
        if ($attributesByEntity.ContainsKey($normalized)) { return $attributesByEntity[$normalized] }
    }
    function Get-QEndpointLineage($Relationship, $Endpoint) {
        $entity = Get-Property $Relationship ($Endpoint + '_logical_entity_name')
        $name = Get-Property $Relationship ($Endpoint + '_logical_attribute_name')
        $schema = Get-Property $Relationship ($Endpoint + '_logical_entity_schema_name')
        $attribute = $attributeIndex[(Get-QTuple @($schema, $entity, $name))]
        if (Get-Property $attribute 'logical_attribute_is_surrogate_key') {
            $set = New-Object 'Collections.Generic.HashSet[string]' ([StringComparer]::Ordinal)
            foreach ($candidate in @(Get-QEntityAttributes $Relationship ($Endpoint + '_'))) {
                if (Get-Property $candidate 'logical_attribute_is_natural_key') {
                    foreach ($source in (Get-QLineage $candidate)) { [void]$set.Add($source) }
                }
            }
            return ,$set
        }
        return ,(Get-QLineage $attribute)
    }
    function Get-QAnalysisAlignment($Relationship, $Analysis) {
        $from = Get-QEndpointLineage $Relationship 'from'
        $to = Get-QEndpointLineage $Relationship 'to'
        $source = Get-QPhysical $Analysis $true 'from_'
        $target = Get-QPhysical $Analysis $true 'to_'
        if ($from.Contains($source) -and $to.Contains($target)) { return 'forward' }
        if ($from.Contains($target) -and $to.Contains($source)) { return 'reverse' }
        return $null
    }
    $affected = @{}
    foreach ($dataset in @('logical_entity', 'logical_relationship')) {
        $affected[$dataset] = New-Object 'Collections.Generic.HashSet[string]' ([StringComparer]::Ordinal)
    }
    function Add-QAffectedRelationship($Record) {
        [void]$affected.logical_relationship.Add((Get-QKey 'logical_relationship' $Record))
        foreach ($endpoint in @('from', 'to')) {
            [void]$affected.logical_entity.Add((Get-QLogicalIdentity $Record ($endpoint + '_')))
        }
    }
    foreach ($dataset in @('logical_entity', 'logical_attribute')) {
        foreach ($record in $changes[$dataset]) { [void]$affected.logical_entity.Add((Get-QLogicalIdentity $record)) }
    }
    foreach ($record in $changes['logical_relationship']) { Add-QAffectedRelationship $record }
    $changedEvidence = New-Object 'Collections.Generic.HashSet[string]' ([StringComparer]::Ordinal)
    foreach ($dataset in @('analysis_result', 'context_record', 'context_group')) {
        foreach ($record in $changes[$dataset]) { [void]$changedEvidence.Add($dataset + ':' + (Get-QKey $dataset $record)) }
    }
    function Test-QReferencesChanged($Entry) {
        $references = Get-Property $Entry 'evidence'
        if ($references -isnot [Array]) { return $false }
        foreach ($reference in $references) {
            $dataset = Get-Property $reference 'dataset'
            $recordKey = Get-Property $reference 'key'
            if ($null -eq $dataset -or -not $indexes.ContainsKey($dataset) -or -not (Test-QObject $recordKey)) { continue }
            try {
                $identity = Get-QKey $dataset $recordKey
                if ($changedEvidence.Contains($dataset + ':' + $identity)) { return $true }
                $context = $indexes[$dataset][$identity]
                if ($dataset -ceq 'context_record' -and $null -ne $context -and
                    $changedEvidence.Contains('context_group:' + (Get-QKey 'context_group' $context))) { return $true }
            }
            catch { continue }
        }
        return $false
    }
    $affectedEntitySeeds = New-Object 'Collections.Generic.HashSet[string]' ([StringComparer]::Ordinal)
    foreach ($name in $affected.logical_entity) { [void]$affectedEntitySeeds.Add($name) }
    foreach ($record in $logical) {
        $cited = $null
        $decisionRelationships = Get-Property $Decisions 'relationships'
        if ($decisionRelationships -is [Array]) {
            foreach ($entry in $decisionRelationships) {
                try {
                    if ((Get-Property $entry 'dataset') -ceq 'logical_relationship' -and
                        (Get-QKey 'logical_relationship' (Get-Property $entry 'key')) -ceq (Get-QKey 'logical_relationship' $record)) { $cited = $entry; break }
                }
                catch { continue }
            }
        }
        $isAffected = $false
        foreach ($endpoint in @('from', 'to')) {
            if ($affectedEntitySeeds.Contains((Get-QLogicalIdentity $record ($endpoint + '_')))) { $isAffected = $true }
        }
        foreach ($analysis in $changes['analysis_result']) {
            if (Get-QAnalysisAlignment $record $analysis) { $isAffected = $true; break }
        }
        if ($isAffected -or (Test-QReferencesChanged $cited)) { Add-QAffectedRelationship $record }
    }
    $decisionEntities = Get-Property $Decisions 'entities'
    if ($decisionEntities -is [Array]) {
        foreach ($entry in $decisionEntities) {
            if ((Get-Property $entry 'dataset') -ceq 'logical_entity' -and (Test-QReferencesChanged $entry)) {
                [void]$affected.logical_entity.Add((Get-QLogicalIdentity (Get-Property $entry 'key')))
            }
        }
    }
    $templateEntities = New-Object Collections.ArrayList
    $templateRelationships = New-Object Collections.ArrayList
    foreach ($record in $entities) {
        if (-not $affected.logical_entity.Contains((Get-QLogicalIdentity $record))) { continue }
        $natural = @(Get-QEntityAttributes $record | Where-Object { Get-Property $_ 'logical_attribute_is_natural_key' })
        $identityMode = if ($natural.Count -gt 0) { 'natural' } else { 'append_only' }
        [void]$templateEntities.Add([ordered]@{
            dataset = 'logical_entity'; key = Get-QKeyObject 'logical_entity' $record
            identity_attributes = @($natural | ForEach-Object { $_.logical_attribute_name }); identity_mode = $identityMode
            decision = ''; evidence = @()
        })
    }
    foreach ($record in $logical) {
        if ($affected.logical_relationship.Contains((Get-QKey 'logical_relationship' $record))) {
            [void]$templateRelationships.Add([ordered]@{ dataset = 'logical_relationship'; key = Get-QKeyObject 'logical_relationship' $record; evidence = @(); decision = '' })
        }
    }
    $template = [ordered]@{ schema_version = '1.0'; entities = @($templateEntities); relationships = @($templateRelationships) }
    $required = $templateEntities.Count -gt 0 -or $templateRelationships.Count -gt 0
    $adjacency = [ordered]@{}
    foreach ($record in $entities) { $adjacency[(Get-QLogicalIdentity $record)] = New-Object 'Collections.Generic.HashSet[string]' ([StringComparer]::Ordinal) }
    $selfEdges = 0
    $crossEdges = 0
    foreach ($relationship in $logical) {
        $from = Get-QLogicalIdentity $relationship 'from_'
        $to = Get-QLogicalIdentity $relationship 'to_'
        if ($from -ceq $to) { $selfEdges++ }
        else {
            $crossEdges++
            if ($adjacency.Contains($from)) { [void]$adjacency[$from].Add($to) }
            if ($adjacency.Contains($to)) { [void]$adjacency[$to].Add($from) }
        }
    }
    $components = New-Object Collections.ArrayList
    $visited = New-Object 'Collections.Generic.HashSet[string]' ([StringComparer]::Ordinal)
    foreach ($name in $adjacency.Keys) {
        if ($visited.Contains($name)) { continue }
        $component = New-Object Collections.ArrayList
        $queue = New-Object Collections.ArrayList
        [void]$queue.Add($name)
        while ($queue.Count -gt 0) {
            $next = [string]$queue[$queue.Count - 1]
            $queue.RemoveAt($queue.Count - 1)
            if ($visited.Contains($next) -or -not $adjacency.Contains($next)) { continue }
            [void]$visited.Add($next)
            [void]$component.Add($entityNames[$next].logical_entity_schema_name + '.' + $entityNames[$next].logical_entity_name)
            foreach ($neighbor in $adjacency[$next]) { [void]$queue.Add($neighbor) }
        }
        [void]$components.Add(@(Get-QSorted @($component)))
    }
    $business = @($attributes | Where-Object { -not (Get-Property $_ 'logical_attribute_is_audit_column') -and -not (Get-Property $_ 'logical_attribute_is_surrogate_key') })
    $singleSource = @($business | Where-Object { (Get-QLineage $_).Count -eq 1 }).Count
    $singleObject = @($entities | Where-Object { (Get-QSupports $_).Count -eq 1 }).Count
    $logicalSourceObjects = New-Object 'Collections.Generic.HashSet[string]' ([StringComparer]::Ordinal)
    foreach ($record in $entities) { foreach ($source in (Get-QSupports $record)) { [void]$logicalSourceObjects.Add($source) } }
    $isolatedEntities = @($entities | Where-Object { $adjacency[(Get-QLogicalIdentity $_)].Count -eq 0 } | ForEach-Object { $_.logical_entity_schema_name + '.' + $_.logical_entity_name })
    $entitiesWithoutNaturalKey = @($entities | Where-Object { @(Get-QEntityAttributes $_ | Where-Object { Get-Property $_ 'logical_attribute_is_natural_key' }).Count -eq 0 } | ForEach-Object { $_.logical_entity_schema_name + '.' + $_.logical_entity_name })
    $componentExamples = New-Object Collections.ArrayList
    $remainingComponentNames = 200
    foreach ($component in $components) {
        if ($remainingComponentNames -eq 0) { break }
        $example = @($component | Select-Object -First $remainingComponentNames)
        [void]$componentExamples.Add($example)
        $remainingComponentNames -= $example.Count
    }
    $metadataAttributes = @{}
    $bronzeObjects = New-Object 'Collections.Generic.HashSet[string]' ([StringComparer]::Ordinal)
    foreach ($state in $MetadataStates) {
        $metadataRecords = if (Test-Property $state 'Effective') { Get-Property $state 'Effective' } else { Get-Property $state 'Baseline' }
        foreach ($record in $metadataRecords) {
            if ((Get-Property $record 'attribute_name') -and (Get-Property $record 'attribute_inferred_data_type')) { $metadataAttributes[(Get-QPhysical $record $true)] = $record }
            elseif (-not (Get-Property $record 'attribute_name') -and (Normalize-Value 'project' 'value' (Get-Property $record 'zone_code')) -ceq 'bronze') { [void]$bronzeObjects.Add((Get-QPhysical $record)) }
        }
    }
    # Subject Areas are optional focus windows over Input Scope Objects, never modeling evidence.
    # Once a Project has an active area, an active Bronze Input Scope Object outside every active
    # area is unassigned. Builds work one area at a time, so each area also reports how many of its
    # Objects are shared with another area and already support an active Logical Entity.
    $subjectAreas = @(Get-QRows 'subject_area' | Where-Object { (Get-Active $_) -eq $true })
    $areaObjects = @{}
    foreach ($record in $subjectAreas) { $areaObjects[(Normalize-Value 'project' 'value' (Get-Property $record 'subject_area_name'))] = New-Object 'Collections.Generic.HashSet[string]' ([StringComparer]::Ordinal) }
    $assignedTables = New-Object 'Collections.Generic.HashSet[string]' ([StringComparer]::Ordinal)
    foreach ($record in @(Get-QRows 'subject_area_table')) {
        $areaName = Normalize-Value 'project' 'value' (Get-Property $record 'subject_area_name')
        if ((Get-Active $record) -ne $true -or -not $areaObjects.ContainsKey($areaName)) { continue }
        [void]$assignedTables.Add((Get-QPhysical $record))
        [void]$areaObjects[$areaName].Add((Get-QPhysical $record))
    }
    $objectAreas = @{}
    foreach ($objects in $areaObjects.Values) { foreach ($object in $objects) { $objectAreas[$object] = 1 + [int]$objectAreas[$object] } }
    $unassignedTables = @()
    if ($subjectAreas.Count -gt 0) {
        $unassignedTables = @(Get-QRows 'project_input_scope' | Where-Object {
            (Get-Active $_) -eq $true -and $bronzeObjects.Contains((Get-QPhysical $_)) -and -not $assignedTables.Contains((Get-QPhysical $_)) })
    }
    $emptyAreas = @($subjectAreas | Where-Object { $areaObjects[(Normalize-Value 'project' 'value' (Get-Property $_ 'subject_area_name'))].Count -eq 0 })
    # Same default order as the web Build dialog: most shared Objects first, then larger areas, then name.
    $areaSummaries = New-Object Collections.ArrayList
    foreach ($record in $subjectAreas) {
        $objects = $areaObjects[(Normalize-Value 'project' 'value' (Get-Property $record 'subject_area_name'))]
        $shared = 0; $modeled = 0
        foreach ($object in $objects) {
            if ($objectAreas[$object] -gt 1) { $shared++ }
            if ($logicalSourceObjects.Contains($object)) { $modeled++ }
        }
        [void]$areaSummaries.Add([ordered]@{ subject_area_name = Get-Property $record 'subject_area_name'; object_count = $objects.Count; shared_object_count = $shared; modeled_object_count = $modeled })
    }
    $areaSummaries = Get-AtlasSortedRecords @($areaSummaries) {
        param($a, $b)
        $order = [Math]::Sign([long]$b.shared_object_count - [long]$a.shared_object_count)
        if ($order -ne 0) { return $order }
        $order = [Math]::Sign([long]$b.object_count - [long]$a.object_count)
        if ($order -ne 0) { return $order }
        return Compare-AtlasCodePoints (Normalize-Value 'project' 'value' $a.subject_area_name) (Normalize-Value 'project' 'value' $b.subject_area_name)
    }
    $metrics = [ordered]@{
        logical_entities = $entities.Count
        logical_relationships = $logical.Count; cross_entity_relationships = $crossEdges; self_relationships = $selfEdges
        connected_components = $components.Count; components = @($componentExamples)
        isolated_entity_count = $isolatedEntities.Count; isolated_entities = @($isolatedEntities | Select-Object -First 200)
        logical_physical_support_objects = $logicalSourceObjects.Count; single_object_entities = $singleObject
        entity_source_support_ratio = [ordered]@{ numerator = $singleObject; denominator = $entities.Count }
        business_attributes = $business.Count; single_source_business_attributes = $singleSource
        single_source_attribute_ratio = [ordered]@{ numerator = $singleSource; denominator = $business.Count }
        audit_attributes = @($attributes | Where-Object { Get-Property $_ 'logical_attribute_is_audit_column' }).Count
        surrogate_attributes = @($attributes | Where-Object { Get-Property $_ 'logical_attribute_is_surrogate_key' }).Count
        framework_attributes = @($attributes | Where-Object { (Get-Property $_ 'logical_attribute_is_audit_column') -or (Get-Property $_ 'logical_attribute_is_surrogate_key') }).Count
        active_attributes = $attributes.Count
        entities_without_natural_key_count = $entitiesWithoutNaturalKey.Count
        entities_without_natural_key = @($entitiesWithoutNaturalKey | Select-Object -First 200)
        subject_areas = $subjectAreas.Count
        unassigned_table_count = $unassignedTables.Count
        unassigned_tables = @($unassignedTables | Select-Object -First 200 | ForEach-Object { Get-QKeyObject 'project_input_scope' $_ })
        empty_subject_area_count = $emptyAreas.Count
        empty_subject_areas = @($emptyAreas | Select-Object -First 200 | ForEach-Object { Get-Property $_ 'subject_area_name' })
        subject_area_summaries = @($areaSummaries | Select-Object -First 200)
        metric_examples_truncated = $entities.Count -gt 200 -or $isolatedEntities.Count -gt 200 -or $entitiesWithoutNaturalKey.Count -gt 200 -or
            $unassignedTables.Count -gt 200 -or $emptyAreas.Count -gt 200 -or $areaSummaries.Count -gt 200
    }
    if ($entities.Count -gt 0 -and $singleObject -eq $entities.Count -and $singleSource -eq $business.Count) {
        Add-QIssue $warnings 'source_shaped_project' 'logical_entity' $null 'All Entities have one physical Object support and all business Attributes have one physical source. Review grain and dependencies; this does not prove copying or require splitting.'
    }
    if ($metrics.isolated_entities.Count -gt 0) {
        Add-QIssue $warnings 'isolated_entities' 'logical_entity' $null 'Some Entities have no cross-entity relationship. Ask the user whether they are intentionally standalone or a supported relationship is missing; do not invent joins.'
    }
    if ($metrics.connected_components -gt 1) {
        Add-QIssue $warnings 'disconnected_components' 'logical_entity' $null 'Logical Entities form separate connected groups. Ask the user whether these groups are intentionally separate or evidence supports a relationship between them; do not invent joins.'
    }
    if ($unassignedTables.Count -gt 0) {
        Add-QIssue $warnings 'unassigned_tables' 'subject_area_table' $null 'Some active Bronze Input Scope Objects are in no active Subject Area. Place each one in an area or report why it stays unassigned.'
    }
    if ($emptyAreas.Count -gt 0) {
        Add-QIssue $warnings 'empty_subject_areas' 'subject_area' $null 'Some active Subject Areas have no active Object. Add their Objects or retire the empty areas.'
    }
    foreach ($attribute in $business) {
        $dataType = Get-Property $attribute 'logical_attribute_data_type'
        $decimal = [regex]::Match([string]$dataType, '^DECIMAL\s*\(\s*([0-9]+)\s*,\s*([0-9]+)\s*\)$', [Text.RegularExpressions.RegexOptions]::IgnoreCase)
        if ($decimal.Success -and [double]$decimal.Groups[1].Value -eq [double]$decimal.Groups[2].Value) {
            Add-QIssue $warnings 'decimal_zero_integer_capacity' 'logical_attribute' (Get-QKeyObject 'logical_attribute' $attribute) 'DECIMAL precision equals scale; values of 1 or greater cannot fit. Confirm business capacity.'
        }
        foreach ($source in (Get-QLineage $attribute)) {
            if ($metadataAttributes.ContainsKey($source) -and
                (Normalize-Value 'project' 'value' $metadataAttributes[$source].attribute_inferred_data_type) -cne (Normalize-Value 'project' 'value' $dataType)) {
                Add-QIssue $warnings 'type_divergence' 'logical_attribute' (Get-QKeyObject 'logical_attribute' $attribute) 'The modeled type differs from current inferred Metadata. Review conversion evidence; divergence can be intentional.'
                break
            }
        }
    }
    $hasDecisions = $null -ne $Decisions
    if ($required -and -not $hasDecisions) { Add-QIssue $warnings 'decision_review_required' 'project' $null 'Review modeled definitions, identity and relationship basis against the available evidence. A separate decision file is optional.' }
    if ($required -and $hasDecisions) {
        if (-not (Test-QFields $Decisions @('schema_version', 'entities', 'relationships')) -or
            (Get-Property $Decisions 'schema_version') -cne '1.0' -or
            (Get-Property $Decisions 'entities') -isnot [Array] -or (Get-Property $Decisions 'relationships') -isnot [Array]) {
            Add-QIssue $errors 'decisions_missing_or_invalid' 'project' $null 'Provide schema_version 1.0 and the two entity/relationship decision arrays; metrics and pass flags are computed.'
        }
        $found = @{}
        foreach ($section in @('entities', 'relationships')) {
            $entries = Get-Property $Decisions $section
            if ($entries -isnot [Array]) { continue }
            foreach ($entry in $entries) {
                $allowed = if ($section -ceq 'entities') { 'logical_entity' } else { 'logical_relationship' }
                $dataset = Get-Property $entry 'dataset'
                $fields = @('dataset', 'key', 'decision', 'evidence')
                if ($dataset -ceq 'logical_entity') { $fields += @('identity_attributes', 'identity_mode') }
                $entryKey = Get-Property $entry 'key'
                if ($dataset -cne $allowed -or -not (Test-QFields $entry $fields) -or
                    -not $indexes.ContainsKey($dataset) -or -not (Test-QFields $entryKey $definitions[$dataset].canonical_key)) {
                    $issueDataset = if ($dataset) { $dataset } else { 'project' }
                    Add-QIssue $errors 'decision_invalid' $issueDataset $entryKey 'Decision fields or canonical key are invalid.'
                    continue
                }
                $recordKey = Get-QKey $dataset $entryKey
                $identity = $dataset + ':' + $recordKey
                $record = $indexes[$dataset][$recordKey]
                if ($found.ContainsKey($identity)) { Add-QIssue $errors 'decision_duplicate' $dataset $entryKey 'Provide one decision for this canonical key.' }
                $found[$identity] = $entry
                if ($null -eq $record -or (Get-Active $record) -ne $true) {
                    Add-QIssue $errors 'decision_unknown' $dataset $entryKey 'Decision does not identify an active effective record.'
                    continue
                }
                $decision = Get-Property $entry 'decision'
                if ($decision -isnot [string] -or [string]::IsNullOrWhiteSpace($decision) -or $decision.Length -gt 8000) {
                    Add-QIssue $errors 'decision_missing' $dataset $entryKey 'Explain the identity/dependency decision in 1 to 8000 characters; its presence does not prove correctness.'
                }
                $evidenceReferences = Get-Property $entry 'evidence'
                if ($evidenceReferences -isnot [Array] -or $evidenceReferences.Count -eq 0) {
                    Add-QIssue $errors 'evidence_missing' $dataset $entryKey 'Cite existing evidence for this decision.'
                }
                $contextEvidence = $false
                $noteEvidence = $false
                $compositeAnalysis = $false
                $evidenceSeen = New-Object 'Collections.Generic.HashSet[string]' ([StringComparer]::Ordinal)
                if ($evidenceReferences -is [Array]) {
                    foreach ($reference in $evidenceReferences) {
                        $referenceIdentity = ConvertTo-StableJson $reference
                        if ($evidenceSeen.Contains($referenceIdentity)) { Add-QIssue $errors 'evidence_duplicate' $dataset $entryKey 'Duplicate evidence reference.' }
                        [void]$evidenceSeen.Add($referenceIdentity)
                        if (Test-QFields $reference @('note')) {
                            $name = Get-Property $reference 'note'
                            if ($name -isnot [string] -or -not $name.EndsWith('.md', [StringComparison]::Ordinal) -or
                                $name.StartsWith('/') -or $name.Contains('\') -or $name.Contains(':') -or $name.StartsWith('.atlas/temp/', [StringComparison]::Ordinal) -or $name -match '[\x00-\x1f\x7f]' -or
                                @($name.Split('/') | Where-Object { $_ -ceq '' -or $_ -ceq '.' -or $_ -ceq '..' }).Count -gt 0) {
                                Add-QIssue $errors 'note_invalid' $dataset $entryKey 'Evidence note must be a session-relative Markdown path.'
                            }
                            else {
                                [void]$notes.Add($name)
                                $noteEvidence = $null -ne $NoteFiles -and $NoteFiles.ContainsKey($name)
                                if ($section -ceq 'relationships') { Add-QIssue $warnings 'relationship_inferred' $dataset $entryKey 'Relationship decision cites a retained business/metadata inference note, not SQL measurement.' }
                                if ($null -eq $NoteFiles -or -not $NoteFiles.ContainsKey($name)) {
                                    Add-QIssue $errors 'note_missing' $dataset $entryKey 'Referenced sanitized evidence note is missing.'
                                }
                            }
                            continue
                        }
                        $evidenceDataset = Get-Property $reference 'dataset'
                        $evidenceKey = Get-Property $reference 'key'
                        if (-not (Test-QFields $reference @('dataset', 'key')) -or
                            @('analysis_result', 'context_record') -cnotcontains $evidenceDataset -or
                            -not $indexes.ContainsKey($evidenceDataset) -or
                            -not (Test-QFields $evidenceKey $definitions[$evidenceDataset].canonical_key)) {
                            Add-QIssue $errors 'evidence_invalid' $dataset $entryKey 'Use an existing Analysis/Context canonical key or a retained inference note.'
                            continue
                        }
                        $evidence = $indexes[$evidenceDataset][(Get-QKey $evidenceDataset $evidenceKey)]
                        if ($null -eq $evidence -or (Get-Active $evidence) -ne $true) {
                            Add-QIssue $errors 'evidence_inactive_or_missing' $dataset $entryKey 'Evidence must identify an active effective record.'
                            continue
                        }
                        if ($evidenceDataset -ceq 'context_record') {
                            $document = $null
                            foreach ($candidate in @(Get-QRows 'context_group')) {
                                if ((Normalize-Value 'project' 'value' $candidate.context_group_name) -ceq
                                    (Normalize-Value 'project' 'value' $evidence.context_group_name)) { $document = $candidate; break }
                            }
                            if ($null -eq $document -or (Get-Active $document) -ne $true) {
                                Add-QIssue $errors 'context_not_applicable' $dataset $entryKey 'Context requires an active group.'
                            }
                            else { $contextEvidence = $true }
                        }
                        else {
                            $counts = New-Object Collections.ArrayList
                            foreach ($name in @('source_non_null', 'source_distinct', 'target_non_null', 'target_distinct', 'source_missing_target', 'unused_target', 'duplicate_target_key')) {
                                [void]$counts.Add((Get-Property $evidence ('validation_' + $name + '_count')))
                            }
                            $sourceCount, $sourceDistinct, $targetCount, $targetDistinct, $missing, $unused, $duplicates = @($counts)
                            $supported = [string](Get-Property $evidence 'validation_policy_version') -cmatch '^[0-9]+\.[0-9]+\.[0-9]+$' -and
                                (Get-Property $evidence 'validation_result') -ceq 'supported' -and
                                @($counts | Where-Object { -not (Test-SafeJsonInteger $_ $true) }).Count -eq 0 -and
                                $sourceCount -gt 0 -and $targetCount -gt 0 -and $sourceDistinct -gt 0 -and $targetDistinct -gt 0 -and
                                $sourceDistinct -le $sourceCount -and $targetDistinct -le $targetCount -and $missing -le $sourceCount -and $unused -le $targetCount -and
                                $duplicates -eq 0 -and $targetCount -eq $targetDistinct -and $missing -eq 0 -and
                                $sourceDistinct -le $targetDistinct -and $unused -eq ($targetDistinct - $sourceDistinct)
                            $measured = @($counts | Where-Object { $null -ne $_ }).Count -gt 0 -or $null -ne (Get-Property $evidence 'validation_result') -or $null -ne (Get-Property $evidence 'validation_policy_version')
                            if ($measured -and -not $supported) {
                                Add-QIssue $errors 'analysis_not_supported' $dataset $entryKey 'Cited measured Analysis is incomplete or contradicts a supported reference. Retain valid measurements; do not describe them as inference.'
                            }
                            if (-not $measured) { Add-QIssue $warnings 'analysis_inferred' $dataset $entryKey 'Relationship relies on documented metadata/business inference; SQL measurements were not required or claimed.' }
                            $alignment = if ($section -ceq 'relationships') { Get-QAnalysisAlignment $record $evidence } else { $null }
                            if ($section -ceq 'relationships' -and -not $alignment) {
                                Add-QIssue $errors 'analysis_endpoint_mismatch' $dataset $entryKey "Analysis endpoints do not match the relationship's physical lineage."
                            }
                            if ($section -ceq 'relationships' -and $supported) {
                                foreach ($endpoint in @('from', 'to')) {
                                    $name = Get-Property $record ($endpoint + '_logical_entity_name')
                                    $attributeName = Get-Property $record ($endpoint + '_logical_attribute_name')
                                    $schema = Get-Property $record ($endpoint + '_logical_entity_schema_name')
                                    $endpointAttribute = $attributeIndex[(Get-QTuple @($schema, $name, $attributeName))]
                                    if ((Get-Property $endpointAttribute 'logical_attribute_is_surrogate_key') -and
                                        @(Get-QEntityAttributes $record ($endpoint + '_') | Where-Object { Get-Property $_ 'logical_attribute_is_natural_key' }).Count -gt 1) { $compositeAnalysis = $true }
                                }
                                # Child -> parent: the Analysis must run from the child's foreign key to the parent's key.
                                $cardinality = Get-Property $record 'logical_relationship_cardinality'
                                if (-not ($alignment -ceq 'forward' -and ($cardinality -ceq 'many_to_one' -or
                                    ($cardinality -ceq 'one_to_one' -and $sourceCount -eq $sourceDistinct)))) {
                                    Add-QIssue $errors 'analysis_cardinality_mismatch' $dataset $entryKey 'Declared cardinality is not supported by the cited directional uniqueness evidence.'
                                }
                            }
                        }
                    }
                }
                if ($compositeAnalysis -and -not $contextEvidence -and -not $noteEvidence) {
                    Add-QIssue $errors 'analysis_composite_identity' $dataset $entryKey 'Individual-Attribute Analysis cannot prove lookup of a composite natural identity. Cite an applicable business Context or retained business decision note for the complete lookup; do not treat component counts as tuple proof.'
                }
                if ($dataset -ceq 'logical_entity') {
                    $naturalNames = @(Get-QEntityAttributes $record | Where-Object { Get-Property $_ 'logical_attribute_is_natural_key' } | ForEach-Object { Normalize-Value 'project' 'value' $_.logical_attribute_name })
                    $natural = @(Get-QSorted $naturalNames)
                    $identityAttributes = Get-Property $entry 'identity_attributes'
                    $declared = $null
                    if ($identityAttributes -is [Array] -and @($identityAttributes | Where-Object { $_ -isnot [string] -or [string]::IsNullOrWhiteSpace($_) }).Count -eq 0) {
                        $declared = @(Get-QSorted @($identityAttributes | ForEach-Object { Normalize-Value 'project' 'value' $_ }))
                    }
                    $unique = New-Object 'Collections.Generic.HashSet[string]' ([StringComparer]::Ordinal)
                    foreach ($name in $declared) { [void]$unique.Add($name) }
                    if ($null -eq $declared -or $unique.Count -ne $declared.Count -or (ConvertTo-StableJson $declared) -cne (ConvertTo-StableJson $natural)) {
                        Add-QIssue $errors 'identity_attributes_mismatch' $dataset $entryKey 'Identity must name the complete tuple of actual active natural-key Attributes.'
                    }
                    if ($natural.Count -gt 0 -and $entry.identity_mode -cne 'natural') {
                        Add-QIssue $errors 'identity_mode_invalid' $dataset $entryKey 'An Entity with natural keys must use natural identity mode.'
                    }
                    if ($natural.Count -eq 0) {
                        if ($entry.identity_mode -cne 'append_only' -or (-not $contextEvidence -and -not $noteEvidence)) {
                            Add-QIssue $errors 'identity_evidence_missing' $dataset $entryKey 'Without natural identity, append-only treatment requires an applicable active business Context or retained business decision note.'
                        }
                        else {
                            Add-QIssue $warnings 'append_only_identity' $dataset $entryKey 'Append-only identity relies on documented business evidence; the generated surrogate does not establish deduplication.'
                        }
                    }
                }
            }
        }
        foreach ($section in @('entities', 'relationships')) {
            foreach ($entry in $template[$section]) {
                if (-not $found.ContainsKey($entry.dataset + ':' + (Get-QKey $entry.dataset $entry.key))) {
                    Add-QIssue $errors 'decision_missing' $entry.dataset $entry.key 'The affected active record needs a current evidence-backed decision.'
                }
            }
        }
    }
    $status = if (-not $required) { 'not_required' } elseif ($errors.Count -gt 0) { 'needs_evidence' } elseif (-not $hasDecisions) { 'review_required' } else { 'evidence_present' }
    return [ordered]@{
        required = $required; status = $status
        errors = @($errors | Select-Object -First 200); warnings = @($warnings | Select-Object -First 200)
        error_count = $errors.Count; warning_count = $warnings.Count; truncated = $errors.Count -gt 200 -or $warnings.Count -gt 200
        metrics = $metrics; template = $template; note_paths = @(Get-QSorted @($notes))
    }
}
