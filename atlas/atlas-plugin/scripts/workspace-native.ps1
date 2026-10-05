# Atlas workspace state and governed operation evidence, native Windows PowerShell 5.1.
# This layer shares the Snapshot codecs and pure validators in atlas-local.ps1.
$script:AtlasUuid = '^[0-9a-fA-F]{8}-[0-9a-fA-F]{4}-[1-8][0-9a-fA-F]{3}-[89abAB][0-9a-fA-F]{3}-[0-9a-fA-F]{12}$'
$script:AtlasDigest = '^[0-9a-f]{64}$'

function Test-AtlasObject($Value) {
    return $null -ne $Value -and $Value -isnot [Array] -and $Value -isnot [string] -and $Value -isnot [ValueType]
}

function Resolve-WorkspacePath([string]$Root, [string]$Relative, [bool]$CreateDirectories = $false) {
    Assert-SafeSnapshotMemberPath $Relative
    $current = Resolve-RegularDirectory $Root 'Workspace'
    $parts = $Relative.Split('/')
    for ($index = 0; $index -lt $parts.Count; $index++) {
        $current = Join-Path $current $parts[$index]
        $item = Get-Item -LiteralPath $current -Force -ErrorAction SilentlyContinue
        if ($null -eq $item) {
            if ($index -lt $parts.Count - 1) {
                if (-not $CreateDirectories) { throw [IO.FileNotFoundException]::new('Workspace parent directory is missing.') }
                [void][IO.Directory]::CreateDirectory($current)
                $item = Get-Item -LiteralPath $current -Force -ErrorAction Stop
            }
            else { return $current }
        }
        if (($item.Attributes -band [IO.FileAttributes]::ReparsePoint) -or
            ($index -lt $parts.Count - 1 -and -not $item.PSIsContainer)) {
            Fail 'Workspace paths must not traverse symbolic links or non-directories.'
        }
    }
    return $current
}

function Read-WorkspaceJson([string]$Root, [string]$Relative) {
    $file = Resolve-WorkspacePath $Root $Relative
    $item = Get-Item -LiteralPath $file -Force -ErrorAction Stop
    if ($item.PSIsContainer -or $item.Length -gt 16MB) { Fail 'Workspace JSON must be a bounded regular file.' }
    $bytes = [IO.File]::ReadAllBytes($file)
    return [ordered]@{ value = ConvertFrom-GdsJson ([Text.Encoding]::UTF8.GetString($bytes)); digest = Get-ByteDigest $bytes; path = $file }
}

function Write-WorkspaceJson([string]$Root, [string]$Relative, $Value, [string]$Expected = 'absent') {
    $file = Resolve-WorkspacePath $Root $Relative $true
    $check = {
        if (Test-Path -LiteralPath $file) {
            if ($Expected -ceq 'absent' -or $Expected -cnotmatch $script:AtlasDigest -or
                (Read-WorkspaceJson $Root $Relative).digest -cne $Expected) { Fail 'Workspace file changed; reread before writing.' }
        }
        elseif ($Expected -cne 'absent') { Fail 'Workspace file disappeared; reread before writing.' }
    }
    & $check
    $temporary = $file + '.' + [Guid]::NewGuid().ToString() + '.tmp'
    $bytes = $script:Utf8NoBom.GetBytes((ConvertTo-GdsJson $Value) + "`n")
    $stream = [IO.File]::Open($temporary, [IO.FileMode]::CreateNew, [IO.FileAccess]::Write, [IO.FileShare]::None)
    try { $stream.Write($bytes, 0, $bytes.Length) } finally { $stream.Dispose() }
    try {
        & $check
        if (Test-Path -LiteralPath $file) { [IO.File]::Replace($temporary, $file, [NullString]::Value, $true) }
        else { [IO.File]::Move($temporary, $file) }
    }
    finally { if (Test-Path -LiteralPath $temporary) { [IO.File]::Delete($temporary) } }
    return Get-FileDigest $file
}

function Assert-AtlasIdentity($Value, [string]$Label) {
    if (-not (Test-AtlasObject $Value) -or -not (Test-SafeJsonInteger (Get-Property $Value 'id') $false) -or
        (Get-Property $Value 'code') -isnot [string] -or [string]::IsNullOrWhiteSpace($Value.code) -or $Value.code.Length -gt 255) {
        Fail "$Label needs a verified positive ID and nonblank code."
    }
}

function Assert-SubagentPolicy($Value) {
    if (-not (Test-AtlasObject $Value) -or @('current', 'auto', 'custom') -cnotcontains (Get-Property $Value 'mode')) {
        Fail 'Invalid sub-agent policy. Choose current, auto or custom.'
    }
    foreach ($key in @(Get-PropertyNames $Value)) {
        if (@('mode', 'model') -cnotcontains $key) { Fail 'Invalid sub-agent policy. Choose current, auto or custom.' }
    }
    if ($Value.mode -ceq 'custom') {
        $model = Get-Property $Value 'model'
        if ($model -isnot [string] -or $model.Length -eq 0 -or $model.Length -gt 200 -or
            $model -match '^[\s\uFEFF]|[\s\uFEFF]$|[\u0000-\u001f\u007f-\u009f]') {
            Fail 'Custom sub-agent policy requires one model name or ID, at most 200 characters, without surrounding whitespace or control characters.'
        }
    } elseif (Test-Property $Value 'model') { Fail 'Only the custom sub-agent policy accepts a model.' }
}

function Read-SessionDocument([string]$Root) {
    $document = Read-WorkspaceJson $Root '.atlas/session.json'
    $state = $document.value
    if (-not (Test-AtlasObject $state) -or (Get-Property $state 'schema_version') -cne '1.0') { Fail 'Invalid Atlas session version.' }
    Assert-AtlasIdentity (Get-Property $state 'tenant') 'Tenant'
    $model = Get-Property $state 'model'
    if ($null -ne $model -and (-not (Test-AtlasObject $model) -or -not (Test-SafeJsonInteger (Get-Property $model 'id') $false) -or
        (Get-Property $model 'name') -isnot [string] -or [string]::IsNullOrWhiteSpace($model.name))) { Fail 'Invalid active Model identity.' }
    $active = Get-Property $state 'active_task'
    if ($null -ne $active -and [string]$active -cnotmatch $script:AtlasUuid) { Fail 'Invalid active task ID.' }
    if (Test-Property $state 'sql') {
        $sql = $state.sql
        if (-not (Test-AtlasObject $sql) -or @('never', 'essential', 'proactive') -cnotcontains (Get-Property $sql 'policy') -or
            ((Test-Property $sql 'environment') -and @('dev', 'qa', 'stg', 'prod') -cnotcontains $sql.environment)) { Fail 'Invalid SQL policy/environment.' }
    }
    if (Test-Property $state 'subagent_policy') { Assert-SubagentPolicy $state.subagent_policy }
    $owners = Get-Property $state 'metadata_owners'
    if ($null -ne $owners -and -not (Test-AtlasObject $owners)) { Fail 'Invalid Metadata owner registry.' }
    foreach ($id in @(Get-PropertyNames $owners)) {
        $owner = Get-Property $owners $id
        Assert-AtlasIdentity $owner 'Metadata owner'
        $expectedRoot = if ($owner.id -eq $state.tenant.id) { '.' } else { 'metadata-owners/tenant-' + $owner.id }
        if ([string]$owner.id -cne $id -or (Get-Property $owner 'root') -cne $expectedRoot -or
            ($owner.id -eq $state.tenant.id -and $owner.code -cne $state.tenant.code)) { Fail 'Metadata owner registry conflicts with workspace identity.' }
    }
    if (Test-Property $state 'refresh_required') {
        if ($state.refresh_required -isnot [Array]) { Fail 'Invalid Snapshot refresh markers.' }
        foreach ($entry in $state.refresh_required) {
            if (-not (Test-AtlasObject $entry) -or @('metadata', 'model') -cnotcontains (Get-Property $entry 'area') -or
                -not (Test-SafeJsonInteger (Get-Property $entry 'owner_tenant_id') $false)) { Fail 'Invalid Snapshot refresh markers.' }
        }
    }
    return $document
}

function Read-SessionState([string]$Session) { return (Read-SessionDocument $Session).value }
function Resolve-Session([hashtable]$Options) {
    $root = Resolve-RegularDirectory (Require-Option $Options 'session') 'Workspace'
    [void](Read-SessionDocument $root)
    return $root
}

function Get-AtlasOwner($State, [string]$Area, $Selected = $null) {
    if (@('metadata', 'model') -cnotcontains $Area) { Fail '--area must be metadata or model.' }
    $id = $State.tenant.id
    if ($null -ne $Selected) { [double]$id = 0; if (-not [double]::TryParse([string]$Selected, [ref]$id)) { Fail '--owner must be a positive Tenant ID.' } }
    if (-not (Test-SafeJsonInteger $id $false)) { Fail '--owner must be a positive Tenant ID.' }
    if ($Area -ceq 'model' -and $id -ne $State.tenant.id) { Fail 'Model ownership must match the primary Tenant.' }
    if ($id -eq $State.tenant.id) { return [ordered]@{ id = $State.tenant.id; code = $State.tenant.code; root = '.' } }
    $owner = Get-Property (Get-Property $State 'metadata_owners') ([string]$id)
    if ($null -eq $owner -or $null -eq (Get-Property $State 'model')) { Fail 'Additional Metadata owner requires a selected Model and registered owner.' }
    return [ordered]@{ id = $owner.id; code = $owner.code; root = $owner.root }
}
function Get-OwnerPrefix($Owner) { if ($Owner.root -ceq '.') { return '' }; return [string]$Owner.root + '/' }

