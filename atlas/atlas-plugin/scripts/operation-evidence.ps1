# Governed response decoding and identifier normalization, native PowerShell 5.1.
# Parse one JSON document; do not repair transcripts or retain raw tool envelopes.
function Read-AtlasResponse([string]$Path) {
    $item = Get-Item -LiteralPath ([IO.Path]::GetFullPath($Path)) -Force -ErrorAction Stop
    if ($item.PSIsContainer -or ($item.Attributes -band [IO.FileAttributes]::ReparsePoint) -or $item.Length -gt 16MB) { Fail 'Response must be a bounded regular JSON file.' }
    try { $value = ConvertFrom-GdsJson ([IO.File]::ReadAllText($item.FullName, [Text.Encoding]::UTF8)) }
    catch { Fail 'Response file must contain exactly one JSON document, without prose or concatenated results.' }
    if (-not (Test-AtlasObject $value) -or (Get-Property $value 'isError') -eq $true) { Fail 'Expected a successful structured tool response.' }
    $hasStructured = Test-Property $value 'structuredContent'
    $content = Get-Property $value 'content'
    if ($hasStructured -or $content -is [Array]) {
        $text = $null; $hasText = Test-Property $value 'content'
        if ($hasText) {
            if ($content -isnot [Array] -or $content.Count -ne 1 -or (Get-Property $content[0] 'type') -cne 'text' -or (Get-Property $content[0] 'text') -isnot [string]) { Fail 'Tool response requires one JSON text block.' }
            try { $text = ConvertFrom-GdsJson $content[0].text }
            catch { Fail 'Tool response text must contain exactly one JSON document.' }
        }
        $structured = Get-Property $value 'structuredContent'
        if ($hasStructured -and $hasText -and (ConvertTo-StableJson $structured) -cne (ConvertTo-StableJson $text)) { Fail 'Tool response payloads conflict.' }
        $value = $text
        if ($null -ne $structured) { $value = $structured }
    }
    if (-not (Test-AtlasObject $value) -or (Get-Property $value 'isError') -eq $true) { Fail 'Expected a successful JSON response object.' }
    return $value
}

function Get-AtlasResponseAlias($Value, [string]$Canonical, [string[]]$Alternatives) {
    $found = $false; $result = $null
    foreach ($name in @($Canonical) + $Alternatives) {
        if (-not (Test-Property $Value $name)) { continue }
        $item = Get-Property $Value $name
        if ($found -and (ConvertTo-StableJson $item) -cne (ConvertTo-StableJson $result)) { Fail "Conflicting $Canonical fields." }
        $result = $item; $found = $true
    }
    if ($result -is [Array]) { return ,$result }
    return $result
}

function ConvertTo-AtlasServerResponse($Value, [string]$Area, $Owner, $ModelId) {
    $other = if ($Area -ceq 'metadata') { 'model_change_set_id' } else { 'metadata_change_set_id' }
    $id = Get-AtlasResponseAlias $Value 'change_set_id' @($Area + '_change_set_id')
    $ownerId = if ($Area -ceq 'metadata') { Get-AtlasResponseAlias $Value 'tenant_id' @('owner_tenant_id') } else { Get-Property $Value 'model_id' }
    $expectedOwner = if ($Area -ceq 'metadata') { $Owner.id } else { $ModelId }
    if ((Get-Property $Value 'schema_version') -isnot [string] -or (Get-Property $Value 'schema_version') -cne '1.0' -or (Test-Property $Value $other) -or
        ((Test-Property $Value 'area') -and (Get-Property $Value 'area') -cne $Area) -or
        ((Test-Property $Value 'owner_tenant_id') -and (-not (Test-SafeJsonInteger (Get-Property $Value 'owner_tenant_id') $false) -or (Get-Property $Value 'owner_tenant_id') -ne $Owner.id)) -or
        -not (Test-SafeJsonInteger $ownerId $false) -or $ownerId -ne $expectedOwner -or $id -isnot [string] -or $id -cnotmatch $script:AtlasUuid -or
        -not (Test-SafeJsonInteger (Get-Property $Value 'draft_revision'))) { Fail 'Server response does not match the owner, Model or Change Set contract.' }
    Set-Property $Value 'change_set_id' $id
    if ($Area -ceq 'metadata') { Set-Property $Value 'tenant_id' $ownerId }
    return $Value
}

function ConvertTo-AtlasStageReceipt($Value) {
    if (-not (Test-AtlasObject $Value)) { return $Value }
    $aliases = [ordered]@{schema_version = 'schemaVersion'; task_id = 'taskId'; operation_id = 'operationId';
        owner_tenant_id = 'ownerTenantId'; owner_root = 'ownerRoot'; change_set_id = 'changeSetId'; starting_revision = 'startingRevision';
        draft_revision = 'resultingRevision'; accepted_digest = 'acceptedDigest'; stage_fingerprint = 'stageFingerprint'; fingerprint_verified = 'fingerprintVerified'}
    foreach ($canonical in $aliases.Keys) {
        $old = $aliases[$canonical]
        $present = (Test-Property $Value $canonical) -or (Test-Property $Value $old)
        $normalized = Get-AtlasResponseAlias $Value $canonical @($old)
        if ($present) { Set-Property $Value $canonical $normalized }
        Remove-Property $Value $old
    }
    if (Test-Property $Value 'datasets') {
        $datasets = Get-Property $Value 'datasets'
        if ($datasets -isnot [Array]) { Fail 'Invalid Stage dataset receipt.' }
        $normalized = New-Object Collections.ArrayList
        foreach ($row in $datasets) {
            if (-not (Test-AtlasObject $row)) { Fail 'Invalid Stage dataset receipt.' }
            $count = Get-AtlasResponseAlias $row 'record_count' @('recordCount')
            if (-not (Test-SafeJsonInteger $count)) { Fail 'Invalid Stage dataset count.' }
            $entry = [ordered]@{record_count = $count}
            if (Test-Property $row 'dataset') { $entry.dataset = Get-Property $row 'dataset' }
            [void]$normalized.Add($entry)
        }
        Set-Property $Value 'datasets' @($normalized)
    }
    return $Value
}
