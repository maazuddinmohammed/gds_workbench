# Native counterpart of workbench/validation/sql.js generated-artifact checks.
# This is the same bounded lexical policy, not a SQL parser or execution validator.
$script:AtlasSqlRegex = [Text.RegularExpressions.RegexOptions]::ECMAScript -bor [Text.RegularExpressions.RegexOptions]::CultureInvariant
$script:AtlasSqlRegexIgnoreCase = $script:AtlasSqlRegex -bor [Text.RegularExpressions.RegexOptions]::IgnoreCase
$script:AtlasSqlLowercase = $null

function Split-AtlasSql([string]$Sql) {
    $statements = New-Object Collections.ArrayList
    $start = 0; $quote = $null; $lineComment = $false; $blockComment = $false
    for ($index = 0; $index -lt $Sql.Length; $index++) {
        $character = [string]$Sql[$index]
        $next = if ($index + 1 -lt $Sql.Length) { [string]$Sql[$index + 1] } else { '' }
        if ($lineComment) { if ($character -ceq "`n") { $lineComment = $false } }
        elseif ($blockComment) {
            if ($character -ceq '*' -and $next -ceq '/') { $blockComment = $false; $index++ }
        }
        elseif ($null -ne $quote) {
            if ($character -ceq $quote -and $next -ceq $quote) { $index++ }
            elseif ($character -ceq $quote) { $quote = $null }
        }
        elseif ($character -ceq '-' -and $next -ceq '-') { $lineComment = $true; $index++ }
        elseif ($character -ceq '/' -and $next -ceq '*') { $blockComment = $true; $index++ }
        elseif (@("'", '"', '`') -ccontains $character) { $quote = $character }
        elseif ($character -ceq ';') {
            $value = $Sql.Substring($start, $index - $start).Trim()
            if ($value) { [void]$statements.Add($value) }
            $start = $index + 1
        }
    }
    $final = $Sql.Substring($start).Trim()
    if ($final) { [void]$statements.Add($final) }
    if ($null -ne $quote -or $blockComment) { return $null }
    return ,@($statements)
}

function Get-AtlasMaskedSql([string]$Sql) {
    $result = New-Object Text.StringBuilder
    $quote = $null; $lineComment = $false; $blockComment = $false
    for ($index = 0; $index -lt $Sql.Length; $index++) {
        $character = [string]$Sql[$index]
        $next = if ($index + 1 -lt $Sql.Length) { [string]$Sql[$index + 1] } else { '' }
        if ($lineComment) {
            [void]$result.Append($(if ($character -ceq "`n") { "`n" } else { ' ' }))
            if ($character -ceq "`n") { $lineComment = $false }
        }
        elseif ($blockComment) {
            [void]$result.Append(' ')
            if ($character -ceq '*' -and $next -ceq '/') {
                [void]$result.Append(' '); $blockComment = $false; $index++
            }
        }
        elseif ($quote -ceq "'") {
            [void]$result.Append(' ')
            if ($character -ceq "'" -and $next -ceq "'") { [void]$result.Append(' '); $index++ }
            elseif ($character -ceq "'") { $quote = $null }
        }
        elseif ($null -ne $quote) {
            [void]$result.Append($character)
            if ($character -ceq $quote -and $next -ceq $quote) { [void]$result.Append($next); $index++ }
            elseif ($character -ceq $quote) { $quote = $null }
        }
        elseif ($character -ceq '-' -and $next -ceq '-') {
            [void]$result.Append('  '); $lineComment = $true; $index++
        }
        elseif ($character -ceq '/' -and $next -ceq '*') {
            [void]$result.Append('  '); $blockComment = $true; $index++
        }
        else {
            [void]$result.Append($character)
            if (@("'", '"', '`') -ccontains $character) { $quote = $character }
        }
    }
    return $result.ToString()
}

function Test-AtlasSqlUnicodeRange([int]$Point, $Ranges) {
    $left = 0; $right = $Ranges.Count - 1
    while ($left -le $right) {
        $middle = [int][Math]::Floor(($left + $right) / 2)
        if ($Point -lt $Ranges[$middle][0]) { $right = $middle - 1 }
        elseif ($Point -gt $Ranges[$middle][1]) { $left = $middle + 1 }
        else { return $true }
    }
    return $false
}