function Assert-AtlasTask($Value) {
    if (-not (Test-AtlasObject $Value) -or (Get-Property $Value 'schema_version') -cne '1.0' -or
        (Get-Property $Value 'outcome') -isnot [string] -or [string]::IsNullOrWhiteSpace($Value.outcome) -or
        ((Test-Property $Value 'progress') -and $Value.progress -isnot [string]) -or
        ((Test-Property $Value 'inputs') -and -not (Test-AtlasObject $Value.inputs))) { Fail 'Invalid Atlas task; outcome is required and progress stays free-form.' }
    foreach ($name in @('work', 'evidence')) {
        if (-not (Test-Property $Value $name)) { continue }
        $entries = Get-Property $Value $name
        if ($entries -isnot [Array]) { Fail 'Task work/evidence must be lists.' }
        foreach ($entry in $entries) {
            if (-not (Test-AtlasObject $entry) -or (Get-Property $entry 'path') -isnot [string] -or (Get-Property $entry 'purpose') -isnot [string]) { Fail 'Task entries require path and purpose.' }
        }
    }
}
function Read-AtlasTask([string]$Root, [string]$Id) {
    if ($Id -cnotmatch $script:AtlasUuid) { Fail 'A task UUID is required.' }
    $document = Read-WorkspaceJson $Root ('.atlas/tasks/' + $Id + '.json')
    Assert-AtlasTask $document.value
    return $document
}
function Read-AtlasOperation([string]$Root, $State, [string]$Area, $Owner) {
    $operations = Get-Property $State 'operations'
    $relative = if ($Area -ceq 'model') { Get-Property $operations 'model' } else { Get-Property (Get-Property $operations 'metadata') ([string]$Owner.id) }
    if (-not $relative) { Fail 'A digest-bound acknowledgement is required first.' }
    $document = Read-WorkspaceJson $Root $relative
    $value = $document.value
    $identity = Get-Property $value 'owner'
    if (-not (Test-AtlasObject $value) -or (Get-Property $value 'schema_version') -cne '1.0' -or
        [string](Get-Property $value 'id') -cnotmatch $script:AtlasUuid -or [string](Get-Property $value 'task_id') -cnotmatch $script:AtlasUuid -or
        $relative -cne ('.atlas/tasks/' + $value.task_id + '.evidence/' + $value.id + '.json') -or $value.area -cne $Area -or
        (Get-Property $identity 'id') -ne $Owner.id -or (Get-Property $identity 'code') -cne $Owner.code -or
        (Get-Property $identity 'root') -cne $Owner.root -or [string](Get-Property $value 'local_digest') -cnotmatch $script:AtlasDigest) { Fail 'Operation evidence does not match its owner/area/path.' }
    [void](Read-AtlasTask $Root $value.task_id)
    $document['relative'] = $relative
    return $document
}

function Initialize-Session([hashtable]$Options) {
    $root = Require-Option $Options 'root'
    if (-not [IO.Path]::IsPathRooted($root)) { Fail '--root must be an absolute working directory.' }
    $root = [IO.Path]::GetFullPath($root)
    $tenant = [ordered]@{ id = [double](Require-Option $Options 'tenant-id'); code = Require-Option $Options 'tenant' }
    Assert-AtlasIdentity $tenant 'Tenant'
    $model = $null
    if ($Options.ContainsKey('model-id')) {
        $model = [ordered]@{ id = [double]$Options['model-id']; name = Require-Option $Options 'model-name' }
        if (-not (Test-SafeJsonInteger $model.id $false)) { Fail 'Model requires verified --model-id and --model-name.' }
    }
    [void][IO.Directory]::CreateDirectory($root)
    $file = Resolve-WorkspacePath $root '.atlas/session.json' $true
    if (Test-Path -LiteralPath $file) {
        $existing = Read-SessionState $root
        if ($existing.tenant.id -ne $tenant.id -or $existing.tenant.code -cne $tenant.code -or
            ($null -ne $model -and (Get-Property (Get-Property $existing 'model') 'id') -ne $model.id)) { Fail 'Existing workspace identity differs; use another directory.' }
        return [ordered]@{ workspace = $root; reused = $true; session = $existing }
    }
    $owners = @{}; $owners[[string]$tenant.id] = [ordered]@{ id = $tenant.id; code = $tenant.code; root = '.' }
    $value = [ordered]@{ schema_version = '1.0'; tenant = $tenant; model = $model; active_task = $null; metadata_owners = $owners }
    if ($Options.ContainsKey('policy')) {
        if (@('never', 'essential', 'proactive') -cnotcontains $Options.policy) { Fail 'Invalid SQL choices.' }
        $value.sql = [ordered]@{ policy = $Options.policy }
        if ($Options.ContainsKey('environment')) {
            if (@('dev', 'qa', 'stg', 'prod') -cnotcontains $Options.environment) { Fail 'Invalid SQL choices.' }
            $value.sql.environment = $Options.environment
        }
    }
    [void](Write-WorkspaceJson $root '.atlas/session.json' $value)
    [void](Resolve-WorkspacePath $root '.atlas/tasks/.check' $true)
    [void](Resolve-WorkspacePath $root '.atlas/temp/.check' $true)
    return [ordered]@{ workspace = $root; reused = $false; session = $value }
}
function Register-Owner([hashtable]$Options) {
    $root = Resolve-Session $Options; $document = Read-SessionDocument $root; $state = $document.value
    $owner = [ordered]@{ id = [double](Require-Option $Options 'tenant-id'); code = Require-Option $Options 'tenant' }
    Assert-AtlasIdentity $owner 'Metadata owner'
    if ($owner.id -ne $state.tenant.id -and $null -eq $state.model) { Fail 'Additional owners require Model-derived work.' }
    $owner.root = if ($owner.id -eq $state.tenant.id) { '.' } else { 'metadata-owners/tenant-' + $owner.id }
    $owners = Get-Property $state 'metadata_owners'
    if ($null -eq $owners) { $owners = @{}; Set-Property $state 'metadata_owners' $owners }
    $previous = Get-Property $owners ([string]$owner.id)
    if ($null -ne $previous -and ($previous.code -cne $owner.code -or $previous.root -cne $owner.root)) { Fail 'Owner identity cannot be rebound.' }
    Set-Property $owners ([string]$owner.id) $owner
    [void](Write-WorkspaceJson $root '.atlas/session.json' $state $document.digest)
    return [ordered]@{ owner = $owner }
}
function Add-Task([hashtable]$Options) {
    $root = Resolve-Session $Options; $document = Read-SessionDocument $root
    $id = [Guid]::NewGuid().ToString()
    $value = [ordered]@{ schema_version = '1.0'; outcome = Require-Option $Options 'outcome' }
    if ($Options.ContainsKey('workflow')) { $value.inputs = [ordered]@{ workflow = $Options.workflow } }
    $relative = '.atlas/tasks/' + $id + '.json'
    [void](Write-WorkspaceJson $root $relative $value)
    [void](Resolve-WorkspacePath $root ('.atlas/tasks/' + $id + '.evidence/.check') $true)
    Set-Property $document.value 'active_task' $id
    [void](Write-WorkspaceJson $root '.atlas/session.json' $document.value $document.digest)
    return [ordered]@{ task = $id; path = $relative }
}
function Update-Task([hashtable]$Options) {
    $root = Resolve-Session $Options
    $id = if ($Options.ContainsKey('task')) { $Options.task } else { (Read-SessionState $root).active_task }
    $previous = Read-AtlasTask $root $id
    if ($Options['expected-digest'] -cne $previous.digest) { Fail 'Task changed; use its current --expected-digest.' }
    $value = $previous.value
    if ($Options.ContainsKey('file')) { $value = Read-Json ([IO.Path]::GetFullPath($Options.file)) 'Task' }
    elseif ($Options.ContainsKey('progress')) { Set-Property $value 'progress' $Options.progress }
    Assert-AtlasTask $value
    $digest = Write-WorkspaceJson $root ('.atlas/tasks/' + $id + '.json') $value $previous.digest
    return [ordered]@{ task = $id; digest = $digest }
}
function Get-SessionStatus([hashtable]$Options) {
    $root = Resolve-Session $Options; $document = Read-SessionDocument $root
    $detail = if ($Options.ContainsKey('detail')) { $Options.detail } else { 'summary' }
    $history = $Options.ContainsKey('history') -and $Options.history -ceq 'true'
    if (@('summary', 'full') -cnotcontains $detail) { Fail '--detail must be summary or full.' }
    if ($Options.ContainsKey('history') -and -not $history) { Fail '--history accepts true only.' }
    if (($history -and $Options.ContainsKey('task')) -or (-not $history -and $Options.ContainsKey('cursor'))) { Fail 'Use --task or paged --history true, not both.' }
    [double]$limitValue = 50
    if ($Options.ContainsKey('limit') -and -not [double]::TryParse($Options.limit, [ref]$limitValue)) { Fail '--limit must be between 1 and 200.' }
    if (-not (Test-SafeJsonInteger $limitValue $false) -or $limitValue -gt 200) { Fail '--limit must be between 1 and 200.' }
    $limit = [int]$limitValue
    $names = New-Object 'System.Collections.Generic.List[string]'
    foreach ($file in @(Get-ChildItem -LiteralPath (Resolve-WorkspacePath $root '.atlas/tasks') -Filter '*.json' -Force)) {
        if ($file.PSIsContainer -or ($file.Attributes -band [IO.FileAttributes]::ReparsePoint) -or [IO.Path]::GetFileNameWithoutExtension($file.Name) -cnotmatch $script:AtlasUuid) {
            Fail 'Task entries must be regular UUID-named JSON files.'
        }
        [void]$names.Add($file.Name)
    }
    $names.Sort([StringComparer]::Ordinal)
    $bindingValue = [ordered]@{names = @($names); session = $document.digest; detail = $detail; limit = $limit}
    $binding = Get-ByteDigest ($script:Utf8NoBom.GetBytes((ConvertTo-StableJson $bindingValue)))
    $offset = Get-PageOffset $Options $binding
    $selected = if ($Options.ContainsKey('task')) { $Options.task } else { Get-Property $document.value 'active_task' }
    $ids = New-Object Collections.ArrayList
    if ($history) {
        for ($i = $offset; $i -lt [Math]::Min($names.Count, $offset + $limit); $i++) { [void]$ids.Add([IO.Path]::GetFileNameWithoutExtension($names[$i])) }
    } elseif ($selected) { [void]$ids.Add($selected) }
    if ($offset -gt 0 -and $ids.Count -eq 0) { Fail 'Cursor is outside the task history; restart without --cursor.' }
    $tasks = New-Object Collections.ArrayList
    foreach ($id in $ids) {
        $task = Read-AtlasTask $root $id; $value = $task.value; $entry = [ordered]@{}
        if ($detail -ceq 'full') {
            foreach ($key in @(Get-PropertyNames $value)) { $entry[$key] = Get-Property $value $key }
        } else {
            $clipped = $false
            foreach ($field in @('outcome', 'workflow', 'progress')) {
                $valueText = Get-Property $value $field
                if ($valueText -isnot [string]) { continue }
                $length = if ($field -ceq 'outcome') { 1000 } elseif ($field -ceq 'workflow') { 200 } else { 2000 }
                $entry[$field] = $valueText.Substring(0, [Math]::Min($valueText.Length, $length))
                if ($valueText.Length -gt $length) { $clipped = $true }
            }
            $entry.text_truncated = $clipped; $entry.has_inputs = Test-Property $value 'inputs'
            $work = Get-Property $value 'work'; $evidence = Get-Property $value 'evidence'
            $entry.work_count = if ($null -eq $work) { 0 } else { @($work).Count }
            $entry.evidence_count = if ($null -eq $evidence) { 0 } else { @($evidence).Count }
        }
        $entry.id = $id; $entry.digest = $task.digest; [void]$tasks.Add($entry)
    }
    $truncated = $history -and $offset + $tasks.Count -lt $names.Count
    return [ordered]@{ workspace = $root; session = $document.value; session_digest = $document.digest; detail = $detail
        task_count = $names.Count; tasks = @($tasks); truncated = $truncated
        next_cursor = if ($truncated) { 'v1.' + $binding + '.' + ($offset + $tasks.Count).ToString([Globalization.CultureInfo]::InvariantCulture) } else { $null } }
}

