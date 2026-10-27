# Read-only submission driver, native Windows PowerShell 5.1 twin of nextStep in atlas-local.js.
# Reports the workspace state and the one next action; it never approves, stages, validates on
# the server or applies. Keep states, priorities and action shapes aligned with the Node helper.
$script:NextPriority = @('stage_uncertain', 'refresh_blocked', 'apply_approved', 'server_validated', 'staged',
    'stage_prepared', 'draft_bound', 'accepted', 'server_validation_failed', 'refresh_required', 'local_files_invalid',
    'validation_failed', 'needs_task', 'needs_validation', 'ready_for_review', 'snapshot_missing', 'no_pending_changes', 'not_started')

function Get-NextStep([hashtable]$Options) {
    if (-not $Options['session']) { Fail '--session must be the working directory containing .atlas.' }
    $root = [IO.Path]::GetFullPath([string]$Options['session'])
    if (-not (Test-Path -LiteralPath ([IO.Path]::Combine($root, '.atlas', 'session.json')) -PathType Leaf)) {
        return [ordered]@{schema_version = '1.0'; state = 'no_session'; area = $null; owner_tenant_id = $null;
            summary = 'This folder has no Atlas workspace yet.';
            action = [ordered]@{kind = 'helper'; command = 'session-init';
                argv = @('session-init', '--root', $root, '--tenant', '<tenant_code>', '--tenant-id', '<tenant_id>');
                instructions = 'Resolve the Tenant with list_tenants (and the Project with list_projects when the work needs one), then run session-init with those verified values. Add --project-id and --project-name for Project work.'};
            then = @('Install the Snapshot the work needs; run next again.'); facts = [ordered]@{}; other_work = @()}
    }
    $root = Resolve-Session $Options
    $state = Read-SessionState $root
    if ($Options.ContainsKey('owner') -and $Options['area'] -cne 'metadata') { Fail '--owner requires --area metadata.' }
    $errorCode = ''
    if ($Options.ContainsKey('error')) {
        if (-not $Options.ContainsKey('area')) { Fail '--error requires --area of the failed call.' }
        $errorCode = [string]$Options['error']
        if ($errorCode -cnotmatch '^[a-z][a-z0-9_]{1,63}\z') { Fail '--error must be the server error code, such as tenant_lock_required.' }
    }
    $pairs = New-Object Collections.ArrayList
    if ($Options.ContainsKey('area')) { [void]$pairs.Add(@($Options['area'], (Get-AtlasOwner $state $Options['area'] $Options['owner']))) }
    else {
        if ($null -ne (Get-Property $state 'project')) { [void]$pairs.Add(@('project', (Get-AtlasOwner $state 'project'))) }
        [void]$pairs.Add(@('metadata', (Get-AtlasOwner $state 'metadata')))
        $owners = Get-Property $state 'metadata_owners'
        # Node orders integer-like object keys ascending.
        foreach ($id in @(Get-PropertyNames $owners | Sort-Object { [long]$_ })) {
            $owner = Get-Property $owners $id
            if ($owner.id -ne $state.tenant.id) { [void]$pairs.Add(@('metadata', (Get-AtlasOwner $state 'metadata' $owner.id))) }
        }
    }
    $ranked = New-Object Collections.ArrayList
    for ($index = 0; $index -lt $pairs.Count; $index++) {
        $result = Get-NextForArea $root $state $pairs[$index][0] $pairs[$index][1] $Options.ContainsKey('area') $errorCode
        [void]$ranked.Add([pscustomobject]@{priority = [Array]::IndexOf($script:NextPriority, [string]$result.state); position = $index; result = $result})
    }
    # Explicit tie-break: Windows PowerShell 5.1 Sort-Object is not guaranteed stable.
    $ordered = @($ranked | Sort-Object -Property priority, position)
    $selected = $ordered[0].result
    $other = New-Object Collections.ArrayList
    for ($index = 1; $index -lt $ordered.Count; $index++) {
        $item = $ordered[$index].result
        if (@('no_pending_changes', 'not_started') -ccontains $item.state) { continue }
        [void]$other.Add([ordered]@{area = $item.area; owner_tenant_id = $item.owner_tenant_id; state = $item.state; summary = $item.summary})
    }
    $selected.other_work = @($other)
    return $selected
}

