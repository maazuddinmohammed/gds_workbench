param([string]$AtlasCommand)
$Command = $AtlasCommand
$RemainingArguments = $args

Set-StrictMode -Version 2.0
$ErrorActionPreference = 'Stop'
$script:Utf8NoBom = New-Object System.Text.UTF8Encoding($false)
$script:JsonMaxDepth = 512
$script:CasefoldMap = $null
$script:Areas = @('metadata', 'model')
if ($null -eq ('Gds.Local.JsonCodec' -as [type])) {
    Add-Type -TypeDefinition @'
using System;
using System.Collections;
using System.Collections.Generic;
using System.Collections.Specialized;
using System.Globalization;
using System.Reflection;
using System.Runtime.CompilerServices;
using System.Text;

namespace Gds.Local
{
    public static class JsonCodec
    {
        public static object Parse(string text, int maxDepth)
        {
            if (text == null) throw new ArgumentNullException("text");
            if (maxDepth < 1) throw new ArgumentOutOfRangeException("maxDepth");
            return new JsonParser(text, maxDepth).Parse();
        }

        public static string Stringify(object value, int maxDepth, bool sortKeys)
        {
            if (maxDepth < 1) throw new ArgumentOutOfRangeException("maxDepth");
            return new JsonWriter(maxDepth, sortKeys).Write(value);
        }

        private sealed class JsonParser
        {
            private readonly string _text;
            private readonly int _maxDepth;
            private int _index;

            internal JsonParser(string text, int maxDepth)
            {
                _text = text;
                _maxDepth = maxDepth;
            }

            internal object Parse()
            {
                SkipWhiteSpace();
                if (_index == _text.Length) InvalidJson();
                object value = ReadValue(1);
                SkipWhiteSpace();
                if (_index != _text.Length) InvalidJson();
                return value;
            }

            private object ReadValue(int depth)
            {
                if (depth > _maxDepth) throw new FormatException("JSON exceeds the maximum depth.");
                SkipWhiteSpace();
                if (_index == _text.Length) InvalidJson();
                char current = _text[_index];
                if (current == '{') return ReadObject(depth);
                if (current == '[') return ReadArray(depth);
                if (current == '"') return ReadString();
                if (current == 't') { ReadLiteral("true"); return true; }
                if (current == 'f') { ReadLiteral("false"); return false; }
                if (current == 'n') { ReadLiteral("null"); return null; }
                if (current == '-' || (current >= '0' && current <= '9')) return ReadNumber();
                InvalidJson();
                return null;
            }

            private object ReadObject(int depth)
            {
                _index++;
                OrderedDictionary result = new OrderedDictionary(StringComparer.Ordinal);
                SkipWhiteSpace();
                if (Take('}')) return result;
                while (true)
                {
                    SkipWhiteSpace();
                    if (_index == _text.Length || _text[_index] != '"') InvalidJson();
                    string name = ReadString();
                    SkipWhiteSpace();
                    if (!Take(':')) InvalidJson();
                    object value = ReadValue(depth + 1);
                    if (result.Contains(name)) result[name] = value;
                    else result.Add(name, value);
                    SkipWhiteSpace();
                    if (Take('}')) return result;
                    if (!Take(',')) InvalidJson();
                }
            }

            private object ReadArray(int depth)
            {
                _index++;
                List<object> result = new List<object>();
                SkipWhiteSpace();
                if (Take(']')) return result.ToArray();
                while (true)
                {
                    result.Add(ReadValue(depth + 1));
                    SkipWhiteSpace();
                    if (Take(']')) return result.ToArray();
                    if (!Take(',')) InvalidJson();
                }
            }

            private string ReadString()
            {
                if (!Take('"')) InvalidJson();
                StringBuilder result = new StringBuilder();
                while (_index < _text.Length)
                {
                    char current = _text[_index++];
                    if (current == '"')
                    {
                        return result.ToString();
                    }
                    if (current < 0x20) InvalidJson();
                    if (current != '\\')
                    {
                        result.Append(current);
                        continue;
                    }
                    if (_index == _text.Length) InvalidJson();
                    char escaped = _text[_index++];
                    switch (escaped)
                    {
                        case '"': result.Append('"'); break;
                        case '\\': result.Append('\\'); break;
                        case '/': result.Append('/'); break;
                        case 'b': result.Append('\b'); break;
                        case 'f': result.Append('\f'); break;
                        case 'n': result.Append('\n'); break;
                        case 'r': result.Append('\r'); break;
                        case 't': result.Append('\t'); break;
                        case 'u': result.Append(ReadHexCharacter()); break;
                        default: InvalidJson(); break;
                    }
                }
                InvalidJson();
                return null;
            }

            private char ReadHexCharacter()
            {
                if (_index + 4 > _text.Length) InvalidJson();
                int value = 0;
                for (int offset = 0; offset < 4; offset++)
                {
                    char current = _text[_index++];
                    int digit;
                    if (current >= '0' && current <= '9') digit = current - '0';
                    else if (current >= 'a' && current <= 'f') digit = current - 'a' + 10;
                    else if (current >= 'A' && current <= 'F') digit = current - 'A' + 10;
                    else { InvalidJson(); return '\0'; }
                    value = (value << 4) | digit;
                }
                return (char)value;
            }

            private object ReadNumber()
            {
                int start = _index;
                Take('-');
                if (_index == _text.Length) InvalidJson();
                if (Take('0'))
                {
                    if (_index < _text.Length && IsDigit(_text[_index])) InvalidJson();
                }
                else
                {
                    if (_index == _text.Length || _text[_index] < '1' || _text[_index] > '9') InvalidJson();
                    while (_index < _text.Length && IsDigit(_text[_index])) _index++;
                }

                bool fraction = false;
                bool exponent = false;
                if (Take('.'))
                {
                    fraction = true;
                    if (_index == _text.Length || !IsDigit(_text[_index])) InvalidJson();
                    while (_index < _text.Length && IsDigit(_text[_index])) _index++;
                }
                if (_index < _text.Length && (_text[_index] == 'e' || _text[_index] == 'E'))
                {
                    exponent = true;
                    _index++;
                    if (_index < _text.Length && (_text[_index] == '+' || _text[_index] == '-')) _index++;
                    if (_index == _text.Length || !IsDigit(_text[_index])) InvalidJson();
                    while (_index < _text.Length && IsDigit(_text[_index])) _index++;
                }

                string token = _text.Substring(start, _index - start);
                NumberStyles integerStyle = NumberStyles.AllowLeadingSign;
                if (!fraction && !exponent)
                {
                    int intValue;
                    if (Int32.TryParse(token, integerStyle, CultureInfo.InvariantCulture, out intValue)) return intValue;
                    long longValue;
                    if (Int64.TryParse(token, integerStyle, CultureInfo.InvariantCulture, out longValue) &&
                        longValue >= -9007199254740991L && longValue <= 9007199254740991L) return longValue;
                }
                double doubleValue;
                if (!Double.TryParse(token, NumberStyles.Float, CultureInfo.InvariantCulture, out doubleValue) ||
                    Double.IsNaN(doubleValue) || Double.IsInfinity(doubleValue)) InvalidJson();
                return doubleValue;
            }

            private void ReadLiteral(string literal)
            {
                if (_index + literal.Length > _text.Length ||
                    String.CompareOrdinal(_text, _index, literal, 0, literal.Length) != 0) InvalidJson();
                _index += literal.Length;
            }

            private bool Take(char expected)
            {
                if (_index < _text.Length && _text[_index] == expected)
                {
                    _index++;
                    return true;
                }
                return false;
            }

            private void SkipWhiteSpace()
            {
                while (_index < _text.Length)
                {
                    char current = _text[_index];
                    if (current != ' ' && current != '\t' && current != '\r' && current != '\n') return;
                    _index++;
                }
            }

            private static bool IsDigit(char value)
            {
                return value >= '0' && value <= '9';
            }

            private void InvalidJson()
            {
                throw new FormatException(
                    "Invalid JSON at index " + _index.ToString(CultureInfo.InvariantCulture) +
                    " of " + _text.Length.ToString(CultureInfo.InvariantCulture) + ".");
            }
        }

        private sealed class JsonWriter
        {
            private readonly int _maxDepth;
            private readonly bool _sortKeys;
            private readonly StringBuilder _output = new StringBuilder();
            private readonly HashSet<object> _ancestors = new HashSet<object>(ReferenceComparer.Instance);

            internal JsonWriter(int maxDepth, bool sortKeys)
            {
                _maxDepth = maxDepth;
                _sortKeys = sortKeys;
            }

            internal string Write(object value)
            {
                WriteValue(value, 1);
                return _output.ToString();
            }

            private void WriteValue(object value, int depth)
            {
                if (depth > _maxDepth) throw new InvalidOperationException("JSON exceeds the maximum depth.");
                if (value == null) { _output.Append("null"); return; }
                value = UnwrapPowerShellObject(value);
                if (value == null) { _output.Append("null"); return; }
                string text = value as string;
                if (text != null) { WriteString(text); return; }
                if (value is char) { WriteString(value.ToString()); return; }
                if (value is bool) { _output.Append((bool)value ? "true" : "false"); return; }
                if (WriteNumber(value)) return;

                IDictionary dictionary = value as IDictionary;
                if (dictionary != null) { WriteObject(dictionary, depth); return; }
                IEnumerable enumerable = value as IEnumerable;
                if (enumerable != null) { WriteArray(enumerable, depth); return; }
                throw new InvalidOperationException("Unsupported JSON value type: " + value.GetType().FullName + ".");
            }

            private static object UnwrapPowerShellObject(object value)
            {
                Type type = value.GetType();
                if (!String.Equals(type.FullName, "System.Management.Automation.PSObject", StringComparison.Ordinal)) return value;
                PropertyInfo baseObject = type.GetProperty("BaseObject", BindingFlags.Public | BindingFlags.Instance);
                if (baseObject == null) return value;
                object unwrapped = baseObject.GetValue(value, null);
                return Object.ReferenceEquals(unwrapped, value) ? value : unwrapped;
            }

            private bool WriteNumber(object value)
            {
                TypeCode code = Type.GetTypeCode(value.GetType());
                if (code == TypeCode.Single)
                {
                    float number = (float)value;
                    if (Single.IsNaN(number) || Single.IsInfinity(number)) throw new InvalidOperationException("JSON number must be finite.");
                    _output.Append(number.ToString("R", CultureInfo.InvariantCulture));
                    return true;
                }
                if (code == TypeCode.Double)
                {
                    double number = (double)value;
                    if (Double.IsNaN(number) || Double.IsInfinity(number)) throw new InvalidOperationException("JSON number must be finite.");
                    _output.Append(number.ToString("R", CultureInfo.InvariantCulture));
                    return true;
                }
                switch (code)
                {
                    case TypeCode.SByte:
                    case TypeCode.Byte:
                    case TypeCode.Int16:
                    case TypeCode.UInt16:
                    case TypeCode.Int32:
                    case TypeCode.UInt32:
                    case TypeCode.Int64:
                    case TypeCode.UInt64:
                    case TypeCode.Decimal:
                        _output.Append(Convert.ToString(value, CultureInfo.InvariantCulture));
                        return true;
                    default:
                        return false;
                }
            }

            private void WriteObject(IDictionary value, int depth)
            {
                Enter(value);
                try
                {
                    List<string> keys = new List<string>();
                    foreach (object key in value.Keys)
                    {
                        string name = key as string;
                        if (name == null) throw new InvalidOperationException("JSON object keys must be strings.");
                        keys.Add(name);
                    }
                    if (_sortKeys) keys.Sort(StringComparer.Ordinal);
                    _output.Append('{');
                    for (int index = 0; index < keys.Count; index++)
                    {
                        if (index > 0) _output.Append(',');
                        string key = keys[index];
                        WriteString(key);
                        _output.Append(':');
                        WriteValue(value[key], depth + 1);
                    }
                    _output.Append('}');
                }
                finally { Exit(value); }
            }

            private void WriteArray(IEnumerable value, int depth)
            {
                Enter(value);
                try
                {
                    _output.Append('[');
                    bool first = true;
                    foreach (object item in value)
                    {
                        if (!first) _output.Append(',');
                        WriteValue(item, depth + 1);
                        first = false;
                    }
                    _output.Append(']');
                }
                finally { Exit(value); }
            }

            private void WriteString(string value)
            {
                _output.Append('"');
                for (int index = 0; index < value.Length; index++)
                {
                    char current = value[index];
                    switch (current)
                    {
                        case '"': _output.Append("\\\""); break;
                        case '\\': _output.Append("\\\\"); break;
                        case '\b': _output.Append("\\b"); break;
                        case '\f': _output.Append("\\f"); break;
                        case '\n': _output.Append("\\n"); break;
                        case '\r': _output.Append("\\r"); break;
                        case '\t': _output.Append("\\t"); break;
                        default:
                            if (current < 0x20 ||
                                (Char.IsHighSurrogate(current) &&
                                    (index + 1 >= value.Length || !Char.IsLowSurrogate(value[index + 1]))) ||
                                Char.IsLowSurrogate(current))
                            {
                                _output.Append("\\u");
                                _output.Append(((int)current).ToString("x4", CultureInfo.InvariantCulture));
                            }
                            else
                            {
                                _output.Append(current);
                                if (Char.IsHighSurrogate(current)) _output.Append(value[++index]);
                            }
                            break;
                    }
                }
                _output.Append('"');
            }

            private void Enter(object value)
            {
                if (!_ancestors.Add(value)) throw new InvalidOperationException("JSON value contains a cycle.");
            }

            private void Exit(object value)
            {
                _ancestors.Remove(value);
            }
        }

        private sealed class ReferenceComparer : IEqualityComparer<object>
        {
            internal static readonly ReferenceComparer Instance = new ReferenceComparer();
            bool IEqualityComparer<object>.Equals(object left, object right) { return Object.ReferenceEquals(left, right); }
            int IEqualityComparer<object>.GetHashCode(object value) { return RuntimeHelpers.GetHashCode(value); }
        }
    }
}
'@
}

function ConvertFrom-GdsJson([string]$Text) {
    return ,([Gds.Local.JsonCodec]::Parse($Text, $script:JsonMaxDepth))
}

function ConvertTo-GdsJson($Value, [bool]$SortKeys = $false) {
    return [Gds.Local.JsonCodec]::Stringify($Value, $script:JsonMaxDepth, $SortKeys)
}

function Fail([string]$Message) {
    throw $Message
}

function Parse-Options([string[]]$Tokens) {
    $options = @{}
    if ($null -eq $Tokens) { return $options }
    if (($Tokens.Count % 2) -ne 0) { Fail 'Every option requires one value.' }
    for ($index = 0; $index -lt $Tokens.Count; $index += 2) {
        $flag = $Tokens[$index]
        if (-not $flag.StartsWith('--')) { Fail "Invalid option $flag." }
        $name = $flag.Substring(2)
        if ($options.ContainsKey($name)) { Fail "Duplicate option $flag." }
        $options[$name] = $Tokens[$index + 1]
    }
    return $options
}

function Require-Option([hashtable]$Options, [string]$Name) {
    if (-not $Options.ContainsKey($Name) -or [string]::IsNullOrWhiteSpace($Options[$Name])) {
        Fail "--$Name is required."
    }
    return [string]$Options[$Name]
}

function Test-Property($Value, [string]$Name) {
    if ($null -eq $Value) { return $false }
    if ($Value -is [Collections.IDictionary]) {
        foreach ($key in @($Value.Keys)) {
            if ([string]$key -ceq $Name) { return $true }
        }
        return $false
    }
    foreach ($property in @($Value.PSObject.Properties)) {
        if ($property.Name -ceq $Name) { return $true }
    }
    return $false
}

function Get-Property($Value, [string]$Name) {
    if ($null -eq $Value) { return $null }
    if ($Value -is [Collections.IDictionary]) {
        foreach ($key in @($Value.Keys)) {
            if ([string]$key -ceq $Name) {
                if ($Value[$key] -is [Array]) { return ,$Value[$key] }
                return $Value[$key]
            }
        }
        return $null
    }
    foreach ($property in @($Value.PSObject.Properties)) {
        if ($property.Name -ceq $Name) {
            if ($property.Value -is [Array]) { return ,$property.Value }
            return $property.Value
        }
    }
    return $null
}

function Get-PropertyNames($Value) {
    if ($null -eq $Value) { return @() }
    if ($Value -is [Collections.IDictionary]) {
        foreach ($key in @($Value.Keys)) { [string]$key }
        return
    }
    foreach ($property in @($Value.PSObject.Properties)) { [string]$property.Name }
}

function Set-Property($Value, [string]$Name, $PropertyValue) {
    if ($Value -is [Collections.IDictionary]) {
        foreach ($key in @($Value.Keys)) {
            if ([string]$key -ceq $Name) {
                $Value[$key] = $PropertyValue
                return
            }
        }
        $Value.Add($Name, $PropertyValue)
        return
    }
    $Value | Add-Member -NotePropertyName $Name -NotePropertyValue $PropertyValue -Force
}

function Remove-Property($Value, [string]$Name) {
    if ($Value -is [Collections.IDictionary]) {
        foreach ($key in @($Value.Keys)) {
            if ([string]$key -ceq $Name) {
                [void]$Value.Remove($key)
                return
            }
        }
        return
    }
    $Value.PSObject.Properties.Remove($Name)
}