function Set-SqlPolicy([hashtable]$Options) {
    $root = Resolve-Session $Options; $document = Read-SessionDocument $root
    if (@('never', 'essential', 'proactive') -cnotcontains $Options.policy) { Fail 'Invalid SQL policy.' }
    $environment = if ($Options.ContainsKey('environment')) { $Options.environment } else { Get-Property (Get-Property $document.value 'sql') 'environment' }
    if (-not $environment) { $environment = 'dev' }
    if (@('dev', 'qa', 'stg', 'prod') -cnotcontains $environment) { Fail 'Invalid SQL environment.' }
    $sql = [ordered]@{ policy = $Options.policy }
    if ($Options.policy -cne 'never') { $sql.environment = $environment }
    Set-Property $document.value 'sql' $sql
    [void](Write-WorkspaceJson $root '.atlas/session.json' $document.value $document.digest)
    return [ordered]@{ sql = $sql }
}

function Set-SubagentPolicy([hashtable]$Options) {
    foreach ($key in $Options.Keys) {
        if (@('session', 'mode', 'model', 'output-file') -cnotcontains $key) {
            Fail 'Sub-agent policy accepts only --session, --mode, --model and --output-file.'
        }
    }
    $root = Resolve-Session $Options; $document = Read-SessionDocument $root
    $policy = [ordered]@{ mode = Require-Option $Options 'mode' }
    if ($Options.ContainsKey('model')) { $policy.model = $Options.model }
    Assert-SubagentPolicy $policy
    Set-Property $document.value 'subagent_policy' $policy
    [void](Write-WorkspaceJson $root '.atlas/session.json' $document.value $document.digest)
    return [ordered]@{ subagent_policy = $policy }
}

function Find-Snapshot([hashtable]$Options) {
    $session = Resolve-Session $Options; $state = Read-SessionState $session
    $area = Require-Option $Options 'area'; $owner = Get-AtlasOwner $state $area $Options['owner']
    $relative = (Get-OwnerPrefix $owner) + $area + '/' + $area + '-snapshot'
    $snapshotRoot = Resolve-WorkspacePath $session $relative
    if (-not (Test-Path -LiteralPath $snapshotRoot -PathType Container)) { throw [IO.FileNotFoundException]::new("$area Snapshot directory is missing.") }
    return Read-SnapshotRoot $snapshotRoot $session $state $owner $area
}

function Read-SnapshotRoot([string]$SnapshotRoot, [string]$Session, $State, $Owner, [string]$Area) {
    [void](Resolve-RegularDirectory $SnapshotRoot 'Snapshot')
    $manifest = Read-Json (Join-Path $snapshotRoot 'manifest.json') 'Snapshot manifest'
    if (-not (Test-Property $manifest 'members') -or @($manifest.members).Count -eq 0) {
        Fail 'Snapshot manifest members are invalid.'
    }
    $members = New-Object 'System.Collections.Generic.Dictionary[string,object]'
    foreach ($member in @($manifest.members)) {
        if (-not (Test-Property $member 'path') -or -not (Test-Property $member 'size_bytes') -or
            -not (Test-Property $member 'sha256')) {
            Fail 'Snapshot manifest members are invalid.'
        }
        $memberPath = [string]$member.path
        Assert-SafeSnapshotMemberPath $memberPath
        $size = $member.size_bytes
        $digest = $member.sha256
        if (($size -isnot [int] -and $size -isnot [long]) -or [long]$size -lt 0 -or
            $digest -isnot [string] -or $digest -cnotmatch '^[0-9a-f]{64}$') {
            Fail 'Snapshot manifest members are invalid.'
        }
        if ($members.ContainsKey($memberPath)) { Fail "Snapshot manifest contains duplicate member path $memberPath." }
        $members.Add($memberPath, $member)
    }
    if (-not (Test-Property $manifest 'catalog') -or -not (Test-Property $manifest.catalog 'path') -or
        -not (Test-Property $manifest.catalog 'sha256') -or
        [string]$manifest.catalog.path -cne 'catalog.json' -or
        $manifest.catalog.sha256 -isnot [string] -or
        $manifest.catalog.sha256 -cnotmatch '^[0-9a-f]{64}$') {
        Fail 'Snapshot manifest catalog descriptor is invalid.'
    }
    $catalogPath = [string]$manifest.catalog.path
    if (-not $members.ContainsKey($catalogPath) -or
        [string]$members[$catalogPath].sha256 -cne [string]$manifest.catalog.sha256) {
        Fail 'Snapshot manifest catalog descriptor does not match its member inventory.'
    }
    $catalog = Read-Json (Resolve-Member $snapshotRoot $catalogPath $members) 'Snapshot catalog'
    if ($manifest.snapshot_kind -ne $area -or $catalog.snapshot_kind -ne $area) {
        Fail "Snapshot kind must match $area."
    }
    if ($area -ceq 'model' -and ((Get-Property $manifest 'schema_version') -cne '2.0' -or (Get-Property $catalog 'schema_version') -cne '2.0')) { Fail 'Model Snapshot schema version 2.0 is required.' }
    $datasets = New-Object System.Collections.ArrayList
    $names = @{}
    foreach ($section in @($catalog.sections)) {
        if ($area -ceq 'model' -and (Get-Property $section 'name') -ceq 'model_binding') { Fail 'Legacy Model Snapshot contract; fetch a new Entity-owned Model Snapshot.' }
        foreach ($dataset in @($section.datasets)) {
            if ($area -ceq 'model') {
                if (@('model_object_binding', 'model_attribute_binding', 'mapping_dependency') -ccontains $dataset.name) { Fail 'Legacy Model Snapshot contract; fetch a new Entity-owned Model Snapshot.' }
                $required = @()
                if (@('mapping_object', 'mapping_attribute', 'generated_code', 'generated_code_source_system') -ccontains $dataset.name) { $required = @('modeled_entity_schema_name') }
                foreach ($layer in @('logical', 'dimensional')) {
                    if (@(($layer + '_entity'), ($layer + '_attribute')) -ccontains $dataset.name) { $required = @($layer + '_entity_schema_name') }
                    if ($dataset.name -ceq ($layer + '_relationship')) { $required = @(('from_' + $layer + '_entity_schema_name'), ('to_' + $layer + '_entity_schema_name')) }
                }
                foreach ($field in $required) { if (@($dataset.canonical_key) -cnotcontains $field) { Fail 'Legacy Model Snapshot contract; fetch a new Entity-owned Model Snapshot.' } }
            }
            if ([string]::IsNullOrWhiteSpace([string]$dataset.name) -or $names.ContainsKey([string]$dataset.name)) {
                Fail 'Snapshot catalog contains an invalid or duplicate dataset.'
            }
            $names[[string]$dataset.name] = $dataset
            [void]$datasets.Add($dataset)
        }
    }
    Assert-SessionSnapshotIdentity $state $owner $area $manifest $catalog
    return [pscustomobject]@{
        Session = $session
        State = $state
        Owner = $owner
        Area = $area
        Root = $snapshotRoot
        Manifest = $manifest
        Catalog = $catalog
        Members = $members
        Datasets = @($datasets)
        ByName = $names
    }
}