function New-NextResult([string]$State, [string]$Area, $Owner, [string]$Summary, $Action, [object[]]$Then, $Facts) {
    if ($null -eq $Then) { $Then = @() }
    if ($null -eq $Facts) { $Facts = [ordered]@{} }
    return [ordered]@{schema_version = '1.0'; state = $State; area = $Area; owner_tenant_id = $Owner.id; summary = $Summary;
        action = $Action; then = @($Then); facts = $Facts}
}

function New-NextHelperAction([string]$Command, [string]$Root, [string]$Area, [object[]]$OwnerArgs, [object[]]$Rest) {
    $argv = New-Object Collections.ArrayList
    foreach ($value in @($Command, '--session', $Root, '--area', $Area)) { [void]$argv.Add($value) }
    foreach ($value in @($OwnerArgs)) { if ($null -ne $value) { [void]$argv.Add($value) } }
    foreach ($value in @($Rest)) { if ($null -ne $value) { [void]$argv.Add($value) } }
    return [ordered]@{kind = 'helper'; command = $Command; argv = @($argv)}
}

function New-NextTempFile([string]$Root, [string]$Label, [string]$Name) {
    for ($index = 1; ; $index++) {
        $file = [IO.Path]::Combine($Root, '.atlas', 'temp', ($Label + '-' + $Name + '-' + $index + '.json'))
        if (-not (Test-Path -LiteralPath $file)) { return $file }
    }
}