function Read-Json([string]$Path, [string]$Label) {
    $item = Get-Item -LiteralPath $Path -Force -ErrorAction Stop
    if ($item.PSIsContainer -or ($item.Attributes -band [IO.FileAttributes]::ReparsePoint)) {
        Fail "$Label must be a regular file."
    }
    try {
        $value = ConvertFrom-GdsJson ([IO.File]::ReadAllText($item.FullName, [Text.Encoding]::UTF8))
        # Match the prior parser behavior: root arrays are emitted item by item.
        # Callers that need an array already wrap this function with @(...).
        return $value
    }
    catch {
        Fail "$Label is not valid JSON."
    }
}

function Get-CommandContract([hashtable]$Options) {
    $path = Join-Path $PSScriptRoot '../contracts/local-helper.json'
    $contract = Read-Json $path 'Local helper command contract'
    $commands = Get-Property $contract 'commands'
    if (-not $Options.ContainsKey('command')) {
        return [ordered]@{
            schema_version = [string](Get-Property $contract 'schema_version')
            commands = @(Get-PropertyNames $commands)
        }
    }
    $name = [string]$Options.command
    if (-not (Test-Property $commands $name)) { Fail "Unknown helper command contract: $name." }
    $definition = Get-Property $commands $name
    return [ordered]@{
        schema_version = [string](Get-Property $contract 'schema_version')
        command = $name
        usage = [string](Get-Property $definition 'usage')
        session_required = [bool](Get-Property $definition 'session_required')
        mutates = [bool](Get-Property $definition 'mutates')
    }
}

function Get-FileDigest([string]$Path) {
    $item = Get-Item -LiteralPath $Path -ErrorAction Stop
    if ($item.PSIsContainer -or ($item.Attributes -band [IO.FileAttributes]::ReparsePoint)) {
        Fail 'Input must be a regular file.'
    }
    $sha = [Security.Cryptography.SHA256]::Create()
    $stream = [IO.File]::OpenRead($item.FullName)
    try { return ([BitConverter]::ToString($sha.ComputeHash($stream))).Replace('-', '').ToLowerInvariant() }
    finally { $stream.Dispose(); $sha.Dispose() }
}

function Get-Sha256Digest([string]$Path) {
    $sha = [Security.Cryptography.SHA256]::Create()
    $stream = [IO.File]::OpenRead($Path)
    try { return ([BitConverter]::ToString($sha.ComputeHash($stream))).Replace('-', '').ToLowerInvariant() }
    finally { $stream.Dispose(); $sha.Dispose() }
}

function Write-JsonAtomic([string]$Path, $Value, [string]$NewLine = "`n") {
    $directory = Split-Path -Parent $Path
    $temporary = Join-Path $directory ('.' + [IO.Path]::GetFileName($Path) + '.' + [Guid]::NewGuid().ToString('N') + '.tmp')
    $text = (ConvertTo-GdsJson $Value) + $NewLine
    [IO.File]::WriteAllText($temporary, $text, $script:Utf8NoBom)
    try {
        if (Test-Path -LiteralPath $Path -PathType Leaf) {
            try { [IO.File]::Replace($temporary, $Path, [NullString]::Value, $true) }
            catch { Move-Item -LiteralPath $temporary -Destination $Path -Force -ErrorAction Stop }
        }
        else {
            Move-Item -LiteralPath $temporary -Destination $Path -ErrorAction Stop
        }
    }
    catch {
        if (Test-Path -LiteralPath $temporary -PathType Leaf) {
            Remove-Item -LiteralPath $temporary -Force -ErrorAction SilentlyContinue
        }
        throw
    }
}

function Write-TextAtomic([string]$Path, [string]$Value) {
    $directory = Split-Path -Parent $Path
    $temporary = Join-Path $directory ('.' + [IO.Path]::GetFileName($Path) + '.' + [Guid]::NewGuid().ToString('N') + '.tmp')
    [IO.File]::WriteAllText($temporary, $Value, $script:Utf8NoBom)
    try {
        if (Test-Path -LiteralPath $Path) {
            $item = Get-Item -LiteralPath $Path -Force -ErrorAction Stop
            if ($item.PSIsContainer -or ($item.Attributes -band [IO.FileAttributes]::ReparsePoint)) {
                Fail 'Generated DBML member must be a regular file.'
            }
            [IO.File]::Delete($item.FullName)
        }
        [IO.File]::Move($temporary, $Path)
    }
    catch {
        if (Test-Path -LiteralPath $temporary -PathType Leaf) {
            [IO.File]::Delete($temporary)
        }
        throw
    }
}

function Resolve-RegularDirectory([string]$Path, [string]$Label) {
    $item = Get-Item -LiteralPath ([IO.Path]::GetFullPath($Path)) -ErrorAction Stop
    if (-not $item.PSIsContainer -or ($item.Attributes -band [IO.FileAttributes]::ReparsePoint)) {
        Fail "$Label must be a regular directory."
    }
    return $item.FullName
}

function Test-SafeJsonInteger($Value, [bool]$AllowZero = $true) {
    if ($Value -is [bool] -or -not (
        $Value -is [byte] -or $Value -is [sbyte] -or $Value -is [short] -or
        $Value -is [ushort] -or $Value -is [int] -or $Value -is [uint] -or
        $Value -is [long] -or $Value -is [ulong] -or $Value -is [single] -or
        $Value -is [double] -or $Value -is [decimal]
    )) { return $false }
    $number = [double]$Value
    if ([double]::IsNaN($number) -or [double]::IsInfinity($number) -or
        [math]::Truncate($number) -ne $number -or [math]::Abs($number) -gt 9007199254740991) {
        return $false
    }
    if ($AllowZero) { return $number -ge 0 }
    return $number -gt 0
}