function Assert-SessionSnapshotIdentity($State, $Owner, [string]$Area, $Manifest, $Catalog) {
    if ($Area -ceq 'metadata') {
        if ((Get-Property $Manifest 'tenant_code') -isnot [string] -or
            (Normalize-Value 'metadata' 'tenant_code' $Manifest.tenant_code) -cne (Normalize-Value 'metadata' 'tenant_code' $Owner.code) -or
            ((Test-Property $Manifest 'tenant_id') -and $Manifest.tenant_id -ne $Owner.id)) { Fail 'Metadata Snapshot owner does not match workspace owner.' }
        return
    }
    $model = Get-Property $Catalog 'model'
    if ($null -eq $State.model -or -not (Test-SafeJsonInteger (Get-Property $Manifest 'model_id') $false) -or
        $Manifest.model_id -ne $State.model.id -or (Get-Property $model 'model_id') -ne $Manifest.model_id -or
        (Get-Property $Manifest 'model_name') -isnot [string] -or [string]::IsNullOrWhiteSpace($Manifest.model_name) -or
        $model.model_name -cne $Manifest.model_name -or -not (Test-SafeJsonInteger (Get-Property $Manifest 'model_revision')) -or
        (Get-Property $model 'model_revision') -ne $Manifest.model_revision) { Fail 'Model identity/revision does not match workspace and Snapshot catalog.' }
    if ((Test-Property $model 'tenant_code') -and
        (Normalize-Value 'model' 'tenant_code' $model.tenant_code) -cne (Normalize-Value 'model' 'tenant_code' $State.tenant.code)) { Fail 'Model Snapshot belongs to another Tenant.' }
}

function Get-ChangeContext([hashtable]$Options) {
    $snapshot = Find-Snapshot $Options
    foreach ($entry in (Get-Property $snapshot.State 'refresh_required')) {
        if ($null -ne $entry -and $entry.area -ceq $snapshot.Area -and $entry.owner_tenant_id -eq $snapshot.Owner.id) { Fail 'Snapshot is known stale; refresh before editing.' }
    }
    $id = if ($Options.ContainsKey('task')) { $Options.task } else { Get-Property $snapshot.State 'active_task' }
    [void](Read-AtlasTask $snapshot.Session $id)
    $relative = (Get-OwnerPrefix $snapshot.Owner) + $snapshot.Area + '-change-set/.check'
    $directory = Split-Path -Parent (Resolve-WorkspacePath $snapshot.Session $relative $true)
    $snapshot | Add-Member -NotePropertyName TaskId -NotePropertyValue $id
    $snapshot | Add-Member -NotePropertyName ChangeDirectory -NotePropertyValue $directory
    return $snapshot
}

function Mark-Review($Context) {
    # Historical approval stays intact; changed bytes fail the operation digest check.
}