function ConvertTo-AtlasSqlLower([string]$Value) {
    if (-not [regex]::IsMatch($Value, '[^\x00-\x7F]')) { return $Value.ToLowerInvariant() }
    # JavaScript lowercase is not casefold or .NET invariant lowercase: dotted I
    # expands, and Greek sigma depends on adjacent cased/ignorable characters.
    if ($null -eq $script:AtlasSqlLowercase) {
        $script:AtlasSqlLowercase = Read-Json (Join-Path (Split-Path -Parent $PSScriptRoot) 'assets/sql-identifier-lowercase.json') 'SQL identifier lowercase table'
    }
    $points = New-Object Collections.ArrayList
    for ($index = 0; $index -lt $Value.Length; $index++) {
        $length = if ([char]::IsHighSurrogate($Value[$index]) -and $index + 1 -lt $Value.Length -and [char]::IsLowSurrogate($Value[$index + 1])) { 2 } else { 1 }
        $point = if ($length -eq 2) { [char]::ConvertToUtf32($Value, $index) } else { [int]$Value[$index] }
        [void]$points.Add(@{point = $point; text = $Value.Substring($index, $length)})
        $index += $length - 1
    }
    $result = New-Object Text.StringBuilder
    for ($index = 0; $index -lt $points.Count; $index++) {
        $point = $points[$index].point
        $mapped = Get-Property $script:AtlasSqlLowercase.lowercase ([string]$point)
        if ($point -eq 0x03A3) {
            $before = $index - 1; $after = $index + 1
            while ($before -ge 0 -and (Test-AtlasSqlUnicodeRange $points[$before].point $script:AtlasSqlLowercase.case_ignorable)) { $before-- }
            while ($after -lt $points.Count -and (Test-AtlasSqlUnicodeRange $points[$after].point $script:AtlasSqlLowercase.case_ignorable)) { $after++ }
            if ($before -ge 0 -and (Test-AtlasSqlUnicodeRange $points[$before].point $script:AtlasSqlLowercase.cased) -and
                ($after -eq $points.Count -or -not (Test-AtlasSqlUnicodeRange $points[$after].point $script:AtlasSqlLowercase.cased))) { $mapped = [string][char]0x03C2 }
        }
        [void]$result.Append($(if ($null -eq $mapped) { $points[$index].text } else { $mapped }))
    }
    return $result.ToString()
}

function Get-AtlasSqlIdentifierParts([string]$Value) {
    $parts = New-Object Collections.ArrayList
    $start = 0; $quote = $null
    for ($index = 0; $index -le $Value.Length; $index++) {
        $character = if ($index -lt $Value.Length) { [string]$Value[$index] } else { '' }
        if ($index -eq $Value.Length -or ($null -eq $quote -and $character -ceq '.')) {
            $part = $Value.Substring($start, $index - $start)
            if (($part.StartsWith('`') -and $part.EndsWith('`')) -or ($part.StartsWith('"') -and $part.EndsWith('"'))) {
                $part = $part.Substring(1, $part.Length - 2)
            }
            [void]$parts.Add((ConvertTo-AtlasSqlLower $part)); $start = $index + 1
        }
        elseif ($null -ne $quote) { if ($character -ceq $quote) { $quote = $null } }
        elseif (@('`', '"') -ccontains $character) { $quote = $character }
    }
    return ,@($parts)
}

function Test-AtlasSqlRelations([string]$Sql, $TemporaryRelations) {
    $masked = Get-AtlasMaskedSql $Sql
    if ([regex]::IsMatch($masked, '\b(?:from|join)\s*(?:$|where\b|group\b|order\b|having\b|limit\b)', $script:AtlasSqlRegexIgnoreCase)) { return $false }
    $localRelations = New-Object 'Collections.Generic.HashSet[string]' ([StringComparer]::Ordinal)
    foreach ($relation in $TemporaryRelations) { [void]$localRelations.Add($relation) }
    $ctes = [regex]::Matches($masked, '(?:\bwith\b|,)\s*(`[^`]+`|"[^"]+"|[A-Za-z_][\w$]*)\s+as\s*\(', $script:AtlasSqlRegexIgnoreCase)
    foreach ($cte in $ctes) { [void]$localRelations.Add((ConvertTo-StableJson (Get-AtlasSqlIdentifierParts $cte.Groups[1].Value))) }
    $tokens = [regex]::Matches($masked, '`(?:``|[^`])+`|"(?:""|[^"])+"|[A-Za-z_][\w$]*|[(),.]', $script:AtlasSqlRegex)
    $fromAtDepth = @{}; $depth = 0
    foreach ($token in $tokens) {
        $value = $token.Value; $keyword = $value.ToLowerInvariant()
        if ($value -ceq '(') { $depth++; $fromAtDepth.Remove($depth); continue }
        if ($value -ceq ')') { $fromAtDepth.Remove($depth); $depth--; continue }
        if (@('select', 'where', 'group', 'order', 'having', 'qualify', 'limit', 'union', 'intersect', 'except') -ccontains $keyword) { $fromAtDepth.Remove($depth) }
        if ($keyword -cne 'from' -and $keyword -cne 'join' -and -not ($value -ceq ',' -and $fromAtDepth[$depth])) { continue }
        $fromAtDepth[$depth] = $true
        $tail = $masked.Substring($token.Index + $value.Length).TrimStart()
        if ($tail.StartsWith('(')) { continue }
        $relation = [regex]::Match($tail, '^((?:`(?:``|[^`])+`|"(?:""|[^"])+"|[A-Za-z_][\w$]*)(?:\s*\.\s*(?:`(?:``|[^`])+`|"(?:""|[^"])+"|[A-Za-z_][\w$]*))*)', $script:AtlasSqlRegex)
        if (-not $relation.Success) { return $false }
        $name = [regex]::Replace($relation.Groups[1].Value, '\s*\.\s*', '.', $script:AtlasSqlRegex)
        if ($tail.Substring($relation.Length).TrimStart().StartsWith('(')) { continue }
        $parts = Get-AtlasSqlIdentifierParts $name
        if ($parts.Count -ne 2 -and -not $localRelations.Contains((ConvertTo-StableJson $parts))) { return $false }
    }
    $described = [regex]::Match($masked, '\bdescribe(?:\s+table)?\s+((?:`[^`]+`|"[^"]+"|[A-Za-z_][\w$]*)(?:\.(?:`[^`]+`|"[^"]+"|[A-Za-z_][\w$]*)){0,2})', $script:AtlasSqlRegexIgnoreCase)
    return -not $described.Success -or (Get-AtlasSqlIdentifierParts $described.Groups[1].Value).Count -eq 2
}

