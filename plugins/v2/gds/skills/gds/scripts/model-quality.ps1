# Native modeling evidence review. Authoring digests and structural validation stay independent.
$script:ModelingQualityDatasets = @('conceptual_object', 'conceptual_relationship', 'logical_entity',
    'logical_attribute', 'logical_relationship', 'analysis_result', 'modeling_assertion_document', 'modeling_assertion_record')

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
    $relative = 'tasks/' + $Task + '.modeling-decisions.json'
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
                if ($notePath -cnotmatch '^working/[0-9]{2,}/object-analysis/.+\.md$') {
                    Fail 'Decision notes must be Markdown inside working/<task>/object-analysis/.'
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

function Assert-ModelingQualityAcceptance([string]$Session, [string]$Task, [string]$Digest, $Acceptance, $Datasets) {
    if (@($Datasets | Where-Object { $script:ModelingQualityDatasets -ccontains $_ }).Count -eq 0) { return }
    $binding = if ($Acceptance.Count -gt 0) { Get-Property $Acceptance[$Acceptance.Count - 1] 'modeling_quality' } else { $null }
    $expectedHash = Get-Property $binding 'report_sha256'
    if ($expectedHash -isnot [string] -or $expectedHash -cnotmatch '^[0-9a-f]{64}$') {
        Fail 'Modeling evidence is not bound to acceptance; validate and acknowledge the current result.'
    }
    $file = Read-ModelingEvidenceFile $Session ('tasks/' + $Task + '.modeling-quality.json') 4194304
    if ($file.sha256 -cne $expectedHash) { Fail 'Modeling quality report changed after acknowledgement.' }
    $report = ConvertFrom-GdsJson ([Text.Encoding]::UTF8.GetString($file.bytes))
    $quality = Get-Property $report 'quality'
    $errors = Get-Property $quality 'errors'
    $files = Get-Property $report 'files'
    if ((Get-Property $report 'schema_version') -cne '1.0' -or (Get-Property $report 'task') -cne $Task -or
        (Get-Property $report 'draft_digest') -cne $Digest -or $files -isnot [Array] -or $errors -isnot [Array] -or
        $errors.Count -gt 0 -or @('not_required', 'evidence_present') -cnotcontains (Get-Property $quality 'status')) {
        Fail 'Required modeling evidence is missing or unresolved.'
    }
    $stateFile = Read-ModelingEvidenceFile $Session 'session.json'
    $state = ConvertFrom-GdsJson ([Text.Encoding]::UTF8.GetString($stateFile.bytes))
    $stale = Get-Property $state 'stale'
    if ($stale -ccontains 'model' -or ((Get-Property $quality 'required') -and $stale -ccontains 'metadata')) {
        Fail 'Modeling evidence uses a stale Snapshot.'
    }
    foreach ($expected in $files) {
        if ($null -eq (Get-Property $expected 'sha256')) {
            try {
                [void](Read-ModelingEvidenceFile $Session ([string]$expected.path))
                Fail 'Modeling evidence changed after acknowledgement.'
            }
            catch { if ($_.Exception.GetBaseException() -isnot [IO.FileNotFoundException]) { throw } }
        }
        else {
            $limit = if ([string]$expected.path -cmatch '^(model|metadata)/(?:.*/)?manifest\.json$') { 8388608 } else { 1048576 }
            $actual = Read-ModelingEvidenceFile $Session ([string]$expected.path) $limit
            if ($actual.sha256 -cne [string]$expected.sha256) { Fail 'Modeling evidence or Snapshot changed after acknowledgement.' }
        }
    }
}

function Get-ModelingQuality($States, $Decisions, $NoteFiles = @{}, $MetadataStates = @()) {
    $objectFields = @('tenant_code', 'system_code', 'connection_code', 'object_schema', 'object_name')
    $entityDatasets = @('conceptual_object', 'logical_entity')
    $relationshipDatasets = @('conceptual_relationship', 'logical_relationship')
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
    function Get-QKey($Dataset, $Record) { return Get-CanonicalKey 'model' $definitions[$Dataset] $Record }
    function Get-QKeyObject($Dataset, $Record) {
        $result = [ordered]@{}
        foreach ($field in $definitions[$Dataset].canonical_key) { $result[$field] = Get-Property $Record $field }
        return $result
    }
    function Get-QTuple($Values) {
        $normalized = New-Object Collections.ArrayList
        foreach ($value in $Values) { [void]$normalized.Add((Normalize-Value 'model' 'value' $value)) }
        return ConvertTo-StableJson @($normalized)
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
        if ($null -eq $sources) { $sources = Get-Property $Record 'supports' }
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
            errors = @([ordered]@{ code = 'model_quality_input_invalid'; dataset = $Dataset; key = $null; message = 'Fix structural validation errors before reviewing quality: modeling records need complete, nonblank canonical keys and valid record arrays.' })
            warnings = @(); error_count = 1; warning_count = 0; truncated = $false; metrics = [ordered]@{}
            template = [ordered]@{ schema_version = '1.0'; entities = @(); relationships = @() }; note_paths = @()
        }
    }
    if ($null -eq $States) { return New-QInvalidInput 'model' }
    foreach ($state in $States) {
        $dataset = [string]$state.Dataset.name
        if ($script:ModelingQualityDatasets -cnotcontains $dataset) { continue }
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
                foreach ($field in @('sources', 'supports')) {
                    if (-not (Test-Property $record $field)) { continue }
                    $sources = Get-Property $record $field
                    if ($sources -isnot [Array] -or @($sources | Where-Object { -not (Test-QObject $_) }).Count -gt 0) { return New-QInvalidInput $dataset }
                }
                if ((Test-Property $record 'modeling_assertion_applicable_layers') -and
                    (Get-Property $record 'modeling_assertion_applicable_layers') -isnot [Array]) { return New-QInvalidInput $dataset }
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
    $entities = @(Get-QRows 'logical_entity' | Where-Object { (Get-Active $_) -eq $true })
    $concepts = @(Get-QRows 'conceptual_object' | Where-Object { (Get-Active $_) -eq $true })
    $attributes = @(Get-QRows 'logical_attribute' | Where-Object { (Get-Active $_) -eq $true })
    $logical = @(Get-QRows 'logical_relationship' | Where-Object { (Get-Active $_) -eq $true })
    $conceptual = @(Get-QRows 'conceptual_relationship' | Where-Object { (Get-Active $_) -eq $true })
    $entityNames = @{}
    $conceptNames = @{}
    $attributesByEntity = @{}
    $attributeIndex = @{}
    foreach ($record in $entities) {
        $name = Normalize-Value 'model' 'value' $record.logical_entity_name
        $entityNames[$name] = $record
        $attributesByEntity[$name] = New-Object Collections.ArrayList
    }
    foreach ($record in $concepts) { $conceptNames[(Normalize-Value 'model' 'value' $record.conceptual_object_name)] = $record }
    foreach ($record in $attributes) {
        $name = Normalize-Value 'model' 'value' $record.logical_entity_name
        if ($attributesByEntity.ContainsKey($name)) { [void]$attributesByEntity[$name].Add($record) }
        $attributeIndex[(Get-QTuple @($record.logical_entity_name, $record.logical_attribute_name))] = $record
    }
    function Get-QEntityAttributes($Name) {
        $normalized = Normalize-Value 'model' 'value' $Name
        if ($attributesByEntity.ContainsKey($normalized)) { return $attributesByEntity[$normalized] }
    }
    function Get-QEndpointLineage($Relationship, $Endpoint) {
        $entity = Get-Property $Relationship ($Endpoint + '_logical_entity_name')
        $name = Get-Property $Relationship ($Endpoint + '_logical_attribute_name')
        $attribute = $attributeIndex[(Get-QTuple @($entity, $name))]
        if (Get-Property $attribute 'logical_attribute_is_surrogate_key') {
            $set = New-Object 'Collections.Generic.HashSet[string]' ([StringComparer]::Ordinal)
            foreach ($candidate in @(Get-QEntityAttributes $entity)) {
                if (Get-Property $candidate 'logical_attribute_is_natural_key') {
                    foreach ($source in (Get-QLineage $candidate)) { [void]$set.Add($source) }
                }
            }
            return ,$set
        }
        return ,(Get-QLineage $attribute)
    }
    function Get-QAnalysisAlignment($Dataset, $Relationship, $Analysis) {
        if ($Dataset -ceq 'logical_relationship') {
            $from = Get-QEndpointLineage $Relationship 'from'
            $to = Get-QEndpointLineage $Relationship 'to'
        }
        else {
            $from = Get-QSupports $conceptNames[(Normalize-Value 'model' 'value' $Relationship.from_conceptual_object_name)]
            $to = Get-QSupports $conceptNames[(Normalize-Value 'model' 'value' $Relationship.to_conceptual_object_name)]
        }
        $source = Get-QPhysical $Analysis ($Dataset -ceq 'logical_relationship') 'from_'
        $target = Get-QPhysical $Analysis ($Dataset -ceq 'logical_relationship') 'to_'
        if ($from.Contains($source) -and $to.Contains($target)) { return 'forward' }
        if ($from.Contains($target) -and $to.Contains($source)) { return 'reverse' }
        return $null
    }
    $affected = @{}
    foreach ($dataset in @($entityDatasets) + @($relationshipDatasets)) {
        $affected[$dataset] = New-Object 'Collections.Generic.HashSet[string]' ([StringComparer]::Ordinal)
    }
    function Add-QAffectedRelationship($Dataset, $Record) {
        [void]$affected[$Dataset].Add((Get-QKey $Dataset $Record))
        $entityDataset = if ($Dataset -ceq 'conceptual_relationship') { 'conceptual_object' } else { 'logical_entity' }
        foreach ($endpoint in @('from', 'to')) {
            [void]$affected[$entityDataset].Add((Normalize-Value 'model' 'value' (Get-Property $Record ($endpoint + '_' + $entityDataset + '_name'))))
        }
    }
    foreach ($dataset in $entityDatasets) {
        foreach ($record in $changes[$dataset]) {
            [void]$affected[$dataset].Add((Normalize-Value 'model' 'value' (Get-Property $record ($dataset + '_name'))))
        }
    }
    foreach ($record in $changes['logical_attribute']) { [void]$affected.logical_entity.Add((Normalize-Value 'model' 'value' $record.logical_entity_name)) }
    foreach ($dataset in $relationshipDatasets) { foreach ($record in $changes[$dataset]) { Add-QAffectedRelationship $dataset $record } }
    $changedEvidence = New-Object 'Collections.Generic.HashSet[string]' ([StringComparer]::Ordinal)
    foreach ($dataset in @('analysis_result', 'modeling_assertion_record', 'modeling_assertion_document')) {
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
                $assertion = $indexes[$dataset][$identity]
                if ($dataset -ceq 'modeling_assertion_record' -and $null -ne $assertion -and
                    $changedEvidence.Contains('modeling_assertion_document:' + (Get-QKey 'modeling_assertion_document' $assertion))) { return $true }
            }
            catch { continue }
        }
        return $false
    }
    $affectedEntitySeeds = @{}
    foreach ($dataset in $entityDatasets) {
        $affectedEntitySeeds[$dataset] = New-Object 'Collections.Generic.HashSet[string]' ([StringComparer]::Ordinal)
        foreach ($name in $affected[$dataset]) { [void]$affectedEntitySeeds[$dataset].Add($name) }
    }
    foreach ($dataset in $relationshipDatasets) {
        foreach ($record in @(Get-QRows $dataset | Where-Object { (Get-Active $_) -eq $true })) {
            $entityDataset = if ($dataset -ceq 'logical_relationship') { 'logical_entity' } else { 'conceptual_object' }
            $cited = $null
            $decisionRelationships = Get-Property $Decisions 'relationships'
            if ($decisionRelationships -is [Array]) {
                foreach ($entry in $decisionRelationships) {
                    try {
                        if ((Get-Property $entry 'dataset') -ceq $dataset -and
                            (Get-QKey $dataset (Get-Property $entry 'key')) -ceq (Get-QKey $dataset $record)) { $cited = $entry; break }
                    }
                    catch { continue }
                }
            }
            $isAffected = $false
            foreach ($endpoint in @('from', 'to')) {
                if ($affectedEntitySeeds[$entityDataset].Contains((Normalize-Value 'model' 'value' (Get-Property $record ($endpoint + '_' + $entityDataset + '_name'))))) { $isAffected = $true }
            }
            foreach ($analysis in $changes['analysis_result']) {
                if (Get-QAnalysisAlignment $dataset $record $analysis) { $isAffected = $true; break }
            }
            if ($isAffected -or (Test-QReferencesChanged $cited)) { Add-QAffectedRelationship $dataset $record }
        }
    }
    $decisionEntities = Get-Property $Decisions 'entities'
    if ($decisionEntities -is [Array]) {
        foreach ($entry in $decisionEntities) {
            $dataset = Get-Property $entry 'dataset'
            if ($entityDatasets -ccontains $dataset -and (Test-QReferencesChanged $entry)) {
                [void]$affected[$dataset].Add((Normalize-Value 'model' 'value' (Get-Property (Get-Property $entry 'key') ($dataset + '_name'))))
            }
        }
    }
    $templateEntities = New-Object Collections.ArrayList
    $templateRelationships = New-Object Collections.ArrayList
    foreach ($dataset in $entityDatasets) {
        foreach ($record in @(Get-QRows $dataset | Where-Object { (Get-Active $_) -eq $true })) {
            $name = Get-Property $record ($dataset + '_name')
            if (-not $affected[$dataset].Contains((Normalize-Value 'model' 'value' $name))) { continue }
            $entry = [ordered]@{ dataset = $dataset; key = Get-QKeyObject $dataset $record }
            if ($dataset -ceq 'logical_entity') {
                $natural = @(Get-QEntityAttributes $name | Where-Object { Get-Property $_ 'logical_attribute_is_natural_key' })
                $entry['identity_attributes'] = @($natural | ForEach-Object { $_.logical_attribute_name })
                $entry['identity_mode'] = if ($natural.Count -gt 0) { 'natural' } else { 'append_only' }
            }
            $entry['decision'] = ''
            $entry['evidence'] = @()
            [void]$templateEntities.Add($entry)
        }
    }
    foreach ($dataset in $relationshipDatasets) {
        foreach ($record in @(Get-QRows $dataset | Where-Object { (Get-Active $_) -eq $true })) {
            if ($affected[$dataset].Contains((Get-QKey $dataset $record))) {
                [void]$templateRelationships.Add([ordered]@{ dataset = $dataset; key = Get-QKeyObject $dataset $record; evidence = @(); decision = '' })
            }
        }
    }
    $template = [ordered]@{ schema_version = '1.0'; entities = @($templateEntities); relationships = @($templateRelationships) }
    $required = $templateEntities.Count -gt 0 -or $templateRelationships.Count -gt 0
    $adjacency = [ordered]@{}
    foreach ($record in $entities) { $adjacency[(Normalize-Value 'model' 'value' $record.logical_entity_name)] = New-Object 'Collections.Generic.HashSet[string]' ([StringComparer]::Ordinal) }
    $selfEdges = 0
    $crossEdges = 0
    foreach ($relationship in $logical) {
        $from = Normalize-Value 'model' 'value' $relationship.from_logical_entity_name
        $to = Normalize-Value 'model' 'value' $relationship.to_logical_entity_name
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
            [void]$component.Add($entityNames[$next].logical_entity_name)
            foreach ($neighbor in $adjacency[$next]) { [void]$queue.Add($neighbor) }
        }
        [void]$components.Add(@(Get-QSorted @($component)))
    }
    $business = @($attributes | Where-Object { -not (Get-Property $_ 'logical_attribute_is_audit_column') -and -not (Get-Property $_ 'logical_attribute_is_surrogate_key') })
    $singleSource = @($business | Where-Object { (Get-QLineage $_).Count -eq 1 }).Count
    $singleObject = @($entities | Where-Object { (Get-QSupports $_).Count -eq 1 }).Count
    $sourceObjects = New-Object 'Collections.Generic.HashSet[string]' ([StringComparer]::Ordinal)
    foreach ($record in @($entities) + @($concepts)) { foreach ($source in (Get-QSupports $record)) { [void]$sourceObjects.Add($source) } }
    $isolatedEntities = @($entities | Where-Object { $adjacency[(Normalize-Value 'model' 'value' $_.logical_entity_name)].Count -eq 0 } | ForEach-Object { $_.logical_entity_name })
    $entitiesWithoutNaturalKey = @($entities | Where-Object { @(Get-QEntityAttributes $_.logical_entity_name | Where-Object { Get-Property $_ 'logical_attribute_is_natural_key' }).Count -eq 0 } | ForEach-Object { $_.logical_entity_name })
    $componentExamples = New-Object Collections.ArrayList
    $remainingComponentNames = 200
    foreach ($component in $components) {
        if ($remainingComponentNames -eq 0) { break }
        $example = @($component | Select-Object -First $remainingComponentNames)
        [void]$componentExamples.Add($example)
        $remainingComponentNames -= $example.Count
    }
    $metrics = [ordered]@{
        conceptual_objects = $concepts.Count; logical_entities = $entities.Count
        logical_relationships = $logical.Count; cross_entity_relationships = $crossEdges; self_relationships = $selfEdges
        connected_components = $components.Count; components = @($componentExamples)
        isolated_entity_count = $isolatedEntities.Count; isolated_entities = @($isolatedEntities | Select-Object -First 200)
        physical_support_objects = $sourceObjects.Count; single_object_entities = $singleObject
        entity_source_support_ratio = [ordered]@{ numerator = $singleObject; denominator = $entities.Count }
        business_attributes = $business.Count; single_source_business_attributes = $singleSource
        single_source_attribute_ratio = [ordered]@{ numerator = $singleSource; denominator = $business.Count }
        audit_attributes = @($attributes | Where-Object { Get-Property $_ 'logical_attribute_is_audit_column' }).Count
        surrogate_attributes = @($attributes | Where-Object { Get-Property $_ 'logical_attribute_is_surrogate_key' }).Count
        framework_attributes = @($attributes | Where-Object { (Get-Property $_ 'logical_attribute_is_audit_column') -or (Get-Property $_ 'logical_attribute_is_surrogate_key') }).Count
        active_attributes = $attributes.Count
        entities_without_natural_key_count = $entitiesWithoutNaturalKey.Count
        entities_without_natural_key = @($entitiesWithoutNaturalKey | Select-Object -First 200)
        metric_examples_truncated = $entities.Count -gt 200 -or $isolatedEntities.Count -gt 200 -or $entitiesWithoutNaturalKey.Count -gt 200
    }
    if ($entities.Count -gt 0 -and $singleObject -eq $entities.Count -and $singleSource -eq $business.Count) {
        Add-QIssue $warnings 'source_shaped_model' 'logical_entity' $null 'All Entities have one physical Object support and all business Attributes have one physical source. Review grain and dependencies; this does not prove copying or require splitting.'
    }
    if ($metrics.isolated_entities.Count -gt 0) {
        Add-QIssue $warnings 'isolated_entities' 'logical_entity' $null 'Some Entities have no cross-entity relationship. Review missing evidence; isolated reference Entities can be intentional.'
    }
    $metadataAttributes = @{}
    foreach ($state in $MetadataStates) {
        $metadataRecords = if (Test-Property $state 'Effective') { Get-Property $state 'Effective' } else { Get-Property $state 'Baseline' }
        foreach ($record in $metadataRecords) {
            if ((Get-Property $record 'attribute_name') -and (Get-Property $record 'attribute_inferred_data_type')) { $metadataAttributes[(Get-QPhysical $record $true)] = $record }
        }
    }
    foreach ($attribute in $business) {
        $dataType = Get-Property $attribute 'logical_attribute_data_type'
        $decimal = [regex]::Match([string]$dataType, '^DECIMAL\s*\(\s*([0-9]+)\s*,\s*([0-9]+)\s*\)$', [Text.RegularExpressions.RegexOptions]::IgnoreCase)
        if ($decimal.Success -and [double]$decimal.Groups[1].Value -eq [double]$decimal.Groups[2].Value) {
            Add-QIssue $warnings 'decimal_zero_integer_capacity' 'logical_attribute' (Get-QKeyObject 'logical_attribute' $attribute) 'DECIMAL precision equals scale; values of 1 or greater cannot fit. Confirm business capacity.'
        }
        foreach ($source in (Get-QLineage $attribute)) {
            if ($metadataAttributes.ContainsKey($source) -and
                (Normalize-Value 'model' 'value' $metadataAttributes[$source].attribute_inferred_data_type) -cne (Normalize-Value 'model' 'value' $dataType)) {
                Add-QIssue $warnings 'type_divergence' 'logical_attribute' (Get-QKeyObject 'logical_attribute' $attribute) 'The modeled type differs from current inferred Metadata. Review conversion evidence; divergence can be intentional.'
                break
            }
        }
    }
    foreach ($relationship in $conceptual) {
        $from = Get-QSupports $conceptNames[(Normalize-Value 'model' 'value' $relationship.from_conceptual_object_name)]
        $to = Get-QSupports $conceptNames[(Normalize-Value 'model' 'value' $relationship.to_conceptual_object_name)]
        if ($from.Count -eq 0 -or $to.Count -eq 0) { continue }
        $hasEdge = $false
        foreach ($edge in $logical) {
            foreach ($orientation in @('forward', 'reverse')) {
                $left = if ($orientation -ceq 'forward') { $edge.from_logical_entity_name } else { $edge.to_logical_entity_name }
                $right = if ($orientation -ceq 'forward') { $edge.to_logical_entity_name } else { $edge.from_logical_entity_name }
                $leftMatches = $false
                $rightMatches = $false
                foreach ($source in (Get-QSupports $entityNames[(Normalize-Value 'model' 'value' $left)])) { if ($from.Contains($source)) { $leftMatches = $true; break } }
                foreach ($source in (Get-QSupports $entityNames[(Normalize-Value 'model' 'value' $right)])) { if ($to.Contains($source)) { $rightMatches = $true; break } }
                if ($leftMatches -and $rightMatches) { $hasEdge = $true; break }
            }
            if ($hasEdge) { break }
        }
        if (-not $hasEdge) {
            Add-QIssue $warnings 'possible_missing_logical_relationship' 'conceptual_relationship' (Get-QKeyObject 'conceptual_relationship' $relationship) 'Support-overlap heuristic found no Logical counterpart. Confirm whether this business relationship is implemented, deferred or rejected.'
        }
    }
    if ($required) {
        if (-not (Test-QFields $Decisions @('schema_version', 'entities', 'relationships')) -or
            (Get-Property $Decisions 'schema_version') -cne '1.0' -or
            (Get-Property $Decisions 'entities') -isnot [Array] -or (Get-Property $Decisions 'relationships') -isnot [Array]) {
            Add-QIssue $errors 'decisions_missing_or_invalid' 'model' $null 'Provide schema_version 1.0 and the two entity/relationship decision arrays; metrics and pass flags are computed.'
        }
        $found = @{}
        foreach ($section in @('entities', 'relationships')) {
            $entries = Get-Property $Decisions $section
            if ($entries -isnot [Array]) { continue }
            foreach ($entry in $entries) {
                $allowed = if ($section -ceq 'entities') { $entityDatasets } else { $relationshipDatasets }
                $dataset = Get-Property $entry 'dataset'
                $fields = @('dataset', 'key', 'decision', 'evidence')
                if ($dataset -ceq 'logical_entity') { $fields += @('identity_attributes', 'identity_mode') }
                $entryKey = Get-Property $entry 'key'
                if ($allowed -cnotcontains $dataset -or -not (Test-QFields $entry $fields) -or
                    -not $indexes.ContainsKey($dataset) -or -not (Test-QFields $entryKey $definitions[$dataset].canonical_key)) {
                    $issueDataset = if ($dataset) { $dataset } else { 'model' }
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
                $assertionEvidence = $false
                $compositeAnalysis = $false
                $conceptualCardinalityMismatch = $false
                $evidenceSeen = New-Object 'Collections.Generic.HashSet[string]' ([StringComparer]::Ordinal)
                if ($evidenceReferences -is [Array]) {
                    foreach ($reference in $evidenceReferences) {
                        $referenceIdentity = ConvertTo-StableJson $reference
                        if ($evidenceSeen.Contains($referenceIdentity)) { Add-QIssue $errors 'evidence_duplicate' $dataset $entryKey 'Duplicate evidence reference.' }
                        [void]$evidenceSeen.Add($referenceIdentity)
                        if ((Test-QFields $reference @('note')) -and $section -ceq 'entities') {
                            $name = Get-Property $reference 'note'
                            if ($name -isnot [string] -or -not $name.EndsWith('.md', [StringComparison]::Ordinal) -or
                                $name.StartsWith('/') -or $name.Contains('\') -or $name.Contains(':') -or
                                @($name.Split('/') | Where-Object { $_ -ceq '' -or $_ -ceq '.' -or $_ -ceq '..' }).Count -gt 0) {
                                Add-QIssue $errors 'note_invalid' $dataset $entryKey 'Evidence note must be a session-relative Markdown path.'
                            }
                            else {
                                [void]$notes.Add($name)
                                if ($null -eq $NoteFiles -or -not $NoteFiles.ContainsKey($name)) {
                                    Add-QIssue $errors 'note_missing' $dataset $entryKey 'Referenced sanitized evidence note is missing.'
                                }
                            }
                            continue
                        }
                        $evidenceDataset = Get-Property $reference 'dataset'
                        $evidenceKey = Get-Property $reference 'key'
                        if (-not (Test-QFields $reference @('dataset', 'key')) -or
                            @('analysis_result', 'modeling_assertion_record') -cnotcontains $evidenceDataset -or
                            -not $indexes.ContainsKey($evidenceDataset) -or
                            -not (Test-QFields $evidenceKey $definitions[$evidenceDataset].canonical_key)) {
                            Add-QIssue $errors 'evidence_invalid' $dataset $entryKey 'Use an existing Analysis/Assertion canonical key; notes are allowed only for Entity decisions.'
                            continue
                        }
                        $evidence = $indexes[$evidenceDataset][(Get-QKey $evidenceDataset $evidenceKey)]
                        if ($null -eq $evidence -or (Get-Active $evidence) -ne $true) {
                            Add-QIssue $errors 'evidence_inactive_or_missing' $dataset $entryKey 'Evidence must identify an active effective record.'
                            continue
                        }
                        if ($evidenceDataset -ceq 'modeling_assertion_record') {
                            $layer = if ($dataset.StartsWith('logical', [StringComparison]::Ordinal)) { 'logical' } else { 'conceptual' }
                            $document = $null
                            foreach ($candidate in @(Get-QRows 'modeling_assertion_document')) {
                                if ((Normalize-Value 'model' 'value' $candidate.modeling_assertion_document_name) -ceq
                                    (Normalize-Value 'model' 'value' $evidence.modeling_assertion_document_name)) { $document = $candidate; break }
                            }
                            if ($null -eq $document -or (Get-Active $document) -ne $true -or
                                (Get-Property $evidence 'modeling_assertion_applicable_layers') -cnotcontains $layer) {
                                Add-QIssue $errors 'assertion_not_applicable' $dataset $entryKey 'Assertion requires an active document and the applicable modeling layer.'
                            }
                            else { $assertionEvidence = $true }
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
                            if (-not $supported) {
                                Add-QIssue $errors 'analysis_not_supported' $dataset $entryKey 'Analysis must contain a complete supported deterministic result with consistent counts, nonempty domains, no orphan values and unique target keys.'
                            }
                            $alignment = if ($section -ceq 'relationships') { Get-QAnalysisAlignment $dataset $record $evidence } else { $null }
                            if ($section -ceq 'relationships' -and -not $alignment) {
                                Add-QIssue $errors 'analysis_endpoint_mismatch' $dataset $entryKey "Analysis endpoints do not match the relationship's physical lineage or supported Conceptual Objects."
                            }
                            if ($section -ceq 'relationships' -and $supported) {
                                if ($dataset -ceq 'logical_relationship') {
                                    foreach ($endpoint in @('from', 'to')) {
                                        $name = Get-Property $record ($endpoint + '_logical_entity_name')
                                        $attributeName = Get-Property $record ($endpoint + '_logical_attribute_name')
                                        $endpointAttribute = $attributeIndex[(Get-QTuple @($name, $attributeName))]
                                        if ((Get-Property $endpointAttribute 'logical_attribute_is_surrogate_key') -and
                                            @(Get-QEntityAttributes $name | Where-Object { Get-Property $_ 'logical_attribute_is_natural_key' }).Count -gt 1) { $compositeAnalysis = $true }
                                    }
                                }
                                $cardinality = Get-Property $record ($dataset + '_cardinality')
                                if (-not (($dataset -ceq 'conceptual_relationship' -and $cardinality -ceq 'unknown') -or
                                    ($cardinality -ceq 'many_to_one' -and $alignment -ceq 'forward') -or
                                    ($cardinality -ceq 'one_to_many' -and $alignment -ceq 'reverse') -or
                                    ($cardinality -ceq 'one_to_one' -and $alignment -and $sourceCount -eq $sourceDistinct))) {
                                    if ($dataset -ceq 'conceptual_relationship') { $conceptualCardinalityMismatch = $true }
                                    else { Add-QIssue $errors 'analysis_cardinality_mismatch' $dataset $entryKey 'Declared cardinality is not supported by the cited directional uniqueness evidence.' }
                                }
                            }
                        }
                    }
                }
                if ($conceptualCardinalityMismatch -and -not $assertionEvidence) {
                    Add-QIssue $errors 'analysis_cardinality_mismatch' $dataset $entryKey 'Known Conceptual cardinality is not supported by the cited directional uniqueness evidence. A different business grain requires an applicable business Assertion; otherwise retain unknown cardinality.'
                }
                if ($compositeAnalysis -and -not $assertionEvidence) {
                    Add-QIssue $errors 'analysis_composite_identity' $dataset $entryKey 'Individual-Attribute Analysis cannot prove lookup of a composite natural identity. Cite an applicable business Assertion for the complete lookup; do not treat component counts as tuple proof.'
                }
                if ($dataset -ceq 'logical_entity') {
                    $naturalNames = @(Get-QEntityAttributes $record.logical_entity_name | Where-Object { Get-Property $_ 'logical_attribute_is_natural_key' } | ForEach-Object { Normalize-Value 'model' 'value' $_.logical_attribute_name })
                    $natural = @(Get-QSorted $naturalNames)
                    $identityAttributes = Get-Property $entry 'identity_attributes'
                    $declared = $null
                    if ($identityAttributes -is [Array] -and @($identityAttributes | Where-Object { $_ -isnot [string] -or [string]::IsNullOrWhiteSpace($_) }).Count -eq 0) {
                        $declared = @(Get-QSorted @($identityAttributes | ForEach-Object { Normalize-Value 'model' 'value' $_ }))
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
                        if ($entry.identity_mode -cne 'append_only' -or -not $assertionEvidence) {
                            Add-QIssue $errors 'identity_evidence_missing' $dataset $entryKey 'Without natural identity, append-only treatment requires an applicable active business Assertion.'
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
    $status = if (-not $required) { 'not_required' } elseif ($errors.Count -gt 0) { 'needs_evidence' } else { 'evidence_present' }
    return [ordered]@{
        required = $required; status = $status
        errors = @($errors | Select-Object -First 200); warnings = @($warnings | Select-Object -First 200)
        error_count = $errors.Count; warning_count = $warnings.Count; truncated = $errors.Count -gt 200 -or $warnings.Count -gt 200
        metrics = $metrics; template = $template; note_paths = @(Get-QSorted @($notes))
    }
}