function Get-SnapshotBinding($Context) {
    $relative = (Join-Path $Context.Root 'manifest.json').Substring($Context.Session.Length + 1).Replace('\', '/')
    $binding = [ordered]@{ area = $Context.Area; owner_tenant_id = $Context.Owner.id; manifest_path = $relative;
        snapshot_id = $Context.Manifest.snapshot_id; manifest_sha256 = Get-FileDigest (Join-Path $Context.Root 'manifest.json') }
    if ($Context.Area -ceq 'model') { $binding.model_revision = $Context.Manifest.model_revision }
    return $binding
}
function Get-ValidationReportRelative($Context) {
    return '.atlas/tasks/' + $Context.TaskId + '.evidence/' + $Context.Area + '-' + $Context.Owner.id + '-validation.json'
}

function Validate-Changes([hashtable]$Options) {
    $context = Get-ChangeContext $Options
    $pending = Read-Pending $context
    $issues = New-Object System.Collections.ArrayList
    $states = New-Object System.Collections.ArrayList
    $metadata = $null
    $inputDigest = Get-WorkspaceDigest $context
    $inputs = New-Object Collections.ArrayList
    [void]$inputs.Add((Get-SnapshotBinding $context))
    $metadataStates = New-Object Collections.ArrayList
    $missingMetadataOwners = New-Object Collections.ArrayList
    foreach ($dataset in @($context.Datasets)) {
        $schema = Get-DatasetSchema $context $dataset
        $draft = @()
        if ($pending.ContainsKey([string]$dataset.name)) { $draft = @($pending[[string]$dataset.name]) }
        $baseline = @(Read-SnapshotRecords $context $dataset)
        $effective = @()
        $overlayError = $null
        try { $effective = @(Get-EffectiveRecords $context $dataset $draft) }
        catch {
            $overlayError = $_.Exception.Message
            $effective = @($baseline)
        }
        [void]$states.Add([pscustomobject]@{
            Area = $context.Area
            Dataset = $dataset
            Schema = $schema
            RecordType = Get-ValidationRecordType $dataset $schema
            Baseline = $baseline
            Pending = $draft
            Effective = $effective
            OverlayError = $overlayError
        })
    }
    Add-CommonValidationIssues $context.Area @($states) $issues
    if ($context.Area -ceq 'metadata') {
        Add-MetadataLockIssues @($states) $issues
        Add-MetadataUniqueIssues @($states) $issues
        Add-DeclaredReferenceIssues 'metadata' @($states) $issues
    }
    else {
        $owners = @{}; $owners[[string]$context.State.tenant.id] = Get-AtlasOwner $context.State 'metadata'
        foreach ($id in @(Get-PropertyNames (Get-Property $context.State 'metadata_owners'))) { $owners[$id] = Get-AtlasOwner $context.State 'metadata' $id }
        $merged = @{}
        foreach ($owner in $owners.Values) {
            foreach ($marker in (Get-Property $context.State 'refresh_required')) {
                if ($null -ne $marker -and $marker.area -ceq 'metadata' -and $marker.owner_tenant_id -eq $owner.id) { Fail 'Model validation needs refreshed Metadata inputs.' }
            }
            try { $snapshot = Find-Snapshot @{session = $context.Session; area = 'metadata'; owner = [string]$owner.id} }
            catch {
                if ($_.Exception.GetBaseException() -is [IO.FileNotFoundException]) {
                    [void]$missingMetadataOwners.Add($owner.id)
                    continue
                }
                throw
            }
            $metadata = $snapshot
            [void]$inputs.Add((Get-SnapshotBinding $snapshot))
            foreach ($dataset in @($snapshot.Datasets)) {
                $name = [string]$dataset.name
                if ($merged.ContainsKey($name) -and
                    (ConvertTo-StableJson @($merged[$name].Dataset.canonical_key)) -cne
                    (ConvertTo-StableJson @($dataset.canonical_key))) {
                    Fail 'Owner Snapshots disagree on dataset key contracts.'
                }
                if (-not $merged.ContainsKey($name)) { $merged[$name] = [ordered]@{ Dataset = $dataset; Schema = Get-DatasetSchema $snapshot $dataset; Rows = @{} } }
                foreach ($record in @(Read-SnapshotRecords $snapshot $dataset)) {
                    $key = Get-CanonicalKey 'metadata' $dataset $record
                    if ($merged[$name].Rows.ContainsKey($key) -and (ConvertTo-StableJson $merged[$name].Rows[$key]) -cne (ConvertTo-StableJson $record)) { Fail 'Owner Snapshots disagree on a shared record; refresh before validation.' }
                    $merged[$name].Rows[$key] = $record
                }
            }
        }
        $referenceStates = New-Object Collections.ArrayList
        foreach ($state in @($states)) { [void]$referenceStates.Add($state) }
        foreach ($entry in $merged.Values) {
            $records = @($entry.Rows.Values)
            $state = [pscustomobject]@{Area = 'metadata'; Dataset = $entry.Dataset; Schema = $entry.Schema; RecordType = Get-ValidationRecordType $entry.Dataset $entry.Schema; Baseline = $records; Pending = @(); Effective = $records; OverlayError = $null}
            [void]$referenceStates.Add($state); [void]$metadataStates.Add($state)
        }
        Add-ModelValidationIssues @($states) $issues @($referenceStates) $context.Owner.code
    }
    # A Metadata task can derive its scope from a Model. Bind every declared input,
    # even when that Snapshot is not needed by the Metadata record validator itself.
    $task = Read-AtlasTask $context.Session $context.TaskId
    $declared = Get-Property (Get-Property $task.value 'inputs') 'snapshots'
    if ($null -eq $declared) { $declared = @() }
    if ($declared -isnot [Array]) { Fail 'Task Snapshot bindings must be an array.' }
    $declaredDigest = ConvertTo-StableJson $declared
    foreach ($inputBinding in $declared) {
        if (-not (Test-AtlasObject $inputBinding) -or
            @('metadata', 'model') -cnotcontains (Get-Property $inputBinding 'area')) {
            Fail 'Invalid task Snapshot binding.'
        }
        $optionsForInput = @{session = $context.Session; area = $inputBinding.area}
        if (Test-Property $inputBinding 'owner_tenant_id') { $optionsForInput.owner = [string]$inputBinding.owner_tenant_id }
        $actual = Get-SnapshotBinding (Find-Snapshot $optionsForInput)
        foreach ($field in @(Get-PropertyNames $actual)) {
            if ((ConvertTo-StableJson (Get-Property $actual $field)) -cne
                (ConvertTo-StableJson (Get-Property $inputBinding $field))) {
                Fail 'Task Snapshot input changed; review its selection before validation.'
            }
        }
        if (@($inputs | Where-Object { $_.manifest_path -ceq $actual.manifest_path }).Count -eq 0) {
            [void]$inputs.Add($actual)
        }
    }
    $boundedIssues = @($issues | Select-Object -First 200)
    $issueOutput = New-Object Collections.ArrayList
    $repairs = New-Object Collections.ArrayList
    foreach ($issue in $boundedIssues) {
        [void]$issueOutput.Add(@($issue.Issue))
        $message = [string]$issue.Detail
        $fields = New-Object Collections.ArrayList
        if ($issue.Field -is [string] -and -not [string]::IsNullOrWhiteSpace($issue.Field)) {
            [void]$fields.Add([string]$issue.Field)
        }
        $path = [regex]::Match($message, '\$(?<path>(?:\.[^.\[\]]+|\[\d+\])*)')
        if ($path.Success) {
            foreach ($part in [regex]::Matches($path.Groups['path'].Value, '\.([^.\[\]]+)|\[(\d+)\]')) {
                $field = if ($part.Groups[1].Success) { $part.Groups[1].Value } else { $part.Groups[2].Value }
                if (@($fields) -cnotcontains $field) { [void]$fields.Add($field) }
            }
        }
        [void]$repairs.Add([ordered]@{
            dataset = [string]$issue.Dataset
            record = $issue.Record
            code = [string]$issue.Code
            fields = @($fields)
            message = $message
        })
    }
    $reportIssues = New-Object Collections.ArrayList
    foreach ($repair in @($repairs)) {
        [void]$reportIssues.Add([ordered]@{ severity = 'error'; dataset = $repair.dataset; record = $repair.record; code = $repair.code; fields = @($repair.fields); message = $repair.message })
    }
    $substantiveModelEdits = @($states | Where-Object {
        $_.Dataset.name -cne 'model_details' -and @($_.Pending).Count -gt 0
    }).Count -gt 0
    foreach ($ownerId in $missingMetadataOwners) {
        [void]$reportIssues.Add([ordered]@{
            severity = $(if ($substantiveModelEdits) { 'error' } else { 'warning' })
            dataset = 'model'; record = $null; code = 'metadata_owner_snapshot_missing'; fields = @()
            message = "Applied Metadata for owner $ownerId is unavailable; physical context completeness needs review."
        })
    }
    $checks = New-Object Collections.ArrayList
    foreach ($id in @('local.schema', 'local.identity', 'local.state', 'local.scope', 'local.references')) { [void]$checks.Add([ordered]@{ id = $id; status = 'ran' }) }
    if ($context.Area -ceq 'model') {
        $structural = @($issues | Where-Object { @('schema', 'canonical_key', 'effective_overlay') -ccontains $_.Code }).Count -gt 0
        if (-not $structural) {
            foreach ($issue in @(Get-AtlasModelPolicy @($states) @($metadataStates) (Get-Property $context.Catalog 'model'))) { [void]$reportIssues.Add($issue) }
            foreach ($issue in @(Get-AtlasGeneratedCodeIssues @($states))) { [void]$reportIssues.Add($issue) }
            [void]$checks.Add([ordered]@{id = 'model.authoring-policy'; status = 'ran'})
        }
        else { [void]$checks.Add([ordered]@{id = 'model.authoring-policy'; status = 'not_run'; reason = 'Repair structural errors first.'}) }
    }
    $quality = $null; $evidenceFiles = @()
    if ($context.Area -ceq 'model') {
        $decisions = $null; $noteFiles = @{}
        if (@($pending.Keys | Where-Object { $script:ModelingQualityDatasets -ccontains $_ }).Count -gt 0) {
            $evidence = Read-ModelingDecisions $context.Session $context.TaskId
            $decisions = $evidence.decisions; $noteFiles = $evidence.noteFiles; $evidenceFiles = @($evidence.files)
        }
        $quality = Get-ModelingQuality @($states) $decisions $noteFiles @($metadataStates)
        foreach ($level in @('errors', 'warnings')) {
            foreach ($issue in @($quality[$level])) {
                [void]$reportIssues.Add([ordered]@{severity = $(if ($level -ceq 'errors') {'error'} else {'warning'}); dataset = $issue.dataset; record = $null; code = $issue.code; fields = @(); message = $issue.message})
            }
        }
        [void]$checks.Add([ordered]@{id = 'local.evidence'; status = $(if ($quality.required) {'ran'} else {'not_required'})})
    }
    else { [void]$checks.Add([ordered]@{id = 'local.evidence'; status = 'not_run'; reason = 'Modeling evidence is not applicable.'}) }
    [void]$checks.Add([ordered]@{id = 'local.meaning'; status = 'review_required'; reason = 'Business meaning requires agent and user review.'})
    [void]$checks.Add([ordered]@{id = 'server.authorization'; status = 'server_only'})
    [void]$checks.Add([ordered]@{id = 'server.validation'; status = 'server_only'})
    $currentTask = Read-AtlasTask $context.Session $context.TaskId
    $currentDeclared = Get-Property (Get-Property $currentTask.value 'inputs') 'snapshots'
    if ($null -eq $currentDeclared) { $currentDeclared = @() }
    if ((ConvertTo-StableJson $currentDeclared) -cne $declaredDigest) {
        Fail 'Task Snapshot inputs changed during validation.'
    }
    if ((Get-WorkspaceDigest $context) -cne $inputDigest) { Fail 'Validation inputs changed; run validation again.' }
    foreach ($binding in $inputs) { if ((Get-FileDigest (Resolve-WorkspacePath $context.Session $binding.manifest_path)) -cne $binding.manifest_sha256) { Fail 'Validation inputs changed; run validation again.' } }
    $binding = $inputs[0]
    $issueCount = $issues.Count - $boundedIssues.Count + $reportIssues.Count
    $valid = $issues.Count -eq 0 -and @($reportIssues | Where-Object { $_.severity -ceq 'error' }).Count -eq 0
    $report = [ordered]@{schema_version = '1.0'; run_by = 'agent'; area = $context.Area; owner_tenant_id = $context.Owner.id;
        generated_at = [DateTimeOffset]::UtcNow.ToString('o'); digest = $inputDigest; inputs = @($inputs);
        snapshot = [ordered]@{id = $binding.snapshot_id; revision = Get-Property $context.Manifest 'model_revision'; manifest_digest = $binding.manifest_sha256};
        valid = $valid; checks = @($checks); issue_count = $issueCount; truncated = $issueCount -gt 200;
        issues = @($reportIssues | Select-Object -First 200); quality = $quality; evidence_files = $evidenceFiles}
    $relative = Get-ValidationReportRelative $context
    $file = Resolve-WorkspacePath $context.Session $relative $true
    $expected = if (Test-Path -LiteralPath $file) { (Read-WorkspaceJson $context.Session $relative).digest } else { 'absent' }
    [void](Write-WorkspaceJson $context.Session $relative $report $expected)
    $report.report = $relative
    return $report
}

function Accept-Changes([hashtable]$Options) {
    $context = Get-ChangeContext $Options
    if ($Options.digest -cnotmatch $script:AtlasDigest -or (Get-WorkspaceDigest $context) -cne $Options.digest) { Fail 'Acknowledged digest does not match local files.' }
    $backend = [ordered]@{profile = $Options['backend-profile']; endpoint_sha256 = $Options['endpoint-sha256']}
    if ($Options['backend-file']) {
        if ($Options.ContainsKey('backend-profile') -or $Options.ContainsKey('endpoint-sha256')) { Fail 'Use --backend-file or explicit backend flags, not both.' }
        $check = Read-AtlasResponse $Options['backend-file']
        if ((Get-Property $check 'schema_version') -isnot [string] -or (Get-Property $check 'schema_version') -cne '1.0' -or (Get-Property $check 'status') -cne 'ready' -or -not (Test-AtlasObject (Get-Property $check 'backend'))) { Fail 'Backend check did not return readiness.' }
        $backend = [ordered]@{profile = Get-Property $check.backend 'profile'; endpoint_sha256 = Get-Property $check.backend 'endpoint_sha256'}
    }
    if (@('production', 'local', 'azureLocalTest') -cnotcontains $backend.profile -or [string]$backend.endpoint_sha256 -cnotmatch $script:AtlasDigest) { Fail 'Supply safe backend identity from Check Stage Runner.' }
    if ($Options.ContainsKey('prepare-stage') -and $Options['prepare-stage'] -cne 'true') { Fail '--prepare-stage must be true when supplied.' }
    $validation = Validate-Changes $Options
    if (-not $validation.valid) { Fail 'Fix local validation findings before acknowledgement.' }
    $stateDocument = Read-SessionDocument $context.Session; $prior = $null
    try { $prior = Read-AtlasOperation $context.Session $stateDocument.value $context.Area $context.Owner }
    catch { if ($_.Exception.Message -cne 'A digest-bound acknowledgement is required first.') { throw } }
    if ($null -ne $prior) {
        if ((Get-Property (Get-Property $prior.value 'stage_attempt') 'status') -ceq 'unknown') { Fail 'Prior Stage result is uncertain; inspect it before accepting another operation.' }
        if ((Get-Property $prior.value 'stage') -and -not (Get-Property $prior.value 'apply') -and -not (Get-Property (Get-Property $prior.value 'draft') 'validation_failed')) { Fail 'Previous Stage needs validation/Apply or explicit reconciliation before new acceptance.' }
    }
    $priorValue = Get-Property $prior 'value'
    $priorDraft = if (Get-Property $priorValue 'apply') { $null } else { Get-Property $priorValue 'draft' }
    $draft = if ((Get-Property $priorDraft 'validation_failed') -eq $true -or (Get-Property $priorValue 'local_digest') -ceq $Options.digest) { $priorDraft } else { $null }
    if ($Options['draft-file']) { $draft = Resolve-AtlasServerDraft $Options $context.Owner $context.State $priorDraft $Options.digest }
    if ($Options['prepare-stage'] -ceq 'true' -and (-not $draft -or $draft.status -cne 'active' -or @((Read-Pending $context).Keys).Count -eq 0)) { Fail 'Preparing Stage requires an active verified server draft and local datasets; supply --draft-file or accept first, then cache the draft.' }
    $id = [Guid]::NewGuid().ToString(); $relative = '.atlas/tasks/' + $context.TaskId + '.evidence/' + $id + '.json'
    $savedReport = '.atlas/tasks/' + $context.TaskId + '.evidence/' + $id + '.validation.json'
    $report = Read-WorkspaceJson $context.Session $validation.report
    $reportHash = Write-WorkspaceJson $context.Session $savedReport $report.value
    $operation = [ordered]@{schema_version = '1.0'; id = $id; task_id = $context.TaskId; area = $context.Area; owner = $context.Owner;
        backend = $backend; inputs = $validation.inputs;
        local_digest = $Options.digest; validation = [ordered]@{outcome = 'valid'; report_path = $savedReport; report_sha256 = $reportHash; checks = $validation.checks};
        acknowledgement = [ordered]@{source = 'conversation'; at = [DateTimeOffset]::UtcNow.ToString('o'); digest = $Options.digest; report_sha256 = $reportHash}}
    if ($draft) { $operation.draft = $draft }
    [void](Write-WorkspaceJson $context.Session $relative $operation)
    $operations = Get-Property $stateDocument.value 'operations'
    if ($null -eq $operations) { $operations = @{}; Set-Property $stateDocument.value 'operations' $operations }
    if ($context.Area -ceq 'model') { Set-Property $operations 'model' $relative }
    else {
        $metadata = Get-Property $operations 'metadata'
        if ($null -eq $metadata) { $metadata = @{}; Set-Property $operations 'metadata' $metadata }
        Set-Property $metadata ([string]$context.Owner.id) $relative
    }
    [void](Write-WorkspaceJson $context.Session '.atlas/session.json' $stateDocument.value $stateDocument.digest)
    $result = [ordered]@{operation_id = $id; task_id = $context.TaskId; accepted_digest = $Options.digest; operation = $id; path = $relative; task = $context.TaskId; digest = $Options.digest}
    if ($Options['prepare-stage'] -ceq 'true') {
        $prepareOptions = $Options.Clone(); [void]$prepareOptions.Remove('draft-file')
        $prepared = Prepare-StageRequest $prepareOptions
        foreach ($key in $prepared.Keys) { $result[$key] = $prepared[$key] }
    }
    return $result
}

function Resolve-AtlasServerDraft([hashtable]$Options, $Owner, $State, $Previous, [string]$AcceptedDigest) {
    if ($Options['file'] -or $Options['draft-file']) {
        foreach ($name in @('id', 'revision', 'status', 'validation-failed')) {
            if ($Options.ContainsKey($name)) { Fail 'Use a draft response file or explicit draft flags, not both.' }
        }
        $file = if ($Options['draft-file']) { $Options['draft-file'] } else { $Options['file'] }
        $response = ConvertTo-AtlasServerResponse (Read-AtlasResponse $file) $Options.area $Owner (Get-Property (Get-Property $State 'model') 'id')
        $id = $response.change_set_id; $revision = $response.draft_revision; $status = Get-Property $response 'status'
        if ($revision -lt 1) { Fail 'Server draft responses require a positive revision.' }
    }
    else {
        $id = $Options.id; [double]$revision = 0; $status = $Options.status
        if (-not [double]::TryParse($Options.revision, [ref]$revision)) { Fail 'Invalid server draft identity/revision/status.' }
    }
    if ([string]$id -cnotmatch $script:AtlasUuid -or -not (Test-SafeJsonInteger $revision) -or @('active', 'validated') -cnotcontains $status) { Fail 'Invalid server draft identity/revision/status.' }
    if ($Previous -and $Previous.id -cne $id) { Fail 'Operation cannot be rebound to another server draft.' }
    if ($Previous -and $revision -lt $Previous.revision) { Fail 'Server revision cannot go backwards.' }
    $validationFailed = ((Get-Property $Previous 'validation_failed') -is [bool] -and (Get-Property $Previous 'validation_failed') -eq $true) -or $Options['validation-failed'] -ceq 'true'
    $digest = if ($validationFailed -and $Previous -and (Get-Property $Previous 'digest')) { $Previous.digest } else { $AcceptedDigest }
    $draft = [ordered]@{id = $id; revision = $revision; status = $status; digest = $digest}
    if ($validationFailed) { $draft.validation_failed = $true }
    return $draft
}

function Set-DraftCache([hashtable]$Options) {
    $root = Resolve-Session $Options; $state = Read-SessionState $root; $owner = Get-AtlasOwner $state $Options.area $Options['owner']
    $document = Read-AtlasOperation $root $state $Options.area $owner; $operation = $document.value
    $draft = Resolve-AtlasServerDraft $Options $owner $state (Get-Property $operation 'draft') $operation.local_digest
    Set-Property $operation 'draft' $draft
    [void](Write-WorkspaceJson $root $document.relative $operation $document.digest)
    return [ordered]@{operation_id = $operation.id; change_set_id = $draft.id; draft_revision = $draft.revision; operation = $operation.id; draft = $draft}
}

function Assert-OperationInputs([string]$Root, $Operation) {
    foreach ($binding in $Operation.inputs) {
        if ((Get-FileDigest (Resolve-WorkspacePath $Root $binding.manifest_path)) -cne $binding.manifest_sha256) { Fail 'Snapshot changed after acknowledgement.' }
    }
    $report = Read-WorkspaceJson $Root $Operation.validation.report_path
    if ($report.digest -cne $Operation.validation.report_sha256 -or $report.value.valid -ne $true) { Fail 'Validation report changed after acknowledgement.' }
    foreach ($evidence in (Get-Property $report.value 'evidence_files')) {
        if ($null -eq $evidence) { continue }
        $file = Resolve-WorkspacePath $Root $evidence.path
        $exists = Test-Path -LiteralPath $file
        if ($null -eq $evidence.sha256) { if ($exists) { Fail 'Modeling evidence changed after acknowledgement.' } }
        elseif (-not $exists -or (Get-FileDigest $file) -cne $evidence.sha256) { Fail 'Modeling evidence changed after acknowledgement.' }
    }
}

function Prepare-StageRequest([hashtable]$Options) {
    $context = Get-ChangeContext $Options; $document = Read-AtlasOperation $context.Session $context.State $context.Area $context.Owner; $operation = $document.value
    if ((Get-WorkspaceDigest $context) -cne $operation.local_digest) { Fail 'Local files changed after acknowledgement.' }
    Assert-OperationInputs $context.Session $operation
    if ((Get-Property (Get-Property $operation 'stage_attempt') 'status') -ceq 'unknown') { Fail 'Stage result is uncertain; inspect before retrying.' }
    if ($Options['draft-file']) {
        $draft = Resolve-AtlasServerDraft $Options $context.Owner $context.State (Get-Property $operation 'draft') $operation.local_digest
        if ($draft.status -cne 'active') { Fail 'Stage requires an active server draft.' }
        Set-Property $operation 'draft' $draft
        [void](Write-WorkspaceJson $context.Session $document.relative $operation $document.digest)
        $document = Read-AtlasOperation $context.Session $context.State $context.Area $context.Owner; $operation = $document.value
    }
    $draft = Get-Property $operation 'draft'
    if (-not $draft -or $draft.status -cne 'active') { Fail 'Supply --draft-file with the active server draft, or cache it before preparing Stage.' }
    $pending = Read-Pending $context; $names = @($pending.Keys | Sort-Object)
    if ($names.Count -eq 0) { Fail 'No local datasets to Stage.' }
    $relative = '.atlas/tasks/' + $operation.task_id + '.evidence/' + $operation.id + '.stage-request.json'
    $binding = Get-SnapshotBinding $context
    $target = [ordered]@{}
    if ($context.Area -ceq 'metadata') { $target.tenant_code = $context.Owner.code }
    else { $target.model_id = $context.Manifest.model_id; $target.model_name = $context.Manifest.model_name; $target.model_revision = $context.Manifest.model_revision }
    $target.change_set_id = $draft.id; $target.starting_revision = $draft.revision
    $datasets = New-Object Collections.ArrayList
    foreach ($name in $names) {
        $payload = (Get-OwnerPrefix $context.Owner) + $context.Area + '-change-set/' + $name + '.json'
        [void]$datasets.Add([ordered]@{dataset = $name; canonical_key = @($context.ByName[$name].canonical_key); record_count = @($pending[$name]).Count;
            payload_file = $payload; sha256 = Get-FileDigest (Resolve-WorkspacePath $context.Session $payload)})
    }
    $manifest = [ordered]@{schema_version = '1.0'; kind = 'atlas-stage-request'; area = $context.Area; task = $operation.task_id;
        accepted_digest = $operation.local_digest; failed_retry = ((Get-Property $draft 'validation_failed') -eq $true -and $draft.digest -cne $operation.local_digest);
        operation = [ordered]@{id = $operation.id; path = $document.relative}; owner = $context.Owner; backend = $operation.backend;
        snapshot = [ordered]@{snapshot_id = $binding.snapshot_id; manifest_sha256 = $binding.manifest_sha256; manifest_path = $binding.manifest_path}; target = $target; datasets = @($datasets)}
    $file = Resolve-WorkspacePath $context.Session $relative
    $expected = if (Test-Path -LiteralPath $file) { (Read-WorkspaceJson $context.Session $relative).digest } else { 'absent' }
    $hash = Write-WorkspaceJson $context.Session $relative $manifest $expected
    Set-Property $operation 'stage_request' ([ordered]@{path = $relative; sha256 = $hash})
    [void](Write-WorkspaceJson $context.Session $document.relative $operation $document.digest)
    return [ordered]@{stage_manifest_path = $file; operation_id = $operation.id; task_id = $operation.task_id;
        change_set_id = $draft.id; draft_revision = $draft.revision; manifest = $file; accepted_digest = $operation.local_digest; operation = $operation.id; dataset_count = $names.Count}
}

function Record-Operation([hashtable]$Options) {
    $root = Resolve-Session $Options; $state = Read-SessionState $root; $owner = Get-AtlasOwner $state $Options.area $Options['owner']
    $document = Read-AtlasOperation $root $state $Options.area $owner; $operation = $document.value; $draft = Get-Property $operation 'draft'
    if (-not $draft) { Fail 'Operation has no bound server draft.' }
    if ($Options.ContainsKey('digest-from-operation') -and ($Options['digest-from-operation'] -cne 'true' -or $Options.checkpoint -cne 'apply-approval' -or $Options.ContainsKey('review-digest'))) { Fail 'Use --digest-from-operation true only for Apply approval, instead of --review-digest.' }
    $modelId = Get-Property (Get-Property $state 'model') 'id'
    if ($Options['file']) { $response = ConvertTo-AtlasServerResponse (Read-AtlasResponse $Options['file']) $Options.area $owner $modelId }
    elseif ($Options.checkpoint -ceq 'apply-approval' -and (Get-Property $operation 'server_validation')) {
        $saved = Read-WorkspaceJson $root $operation.server_validation.path
        if ($saved.digest -cne $operation.server_validation.sha256 -or (Get-Property $saved.value 'area') -cne $Options.area -or (Get-Property $saved.value 'owner_tenant_id') -ne $owner.id) { Fail 'Server review changed or belongs to another owner.' }
        if ($Options.area -ceq 'model' -and -not (Test-Property $saved.value 'model_id')) { Set-Property $saved.value 'model_id' $modelId }
        $response = ConvertTo-AtlasServerResponse $saved.value $Options.area $owner $modelId
    }
    else { Fail '--file is required for a server validation or Apply result.' }
    $changeId = $response.change_set_id
    $correctOwner = if ($Options.area -ceq 'metadata') { (Get-Property $response 'tenant_id') -eq $owner.id } else { (Get-Property $response 'model_id') -eq $state.model.id }
    if ($changeId -cne $draft.id -or (Get-Property $response 'draft_revision') -ne $draft.revision -or -not $correctOwner) { Fail 'Server result does not match the bound owner/draft/revision.' }
    $stage = ConvertTo-AtlasStageReceipt (Get-Property $operation 'stage')
    if (-not $stage -or (Get-Property $stage 'status') -cne 'staged' -or ((Get-Property $stage 'fingerprint_verified') -isnot [bool] -or (Get-Property $stage 'fingerprint_verified') -ne $true) -or (Get-Property $stage 'accepted_digest') -cne $operation.local_digest -or
        (Get-Property $stage 'change_set_id') -cne $draft.id -or (-not (Test-SafeJsonInteger (Get-Property $stage 'draft_revision')) -or (Get-Property $stage 'draft_revision') -ne $draft.revision) -or [string](Get-Property $stage 'stage_fingerprint') -cnotmatch $script:AtlasDigest -or
        (Get-Property (Get-Property $operation 'stage_attempt') 'status') -ceq 'unknown') { Fail 'Resolve and verify Stage before recording server validation or Apply.' }
    Set-Property $operation 'stage' $stage
    if ((Get-Property $operation 'apply') -and $Options.checkpoint -cne 'apply') { Fail 'Applied operation history cannot return to an earlier checkpoint.' }
    if ($Options.checkpoint -ceq 'apply-approval') {
        $contextOptions = $Options.Clone(); $contextOptions.task = $operation.task_id
        if ((Get-WorkspaceDigest (Get-ChangeContext $contextOptions)) -cne $operation.local_digest) { Fail 'Local work changed after review; reconcile it before Apply approval.' }
        Assert-OperationInputs $root $operation
    }
    switch ($Options.checkpoint) {
        'validation' {
            if ((Get-Property $response 'valid') -isnot [bool] -or ($response.valid -and ([string](Get-Property $response 'candidate_digest') -cnotmatch $script:AtlasDigest -or $response.status -cne 'validated' -or (Get-Property $response 'error_count') -ne 0)) -or
                @('active', 'validated') -cnotcontains (Get-Property $response 'status') -or -not (Test-SafeJsonInteger (Get-Property $response 'error_count')) -or (Get-Property $response 'action_review') -isnot [Array]) { Fail 'Invalid server validation result.' }
            $relative = '.atlas/tasks/' + $operation.task_id + '.evidence/' + $operation.id + '.server-validation.json'
            $saved = [ordered]@{area = $Options.area; owner_tenant_id = $owner.id; change_set_id = $changeId}
            if ($Options.area -ceq 'metadata') { $saved.tenant_id = $owner.id } else { $saved.model_id = $modelId }
            foreach ($key in @('schema_version', 'draft_revision', 'valid', 'status', 'candidate_digest', 'error_count', 'action_review', 'validated_at', 'expires_at')) {
                if (Test-Property $response $key) { $saved[$key] = Get-Property $response $key }
            }
            $file = Resolve-WorkspacePath $root $relative
            $expected = if (Test-Path -LiteralPath $file) { (Read-WorkspaceJson $root $relative).digest } else { 'absent' }
            $hash = Write-WorkspaceJson $root $relative $saved $expected
            Set-Property $operation 'server_validation' ([ordered]@{path = $relative; sha256 = $hash; valid = $response.valid; candidate_digest = Get-Property $response 'candidate_digest'; revision = $response.draft_revision})
            Set-Property $draft 'status' $response.status; Set-Property $draft 'validation_failed' (-not $response.valid)
        }
        'apply-approval' {
            $validation = Get-Property $operation 'server_validation'
            $reviewDigest = if ($Options['digest-from-operation'] -ceq 'true') { Get-Property $validation 'sha256' } else { $Options['review-digest'] }
            if (-not (Get-Property $validation 'valid') -or $reviewDigest -cne $validation.sha256) { Fail 'Separate Apply acknowledgement must bind the current complete server review.' }
            $savedReview = Read-WorkspaceJson $root $validation.path
            if ($savedReview.digest -cne $validation.sha256) { Fail 'Server review changed.' }
            if ((Get-Property $response 'valid') -isnot [bool] -or (Get-Property $response 'valid') -ne $true -or (Get-Property $response 'status') -cne 'validated' -or
                (Get-Property $response 'candidate_digest') -cne $validation.candidate_digest -or (ConvertTo-StableJson (Get-Property $response 'action_review')) -cne (ConvertTo-StableJson (Get-Property $savedReview.value 'action_review'))) { Fail 'Apply acknowledgement must use the current complete server review.' }
            Set-Property $operation 'apply_approval' ([ordered]@{source = 'conversation'; at = [DateTimeOffset]::UtcNow.ToString('o'); review_sha256 = $validation.sha256; revision = $draft.revision; candidate_digest = $validation.candidate_digest})
        }
        'apply' {
            $approval = Get-Property $operation 'apply_approval'
            if ((Get-Property $response 'applied') -isnot [bool] -or (Get-Property $response 'applied') -ne $true -or (Get-Property $response 'status') -cne 'applied' -or ($Options.area -ceq 'metadata' -and ((Get-Property $response 'valid') -isnot [bool] -or (Get-Property $response 'valid') -ne $true)) -or -not $approval -or
                (Get-Property $response 'candidate_digest') -cne $approval.candidate_digest) { Fail 'Apply result does not match a separately approved validated candidate.' }
            $applied = [ordered]@{applied = $true; status = 'applied'; draft_revision = $response.draft_revision; candidate_digest = $response.candidate_digest;
                applied_at = Get-Property $response 'applied_at'; action_count = Get-Property $response 'action_count'}
            if (Test-Property $response 'model_revision') { $applied.model_revision = $response.model_revision }
            Set-Property $operation 'apply' $applied
        }
        default { Fail 'Checkpoint must be validation, apply-approval or apply.' }
    }
    [void](Write-WorkspaceJson $root $document.relative $operation $document.digest)
    $isApplied = [bool](Get-Property $operation 'apply')
    if ($isApplied) {
        $latest = Read-SessionDocument $root
        $markers = @((Get-Property $latest.value 'refresh_required') | Where-Object { $null -ne $_ })
        if (@($markers | Where-Object { $_.area -ceq $Options.area -and $_.owner_tenant_id -eq $owner.id }).Count -eq 0) {
            $markers += @([ordered]@{area = $Options.area; owner_tenant_id = $owner.id; reason = 'Applied changes require a fresh Snapshot.'; evidence = $document.relative})
        }
        Set-Property $latest.value 'refresh_required' $markers
        [void](Write-WorkspaceJson $root '.atlas/session.json' $latest.value $latest.digest)
    }
    return [ordered]@{operation_id = $operation.id; change_set_id = $draft.id; draft_revision = $draft.revision; operation = $operation.id; checkpoint = $Options.checkpoint; refresh_required = $isApplied}
}

function Install-Snapshot([hashtable]$Options) {
    $session = Resolve-Session $Options; $state = Read-SessionState $session; $area = Require-Option $Options 'area'; $owner = Get-AtlasOwner $state $area $Options['owner']
    if ($Options['snapshot-id'] -cnotmatch $script:AtlasUuid -or $Options.sha256 -cnotmatch $script:AtlasDigest) { Fail 'Snapshot ID and SHA-256 are required.' }
    $archive = Get-Item -LiteralPath ([IO.Path]::GetFullPath((Require-Option $Options 'archive'))) -Force -ErrorAction Stop
    [long]$size = 0
    if (-not [long]::TryParse($Options['size-bytes'], [ref]$size) -or $archive.PSIsContainer -or
        ($archive.Attributes -band [IO.FileAttributes]::ReparsePoint) -or $archive.Length -ne $size -or (Get-FileDigest $archive.FullName) -cne $Options.sha256) { Fail 'Snapshot archive identity/size/hash mismatch.' }
    $pendingDirectory = Split-Path -Parent (Resolve-WorkspacePath $session ((Get-OwnerPrefix $owner) + $area + '-change-set/.check') $true)
    $pendingNames = @(Get-ChildItem -LiteralPath $pendingDirectory -Force)
    $applied = $null
    foreach ($file in $pendingNames) {
        if ($file.PSIsContainer -or ($file.Attributes -band [IO.FileAttributes]::ReparsePoint) -or -not $file.Name.EndsWith('.json')) { Fail 'Unexpected local draft entry.' }
        $records = ConvertFrom-GdsJson ([IO.File]::ReadAllText($file.FullName, [Text.Encoding]::UTF8))
        if ($records -isnot [Array]) { Fail 'Pending dataset must contain an array.' }
        if ($records.Count -gt 0) {
            $applied = Read-AtlasOperation $session $state $area $owner
            if ((Get-Property (Get-Property $applied.value 'apply') 'applied') -ne $true) { Fail 'Preserve local drafts; Apply or reconcile them before replacing the Snapshot.' }
        }
    }
    if ($null -eq $applied -and @((Get-Property $state 'refresh_required') | Where-Object { $null -ne $_ -and $_.area -ceq $area -and $_.owner_tenant_id -eq $owner.id }).Count -gt 0) {
        $previous = Read-AtlasOperation $session $state $area $owner
        if ((Get-Property (Get-Property $previous.value 'apply') 'applied') -eq $true) { $applied = $previous }
    }
    $temporary = Split-Path -Parent (Resolve-WorkspacePath $session ('.atlas/temp/snapshot-' + [Guid]::NewGuid().ToString() + '/.check') $true)
    $extracted = Join-Path $temporary 'incoming'; [void][IO.Directory]::CreateDirectory($extracted)
        Add-Type -AssemblyName System.IO.Compression
        Add-Type -AssemblyName System.IO.Compression.FileSystem
        $zip = [IO.Compression.ZipFile]::OpenRead($archive.FullName)
        try {
            if ($zip.Entries.Count -lt 1 -or $zip.Entries.Count -gt 4096) {
                Fail 'Snapshot ZIP member count is invalid.'
            }
            $seen = New-Object 'System.Collections.Generic.HashSet[string]' ([StringComparer]::Ordinal)
            [long]$expandedBytes = 0
            foreach ($entry in @($zip.Entries)) {
                $name = [string]$entry.FullName
                $isDirectory = $name.EndsWith('/', [StringComparison]::Ordinal)
                $safeName = if ($isDirectory) { $name.TrimEnd('/') } else { $name }
                Assert-SafeSnapshotMemberPath $safeName
                if (-not $seen.Add($safeName)) { Fail "Snapshot ZIP contains duplicate member path $safeName." }
                $unixType = ([int64]$entry.ExternalAttributes -shr 16) -band 0xF000
                if (@(0, 0x8000, 0x4000) -notcontains $unixType -or
                    ([int64]$entry.ExternalAttributes -band [int][IO.FileAttributes]::ReparsePoint)) {
                    Fail 'Snapshot ZIP may not contain symbolic links.'
                }
                if ($isDirectory) { continue }
                $expandedBytes += [long]$entry.Length
                if ($expandedBytes -gt 512MB) { Fail 'Snapshot ZIP expands beyond the local safety limit.' }
                $target = [IO.Path]::GetFullPath((Join-Path $extracted ($safeName.Replace('/', [IO.Path]::DirectorySeparatorChar))))
                $prefix = $extracted.TrimEnd([IO.Path]::DirectorySeparatorChar) + [IO.Path]::DirectorySeparatorChar
                if (-not $target.StartsWith($prefix, [StringComparison]::Ordinal)) {
                    Fail 'Snapshot ZIP member escapes its extraction directory.'
                }
                [void][IO.Directory]::CreateDirectory([IO.Path]::GetDirectoryName($target))
                $inputStream = $entry.Open()
                try {
                    $outputStream = New-Object IO.FileStream($target, [IO.FileMode]::CreateNew, [IO.FileAccess]::Write, [IO.FileShare]::None)
                    try {
                        $buffer = New-Object byte[] 65536; [long]$copied = 0
                        while (($read = $inputStream.Read($buffer, 0, $buffer.Length)) -gt 0) {
                            $copied += $read
                            if ($copied -gt $entry.Length) { Fail 'Snapshot member exceeds its declared size.' }
                            $outputStream.Write($buffer, 0, $read)
                        }
                        if ($copied -ne $entry.Length) { Fail 'Snapshot member size mismatch.' }
                    }
                    finally { $outputStream.Dispose() }
                }
                finally { $inputStream.Dispose() }
            }
        }
        finally { if ($null -ne $zip) { $zip.Dispose() } }

        $candidateRoots = New-Object System.Collections.Generic.List[string]
        if ((Test-Path -LiteralPath (Join-Path $extracted 'manifest.json') -PathType Leaf) -and
            (Test-Path -LiteralPath (Join-Path $extracted 'catalog.json') -PathType Leaf)) {
            [void]$candidateRoots.Add($extracted)
        }
        foreach ($child in @(Get-ChildItem -LiteralPath $extracted -Directory -Force)) {
            if ($child.Attributes -band [IO.FileAttributes]::ReparsePoint) { continue }
            if ((Test-Path -LiteralPath (Join-Path $child.FullName 'manifest.json') -PathType Leaf) -and
                (Test-Path -LiteralPath (Join-Path $child.FullName 'catalog.json') -PathType Leaf)) {
                [void]$candidateRoots.Add($child.FullName)
            }
        }
        if ($candidateRoots.Count -ne 1) {
            Fail 'Snapshot ZIP must contain exactly one Snapshot root.'
        }

    $candidate = Read-SnapshotRoot $candidateRoots[0] $session $state $owner $area
    if ($candidate.Manifest.snapshot_id -cne $Options['snapshot-id']) { Fail 'Extracted Snapshot ID mismatch.' }
    if ($area -ceq 'model') {
        $previousManifest = Join-Path $session 'model/model-snapshot/manifest.json'
        $previousRevision = if (Test-Path -LiteralPath $previousManifest) { (Read-WorkspaceJson $session 'model/model-snapshot/manifest.json').value.model_revision } else { 0 }
        $appliedRevision = if ($null -ne $applied) { Get-Property (Get-Property $applied.value 'apply') 'model_revision' } else { 0 }
        if ($candidate.Manifest.model_revision -lt [Math]::Max([double]$previousRevision, [double]$appliedRevision)) { Fail 'Refreshed Model Snapshot is older than the known Model revision.' }
    }
    foreach ($member in $candidate.Members.Keys) { [void](Resolve-Member $candidate.Root $member $candidate.Members) }
    $retire = New-Object Collections.ArrayList
    if ($null -ne $applied) {
        foreach ($file in $pendingNames) {
            $name = [IO.Path]::GetFileNameWithoutExtension($file.Name)
            if (-not $candidate.ByName.ContainsKey($name)) { Fail 'Applied dataset missing from refreshed Snapshot.' }
            $definition = $candidate.ByName[$name]; $schema = Get-DatasetSchema $candidate $definition
            $baseline = @{}
            foreach ($row in @(Read-SnapshotRecords $candidate $definition)) { $baseline[(Get-CanonicalKey $area $definition $row)] = $row }
            $pending = @(Read-Json $file.FullName 'Pending dataset'); $remaining = New-Object Collections.ArrayList
            foreach ($row in $pending) {
                $key = Get-CanonicalKey $area $definition $row
                if (-not $baseline.ContainsKey($key) -or -not (Test-AppliedRecordEqual $row $baseline[$key] $schema)) { [void]$remaining.Add($row) }
            }
            [void]$retire.Add([ordered]@{name = $file.Name; remaining = @($remaining); digest = Get-FileDigest $file.FullName})
        }
    }
    $relative = (Get-OwnerPrefix $owner) + $area + '/' + $area + '-snapshot'
    $destination = Resolve-WorkspacePath $session $relative $true; $backup = Join-Path $temporary 'previous'
    $existed = Test-Path -LiteralPath $destination
    if ($existed) { [void](Resolve-RegularDirectory $destination 'Previous Snapshot'); [IO.Directory]::Move($destination, $backup) }
    try { [IO.Directory]::Move($candidate.Root, $destination) }
    catch { if ($existed) { [IO.Directory]::Move($backup, $destination) }; throw }
    foreach ($item in $retire) {
        $file = Join-Path $pendingDirectory $item.name
        if ((Get-FileDigest $file) -cne $item.digest) { Fail 'Local draft changed during refresh; Snapshot installed, draft preserved for reconciliation.' }
        Write-JsonAtomic $file $item.remaining
    }
    $document = Read-SessionDocument $session
    $markers = @((Get-Property $document.value 'refresh_required') | Where-Object { $null -ne $_ -and ($_.area -cne $area -or $_.owner_tenant_id -ne $owner.id) })
    Set-Property $document.value 'refresh_required' $markers
    [void](Write-WorkspaceJson $session '.atlas/session.json' $document.value $document.digest)
    return [ordered]@{snapshot_id = $candidate.Manifest.snapshot_id; area = $area; owner_tenant_id = $owner.id;
        model_revision = Get-Property $candidate.Manifest 'model_revision'; dataset_count = @($candidate.Datasets).Count;
        backup = $(if ($existed) { $backup.Substring($session.Length + 1).Replace('\', '/') } else { $null })}
}

function Select-AtlasTask([hashtable]$Options) {
    $root = Resolve-Session $Options; $document = Read-SessionDocument $root
    [void](Read-AtlasTask $root $Options.task)
    Set-Property $document.value 'active_task' $Options.task
    [void](Write-WorkspaceJson $root '.atlas/session.json' $document.value $document.digest)
    return [ordered]@{task = $Options.task}
}
function Select-AtlasModel([hashtable]$Options) {
    $root = Resolve-Session $Options; $document = Read-SessionDocument $root
    $model = [ordered]@{id = [double](Require-Option $Options 'model-id'); name = Require-Option $Options 'model-name'}
    if (-not (Test-SafeJsonInteger $model.id $false)) { Fail 'Model requires a verified ID and name.' }
    if ($document.value.model -and $document.value.model.id -ne $model.id) { Fail 'One Model per directory; use a different directory for another Model.' }
    Set-Property $document.value 'model' $model
    [void](Write-WorkspaceJson $root '.atlas/session.json' $document.value $document.digest)
    return [ordered]@{model = $model}
}