function Get-AtlasSqlFinalProjection([string]$Sql) {
    $masked = Get-AtlasMaskedSql $Sql
    $columns = New-Object Collections.ArrayList
    $start = 0; $depth = 0; $quote = $null; $projecting = $false
    for ($index = 0; $index -lt $masked.Length; $index++) {
        $character = [string]$masked[$index]
        $next = if ($index + 1 -lt $masked.Length) { [string]$masked[$index + 1] } else { '' }
        if ($null -ne $quote) {
            if ($character -ceq $quote -and $next -ceq $quote) { $index++ }
            elseif ($character -ceq $quote) { $quote = $null }
            continue
        }
        if (@('`', '"') -ccontains $character) { $quote = $character; continue }
        if ($character -ceq '(') { $depth++ } elseif ($character -ceq ')') { $depth-- }
        if ($depth -ne 0) { continue }
        $boundary = $index -eq 0 -or -not [regex]::IsMatch([string]$masked[$index - 1], '[A-Za-z0-9_]', $script:AtlasSqlRegex)
        $tail = $masked.Substring($index)
        if ($boundary -and [regex]::IsMatch($tail, '^select\b', $script:AtlasSqlRegexIgnoreCase)) {
            $projecting = $true; $start = $index + 6; $index += 5; continue
        }
        if ($projecting -and $boundary -and [regex]::IsMatch($tail, '^(?:from|union|intersect|except)\b', $script:AtlasSqlRegexIgnoreCase)) {
            [void]$columns.Add([regex]::Replace($masked.Substring($start, $index - $start).Trim(), '^distinct\s+', '', $script:AtlasSqlRegexIgnoreCase))
            $projecting = $false; continue
        }
        if ($projecting -and $character -ceq ',') {
            [void]$columns.Add([regex]::Replace($masked.Substring($start, $index - $start).Trim(), '^distinct\s+', '', $script:AtlasSqlRegexIgnoreCase))
            $start = $index + 1
        }
    }
    if ($projecting) { [void]$columns.Add([regex]::Replace($masked.Substring($start).Trim(), '^distinct\s+', '', $script:AtlasSqlRegexIgnoreCase)) }
    return ,@($columns)
}