function Get-NextForArea([string]$Root, $State, [string]$Area, $Owner, [bool]$Explicit, [string]$ErrorCode = '') {
    $project = Get-Property $State 'project'
    $label = if ($Area -ceq 'metadata') { 'metadata-' + $Owner.id } else { 'project' }
    $scope = [ordered]@{}
    if ($Area -ceq 'metadata') { $scope.tenant_id = $Owner.id }
    elseif ($null -ne (Get-Property $project 'id')) { $scope.project_id = Get-Property $project 'id' }
    $lockTenant = if ($Area -ceq 'metadata') { $Owner.id } else { $State.tenant.id }
    $target = if ($Area -ceq 'metadata') { 'Metadata for Tenant ' + $Owner.code } else { 'Project ' + (Get-Property $project 'name') }
    $ownerArgs = @()
    if ($Area -ceq 'metadata' -and $Owner.id -ne $State.tenant.id) { $ownerArgs = @('--owner', [string]$Owner.id) }
    $refresh = $false
    foreach ($entry in (Get-Property $State 'refresh_required')) {
        if ($null -ne $entry -and $entry.area -ceq $Area -and $entry.owner_tenant_id -eq $Owner.id) { $refresh = $true }
    }
    $snapshotThen = @('Download download_url to a new .atlas/temp/*.zip file; never store the URL.',
        "Run snapshot-install with that archive and the response's snapshot_id, size_bytes and sha256.", 'Run next again.')
    $operation = $null
    try { $operation = (Read-AtlasOperation $Root $State $Area $Owner).value }
    catch { if ($_.Exception.Message -cne 'A digest-bound acknowledgement is required first.') { throw } }
    if ($ErrorCode) {
        # One recovery per server error code from a failed MCP call; never a blind retry.
        $draft = Get-Property $operation 'draft'
        $changeSet = $null
        if ($null -ne $draft) {
            $changeSet = [ordered]@{}
            foreach ($key in $scope.Keys) { $changeSet[$key] = $scope[$key] }
            $changeSet[$Area + '_change_set_id'] = Get-Property $draft 'id'
            $changeSet.expected_draft_revision = Get-Property $draft 'revision'
        }
        $facts = [ordered]@{error_code = $ErrorCode}
        if ($null -ne $operation) {
            $facts.operation_id = $operation.id
            $facts.change_set_id = Get-Property $draft 'id'
            $facts.draft_revision = Get-Property $draft 'revision'
        }
        $code = $ErrorCode
        if ($code -ceq ($Area + '_change_set_not_validated')) { $code = 'candidate_digest_conflict' }
        elseif ($code -ceq ($Area + '_change_set_not_active') -or $code -ceq ($Area + '_change_set_not_found')) { $code = 'draft_revision_conflict' }
        $stop = $null
        switch -CaseSensitive ($code) {
            'tenant_lock_required' {
                return New-NextResult 'error_recovery' $Area $Owner "Writes need your active Tenant Lock for tenant $lockTenant." ([ordered]@{kind = 'mcp';
                    tool = 'check_tenant_lock'; arguments = [ordered]@{tenant_id = $lockTenant}; save_response_to = (New-NextTempFile $Root $label 'lock')}) @(
                    "If no one else holds it, call acquire_tenant_lock({tenant_id: $lockTenant}) and retry the failed call.",
                    'If another user holds it, tell the user and stop. Never call override_tenant_lock unless the user explicitly asks.') $facts
            }
            'tenant_locked' {
                return New-NextResult 'error_recovery' $Area $Owner "Another user holds the Tenant Lock for tenant $lockTenant." ([ordered]@{kind = 'ask_user';
                    question = 'The Tenant is locked by another user. Wait until they release it?'}) @(
                    'Retry only after the lock is free. Never call override_tenant_lock unless the user explicitly asks.') $facts
            }
            'project_locked' { $stop = 'The Project is locked; a human must unlock it in the GDS web app.' }
            'authorization_denied' { $stop = "The signed-in user's role does not allow this operation." }
            'stage_runner_required' {
                return New-NextResult 'error_recovery' $Area $Owner 'Stage uploads run only through the Stage Runner.' (New-NextHelperAction 'next' $Root $Area $ownerArgs @()) @(
                    "Follow next's atlas_stageApprovedManifest action. Never call stage_*, begin_*, put_* or commit_* tools.") $facts
            }
            'candidate_digest_conflict' {
                if ($null -eq $changeSet) { $stop = 'No Change Set is bound to this operation.'; break }
                return New-NextResult 'error_recovery' $Area $Owner 'The approved server review no longer matches the draft; validate it again.' ([ordered]@{kind = 'mcp';
                    tool = 'validate_' + $Area + '_change_set'; arguments = $changeSet; save_response_to = (New-NextTempFile $Root $label 'validation'); requires_tenant_lock = $lockTenant}) @(
                    'Run operation-record --checkpoint validation --file <saved response>; it clears the old Apply approval.',
                    'Show the new server review and ask for Apply approval again.', 'Run next again.') $facts
            }
            { $_ -ceq 'object_locked' -or $_ -ceq 'attribute_locked' } {
                return New-NextResult 'error_recovery' $Area $Owner 'A changed record is locked on the server.' ([ordered]@{kind = 'author';
                    instructions = 'Discard local changes to the locked Objects or Attributes, then validate, review and accept again.'}) @('Run next again.') $facts
            }
            'mapping_branch_unavailable' {
                return New-NextResult 'error_recovery' $Area $Owner 'A Mapping would map an Entity from a System that is not one of its Mapping branches.' ([ordered]@{kind = 'author';
                    instructions = "The failed call's message names the mapping_object record. Remove it and its mapping_attribute records, or apply the Entity's source change first: map only from the Systems the Entity's sources come from (Dimensional: Systems where a supporting Logical Entity has complete Mapping). Then validate, review and accept again."}) @('Run next again.') $facts
            }
            'draft_revision_conflict' {
                if ($null -eq $changeSet) { $stop = 'The server draft changed or ended outside this operation.'; break }
                $read = [ordered]@{}
                foreach ($key in $scope.Keys) { $read[$key] = $scope[$key] }
                $read[$Area + '_change_set_id'] = Get-Property $draft 'id'
                return New-NextResult 'error_recovery' $Area $Owner 'The server draft changed or ended outside this operation.' ([ordered]@{kind = 'mcp';
                    tool = 'get_' + $Area + '_change_set'; arguments = $read; save_response_to = (New-NextTempFile $Root $label 'draft')}) @(
                    'Show the user its status and draft_revision. Do not retry the failed call, restage or create a new draft without their decision.') $facts
            }
            'invalid_request' {
                return New-NextResult 'error_recovery' $Area $Owner "The server rejected the call's arguments." (New-NextHelperAction 'next' $Root $Area $ownerArgs @()) @(
                    "Run next and use its action's exact arguments; never edit or invent them.") $facts
            }
            { $_ -ceq 'dependency_unavailable' -or $_ -ceq 'internal_error' } { $stop = 'The server could not complete the call. Retry once later; if it fails again, report the code.' }
            default { $stop = "Unrecognized server error $ErrorCode." }
        }
        return New-NextResult 'error_recovery' $Area $Owner $stop ([ordered]@{kind = 'stop'; instructions = ($stop + ' Tell the user; do not retry or work around it.')}) @() $facts
    }
    $snapshotOptions = @{session = $Root; area = $Area}
    if ($Area -ceq 'metadata') { $snapshotOptions.owner = [string]$Owner.id }
    try { $snapshot = Find-Snapshot $snapshotOptions }
    catch {
        if ($_.Exception.Message -notmatch 'Snapshot directory is missing|parent directory is missing') { throw }
        if ($Explicit -or $Area -ceq 'project') {
            return New-NextResult 'snapshot_missing' $Area $Owner "No $Area Snapshot is installed." ([ordered]@{kind = 'mcp';
                tool = 'create_' + $Area + '_snapshot'; arguments = $scope; save_response_to = (New-NextTempFile $Root $label 'snapshot')}) $snapshotThen $null
        }
        return New-NextResult 'not_started' $Area $Owner "No $Area work in this folder." ([ordered]@{kind = 'done'}) $null $null
    }
    $directory = [IO.Path]::Combine($Root, ((Get-OwnerPrefix $Owner) + $Area + '-change-set'))
    $pending = @{}
    try {
        if (Test-Path -LiteralPath $directory -PathType Container) {
            $snapshot | Add-Member -NotePropertyName ChangeDirectory -NotePropertyValue $directory
            $pending = Read-Pending $snapshot
            $digest = Get-WorkspaceDigest $snapshot
        }
        else { $digest = Get-ByteDigest ([byte[]]@()) }
    }
    catch {
        return New-NextResult 'local_files_invalid' $Area $Owner 'Local Change Set files are invalid.' ([ordered]@{kind = 'author';
            instructions = 'Repair the local ' + $Area + ' Change Set files before continuing: ' + $_.Exception.Message}) $null $null
    }
    $counts = [ordered]@{}
    foreach ($name in @($pending.Keys | Sort-Object)) { if (@($pending[$name]).Count -gt 0) { $counts[$name] = @($pending[$name]).Count } }
    $facts = [ordered]@{pending_datasets = $counts; local_digest = $digest}
    if ($null -ne $operation) {
        $draft = Get-Property $operation 'draft'
        $facts.operation_id = $operation.id; $facts.change_set_id = Get-Property $draft 'id'; $facts.draft_revision = Get-Property $draft 'revision'
    }
    if ((Get-Property (Get-Property $operation 'stage_attempt') 'status') -ceq 'unknown') {
        return New-NextResult 'stage_uncertain' $Area $Owner 'The last Stage outcome is unknown. Recover it before any other write.' ([ordered]@{kind = 'extension';
            tool = 'atlas_stageApprovedManifest'; input = [ordered]@{manifestPath = (Resolve-WorkspacePath $Root $operation.stage_request.path); recoverOnly = $true}}) @(
            'recoverOnly only reads: never restage, re-accept or create a new draft until it reports the outcome.', 'Run next again.') $facts
    }
    if ($refresh -and -not (Get-Property $operation 'apply') -and $counts.Count -gt 0) {
        return New-NextResult 'refresh_blocked' $Area $Owner 'A refresh is required but unapplied local drafts exist.' ([ordered]@{kind = 'author';
            instructions = 'Show the user the base/current/proposed differences, reconcile the draft against the new server state, then refresh. Never discard the draft or edit Snapshot files to force installation.'}) $null $facts
    }
    if (Get-Property $operation 'apply') {
        if ($refresh) {
            return New-NextResult 'refresh_required' $Area $Owner "Applied changes need a fresh $Area Snapshot." ([ordered]@{kind = 'mcp';
                tool = 'create_' + $Area + '_snapshot'; arguments = $scope; save_response_to = (New-NextTempFile $Root $label 'snapshot')}) @(
                $snapshotThen[0], $snapshotThen[1], ('Release the Tenant Lock with release_tenant_lock({tenant_id: ' + $lockTenant + '}) when no further writes are planned.'), 'Run next again.') $facts
        }
        $operation = $null
    }
    if ($null -ne $operation) {
        $unchanged = $digest -ceq $operation.local_digest
        $draft = Get-Property $operation 'draft'
        $changeSet = [ordered]@{}
        foreach ($key in $scope.Keys) { $changeSet[$key] = $scope[$key] }
        $changeSet[$Area + '_change_set_id'] = Get-Property $draft 'id'
        $changeSet.expected_draft_revision = Get-Property $draft 'revision'
        $stage = ConvertTo-AtlasStageReceipt (Get-Property $operation 'stage')
        $serverValidation = Get-Property $operation 'server_validation'
        $applyApproval = Get-Property $operation 'apply_approval'
        if ($applyApproval) {
            # The server applies only the candidate the user approved.
            $applyArguments = [ordered]@{}
            foreach ($key in $changeSet.Keys) { $applyArguments[$key] = $changeSet[$key] }
            $applyArguments.expected_candidate_digest = Get-Property $applyApproval 'candidate_digest'
            return New-NextResult 'apply_approved' $Area $Owner ('The user approved Apply for ' + $target + '.') ([ordered]@{kind = 'mcp';
                tool = 'apply_' + $Area + '_change_set'; arguments = $applyArguments; save_response_to = (New-NextTempFile $Root $label 'apply'); requires_tenant_lock = $lockTenant}) @(
                'Run operation-record --checkpoint apply --file <saved response>.', 'Run next again to refresh.') $facts
        }
        if ((Get-Property $serverValidation 'valid') -eq $true) {
            $approve = New-NextHelperAction 'operation-record' $Root $Area $ownerArgs @('--checkpoint', 'apply-approval', '--digest-from-operation', 'true')
            return New-NextResult 'server_validated' $Area $Owner 'The server validated the staged draft.' ([ordered]@{kind = 'ask_user';
                question = 'Apply these validated changes to ' + $target + '?'; show = (Resolve-WorkspacePath $Root $serverValidation.path);
                after_approval = @($approve)}) @(
                'Ask separately from the Stage approval; show the complete server action review first.', 'Run next again after recording approval.') $facts
        }
        if ($null -ne $serverValidation -and (Get-Property $serverValidation 'valid') -eq $false -and $unchanged) {
            return New-NextResult 'server_validation_failed' $Area $Owner 'Server validation rejected the staged draft.' ([ordered]@{kind = 'author';
                instructions = 'Read ' + (Resolve-WorkspacePath $Root $serverValidation.path) + ', repair the local records, then run next. The repaired batch restages into the same draft.'}) $null $facts
        }
        if ((Get-Property $stage 'status') -ceq 'staged' -and (Get-Property $stage 'fingerprint_verified') -eq $true -and $null -eq $serverValidation) {
            $summary = if ($unchanged) { 'Stage completed and was verified.' } else { 'Stage completed; local files changed afterwards and stay for a later batch.' }
            return New-NextResult 'staged' $Area $Owner $summary ([ordered]@{kind = 'mcp';
                tool = 'validate_' + $Area + '_change_set'; arguments = $changeSet; save_response_to = (New-NextTempFile $Root $label 'validation'); requires_tenant_lock = $lockTenant}) @(
                'Run operation-record --checkpoint validation --file <saved response>.', 'Run next again.') $facts
        }
        if ($null -eq $stage -and $null -eq $serverValidation -and $unchanged) {
            $stageRequest = Get-Property $operation 'stage_request'
            if ($null -ne $stageRequest) {
                return New-NextResult 'stage_prepared' $Area $Owner 'The approved batch is ready for Stage Runner.' ([ordered]@{kind = 'extension';
                    tool = 'atlas_stageApprovedManifest'; input = [ordered]@{manifestPath = (Resolve-WorkspacePath $Root $stageRequest.path)}}) @(
                    'Require status=staged and fingerprint_verified=true; on an uncertain result run next (it switches to recovery).', 'Run next again.') $facts
            }
            if ($null -ne $draft) {
                return New-NextResult 'draft_bound' $Area $Owner 'The acknowledged batch has a server draft.' (New-NextHelperAction 'prepare-stage-request' $Root $Area $ownerArgs @()) @('Run next again.') $facts
            }
            $draftFile = New-NextTempFile $Root $label 'draft'
            return New-NextResult 'accepted' $Area $Owner 'The batch is acknowledged; it needs a server draft.' ([ordered]@{kind = 'mcp';
                tool = 'create_' + $Area + '_change_set'; arguments = $scope; save_response_to = $draftFile; requires_tenant_lock = $lockTenant}) @(
                ('Run prepare-stage-request --draft-file ' + $draftFile + '.'), 'Run next again.') $facts
        }
    }
    if ($counts.Count -eq 0) {
        return New-NextResult 'no_pending_changes' $Area $Owner "No local $Area changes to submit." ([ordered]@{kind = 'done'}) $null $facts
    }
    $task = Get-Property $State 'active_task'
    if (-not $task) {
        return New-NextResult 'needs_task' $Area $Owner 'Local changes exist but no task is active.' ([ordered]@{kind = 'helper'; command = 'task-add';
            argv = @('task-add', '--session', $Root, '--outcome', '<short outcome>')}) @('Run next again.') $facts
    }
    $reportRelative = '.atlas/tasks/' + $task + '.evidence/' + $Area + '-' + $Owner.id + '-validation.json'
    $reportFile = [IO.Path]::Combine($Root, '.atlas', 'tasks', ($task + '.evidence'), ($Area + '-' + $Owner.id + '-validation.json'))
    $report = $null
    if (Test-Path -LiteralPath $reportFile -PathType Leaf) { $report = Read-Json $reportFile 'Validation report' }
    $current = $null -ne $report -and (Get-Property $report 'digest') -ceq $digest -and (Get-Property $report 'owner_tenant_id') -eq $Owner.id -and
        (Get-Property $report 'inputs') -is [Array]
    if ($current) {
        foreach ($binding in @($report.inputs)) {
            try { if ((Get-FileDigest (Resolve-WorkspacePath $Root $binding.manifest_path)) -cne $binding.manifest_sha256) { $current = $false } }
            catch { $current = $false }
        }
    }
    if (-not $current) {
        $summary = if ($null -ne $operation) { 'Local files changed after acknowledgement; validate before review.' } else { 'Local changes have not been validated.' }
        return New-NextResult 'needs_validation' $Area $Owner $summary (New-NextHelperAction 'validate' $Root $Area $ownerArgs @()) @('Run next again.') $facts
    }
    $facts.validation_report = Resolve-WorkspacePath $Root $reportRelative
    $facts.issue_count = Get-Property $report 'issue_count'
    if ((Get-Property $report 'valid') -ne $true) {
        $issues = New-Object Collections.ArrayList
        foreach ($issue in @((Get-Property $report 'issues') | Select-Object -First 5)) {
            if ($null -eq $issue) { continue }
            $code = Get-Property $issue 'code'; if (-not $code) { $code = Get-Property $issue 'rule' }; if (-not $code) { $code = 'issue' }
            [void]$issues.Add(($code + ': ' + [string](Get-Property $issue 'message')).Trim())
        }
        $first = if ($issues.Count) { $issues -join ' | ' } else { 'see the validation report' }
        return New-NextResult 'validation_failed' $Area $Owner 'Local validation found errors.' ([ordered]@{kind = 'author';
            instructions = 'Repair the records, then run next. First findings: ' + $first}) $null $facts
    }
    $checkFile = New-NextTempFile $Root $label 'check'
    $draftFile = New-NextTempFile $Root $label 'draft'
    $accept = New-NextHelperAction 'accept' $Root $Area $ownerArgs @('--digest', $digest, '--backend-file', $checkFile, '--draft-file', $draftFile, '--prepare-stage', 'true')
    return New-NextResult 'ready_for_review' $Area $Owner 'Local changes are valid and ready for the user''s review.' ([ordered]@{kind = 'ask_user';
        question = 'Review the pending ' + $Area + ' changes in Atlas Local Workbench. Approve them for Stage?';
        after_approval = @(
            [ordered]@{kind = 'extension'; tool = 'atlas_checkStageRunner'; input = [ordered]@{outputFile = $checkFile}},
            [ordered]@{kind = 'mcp'; tool = 'check_tenant_lock'; arguments = [ordered]@{tenant_id = $lockTenant}; note = 'Call acquire_tenant_lock first if the current Principal does not hold it.'},
            [ordered]@{kind = 'mcp'; tool = 'create_' + $Area + '_change_set'; arguments = $scope; save_response_to = $draftFile},
            $accept,
            [ordered]@{kind = 'extension'; tool = 'atlas_stageApprovedManifest'; input = [ordered]@{manifestPath = '<stage_manifest_path from accept>'}})}) @(
        'Any edit after approval invalidates it: validate and review again.', 'Run next after Stage.') $facts
}
