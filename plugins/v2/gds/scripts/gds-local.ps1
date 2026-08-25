[CmdletBinding()]
param(
    [Parameter(Position = 0, Mandatory = $true)]
    [string]$Command,

    [Parameter(ValueFromRemainingArguments = $true)]
    [string[]]$RemainingArguments
)

Set-StrictMode -Version 2.0
$ErrorActionPreference = 'Stop'
$script:Utf8NoBom = New-Object System.Text.UTF8Encoding($false)
$script:JsonMaxDepth = 512
$script:CasefoldMap = $null
$script:Areas = @('metadata', 'model')
$script:TaskAreas = @('metadata', 'model', 'code', 'validation')
$script:PhysicalObjectFields = @('tenant_code', 'system_code', 'connection_code', 'object_schema', 'object_name')
$script:ReadinessTargets = [ordered]@{
    'logical-build' = @('metadata', 'model')
    'silver-registration' = @('metadata', 'model')
    'logical-mapping' = @('metadata', 'model')
    'logical-code' = @('model')
    'dimensional-build' = @('metadata', 'model')
    'gold-registration' = @('metadata', 'model')
    'dimensional-mapping' = @('metadata', 'model')
    'dimensional-code' = @('model')
}
$script:ReadinessStatusFields = @{
    logical_entity = 'logical_entity_status'
    logical_attribute = 'logical_attribute_status'
    dimensional_entity = 'dimensional_entity_status'
    dimensional_attribute = 'dimensional_attribute_status'
    mapping_dependency = 'mapping_source_system_dependency_status'
    mapping_object = 'object_mapping_status'
    mapping_attribute = 'attribute_mapping_status'
}
$script:Transitions = @{
    queued     = @('todo', 'doing', 'waiting', 'cancelled')
    todo       = @('doing', 'waiting', 'cancelled')
    doing      = @('waiting', 'review', 'done', 'cancelled')
    waiting    = @('todo', 'doing', 'cancelled')
    review     = @('doing', 'ready', 'overridden', 'cancelled')
    ready      = @('doing', 'staged', 'cancelled')
    overridden = @('doing', 'staged', 'cancelled')
    staged     = @('doing', 'review', 'ready', 'overridden', 'applied', 'cancelled')
    applied    = @()
    done       = @()
    cancelled  = @()
}

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
    $item = Get-Item -LiteralPath $Path -ErrorAction Stop
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