function Get-AtlasGeneratedSqlIssues($Sql) {
    if ($Sql -isnot [string] -or [string]::IsNullOrWhiteSpace($Sql)) {
        return [ordered]@{code = 'code.statements'; message = 'SQL content is required.'}
    }
    $statements = Split-AtlasSql $Sql
    if ($null -eq $statements -or $statements.Count -eq 0) {
        return [ordered]@{code = 'code.statements'; message = 'SQL has unclosed quotes/comments or no statements.'}
    }
    $failures = New-Object Collections.ArrayList
    $temporary = New-Object 'Collections.Generic.HashSet[string]' ([StringComparer]::Ordinal)
    $noQuotes = [regex]::Replace($Sql, '''(?:''''|[^''])*''|`(?:``|[^`])*`|"(?:""|[^"])*"', '', $script:AtlasSqlRegex)
    if ([regex]::IsMatch($noQuotes, '--|/\*', $script:AtlasSqlRegex)) {
        [void]$failures.Add([ordered]@{code = 'code.statements'; message = 'SQL artifacts contain code only; keep explanatory comments in task or Mapping notes.'})
    }
    for ($index = 0; $index -lt $statements.Count; $index++) {
        $masked = (Get-AtlasMaskedSql $statements[$index]).Trim()
        $syntax = [regex]::Replace($masked, '`(?:``|[^`])*`|"(?:""|[^"])*"', 'identifier', $script:AtlasSqlRegex)
        if ([regex]::IsMatch($syntax, '\b(insert|update|delete|merge|drop|alter|truncate|copy|grant|revoke|call|execute|use|set|cache|uncache|vacuum|optimize|into)\b|\b(secret|try_secret|read_files)\s*\(', $script:AtlasSqlRegexIgnoreCase)) {
            [void]$failures.Add([ordered]@{code = 'code.statements'; message = 'Transformation SQL cannot contain persistent writes, commands or credential/external-file functions.'}); continue
        }
        if ($index -eq $statements.Count - 1) {
            if (-not [regex]::IsMatch($masked, '^select\b', $script:AtlasSqlRegexIgnoreCase)) {
                [void]$failures.Add([ordered]@{code = 'code.statements'; message = 'The final statement must be one explicit SELECT.'}); continue
            }
            $columns = Get-AtlasSqlFinalProjection $masked
            $invalidProjection = @($columns | Where-Object { -not $_ -or [regex]::IsMatch($_, '^(?:(?:`[^`]+`|"[^"]+"|[A-Za-z_][\w$]*)\s*\.\s*)?\*(?:\s+(?:except|exclude|replace)\b.*)?$', $script:AtlasSqlRegexIgnoreCase) }).Count -gt 0
            if ($invalidProjection) { [void]$failures.Add([ordered]@{code = 'code.projection'; message = 'The final SELECT must list explicit target columns; wildcard projection is prohibited.'}) }
            if (-not (Test-AtlasSqlRelations $masked $temporary)) { [void]$failures.Add([ordered]@{code = 'code.stage-flow'; message = 'Read physical schema.table names or temporary views declared earlier in this file; runtime supplies the catalog.'}) }
            continue
        }
        $create = [regex]::Match($masked, '^create\s+or\s+replace\s+temp(?:orary)?\s+view\s+(`[^`]+`|"[^"]+"|[A-Za-z_][\w$]*)\s+as\s+((?:select|with)\b[\s\S]+)$', $script:AtlasSqlRegexIgnoreCase)
        if (-not $create.Success) {
            [void]$failures.Add([ordered]@{code = 'code.statements'; message = 'Preparation uses CREATE OR REPLACE TEMPORARY VIEW with an unqualified name and query.'}); continue
        }
        $key = ConvertTo-StableJson (Get-AtlasSqlIdentifierParts $create.Groups[1].Value)
        if ($temporary.Contains($key)) { [void]$failures.Add([ordered]@{code = 'code.stage-flow'; message = 'Temporary stage names must be unique within the artifact.'}) }
        if (-not (Test-AtlasSqlRelations $create.Groups[2].Value $temporary)) { [void]$failures.Add([ordered]@{code = 'code.stage-flow'; message = 'A stage reads an unresolved temporary relation or unsupported physical qualification.'}) }
        [void]$temporary.Add($key)
    }
    return @($failures)
}

function Get-AtlasGeneratedCodeIssues($States) {
    $state = @($States | Where-Object { $_.Dataset.name -ceq 'generated_code' }) | Select-Object -First 1
    if ($null -eq $state) { return }
    $originals = New-Object 'Collections.Generic.Dictionary[string,object]' ([StringComparer]::Ordinal)
    foreach ($record in @($state.Baseline)) { $originals[(Get-CanonicalKey 'model' $state.Dataset $record)] = $record }
    $index = 0
    foreach ($record in @($state.Pending)) {
        $index++
        $key = Get-CanonicalKey 'model' $state.Dataset $record
        if ((Get-Property $record 'artifact_type') -cne 'sql_file' -or (Get-Active $record) -ne $true -or
            ($originals.ContainsKey($key) -and (ConvertTo-StableJson $originals[$key]) -ceq (ConvertTo-StableJson $record))) { continue }
        foreach ($issue in @(Get-AtlasGeneratedSqlIssues (Get-Property $record 'generated_code_content'))) {
            [ordered]@{severity = 'error'; dataset = 'generated_code'; record = $index; code = $issue.code; fields = @('generated_code_content'); message = $issue.message}
        }
    }
}