function Assert-SafeSnapshotMemberPath([string]$RelativePath) {
    $unsafePart = $false
    if (-not [string]::IsNullOrWhiteSpace($RelativePath)) {
        foreach ($part in @($RelativePath.Split('/'))) {
            if ([string]::IsNullOrEmpty($part) -or $part -eq '.' -or $part -eq '..') {
                $unsafePart = $true
                break
            }
        }
    }
    if ([string]::IsNullOrWhiteSpace($RelativePath) -or [IO.Path]::IsPathRooted($RelativePath) -or
        $RelativePath.Contains(':') -or $RelativePath.Contains('\') -or
        $RelativePath.IndexOf([char]0) -ge 0 -or $unsafePart) {
        Fail 'Snapshot manifest contains an unsafe member path.'
    }
}

function Resolve-Member([string]$Root, [string]$RelativePath, $Members) {
    Assert-SafeSnapshotMemberPath $RelativePath
    if (-not $Members.ContainsKey($RelativePath)) {
        Fail "Snapshot member $RelativePath is missing from the manifest inventory."
    }
    $candidate = Resolve-WorkspacePath $Root $RelativePath
    $item = Get-Item -LiteralPath $candidate -ErrorAction Stop
    if ($item.PSIsContainer -or ($item.Attributes -band [IO.FileAttributes]::ReparsePoint)) {
        Fail 'Snapshot member must be a regular file.'
    }
    $member = $Members[$RelativePath]
    if ([long]$item.Length -ne [long]$member.size_bytes) { Fail "Snapshot member size mismatch: $RelativePath." }
    if ((Get-Sha256Digest $item.FullName) -cne [string]$member.sha256) {
        Fail "Snapshot member SHA-256 mismatch: $RelativePath."
    }
    return $item.FullName
}

function ConvertTo-Casefold([string]$Value) {
    if ($null -eq $script:CasefoldMap) {
        $mapPath = Join-Path (Split-Path -Parent $PSScriptRoot) 'workbench\unicode-casefold.json'
        $script:CasefoldMap = Read-Json $mapPath 'Unicode casefold table'
    }
    $builder = New-Object Text.StringBuilder
    for ($index = 0; $index -lt $Value.Length; $index++) {
        $codePoint = [char]::ConvertToUtf32($Value, $index)
        if ($codePoint -gt 0xFFFF) { $index++ }
        $mapped = Get-Property $script:CasefoldMap ([string]$codePoint)
        if ($null -ne $mapped) { [void]$builder.Append([string]$mapped) }
        else { [void]$builder.Append([char]::ConvertFromUtf32($codePoint)) }
    }
    return $builder.ToString()
}

function Normalize-Value([string]$Area, [string]$Field, $Value) {
    if ($Value -isnot [string]) { return $Value }
    if ($Area -eq 'model') {
        return ConvertTo-Casefold ($Value.Trim([char]0x20))
    }
    if ($Field -match '(_code|_name|_schema)$') {
        return $Value.Trim([char]0x20).ToLowerInvariant()
    }
    return $Value
}

function Get-CanonicalKey([string]$Area, $Dataset, $Record) {
    $values = New-Object System.Collections.ArrayList
    foreach ($field in @($Dataset.canonical_key)) {
        if (-not (Test-Property $Record ([string]$field))) { Fail "$($Dataset.name).$field is required by its canonical key." }
        [void]$values.Add((Normalize-Value $Area ([string]$field) (Get-Property $Record ([string]$field))))
    }
    return ConvertTo-GdsJson @($values)
}

function Get-CanonicalKeyObject([string]$Area, $Dataset, $Record) {
    $key = [ordered]@{}
    foreach ($field in @($Dataset.canonical_key)) {
        $name = [string]$field
        if (-not (Test-Property $Record $name)) { Fail "$($Dataset.name).$name is required by its canonical key." }
        $key[$name] = Normalize-Value $Area $name (Get-Property $Record $name)
    }
    return $key
}

function Test-Where($Record, $Where, [string]$Area) {
    foreach ($name in @(Get-PropertyNames $Where)) {
        if (-not (Test-Property $Record $name)) { return $false }
        $actual = Normalize-Value $Area $name (Get-Property $Record $name)
        $expected = Normalize-Value $Area $name (Get-Property $Where $name)
        if ($actual -ne $expected) { return $false }
    }
    return $true
}

function Parse-Object([hashtable]$Options, [string]$Name) {
    $text = Require-Option $Options $Name
    try { $value = ConvertFrom-GdsJson $text }
    catch { Fail "--$Name must be a JSON object." }
    if ($null -eq $value -or $value -is [Array] -or $value -is [string] -or $value -is [ValueType]) {
        Fail "--$Name must be a JSON object."
    }
    return $value
}

function Select-Records([hashtable]$Options, $Snapshot) {
    $datasetName = Require-Option $Options 'dataset'
    if (-not $Snapshot.ByName.ContainsKey($datasetName)) { Fail "Unknown Snapshot dataset: $datasetName." }
    $limit = 50
    if ($Options.ContainsKey('limit')) { $limit = [int]$Options['limit'] }
    if ($limit -lt 1 -or $limit -gt 200) { Fail '--limit must be between 1 and 200.' }
    $where = if ($Options.ContainsKey('where')) { Parse-Object $Options 'where' } else { @{} }
    $dataset = $Snapshot.ByName[$datasetName]
    $rowsPath = Resolve-Member $Snapshot.Root ([string]$dataset.rows_file) $Snapshot.Members
    $records = New-Object System.Collections.ArrayList
    $truncated = $false
    $lineNumber = 0
    foreach ($line in [IO.File]::ReadLines($rowsPath, [Text.Encoding]::UTF8)) {
        $lineNumber++
        if ([string]::IsNullOrWhiteSpace($line)) { continue }
        try { $record = ConvertFrom-GdsJson $line }
        catch { Fail "$datasetName contains invalid JSON on line $lineNumber." }
        if (-not (Test-Where $record $where $Snapshot.Area)) { continue }
        if ($records.Count -eq $limit) { $truncated = $true; break }
        [void]$records.Add($record)
    }
    return [pscustomobject]@{ Dataset = $dataset; Records = @($records); Truncated = $truncated }
}

function Inspect-Snapshot([hashtable]$Options) {
    $snapshot = Find-Snapshot $Options
    $datasets = New-Object System.Collections.ArrayList
    foreach ($dataset in @($snapshot.Datasets)) { [void]$datasets.Add(@([string]$dataset.name, [int]$dataset.row_count)) }
    $revision = if (Test-Property $snapshot.Manifest 'model_revision') { $snapshot.Manifest.model_revision } else { $null }
    $id = if (Test-Property $snapshot.Manifest 'snapshot_id') { [string]$snapshot.Manifest.snapshot_id } else { $null }
    return [ordered]@{ area = $snapshot.Area; kind = [string]$snapshot.Catalog.snapshot_kind; id = $id; revision = $revision; datasets = @($datasets) }
}

function ConvertTo-CompactAuthoringSchema($Value) {
    if ($null -eq $Value) { return $null }
    if ($Value -is [Collections.IDictionary] -or ($Value -isnot [Array] -and $Value -isnot [Collections.ArrayList] -and $Value -isnot [string] -and @($Value.PSObject.Properties).Count -gt 0)) {
        $result = New-Object Collections.Specialized.OrderedDictionary ([StringComparer]::Ordinal)
        foreach ($name in @(Get-PropertyNames $Value)) {
            if (@('x-gds-columns', 'x-gds-governed-authoring-schema', 'x-gds-stage-record-validation') -ccontains $name) { continue }
            $result.Add($name, (ConvertTo-CompactAuthoringSchema (Get-Property $Value $name)))
        }
        return $result
    }
    if ($Value -is [Array] -or $Value -is [Collections.ArrayList]) {
        $result = New-Object Collections.ArrayList
        foreach ($item in @($Value)) { [void]$result.Add((ConvertTo-CompactAuthoringSchema $item)) }
        return ,$result.ToArray()
    }
    return $Value
}

function Describe-Dataset([hashtable]$Options) {
    $snapshot = Find-Snapshot $Options
    $datasetName = Require-Option $Options 'dataset'
    if (-not $snapshot.ByName.ContainsKey($datasetName)) { Fail "Unknown Snapshot dataset: $datasetName." }
    $dataset = $snapshot.ByName[$datasetName]
    if (-not (Test-Property $dataset 'schema_file')) { Fail "$datasetName schema path is missing." }
    $schema = Read-Json (Resolve-Member $snapshot.Root ([string]$dataset.schema_file) $snapshot.Members) "$datasetName schema"
    $detail = if ($Options.ContainsKey('detail')) { [string]$Options.detail } else { 'compact' }
    if (@('compact', 'full') -cnotcontains $detail) { Fail '--detail must be compact or full.' }
    return [ordered]@{
        detail = $detail
        dataset = $datasetName
        count = [int]$dataset.row_count
        canonical_key = @($dataset.canonical_key)
        authoring_schema = ConvertTo-CompactAuthoringSchema $schema
        schema = if ($detail -ceq 'full') { $schema } else { $null }
    }
}

function Select-Snapshot([hashtable]$Options) {
    $snapshot = Find-Snapshot $Options
    if ($Options.ContainsKey('view') -and @('snapshot', 'effective') -cnotcontains $Options.view) { Fail '--view must be snapshot or effective.' }
    if ($Options['view'] -ceq 'effective') {
        $name = Require-Option $Options 'dataset'
        if (-not $snapshot.ByName.ContainsKey($name)) { Fail 'Unknown Snapshot dataset.' }
        $limit = if ($Options.ContainsKey('limit')) { [int]$Options.limit } else { 50 }
        if ($limit -lt 1 -or $limit -gt 200) { Fail '--limit must be between 1 and 200.' }
        $where = if ($Options.ContainsKey('where')) { Parse-Object $Options 'where' } else { @{} }
        $directory = Resolve-WorkspacePath $snapshot.Session ((Get-OwnerPrefix $snapshot.Owner) + $snapshot.Area + '-change-set')
        $pending = @()
        if (Test-Path -LiteralPath $directory) {
            $snapshot | Add-Member -NotePropertyName ChangeDirectory -NotePropertyValue $directory
            $allPending = Read-Pending $snapshot
            if ($allPending.ContainsKey($name)) { $pending = @($allPending[$name]) }
        }
        $matches = @(Get-EffectiveRecords $snapshot $snapshot.ByName[$name] $pending | Where-Object { Test-Where $_ $where $snapshot.Area })
        return [ordered]@{dataset = $name; view = 'effective'; count = [Math]::Min($matches.Count, $limit); truncated = $matches.Count -gt $limit; records = @($matches | Select-Object -First $limit)}
    }
    $selection = Select-Records $Options $snapshot
    return [ordered]@{
        dataset = [string]$selection.Dataset.name
        count = @($selection.Records).Count
        truncated = [bool]$selection.Truncated
        records = @($selection.Records)
    }
}

function Get-WorkspaceDigest($Context) {
    $names = New-Object System.Collections.Generic.List[string]
    foreach ($item in @(Get-ChildItem -LiteralPath $Context.ChangeDirectory -Force)) {
        if ($item.PSIsContainer -or ($item.Attributes -band [IO.FileAttributes]::ReparsePoint) -or -not $item.Name.EndsWith('.json')) {
            Fail 'Local Change Set contains an unsupported entry.'
        }
        [void]$names.Add($item.Name)
    }
    $names.Sort([StringComparer]::Ordinal)
    $sha = [Security.Cryptography.SHA256]::Create()
    try {
        foreach ($name in $names) {
            $path = Join-Path $Context.ChangeDirectory $name
            $bytes = [IO.File]::ReadAllBytes($path)
            $prefix = [Text.Encoding]::UTF8.GetBytes($name + [char]0 + $bytes.Length.ToString() + [char]0)
            [void]$sha.TransformBlock($prefix, 0, $prefix.Length, $prefix, 0)
            if ($bytes.Length -gt 0) { [void]$sha.TransformBlock($bytes, 0, $bytes.Length, $bytes, 0) }
        }
        [void]$sha.TransformFinalBlock([byte[]]@(), 0, 0)
        return ([BitConverter]::ToString($sha.Hash)).Replace('-', '').ToLowerInvariant()
    }
    finally { $sha.Dispose() }
}

function Assert-Digest([hashtable]$Options, $Context) {
    $expected = Require-Option $Options 'expected-digest'
    $actual = Get-WorkspaceDigest $Context
    if ($expected -eq 'empty') {
        if (@(Get-ChildItem -LiteralPath $Context.ChangeDirectory -Force).Count -ne 0) {
            Fail "Local Change Set digest conflict: expected an empty directory, found $actual."
        }
        return
    }
    if ($expected -notmatch '^[0-9a-f]{64}$') { Fail '--expected-digest must be empty or a lowercase SHA-256 digest.' }
    if ($expected -ne $actual) { Fail "Local Change Set digest conflict: expected $expected, found $actual." }
}

function Read-Pending($Context) {
    $pending = @{}
    foreach ($item in @(Get-ChildItem -LiteralPath $Context.ChangeDirectory -Force)) {
        if ($item.PSIsContainer -or ($item.Attributes -band [IO.FileAttributes]::ReparsePoint) -or -not $item.Name.EndsWith('.json')) {
            Fail 'Local Change Set contains an unsupported entry.'
        }
        $name = $item.BaseName
        if (-not $Context.ByName.ContainsKey($name)) { Fail "Local Change Set contains unknown dataset $name." }
        [void](Get-EditableSchema $Context $Context.ByName[$name])
        $raw = [IO.File]::ReadAllText($item.FullName, [Text.Encoding]::UTF8)
        if (-not $raw.TrimStart().StartsWith('[')) { Fail "$name pending file must contain a JSON array." }
        try {
            $parsed = ConvertFrom-GdsJson $raw
            if ($parsed -isnot [Array]) { throw 'Pending root is not an array.' }
            $records = @($parsed)
        }
        catch { Fail "$name pending file is not valid JSON." }
        $seen = New-Object 'System.Collections.Generic.Dictionary[string,bool]'
        foreach ($record in $records) {
            if ($null -eq $record -or $record -is [Array] -or $record -is [string] -or $record -is [ValueType]) {
                Fail "$name pending file contains a non-object record."
            }
            $key = Get-CanonicalKey $Context.Area $Context.ByName[$name] $record
            if ($seen.ContainsKey($key)) { Fail "$name pending file contains a duplicate canonical key." }
            $seen[$key] = $true
        }
        $pending[$name] = @($records)
    }
    return $pending
}

function Read-SnapshotRecords($Context, $Dataset) {
    $records = New-Object System.Collections.ArrayList
    $path = Resolve-Member $Context.Root ([string]$Dataset.rows_file) $Context.Members
    $lineNumber = 0
    foreach ($line in [IO.File]::ReadLines($path, [Text.Encoding]::UTF8)) {
        $lineNumber++
        if ([string]::IsNullOrWhiteSpace($line)) { continue }
        try { [void]$records.Add((ConvertFrom-GdsJson $line)) }
        catch { Fail "$($Dataset.name) contains invalid JSON on line $lineNumber." }
    }
    return @($records)
}

function Get-DatasetSchema($Context, $Dataset) {
    if (-not (Test-Property $Dataset 'schema_file')) { Fail "$($Dataset.name) schema path is missing." }
    return Read-Json (Resolve-Member $Context.Root ([string]$Dataset.schema_file) $Context.Members) "$($Dataset.name) schema"
}

function Get-EditableSchema($Context, $Dataset) {
    $schema = Get-DatasetSchema $Context $Dataset
    if (-not (Test-Property $schema 'x-gds-change-set-eligible') -or -not [bool]$schema.'x-gds-change-set-eligible') {
        Fail "$($Dataset.name) is not Change Set eligible."
    }
    return $schema
}

function Get-JsonSchemaType($Value) {
    if ($null -eq $Value) { return 'null' }
    if ($Value -is [Array]) { return 'array' }
    if ($Value -is [string]) { return 'string' }
    if ($Value -is [bool]) { return 'boolean' }
    if ($Value -is [byte] -or $Value -is [sbyte] -or $Value -is [short] -or
        $Value -is [ushort] -or $Value -is [int] -or $Value -is [uint] -or
        $Value -is [long] -or $Value -is [ulong]) { return 'integer' }
    if ($Value -is [decimal]) {
        if ([decimal]::Truncate([decimal]$Value) -eq [decimal]$Value) { return 'integer' }
        return 'number'
    }
    if ($Value -is [single] -or $Value -is [double]) {
        $number = [double]$Value
        if (-not [double]::IsNaN($number) -and -not [double]::IsInfinity($number) -and
            [math]::Truncate($number) -eq $number) { return 'integer' }
        return 'number'
    }
    return 'object'
}

function Test-JsonNumber($Value) {
    return (
        $Value -is [byte] -or $Value -is [sbyte] -or $Value -is [short] -or
        $Value -is [ushort] -or $Value -is [int] -or $Value -is [uint] -or
        $Value -is [long] -or $Value -is [ulong] -or $Value -is [single] -or
        $Value -is [double] -or $Value -is [decimal]
    )
}

function Test-JsonSchemaFormat([string]$Value, [string]$Format) {
    switch -CaseSensitive ($Format) {
        'date' {
            $match = [regex]::Match($Value, '^([0-9]{4})-([0-9]{2})-([0-9]{2})\z', [Text.RegularExpressions.RegexOptions]::CultureInvariant)
            if (-not $match.Success) { return $false }
            $year = [int]$match.Groups[1].Value
            $month = [int]$match.Groups[2].Value
            $day = [int]$match.Groups[3].Value
            $leap = ($year % 4 -eq 0) -and (($year % 100 -ne 0) -or ($year % 400 -eq 0))
            $february = if ($leap) { 29 } else { 28 }
            $days = @(31, $february, 31, 30, 31, 30, 31, 31, 30, 31, 30, 31)
            return (
                $month -ge 1 -and $month -le 12 -and
                $day -ge 1 -and $day -le $days[$month - 1]
            )
        }
        'date-time' {
            $separator = $Value.IndexOf('T', [StringComparison]::Ordinal)
            return (
                $separator -gt 0 -and
                (Test-JsonSchemaFormat $Value.Substring(0, $separator) 'date') -and
                (Test-JsonSchemaFormat $Value.Substring($separator + 1) 'time')
            )
        }
        'time' {
            $match = [regex]::Match(
                $Value,
                '^([0-9]{2}):([0-9]{2}):([0-9]{2})(?:\.[0-9]+)?(?:Z|([+-])([0-9]{2}):([0-9]{2}))\z',
                [Text.RegularExpressions.RegexOptions]::CultureInvariant
            )
            if (-not $match.Success) { return $false }
            return (
                [int]$match.Groups[1].Value -le 23 -and
                [int]$match.Groups[2].Value -le 59 -and
                [int]$match.Groups[3].Value -le 59 -and
                (-not $match.Groups[4].Success -or
                    ([int]$match.Groups[5].Value -le 23 -and [int]$match.Groups[6].Value -le 59))
            )
        }
        'uuid' {
            return [regex]::IsMatch(
                $Value,
                '^[0-9a-f]{8}-[0-9a-f]{4}-[1-8][0-9a-f]{3}-[89ab][0-9a-f]{3}-[0-9a-f]{12}\z',
                [Text.RegularExpressions.RegexOptions]::IgnoreCase -bor [Text.RegularExpressions.RegexOptions]::CultureInvariant
            )
        }
        default { return $true }
    }
}

function Test-JsonSchemaPattern([string]$Value, [string]$Pattern) {
    if ($Pattern -ceq '\S') {
        foreach ($character in $Value.ToCharArray()) {
            $codePoint = [int]$character
            $whiteSpace = @(
                0x0009, 0x000A, 0x000B, 0x000C, 0x000D, 0x0020, 0x00A0, 0x1680,
                0x2028, 0x2029, 0x202F, 0x205F, 0x3000, 0xFEFF
            ) -contains $codePoint -or ($codePoint -ge 0x2000 -and $codePoint -le 0x200A)
            if (-not $whiteSpace) { return $true }
        }
        return $false
    }
    return [regex]::IsMatch($Value, $Pattern, [Text.RegularExpressions.RegexOptions]::ECMAScript)
}

function Get-SchemaIssues {
    param(
        $Value,
        $Schema,
        $Root = $null,
        [string]$Location = '$',
        [string[]]$SeenReferences = @()
    )

    $issues = New-Object System.Collections.ArrayList
    if ($null -eq $Schema -or $Schema -is [Array] -or $Schema -is [string] -or $Schema -is [ValueType]) {
        [void]$issues.Add("$Location`: schema is invalid")
        return @($issues)
    }
    if ($null -eq $Root) { $Root = $Schema }

    $referenceValue = Get-Property $Schema '$ref'
    if ($referenceValue -is [string]) {
        $reference = [string]$referenceValue
        if (-not $reference.StartsWith('#/$defs/', [StringComparison]::Ordinal)) {
            [void]$issues.Add("$Location`: unsupported schema reference")
            return @($issues)
        }
        if (@($SeenReferences) -ccontains $reference) {
            [void]$issues.Add("$Location`: unresolved schema reference")
            return @($issues)
        }
        $definitions = Get-Property $Root '$defs'
        $name = $reference.Substring(8)
        $target = if ($null -ne $definitions) { Get-Property $definitions $name } else { $null }
        if ($null -eq $target) {
            [void]$issues.Add("$Location`: unresolved schema reference")
            return @($issues)
        }
        return @(Get-SchemaIssues -Value $Value -Schema $target -Root $Root -Location $Location -SeenReferences @($SeenReferences + $reference))
    }

    $anyOf = Get-Property $Schema 'anyOf'
    if ($anyOf -is [Array]) {
        $matches = 0
        foreach ($option in @($anyOf)) {
            if (@(Get-SchemaIssues -Value $Value -Schema $option -Root $Root -Location $Location -SeenReferences @()).Count -eq 0) {
                $matches++
            }
        }
        if ($matches -eq 0) {
            [void]$issues.Add("$Location`: value does not match any allowed schema")
            return @($issues)
        }
    }
    $oneOf = Get-Property $Schema 'oneOf'
    if ($oneOf -is [Array]) {
        $matches = 0
        foreach ($option in @($oneOf)) {
            if (@(Get-SchemaIssues -Value $Value -Schema $option -Root $Root -Location $Location -SeenReferences @()).Count -eq 0) {
                $matches++
            }
        }
        if ($matches -ne 1) {
            [void]$issues.Add("$Location`: value must match exactly one allowed schema")
            return @($issues)
        }
    }
    $allOf = Get-Property $Schema 'allOf'
    if ($allOf -is [Array]) {
        foreach ($option in @($allOf)) {
            foreach ($issue in @(Get-SchemaIssues -Value $Value -Schema $option -Root $Root -Location $Location -SeenReferences $SeenReferences)) {
                [void]$issues.Add($issue)
            }
        }
    }
    $condition = Get-Property $Schema 'if'
    if ($null -ne $condition -and $condition -isnot [Array] -and $condition -isnot [string] -and
        $condition -isnot [ValueType]) {
        $conditionMatches = @(
            Get-SchemaIssues -Value $Value -Schema $condition -Root $Root -Location $Location -SeenReferences @()
        ).Count -eq 0
        $branch = if ($conditionMatches) { Get-Property $Schema 'then' } else { Get-Property $Schema 'else' }
        if ($null -ne $branch) {
            foreach ($issue in @(Get-SchemaIssues -Value $Value -Schema $branch -Root $Root -Location $Location -SeenReferences $SeenReferences)) {
                [void]$issues.Add($issue)
            }
        }
    }

    if (Test-Property $Schema 'const') {
        if ((ConvertTo-StableJson $Value) -cne (ConvertTo-StableJson (Get-Property $Schema 'const'))) {
            [void]$issues.Add("$Location`: fixed value is required")
            return @($issues)
        }
    }
    $enum = Get-Property $Schema 'enum'
    if ($enum -is [Array]) {
        $matched = $false
        foreach ($allowed in @($enum)) {
            if ((ConvertTo-StableJson $Value) -ceq (ConvertTo-StableJson $allowed)) {
                $matched = $true
                break
            }
        }
        if (-not $matched) {
            [void]$issues.Add("$Location`: value is not allowed")
            return @($issues)
        }
    }

    $schemaType = Get-Property $Schema 'type'
    $types = @()
    if ($schemaType -is [Array]) { $types = @($schemaType) }
    elseif ($schemaType) { $types = @($schemaType) }
    $actualType = Get-JsonSchemaType $Value
    if ($types.Count -gt 0 -and @($types) -cnotcontains $actualType -and
        -not ($actualType -ceq 'integer' -and @($types) -ccontains 'number')) {
        [void]$issues.Add("$Location`: expected $([string]::Join(' or ', @($types)))")
        return @($issues)
    }

    if ($actualType -ceq 'string') {
        $minLength = Get-Property $Schema 'minLength'
        if ((Get-JsonSchemaType $minLength) -ceq 'integer' -and $Value.Length -lt [double]$minLength) {
            [void]$issues.Add("$Location`: shorter than minLength")
        }
        $maxLength = Get-Property $Schema 'maxLength'
        if ((Get-JsonSchemaType $maxLength) -ceq 'integer' -and $Value.Length -gt [double]$maxLength) {
            [void]$issues.Add("$Location`: longer than maxLength")
        }
        $pattern = Get-Property $Schema 'pattern'
        if ($pattern -is [string]) {
            try {
                if (-not (Test-JsonSchemaPattern $Value $pattern)) {
                    [void]$issues.Add("$Location`: fails pattern")
                }
            }
            catch { [void]$issues.Add("$Location`: schema pattern is invalid") }
        }
        $format = Get-Property $Schema 'format'
        if ($format -is [string] -and -not (Test-JsonSchemaFormat $Value $format)) {
            [void]$issues.Add("$Location`: fails $format format")
        }
    }
    if ($actualType -ceq 'integer' -or $actualType -ceq 'number') {
        $number = [double]$Value
        if ([double]::IsNaN($number) -or [double]::IsInfinity($number)) {
            [void]$issues.Add("$Location`: number must be finite")
        }
        else {
            $minimum = Get-Property $Schema 'minimum'
            $maximum = Get-Property $Schema 'maximum'
            $exclusiveMinimum = Get-Property $Schema 'exclusiveMinimum'
            $exclusiveMaximum = Get-Property $Schema 'exclusiveMaximum'
            if ((Test-JsonNumber $minimum) -and $number -lt [double]$minimum) {
                [void]$issues.Add("$Location`: below minimum")
            }
            if ((Test-JsonNumber $maximum) -and $number -gt [double]$maximum) {
                [void]$issues.Add("$Location`: above maximum")
            }
            if ((Test-JsonNumber $exclusiveMinimum) -and $number -le [double]$exclusiveMinimum) {
                [void]$issues.Add("$Location`: not above exclusiveMinimum")
            }
            if ((Test-JsonNumber $exclusiveMaximum) -and $number -ge [double]$exclusiveMaximum) {
                [void]$issues.Add("$Location`: not below exclusiveMaximum")
            }
        }
    }
    if ($actualType -ceq 'array') {
        $items = @($Value)
        $minItems = Get-Property $Schema 'minItems'
        if ((Get-JsonSchemaType $minItems) -ceq 'integer' -and $items.Count -lt [double]$minItems) {
            [void]$issues.Add("$Location`: fewer than minItems")
        }
        $maxItems = Get-Property $Schema 'maxItems'
        if ((Get-JsonSchemaType $maxItems) -ceq 'integer' -and $items.Count -gt [double]$maxItems) {
            [void]$issues.Add("$Location`: more than maxItems")
        }
        $itemSchema = Get-Property $Schema 'items'
        if ($null -ne $itemSchema -and -not ($itemSchema -is [bool] -and -not $itemSchema)) {
            for ($index = 0; $index -lt $items.Count; $index++) {
                foreach ($issue in @(Get-SchemaIssues -Value $items[$index] -Schema $itemSchema -Root $Root -Location "$Location[$index]" -SeenReferences @())) {
                    [void]$issues.Add($issue)
                }
            }
        }
    }
    if ($actualType -ceq 'object') {
        $properties = Get-Property $Schema 'properties'
        $required = Get-Property $Schema 'required'
        $requiredFields = @()
        if ($required -is [Array]) { $requiredFields = @($required) }
        foreach ($field in $requiredFields) {
            if (-not (Test-Property $Value ([string]$field))) {
                [void]$issues.Add("$Location.$field`: required field is missing")
            }
        }
        $additionalProperties = Get-Property $Schema 'additionalProperties'
        if ($additionalProperties -is [bool] -and -not $additionalProperties) {
            $allowed = @()
            if ($null -ne $properties) {
                $allowed = @(Get-PropertyNames $properties)
            }
            foreach ($name in @(Get-PropertyNames $Value)) {
                if (@($allowed) -cnotcontains $name) {
                    [void]$issues.Add("$Location.$name`: additional property is forbidden")
                }
            }
        }
        if ($null -ne $properties) {
            foreach ($name in @(Get-PropertyNames $Value)) {
                $childSchema = Get-Property $properties $name
                if ($null -eq $childSchema) { continue }
                foreach ($issue in @(Get-SchemaIssues -Value (Get-Property $Value $name) -Schema $childSchema -Root $Root -Location "$Location.$name" -SeenReferences @())) {
                    [void]$issues.Add($issue)
                }
            }
        }
    }
    # Match the shared Analysis record invariant after its field types pass.
    $recordContract = Get-Property $Schema 'x-gds-record-validation'
    $recordRules = Get-Property $recordContract 'rules'
    if ($issues.Count -eq 0 -and $null -ne $recordContract -and
        $recordRules -ccontains 'analysis_result') {
        $fields = @('validation_policy_version', 'validation_result',
            'validation_source_non_null_count', 'validation_source_distinct_count',
            'validation_target_non_null_count', 'validation_target_distinct_count',
            'validation_source_missing_target_count', 'validation_unused_target_count',
            'validation_duplicate_target_key_count')
        $present = @($fields | Where-Object { $null -ne (Get-Property $Value $_) })
        if ($present.Count -gt 0 -and $present.Count -ne $fields.Count) {
            [void]$issues.Add("$Location`: Analysis validation fields must all be present or all be absent")
        }
        elseif ($present.Count -eq $fields.Count) {
            $sourceRows = Get-Property $Value 'validation_source_non_null_count'
            $sourceDistinct = Get-Property $Value 'validation_source_distinct_count'
            $targetRows = Get-Property $Value 'validation_target_non_null_count'
            $targetDistinct = Get-Property $Value 'validation_target_distinct_count'
            $missing = Get-Property $Value 'validation_source_missing_target_count'
            $unused = Get-Property $Value 'validation_unused_target_count'
            $duplicates = Get-Property $Value 'validation_duplicate_target_key_count'
            if ($sourceDistinct -gt $sourceRows -or (($sourceRows -eq 0) -ne ($sourceDistinct -eq 0))) {
                [void]$issues.Add("$Location`: Source validation counts do not reconcile")
            }
            if ($targetDistinct -gt $targetRows -or (($targetRows -eq 0) -ne ($targetDistinct -eq 0))) {
                [void]$issues.Add("$Location`: Target validation counts do not reconcile")
            }
            if ($missing -gt $sourceDistinct) {
                [void]$issues.Add("$Location`: Missing-target count exceeds source distinct count")
            }
            if ($unused -gt $targetDistinct) {
                [void]$issues.Add("$Location`: Unused-target count exceeds target distinct count")
            }
            if (($sourceDistinct - $missing) -ne ($targetDistinct - $unused)) {
                [void]$issues.Add("$Location`: Matched distinct counts do not reconcile")
            }
            if ($duplicates -ne ($targetRows - $targetDistinct)) {
                [void]$issues.Add("$Location`: Duplicate-target count does not reconcile")
            }
            $expected = if ($sourceRows -eq 0 -or $targetRows -eq 0) { 'inconclusive' }
                elseif ($missing -eq 0 -and $duplicates -eq 0) { 'supported' } else { 'unsupported' }
            if ((Get-Property $Value 'validation_result') -cne $expected) {
                [void]$issues.Add("$Location`: Analysis validation result does not match its evidence")
            }
        }
    }
    return @($issues)
}

function Add-LocalValidationIssue(
    $Issues,
    [string]$Dataset,
    $Record,
    [string]$Code,
    $Detail = $null,
    $Field = $null
) {
    if ($Issues.Count -ge 200) { return }
    $humanCode = $Code.Replace('_', ' ')
    $message = if ($null -eq $Detail -or [string]$Detail -ceq $Code) {
        "${Code}: $humanCode"
    }
    else {
        "${Code}: ${humanCode}: $Detail"
    }
    [void]$Issues.Add([pscustomobject]@{
        Dataset = $Dataset
        Record = $Record
        Code = $Code
        Detail = if ($null -eq $Detail) { $Code } else { [string]$Detail }
        Field = $Field
        Issue = @($Dataset, $Record, $message)
    })
}

function Get-EffectiveRecords($Context, $Dataset, [object[]]$Draft) {
    $records = New-Object 'System.Collections.Generic.Dictionary[string,object]'
    foreach ($record in @(Read-SnapshotRecords $Context $Dataset)) {
        $records[(Get-CanonicalKey $Context.Area $Dataset $record)] = $record
    }
    foreach ($record in $Draft) {
        $records[(Get-CanonicalKey $Context.Area $Dataset $record)] = $record
    }
    $keys = New-Object 'System.Collections.Generic.List[string]'
    foreach ($key in $records.Keys) { [void]$keys.Add($key) }
    $keys.Sort([StringComparer]::Ordinal)
    $effective = New-Object System.Collections.ArrayList
    foreach ($key in $keys) { [void]$effective.Add($records[$key]) }
    return @($effective)
}

function Get-ValidationRecordType($Dataset, $Schema) {
    $recordType = Get-Property $Schema 'x-gds-record-type'
    if ($recordType -is [string] -and -not [string]::IsNullOrWhiteSpace($recordType)) {
        return $recordType
    }
    $recordType = Get-Property $Dataset 'record_type'
    if ($recordType -is [string] -and -not [string]::IsNullOrWhiteSpace($recordType)) {
        return $recordType
    }
    return [string]$Dataset.name
}

function Get-NormalizedValidationKey([string]$Area, [object[]]$Fields, $Record) {
    $parts = New-Object System.Collections.Generic.List[string]
    foreach ($field in @($Fields)) {
        if (-not (Test-Property $Record ([string]$field))) {
            [void]$parts.Add('')
            continue
        }
        $value = Get-Property $Record ([string]$field)
        if ($value -is [string]) { $value = Normalize-Value $Area ([string]$field) $value }
        [void]$parts.Add((ConvertTo-StableJson $value))
    }
    return '[' + ($parts -join ',') + ']'
}

function Test-ValidationConstraint($Constraint) {
    if ($Constraint -isnot [Array] -or @($Constraint).Count -eq 0) { return $false }
    foreach ($field in @($Constraint)) {
        if ($field -isnot [string] -or [string]::IsNullOrEmpty([string]$field)) { return $false }
    }
    return $true
}

function Add-CommonValidationIssues([string]$Area, [object[]]$States, $Issues) {
    foreach ($state in @($States)) {
        if (-not [string]::IsNullOrWhiteSpace([string]$state.OverlayError)) {
            Add-LocalValidationIssue $Issues $state.Dataset.name $null 'effective_overlay' $state.OverlayError
        }
        $recordNumber = 0
        foreach ($record in @($state.Pending)) {
            $recordNumber++
            foreach ($message in @(Get-SchemaIssues $record $state.Schema)) {
                Add-LocalValidationIssue $Issues $state.Dataset.name $recordNumber 'schema' $message
            }
        }

        $constraints = Get-Property $state.Schema 'x-gds-unique-constraints'
        if ((Test-Property $state.Schema 'x-gds-unique-constraints') -and $constraints -isnot [Array]) {
            Add-LocalValidationIssue $Issues $state.Dataset.name $null 'invalid_unique_constraint_contract'
            continue
        }
        if ($constraints -isnot [Array]) { continue }
        foreach ($constraint in @($constraints)) {
            if (-not (Test-ValidationConstraint $constraint)) {
                Add-LocalValidationIssue $Issues $state.Dataset.name $null 'invalid_unique_constraint_contract'
                continue
            }
            $seen = New-Object 'System.Collections.Generic.Dictionary[string,bool]'
            $effectiveNumber = 0
            foreach ($record in @($state.Effective)) {
                $effectiveNumber++
                $key = Get-NormalizedValidationKey $Area @($constraint) $record
                if ($seen.ContainsKey($key)) {
                    $detail = "Effective records duplicate ($([string]::Join(', ', @($constraint))))."
                    Add-LocalValidationIssue $Issues $state.Dataset.name $effectiveNumber 'duplicate_unique_constraint' $detail
                }
                else { $seen[$key] = $true }
            }
        }
    }
}

function Add-MetadataLockIssues([object[]]$States, $Issues) {
    $objectKey = @('tenant_code', 'system_code', 'connection_code', 'object_schema', 'object_name')
    $attributeKey = @($objectKey) + @('attribute_name')
    $lockedObjects = New-Object 'System.Collections.Generic.Dictionary[string,bool]' ([StringComparer]::Ordinal)
    $lockedAttributes = New-Object 'System.Collections.Generic.Dictionary[string,bool]' ([StringComparer]::Ordinal)
    foreach ($state in @($States)) {
        if (@('object', 'attribute') -cnotcontains [string]$state.RecordType) { continue }
        foreach ($record in @($state.Baseline)) {
            $locked = Get-Property $record 'is_locked'
            if ($locked -isnot [bool] -or -not $locked) { continue }
            if ($state.RecordType -ceq 'object') {
                $lockedObjects[(Get-NormalizedValidationKey 'metadata' $objectKey $record)] = $true
            }
            else {
                $lockedAttributes[(Get-NormalizedValidationKey 'metadata' $attributeKey $record)] = $true
            }
        }
    }
    foreach ($state in @($States)) {
        if (@('object', 'attribute') -cnotcontains [string]$state.RecordType) { continue }
        $recordNumber = 0
        foreach ($record in @($state.Pending)) {
            $recordNumber++
            if ($lockedObjects.ContainsKey((Get-NormalizedValidationKey 'metadata' $objectKey $record))) {
                Add-LocalValidationIssue $Issues $state.Dataset.name $recordNumber 'object_locked' 'Object is locked; neither it nor its Attributes can be changed.' 'object_name'
            }
            elseif ($state.RecordType -ceq 'attribute' -and
                $lockedAttributes.ContainsKey((Get-NormalizedValidationKey 'metadata' $attributeKey $record))) {
                Add-LocalValidationIssue $Issues $state.Dataset.name $recordNumber 'attribute_locked' 'Attribute is locked and cannot be changed.' 'attribute_name'
            }
        }
    }
}

function Add-MetadataUniqueIssues([object[]]$States, $Issues) {
    $groups = New-Object 'System.Collections.Generic.Dictionary[string,object]'
    $groupOrder = New-Object System.Collections.Generic.List[string]
    foreach ($state in @($States)) {
        $type = [string]$state.RecordType
        if (-not $groups.ContainsKey($type)) {
            $groups[$type] = New-Object System.Collections.ArrayList
            [void]$groupOrder.Add($type)
        }
        [void]$groups[$type].Add($state)
    }
    foreach ($type in $groupOrder) {
        $statesForType = $groups[$type]
        $constraints = New-Object 'System.Collections.Generic.Dictionary[string,bool]'
        $constraintOrder = New-Object System.Collections.ArrayList
        foreach ($state in @($statesForType)) {
            $schemaConstraints = Get-Property $state.Schema 'x-gds-unique-constraints'
            foreach ($constraint in @($schemaConstraints)) {
                if (Test-ValidationConstraint $constraint) {
                    $constraintKey = ConvertTo-StableJson @($constraint)
                    if (-not $constraints.ContainsKey($constraintKey)) {
                        $constraints[$constraintKey] = $true
                        [void]$constraintOrder.Add(@($constraint))
                    }
                }
            }
        }
        foreach ($constraint in @($constraintOrder)) {
            $seen = New-Object 'System.Collections.Generic.Dictionary[string,string]'
            foreach ($state in @($statesForType)) {
                $recordNumber = 0
                foreach ($record in @($state.Effective)) {
                    $recordNumber++
                    $key = Get-NormalizedValidationKey 'metadata' @($constraint) $record
                    if ($seen.ContainsKey($key) -and $seen[$key] -cne [string]$state.Dataset.name) {
                        $detail = "Effective zone datasets duplicate ($([string]::Join(', ', @($constraint))))."
                        Add-LocalValidationIssue $Issues $state.Dataset.name $recordNumber 'duplicate_unique_constraint' $detail
                    }
                    elseif (-not $seen.ContainsKey($key)) {
                        $seen[$key] = [string]$state.Dataset.name
                    }
                }
            }
        }
    }
}

function Add-DeclaredReferenceIssues(
    [string]$Area,
    [object[]]$States,
    $Issues,
    [object[]]$CandidateStates = $null
) {
    if ($null -eq $CandidateStates) { $CandidateStates = @($States) }
    $byType = New-Object 'System.Collections.Generic.Dictionary[string,object]'
    foreach ($state in @($CandidateStates)) {
        $type = [string]$state.RecordType
        if (-not $byType.ContainsKey($type)) {
            $byType[$type] = New-Object System.Collections.ArrayList
        }
        [void]$byType[$type].Add($state)
    }
    foreach ($state in @($States)) {
        $references = Get-Property $state.Schema 'x-gds-references'
        if ((Test-Property $state.Schema 'x-gds-references') -and $references -isnot [Array]) {
            Add-LocalValidationIssue $Issues $state.Dataset.name $null 'invalid_reference_contract' 'Reference metadata must be an array.'
            continue
        }
        if ($references -isnot [Array]) { continue }
        $recordNumber = 0
        foreach ($record in @($state.Effective)) {
            $recordNumber++
            if ($Area -cne 'model' -and (Get-Active $record) -eq $false) { continue }
            foreach ($reference in @($references)) {
                $targetType = [string](Get-Property $reference 'target_record_type')
                $columns = Get-Property $reference 'columns'
                $targetColumns = Get-Property $reference 'target_columns'
                if ($columns -isnot [Array] -or @($columns).Count -eq 0 -or
                    $targetColumns -isnot [Array] -or @($columns).Count -ne @($targetColumns).Count -or
                    -not $byType.ContainsKey($targetType)) {
                    Add-LocalValidationIssue $Issues $state.Dataset.name $recordNumber 'invalid_reference_contract'
                    continue
                }
                $values = New-Object System.Collections.ArrayList
                $nulls = 0
                foreach ($field in @($columns)) {
                    $value = Get-Property $record ([string]$field)
                    if ($null -eq $value) { $nulls++ }
                    [void]$values.Add($value)
                }
                $nullable = Get-Property $reference 'nullable'
                if ($nulls -eq $values.Count -and $nullable -is [bool] -and $nullable) { continue }
                if ($nulls -gt 0) {
                    Add-LocalValidationIssue $Issues $state.Dataset.name $recordNumber 'partial_null_reference'
                    continue
                }
                $found = $false
                foreach ($candidateState in @($byType[$targetType])) {
                    $candidateArea = if (Test-Property $candidateState 'Area') { [string]$candidateState.Area } else { $Area }
                    $wanted = New-Object System.Collections.ArrayList
                    for ($index = 0; $index -lt $values.Count; $index++) {
                        [void]$wanted.Add((Normalize-Value $candidateArea ([string](@($targetColumns)[$index])) $values[$index]))
                    }
                    $wantedKey = ConvertTo-StableJson @($wanted)
                    foreach ($candidate in @($candidateState.Effective)) {
                        if ($candidateArea -cne 'model' -and
                            -not ($Area -ceq 'model' -and @('object', 'attribute') -ccontains $targetType) -and
                            (Get-Active $candidate) -eq $false) { continue }
                        if ((Get-NormalizedValidationKey $candidateArea @($targetColumns) $candidate) -ceq $wantedKey) {
                            $found = $true
                            break
                        }
                    }
                    if ($found) { break }
                }
                if (-not $found) {
                    Add-LocalValidationIssue $Issues $state.Dataset.name $recordNumber 'broken_reference' $targetType
                }
            }
        }
    }
}

function Test-RetainedModelRecord($Previous, $Changed) {
    if ($null -eq $Previous) { return $false }
    if ((ConvertTo-StableJson $Previous) -ceq (ConvertTo-StableJson $Changed)) { return $true }
    $beforeFields = @(Get-PropertyNames $Previous)
    $afterFields = @(Get-PropertyNames $Changed)
    if ($beforeFields.Count -ne $afterFields.Count) { return $false }
    foreach ($field in $beforeFields) {
        if ($afterFields -cnotcontains $field) { return $false }
        $before = Get-Property $Previous $field
        $after = Get-Property $Changed $field
        if ((ConvertTo-StableJson $before) -ceq (ConvertTo-StableJson $after)) { continue }
        if (($field -ceq 'is_locked' -or $field.EndsWith('_is_locked', [StringComparison]::Ordinal)) -and
            $before -is [bool] -and $after -is [bool]) { continue }
        if ($field -ceq 'is_active' -and $before -is [bool] -and $before -and
            $after -is [bool] -and -not $after) { continue }
        if (($field -ceq 'status' -or $field.EndsWith('_status', [StringComparison]::Ordinal)) -and
            $before -is [string] -and $before -ceq 'active' -and $after -ceq 'inactive') { continue }
        if (@('supports', 'sources', 'submodels') -ccontains $field -and
            $before -is [Array] -and $after -is [Array] -and $before.Count -eq $after.Count) {
            for ($index = 0; $index -lt $before.Count; $index++) {
                if (-not (Test-RetainedModelRecord $before[$index] $after[$index])) { return $false }
            }
            continue
        }
        return $false
    }
    return $true
}

function Add-ModelPhysicalScopeIssues([object[]]$States, [object[]]$ReferenceStates, [string]$TenantCode, $Issues) {
    $byType = New-Object 'System.Collections.Generic.Dictionary[string,object]' ([StringComparer]::Ordinal)
    foreach ($state in $States) { $byType[[string]$state.RecordType] = $state }
    if (-not $byType.ContainsKey('model_details') -or -not $byType.ContainsKey('model_input_scope')) { return }
    $sets = @{}
    foreach ($name in @('objects', 'attributes', 'inputs', 'inputAttributes', 'silver', 'silverAttributes',
        'gold', 'goldAttributes', 'activeInputs', 'activeInputAttributes', 'dimensional', 'dimensionalAttributes')) {
        $sets[$name] = New-Object 'System.Collections.Generic.HashSet[string]' ([StringComparer]::Ordinal)
    }
    $objectFields = @('tenant_code', 'system_code', 'connection_code', 'object_schema', 'object_name')
    $attributeFields = @($objectFields) + @('attribute_name')
    $objects = New-Object 'System.Collections.Generic.Dictionary[string,object]' ([StringComparer]::Ordinal)
    foreach ($state in $ReferenceStates) {
        if ([string]$state.Area -cne 'metadata' -or [string]$state.RecordType -cne 'object') { continue }
        foreach ($record in @($state.Effective)) {
            if ((Normalize-Value 'model' 'tenant_code' (Get-Property $record 'source_tenant_code')) -cne
                (Normalize-Value 'model' 'tenant_code' $TenantCode) -and
                @('source', 'bronze') -cnotcontains (Normalize-Value 'model' 'zone_code' (Get-Property $record 'zone_code'))) { continue }
            $key = Get-NormalizedValidationKey 'model' $objectFields $record
            $objects[$key] = $record
            [void]$sets.objects.Add($key)
            if ((Get-Active $record) -eq $false) { continue }
            $zone = Normalize-Value 'model' 'zone_code' (Get-Property $record 'zone_code')
            if (@('source', 'bronze') -ccontains $zone) { [void]$sets.inputs.Add($key) }
            if ($zone -ceq 'silver') { [void]$sets.silver.Add($key) }
            if ($zone -ceq 'gold') { [void]$sets.gold.Add($key) }
        }
    }
    foreach ($state in $ReferenceStates) {
        if ([string]$state.Area -cne 'metadata' -or [string]$state.RecordType -cne 'attribute') { continue }
        foreach ($record in @($state.Effective)) {
            $parent = Get-NormalizedValidationKey 'model' $objectFields $record
            if (-not $objects.ContainsKey($parent)) { continue }
            $key = Get-NormalizedValidationKey 'model' $attributeFields $record
            [void]$sets.attributes.Add($key)
            if ((Get-Active $record) -eq $false -or (Get-Active $objects[$parent]) -eq $false) { continue }
            foreach ($pair in @(@('inputs', 'inputAttributes'), @('silver', 'silverAttributes'), @('gold', 'goldAttributes'))) {
                if ($sets[$pair[0]].Contains($parent)) { [void]$sets[$pair[1]].Add($key) }
            }
        }
    }
    $requirePhysical = {
        param($State, $Record, [string]$Field, [string]$Key, $Eligible, [string]$Message)
        if (-not $Eligible.Contains($Key)) {
            Add-LocalValidationIssue $Issues $State.Dataset.name $null 'model_input_reference_invalid' $Message $Field
        }
    }
    foreach ($record in @($byType['model_input_scope'].Effective)) {
        $key = Get-NormalizedValidationKey 'model' $objectFields $record
        $state = $byType['model_input_scope']
        $retained = $state.RetainedKeys.Contains((Get-NormalizedValidationKey 'model' @($state.Dataset.canonical_key) $record))
        $eligible = if ($retained) { ,$sets.objects } else { ,$sets.inputs }
        & $requirePhysical $state $record 'object_name' $key $eligible 'Model Input Scope requires an available Source or Bronze Object.'
        if ((Get-Property $record 'is_active') -eq $true -and $sets.inputs.Contains($key)) { [void]$sets.activeInputs.Add($key) }
    }
    foreach ($key in $sets.inputAttributes) {
        $parts = ConvertFrom-GdsJson $key
        if ($sets.activeInputs.Contains((ConvertTo-StableJson @($parts[0..4])))) { [void]$sets.activeInputAttributes.Add($key) }
    }
    $objectBindings = New-Object 'System.Collections.Generic.Dictionary[string,object]' ([StringComparer]::Ordinal)
    $attributeBindings = New-Object 'System.Collections.Generic.Dictionary[string,object]' ([StringComparer]::Ordinal)
    $allAttributeBindings = New-Object 'System.Collections.Generic.Dictionary[string,object]' ([StringComparer]::Ordinal)
    $retainedBindings = New-Object 'System.Collections.Generic.HashSet[string]' ([StringComparer]::Ordinal)
    $retainedAttributes = New-Object 'System.Collections.Generic.HashSet[string]' ([StringComparer]::Ordinal)
    $entityFields = @('modeled_entity_type', 'modeled_entity_name')
    $modeledAttributeFields = @($entityFields) + @('modeled_attribute_name')
    if ($byType.ContainsKey('model_object_binding')) {
        $state = $byType['model_object_binding']
        foreach ($record in @($state.Effective)) {
            $entity = Get-NormalizedValidationKey 'model' $entityFields $record
            $key = Get-NormalizedValidationKey 'model' $objectFields $record
            $retained = $state.RetainedKeys.Contains((Get-NormalizedValidationKey 'model' @($state.Dataset.canonical_key) $record))
            if ($retained) { [void]$retainedBindings.Add($entity) }
            $eligible = if ($retained) { ,$sets.objects } elseif ($record.modeled_entity_type -ceq 'logical_entity') { ,$sets.silver } else { ,$sets.gold }
            & $requirePhysical $state $record 'object_name' $key $eligible 'Bound target Object is not eligible for its modeled layer.'
            $objectBindings[$entity] = @{ Record = $record; Key = $key }
        }
    }
    if ($byType.ContainsKey('model_attribute_binding')) {
        $state = $byType['model_attribute_binding']
        foreach ($record in @($state.Effective)) {
            $entity = Get-NormalizedValidationKey 'model' $entityFields $record
            if (-not $objectBindings.ContainsKey($entity)) { continue }
            $parent = $objectBindings[$entity]
            $parts = ConvertFrom-GdsJson $parent.Key
            $key = ConvertTo-StableJson (@($parts) + @((Normalize-Value 'model' 'attribute_name' $record.attribute_name)))
            $retained = $retainedBindings.Contains($entity) -and $state.RetainedKeys.Contains((Get-NormalizedValidationKey 'model' @($state.Dataset.canonical_key) $record))
            $eligible = if ($retained) { ,$sets.attributes } elseif ($record.modeled_entity_type -ceq 'logical_entity') { ,$sets.silverAttributes } else { ,$sets.goldAttributes }
            & $requirePhysical $state $record 'attribute_name' $key $eligible 'Bound target Attribute is not eligible for its modeled layer.'
            $allAttributeBindings[(Get-NormalizedValidationKey 'model' $modeledAttributeFields $record)] = @{ Record = $record; Key = $key; Parent = $entity }
            if ((Get-Property $record 'model_attribute_binding_status') -ceq 'active' -and
                (Get-Property $parent.Record 'model_object_binding_status') -ceq 'active') {
                $attributeBindings[(Get-NormalizedValidationKey 'model' $modeledAttributeFields $record)] = @{ Record = $record; Key = $key; Parent = $entity }
                if ($retained -and $sets.attributes.Contains($key)) { [void]$retainedAttributes.Add($key) }
            }
        }
    }
    foreach ($state in $States) {
        $type = [string]$state.RecordType
        foreach ($record in @($state.Effective)) {
            $retained = $state.RetainedKeys.Contains((Get-NormalizedValidationKey 'model' @($state.Dataset.canonical_key) $record))
            if ($type -ceq 'profiling_profile') {
                $eligible = if ($retained) { ,$sets.attributes } else { ,$sets.activeInputAttributes }
                & $requirePhysical $state $record 'attribute_name' (Get-NormalizedValidationKey 'model' $attributeFields $record) $eligible 'Profile Attribute is not in active Model Input Scope.'
            }
            elseif ($type -ceq 'analysis_result') {
                $eligible = if ($retained) { ,$sets.attributes } else { ,$sets.activeInputAttributes }
                foreach ($prefix in @('from', 'to')) {
                    $fields = @($attributeFields | ForEach-Object { $prefix + '_' + $_ })
                    & $requirePhysical $state $record ($prefix + '_attribute_name') (Get-NormalizedValidationKey 'model' $fields $record) $eligible 'Analysis Attribute is not in active Model Input Scope.'
                }
            }
            if (@('mapping_object', 'mapping_attribute', 'generated_code', 'generated_code_source_system') -ccontains $type) {
                $entity = Get-NormalizedValidationKey 'model' $entityFields $record
                $binding = if ($objectBindings.ContainsKey($entity)) { $objectBindings[$entity] } else { $null }
                $attributeKey = Get-NormalizedValidationKey 'model' $modeledAttributeFields $record
                if ($type -ceq 'mapping_attribute') { $binding = if ($allAttributeBindings.ContainsKey($attributeKey)) { $allAttributeBindings[$attributeKey] } else { $null } }
                if ($null -ne $binding) {
                    $eligible = if ($type -ceq 'mapping_attribute') {
                        if ($record.modeled_entity_type -ceq 'logical_entity') { ,$sets.silverAttributes } else { ,$sets.goldAttributes }
                    } elseif ($record.modeled_entity_type -ceq 'logical_entity') { ,$sets.silver } else { ,$sets.gold }
                    if (-not $retained) {
                        $bindingField = if ($type -ceq 'mapping_attribute') { 'model_attribute_binding' } else { 'model_object_binding' }
                        $targetLabel = if ($type -ceq 'mapping_attribute') { 'Attribute' } else { 'Object' }
                        & $requirePhysical $state $record $bindingField $binding.Key $eligible "New or changed authoring requires an eligible active physical target $targetLabel."
                    }
                    if ($record.modeled_entity_type -ceq 'logical_entity' -and $eligible.Contains($binding.Key)) {
                        if ($type -ceq 'mapping_object' -and $record.object_mapping_status -ceq 'active' -and
                            $binding.Record.model_object_binding_status -ceq 'active') { [void]$sets.dimensional.Add($binding.Key) }
                        if ($type -ceq 'mapping_attribute' -and $record.attribute_mapping_status -ceq 'active' -and
                            $attributeBindings.ContainsKey($attributeKey)) { [void]$sets.dimensionalAttributes.Add($binding.Key) }
                    }
                }
            }
        }
    }
    foreach ($state in $States) {
        $type = [string]$state.RecordType
        if (@('conceptual_object', 'conceptual_relationship', 'logical_entity', 'logical_attribute', 'dimensional_entity', 'dimensional_attribute') -cnotcontains $type) { continue }
        foreach ($record in @($state.Effective)) {
            $retained = $state.RetainedKeys.Contains((Get-NormalizedValidationKey 'model' @($state.Dataset.canonical_key) $record))
            $field = if ($type.StartsWith('conceptual_', [StringComparison]::Ordinal)) { 'supports' } else { 'sources' }
            $sources = Get-Property $record $field
            foreach ($source in @($sources)) {
                $sourceType = Get-Property $source 'support_source_type'
                if (@('object', 'attribute') -cnotcontains $sourceType) { continue }
                $isAttribute = $sourceType -ceq 'attribute'
                $targetField = if ($isAttribute) { 'source_attribute' } else { 'source_object' }
                $fields = if ($isAttribute) { $attributeFields } else { $objectFields }
                $eligible = if ($retained) { if ($isAttribute) { ,$sets.attributes } else { ,$sets.objects } }
                    elseif ($type.StartsWith('dimensional_', [StringComparison]::Ordinal)) { if ($isAttribute) { ,$sets.dimensionalAttributes } else { ,$sets.dimensional } }
                    else { if ($isAttribute) { ,$sets.activeInputAttributes } else { ,$sets.activeInputs } }
                $key = Get-NormalizedValidationKey 'model' $fields (Get-Property $source $targetField)
                & $requirePhysical $state $record $targetField $key $eligible 'Physical source is not available for this modeling layer.'
            }
        }
    }
    foreach ($entity in $objectBindings.Keys) {
        $parent = $objectBindings[$entity]
        if ($parent.Record.model_object_binding_status -cne 'active') { continue }
        $eligible = if ($parent.Record.modeled_entity_type -ceq 'logical_entity') { ,$sets.silverAttributes } else { ,$sets.goldAttributes }
        $expected = New-Object 'System.Collections.Generic.HashSet[string]' ([StringComparer]::Ordinal)
        foreach ($key in @($eligible) + @($retainedAttributes)) {
            $parts = ConvertFrom-GdsJson $key
            if ((ConvertTo-StableJson @($parts[0..4])) -ceq $parent.Key) { [void]$expected.Add($key) }
        }
        $bound = New-Object 'System.Collections.Generic.HashSet[string]' ([StringComparer]::Ordinal)
        foreach ($binding in $attributeBindings.Values) { if ($binding.Parent -ceq $entity) { [void]$bound.Add($binding.Key) } }
        if (-not $expected.SetEquals($bound)) {
            Add-LocalValidationIssue $Issues 'model_attribute_binding' $null 'binding_coverage_missing' 'An active Object Binding requires one active Binding for every active physical Attribute.' 'attribute_name'
        }
    }
}

function Add-ModelValidationIssues([object[]]$States, $Issues, [object[]]$ReferenceStates, [string]$TenantCode) {
    foreach ($state in $States) {
        $baseline = New-Object 'System.Collections.Generic.Dictionary[string,object]' ([StringComparer]::Ordinal)
        foreach ($record in @($state.Baseline)) { $baseline[(Get-NormalizedValidationKey 'model' @($state.Dataset.canonical_key) $record)] = $record }
        $retained = New-Object 'System.Collections.Generic.HashSet[string]' ([StringComparer]::Ordinal)
        foreach ($record in @($state.Effective)) {
            $key = Get-NormalizedValidationKey 'model' @($state.Dataset.canonical_key) $record
            if ($baseline.ContainsKey($key) -and (Test-RetainedModelRecord $baseline[$key] $record)) { [void]$retained.Add($key) }
        }
        $state | Add-Member -NotePropertyName RetainedKeys -NotePropertyValue $retained
    }
    Add-ModelPhysicalScopeIssues $States $ReferenceStates $TenantCode $Issues
    $activeKeys = New-Object 'System.Collections.Generic.Dictionary[string,object]' ([StringComparer]::Ordinal)
    foreach ($type in @('conceptual_object', 'logical_entity', 'logical_attribute', 'dimensional_entity', 'dimensional_attribute')) {
        $activeKeys[$type] = New-Object 'System.Collections.Generic.HashSet[string]' ([StringComparer]::Ordinal)
    }
    foreach ($state in @($States)) {
        $type = [string]$state.RecordType
        if (-not $activeKeys.ContainsKey($type)) { continue }
        $keyFields = @($type + '_name')
        if ($type.EndsWith('_attribute', [StringComparison]::Ordinal)) {
            $layer = $type.Substring(0, $type.Length - '_attribute'.Length)
            $keyFields = @(($layer + '_entity_name'), ($type + '_name'))
        }
        foreach ($record in @($state.Effective)) {
            if ([string](Get-Property $record ($type + '_status')) -ceq 'active') {
                [void]$activeKeys[$type].Add((Get-NormalizedValidationKey 'model' $keyFields $record))
            }
        }
    }
    foreach ($state in @($States)) {
        $type = [string]$state.RecordType
        $recordNumber = 0
        foreach ($record in @($state.Effective)) {
            $recordNumber++
            if ([string](Get-Property $record ($type + '_status')) -cne 'active') { continue }
            if ($type -ceq 'conceptual_relationship') {
                $invalidEndpoint = $false
                foreach ($prefix in @('from', 'to')) {
                    $key = Get-NormalizedValidationKey 'model' @($prefix + '_conceptual_object_name') $record
                    if (-not $activeKeys['conceptual_object'].Contains($key)) { $invalidEndpoint = $true }
                }
                if ($invalidEndpoint) {
                    Add-LocalValidationIssue $Issues $state.Dataset.name $recordNumber 'active_dependency_invalid' 'Active Conceptual Relationship requires active endpoint Objects.' 'conceptual_object_name'
                }
            }
            foreach ($layer in @('logical', 'dimensional')) {
                $label = if ($layer -ceq 'logical') { 'Logical' } else { 'Dimensional' }
                if ($type -ceq ($layer + '_attribute')) {
                    $parent = Get-NormalizedValidationKey 'model' @($layer + '_entity_name') $record
                    if (-not $activeKeys[$layer + '_entity'].Contains($parent)) {
                        Add-LocalValidationIssue $Issues $state.Dataset.name $recordNumber 'active_dependency_invalid' "Active $label Attribute requires an active parent Entity." ($layer + '_entity_name')
                    }
                }
                elseif ($type -ceq ($layer + '_relationship')) {
                    $invalidEndpoint = $false
                    foreach ($prefix in @('from', 'to')) {
                        $entityField = $prefix + '_' + $layer + '_entity_name'
                        $attributeField = $prefix + '_' + $layer + '_attribute_name'
                        $parent = Get-NormalizedValidationKey 'model' @($entityField) $record
                        $attribute = Get-NormalizedValidationKey 'model' @($entityField, $attributeField) $record
                        if (-not $activeKeys[$layer + '_entity'].Contains($parent) -or
                            -not $activeKeys[$layer + '_attribute'].Contains($attribute)) { $invalidEndpoint = $true }
                    }
                    if ($invalidEndpoint) {
                        Add-LocalValidationIssue $Issues $state.Dataset.name $recordNumber 'active_dependency_invalid' "Active $label Relationship requires active endpoint Attributes and Entities." ($layer + '_attribute_name')
                    }
                }
            }
        }
        $canonicalKey = @(Get-Property $state.Dataset 'canonical_key')
        if ($canonicalKey.Count -eq 0) { continue }
        $baseline = New-Object 'System.Collections.Generic.Dictionary[string,object]' ([StringComparer]::Ordinal)
        foreach ($record in @($state.Baseline)) {
            $baseline[(Get-NormalizedValidationKey 'model' $canonicalKey $record)] = $record
        }
        $recordNumber = 0
        foreach ($record in @($state.Pending)) {
            $recordNumber++
            $key = Get-NormalizedValidationKey 'model' $canonicalKey $record
            if (-not $baseline.ContainsKey($key)) { continue }
            $existing = $baseline[$key]
            $locked = $false
            foreach ($field in @(Get-PropertyNames $existing)) {
                $value = Get-Property $existing $field
                if (($field -ceq 'is_locked' -or
                    $field.EndsWith('_is_locked', [StringComparison]::Ordinal)) -and
                    $value -is [bool] -and $value) {
                    $locked = $true
                    break
                }
            }
            if ($locked -and
                (ConvertTo-StableJson $existing) -cne (ConvertTo-StableJson $record)) {
                Add-LocalValidationIssue $Issues $state.Dataset.name $recordNumber 'locked_record' 'Locked records cannot be changed locally.'
            }
        }
    }
    Add-DeclaredReferenceIssues 'model' @($States) $Issues @($ReferenceStates)
}

function Write-Pending($Context, $Dataset, [object[]]$Records) {
    $byKey = New-Object 'System.Collections.Generic.Dictionary[string,object]'
    $keys = New-Object 'System.Collections.Generic.List[string]'
    foreach ($record in @($Records)) {
        $key = Get-CanonicalKey $Context.Area $Dataset $record
        if ($byKey.ContainsKey($key)) { Fail "$($Dataset.name) pending records contain a duplicate canonical key." }
        $byKey[$key] = $record
        [void]$keys.Add($key)
    }
    $keys.Sort([StringComparer]::Ordinal)
    $sorted = New-Object System.Collections.ArrayList
    foreach ($key in $keys) { [void]$sorted.Add($byKey[$key]) }
    Write-JsonAtomic (Join-Path $Context.ChangeDirectory ([string]$Dataset.name + '.json')) @($sorted)
}

function Copy-Records([hashtable]$Options) {
    $context = Get-ChangeContext $Options
    Assert-Digest $Options $context
    $selectionOptions = @{}
    foreach ($key in $Options.Keys) { $selectionOptions[$key] = $Options[$key] }
    if (-not $selectionOptions.ContainsKey('limit')) { $selectionOptions['limit'] = '200' }
    $selection = Select-Records $selectionOptions $context
    if ($selection.Truncated) { Fail 'Selection exceeds 200 records; narrow --where.' }
    $dataset = $selection.Dataset
    $schema = Get-EditableSchema $context $dataset
    $pending = Read-Pending $context
    $records = New-Object System.Collections.ArrayList
    if ($pending.ContainsKey([string]$dataset.name)) {
        foreach ($item in @($pending[[string]$dataset.name])) { [void]$records.Add($item) }
    }
    $index = @{}
    for ($i = 0; $i -lt $records.Count; $i++) { $index[(Get-CanonicalKey $context.Area $dataset $records[$i])] = $i }
    foreach ($record in @($selection.Records)) {
        $issues = @(Get-SchemaIssues $record $schema)
        if ($issues.Count -gt 0) { Fail "$($dataset.name) Snapshot record fails its schema: $($issues[0])" }
        $key = Get-CanonicalKey $context.Area $dataset $record
        if (-not $index.ContainsKey($key)) { $index[$key] = $records.Count; [void]$records.Add($record) }
    }
    Write-Pending $context $dataset @($records)
    Mark-Review $context
    return [ordered]@{ dataset = [string]$dataset.name; count = $records.Count; digest = Get-WorkspaceDigest $context }
}

function Upsert-Record([hashtable]$Options) {
    $context = Get-ChangeContext $Options
    Assert-Digest $Options $context
    $name = Require-Option $Options 'dataset'
    if (-not $context.ByName.ContainsKey($name)) { Fail "Unknown Snapshot dataset: $name." }
    $dataset = $context.ByName[$name]
    $schema = Get-EditableSchema $context $dataset
    $record = Parse-Object $Options 'record'
    $issues = @(Get-SchemaIssues $record $schema)
    if ($issues.Count -gt 0) { Fail "$name record is invalid: $($issues[0])" }
    $pending = Read-Pending $context
    $records = New-Object System.Collections.ArrayList
    if ($pending.ContainsKey($name)) {
        foreach ($item in @($pending[$name])) { [void]$records.Add($item) }
    }
    $key = Get-CanonicalKey $context.Area $dataset $record
    $found = -1
    for ($i = 0; $i -lt $records.Count; $i++) { if ((Get-CanonicalKey $context.Area $dataset $records[$i]) -eq $key) { $found = $i; break } }
    if ($found -lt 0) { [void]$records.Add($record) } else { $records[$found] = $record }
    $baseline = $null
    foreach ($item in @(Read-SnapshotRecords $context $dataset)) { if ((Get-CanonicalKey $context.Area $dataset $item) -eq $key) { $baseline = $item; break } }
    $action = if ($null -eq $baseline) { 'added' } elseif ((ConvertTo-StableJson $baseline) -ceq (ConvertTo-StableJson $record)) { 'unchanged' } else { 'changed' }
    Write-Pending $context $dataset @($records)
    Mark-Review $context
    return [ordered]@{ dataset = $name; action = $action; count = $records.Count; digest = Get-WorkspaceDigest $context }
}

function Upsert-RecordsBatch([hashtable]$Options) {
    $context = Get-ChangeContext $Options
    Assert-Digest $Options $context
    $changes = Parse-Object $Options 'changes'
    $names = New-Object 'System.Collections.Generic.List[string]'
    foreach ($name in @(Get-PropertyNames $changes)) { [void]$names.Add($name) }
    $names.Sort([StringComparer]::Ordinal)
    if ($names.Count -eq 0) { Fail '--changes must contain at least one dataset.' }

    $pending = Read-Pending $context
    $prepared = New-Object System.Collections.ArrayList
    $total = 0
    foreach ($name in $names) {
        if (-not $context.ByName.ContainsKey($name)) { Fail "Unknown Snapshot dataset: $name." }
        $dataset = $context.ByName[$name]
        $schema = Get-EditableSchema $context $dataset
        $incoming = Get-Property $changes $name
        if ($incoming -isnot [Array] -or @($incoming).Count -eq 0) {
            Fail "$name batch must be a non-empty JSON array."
        }
        $total += @($incoming).Count
        if ($total -gt 200) { Fail '--changes may contain at most 200 records.' }

        $records = New-Object System.Collections.ArrayList
        if ($pending.ContainsKey($name)) {
            foreach ($record in @($pending[$name])) { [void]$records.Add($record) }
        }
        $recordIndex = New-Object 'System.Collections.Generic.Dictionary[string,int]'
        for ($index = 0; $index -lt $records.Count; $index++) {
            $recordIndex[(Get-CanonicalKey $context.Area $dataset $records[$index])] = $index
        }
        $batchKeys = New-Object 'System.Collections.Generic.Dictionary[string,bool]'
        $batchIndex = 0
        foreach ($record in @($incoming)) {
            $batchIndex++
            if ((Get-JsonSchemaType $record) -cne 'object') {
                Fail "$name batch record $batchIndex must be a JSON object."
            }
            $issues = @(Get-SchemaIssues $record $schema)
            if ($issues.Count -gt 0) {
                Fail "$name batch record $batchIndex is invalid: $($issues[0])"
            }
            $key = Get-CanonicalKey $context.Area $dataset $record
            if ($batchKeys.ContainsKey($key)) { Fail "$name batch contains a duplicate canonical key." }
            $batchKeys[$key] = $true
            if ($recordIndex.ContainsKey($key)) { $records[$recordIndex[$key]] = $record }
            else {
                $recordIndex[$key] = $records.Count
                [void]$records.Add($record)
            }
        }
        [void]$prepared.Add([pscustomobject]@{
            Dataset = $dataset
            InputCount = @($incoming).Count
            Records = @($records)
        })
    }

    foreach ($item in @($prepared)) { Write-Pending $context $item.Dataset @($item.Records) }
    Mark-Review $context
    $summary = New-Object System.Collections.ArrayList
    foreach ($item in @($prepared)) {
        [void]$summary.Add(@(
            [string]$item.Dataset.name,
            [int]$item.InputCount,
            @($item.Records).Count
        ))
    }
    return [ordered]@{
        datasets = @($summary)
        records = $total
        digest = Get-WorkspaceDigest $context
    }
}

function Discard-Record([hashtable]$Options) {
    $context = Get-ChangeContext $Options
    Assert-Digest $Options $context
    $name = Require-Option $Options 'dataset'
    if (-not $context.ByName.ContainsKey($name)) { Fail "Unknown Snapshot dataset: $name." }
    $dataset = $context.ByName[$name]
    [void](Get-EditableSchema $context $dataset)
    $keyRecord = Parse-Object $Options 'key'
    $key = Get-CanonicalKey $context.Area $dataset $keyRecord
    $pending = Read-Pending $context
    $records = New-Object System.Collections.ArrayList
    foreach ($record in @($pending[$name])) { if ((Get-CanonicalKey $context.Area $dataset $record) -ne $key) { [void]$records.Add($record) } }
    Write-Pending $context $dataset @($records)
    Mark-Review $context
    return [ordered]@{ dataset = $name; count = $records.Count; digest = Get-WorkspaceDigest $context }
}

function Get-Active($Record) {
    $isActive = Get-Property $Record 'is_active'
    if ($isActive -is [bool]) { return $isActive }
    $status = Get-Property $Record 'status'
    if ($status -is [string]) { return $status -ceq 'active' }
    foreach ($name in @(Get-PropertyNames $Record)) {
        $value = Get-Property $Record $name
        if ($name.EndsWith('_status', [StringComparison]::Ordinal) -and $value -is [string]) {
            return [string]$value -ceq 'active'
        }
    }
    return $null
}

function Review-Changes([hashtable]$Options) {
    $context = Get-ChangeContext $Options
    $pending = Read-Pending $context
    $counts = [ordered]@{ added = 0; changed = 0; reactivated = 0; deactivated = 0; unchanged = 0; total = 0 }
    $actions = New-Object System.Collections.ArrayList
    foreach ($name in @($pending.Keys | Sort-Object)) {
        $dataset = $context.ByName[$name]
        $baseline = @{}
        foreach ($record in @(Read-SnapshotRecords $context $dataset)) { $baseline[(Get-CanonicalKey $context.Area $dataset $record)] = $record }
        foreach ($record in @($pending[$name])) {
            $key = Get-CanonicalKey $context.Area $dataset $record
            $original = if ($baseline.ContainsKey($key)) { $baseline[$key] } else { $null }
            if ($null -eq $original) { $action = 'added' }
            elseif ((ConvertTo-StableJson $original) -ceq (ConvertTo-StableJson $record)) { $action = 'unchanged' }
            elseif ((Get-Active $original) -eq $true -and (Get-Active $record) -eq $false) { $action = 'deactivated' }
            elseif ((Get-Active $original) -eq $false -and (Get-Active $record) -eq $true) { $action = 'reactivated' }
            else { $action = 'changed' }
            $counts[$action] = [int]$counts[$action] + 1
            $counts.total = [int]$counts.total + 1
            if ($actions.Count -lt 200) {
                [void]$actions.Add(@($name, (Get-CanonicalKeyObject $context.Area $dataset $record), $action))
            }
        }
    }
    return [ordered]@{ counts = $counts; actions = @($actions); truncated = $counts.total -gt $actions.Count; digest = Get-WorkspaceDigest $context }
}

function Test-AppliedRecordEqual($Local, $Server, $Schema, $Root = $null, [string]$RecordType = '', [string]$Collection = '') {
    # Retirement only: accepted bytes and Stage fingerprints must stay exact.
    if ((ConvertTo-StableJson $Local) -ceq (ConvertTo-StableJson $Server)) { return $true }
    if ($null -eq $Schema) { return $false }
    if ($null -eq $Root) { $Root = $Schema }
    $reference = Get-Property $Schema '$ref'
    if ($reference -is [string]) {
        if (-not $reference.StartsWith('#/$defs/', [StringComparison]::Ordinal)) { return $false }
        $target = Get-Property (Get-Property $Root '$defs') $reference.Substring(8)
        return Test-AppliedRecordEqual $Local $Server $target $Root $RecordType $Collection
    }
    $alternatives = Get-Property $Schema 'anyOf'
    if ($null -eq $alternatives) { $alternatives = Get-Property $Schema 'oneOf' }
    if ($alternatives -is [Array]) {
        $hasNumber = $false
        $hasNumericString = $false
        foreach ($part in $alternatives) {
            if ((Get-Property $part 'type') -ceq 'number') { $hasNumber = $true }
            if ((Get-Property $part 'type') -ceq 'string' -and (Get-Property $part 'pattern') -is [string]) {
                $hasNumericString = $true
            }
        }
        if ($hasNumber -and $hasNumericString) {
            $values = New-Object Collections.Generic.List[string]
            foreach ($value in @($Local, $Server)) {
                if (($value -isnot [string] -and -not (Test-JsonNumber $value)) -or
                    @(Get-SchemaIssues -Value $value -Schema $Schema -Root $Root).Count -gt 0) { return $false }
                $text = if ($value -is [string]) { $value } else { ConvertTo-StableJson $value }
                $match = [regex]::Match($text, '^([+-]?)(\d+)(?:\.(\d*))?(?:[eE]([+-]?\d+))?$')
                if (-not $match.Success) { return $false }
                [long]$exponent = 0
                if ($match.Groups[4].Success -and -not [long]::TryParse($match.Groups[4].Value, [ref]$exponent)) { return $false }
                $exponent -= $match.Groups[3].Value.Length
                if ($exponent -lt -9007199254740991 -or $exponent -gt 9007199254740991) { return $false }
                $digits = ($match.Groups[2].Value + $match.Groups[3].Value).TrimStart([char]'0')
                if ($digits.Length -eq 0) { $values.Add('0'); continue }
                $trimmed = $digits.TrimEnd([char]'0')
                $exponent += $digits.Length - $trimmed.Length
                $sign = if ($match.Groups[1].Value -ceq '-') { '-' } else { '' }
                $values.Add($sign + $trimmed + 'e' + $exponent.ToString([Globalization.CultureInfo]::InvariantCulture))
            }
            return $values[0] -ceq $values[1]
        }
        foreach ($part in $alternatives) {
            if (@(Get-SchemaIssues -Value $Local -Schema $part -Root $Root).Count -eq 0 -and
                @(Get-SchemaIssues -Value $Server -Schema $part -Root $Root).Count -eq 0 -and
                (Test-AppliedRecordEqual $Local $Server $part $Root $RecordType $Collection)) { return $true }
        }
        return $false
    }
    if ($Local -is [Array] -or $Server -is [Array]) {
        if ($Local -isnot [Array] -or $Server -isnot [Array] -or $Local.Count -ne $Server.Count) { return $false }
        if ($Collection) {
            # SQL orders owned collections by database ID/name; explicit source_order stays compared.
            function Get-AppliedCollectionIdentity($Item) {
                if ($null -eq $Item -or $Item -is [Array] -or $Item -is [string] -or $Item -is [ValueType]) { return $null }
                if ($Collection -ceq 'submodels') {
                    $name = Get-Property $Item 'submodel_name'
                    if ($name -isnot [string]) { return $null }
                    return ConvertTo-StableJson @('submodel', $name)
                }
                $kind = Get-Property $Item 'support_source_type'
                $field = switch -CaseSensitive ($kind) {
                    'object' { 'source_object' }; 'attribute' { 'source_attribute' }; 'assertion' { 'assertion_record' }
                    default { $null }
                }
                if ($null -eq $field) { return $null }
                $reference = Get-Property $Item $field
                if ($null -eq $reference -or $reference -is [Array] -or $reference -is [string] -or $reference -is [ValueType]) { return $null }
                return ConvertTo-StableJson @($kind, $reference)
            }
            $candidates = New-Object 'Collections.Generic.Dictionary[string,object]' ([StringComparer]::Ordinal)
            foreach ($item in $Server) {
                $key = Get-AppliedCollectionIdentity $item
                if ($null -eq $key -or $candidates.ContainsKey($key)) { return $false }
                $candidates[$key] = $item
            }
            foreach ($item in $Local) {
                $key = Get-AppliedCollectionIdentity $item
                if ($null -eq $key -or -not $candidates.ContainsKey($key) -or
                    -not (Test-AppliedRecordEqual $item $candidates[$key] (Get-Property $Schema 'items') $Root $RecordType)) { return $false }
                [void]$candidates.Remove($key)
            }
            return $candidates.Count -eq 0
        }
        for ($index = 0; $index -lt $Local.Count; $index++) {
            if (-not (Test-AppliedRecordEqual $Local[$index] $Server[$index] (Get-Property $Schema 'items') $Root $RecordType)) { return $false }
        }
        return $true
    }
    if ($null -eq $Local -or $null -eq $Server -or $Local -is [string] -or $Server -is [string] -or
        $Local -is [ValueType] -or $Server -is [ValueType]) { return $false }
    $fields = New-Object 'System.Collections.Generic.HashSet[string]' ([StringComparer]::Ordinal)
    foreach ($field in @((Get-PropertyNames $Local)) + @((Get-PropertyNames $Server))) { [void]$fields.Add($field) }
    foreach ($field in $fields) {
        $child = Get-Property (Get-Property $Schema 'properties') $field
        $hasLocal = Test-Property $Local $field
        $hasServer = Test-Property $Server $field
        if ((-not $hasLocal -or -not $hasServer) -and
            ($null -eq $child -or -not (Test-Property $child 'default') -or
             (Get-Property $Schema 'required') -ccontains $field)) { return $false }
        $left = if ($hasLocal) { Get-Property $Local $field } else { Get-Property $child 'default' }
        $right = if ($hasServer) { Get-Property $Server $field } else { Get-Property $child 'default' }
        $ownedCollection = if ([object]::ReferenceEquals($Schema, $Root) -and (
            ($field -ceq 'supports' -and @('conceptual_object', 'conceptual_relationship') -ccontains $RecordType) -or
            ($field -ceq 'sources' -and @('logical_entity', 'logical_attribute', 'dimensional_entity', 'dimensional_attribute') -ccontains $RecordType) -or
            ($field -ceq 'submodels' -and @('logical_entity', 'dimensional_entity') -ccontains $RecordType))) { $field } else { '' }
        if (-not (Test-AppliedRecordEqual $left $right $child $Root $RecordType $ownedCollection)) { return $false }
    }
    return $true
}

function ConvertTo-StableJson($Value) {
    return ConvertTo-GdsJson $Value $true
}

function Get-JsonByteCount($Value) {
    return $script:Utf8NoBom.GetByteCount((ConvertTo-StableJson $Value))
}

function Get-ByteDigest([byte[]]$Bytes) {
    $sha = [Security.Cryptography.SHA256]::Create()
    try { return ([BitConverter]::ToString($sha.ComputeHash($Bytes))).Replace('-', '').ToLowerInvariant() }
    finally { $sha.Dispose() }
}

function ConvertTo-DbmlLine($Value) {
    if ($null -eq $Value) { return '' }
    if ($Value -is [Array]) {
        $parts = @($Value | ForEach-Object { ConvertTo-DbmlLine $_ })
        $text = $parts -join ', '
    }
    else { $text = [string]$Value }
    $text = $text.Normalize([Text.NormalizationForm]::FormC)
    $text = [regex]::Replace($text, '[\x00-\x1F\x7F]', ' ')
    return ([regex]::Replace($text.Trim(), '\s+', ' '))
}

function ConvertTo-DbmlIdentifier($Value) {
    $text = ConvertTo-DbmlLine $Value
    return '"' + $text.Replace('\', '\\').Replace('"', '\"') + '"'
}

function ConvertTo-DbmlQuoted($Value) {
    $text = ConvertTo-DbmlLine $Value
    return "'" + $text.Replace('\', '\\').Replace("'", "\'") + "'"
}

function ConvertTo-DbmlToken($Value, [string]$Fallback = 'item', [int]$Limit = 128) {
    $text = [regex]::Replace((ConvertTo-DbmlLine $Value), '[^A-Za-z0-9_]+', '_').Trim('_')
    if ([string]::IsNullOrEmpty($text)) { $text = $Fallback }
    if ($text -match '^\d') { $text = '_' + $text }
    if ($text.Length -gt $Limit) { $text = $text.Substring(0, $Limit) }
    return $text
}

function ConvertTo-DbmlType($Value) {
    $text = ConvertTo-DbmlLine $Value
    if ([string]::IsNullOrEmpty($text)) { return 'unknown' }
    if ($text -match '^[A-Za-z_][A-Za-z0-9_]*(?:\.[A-Za-z_][A-Za-z0-9_]*)*(?:\((?:[A-Za-z_][A-Za-z0-9_]*|[0-9]+(?:\.[0-9]+)?)(?: *, *(?:[A-Za-z_][A-Za-z0-9_]*|[0-9]+(?:\.[0-9]+)?))*\))?$') {
        return $text
    }
    return ConvertTo-DbmlIdentifier $text
}

function Get-DbmlNormalizedName($Value) {
    return ConvertTo-Casefold (ConvertTo-DbmlLine $Value)
}

function Get-DbmlRows($Loaded, [string]$Name) {
    if ($Loaded.ContainsKey($Name)) { return @($Loaded[$Name]) }
    return @()
}

function New-DbmlDocument(
    [string]$Path,
    [string]$Layer,
    [string]$View,
    $SubmodelName,
    $Lines,
    [int]$TableCount,
    [int]$RelationshipCount
) {
    return [pscustomobject]@{
        path = $Path
        layer = $Layer
        view = $View
        submodel_name = $SubmodelName
        content = (($Lines -join [Environment]::NewLine).TrimEnd() + [Environment]::NewLine)
        table_count = $TableCount
        relationship_count = $RelationshipCount
    }
}

function Add-DbmlProjectLines($Lines, $Model, [string]$Suffix, [string]$Description) {
    $name = ConvertTo-DbmlToken (([string](Get-Property $Model 'model_name')) + '_' + $Suffix) 'model'
    [void]$Lines.Add("Project $name {")
    [void]$Lines.Add("  Note: " + (ConvertTo-DbmlQuoted (
        'Model: ' + [string](Get-Property $Model 'model_name') +
        ' | Model ID: ' + [string](Get-Property $Model 'model_id') +
        ' | Model revision: ' + [string](Get-Property $Model 'model_revision') +
        ' | View: ' + $Description
    )))
    [void]$Lines.Add('}')
    [void]$Lines.Add('')
}

function Render-ConceptualDbml($Loaded, $Model) {
    $objects = @(Get-DbmlRows $Loaded 'conceptual_object' | Where-Object {
        [string](Get-Property $_ 'conceptual_object_status') -ceq 'active'
    } | Sort-Object @{ Expression = { Get-DbmlNormalizedName (Get-Property $_ 'conceptual_object_name') } })
    $objectMap = @{}
    foreach ($record in $objects) {
        $key = Get-DbmlNormalizedName (Get-Property $record 'conceptual_object_name')
        if ($objectMap.ContainsKey($key)) { Fail 'Effective Conceptual Object names are not unique.' }
        $objectMap[$key] = $record
    }
    $relationships = @(Get-DbmlRows $Loaded 'conceptual_relationship' | Where-Object {
        [string](Get-Property $_ 'conceptual_relationship_status') -ceq 'active'
    } | Sort-Object @{ Expression = {
        (Get-DbmlNormalizedName (Get-Property $_ 'from_conceptual_object_name')) + [char]0 +
        (Get-DbmlNormalizedName (Get-Property $_ 'to_conceptual_object_name')) + [char]0 +
        (Get-DbmlNormalizedName (Get-Property $_ 'conceptual_relationship_name'))
    } })
    $lines = New-Object System.Collections.ArrayList
    Add-DbmlProjectLines $lines $Model 'conceptual' 'Complete conceptual model'
    foreach ($record in $objects) {
        $name = Get-Property $record 'conceptual_object_name'
        [void]$lines.Add("Table $(ConvertTo-DbmlIdentifier $name) [headercolor: #4E79A7] {")
        [void]$lines.Add("  `"__conceptual_key`" conceptual_key [pk, not null, note: 'Visualization-only endpoint; not a modeled Attribute.']")
        $note = @(
            'Type: ' + [string](Get-Property $record 'conceptual_object_type'),
            'Grain: ' + [string](Get-Property $record 'conceptual_object_grain'),
            'Definition: ' + [string](Get-Property $record 'conceptual_object_definition')
        ) -join ' | '
        if (-not [string]::IsNullOrWhiteSpace($note.Replace('Type:  | Grain:  | Definition: ', ''))) {
            [void]$lines.Add('  Note: ' + (ConvertTo-DbmlQuoted $note))
        }
        [void]$lines.Add('}')
        [void]$lines.Add('')
    }
    $cardinalities = @{ one_to_one = '-'; one_to_many = '<'; many_to_one = '>'; many_to_many = '<>' }
    $index = 0
    foreach ($record in $relationships) {
        $fromKey = Get-DbmlNormalizedName (Get-Property $record 'from_conceptual_object_name')
        $toKey = Get-DbmlNormalizedName (Get-Property $record 'to_conceptual_object_name')
        if (-not $objectMap.ContainsKey($fromKey) -or -not $objectMap.ContainsKey($toKey)) {
            Fail 'An effective Conceptual Relationship has an inactive or missing endpoint.'
        }
        $index++
        $cardinality = [string](Get-Property $record 'conceptual_relationship_cardinality')
        $operator = if ($cardinalities.ContainsKey($cardinality)) { $cardinalities[$cardinality] } else { '-' }
        [void]$lines.Add('// Relationship: ' + (ConvertTo-DbmlLine (Get-Property $record 'conceptual_relationship_name')))
        [void]$lines.Add(
            "Ref conceptual_relationship_${index}: " +
            (ConvertTo-DbmlIdentifier (Get-Property $objectMap[$fromKey] 'conceptual_object_name')) + '."__conceptual_key" ' +
            $operator + ' ' +
            (ConvertTo-DbmlIdentifier (Get-Property $objectMap[$toKey] 'conceptual_object_name')) + '."__conceptual_key"'
        )
        [void]$lines.Add('')
    }
    return New-DbmlDocument 'conceptual.dbml' 'conceptual' 'complete' $null $lines $objects.Count $relationships.Count
}

function Get-DbmlLayerSpec([string]$Layer) {
    if ($Layer -ceq 'logical') {
        return [ordered]@{
            submodel_dataset = 'logical_submodel'; submodel_name = 'logical_submodel_name'; submodel_definition = 'logical_submodel_definition'; submodel_status = 'logical_submodel_status'
            entity_dataset = 'logical_entity'; entity_name = 'logical_entity_name'; entity_status = 'logical_entity_status'; entity_order = 'logical_entity_dependency_order'; entity_definition = 'logical_entity_definition'
            attribute_dataset = 'logical_attribute'; attribute_entity = 'logical_entity_name'; attribute_name = 'logical_attribute_name'; attribute_status = 'logical_attribute_status'; attribute_type = 'logical_attribute_data_type'; attribute_ordinal = 'logical_attribute_ordinal_position'; attribute_nullable = 'logical_attribute_is_nullable'
            relationship_dataset = 'logical_relationship'; relationship_name = 'logical_relationship_name'; relationship_status = 'logical_relationship_status'; from_entity = 'from_logical_entity_name'; from_attribute = 'from_logical_attribute_name'; to_entity = 'to_logical_entity_name'; to_attribute = 'to_logical_attribute_name'; relationship_cardinality = 'logical_relationship_cardinality'
        }
    }
    return [ordered]@{
        submodel_dataset = 'dimensional_submodel'; submodel_name = 'dimensional_submodel_name'; submodel_definition = 'dimensional_submodel_definition'; submodel_status = 'dimensional_submodel_status'
        entity_dataset = 'dimensional_entity'; entity_name = 'dimensional_entity_name'; entity_status = 'dimensional_entity_status'; entity_order = 'dimensional_entity_dependency_order'; entity_definition = 'dimensional_entity_definition'
        attribute_dataset = 'dimensional_attribute'; attribute_entity = 'dimensional_entity_name'; attribute_name = 'dimensional_attribute_name'; attribute_status = 'dimensional_attribute_status'; attribute_type = 'dimensional_attribute_data_type'; attribute_ordinal = 'dimensional_attribute_ordinal_position'; attribute_nullable = 'dimensional_attribute_is_nullable'
        relationship_dataset = 'dimensional_relationship'; relationship_name = 'dimensional_relationship_name'; relationship_status = 'dimensional_relationship_status'; from_entity = 'from_dimensional_entity_name'; from_attribute = 'from_dimensional_attribute_name'; to_entity = 'to_dimensional_entity_name'; to_attribute = 'to_dimensional_attribute_name'; relationship_cardinality = 'dimensional_relationship_cardinality'
    }
}

function Get-DbmlLayerData($Loaded, [string]$Layer) {
    $spec = Get-DbmlLayerSpec $Layer
    $submodels = @(Get-DbmlRows $Loaded $spec.submodel_dataset | Where-Object {
        [string](Get-Property $_ $spec.submodel_status) -ceq 'active'
    } | Sort-Object @{ Expression = { Get-DbmlNormalizedName (Get-Property $_ $spec.submodel_name) } })
    $submodelMap = @{}
    foreach ($record in $submodels) {
        $key = Get-DbmlNormalizedName (Get-Property $record $spec.submodel_name)
        if ($submodelMap.ContainsKey($key)) { Fail "Effective $Layer Submodel names are not unique." }
        $submodelMap[$key] = $record
    }
    $entities = @(Get-DbmlRows $Loaded $spec.entity_dataset | Where-Object {
        [string](Get-Property $_ $spec.entity_status) -ceq 'active'
    } | Sort-Object @{ Expression = { Get-Property $_ $spec.entity_order } }, @{ Expression = { Get-DbmlNormalizedName (Get-Property $_ $spec.entity_name) } })
    $entityMap = @{}
    $memberships = @{}
    foreach ($record in $entities) {
        $key = Get-DbmlNormalizedName (Get-Property $record $spec.entity_name)
        if ($entityMap.ContainsKey($key)) { Fail "Effective $Layer Entity names are not unique." }
        $entityMap[$key] = $record
        $memberships[$key] = @{}
        $values = Get-Property $record 'submodels'
        if ($values -is [Array]) {
            foreach ($membership in @($values)) {
                if ([string](Get-Property $membership 'membership_status') -cne 'active') { continue }
                $submodelKey = Get-DbmlNormalizedName (Get-Property $membership 'submodel_name')
                if (-not $submodelMap.ContainsKey($submodelKey)) {
                    Fail "An effective $Layer Entity membership has an inactive or missing Submodel."
                }
                $memberships[$key][$submodelKey] = $true
            }
        }
    }
    $attributes = @{}
    $attributeKeys = @{}
    foreach ($record in @(Get-DbmlRows $Loaded $spec.attribute_dataset | Where-Object {
        [string](Get-Property $_ $spec.attribute_status) -ceq 'active'
    })) {
        $entityKey = Get-DbmlNormalizedName (Get-Property $record $spec.attribute_entity)
        $attributeKey = Get-DbmlNormalizedName (Get-Property $record $spec.attribute_name)
        if (-not $entityMap.ContainsKey($entityKey)) { Fail "An effective $Layer Attribute has an inactive or missing Entity." }
        $combined = $entityKey + [char]0 + $attributeKey
        if ($attributeKeys.ContainsKey($combined)) { Fail "Effective $Layer Attribute names are not unique." }
        $attributeKeys[$combined] = $true
        if (-not $attributes.ContainsKey($entityKey)) { $attributes[$entityKey] = New-Object System.Collections.ArrayList }
        [void]$attributes[$entityKey].Add($record)
    }
    foreach ($entityKey in @($attributes.Keys)) {
        $attributes[$entityKey] = @($attributes[$entityKey] | Sort-Object @{ Expression = { Get-Property $_ $spec.attribute_ordinal } }, @{ Expression = { Get-DbmlNormalizedName (Get-Property $_ $spec.attribute_name) } })
    }
    $relationships = @(Get-DbmlRows $Loaded $spec.relationship_dataset | Where-Object {
        [string](Get-Property $_ $spec.relationship_status) -ceq 'active'
    })
    $validCardinalities = @('one_to_one', 'one_to_many', 'many_to_one', 'many_to_many')
    foreach ($record in $relationships) {
        $fromEntity = Get-DbmlNormalizedName (Get-Property $record $spec.from_entity)
        $fromAttribute = Get-DbmlNormalizedName (Get-Property $record $spec.from_attribute)
        $toEntity = Get-DbmlNormalizedName (Get-Property $record $spec.to_entity)
        $toAttribute = Get-DbmlNormalizedName (Get-Property $record $spec.to_attribute)
        if (-not $entityMap.ContainsKey($fromEntity) -or -not $entityMap.ContainsKey($toEntity) -or
            -not $attributeKeys.ContainsKey($fromEntity + [char]0 + $fromAttribute) -or
            -not $attributeKeys.ContainsKey($toEntity + [char]0 + $toAttribute)) {
            Fail "An effective $Layer Relationship has an inactive or missing endpoint."
        }
        if ($validCardinalities -cnotcontains [string](Get-Property $record $spec.relationship_cardinality)) {
            Fail "An effective $Layer Relationship has invalid cardinality."
        }
    }
    return [pscustomobject]@{
        Spec = $spec; Submodels = $submodels; SubmodelMap = $submodelMap
        Entities = $entities; EntityMap = $entityMap; Memberships = $memberships
        Attributes = $attributes; Relationships = $relationships
    }
}

function Render-ModeledDbml($Data, $Model, [string]$Layer, $Included, [string]$Path, [string]$View, $SubmodelName, [string]$Description) {
    $spec = $Data.Spec
    $lines = New-Object System.Collections.ArrayList
    Add-DbmlProjectLines $lines $Model (ConvertTo-DbmlToken $Description 'model') $Description
    $tableCount = 0
    foreach ($entity in @($Data.Entities)) {
        $entityKey = Get-DbmlNormalizedName (Get-Property $entity $spec.entity_name)
        if ($null -ne $Included -and -not $Included.ContainsKey($entityKey)) { continue }
        $tableCount++
        [void]$lines.Add("Table $(ConvertTo-DbmlIdentifier (Get-Property $entity $spec.entity_name)) [headercolor: #4E79A7] {")
        $entityAttributes = if ($Data.Attributes.ContainsKey($entityKey)) { @($Data.Attributes[$entityKey]) } else { @() }
        foreach ($attribute in $entityAttributes) {
            $settings = New-Object System.Collections.Generic.List[string]
            if ($Layer -ceq 'logical' -and [bool](Get-Property $attribute 'logical_attribute_is_primary_key')) { [void]$settings.Add('pk') }
            if ($Layer -ceq 'dimensional' -and [string](Get-Property $attribute 'dimensional_attribute_key_role') -ceq 'surrogate') { [void]$settings.Add('pk') }
            if ([bool](Get-Property $attribute $spec.attribute_nullable)) { [void]$settings.Add('null') } else { [void]$settings.Add('not null') }
            $definition = Get-Property $attribute ($Layer + '_attribute_definition')
            if (-not [string]::IsNullOrWhiteSpace([string]$definition)) { [void]$settings.Add('note: ' + (ConvertTo-DbmlQuoted $definition)) }
            [void]$lines.Add(
                '  ' + (ConvertTo-DbmlIdentifier (Get-Property $attribute $spec.attribute_name)) + ' ' +
                (ConvertTo-DbmlType (Get-Property $attribute $spec.attribute_type)) + ' [' + ($settings -join ', ') + ']'
            )
        }
        $definition = Get-Property $entity $spec.entity_definition
        if (-not [string]::IsNullOrWhiteSpace([string]$definition)) { [void]$lines.Add('  Note: ' + (ConvertTo-DbmlQuoted $definition)) }
        [void]$lines.Add('}')
        [void]$lines.Add('')
    }
    $operators = @{ one_to_one = '-'; one_to_many = '<'; many_to_one = '>'; many_to_many = '<>' }
    $relationshipCount = 0
    foreach ($relationship in @($Data.Relationships)) {
        $fromKey = Get-DbmlNormalizedName (Get-Property $relationship $spec.from_entity)
        $toKey = Get-DbmlNormalizedName (Get-Property $relationship $spec.to_entity)
        if ($null -ne $Included -and (-not $Included.ContainsKey($fromKey) -or -not $Included.ContainsKey($toKey))) { continue }
        $relationshipCount++
        [void]$lines.Add('// Relationship: ' + (ConvertTo-DbmlLine (Get-Property $relationship $spec.relationship_name)))
        [void]$lines.Add(
            "Ref ${Layer}_relationship_${relationshipCount}: " +
            (ConvertTo-DbmlIdentifier (Get-Property $Data.EntityMap[$fromKey] $spec.entity_name)) + '.' +
            (ConvertTo-DbmlIdentifier (Get-Property $relationship $spec.from_attribute)) + ' ' +
            $operators[[string](Get-Property $relationship $spec.relationship_cardinality)] + ' ' +
            (ConvertTo-DbmlIdentifier (Get-Property $Data.EntityMap[$toKey] $spec.entity_name)) + '.' +
            (ConvertTo-DbmlIdentifier (Get-Property $relationship $spec.to_attribute))
        )
        [void]$lines.Add('')
    }
    return New-DbmlDocument $Path $Layer $View $SubmodelName $lines $tableCount $relationshipCount
}

function Render-ModeledDbmlDocuments($Loaded, $Model, [string]$Layer, [bool]$IncludeSubmodels) {
    $data = Get-DbmlLayerData $Loaded $Layer
    $documents = New-Object System.Collections.ArrayList
    [void]$documents.Add((Render-ModeledDbml $data $Model $Layer $null ($Layer + '_complete.dbml') 'complete' $null ('Complete ' + $Layer + ' model')))
    if (-not $IncludeSubmodels) { return @($documents) }
    $used = @{ ($Layer + '_complete.dbml') = $true; ($Layer + '_default.dbml') = $true }
    $assigned = @{}
    foreach ($submodel in @($data.Submodels)) {
        $name = Get-Property $submodel $data.Spec.submodel_name
        $key = Get-DbmlNormalizedName $name
        $included = @{}
        foreach ($entityKey in @($data.Memberships.Keys)) {
            if ($data.Memberships[$entityKey].ContainsKey($key)) { $included[$entityKey] = $true; $assigned[$entityKey] = $true }
        }
        $base = $Layer + '_' + (ConvertTo-DbmlToken $name 'submodel' 220).ToLowerInvariant()
        $path = $base + '.dbml'
        $suffix = 2
        while ($used.ContainsKey($path.ToLowerInvariant())) { $path = $base + '_' + $suffix + '.dbml'; $suffix++ }
        $used[$path.ToLowerInvariant()] = $true
        $description = $Layer.Substring(0, 1).ToUpperInvariant() + $Layer.Substring(1) + ' Submodel: ' + [string]$name
        [void]$documents.Add((Render-ModeledDbml $data $Model $Layer $included $path 'submodel' $name $description))
    }
    $unassigned = @{}
    foreach ($entityKey in @($data.EntityMap.Keys)) { if (-not $assigned.ContainsKey($entityKey)) { $unassigned[$entityKey] = $true } }
    if ($unassigned.Count -gt 0) {
        [void]$documents.Add((Render-ModeledDbml $data $Model $Layer $unassigned ($Layer + '_default.dbml') 'default' $null ($Layer + ' Entities without an active Submodel membership')))
    }
    return @($documents)
}

function Generate-LocalDbml([hashtable]$Options) {
    if ((Require-Option $Options 'area') -cne 'model') { Fail '--area must be model for generate-dbml.' }
    $modelType = if ($Options.ContainsKey('model-type')) { [string]$Options['model-type'] } else { 'full' }
    if (@('full', 'conceptual', 'logical', 'dimensional') -cnotcontains $modelType) {
        Fail '--model-type must be full, conceptual, logical, or dimensional.'
    }
    $includeText = if ($Options.ContainsKey('include-submodels')) { [string]$Options['include-submodels'] } else { 'true' }
    if (@('true', 'false') -cnotcontains $includeText) { Fail '--include-submodels must be true or false.' }
    $includeSubmodels = $includeText -ceq 'true'
    $context = Get-ChangeContext $Options
    $sessionDigest = (Read-SessionDocument $context.Session).digest
    $validationOptions = $Options.Clone(); $validationOptions['_includeQuality'] = $false
    $validation = Validate-Changes $validationOptions
    if (-not $validation.valid) { Fail 'Correct local Model findings before generating DBML.' }
    $verifyInputs = {
        if ((Read-SessionDocument $context.Session).digest -cne $sessionDigest -or (Get-WorkspaceDigest $context) -cne $validation.digest) { Fail 'DBML inputs changed during generation; reload and generate again.' }
        foreach ($inputBinding in $validation.inputs) { if ((Get-FileDigest (Resolve-WorkspacePath $context.Session $inputBinding.manifest_path)) -cne $inputBinding.manifest_sha256) { Fail 'DBML inputs changed during generation; reload and generate again.' } }
    }
    & $verifyInputs
    $pending = Read-Pending $context
    $loaded = @{}
    foreach ($dataset in @($context.Datasets)) {
        $draft = if ($pending.ContainsKey([string]$dataset.name)) { @($pending[[string]$dataset.name]) } else { @() }
        $loaded[[string]$dataset.name] = @(Get-EffectiveRecords $context $dataset $draft)
    }
    $model = Get-Property $context.Catalog 'model'
    if ($null -eq $model -or -not (Test-SafeJsonInteger (Get-Property $model 'model_id') $false) -or
        -not (Test-SafeJsonInteger (Get-Property $model 'model_revision') $true) -or
        [string]::IsNullOrWhiteSpace([string](Get-Property $model 'model_name'))) {
        Fail 'Model identity is required for DBML generation.'
    }
    $documents = New-Object System.Collections.ArrayList
    if (@('full', 'conceptual') -ccontains $modelType) { [void]$documents.Add((Render-ConceptualDbml $loaded $model)) }
    if (@('full', 'logical') -ccontains $modelType) {
        foreach ($document in @(Render-ModeledDbmlDocuments $loaded $model 'logical' $includeSubmodels)) { [void]$documents.Add($document) }
    }
    if (@('full', 'dimensional') -ccontains $modelType) {
        foreach ($document in @(Render-ModeledDbmlDocuments $loaded $model 'dimensional' $includeSubmodels)) { [void]$documents.Add($document) }
    }
    $documents = @($documents | Sort-Object path)
    if ($documents.Count -lt 1 -or $documents.Count -gt 1002) { Fail 'DBML file inventory is invalid.' }

    $temporary = Split-Path -Parent (Resolve-WorkspacePath $context.Session ('.atlas/temp/dbml-' + [Guid]::NewGuid().ToString() + '/.check') $true)
    $directory = Join-Path $temporary 'candidate'; [void][IO.Directory]::CreateDirectory($directory)
    $manifestPath = Join-Path $directory 'manifest.json'
    $files = New-Object System.Collections.ArrayList
    $names = @{}
    [long]$totalBytes = 0
    foreach ($document in $documents) {
        $name = [string]$document.path
        if ($name -notmatch '^[A-Za-z0-9_][A-Za-z0-9_.-]*\.dbml$' -or $names.ContainsKey($name.ToLowerInvariant())) {
            Fail 'DBML file inventory is invalid.'
        }
        $names[$name.ToLowerInvariant()] = $true
        [byte[]]$bytes = $script:Utf8NoBom.GetBytes([string]$document.content)
        if ($bytes.Length -lt 1 -or $bytes.Length -gt 12 * 1024 * 1024) { Fail 'DBML output exceeds its safe file bounds.' }
        $totalBytes += $bytes.Length
        if ($totalBytes -gt 16 * 1024 * 1024) { Fail 'DBML output exceeds its safe file bounds.' }
        Write-TextAtomic (Join-Path $directory $name) ([string]$document.content)
        [void]$files.Add([ordered]@{
            path = $name; layer = [string]$document.layer; view = [string]$document.view
            submodel_name = $document.submodel_name; table_count = [int]$document.table_count
            relationship_count = [int]$document.relationship_count; size_bytes = $bytes.Length
            sha256 = Get-ByteDigest $bytes
        })
    }
    $manifest = [ordered]@{
        schema_version = '1.0'; snapshot_kind = 'dbml'; source = 'local_effective_model'; generated_by = 'agent'; inputs = $validation.inputs
        model = [ordered]@{ id = Get-Property $model 'model_id'; name = Get-Property $model 'model_name'; revision = Get-Property $model 'model_revision' }
        draft_digest = Get-WorkspaceDigest $context; model_type = $modelType
        include_submodels = $includeSubmodels; files = @($files)
    }
    Write-JsonAtomic $manifestPath $manifest
    & $verifyInputs
    $destination = Resolve-WorkspacePath $context.Session 'model-dbml'; $backup = Join-Path $temporary 'previous'
    $existed = Test-Path -LiteralPath $destination
    if ($existed) { [void](Resolve-RegularDirectory $destination 'DBML'); [IO.Directory]::Move($destination, $backup) }
    try { [IO.Directory]::Move($directory, $destination); & $verifyInputs }
    catch {
        if (Test-Path -LiteralPath $destination) { [IO.Directory]::Move($destination, $directory) }
        if ($existed) { [IO.Directory]::Move($backup, $destination) }
        throw
    }
    $directory = $destination; $manifestPath = Join-Path $destination 'manifest.json'
    return [ordered]@{
        directory = $directory; manifest = $manifestPath; file_count = $files.Count
        draft_digest = [string]$manifest.draft_digest; files = @($files | ForEach-Object { [string](Get-Property $_ 'path') })
    }
}

. (Join-Path $PSScriptRoot 'model-quality.ps1')
. (Join-Path $PSScriptRoot 'model-policy.ps1')
. (Join-Path $PSScriptRoot 'sql-validation.ps1')
. (Join-Path $PSScriptRoot 'workspace-native.ps1')
. (Join-Path $PSScriptRoot 'operation-evidence.ps1')

try {
    $options = Parse-Options $RemainingArguments
    $definition = Get-CommandContract @{command = $Command}
    $allowed = @{}
    foreach ($match in [regex]::Matches($definition.usage, '--([a-z0-9-]+)')) { $allowed[$match.Groups[1].Value] = $true }
    if (@('copy', 'upsert', 'upsert-batch', 'discard', 'review', 'accept', 'generate-dbml') -ccontains $Command) { $allowed.task = $true }
    foreach ($option in $options.Keys) { if (-not $allowed.ContainsKey($option)) { Fail "Unsupported option --$option for $Command. Read command-contract." } }
    $outputTarget = $null
    if ($options['output-file']) {
        $root = Resolve-Session $options
        $path = if ([IO.Path]::IsPathRooted($options['output-file'])) { [IO.Path]::GetFullPath($options['output-file']) } else { [IO.Path]::GetFullPath((Join-Path $root $options['output-file'])) }
        $prefix = $root.TrimEnd([IO.Path]::DirectorySeparatorChar) + [IO.Path]::DirectorySeparatorChar
        $comparison = if ([IO.Path]::DirectorySeparatorChar -eq '\') { [StringComparison]::OrdinalIgnoreCase } else { [StringComparison]::Ordinal }
        if (-not $path.StartsWith($prefix, $comparison)) { Fail '--output-file must be a new JSON file under .atlas/temp/.' }
        $relative = $path.Substring($prefix.Length).Replace('\', '/')
        if (-not $relative.StartsWith('.atlas/temp/', [StringComparison]::Ordinal) -or -not $relative.EndsWith('.json', [StringComparison]::Ordinal)) { Fail '--output-file must be a new JSON file under .atlas/temp/.' }
        $file = Resolve-WorkspacePath $root $relative $true
        if (Test-Path -LiteralPath $file) { Fail '--output-file already exists; choose a new file.' }
        $outputTarget = [ordered]@{root = $root; relative = $relative}
    }
    switch ($Command) {
        'command-contract' { $output = Get-CommandContract $options }
        'session-init' { $output = Initialize-Session $options }
        'task-select' { $output = Select-AtlasTask $options }
        'model-select' { $output = Select-AtlasModel $options }
        'status' { $output = Get-SessionStatus $options }
        'owner-add' { $output = Register-Owner $options }
        'sql-policy' { $output = Set-SqlPolicy $options }
        'task-add' { $output = Add-Task $options }
        'task-update' { $output = Update-Task $options }
        'inspect' { $output = Inspect-Snapshot $options }
        'describe' { $output = Describe-Dataset $options }
        'select' { $output = Select-Snapshot $options }
        'copy' { $output = Copy-Records $options }
        'upsert' { $output = Upsert-Record $options }
        'upsert-batch' { $output = Upsert-RecordsBatch $options }
        'discard' { $output = Discard-Record $options }
        'review' { $output = Review-Changes $options }
        'validate' { $output = Validate-Changes $options }
        'accept' { $output = Accept-Changes $options }
        'draft-cache' { $output = Set-DraftCache $options }
        'prepare-stage-request' { $output = Prepare-StageRequest $options }
        'generate-dbml' { $output = Generate-LocalDbml $options }
        'snapshot-install' { $output = Install-Snapshot $options }
        'operation-record' { $output = Record-Operation $options }
        'profile-results' { $output = Import-ProfileResults $options }
        'profile-plan' { . (Join-Path $PSScriptRoot 'profiling.ps1'); $output = New-AggregatePlan $options 'profiling' }
        'analysis-plan' { . (Join-Path $PSScriptRoot 'analysis.ps1'); $output = New-AggregatePlan $options 'analysis' }
        default { Fail "Unknown Atlas command: $Command." }
    }
    if ($outputTarget) {
        $temporary = $null
        try {
            $file = Resolve-WorkspacePath $outputTarget.root $outputTarget.relative
            $temporary = $file + '.' + [Guid]::NewGuid().ToString() + '.tmp'
            $bytes = $script:Utf8NoBom.GetBytes((ConvertTo-GdsJson $output) + "`n")
            $stream = [IO.File]::Open($temporary, [IO.FileMode]::CreateNew, [IO.FileAccess]::Write, [IO.FileShare]::None)
            try { $stream.Write($bytes, 0, $bytes.Length) } finally { $stream.Dispose() }
            [void](Resolve-WorkspacePath $outputTarget.root $outputTarget.relative)
            [IO.File]::Move($temporary, $file) # Atomic new-file publication; never replace another result.
        }
        catch {
            Set-Property $output 'receipt_export' ([ordered]@{status = 'failed'; code = 'RECEIPT_EXPORT_FAILED';
                message = 'Result export failed; the command outcome above is unchanged. Use its returned result; do not repeat the operation.'})
        }
        finally {
            if ($temporary) { try { [IO.File]::Delete($temporary) } catch {} }
        }
    }
    [Console]::Out.WriteLine((ConvertTo-GdsJson $output))
    exit 0
}
catch {
    [Console]::Error.WriteLine('atlas-local: ' + $_.Exception.Message)
    exit 1
}