function Get-FileDigest([string]$Path) {
    $item = Get-Item -LiteralPath $Path -ErrorAction Stop
    if ($item.PSIsContainer -or ($item.Attributes -band [IO.FileAttributes]::ReparsePoint)) {
        Fail 'Task plan must be a regular file.'
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

function Write-JsonAtomic([string]$Path, $Value) {
    $directory = Split-Path -Parent $Path
    $temporary = Join-Path $directory ('.' + [IO.Path]::GetFileName($Path) + '.' + [Guid]::NewGuid().ToString('N') + '.tmp')
    $text = (ConvertTo-GdsJson $Value) + [Environment]::NewLine
    [IO.File]::WriteAllText($temporary, $text, $script:Utf8NoBom)
    try {
        if (Test-Path -LiteralPath $Path -PathType Leaf) {
            try { [IO.File]::Replace($temporary, $Path, $null, $true) }
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

function Resolve-RegularDirectory([string]$Path, [string]$Label) {
    $item = Get-Item -LiteralPath ([IO.Path]::GetFullPath($Path)) -ErrorAction Stop
    if (-not $item.PSIsContainer -or ($item.Attributes -band [IO.FileAttributes]::ReparsePoint)) {
        Fail "$Label must be a regular directory."
    }
    return $item.FullName
}

function Resolve-Session([hashtable]$Options) {
    $session = Resolve-RegularDirectory (Require-Option $Options 'session') 'Session'
    if (-not (Test-Path -LiteralPath (Join-Path $session 'session.json') -PathType Leaf)) {
        Fail 'Session does not contain session.json.'
    }
    return $session
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

function Read-SessionState([string]$Session) {
    $state = Read-Json (Join-Path $Session 'session.json') 'Session state'
    if ($null -eq $state -or $state -is [Array] -or $state -is [string] -or $state -is [ValueType] -or
        -not (Test-Property $state 'tasks') -or -not (Test-Property $state 'current')) {
        Fail 'Session state has an invalid shape.'
    }
    $tasksValue = Get-Property $state 'tasks'
    $currentValue = Get-Property $state 'current'
    if ($tasksValue -isnot [Array] -or ($null -ne $currentValue -and $currentValue -isnot [string])) {
        Fail 'Session state has an invalid shape.'
    }
    $taskIds = New-Object 'System.Collections.Generic.HashSet[string]' ([StringComparer]::Ordinal)
    foreach ($task in @($tasksValue)) {
        $tuple = @($task)
        if ($tuple.Count -ne 4 -or $tuple[0] -isnot [string] -or $tuple[0] -notmatch '^\d{2,}$' -or
            $tuple[1] -isnot [string] -or $script:TaskAreas -cnotcontains [string]$tuple[1] -or
            $tuple[2] -isnot [string] -or ([string]$tuple[2]).Length -eq 0 -or
            $tuple[3] -isnot [string] -or $script:Transitions.Keys -cnotcontains [string]$tuple[3] -or
            -not $taskIds.Add([string]$tuple[0])) {
            Fail 'Session state has an invalid shape.'
        }
    }
    if ($null -ne $currentValue -and -not $taskIds.Contains([string]$currentValue)) {
        Fail 'Session state has an invalid shape.'
    }
    if (Test-Property $state 'model') {
        $binding = Get-Property $state 'model'
        if ($binding.Count -ne 2 -or -not (Test-SafeJsonInteger $binding[0] $false) -or
            $binding[1] -isnot [string] -or [string]::IsNullOrWhiteSpace([string]$binding[1]) -or
            ([string]$binding[1]).Length -gt 255) {
            Fail 'Session state has an invalid shape.'
        }
    }
    if (Test-Property $state 'cs') {
        $serverDraftCache = Get-Property $state 'cs'
        if ($null -eq $serverDraftCache -or $serverDraftCache -is [Array] -or
            $serverDraftCache -is [string] -or $serverDraftCache -is [ValueType]) {
            Fail 'Session state has an invalid shape.'
        }
        foreach ($name in @(Get-PropertyNames $serverDraftCache)) {
            $draft = Get-Property $serverDraftCache $name
            if ($script:Areas -cnotcontains $name -or $draft.Count -ne 5 -or
                $draft[0] -isnot [string] -or [string]$draft[0] -notmatch '^[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}$' -or
                -not (Test-SafeJsonInteger $draft[1] $true) -or
                $draft[2] -isnot [string] -or @('active', 'validated') -cnotcontains [string]$draft[2] -or
                $draft[3] -isnot [string] -or [string]$draft[3] -notmatch '^\d{2,}$' -or
                $draft[4] -isnot [string] -or [string]$draft[4] -cnotmatch '^[0-9a-f]{64}$') {
                Fail 'Session state has an invalid shape.'
            }
            $boundTask = $null
            foreach ($task in @($tasksValue)) {
                if ([string]$task[0] -ceq [string]$draft[3]) { $boundTask = $task; break }
            }
            if ($null -eq $boundTask -or [string]$boundTask[1] -cne $name) {
                Fail 'Session server-draft cache does not match its bound task area.'
            }
        }
    }
    return $state
}

function Initialize-Session([hashtable]$Options) {
    $rootValue = Require-Option $Options 'root'
    $tenant = Require-Option $Options 'tenant'
    if ($tenant -notmatch '^[A-Za-z0-9][A-Za-z0-9._-]{0,99}$') {
        Fail 'Tenant Code must contain only letters, numbers, dot, underscore, or hyphen.'
    }
    $root = [IO.Path]::GetFullPath($rootValue)
    $tenantRoot = Join-Path (Join-Path $root 'GDS') $tenant
    [void][IO.Directory]::CreateDirectory($tenantRoot)
    $manifestPath = Join-Path $tenantRoot 'manifest.json'
    $highest = 0
    if (Test-Path -LiteralPath $manifestPath -PathType Leaf) {
        $manifest = Read-Json $manifestPath 'Tenant manifest'
        if (-not (Test-Property $manifest 'highest')) { Fail 'Tenant manifest has an invalid shape.' }
        $highest = [int]$manifest.highest
        if ($highest -lt 0) { Fail 'Tenant manifest has an invalid shape.' }
    }
    $next = $highest + 1
    $sessionId = if ($next -lt 100) { $next.ToString('00') } else { $next.ToString() }
    $session = Join-Path $tenantRoot $sessionId
    if (Test-Path -LiteralPath $session) { Fail "Session $sessionId already exists." }
    [void][IO.Directory]::CreateDirectory($session)
    foreach ($name in @('tasks', 'metadata', 'metadata-change-set', 'model', 'model-change-set', 'code')) {
        [void][IO.Directory]::CreateDirectory((Join-Path $session $name))
    }
    Write-JsonAtomic (Join-Path $session 'session.json') ([ordered]@{ current = $null; tasks = @() })
    Write-JsonAtomic $manifestPath ([ordered]@{ current = $sessionId; highest = $next })
    return [ordered]@{ tenant = $tenant; session = $sessionId; path = $session }
}

function Parse-TaskPlan([string]$Text) {
    try {
        $value = ConvertFrom-GdsJson $Text
        if ($value -isnot [Array]) { throw 'Task plan root is not an array.' }
        $plan = @($value)
    }
    catch { Fail '--plan must be a JSON array of action lines.' }
    if ($plan.Count -lt 1 -or $plan.Count -gt 64) { Fail '--plan must contain 1 to 64 action lines.' }
    foreach ($line in $plan) {
        if ($line -isnot [string] -or [string]::IsNullOrWhiteSpace($line) -or $line -ne $line.Trim() -or $line.Length -gt 300) {
            Fail '--plan contains an invalid action line.'
        }
    }
    return @($plan)
}

function Get-SessionStatus([hashtable]$Options) {
    $session = Resolve-Session $Options
    $snapshots = [ordered]@{}
    foreach ($area in $script:Areas) {
        $snapshotOptions = @{ session = $session; area = $area }
        try {
            $snapshot = Find-Snapshot $snapshotOptions
            $revision = if (Test-Property $snapshot.Manifest 'model_revision') { $snapshot.Manifest.model_revision } else { $null }
            $snapshots[$area] = @($snapshot.Manifest.snapshot_id, $revision)
        }
        catch {
            if ($_.Exception.Message -eq "Expected exactly one unzipped $area Snapshot; found 0.") { $snapshots[$area] = $null }
            else { throw }
        }
    }
    $state = Read-SessionState $session
    $current = $null
    foreach ($task in @($state.tasks)) { if ($task[0] -eq $state.current) { $current = @($task); break } }
    $resume = $null
    if ($null -eq $current) {
        foreach ($task in @($state.tasks)) { if ($task[3] -eq 'waiting') { $resume = @($task); break } }
    }
    $planTask = if ($null -ne $current) { $current } else { $resume }
    $plan = $null
    $planDigest = $null
    if ($null -ne $planTask) {
        $planPath = Join-Path (Join-Path $session 'tasks') ([string]$planTask[0] + '.json')
        $plan = @(Read-Json $planPath 'Active or waiting task plan')
        [void](Parse-TaskPlan (ConvertTo-GdsJson $plan))
        $planDigest = Get-FileDigest $planPath
    }
    $pending = [ordered]@{}
    foreach ($area in $script:Areas) {
        $summary = Get-PendingSummary (Get-PendingDirectory $session $area)
        $pending[$area] = @($summary.Files, $summary.Bytes, $summary.Digest)
    }
    $stashes = New-Object System.Collections.ArrayList
    foreach ($task in @($state.tasks)) {
        if ($script:Areas -cnotcontains [string]$task[1]) { continue }
        $stash = Get-TaskStashDirectory $session $task
        if (-not (Test-Path -LiteralPath $stash)) { continue }
        $item = Get-Item -LiteralPath $stash -Force -ErrorAction Stop
        if (-not $item.PSIsContainer -or ($item.Attributes -band [IO.FileAttributes]::ReparsePoint)) {
            Fail 'Task stash must be a regular directory.'
        }
        $summary = Get-PendingSummary $item.FullName
        if ($summary.Files -eq 0) { Fail 'Task stash must not be empty.' }
        [void]$stashes.Add(@([string]$task[0], [string]$task[1], [int]$summary.Files, [string]$summary.Digest))
    }
    $stale = @()
    if (Test-Property $state 'stale') { $stale = @($state.stale) }
    $cache = if (Test-Property $state 'cs') { $state.cs } else { [ordered]@{} }
    $model = $null
    if (Test-Property $state 'model') { $model = @($state.model) }
    return [ordered]@{ current = $current; resume = $resume; plan = $plan; plan_digest = $planDigest; tasks = @($state.tasks); model = $model; cs = $cache; stale = $stale; snapshots = $snapshots; pending = $pending; stashes = @($stashes) }
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
        $RelativePath -match '^[A-Za-z]:' -or $RelativePath.Contains('\') -or
        $RelativePath.IndexOf([char]0) -ge 0 -or $unsafePart) {
        Fail 'Snapshot manifest contains an unsafe member path.'
    }
}

function Find-Snapshot([hashtable]$Options) {
    $session = Resolve-Session $Options
    $area = Require-Option $Options 'area'
    if ($script:Areas -notcontains $area) { Fail '--area must be metadata or model.' }
    $areaPath = Resolve-RegularDirectory (Join-Path $session $area) "$area Snapshot directory"
    $candidates = New-Object System.Collections.Generic.List[string]
    if ((Test-Path -LiteralPath (Join-Path $areaPath 'manifest.json') -PathType Leaf) -and
        (Test-Path -LiteralPath (Join-Path $areaPath 'catalog.json') -PathType Leaf)) {
        [void]$candidates.Add($areaPath)
    }
    foreach ($child in @(Get-ChildItem -LiteralPath $areaPath -Directory -Force)) {
        if ($child.Attributes -band [IO.FileAttributes]::ReparsePoint) { continue }
        if ((Test-Path -LiteralPath (Join-Path $child.FullName 'manifest.json') -PathType Leaf) -and
            (Test-Path -LiteralPath (Join-Path $child.FullName 'catalog.json') -PathType Leaf)) {
            [void]$candidates.Add($child.FullName)
        }
    }
    if ($candidates.Count -ne 1) { Fail "Expected exactly one unzipped $area Snapshot; found $($candidates.Count)." }
    $snapshotRoot = $candidates[0]
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
    $datasets = New-Object System.Collections.ArrayList
    $names = @{}
    foreach ($section in @($catalog.sections)) {
        foreach ($dataset in @($section.datasets)) {
            if ([string]::IsNullOrWhiteSpace([string]$dataset.name) -or $names.ContainsKey([string]$dataset.name)) {
                Fail 'Snapshot catalog contains an invalid or duplicate dataset.'
            }
            $names[[string]$dataset.name] = $dataset
            [void]$datasets.Add($dataset)
        }
    }
    Assert-SessionSnapshotIdentity $session $area $manifest $catalog
    return [pscustomobject]@{
        Session = $session
        Area = $area
        Root = $snapshotRoot
        Manifest = $manifest
        Catalog = $catalog
        Members = $members
        Datasets = @($datasets)
        ByName = $names
    }
}

function Resolve-Member([string]$Root, [string]$RelativePath, $Members) {
    Assert-SafeSnapshotMemberPath $RelativePath
    if (-not $Members.ContainsKey($RelativePath)) {
        Fail "Snapshot member $RelativePath is missing from the manifest inventory."
    }
    $rootFull = [IO.Path]::GetFullPath($Root).TrimEnd([IO.Path]::DirectorySeparatorChar)
    $candidate = [IO.Path]::GetFullPath((Join-Path $rootFull ($RelativePath.Replace('/', [IO.Path]::DirectorySeparatorChar))))
    if (-not $candidate.StartsWith($rootFull + [IO.Path]::DirectorySeparatorChar, [StringComparison]::Ordinal)) {
        Fail 'Snapshot member escapes its Snapshot directory.'
    }
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

function Assert-SessionSnapshotIdentity([string]$Session, [string]$Area, $Manifest, $Catalog) {
    if ($Area -eq 'metadata') {
        $sessionTenant = Split-Path -Leaf (Split-Path -Parent $Session)
        if (-not (Test-Property $Manifest 'tenant_code') -or $Manifest.tenant_code -isnot [string] -or
            (Normalize-Value 'metadata' 'tenant_code' $Manifest.tenant_code) -cne
            (Normalize-Value 'metadata' 'tenant_code' $sessionTenant)) {
            Fail 'Metadata Snapshot Tenant Code does not match the session Tenant Code.'
        }
        return
    }

    $catalogModel = Get-Property $Catalog 'model'
    $modelId = Get-Property $Manifest 'model_id'
    $modelName = Get-Property $Manifest 'model_name'
    $modelRevision = Get-Property $Manifest 'model_revision'
    if ($null -eq $catalogModel -or $catalogModel -is [Array] -or
        -not (Test-Property $catalogModel 'model_id') -or
        -not (Test-Property $catalogModel 'model_name') -or
        -not (Test-Property $catalogModel 'model_revision') -or
        ($modelId -isnot [int] -and $modelId -isnot [long]) -or
        [long]$modelId -le 0 -or [long]$modelId -gt 9007199254740991 -or
        $modelName -isnot [string] -or [string]::IsNullOrWhiteSpace([string]$modelName) -or
        ([string]$modelName).Length -gt 255 -or
        ($modelRevision -isnot [int] -and $modelRevision -isnot [long]) -or
        [long]$modelRevision -lt 0 -or
        [long](Get-Property $catalogModel 'model_id') -ne [long]$modelId -or
        [string](Get-Property $catalogModel 'model_name') -cne [string]$modelName -or
        [long](Get-Property $catalogModel 'model_revision') -ne [long]$modelRevision) {
        Fail 'Model identity does not match between Snapshot manifest and catalog.'
    }

    $state = Read-SessionState $Session
    if (Test-Property $state 'model') {
        $binding = @($state.model)
        if ([long]$binding[0] -ne [long]$modelId) {
            Fail "Session is bound to Model $($binding[0]); start a new session for Model $modelId."
        }
        if ([string]$binding[1] -cne [string]$modelName) {
            Set-Property $state 'model' @([long]$modelId, [string]$modelName)
            Write-JsonAtomic (Join-Path $Session 'session.json') $state
        }
    }
    else {
        Set-Property $state 'model' @([long]$modelId, [string]$modelName)
        Write-JsonAtomic (Join-Path $Session 'session.json') $state
    }
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

function Describe-Dataset([hashtable]$Options) {
    $snapshot = Find-Snapshot $Options
    $datasetName = Require-Option $Options 'dataset'
    if (-not $snapshot.ByName.ContainsKey($datasetName)) { Fail "Unknown Snapshot dataset: $datasetName." }
    $dataset = $snapshot.ByName[$datasetName]
    if (-not (Test-Property $dataset 'schema_file')) { Fail "$datasetName schema path is missing." }
    $schema = Read-Json (Resolve-Member $snapshot.Root ([string]$dataset.schema_file) $snapshot.Members) "$datasetName schema"
    return [ordered]@{
        dataset = $datasetName
        count = [int]$dataset.row_count
        canonical_key = @($dataset.canonical_key)
        schema = $schema
    }
}

function Select-Snapshot([hashtable]$Options) {
    $snapshot = Find-Snapshot $Options
    $selection = Select-Records $Options $snapshot
    return [ordered]@{
        dataset = [string]$selection.Dataset.name
        count = @($selection.Records).Count
        truncated = [bool]$selection.Truncated
        records = @($selection.Records)
    }
}

function Add-Task([hashtable]$Options) {
    $session = Resolve-Session $Options
    $area = Require-Option $Options 'area'
    if ($script:TaskAreas -cnotcontains $area) { Fail '--area must be metadata, model, code, or validation.' }
    $title = Require-Option $Options 'title'
    if ($title -ne $title.Trim() -or $title.Length -gt 120) {
        Fail '--title must be a trimmed string of at most 120 characters.'
    }
    $plan = @(Parse-TaskPlan (Require-Option $Options 'plan'))
    $state = Read-SessionState $session
    if ($null -eq (Get-Property $state 'current') -and $script:Areas -ccontains $area) {
        $live = Get-PendingSummary (Get-PendingDirectory $session $area)
        if ($live.Files -gt 0) {
            Fail "The live $area Local Change Set is not task-bound; use task-stash/task-restore before starting another task."
        }
    }
    [long]$highest = 0
    foreach ($task in @($state.tasks)) {
        [long]$numeric = 0
        if ([long]::TryParse([string]$task[0], [ref]$numeric) -and $numeric -le 9007199254740991) {
            $highest = [Math]::Max($highest, $numeric)
        }
    }
    $next = $highest + 1
    $taskId = if ($next -lt 100) { $next.ToString('00') } else { $next.ToString() }
    $taskState = if ($null -eq $state.current) { 'doing' } else { 'queued' }
    $planPath = Join-Path (Join-Path $session 'tasks') ($taskId + '.json')
    if (Test-Path -LiteralPath $planPath) { Fail "Task plan $taskId already exists." }
    Write-JsonAtomic $planPath @($plan)
    $tasks = New-Object System.Collections.ArrayList
    foreach ($task in @($state.tasks)) { [void]$tasks.Add(@($task)) }
    [void]$tasks.Add(@($taskId, $area, $title, $taskState))
    Set-Property $state 'tasks' @($tasks)
    if ($taskState -eq 'doing') { Set-Property $state 'current' $taskId }
    Write-JsonAtomic (Join-Path $session 'session.json') $state
    return [ordered]@{ task = $taskId; state = $taskState; plan_digest = (Get-FileDigest $planPath) }
}

function Update-TaskPlan([hashtable]$Options) {
    $session = Resolve-Session $Options
    $taskId = Require-Option $Options 'task'
    if ($taskId -notmatch '^\d{2,}$') { Fail '--task must be a numeric task ID.' }
    $expected = Require-Option $Options 'expected-digest'
    if ($expected -notmatch '^[0-9a-f]{64}$') { Fail '--expected-digest must be a lowercase SHA-256 digest.' }
    $state = Read-SessionState $session
    $task = $null
    foreach ($candidate in @($state.tasks)) { if ($candidate[0] -eq $taskId) { $task = $candidate; break } }
    if ($null -eq $task) { Fail "Task $taskId does not exist." }
    if (@('queued', 'todo', 'doing', 'waiting', 'review') -notcontains [string]$task[3]) {
        Fail "Task plan cannot change in $($task[3]) state."
    }
    $planPath = Join-Path (Join-Path $session 'tasks') ($taskId + '.json')
    $actual = Get-FileDigest $planPath
    if ($actual -ne $expected) { Fail "Task plan digest conflict: expected $expected, found $actual." }
    $plan = @(Parse-TaskPlan (Require-Option $Options 'plan'))
    Write-JsonAtomic $planPath @($plan)
    return [ordered]@{ task = $taskId; plan_digest = (Get-FileDigest $planPath) }
}

function Set-DraftCache([hashtable]$Options) {
    $session = Resolve-Session $Options
    $area = Require-Option $Options 'area'
    if ($script:Areas -cnotcontains $area) { Fail '--area must be metadata or model.' }
    $state = Read-SessionState $session
    $cache = [ordered]@{}
    if (Test-Property $state 'cs') {
        $existingCache = Get-Property $state 'cs'
        foreach ($name in @(Get-PropertyNames $existingCache)) { $cache[$name] = Get-Property $existingCache $name }
    }
    if ($Options.ContainsKey('clear')) {
        if ($Options['clear'] -ne 'true') { Fail '--clear must be true when supplied.' }
        if ($Options.ContainsKey('id') -or $Options.ContainsKey('revision') -or $Options.ContainsKey('status')) {
            Fail '--clear cannot be combined with --id, --revision, or --status.'
        }
        if (-not $cache.Contains($area)) { Fail "No cached $area server draft exists." }
        $existing = @($cache[$area])
        $expectedId = if ($Options.ContainsKey('expected-id')) { [string]$Options['expected-id'] } else { '' }
        $expectedRevisionText = if ($Options.ContainsKey('expected-revision')) { [string]$Options['expected-revision'] } else { '' }
        [long]$expectedRevision = 0
        $validExpectedRevision = $expectedRevisionText -match '^\d+$' -and
            [long]::TryParse($expectedRevisionText, [ref]$expectedRevision) -and
            $expectedRevision -le 9007199254740991
        if ($expectedId -notmatch '^[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}$' -or
            -not $validExpectedRevision) {
            Fail '--expected-id and --expected-revision must identify a valid cached server draft.'
        }
        if ($expectedId.ToLowerInvariant() -cne [string]$existing[0] -or
            $expectedRevision -ne [long]$existing[1]) {
            Fail '--expected-id and --expected-revision must match the exact cached server draft.'
        }
        if ([string](Get-Property $state 'current') -cne [string]$existing[3]) {
            Fail "Cached $area server draft belongs to task $($existing[3]); make it current before clearing."
        }
        [void]$cache.Remove($area)
        if ($cache.Count -eq 0) { Remove-Property $state 'cs' }
        else { Set-Property $state 'cs' $cache }
        Write-JsonAtomic (Join-Path $session 'session.json') $state
        return [ordered]@{ area = $area; draft = $null }
    }
    $idText = Require-Option $Options 'id'
    try { $id = [Guid]::ParseExact($idText, 'D').ToString('D') }
    catch { Fail '--id must be a UUID.' }
    $revisionText = Require-Option $Options 'revision'
    [long]$revision = 0
    if ($revisionText -notmatch '^\d+$' -or -not [long]::TryParse($revisionText, [ref]$revision) -or
        $revision -gt 9007199254740991) {
        Fail '--revision must be a nonnegative integer.'
    }
    $status = Require-Option $Options 'status'
    if (@('active', 'validated') -cnotcontains $status) { Fail '--status must be active or validated.' }
    $task = $null
    foreach ($candidate in @($state.tasks)) {
        if ([string]$candidate[0] -ceq [string](Get-Property $state 'current')) { $task = $candidate; break }
    }
    if ($null -eq $task -or [string]$task[1] -cne $area) {
        Fail "A current $area task is required to cache a server draft."
    }
    $digest = Get-AcceptedWorkspaceDigest $session $task $area
    $draft = @($id.ToLowerInvariant(), $revision, $status, [string]$task[0], $digest)
    if ($cache.Contains($area)) {
        $existing = @($cache[$area])
        if ([string]$existing[0] -cne [string]$draft[0] -or
            [string]$existing[3] -cne [string]$draft[3]) {
            Fail 'Cached server draft ID and task are immutable; archive and clear it first.'
        }
        if ([long]$revision -lt [long]$existing[1]) { Fail 'Cached server draft revision cannot decrease.' }
        if ([string]$existing[2] -ceq 'validated' -and $status -ceq 'active' -and
            [long]$revision -eq [long]$existing[1]) {
            Fail 'Cached server draft status cannot regress at the same revision.'
        }
        if ([string]$existing[4] -cne $digest -and
            ($revision -le [long]$existing[1] -or $status -cne 'active')) {
            Fail 'A new accepted digest requires a newer active Stage revision for the same server draft.'
        }
    }
    $cache[$area] = $draft
    Set-Property $state 'cs' $cache
    Write-JsonAtomic (Join-Path $session 'session.json') $state
    return [ordered]@{ area = $area; draft = $draft }
}

function Set-TaskState([hashtable]$Options) {
    $session = Resolve-Session $Options
    $taskId = if ($Options.ContainsKey('task')) { [string]$Options['task'] } else { '' }
    if ($taskId -notmatch '^\d{2,}$') { Fail '--task must be a numeric task ID.' }
    $nextState = if ($Options.ContainsKey('state')) { [string]$Options['state'] } else { '' }
    if ($script:Transitions.Keys -cnotcontains $nextState) { Fail '--state is invalid.' }
    $state = Read-SessionState $session
    $found = $null
    foreach ($task in @($state.tasks)) { if ($task[0] -eq $taskId) { $found = $task; break } }
    if ($null -eq $found) { Fail "Task $taskId does not exist." }
    $previous = [string]$found[3]
    $area = [string]$found[1]
    if ($script:Areas -ccontains $area -and @('waiting', 'done', 'cancelled') -ccontains $nextState -and
        [string](Get-Property $state 'current') -ceq [string]$found[0]) {
        $live = Get-PendingSummary (Get-PendingDirectory $session $area)
        if ($live.Files -gt 0) {
            Fail "Task $($found[0]) has live pending work; use task-stash instead of $nextState."
        }
        if (Test-Property $state 'cs') {
            $cache = Get-Property $state 'cs'
            if (Test-Property $cache $area) {
                $draft = Get-Property $cache $area
                if ([string]$draft[3] -ceq [string]$found[0]) {
                    Fail "Task $($found[0]) has a cached server draft; archive it explicitly and clear the cache first."
                }
            }
        }
    }
    if ($script:Transitions[$previous] -cnotcontains $nextState) { Fail "Task transition $previous -> $nextState is not allowed." }
    if ($nextState -eq 'doing' -and $null -ne $state.current -and $state.current -ne $taskId) {
        Fail "Task $($state.current) is current; move it to waiting or terminal state first."
    }
    if ($nextState -ceq 'doing' -and $null -eq (Get-Property $state 'current') -and $script:Areas -ccontains $area) {
        if (Test-Path -LiteralPath (Get-TaskStashDirectory $session $found)) {
            Fail "Task $($found[0]) has stashed work; use task-restore."
        }
        $live = Get-PendingSummary (Get-PendingDirectory $session $area)
        if ($live.Files -gt 0) {
            Fail "The live $area Local Change Set belongs to another task; use task-stash/task-restore."
        }
    }
    $appliedAcceptance = $null
    if ($nextState -eq 'staged') {
        if ($script:Areas -cnotcontains $area) { Fail 'Only Metadata or Model tasks can enter staged state.' }
        if ((Test-Property $state 'stale') -and @($state.stale) -ccontains $area) {
            Fail "$area Snapshot is stale; refresh it before Stage."
        }
        $changeDirectory = Get-PendingDirectory $session $area
        if (@(Get-ChildItem -LiteralPath $changeDirectory -Force).Count -eq 0) { Fail 'Local Change Set is empty; there is nothing to Stage.' }
        $acceptancePath = Join-Path (Join-Path $session 'tasks') ($taskId + '.accept.json')
        if (-not (Test-Path -LiteralPath $acceptancePath -PathType Leaf)) { Fail 'Task has no accepted digest; review and accept first.' }
        $acceptance = @(Read-Json $acceptancePath 'Task acceptance')
        $actual = Get-WorkspaceDigest ([pscustomobject]@{ ChangeDirectory = $changeDirectory })
        if ($acceptance.Count -lt 2 -or $acceptance[0] -isnot [string] -or
            [string]$acceptance[0] -cnotmatch '^[0-9a-f]{64}$' -or [string]$acceptance[0] -cne $actual -or
            ($previous -ceq 'ready' -and [string]$acceptance[1] -cne 'valid') -or
            ($previous -ceq 'overridden' -and [string]$acceptance[1] -cne 'override')) {
            Fail 'Task accepted digest does not match the exact local Change Set.'
        }
        [void](Assert-CachedDraftBinding $state $found $area $actual)
    }
    if ($nextState -ceq 'applied' -and $script:Areas -ccontains $area) {
        $acceptancePath = Join-Path (Join-Path $session 'tasks') ($taskId + '.accept.json')
        $appliedAcceptance = @(Read-Json $acceptancePath 'Task acceptance')
        $changeDirectory = Get-PendingDirectory $session $area
        $actual = Get-WorkspaceDigest ([pscustomobject]@{ ChangeDirectory = $changeDirectory })
        if ($appliedAcceptance.Count -lt 2 -or [string]$appliedAcceptance[0] -cne $actual -or
            @('valid', 'override') -cnotcontains [string]$appliedAcceptance[1]) {
            Fail 'Task accepted digest does not match the exact local Change Set.'
        }
        [void](Assert-CachedDraftBinding $state $found $area $actual $true)
    }
    $found[3] = $nextState
    if ($nextState -eq 'doing') { Set-Property $state 'current' $taskId }
    elseif (@('waiting', 'applied', 'done', 'cancelled') -contains $nextState) {
        if ($state.current -eq $taskId) { Set-Property $state 'current' $null }
    }
    else { Set-Property $state 'current' $taskId }
    if ($nextState -eq 'applied' -and $script:Areas -ccontains $area) {
        $snapshotIndex = if ([string]$appliedAcceptance[1] -ceq 'override') { 3 } else { 2 }
        if ($appliedAcceptance.Count -le $snapshotIndex -or $appliedAcceptance[$snapshotIndex] -isnot [string] -or
            ([string]$appliedAcceptance[$snapshotIndex]).Length -eq 0) {
            Fail 'Task acceptance does not identify its input Snapshot.'
        }
        $revision = if ($appliedAcceptance.Count -gt ($snapshotIndex + 1)) { $appliedAcceptance[$snapshotIndex + 1] } else { $null }
        Write-JsonAtomic (Join-Path (Join-Path $session 'tasks') ($taskId + '.applied.json')) @(
            $area, [string]$appliedAcceptance[$snapshotIndex], $revision
        )
        $stale = New-Object System.Collections.ArrayList
        if (Test-Property $state 'stale') { foreach ($item in @($state.stale)) { [void]$stale.Add([string]$item) } }
        if ($stale -cnotcontains $area) { [void]$stale.Add($area) }
        Set-Property $state 'stale' @($stale | Sort-Object)
        $serverDraftCache = if (Test-Property $state 'cs') { Get-Property $state 'cs' } else { $null }
        if ($null -ne $serverDraftCache -and (Test-Property $serverDraftCache $area)) {
            $remaining = [ordered]@{}
            foreach ($name in @(Get-PropertyNames $serverDraftCache)) {
                if ($name -cne $area) { $remaining[$name] = Get-Property $serverDraftCache $name }
            }
            if ($remaining.Count -eq 0) { Remove-Property $state 'cs' }
            else { Set-Property $state 'cs' $remaining }
        }
    }
    Write-JsonAtomic (Join-Path $session 'session.json') $state
    return [ordered]@{ task = $taskId; state = $nextState }
}

function Stash-Task([hashtable]$Options) {
    $session = Resolve-Session $Options
    $taskId = if ($Options.ContainsKey('task')) { [string]$Options['task'] } else { '' }
    if ($taskId -notmatch '^\d{2,}$') { Fail '--task must be a numeric task ID.' }
    $expected = if ($Options.ContainsKey('expected-digest')) { [string]$Options['expected-digest'] } else { '' }
    if ($expected -cnotmatch '^[0-9a-f]{64}$') { Fail '--expected-digest must be a lowercase SHA-256 digest.' }
    $state = Read-SessionState $session
    $task = $null
    foreach ($candidate in @($state.tasks)) { if ([string]$candidate[0] -ceq $taskId) { $task = $candidate; break } }
    if ($null -eq $task) { Fail "Task $taskId does not exist." }
    if ([string](Get-Property $state 'current') -cne [string]$task[0]) {
        Fail "Task $($task[0]) must be current before it can be stashed."
    }
    $area = [string]$task[1]
    if ($script:Areas -cnotcontains $area) { Fail 'Only Metadata or Model tasks can stash a Local Change Set.' }
    if (@('doing', 'review', 'ready', 'overridden', 'staged') -cnotcontains [string]$task[3]) {
        Fail "Task $($task[0]) cannot be stashed in $($task[3]) state."
    }
    if (Test-Property $state 'cs') {
        $cache = Get-Property $state 'cs'
        if (Test-Property $cache $area) {
            Fail "Archive the cached $area server draft and clear its cache before task-stash."
        }
    }

    $live = Get-PendingDirectory $session $area
    $summary = Test-PortablePendingSet $live
    if ($summary.Files -eq 0) { Fail 'Local Change Set is empty; there is nothing to stash.' }
    if ([string]$summary.Digest -cne $expected) {
        Fail "Local Change Set digest conflict: expected $expected, found $($summary.Digest)."
    }
    $stash = Get-TaskStashDirectory $session $task
    $taskDirectory = Split-Path -Parent $stash
    if (Test-Path -LiteralPath $taskDirectory) {
        [void](Resolve-RegularDirectory $taskDirectory 'Task stash parent')
    }
    else { [void][IO.Directory]::CreateDirectory($taskDirectory) }
    if (Test-Path -LiteralPath $stash) { Fail "Task $($task[0]) already has a $area stash." }

    $acceptancePath = Join-Path (Join-Path $session 'tasks') ($taskId + '.accept.json')
    $acceptance = $null
    if (Test-Path -LiteralPath $acceptancePath) {
        $acceptanceItem = Get-Item -LiteralPath $acceptancePath -Force -ErrorAction Stop
        if ($acceptanceItem.PSIsContainer -or ($acceptanceItem.Attributes -band [IO.FileAttributes]::ReparsePoint)) {
            Fail 'Task acceptance must be a regular file.'
        }
        $acceptance = [IO.File]::ReadAllBytes($acceptanceItem.FullName)
    }
    [IO.Directory]::Move($live, $stash)
    try {
        [void][IO.Directory]::CreateDirectory($live)
        if ($null -ne $acceptance) { [IO.File]::Delete($acceptancePath) }
        $task[3] = 'waiting'
        Set-Property $state 'current' $null
        Write-JsonAtomic (Join-Path $session 'session.json') $state
    }
    catch {
        if (Test-Path -LiteralPath $live) {
            $liveItem = Get-Item -LiteralPath $live -Force -ErrorAction Stop
            if ($liveItem.PSIsContainer -and -not ($liveItem.Attributes -band [IO.FileAttributes]::ReparsePoint) -and
                @(Get-ChildItem -LiteralPath $liveItem.FullName -Force).Count -eq 0) {
                [IO.Directory]::Delete($liveItem.FullName)
            }
        }
        if ((Test-Path -LiteralPath $stash) -and -not (Test-Path -LiteralPath $live)) {
            $stashItem = Get-Item -LiteralPath $stash -Force -ErrorAction Stop
            if ($stashItem.PSIsContainer -and -not ($stashItem.Attributes -band [IO.FileAttributes]::ReparsePoint)) {
                [IO.Directory]::Move($stashItem.FullName, $live)
            }
        }
        if ($null -ne $acceptance -and -not (Test-Path -LiteralPath $acceptancePath)) {
            [IO.File]::WriteAllBytes($acceptancePath, $acceptance)
        }
        throw
    }
    return [ordered]@{ task = [string]$task[0]; area = $area; digest = [string]$summary.Digest; files = [int]$summary.Files }
}

function Restore-Task([hashtable]$Options) {
    $session = Resolve-Session $Options
    $taskId = if ($Options.ContainsKey('task')) { [string]$Options['task'] } else { '' }
    if ($taskId -notmatch '^\d{2,}$') { Fail '--task must be a numeric task ID.' }
    $expected = if ($Options.ContainsKey('expected-digest')) { [string]$Options['expected-digest'] } else { '' }
    if ($expected -cnotmatch '^[0-9a-f]{64}$') { Fail '--expected-digest must be a lowercase SHA-256 digest.' }
    $state = Read-SessionState $session
    $task = $null
    foreach ($candidate in @($state.tasks)) { if ([string]$candidate[0] -ceq $taskId) { $task = $candidate; break } }
    if ($null -eq $task) { Fail "Task $taskId does not exist." }
    $current = Get-Property $state 'current'
    if ($null -ne $current) { Fail "Task $current is current; finish or stash it first." }
    if ([string]$task[3] -cne 'waiting') { Fail "Task $($task[0]) must be waiting before restore." }
    $area = [string]$task[1]
    if ($script:Areas -cnotcontains $area) { Fail 'Only Metadata or Model tasks can restore a Local Change Set.' }
    if ((Test-Property $state 'stale') -and @($state.stale) -ccontains $area) {
        Fail "$area Snapshot is stale; replace it before task-restore."
    }
    if ((Test-Property $state 'cs') -and (Test-Property (Get-Property $state 'cs') $area)) {
        Fail "Clear the cached $area server draft before task-restore."
    }

    $snapshot = Find-Snapshot @{ session = $session; area = $area }
    $state = Read-SessionState $session
    $task = $null
    foreach ($candidate in @($state.tasks)) { if ([string]$candidate[0] -ceq $taskId) { $task = $candidate; break } }
    if ($null -ne (Get-Property $state 'current') -or $null -eq $task -or [string]$task[3] -cne 'waiting') {
        Fail 'Session task state changed during restore; retry from status.'
    }
    $live = Get-PendingDirectory $session $area
    if ((Get-PendingSummary $live).Files -ne 0) {
        Fail "The live $area Local Change Set must be empty before task-restore."
    }
    $stash = Get-TaskStashDirectory $session $task
    if (-not (Test-Path -LiteralPath $stash)) { Fail "Task $($task[0]) has no $area stash." }
    $stashItem = Get-Item -LiteralPath $stash -Force -ErrorAction Stop
    if (-not $stashItem.PSIsContainer -or ($stashItem.Attributes -band [IO.FileAttributes]::ReparsePoint)) {
        Fail 'Task stash must be a regular directory.'
    }
    $snapshot | Add-Member -NotePropertyName State -NotePropertyValue $state
    $snapshot | Add-Member -NotePropertyName Current -NotePropertyValue $task
    $snapshot | Add-Member -NotePropertyName ChangeDirectory -NotePropertyValue $stashItem.FullName
    [void](Read-Pending $snapshot)
    $summary = Get-PendingSummary $stashItem.FullName
    if ($summary.Files -eq 0) { Fail 'Task stash is empty.' }
    if ([string]$summary.Digest -cne $expected) {
        Fail "Task stash digest conflict: expected $expected, found $($summary.Digest)."
    }

    [IO.Directory]::Delete($live)
    try {
        [IO.Directory]::Move($stashItem.FullName, $live)
        $acceptancePath = Join-Path (Join-Path $session 'tasks') ($taskId + '.accept.json')
        if (Test-Path -LiteralPath $acceptancePath) { [IO.File]::Delete($acceptancePath) }
        $task[3] = 'doing'
        Set-Property $state 'current' ([string]$task[0])
        Write-JsonAtomic (Join-Path $session 'session.json') $state
    }
    catch {
        if ((Test-Path -LiteralPath $live) -and -not (Test-Path -LiteralPath $stash)) {
            $liveItem = Get-Item -LiteralPath $live -Force -ErrorAction Stop
            if ($liveItem.PSIsContainer -and -not ($liveItem.Attributes -band [IO.FileAttributes]::ReparsePoint)) {
                [IO.Directory]::Move($liveItem.FullName, $stash)
            }
        }
        if (-not (Test-Path -LiteralPath $live)) { [void][IO.Directory]::CreateDirectory($live) }
        throw
    }
    return [ordered]@{ task = [string]$task[0]; area = $area; digest = [string]$summary.Digest; files = [int]$summary.Files }
}

function Get-ChangeContext([hashtable]$Options) {
    $snapshot = Find-Snapshot $Options
    $state = Read-SessionState $snapshot.Session
    if ((Test-Property $state 'stale') -and @($state.stale) -contains $snapshot.Area) {
        Fail "$($snapshot.Area) Snapshot is stale; replace it before local mutation."
    }
    $current = $null
    foreach ($task in @($state.tasks)) { if ($task[0] -eq $state.current) { $current = $task; break } }
    if ($null -eq $current -or $current[1] -ne $snapshot.Area) {
        Fail "A current $($snapshot.Area) task is required before local mutation."
    }
    $directory = Resolve-RegularDirectory (Join-Path $snapshot.Session ($snapshot.Area + '-change-set')) 'Local Change Set'
    $snapshot | Add-Member -NotePropertyName State -NotePropertyValue $state
    $snapshot | Add-Member -NotePropertyName Current -NotePropertyValue $current
    $snapshot | Add-Member -NotePropertyName ChangeDirectory -NotePropertyValue $directory
    return $snapshot
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

function Get-PendingDirectory([string]$Session, [string]$Area) {
    return Resolve-RegularDirectory (Join-Path $Session ($Area + '-change-set')) 'Local Change Set'
}

function Get-PendingSummary([string]$Directory) {
    $items = @(Get-ChildItem -LiteralPath $Directory -Force)
    [long]$bytes = 0
    foreach ($item in $items) {
        if ($item.PSIsContainer -or ($item.Attributes -band [IO.FileAttributes]::ReparsePoint) -or
            -not $item.Name.EndsWith('.json', [StringComparison]::Ordinal)) {
            Fail 'Local Change Set contains an unsupported entry.'
        }
        $bytes += [long]$item.Length
    }
    $digest = Get-WorkspaceDigest ([pscustomobject]@{ ChangeDirectory = $Directory })
    return [pscustomobject]@{ Files = $items.Count; Bytes = $bytes; Digest = $digest }
}

function Get-TaskStashDirectory([string]$Session, $Task) {
    return Join-Path (Join-Path (Join-Path $Session 'tasks') ([string]$Task[0])) ([string]$Task[1] + '-change-set')
}

function Get-AcceptedWorkspaceDigest([string]$Session, $Task, [string]$Area) {
    if (@('ready', 'overridden', 'staged') -cnotcontains [string]$Task[3]) {
        Fail 'Current task must have a digest-bound acceptance before caching a server draft.'
    }
    $acceptancePath = Join-Path (Join-Path $Session 'tasks') ([string]$Task[0] + '.accept.json')
    if (-not (Test-Path -LiteralPath $acceptancePath -PathType Leaf)) {
        Fail 'Task has no accepted digest; review and accept first.'
    }
    $acceptance = @(Read-Json $acceptancePath 'Task acceptance')
    $directory = Get-PendingDirectory $Session $Area
    $actual = Get-WorkspaceDigest ([pscustomobject]@{ ChangeDirectory = $directory })
    if ($acceptance.Count -lt 2 -or [string]$acceptance[0] -cne $actual -or
        ([string]$Task[3] -ceq 'ready' -and [string]$acceptance[1] -cne 'valid') -or
        ([string]$Task[3] -ceq 'overridden' -and [string]$acceptance[1] -cne 'override') -or
        ([string]$Task[3] -ceq 'staged' -and @('valid', 'override') -cnotcontains [string]$acceptance[1])) {
        Fail 'Task accepted digest does not match the exact local Change Set.'
    }
    return $actual
}

function Assert-CachedDraftBinding($State, $Task, [string]$Area, [string]$Digest, [bool]$RequireValidated = $false) {
    $cache = if (Test-Property $State 'cs') { Get-Property $State 'cs' } else { $null }
    if ($null -eq $cache -or -not (Test-Property $cache $Area)) {
        Fail "Cache the $Area server draft before continuing."
    }
    $draft = Get-Property $cache $Area
    if ([string]$draft[3] -cne [string]$Task[0]) {
        Fail "Cached $Area server draft belongs to task $($draft[3]), not task $($Task[0])."
    }
    if ([string]$draft[4] -cne $Digest) {
        Fail 'Cached server draft is bound to a different accepted local digest.'
    }
    if ($RequireValidated -and [string]$draft[2] -cne 'validated') {
        Fail 'Cached server draft must be validated before marking the task applied.'
    }
    return ,$draft
}

function Test-BoundServerDraftForReconcile($State, $Task, [string]$Area, [string]$Digest) {
    $cache = if (Test-Property $State 'cs') { Get-Property $State 'cs' } else { $null }
    if ($null -eq $cache -or -not (Test-Property $cache $Area)) {
        Fail "Cache the $Area server draft before reconciliation."
    }
    $draft = Get-Property $cache $Area
    if ([string]$draft[3] -cne [string]$Task[0]) {
        Fail "Cached $Area server draft belongs to task $($draft[3]), not task $($Task[0])."
    }
    return ([string]$draft[4] -ceq $Digest)
}

function Test-PortablePendingSet([string]$Directory) {
    $summary = Get-PendingSummary $Directory
    foreach ($item in @(Get-ChildItem -LiteralPath $Directory -Force)) {
        $raw = [IO.File]::ReadAllText($item.FullName, [Text.Encoding]::UTF8)
        try { $records = ConvertFrom-GdsJson $raw }
        catch { Fail "$($item.Name) pending file is not valid JSON." }
        if ($records -isnot [Array]) {
            Fail "$($item.Name) pending file must contain a JSON array of complete records."
        }
        foreach ($record in @($records)) {
            if ($null -eq $record -or $record -is [Array] -or $record -is [string] -or $record -is [ValueType]) {
                Fail "$($item.Name) pending file must contain a JSON array of complete records."
            }
        }
    }
    return $summary
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

function Normalize-ReadinessValue($Value) {
    if ($Value -is [string]) { return ConvertTo-Casefold ($Value.Trim([char]0x20)) }
    return $Value
}

function Get-ReadinessObjectKey($Record) {
    $values = New-Object System.Collections.ArrayList
    foreach ($field in $script:PhysicalObjectFields) {
        [void]$values.Add((Normalize-ReadinessValue (Get-Property $Record $field)))
    }
    return ConvertTo-GdsJson @($values)
}

function Test-ReadinessActive([string]$DatasetName, $Record) {
    if (Test-Property $Record 'is_active') {
        $active = Get-Property $Record 'is_active'
        if ($active -is [bool]) { return $active }
    }
    if ($script:ReadinessStatusFields.ContainsKey($DatasetName)) {
        return [string](Get-Property $Record $script:ReadinessStatusFields[$DatasetName]) -ceq 'active'
    }
    return $true
}

function Get-ReadinessRows($Snapshot, [string]$DatasetName) {
    if ($null -eq $Snapshot -or -not $Snapshot.ByName.ContainsKey($DatasetName)) { return @() }
    $active = New-Object System.Collections.ArrayList
    foreach ($record in @(Read-SnapshotRecords $Snapshot $Snapshot.ByName[$DatasetName])) {
        if (Test-ReadinessActive $DatasetName $record) { [void]$active.Add($record) }
    }
    return @($active)
}

function New-ReadinessIssues {
    return [pscustomobject]@{
        Counts = [ordered]@{}
        Examples = (New-Object System.Collections.ArrayList)
        Truncated = $false
    }
}

function Add-ReadinessIssue($Issues, [string]$Code, $Example = $null, [int]$Amount = 1) {
    if ($Issues.Counts.Contains($Code)) { $Issues.Counts[$Code] = [int]$Issues.Counts[$Code] + $Amount }
    else { $Issues.Counts[$Code] = $Amount }
    if ($null -ne $Example) {
        if ($Issues.Examples.Count -lt 10) {
            $entry = New-Object object[] 2
            $entry[0] = $Code
            $entry[1] = $Example
            [void]$Issues.Examples.Add($entry)
        }
        else { $Issues.Truncated = $true }
    }
}

function Test-ReadinessIssue($Issues, [string]$Code) {
    return $Issues.Counts.Contains($Code)
}

function Get-ReadinessIssueOutput($Issues) {
    $blockers = New-Object System.Collections.ArrayList
    foreach ($code in $Issues.Counts.Keys) { [void]$blockers.Add(@([string]$code, [int]$Issues.Counts[$code])) }
    return [pscustomobject]@{ Blockers = @($blockers); Examples = @($Issues.Examples); Truncated = [bool]$Issues.Truncated }
}

function Get-ActiveMetadataObjects($Metadata, [string]$Zone) {
    return @(Get-ReadinessRows $Metadata ($Zone + '_object'))
}

function Get-ActiveMetadataAttributes($Metadata, [string]$Zone) {
    return @(Get-ReadinessRows $Metadata ($Zone + '_attribute'))
}

function Get-AttributeCountsByObject([array]$Records) {
    $counts = @{}
    foreach ($record in $Records) {
        $key = Get-ReadinessObjectKey $record
        if ($counts.ContainsKey($key)) { $counts[$key]++ } else { $counts[$key] = 1 }
    }
    return $counts
}

function Test-AuthoredMappingObject($Record) {
    foreach ($field in @(
        'artifact_type', 'artifact_generation_instructions', 'mapping_profile_key',
        'mapping_profile_version', 'mapping_package_document', 'object_mapping_transformation_document'
    )) {
        if ($null -eq (Get-Property $Record $field)) { return $false }
    }
    return $true
}

function Get-ModeledLayerReadiness($Model, [string]$Layer, $Issues) {
    $entityDataset = $Layer + '_entity'
    $attributeDataset = $Layer + '_attribute'
    $entityNameField = $Layer + '_entity_name'
    $entities = @(Get-ReadinessRows $Model $entityDataset)
    $attributes = @(Get-ReadinessRows $Model $attributeDataset)
    $counts = @{}
    foreach ($record in $attributes) {
        $key = [string](Normalize-ReadinessValue (Get-Property $record $entityNameField))
        if ($counts.ContainsKey($key)) { $counts[$key]++ } else { $counts[$key] = 1 }
    }
    if ($entities.Count -eq 0) { Add-ReadinessIssue $Issues 'upstream_missing' }
    foreach ($entity in $entities) {
        $name = Get-Property $entity $entityNameField
        $key = [string](Normalize-ReadinessValue $name)
        if (-not $counts.ContainsKey($key)) { Add-ReadinessIssue $Issues 'attributes_missing' @($name) }
    }
    return [pscustomobject]@{ Entities = $entities; Attributes = $attributes }
}

function Get-RegistrationReadiness($Metadata, $Model, [string]$Layer, [string]$Zone, $Issues) {
    $modeled = Get-ModeledLayerReadiness $Model $Layer $Issues
    $patterns = [ordered]@{}
    foreach ($record in @(Get-ActiveMetadataObjects $Metadata $Zone)) {
        $pattern = @(
            (Get-Property $record 'tenant_code'), (Get-Property $record 'system_code'),
            (Get-Property $record 'connection_code'), (Get-Property $record 'object_schema'),
            (Get-Property $record 'object_type_code')
        )
        $normalized = @($pattern | ForEach-Object { Normalize-ReadinessValue $_ })
        $patterns[(ConvertTo-GdsJson $normalized)] = $pattern
    }
    if ($patterns.Count -eq 0) { Add-ReadinessIssue $Issues 'destination_pattern_missing' }
    if ($patterns.Count -gt 1) {
        foreach ($pattern in $patterns.Values) { Add-ReadinessIssue $Issues 'destination_pattern_ambiguous' $pattern }
    }
    return [ordered]@{
        entities = @($modeled.Entities).Count
        attributes = @($modeled.Attributes).Count
        destination_patterns = $patterns.Count
    }
}

function Get-CompleteMappingLayer($Model, [string]$Layer, $Issues) {
    $entityType = $Layer + '_entity'
    $dependencies = @(Get-ReadinessRows $Model 'mapping_dependency' | Where-Object { $_.modeled_entity_type -ceq $entityType })
    $objects = @(Get-ReadinessRows $Model 'mapping_object' | Where-Object { $_.modeled_entity_type -ceq $entityType })
    $attributes = @(Get-ReadinessRows $Model 'mapping_attribute' | Where-Object { $_.modeled_entity_type -ceq $entityType })
    if ($dependencies.Count -eq 0 -or $objects.Count -eq 0 -or $attributes.Count -eq 0) {
        Add-ReadinessIssue $Issues 'applied_mapping_missing'
    }
    $unauthored = 0
    foreach ($record in $objects) { if (-not (Test-AuthoredMappingObject $record)) { $unauthored++ } }
    foreach ($record in $attributes) {
        if ($null -eq (Get-Property $record 'attribute_mapping_transformation_document')) { $unauthored++ }
    }
    if ($unauthored -gt 0) { Add-ReadinessIssue $Issues 'mapping_unauthored' $null $unauthored }
    return [pscustomobject]@{ Dependencies = $dependencies; Objects = $objects; Attributes = $attributes }
}

function Get-LogicalBuildReadiness($Metadata, $Model, $Issues) {
    $scope = @(Get-ReadinessRows $Model 'model_scope' | Where-Object {
        $eligible = Get-Property $_ 'is_bronze_source_eligible'
        $eligible -is [bool] -and $eligible
    })
    $objects = New-Object System.Collections.ArrayList
    $attributes = New-Object System.Collections.ArrayList
    foreach ($zone in @('source', 'bronze', 'silver', 'gold')) {
        foreach ($record in @(Get-ActiveMetadataObjects $Metadata $zone)) { [void]$objects.Add($record) }
        foreach ($record in @(Get-ActiveMetadataAttributes $Metadata $zone)) { [void]$attributes.Add($record) }
    }
    $objectKeys = @{}
    foreach ($record in $objects) { $objectKeys[(Get-ReadinessObjectKey $record)] = $true }
    $attributeCounts = Get-AttributeCountsByObject @($attributes)
    if ($scope.Count -eq 0) { Add-ReadinessIssue $Issues 'active_scope_missing' }
    foreach ($record in $scope) {
        $key = Get-ReadinessObjectKey $record
        $example = @($script:PhysicalObjectFields | ForEach-Object { Get-Property $record $_ })
        if (-not $objectKeys.ContainsKey($key)) { Add-ReadinessIssue $Issues 'catalog_object_missing' $example }
        elseif (-not $attributeCounts.ContainsKey($key)) { Add-ReadinessIssue $Issues 'attributes_missing' $example }
    }
    return [ordered]@{ scoped_objects = $scope.Count; catalog_objects = $objects.Count; attributes = $attributes.Count }
}

function Get-MappingReadiness($Metadata, $Model, [string]$Layer, [string]$Zone, $Issues) {
    $modeled = Get-ModeledLayerReadiness $Model $Layer $Issues
    $targets = @(Get-ActiveMetadataObjects $Metadata $Zone)
    $targetAttributes = @(Get-ActiveMetadataAttributes $Metadata $Zone)
    $attributeCounts = Get-AttributeCountsByObject $targetAttributes
    $targetEligibilityField = if ($Layer -eq 'logical') {
        'is_logical_mapping_target_eligible'
    } else {
        'is_dimensional_mapping_target_eligible'
    }
    $scope = @{}
    foreach ($record in @(Get-ReadinessRows $Model 'model_scope')) {
        $eligible = Get-Property $record $targetEligibilityField
        if ($eligible -is [bool] -and $eligible) { $scope[(Get-ReadinessObjectKey $record)] = $true }
    }
    $entityType = $Layer + '_entity'
    $existing = @(Get-ReadinessRows $Model 'mapping_object' | Where-Object { $_.modeled_entity_type -ceq $entityType })
    $mapped = @{}
    foreach ($record in $existing) { $mapped[(Get-ReadinessObjectKey $record)] = $true }
    if ($targets.Count -eq 0) { Add-ReadinessIssue $Issues 'registered_targets_missing' }
    foreach ($target in $targets) {
        $key = Get-ReadinessObjectKey $target
        $example = @($script:PhysicalObjectFields | ForEach-Object { Get-Property $target $_ })
        if (-not $scope.ContainsKey($key)) { Add-ReadinessIssue $Issues 'scope_missing' $example }
        if (-not $attributeCounts.ContainsKey($key)) { Add-ReadinessIssue $Issues 'attributes_missing' $example }
        if (-not $mapped.ContainsKey($key) -and @($modeled.Entities).Count -ne 1) {
            Add-ReadinessIssue $Issues 'target_association_required' $example
        }
    }
    $executableEligibilityField = if ($Layer -eq 'logical') {
        'is_bronze_source_eligible'
    } else {
        'is_dimensional_source_eligible'
    }
    $executable = @{}
    foreach ($record in @(Get-ReadinessRows $Model 'model_scope')) {
        $eligible = Get-Property $record $executableEligibilityField
        if ($eligible -is [bool] -and $eligible) { $executable[(Get-ReadinessObjectKey $record)] = $true }
    }
    $entityNameField = $Layer + '_entity_name'
    foreach ($entity in @($modeled.Entities)) {
        $found = $false
        $sources = Get-Property $entity 'sources'
        foreach ($source in @($sources)) {
            if ((Get-Property $source 'support_source_type') -ceq 'object' -and
                (Get-Property $source 'status') -ceq 'active' -and
                $executable.ContainsKey((Get-ReadinessObjectKey (Get-Property $source 'source_object')))) {
                $found = $true
                break
            }
        }
        if (-not $found) { Add-ReadinessIssue $Issues 'lineage_missing' @((Get-Property $entity $entityNameField)) }
    }
    Add-ReadinessIssue $Issues 'mapping_contract_unavailable'
    return [ordered]@{
        targets = $targets.Count
        attributes = $targetAttributes.Count
        modeled_entities = @($modeled.Entities).Count
        modeled_attributes = @($modeled.Attributes).Count
    }
}

function Get-CodeReadiness($Model, [string]$Layer, $Issues) {
    $mapping = Get-CompleteMappingLayer $Model $Layer $Issues
    Add-ReadinessIssue $Issues 'generator_contract_unavailable'
    return [ordered]@{
        packages = @($mapping.Objects).Count
        attributes = @($mapping.Attributes).Count
        dependencies = @($mapping.Dependencies).Count
    }
}

function Get-ReadinessPrompt($Issues) {
    $prompts = New-Object System.Collections.ArrayList
    if (Test-ReadinessIssue $Issues 'applied_mapping_missing') {
        [void]$prompts.Add('Complete and Apply the matching Logical or Dimensional Mapping, download a fresh Model Snapshot, then resume code generation.')
    }
    if (Test-ReadinessIssue $Issues 'scope_missing') {
        [void]$prompts.Add('Ask the authorized scope owner to add and apply this target to Model Scope, download a fresh Model Snapshot, replace model/, then resume this task.')
    }
    if (Test-ReadinessIssue $Issues 'mapping_contract_unavailable') {
        [void]$prompts.Add('Ask the platform owner to expose the committed mapper/materializer contract for this Mapping profile, download a fresh Model Snapshot, then resume.')
    }
    if (Test-ReadinessIssue $Issues 'generator_contract_unavailable') {
        [void]$prompts.Add('Ask the platform owner to expose the committed name-based GeneratorDocumentV1, download a fresh Model Snapshot, then resume code generation.')
    }
    if ((Test-ReadinessIssue $Issues 'destination_pattern_missing') -or
        (Test-ReadinessIssue $Issues 'destination_pattern_ambiguous')) {
        [void]$prompts.Add('Choose one exact destination System, Connection, schema, and Object Type; never infer it from a source System.')
    }
    if ((Test-ReadinessIssue $Issues 'snapshot_missing') -or (Test-ReadinessIssue $Issues 'snapshot_stale')) {
        [void]$prompts.Add('Download and unzip exactly one fresh required Snapshot, replace its area, then resume.')
    }
    return [string]::Join(' ', @($prompts))
}

function Get-WorkflowReadiness([hashtable]$Options) {
    $target = Require-Option $Options 'target'
    if (@($script:ReadinessTargets.Keys) -cnotcontains $target) {
        Fail ('--target must be one of: ' + [string]::Join(', ', @($script:ReadinessTargets.Keys)) + '.')
    }
    $session = Resolve-Session $Options
    $state = Read-SessionState $session
    $issues = New-ReadinessIssues
    $snapshots = @{}
    $inputs = New-Object System.Collections.ArrayList
    foreach ($area in @($script:ReadinessTargets[$target])) {
        try {
            $snapshot = Find-Snapshot @{ session = $session; area = $area }
            $snapshots[$area] = $snapshot
            $revision = if (Test-Property $snapshot.Manifest 'model_revision') { $snapshot.Manifest.model_revision } else { $null }
            [void]$inputs.Add(@($area, (Get-Property $snapshot.Manifest 'snapshot_id'), $revision))
        }
        catch {
            if ($_.Exception.Message -eq "Expected exactly one unzipped $area Snapshot; found 0.") {
                Add-ReadinessIssue $issues 'snapshot_missing' @($area)
                [void]$inputs.Add(@($area, $null, $null))
            }
            else { throw }
        }
        if ((Test-Property $state 'stale') -and @($state.stale) -ccontains $area) {
            Add-ReadinessIssue $issues 'snapshot_stale' @($area)
        }
    }
    $counts = [ordered]@{}
    if (-not (Test-ReadinessIssue $issues 'snapshot_missing') -and -not (Test-ReadinessIssue $issues 'snapshot_stale')) {
        $metadata = if ($snapshots.ContainsKey('metadata')) { $snapshots['metadata'] } else { $null }
        $model = if ($snapshots.ContainsKey('model')) { $snapshots['model'] } else { $null }
        switch -CaseSensitive ($target) {
            'logical-build' { $counts = Get-LogicalBuildReadiness $metadata $model $issues }
            'silver-registration' { $counts = Get-RegistrationReadiness $metadata $model 'logical' 'silver' $issues }
            'logical-mapping' { $counts = Get-MappingReadiness $metadata $model 'logical' 'silver' $issues }
            'logical-code' { $counts = Get-CodeReadiness $model 'logical' $issues }
            'dimensional-build' {
                $mapping = Get-CompleteMappingLayer $model 'logical' $issues
                $silver = @{}
                foreach ($record in @(Get-ActiveMetadataObjects $metadata 'silver')) {
                    $silver[(Get-ReadinessObjectKey $record)] = $true
                }
                $eligibleSources = @{}
                foreach ($record in @(Get-ReadinessRows $model 'model_scope')) {
                    $active = Get-Property $record 'is_active'
                    $eligible = Get-Property $record 'is_dimensional_source_eligible'
                    $key = Get-ReadinessObjectKey $record
                    if (($active -isnot [bool] -or $active) -and
                        $eligible -is [bool] -and $eligible) {
                        $eligibleSources[$key] = $true
                    }
                }
                foreach ($record in @($mapping.Objects)) {
                    $key = Get-ReadinessObjectKey $record
                    $example = @($script:PhysicalObjectFields | ForEach-Object { Get-Property $record $_ })
                    if (-not $silver.ContainsKey($key)) {
                        Add-ReadinessIssue $issues 'silver_target_missing' $example
                    }
                    if (-not $eligibleSources.ContainsKey($key)) {
                        Add-ReadinessIssue $issues 'scope_missing' $example
                    }
                }
                $counts = [ordered]@{
                    packages = @($mapping.Objects).Count
                    attributes = @($mapping.Attributes).Count
                    silver_targets = $silver.Count
                }
            }
            'gold-registration' { $counts = Get-RegistrationReadiness $metadata $model 'dimensional' 'gold' $issues }
            'dimensional-mapping' {
                [void](Get-CompleteMappingLayer $model 'logical' $issues)
                $counts = Get-MappingReadiness $metadata $model 'dimensional' 'gold' $issues
            }
            'dimensional-code' { $counts = Get-CodeReadiness $model 'dimensional' $issues }
        }
    }
    $issueOutput = Get-ReadinessIssueOutput $issues
    $prompt = Get-ReadinessPrompt $issues
    $output = [ordered]@{
        target = $target
        ready = @($issueOutput.Blockers).Count -eq 0
        inputs = @($inputs)
        counts = $counts
        blockers = @($issueOutput.Blockers)
        examples = @($issueOutput.Examples)
        truncated = [bool]$issueOutput.Truncated
    }
    if (-not [string]::IsNullOrWhiteSpace($prompt)) { $output['resolution_prompt'] = $prompt }
    return $output
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
    if ($Context.Area -eq 'model' -and $Dataset.name -ceq 'model_scope') {
        Fail "$($Dataset.name) mutation is not exposed by GDS Workbench."
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
    return @($issues)
}

function Add-LocalValidationIssue($Issues, [string]$Dataset, $Record, [string]$Code, $Detail = $null) {
    if ($Issues.Count -ge 200) { return }
    $humanCode = $Code.Replace('_', ' ')
    $message = if ($null -eq $Detail -or [string]$Detail -ceq $Code) {
        "${Code}: $humanCode"
    }
    else {
        "${Code}: ${humanCode}: $Detail"
    }
    [void]$Issues.Add(@($Dataset, $Record, $message))
}

function Get-EffectiveRecords($Context, $Dataset, [object[]]$Draft) {
    $records = New-Object 'System.Collections.Generic.Dictionary[string,object]'
    foreach ($record in @(Read-SnapshotRecords $Context $Dataset)) {
        $records[(Get-CanonicalKey $Context.Area $Dataset $record)] = $record
    }
    foreach ($record in @($Draft)) {
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

function Add-MetadataReferenceIssues([object[]]$States, $Issues) {
    $byType = New-Object 'System.Collections.Generic.Dictionary[string,object]'
    foreach ($state in @($States)) { $byType[[string]$state.RecordType] = $state }
    foreach ($state in @($States)) {
        $references = Get-Property $state.Schema 'x-gds-references'
        if ($references -isnot [Array]) { continue }
        $recordNumber = 0
        foreach ($record in @($state.Effective)) {
            $recordNumber++
            if ((Get-Active $record) -eq $false) { continue }
            foreach ($reference in @($references)) {
                $targetType = [string](Get-Property $reference 'target_record_type')
                if (-not $byType.ContainsKey($targetType)) {
                    Add-LocalValidationIssue $Issues $state.Dataset.name $recordNumber 'invalid_reference_contract'
                    continue
                }
                $columns = Get-Property $reference 'columns'
                $targetColumns = Get-Property $reference 'target_columns'
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
                $wanted = New-Object System.Collections.ArrayList
                for ($index = 0; $index -lt $values.Count; $index++) {
                    [void]$wanted.Add((Normalize-Value 'metadata' ([string](@($targetColumns)[$index])) $values[$index]))
                }
                $wantedKey = ConvertTo-StableJson @($wanted)
                $found = $false
                foreach ($candidate in @($byType[$targetType].Effective)) {
                    if ((Get-Active $candidate) -eq $false) { continue }
                    if ((Get-NormalizedValidationKey 'metadata' @($targetColumns) $candidate) -ceq $wantedKey) {
                        $found = $true
                        break
                    }
                }
                if (-not $found) {
                    Add-LocalValidationIssue $Issues $state.Dataset.name $recordNumber 'broken_reference' $targetType
                }
            }
        }
    }
}

function Get-ModelValidationRecords($ByName, [string]$Dataset, [bool]$Changed) {
    if (-not $ByName.ContainsKey($Dataset)) { return }
    $records = if ($Changed) { $ByName[$Dataset].Pending } else { $ByName[$Dataset].Effective }
    foreach ($record in @($records)) { Write-Output $record }
}

function Get-ModelNormalized($Value) {
    return Normalize-Value 'model' 'value' $Value
}

function Get-ModelNameSet($ByName, [string]$Dataset, [string]$Field) {
    $names = New-Object 'System.Collections.Generic.Dictionary[string,bool]'
    foreach ($record in @(Get-ModelValidationRecords $ByName $Dataset $false)) {
        $name = ConvertTo-StableJson (Get-ModelNormalized (Get-Property $record $Field))
        $names[$name] = $true
    }
    return ,$names
}

function Get-ModelPairKey($Entity, $Attribute) {
    return ConvertTo-StableJson @(
        (Get-ModelNormalized $Entity),
        (Get-ModelNormalized $Attribute)
    )
}

function Get-ModelPhysicalObjectKey($Record, [string]$Prefix = '') {
    $values = New-Object System.Collections.ArrayList
    foreach ($field in $script:PhysicalObjectFields) {
        $name = if ([string]::IsNullOrEmpty($Prefix)) { $field } else { $Prefix + '_' + $field }
        [void]$values.Add((Get-ModelNormalized (Get-Property $Record $name)))
    }
    return ConvertTo-StableJson @($values)
}

function Get-ModelSourceKey($Source) {
    $type = Get-Property $Source 'support_source_type'
    if ($type -is [string] -and $type -ceq 'assertion') {
        $assertion = Get-Property $Source 'assertion_record'
        return ConvertTo-StableJson @(
            'assertion',
            (Get-ModelNormalized (Get-Property $assertion 'modeling_assertion_record_key'))
        )
    }
    $physical = Get-Property $Source 'source_object'
    if ($null -eq $physical) { $physical = Get-Property $Source 'source_attribute' }
    $values = New-Object System.Collections.ArrayList
    [void]$values.Add($type)
    foreach ($field in $script:PhysicalObjectFields) {
        [void]$values.Add((Get-ModelNormalized (Get-Property $physical $field)))
    }
    if ($type -is [string] -and $type -ceq 'attribute') {
        [void]$values.Add((Get-ModelNormalized (Get-Property $physical 'attribute_name')))
    }
    return ConvertTo-StableJson @($values)
}

function Get-ModelMappingObjectKey($Record) {
    return ConvertTo-StableJson @(
        (Get-ModelPhysicalObjectKey $Record),
        (Get-ModelNormalized (Get-Property $Record 'source_system_code')),
        (Get-Property $Record 'modeled_entity_type'),
        (Get-ModelNormalized (Get-Property $Record 'modeled_entity_name'))
    )
}

function Add-ModelMissingIssue($Issues, [string]$Dataset, [int]$RecordNumber) {
    $message = 'Referenced record is not present in the effective Model graph.'
    Add-LocalValidationIssue $Issues $Dataset $RecordNumber 'reference_not_found' $message
}

function Test-ModelNestedDuplicate($Values, [string]$Kind) {
    if ($Values -isnot [Array]) { return $false }
    $seen = New-Object 'System.Collections.Generic.Dictionary[string,bool]'
    foreach ($value in @($Values)) {
        switch -CaseSensitive ($Kind) {
            'source' { $key = Get-ModelSourceKey $value }
            'submodel' {
                $key = ConvertTo-StableJson (Get-ModelNormalized (Get-Property $value 'submodel_name'))
            }
            default { $key = ConvertTo-StableJson (Get-ModelNormalized $value) }
        }
        if ($seen.ContainsKey($key)) { return $true }
        $seen[$key] = $true
    }
    return $false
}

function Add-ModelNestedUniquenessIssues($ByName, $Issues) {
    $records = @(Get-ModelValidationRecords $ByName 'modeling_assertion_record' $false)
    for ($index = 0; $index -lt $records.Count; $index++) {
        $field = 'modeling_assertion_applicable_layers'
        if (Test-ModelNestedDuplicate (Get-Property $records[$index] $field) 'normalized') {
            Add-LocalValidationIssue $Issues 'modeling_assertion_record' ($index + 1) `
                'duplicate_nested_key' "$field contains a normalized duplicate."
        }
    }
    foreach ($dataset in @('conceptual_object', 'conceptual_relationship')) {
        $records = @(Get-ModelValidationRecords $ByName $dataset $false)
        for ($index = 0; $index -lt $records.Count; $index++) {
            if ($dataset -ceq 'conceptual_object') {
                $field = 'conceptual_object_aliases'
                if (Test-ModelNestedDuplicate (Get-Property $records[$index] $field) 'normalized') {
                    Add-LocalValidationIssue $Issues $dataset ($index + 1) 'duplicate_nested_key' `
                        "$field contains a normalized duplicate."
                }
            }
            $field = 'supports'
            if (Test-ModelNestedDuplicate (Get-Property $records[$index] $field) 'source') {
                Add-LocalValidationIssue $Issues $dataset ($index + 1) 'duplicate_nested_key' `
                    "$field contains a normalized duplicate."
            }
        }
    }
    foreach ($layer in @('logical', 'dimensional')) {
        $entityDataset = $layer + '_entity'
        $records = @(Get-ModelValidationRecords $ByName $entityDataset $false)
        for ($index = 0; $index -lt $records.Count; $index++) {
            $field = 'submodels'
            if (Test-ModelNestedDuplicate (Get-Property $records[$index] $field) 'submodel') {
                Add-LocalValidationIssue $Issues $entityDataset ($index + 1) `
                    'duplicate_nested_key' "$field contains a normalized duplicate."
            }
            $field = 'sources'
            if (Test-ModelNestedDuplicate (Get-Property $records[$index] $field) 'source') {
                Add-LocalValidationIssue $Issues $entityDataset ($index + 1) `
                    'duplicate_nested_key' "$field contains a normalized duplicate."
            }
        }
        $attributeDataset = $layer + '_attribute'
        $records = @(Get-ModelValidationRecords $ByName $attributeDataset $false)
        for ($index = 0; $index -lt $records.Count; $index++) {
            $field = 'sources'
            if (Test-ModelNestedDuplicate (Get-Property $records[$index] $field) 'source') {
                Add-LocalValidationIssue $Issues $attributeDataset ($index + 1) `
                    'duplicate_nested_key' "$field contains a normalized duplicate."
            }
        }
    }
}

function Add-ModelPolicyIssue(
    $Issues,
    [string]$Dataset,
    [int]$RecordNumber,
    [string]$Message
) {
    Add-LocalValidationIssue $Issues $Dataset $RecordNumber 'record_policy_invalid' $Message
}

function Get-JsonStringUtf8ByteCount([string]$Value) {
    [long]$size = 2
    for ($index = 0; $index -lt $Value.Length; $index++) {
        $code = [int][char]$Value[$index]
        if ($code -eq 0x22 -or $code -eq 0x5C -or @(
            0x08, 0x09, 0x0A, 0x0C, 0x0D
        ) -contains $code) {
            $size += 2
        }
        elseif ($code -le 0x1F) { $size += 6 }
        elseif ($code -ge 0xD800 -and $code -le 0xDBFF) {
            if ($index + 1 -lt $Value.Length) {
                $next = [int][char]$Value[$index + 1]
                if ($next -ge 0xDC00 -and $next -le 0xDFFF) {
                    $size += 4
                    $index++
                    continue
                }
            }
            $size += 6
        }
        elseif ($code -ge 0xDC00 -and $code -le 0xDFFF) { $size += 6 }
        elseif ($code -le 0x7F) { $size++ }
        elseif ($code -le 0x7FF) { $size += 2 }
        else { $size += 3 }
    }
    return $size
}

function Get-JsonUtf8ByteCount($Value) {
    if ($null -eq $Value) { return 4 }
    if ($Value -is [string]) { return Get-JsonStringUtf8ByteCount $Value }
    if ($Value -is [ValueType]) {
        $json = ConvertTo-GdsJson $Value
        return [Text.Encoding]::UTF8.GetByteCount([string]$json)
    }
    if ($Value -is [Array]) {
        [long]$size = 2
        $items = @($Value)
        if ($items.Count -gt 1) { $size += $items.Count - 1 }
        foreach ($item in $items) { $size += Get-JsonUtf8ByteCount $item }
        return $size
    }

    $properties = @(if ($Value -is [Collections.IDictionary]) {
        $Value.Keys | ForEach-Object {
            [pscustomobject]@{ Name = [string]$_; Value = $Value[$_] }
        }
    }
    else { $Value.PSObject.Properties })
    [long]$size = 2
    if ($properties.Count -gt 1) { $size += $properties.Count - 1 }
    foreach ($property in $properties) {
        $size += Get-JsonUtf8ByteCount ([string]$property.Name)
        $size++
        $size += Get-JsonUtf8ByteCount $property.Value
    }
    return $size
}

function Add-ModelRecordPolicyIssues($ByName, $Issues) {
    $records = @(Get-ModelValidationRecords $ByName 'profiling_profile' $true)
    for ($index = 0; $index -lt $records.Count; $index++) {
        $record = $records[$index]
        $nonNull = Get-Property $record 'non_null_count'
        $nullCount = Get-Property $record 'null_count'
        $rowCount = Get-Property $record 'row_count'
        $blank = Get-Property $record 'blank_count'
        $distinct = Get-Property $record 'distinct_count'
        $minimumLength = Get-Property $record 'min_data_length'
        $maximumLength = Get-Property $record 'max_data_length'
        $invalidCounts = -not (
            (Test-JsonNumber $nonNull) -and
            (Test-JsonNumber $nullCount) -and
            (Test-JsonNumber $rowCount)
        )
        if (-not $invalidCounts) {
            $invalidCounts = (
                ([double]$nonNull + [double]$nullCount) -ne [double]$rowCount -or
                ($null -ne $blank -and (Test-JsonNumber $blank) -and
                    [double]$blank -gt [double]$nonNull) -or
                ($null -ne $distinct -and (Test-JsonNumber $distinct) -and
                    [double]$distinct -gt [double]$nonNull) -or
                ($null -ne $minimumLength -and $null -ne $maximumLength -and
                    (Test-JsonNumber $minimumLength) -and
                    (Test-JsonNumber $maximumLength) -and
                    [double]$minimumLength -gt [double]$maximumLength)
            )
        }
        if ($invalidCounts) {
            Add-ModelPolicyIssue $Issues 'profiling_profile' ($index + 1) `
                'Profiling counts or length bounds are inconsistent.'
        }
    }

    $records = @(Get-ModelValidationRecords $ByName 'analysis_result' $true)
    for ($index = 0; $index -lt $records.Count; $index++) {
        $record = $records[$index]
        $validationFields = @(
            'validation_policy_version',
            'validation_result',
            'validation_source_non_null_count',
            'validation_source_distinct_count',
            'validation_target_non_null_count',
            'validation_target_distinct_count',
            'validation_source_missing_target_count',
            'validation_unused_target_count',
            'validation_duplicate_target_key_count'
        )
        $validationValueCount = 0
        foreach ($field in $validationFields) {
            if ($null -ne (Get-Property $record $field)) { $validationValueCount++ }
        }
        if ($validationValueCount -ne 0 -and $validationValueCount -ne $validationFields.Count) {
            Add-ModelPolicyIssue $Issues 'analysis_result' ($index + 1) `
                'Analysis validation fields must all be present or all be absent.'
        }
        $endpoints = New-Object System.Collections.ArrayList
        foreach ($prefix in @('from', 'to')) {
            $values = New-Object System.Collections.ArrayList
            foreach ($field in @($script:PhysicalObjectFields + 'attribute_name')) {
                [void]$values.Add((Get-ModelNormalized (Get-Property $record ($prefix + '_' + $field))))
            }
            [void]$endpoints.Add((ConvertTo-StableJson @($values)))
        }
        if ($endpoints[0] -ceq $endpoints[1]) {
            Add-ModelPolicyIssue $Issues 'analysis_result' ($index + 1) `
                'Analysis endpoints must differ.'
        }
    }

    $records = @(Get-ModelValidationRecords $ByName 'conceptual_relationship' $true)
    for ($index = 0; $index -lt $records.Count; $index++) {
        $from = Get-ModelNormalized (Get-Property $records[$index] 'from_conceptual_object_name')
        $to = Get-ModelNormalized (Get-Property $records[$index] 'to_conceptual_object_name')
        if ((ConvertTo-StableJson $from) -ceq (ConvertTo-StableJson $to)) {
            Add-ModelPolicyIssue $Issues 'conceptual_relationship' ($index + 1) `
                'Conceptual Relationship endpoints must differ.'
        }
    }

    foreach ($layer in @('logical', 'dimensional')) {
        $dataset = $layer + '_relationship'
        $entityField = $layer + '_entity_name'
        $attributeField = $layer + '_attribute_name'
        $records = @(Get-ModelValidationRecords $ByName $dataset $true)
        for ($index = 0; $index -lt $records.Count; $index++) {
            $record = $records[$index]
            $from = Get-ModelPairKey `
                (Get-Property $record ('from_' + $entityField)) `
                (Get-Property $record ('from_' + $attributeField))
            $to = Get-ModelPairKey `
                (Get-Property $record ('to_' + $entityField)) `
                (Get-Property $record ('to_' + $attributeField))
            if ($from -ceq $to) {
                Add-ModelPolicyIssue $Issues $dataset ($index + 1) `
                    "$layer Relationship endpoints must differ."
            }
        }
    }

    $records = @(Get-ModelValidationRecords $ByName 'logical_entity' $true)
    for ($index = 0; $index -lt $records.Count; $index++) {
        $record = $records[$index]
        $type = Get-Property $record 'logical_entity_type'
        $isOther = $type -is [string] -and $type -ceq 'other'
        $hasDetail = $null -ne (Get-Property $record 'logical_entity_type_detail')
        if ($isOther -ne $hasDetail) {
            Add-ModelPolicyIssue $Issues 'logical_entity' ($index + 1) `
                'Logical Entity type detail is required only for other.'
        }
    }

    $records = @(Get-ModelValidationRecords $ByName 'logical_attribute' $true)
    for ($index = 0; $index -lt $records.Count; $index++) {
        $record = $records[$index]
        $naturalValue = Get-Property $record 'logical_attribute_is_natural_key'
        $surrogateValue = Get-Property $record 'logical_attribute_is_surrogate_key'
        $primaryValue = Get-Property $record 'logical_attribute_is_primary_key'
        $nullableValue = Get-Property $record 'logical_attribute_is_nullable'
        $natural = $naturalValue -is [bool] -and $naturalValue
        $surrogate = $surrogateValue -is [bool] -and $surrogateValue
        $primary = $primaryValue -is [bool] -and $primaryValue
        $nullable = $nullableValue -is [bool] -and $nullableValue
        if (($natural -and $surrogate) -or (($primary -or $natural -or $surrogate) -and $nullable)) {
            Add-ModelPolicyIssue $Issues 'logical_attribute' ($index + 1) `
                'Logical key flags and nullability are inconsistent.'
        }
    }

    $records = @(Get-ModelValidationRecords $ByName 'dimensional_entity' $true)
    for ($index = 0; $index -lt $records.Count; $index++) {
        $record = $records[$index]
        $type = Get-Property $record 'dimensional_entity_type'
        $isFact = $type -is [string] -and $type -ceq 'fact'
        $isBridge = $type -is [string] -and $type -ceq 'bridge'
        $hasFactType = $null -ne (Get-Property $record 'dimensional_fact_type')
        $needsGrain = $isFact -or $isBridge
        $hasGrain = $null -ne (Get-Property $record 'dimensional_entity_grain_definition')
        if (($isFact -ne $hasFactType) -or ($needsGrain -and -not $hasGrain)) {
            Add-ModelPolicyIssue $Issues 'dimensional_entity' ($index + 1) `
                'Dimensional type, fact type, and grain are inconsistent.'
        }
    }

    $records = @(Get-ModelValidationRecords $ByName 'dimensional_attribute' $true)
    for ($index = 0; $index -lt $records.Count; $index++) {
        $record = $records[$index]
        $keyRole = Get-Property $record 'dimensional_attribute_key_role'
        $role = Get-Property $record 'dimensional_attribute_role'
        $isNoKey = $keyRole -is [string] -and $keyRole -ceq 'none'
        $roleAllowsKey = $role -is [string] -and @('key', 'technical') -ccontains $role
        if (-not $isNoKey -and -not $roleAllowsKey) {
            Add-ModelPolicyIssue $Issues 'dimensional_attribute' ($index + 1) `
                'A Dimensional key role requires a key or technical Attribute.'
        }
        $additivity = Get-Property $record 'dimensional_attribute_additivity'
        $aggregation = Get-Property $record 'dimensional_attribute_default_aggregation'
        $basis = Get-Property $record 'dimensional_attribute_aggregation_basis'
        $isMeasure = $role -is [string] -and $role -ceq 'measure'
        $isAdditive = $additivity -is [string] -and $additivity -ceq 'additive'
        $invalidMeasure = if ($isMeasure) {
            $null -eq $additivity -or $null -eq $aggregation -or
                (-not $isAdditive -and $null -eq $basis)
        }
        else {
            $null -ne $additivity -or $null -ne $aggregation -or $null -ne $basis
        }
        if ($invalidMeasure) {
            Add-ModelPolicyIssue $Issues 'dimensional_attribute' ($index + 1) `
                'Dimensional measure policy fields are inconsistent.'
        }
        $auditValue = Get-Property $record 'dimensional_attribute_is_audit_column'
        $roleIsAudit = $role -is [string] -and $role -ceq 'audit'
        if ($auditValue -isnot [bool] -or $auditValue -ne $roleIsAudit) {
            Add-ModelPolicyIssue $Issues 'dimensional_attribute' ($index + 1) `
                'Dimensional audit flag and role must agree.'
        }
    }

    $records = @(Get-ModelValidationRecords $ByName 'mapping_object' $true)
    for ($index = 0; $index -lt $records.Count; $index++) {
        $record = $records[$index]
        $authored = @(
            (Get-Property $record 'artifact_type'),
            (Get-Property $record 'artifact_generation_instructions'),
            (Get-Property $record 'mapping_profile_key'),
            (Get-Property $record 'mapping_profile_version'),
            (Get-Property $record 'mapping_package_document'),
            (Get-Property $record 'object_mapping_transformation_document')
        )
        $hasNull = $false
        $hasValue = $false
        foreach ($value in $authored) {
            if ($null -eq $value) { $hasNull = $true }
            else { $hasValue = $true }
        }
        if ($hasNull -and $hasValue) {
            Add-ModelPolicyIssue $Issues 'mapping_object' ($index + 1) `
                'Mapping authored fields must be entirely present or absent.'
        }
        $package = Get-Property $record 'mapping_package_document'
        if ($null -ne $package -and (Get-JsonUtf8ByteCount $package) -gt 524288) {
            Add-ModelPolicyIssue $Issues 'mapping_object' ($index + 1) `
                'Mapping package document is too large.'
        }
        $transformation = Get-Property $record 'object_mapping_transformation_document'
        $version = Get-Property $transformation 'schema_version'
        $kind = Get-Property $transformation 'transformation_kind'
        $validVersion = $version -is [string] -and $version -ceq '1.0'
        $validKind = $kind -is [string] -and @('direct', 'derived') -ccontains $kind
        if ($null -ne $transformation -and (-not $validVersion -or -not $validKind -or
            (Get-JsonUtf8ByteCount $transformation) -gt 262144)) {
            Add-ModelPolicyIssue $Issues 'mapping_object' ($index + 1) `
                'Object Mapping transformation contract is invalid.'
        }
    }

    $records = @(Get-ModelValidationRecords $ByName 'mapping_attribute' $true)
    for ($index = 0; $index -lt $records.Count; $index++) {
        $transformation = Get-Property $records[$index] 'attribute_mapping_transformation_document'
        $version = Get-Property $transformation 'schema_version'
        $kind = Get-Property $transformation 'transformation_kind'
        $validVersion = $version -is [string] -and $version -ceq '1.0'
        $validKind = $kind -is [string] -and @('direct', 'expression') -ccontains $kind
        if ($null -ne $transformation -and (-not $validVersion -or -not $validKind -or
            (Get-JsonUtf8ByteCount $transformation) -gt 65536)) {
            Add-ModelPolicyIssue $Issues 'mapping_attribute' ($index + 1) `
                'Attribute Mapping transformation contract is invalid.'
        }
    }
}

function Add-ModelAssertionIssues($ByName, $Issues) {
    $documents = Get-ModelNameSet $ByName 'modeling_assertion_document' 'modeling_assertion_document_name'
    $assertions = New-Object 'System.Collections.Generic.Dictionary[string,object]'
    $records = @(Get-ModelValidationRecords $ByName 'modeling_assertion_record' $false)
    for ($index = 0; $index -lt $records.Count; $index++) {
        $record = $records[$index]
        $key = ConvertTo-StableJson (Get-ModelNormalized (Get-Property $record 'modeling_assertion_record_key'))
        $assertions[$key] = $record
        $document = ConvertTo-StableJson (Get-ModelNormalized (Get-Property $record 'modeling_assertion_document_name'))
        if (-not $documents.ContainsKey($document)) {
            Add-ModelMissingIssue $Issues 'modeling_assertion_record' ($index + 1)
        }
    }
    $rules = @(
        [pscustomobject]@{ Dataset = 'conceptual_object'; Layer = 'conceptual'; Field = 'supports' }
        [pscustomobject]@{ Dataset = 'conceptual_relationship'; Layer = 'conceptual'; Field = 'supports' }
        [pscustomobject]@{ Dataset = 'logical_entity'; Layer = 'logical'; Field = 'sources' }
        [pscustomobject]@{ Dataset = 'logical_attribute'; Layer = 'logical'; Field = 'sources' }
        [pscustomobject]@{ Dataset = 'dimensional_entity'; Layer = 'dimensional'; Field = 'sources' }
        [pscustomobject]@{ Dataset = 'dimensional_attribute'; Layer = 'dimensional'; Field = 'sources' }
    )
    foreach ($rule in $rules) {
        $dataset = [string]$rule.Dataset
        $layer = [string]$rule.Layer
        $field = [string]$rule.Field
        $records = @(Get-ModelValidationRecords $ByName $dataset $false)
        for ($index = 0; $index -lt $records.Count; $index++) {
            $sources = Get-Property $records[$index] $field
            if ($sources -isnot [Array]) { continue }
            foreach ($source in @($sources)) {
                if ((Get-Property $source 'support_source_type') -cne 'assertion') { continue }
                $assertionRecord = Get-Property $source 'assertion_record'
                $key = ConvertTo-StableJson (
                    Get-ModelNormalized (Get-Property $assertionRecord 'modeling_assertion_record_key')
                )
                if (-not $assertions.ContainsKey($key)) {
                    Add-ModelMissingIssue $Issues $dataset ($index + 1)
                    continue
                }
                $layers = Get-Property $assertions[$key] 'modeling_assertion_applicable_layers'
                if ($layers -isnot [Array] -or @($layers) -cnotcontains $layer) {
                    $message = 'Referenced Assertion does not apply to this modeling layer.'
                    Add-LocalValidationIssue $Issues $dataset ($index + 1) `
                        'assertion_layer_invalid' $message
                }
            }
        }
    }
}

function Add-ModelStructureIssues($ByName, $Issues) {
    $conceptual = Get-ModelNameSet $ByName 'conceptual_object' 'conceptual_object_name'
    $records = @(Get-ModelValidationRecords $ByName 'conceptual_relationship' $false)
    for ($index = 0; $index -lt $records.Count; $index++) {
        $from = ConvertTo-StableJson (
            Get-ModelNormalized (Get-Property $records[$index] 'from_conceptual_object_name')
        )
        $to = ConvertTo-StableJson (
            Get-ModelNormalized (Get-Property $records[$index] 'to_conceptual_object_name')
        )
        if (-not $conceptual.ContainsKey($from) -or -not $conceptual.ContainsKey($to)) {
            Add-ModelMissingIssue $Issues 'conceptual_relationship' ($index + 1)
        }
    }

    $indexes = [ordered]@{}
    foreach ($layer in @('logical', 'dimensional')) {
        $entityDataset = $layer + '_entity'
        $attributeDataset = $layer + '_attribute'
        $relationshipDataset = $layer + '_relationship'
        $entityField = $layer + '_entity_name'
        $attributeField = $layer + '_attribute_name'
        $submodels = Get-ModelNameSet $ByName ($layer + '_submodel') ($layer + '_submodel_name')
        $entities = Get-ModelNameSet $ByName $entityDataset $entityField
        $attributes = New-Object 'System.Collections.Generic.Dictionary[string,bool]'

        $entityRecords = @(Get-ModelValidationRecords $ByName $entityDataset $false)
        for ($index = 0; $index -lt $entityRecords.Count; $index++) {
            $memberships = Get-Property $entityRecords[$index] 'submodels'
            if ($memberships -isnot [Array]) { continue }
            foreach ($membership in @($memberships)) {
                $key = ConvertTo-StableJson (
                    Get-ModelNormalized (Get-Property $membership 'submodel_name')
                )
                if (-not $submodels.ContainsKey($key)) {
                    Add-ModelMissingIssue $Issues $entityDataset ($index + 1)
                }
            }
        }

        $attributeRecords = @(Get-ModelValidationRecords $ByName $attributeDataset $false)
        for ($index = 0; $index -lt $attributeRecords.Count; $index++) {
            $record = $attributeRecords[$index]
            $entity = ConvertTo-StableJson (Get-ModelNormalized (Get-Property $record $entityField))
            if (-not $entities.ContainsKey($entity)) {
                Add-ModelMissingIssue $Issues $attributeDataset ($index + 1)
            }
            $attributes[(Get-ModelPairKey (Get-Property $record $entityField) (Get-Property $record $attributeField))] = $true
        }

        $relationshipRecords = @(Get-ModelValidationRecords $ByName $relationshipDataset $false)
        for ($index = 0; $index -lt $relationshipRecords.Count; $index++) {
            $record = $relationshipRecords[$index]
            $missingEndpoint = $false
            foreach ($endpoint in @('from', 'to')) {
                $key = Get-ModelPairKey `
                    (Get-Property $record ($endpoint + '_' + $entityField)) `
                    (Get-Property $record ($endpoint + '_' + $attributeField))
                if (-not $attributes.ContainsKey($key)) { $missingEndpoint = $true }
            }
            if ($missingEndpoint) {
                Add-ModelMissingIssue $Issues $relationshipDataset ($index + 1)
            }
        }
        $indexes[$layer] = [pscustomobject]@{ Entities = $entities; Attributes = $attributes }
    }
    return [pscustomobject]$indexes
}

function Add-ModelPhysicalScopeIssues($ByName, $Issues) {
    $scope = New-Object 'System.Collections.Generic.Dictionary[string,object]'
    foreach ($record in @(Get-ModelValidationRecords $ByName 'model_scope' $false)) {
        $active = Get-Property $record 'is_active'
        if ($active -is [bool] -and $active) {
            $scope[(Get-ModelPhysicalObjectKey $record)] = $record
        }
    }

    foreach ($dataset in @('conceptual_object', 'conceptual_relationship')) {
        $records = @(Get-ModelValidationRecords $ByName $dataset $true)
        for ($index = 0; $index -lt $records.Count; $index++) {
            $supports = Get-Property $records[$index] 'supports'
            if ($supports -isnot [Array]) { continue }
            foreach ($support in @($supports)) {
                $sourceType = Get-Property $support 'support_source_type'
                if ($sourceType -isnot [string] -or $sourceType -cne 'object') { continue }
                $key = Get-ModelPhysicalObjectKey (Get-Property $support 'source_object')
                $scopeRecord = if ($scope.ContainsKey($key)) { $scope[$key] } else { $null }
                $eligible = Get-Property $scopeRecord 'is_bronze_source_eligible'
                if ($null -eq $scopeRecord -or $eligible -isnot [bool] -or -not $eligible) {
                    Add-LocalValidationIssue $Issues $dataset ($index + 1) `
                        'model_scope_reference_invalid' `
                        'Referenced physical Object is not an eligible Bronze source.'
                }
            }
        }
    }

    foreach ($layer in @('logical', 'dimensional')) {
        $eligibilityField = if ($layer -ceq 'logical') {
            'is_bronze_source_eligible'
        } else {
            'is_dimensional_source_eligible'
        }
        $objectEligibilityMessage = if ($layer -ceq 'logical') {
            'Referenced physical Object is not an eligible Bronze source.'
        } else {
            'Referenced physical Object is not an eligible Silver contribution from applied Logical Mapping.'
        }
        $attributeEligibilityMessage = if ($layer -ceq 'logical') {
            'Referenced physical Attribute is not an eligible Bronze source.'
        } else {
            'Referenced physical Attribute is not an eligible Silver contribution from applied Logical Mapping.'
        }
        $entityDataset = $layer + '_entity'
        $records = @(Get-ModelValidationRecords $ByName $entityDataset $true)
        for ($index = 0; $index -lt $records.Count; $index++) {
            $sources = Get-Property $records[$index] 'sources'
            if ($sources -isnot [Array]) { continue }
            foreach ($source in @($sources)) {
                $sourceType = Get-Property $source 'support_source_type'
                if ($sourceType -isnot [string] -or $sourceType -cne 'object') { continue }
                $key = Get-ModelPhysicalObjectKey (Get-Property $source 'source_object')
                $scopeRecord = if ($scope.ContainsKey($key)) { $scope[$key] } else { $null }
                $eligible = Get-Property $scopeRecord $eligibilityField
                if ($null -eq $scopeRecord -or $eligible -isnot [bool] -or -not $eligible) {
                    Add-LocalValidationIssue $Issues $entityDataset ($index + 1) `
                        'model_scope_reference_invalid' `
                        $objectEligibilityMessage
                }
            }
        }

        $attributeDataset = $layer + '_attribute'
        $records = @(Get-ModelValidationRecords $ByName $attributeDataset $true)
        for ($index = 0; $index -lt $records.Count; $index++) {
            $sources = Get-Property $records[$index] 'sources'
            if ($sources -isnot [Array]) { continue }
            foreach ($source in @($sources)) {
                $sourceType = Get-Property $source 'support_source_type'
                if ($sourceType -isnot [string] -or $sourceType -cne 'attribute') { continue }
                $key = Get-ModelPhysicalObjectKey (Get-Property $source 'source_attribute')
                $scopeRecord = if ($scope.ContainsKey($key)) { $scope[$key] } else { $null }
                $eligible = Get-Property $scopeRecord $eligibilityField
                if ($null -eq $scopeRecord -or $eligible -isnot [bool] -or -not $eligible) {
                    Add-LocalValidationIssue $Issues $attributeDataset ($index + 1) `
                        'model_scope_reference_invalid' `
                        $attributeEligibilityMessage
                }
            }
        }
    }

    $records = @(Get-ModelValidationRecords $ByName 'profiling_profile' $true)
    for ($index = 0; $index -lt $records.Count; $index++) {
        $key = Get-ModelPhysicalObjectKey $records[$index]
        $scopeRecord = if ($scope.ContainsKey($key)) { $scope[$key] } else { $null }
        $eligible = Get-Property $scopeRecord 'is_bronze_source_eligible'
        if ($null -eq $scopeRecord -or $eligible -isnot [bool] -or -not $eligible) {
            Add-LocalValidationIssue $Issues 'profiling_profile' ($index + 1) `
                'model_scope_reference_invalid' `
                'Referenced physical Attribute is not an eligible Bronze source.'
        }
    }

    $records = @(Get-ModelValidationRecords $ByName 'analysis_result' $true)
    for ($index = 0; $index -lt $records.Count; $index++) {
        foreach ($endpoint in @('from', 'to')) {
            $key = Get-ModelPhysicalObjectKey $records[$index] $endpoint
            $scopeRecord = if ($scope.ContainsKey($key)) { $scope[$key] } else { $null }
            $eligible = Get-Property $scopeRecord 'is_bronze_source_eligible'
            if ($null -eq $scopeRecord -or $eligible -isnot [bool] -or -not $eligible) {
                Add-LocalValidationIssue $Issues 'analysis_result' ($index + 1) `
                    'model_scope_reference_invalid' `
                    'Referenced physical Attribute is not an eligible Bronze source.'
            }
        }
    }

    foreach ($dataset in @('mapping_object', 'mapping_attribute')) {
        $records = @(Get-ModelValidationRecords $ByName $dataset $true)
        for ($index = 0; $index -lt $records.Count; $index++) {
            $record = $records[$index]
            $key = Get-ModelPhysicalObjectKey $record
            $scopeRecord = if ($scope.ContainsKey($key)) { $scope[$key] } else { $null }
            $eligibilityField = if ((Get-Property $record 'modeled_entity_type') -ceq 'logical_entity') {
                'is_logical_mapping_target_eligible'
            } else {
                'is_dimensional_mapping_target_eligible'
            }
            $eligible = Get-Property $scopeRecord $eligibilityField
            if ($null -eq $scopeRecord -or $eligible -isnot [bool] -or -not $eligible) {
                Add-LocalValidationIssue $Issues $dataset ($index + 1) `
                    'model_scope_reference_invalid' `
                    'Referenced Mapping target is not eligible for its modeled layer.'
            }
        }
    }
}

function Add-ModelMappingIssues($ByName, $Indexes, $Issues) {
    $dependencies = New-Object 'System.Collections.Generic.Dictionary[string,bool]'
    foreach ($record in @(Get-ModelValidationRecords $ByName 'mapping_dependency' $false)) {
        $key = ConvertTo-StableJson @(
            (Get-Property $record 'modeled_entity_type'),
            (Get-ModelNormalized (Get-Property $record 'source_system_code'))
        )
        $dependencies[$key] = $true
    }
    $mappingObjects = New-Object 'System.Collections.Generic.Dictionary[string,bool]'
    $records = @(Get-ModelValidationRecords $ByName 'mapping_object' $false)
    for ($index = 0; $index -lt $records.Count; $index++) {
        $record = $records[$index]
        $dependency = ConvertTo-StableJson @(
            (Get-Property $record 'modeled_entity_type'),
            (Get-ModelNormalized (Get-Property $record 'source_system_code'))
        )
        if (-not $dependencies.ContainsKey($dependency)) {
            Add-ModelMissingIssue $Issues 'mapping_object' ($index + 1)
        }
        $entityType = Get-Property $record 'modeled_entity_type'
        $entityNames = $null
        if ($entityType -ceq 'logical_entity') { $entityNames = $Indexes.logical.Entities }
        elseif ($entityType -ceq 'dimensional_entity') { $entityNames = $Indexes.dimensional.Entities }
        $entityName = ConvertTo-StableJson (Get-ModelNormalized (Get-Property $record 'modeled_entity_name'))
        if ($null -eq $entityNames -or -not $entityNames.ContainsKey($entityName)) {
            Add-ModelMissingIssue $Issues 'mapping_object' ($index + 1)
        }
        $mappingObjects[(Get-ModelMappingObjectKey $record)] = $true
    }
    $records = @(Get-ModelValidationRecords $ByName 'mapping_attribute' $false)
    for ($index = 0; $index -lt $records.Count; $index++) {
        $record = $records[$index]
        if (-not $mappingObjects.ContainsKey((Get-ModelMappingObjectKey $record))) {
            Add-ModelMissingIssue $Issues 'mapping_attribute' ($index + 1)
        }
        $entityType = Get-Property $record 'modeled_entity_type'
        $attributes = $null
        if ($entityType -ceq 'logical_entity') { $attributes = $Indexes.logical.Attributes }
        elseif ($entityType -ceq 'dimensional_entity') { $attributes = $Indexes.dimensional.Attributes }
        $attribute = Get-ModelPairKey `
            (Get-Property $record 'modeled_entity_name') `
            (Get-Property $record 'modeled_attribute_name')
        if ($null -eq $attributes -or -not $attributes.ContainsKey($attribute)) {
            Add-ModelMissingIssue $Issues 'mapping_attribute' ($index + 1)
        }
    }
}

function Add-ModelValidationIssues([object[]]$States, $Issues) {
    $byName = New-Object 'System.Collections.Generic.Dictionary[string,object]'
    foreach ($state in @($States)) { $byName[[string]$state.Dataset.name] = $state }
    Add-ModelNestedUniquenessIssues $byName $Issues
    Add-ModelRecordPolicyIssues $byName $Issues
    Add-ModelAssertionIssues $byName $Issues
    $indexes = Add-ModelStructureIssues $byName $Issues
    Add-ModelPhysicalScopeIssues $byName $Issues
    Add-ModelMappingIssues $byName $indexes $Issues
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

function Mark-Review($Context) {
    if (@('doing', 'review', 'ready', 'overridden', 'staged') -notcontains [string]$Context.Current[3]) {
        Fail "Task state $($Context.Current[3]) does not permit local editing."
    }
    $Context.Current[3] = 'review'
    Write-JsonAtomic (Join-Path $Context.Session 'session.json') $Context.State
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
        if ($index.ContainsKey($key)) { $records[$index[$key]] = $record }
        else { $index[$key] = $records.Count; [void]$records.Add($record) }
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

function Get-StagePlan($Context) {
    $pending = Read-Pending $Context
    $names = New-Object 'System.Collections.Generic.List[string]'
    foreach ($name in $pending.Keys) { [void]$names.Add([string]$name) }
    $names.Sort([StringComparer]::Ordinal)
    $datasets = New-Object System.Collections.ArrayList
    $records = 0
    foreach ($name in $names) {
        $count = @($pending[$name]).Count
        [void]$datasets.Add(@($name, $count))
        $records += $count
    }
    $bytes = 0
    foreach ($item in @(Get-ChildItem -LiteralPath $Context.ChangeDirectory -Force)) {
        if (-not $item.PSIsContainer -and $item.Name.EndsWith('.json')) { $bytes += [int64]$item.Length }
    }
    $mode = if ($records -le 5000 -and $bytes -le (450 * 1024)) { 'direct' } else { 'batch' }
    return [ordered]@{ mode = $mode; datasets = @($datasets); records = $records; bytes = $bytes }
}

function Validate-Changes([hashtable]$Options) {
    $context = Get-ChangeContext $Options
    $pending = Read-Pending $context
    $issues = New-Object System.Collections.ArrayList
    $states = New-Object System.Collections.ArrayList
    foreach ($dataset in @($context.Datasets)) {
        $schema = Get-DatasetSchema $context $dataset
        $draft = @()
        if ($pending.ContainsKey([string]$dataset.name)) { $draft = @($pending[[string]$dataset.name]) }
        $effective = @()
        $overlayError = $null
        try { $effective = @(Get-EffectiveRecords $context $dataset $draft) }
        catch {
            $overlayError = $_.Exception.Message
            $effective = @(Read-SnapshotRecords $context $dataset)
        }
        [void]$states.Add([pscustomobject]@{
            Dataset = $dataset
            Schema = $schema
            RecordType = Get-ValidationRecordType $dataset $schema
            Pending = $draft
            Effective = $effective
            OverlayError = $overlayError
        })
    }
    Add-CommonValidationIssues $context.Area @($states) $issues
    if ($context.Area -ceq 'metadata') {
        Add-MetadataUniqueIssues @($states) $issues
        Add-MetadataReferenceIssues @($states) $issues
    }
    elseif ($context.Area -ceq 'model') {
        Add-ModelValidationIssues @($states) $issues
    }
    return [ordered]@{ valid = $issues.Count -eq 0; issues = @($issues); digest = Get-WorkspaceDigest $context }
}

function Accept-Changes([hashtable]$Options) {
    $context = Get-ChangeContext $Options
    $digest = Require-Option $Options 'digest'
    $actual = Get-WorkspaceDigest $context
    if ($digest -ne $actual) { Fail "Local Change Set digest conflict: accepted $digest, found $actual." }
    $validation = Validate-Changes $Options
    $override = $Options.ContainsKey('override') -and $Options['override'] -eq 'true'
    if (-not $validation.valid -and -not $override) { Fail 'Local validation fails; fix issues or explicitly accept an override.' }
    if (-not $validation.valid) {
        $reason = Require-Option $Options 'reason'
        if ($reason -ne $reason.Trim() -or $reason.Length -gt 300) { Fail '--reason is invalid.' }
    }
    if (@('review', 'ready', 'overridden') -notcontains [string]$context.Current[3]) { Fail 'Current task must be in review before acceptance.' }
    if ($validation.valid) {
        $revision = if (Test-Property $context.Manifest 'model_revision') { $context.Manifest.model_revision } else { $null }
        $acceptance = @($actual, 'valid', [string]$context.Manifest.snapshot_id, $revision)
        $context.Current[3] = 'ready'
    }
    else {
        $revision = if (Test-Property $context.Manifest 'model_revision') { $context.Manifest.model_revision } else { $null }
        $acceptance = @($actual, 'override', $Options['reason'], [string]$context.Manifest.snapshot_id, $revision)
        $context.Current[3] = 'overridden'
    }
    Write-JsonAtomic (Join-Path (Join-Path $context.Session 'tasks') ([string]$context.Current[0] + '.accept.json')) $acceptance
    Write-JsonAtomic (Join-Path $context.Session 'session.json') $context.State
    return [ordered]@{
        task = [string]$context.Current[0]
        state = [string]$context.Current[3]
        digest = $actual
        stage = Get-StagePlan $context
    }
}

function Accept-RefreshedSnapshot([hashtable]$Options) {
    $area = Require-Option $Options 'area'
    if ($script:Areas -notcontains $area) { Fail '--area must be metadata or model.' }
    $session = Resolve-Session $Options
    $snapshot = Find-Snapshot $Options
    $state = Read-SessionState $session
    if (-not (Test-Property $state 'stale') -or @($state.stale) -notcontains $area) { Fail "$area is not marked stale." }
    $marker = $null
    $tasks = @($state.tasks)
    for ($index = $tasks.Count - 1; $index -ge 0; $index--) {
        $task = $tasks[$index]
        if ($task[1] -ne $area -or $task[3] -ne 'applied') { continue }
        $path = Join-Path (Join-Path $session 'tasks') ([string]$task[0] + '.applied.json')
        if (Test-Path -LiteralPath $path -PathType Leaf) { $marker = @(Read-Json $path 'Applied Snapshot marker'); break }
    }
    if ($null -eq $marker -or $marker.Count -ne 3 -or $marker[0] -ne $area) { Fail "No applied $area Snapshot marker is available." }
    $currentId = [string]$snapshot.Manifest.snapshot_id
    $revision = if (Test-Property $snapshot.Manifest 'model_revision') { $snapshot.Manifest.model_revision } else { $null }
    if ([string]::IsNullOrWhiteSpace($currentId) -or $currentId -eq [string]$marker[1]) { Fail "$area Snapshot was not replaced after Apply." }
    if ($area -eq 'model' -and ([int]$revision -le [int]$marker[2])) {
        Fail 'Refreshed Model Snapshot revision must be greater than the applied base revision.'
    }
    $changeDirectory = Resolve-RegularDirectory (Join-Path $session ($area + '-change-set')) 'Local Change Set'
    $files = New-Object System.Collections.ArrayList
    foreach ($item in @(Get-ChildItem -LiteralPath $changeDirectory -Force)) {
        if ($item.PSIsContainer -or ($item.Attributes -band [IO.FileAttributes]::ReparsePoint) -or -not $item.Name.EndsWith('.json')) {
            Fail 'Local Change Set contains an unsupported entry.'
        }
        $name = $item.BaseName
        $raw = [IO.File]::ReadAllText($item.FullName, [Text.Encoding]::UTF8)
        if (-not $raw.TrimStart().StartsWith('[')) { Fail "$name pending file must contain a JSON array." }
        try {
            $parsed = ConvertFrom-GdsJson $raw
            if ($parsed -isnot [Array]) { throw 'Pending root is not an array.' }
            $records = @($parsed)
        }
        catch { Fail "$name pending file is not valid JSON." }
        if ($records.Count -gt 0) {
            if (-not $snapshot.ByName.ContainsKey($name)) { Fail "Refreshed Snapshot has no dataset $name." }
            $dataset = $snapshot.ByName[$name]
            $baseline = @{}
            foreach ($record in @(Read-SnapshotRecords $snapshot $dataset)) {
                $key = Get-CanonicalKey $area $dataset $record
                if ($baseline.ContainsKey($key)) { Fail "Refreshed Snapshot $name has a duplicate canonical key." }
                $baseline[$key] = $record
            }
            foreach ($record in $records) {
                if ($null -eq $record -or $record -is [Array] -or $record -is [string] -or $record -is [ValueType]) {
                    Fail "$name pending file contains a non-object record."
                }
                $key = Get-CanonicalKey $area $dataset $record
                if (-not $baseline.ContainsKey($key) -or
                    (ConvertTo-StableJson $baseline[$key]) -cne (ConvertTo-StableJson $record)) {
                    Fail "Refreshed Snapshot does not contain the exact applied local record for $name."
                }
            }
        }
        [void]$files.Add($item.FullName)
    }
    foreach ($file in $files) { [IO.File]::Delete([string]$file) }
    $remaining = @($state.stale | Where-Object { $_ -ne $area })
    if ($remaining.Count -eq 0) { Remove-Property $state 'stale' }
    else { Set-Property $state 'stale' $remaining }
    Write-JsonAtomic (Join-Path $session 'session.json') $state
    return [ordered]@{ area = $area; id = $currentId; revision = $revision; retired = $files.Count }
}

function ConvertTo-StableJson($Value) {
    return ConvertTo-GdsJson $Value $true
}

function Assert-Accepted($Context) {
    if (@('ready', 'overridden', 'staged') -cnotcontains [string]$Context.Current[3]) {
        Fail 'Current task must have a digest-bound acceptance before reconciliation.'
    }
    $path = Join-Path (Join-Path $Context.Session 'tasks') ([string]$Context.Current[0] + '.accept.json')
    $acceptance = @(Read-Json $path 'Task acceptance')
    $digest = Get-WorkspaceDigest $Context
    if ($acceptance.Count -lt 2 -or [string]$acceptance[0] -cne $digest -or
        ([string]$Context.Current[3] -ceq 'ready' -and [string]$acceptance[1] -cne 'valid') -or
        ([string]$Context.Current[3] -ceq 'overridden' -and [string]$acceptance[1] -cne 'override') -or
        ([string]$Context.Current[3] -ceq 'staged' -and @('valid', 'override') -cnotcontains [string]$acceptance[1])) {
        Fail 'Task accepted digest does not match the exact local Change Set.'
    }
    return $digest
}

function Reconcile-Changes([hashtable]$Options) {
    $context = Get-ChangeContext $Options
    $digest = Assert-Accepted $context
    $cacheBound = Test-BoundServerDraftForReconcile $context.State $context.Current $context.Area $digest
    $pending = Read-Pending $context
    $server = Parse-Object $Options 'server'
    $nameSet = @{}
    foreach ($name in $pending.Keys) { $nameSet[$name] = $true }
    foreach ($name in @(Get-PropertyNames $server)) { $nameSet[$name] = $true }
    $datasets = New-Object System.Collections.ArrayList
    $conflicts = New-Object System.Collections.ArrayList
    foreach ($name in @($nameSet.Keys | Sort-Object)) {
        if (-not $context.ByName.ContainsKey($name)) { Fail "Server draft contains unknown dataset $name." }
        $dataset = $context.ByName[$name]
        $schema = Get-EditableSchema $context $dataset
        $hasLocal = $pending.ContainsKey($name)
        $localRecords = @()
        if ($hasLocal) { $localRecords = @($pending[$name]) }
        $serverValue = Get-Property $server $name
        $serverRecords = @()
        if (Test-Property $server $name) {
            if ($serverValue -isnot [Array]) { Fail "Server draft dataset $name must be a JSON array." }
            $serverRecords = @($serverValue)
        }
        foreach ($record in $serverRecords) {
            $issues = @(Get-SchemaIssues $record $schema)
            if ($issues.Count -gt 0) { Fail "Server draft $name record is invalid: $($issues[0])" }
        }
        if ($hasLocal -and $localRecords.Count -eq 0 -and $serverRecords.Count -gt 0) {
            [void]$datasets.Add(@($name, 'conflict', 0, $serverRecords.Count))
            [void]$conflicts.Add(@($name, [ordered]@{ explicit_clear = $true }))
            continue
        }
        $localMap = @{}
        foreach ($record in $localRecords) { $localMap[(Get-CanonicalKey $context.Area $dataset $record)] = $record }
        $serverMap = @{}
        foreach ($record in $serverRecords) {
            $key = Get-CanonicalKey $context.Area $dataset $record
            if ($serverMap.ContainsKey($key)) { Fail "Server draft $name contains a duplicate canonical key." }
            $serverMap[$key] = $record
        }
        $onlyLocal = 0
        $onlyServer = 0
        $exactOverlap = 0
        $datasetConflict = $false
        foreach ($key in $localMap.Keys) {
            if (-not $serverMap.ContainsKey($key)) { $onlyLocal++ }
            elseif ((ConvertTo-StableJson $localMap[$key]) -ceq (ConvertTo-StableJson $serverMap[$key])) { $exactOverlap++ }
            else {
                $datasetConflict = $true
                [void]$conflicts.Add(@($name, (Get-CanonicalKeyObject $context.Area $dataset $localMap[$key])))
            }
        }
        foreach ($key in $serverMap.Keys) { if (-not $localMap.ContainsKey($key)) { $onlyServer++ } }
        if ($datasetConflict) { $classification = 'conflict' }
        elseif ($onlyLocal -eq 0 -and $onlyServer -eq 0) { $classification = 'exact' }
        elseif ($onlyLocal -eq 0 -and $exactOverlap -eq $localMap.Count) { $classification = 'contained' }
        else { $classification = 'non_overlap' }
        [void]$datasets.Add(@($name, $classification, $localMap.Count, $serverMap.Count))
    }
    $classification = 'exact'
    if ($conflicts.Count -gt 0) { $classification = 'conflict' }
    elseif (@($datasets | Where-Object { $_[1] -eq 'non_overlap' }).Count -gt 0) { $classification = 'non_overlap' }
    elseif (@($datasets | Where-Object { $_[1] -eq 'contained' }).Count -gt 0) { $classification = 'contained' }
    $output = [ordered]@{
        classification = $classification
        ready = $classification -ne 'conflict'
        datasets = @($datasets)
        conflicts = @($conflicts)
        digest = $digest
        cache_bound = [bool]$cacheBound
    }
    if ($classification -eq 'conflict') {
        $output['resolution_prompt'] = 'Server draft and local records differ at the listed canonical keys. Choose which complete record is authoritative; never overwrite automatically.'
    }
    return $output
}

try {
    $options = Parse-Options $RemainingArguments
    switch ($Command) {
        'session-init' { $output = Initialize-Session $options }
        'status' { $output = Get-SessionStatus $options }
        'readiness' { $output = Get-WorkflowReadiness $options }
        'inspect' { $output = Inspect-Snapshot $options }
        'describe' { $output = Describe-Dataset $options }
        'select' { $output = Select-Snapshot $options }
        'task-add' { $output = Add-Task $options }
        'task-plan' { $output = Update-TaskPlan $options }
        'draft-cache' { $output = Set-DraftCache $options }
        'task-state' { $output = Set-TaskState $options }
        'task-stash' { $output = Stash-Task $options }
        'task-restore' { $output = Restore-Task $options }
        'copy' { $output = Copy-Records $options }
        'upsert' { $output = Upsert-Record $options }
        'upsert-batch' { $output = Upsert-RecordsBatch $options }
        'discard' { $output = Discard-Record $options }
        'review' { $output = Review-Changes $options }
        'validate' { $output = Validate-Changes $options }
        'accept' { $output = Accept-Changes $options }
        'snapshot-refresh' { $output = Accept-RefreshedSnapshot $options }
        'reconcile' { $output = Reconcile-Changes $options }
        default { Fail "Unknown command: $Command." }
    }
    [Console]::Out.WriteLine((ConvertTo-GdsJson $output))
    exit 0
}
catch {
    [Console]::Error.WriteLine('gds-local: ' + $_.Exception.Message)
    exit 1
}
