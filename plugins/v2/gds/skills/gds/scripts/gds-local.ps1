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
$script:DirectStageMaxBytes = 1024 * 1024
$script:MetadataStageChunkMaxBytes = 450 * 1024
$script:ModelStageRecordChunkMaxBytes = 900 * 1024
$script:ModelStageFragmentMaxBytes = 1024 * 1024
$script:StageChunkMaxRecords = 5000
$script:StageMaxChunks = 64
$script:ReadinessTargets = [ordered]@{
    'metadata-authoring' = @('metadata')
    'model-input-scope' = @('metadata', 'model')
    'logical-build' = @('metadata', 'model')
    'silver-registration' = @('metadata', 'model')
    'logical-binding' = @('metadata', 'model')
    'logical-mapping' = @('metadata', 'model')
    'logical-code' = @('model')
    'dimensional-build' = @('metadata', 'model')
    'gold-registration' = @('metadata', 'model')
    'dimensional-binding' = @('metadata', 'model')
    'dimensional-mapping' = @('metadata', 'model')
    'dimensional-code' = @('model')
    'validation' = @('model')
    'process-registration' = @('metadata', 'model')
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

function Get-ValidationReportPath($Context) {
    $current = [string]$Context.Session
    foreach ($segment in @('reports', 'local-validation')) {
        $current = Join-Path $current $segment
        if (-not (Test-Path -LiteralPath $current)) {
            [void](New-Item -ItemType Directory -Path $current -ErrorAction Stop)
        }
        $item = Get-Item -LiteralPath $current -ErrorAction Stop
        if (-not $item.PSIsContainer -or ($item.Attributes -band [IO.FileAttributes]::ReparsePoint)) {
            Fail 'Local validation report directory must be a regular directory.'
        }
    }
    return Join-Path $current ([string]$Context.Area + '.json')
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
    if (Test-Property $state 'sql') {
        $sqlPolicy = Get-Property $state 'sql'
        if ($sqlPolicy -isnot [string] -or
            @('never', 'essential', 'as_needed') -cnotcontains [string]$sqlPolicy) {
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
        if ($null -eq $resume) {
            foreach ($task in @($state.tasks)) {
                if (@('todo', 'queued') -ccontains [string]$task[3]) {
                    $resume = @($task)
                    break
                }
            }
        }
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
    $sqlPolicy = if (Test-Property $state 'sql') { [string](Get-Property $state 'sql') } else { $null }
    return [ordered]@{ current = $current; resume = $resume; plan = $plan; plan_digest = $planDigest; tasks = @($state.tasks); model = $model; sql_policy = $sqlPolicy; cs = $cache; stale = $stale; snapshots = $snapshots; pending = $pending; stashes = @($stashes) }
}

function Set-SqlPolicy([hashtable]$Options) {
    $session = Resolve-Session $Options
    $policy = Require-Option $Options 'policy'
    if (@('never', 'essential', 'as_needed') -cnotcontains $policy) {
        Fail '--policy must be never, essential, or as_needed.'
    }
    $state = Read-SessionState $session
    Set-Property $state 'sql' $policy
    Write-JsonAtomic (Join-Path $session 'session.json') $state
    return [ordered]@{ sql_policy = $policy }
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

function Get-SelectedSystemCodes([hashtable]$Options) {
    if (-not $Options.ContainsKey('system-codes')) {
        Fail '--system-codes is required for Validation readiness.'
    }
    try { $parsed = ConvertFrom-GdsJson ([string]$Options['system-codes']) }
    catch { Fail '--system-codes must be a JSON array of 1..1000 System codes.' }
    if ($parsed -isnot [Array]) {
        Fail '--system-codes must be a JSON array of 1..1000 System codes.'
    }
    $values = @($parsed)
    if ($values.Count -lt 1 -or $values.Count -gt 1000) {
        Fail '--system-codes must be a JSON array of 1..1000 System codes.'
    }
    $codes = New-Object System.Collections.ArrayList
    $seen = New-Object 'System.Collections.Generic.Dictionary[string,bool]' ([StringComparer]::Ordinal)
    foreach ($value in $values) {
        if ($value -isnot [string]) {
            Fail '--system-codes must contain 1..1000 nonblank System codes of at most 100 characters.'
        }
        $code = $value.Trim()
        if ([string]::IsNullOrWhiteSpace($code) -or $code.Length -gt 100 -or
            [regex]::IsMatch($code, '[\x00-\x1F\x7F]')) {
            Fail '--system-codes must contain 1..1000 nonblank System codes of at most 100 characters.'
        }
        $normalized = ConvertTo-Casefold $code
        if ($seen.ContainsKey($normalized)) {
            Fail '--system-codes must be unique case-insensitively.'
        }
        $seen[$normalized] = $true
        [void]$codes.Add($code)
    }
    return ,@($codes)
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
    foreach ($code in $Issues.Counts.Keys) {
        [void]$blockers.Add(@([string]$code, [int]$Issues.Counts[$code]))
    }
    return [pscustomobject]@{
        Blockers = @($blockers)
        Examples = @($Issues.Examples)
        Truncated = [bool]$Issues.Truncated
    }
}

function Get-ReadinessPrompt($Issues) {
    if ((Test-ReadinessIssue $Issues 'snapshot_missing') -or
        (Test-ReadinessIssue $Issues 'snapshot_stale')) {
        return 'Download and unzip one fresh required Snapshot, replace its area, then resume.'
    }
    return ''
}

function Get-WorkflowReadiness([hashtable]$Options) {
    $target = Require-Option $Options 'target'
    if (@($script:ReadinessTargets.Keys) -cnotcontains $target) {
        Fail ('--target must be one of: ' + [string]::Join(', ', @($script:ReadinessTargets.Keys)) + '.')
    }
    $systems = if ($target -ceq 'validation') { @(Get-SelectedSystemCodes $Options) } else { @() }
    if ($target -cne 'validation' -and $Options.ContainsKey('system-codes')) {
        Fail '--system-codes is available only for Validation readiness.'
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
            $revision = if (Test-Property $snapshot.Manifest 'model_revision') {
                $snapshot.Manifest.model_revision
            } else { $null }
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
    if (-not (Test-ReadinessIssue $issues 'snapshot_missing') -and
        -not (Test-ReadinessIssue $issues 'snapshot_stale')) {
        foreach ($area in @($script:ReadinessTargets[$target])) {
            [int]$records = 0
            $datasets = @($snapshots[$area].ByName.Values)
            foreach ($dataset in $datasets) {
                $rowCount = Get-Property $dataset 'row_count'
                if ($rowCount -is [ValueType]) { $records += [int]$rowCount }
            }
            $counts[$area] = [ordered]@{
                datasets = $datasets.Count
                records = $records
            }
        }
        if ($systems.Count -gt 0) { $counts['selected_systems'] = $systems.Count }
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
    if (-not [string]::IsNullOrWhiteSpace($prompt)) {
        $output['resolution_prompt'] = $prompt
    }
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
            if ((Get-Active $record) -eq $false) { continue }
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
                        if ((Get-Active $candidate) -eq $false) { continue }
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

function Add-ModelValidationIssues([object[]]$States, $Issues, [object[]]$ReferenceStates) {
    foreach ($state in @($States)) {
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

function Validate-Changes([hashtable]$Options) {
    $context = Get-ChangeContext $Options
    $pending = Read-Pending $context
    $issues = New-Object System.Collections.ArrayList
    $states = New-Object System.Collections.ArrayList
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
        Add-MetadataUniqueIssues @($states) $issues
        Add-DeclaredReferenceIssues 'metadata' @($states) $issues
    }
    elseif ($context.Area -ceq 'model') {
        $referenceStates = New-Object System.Collections.ArrayList
        foreach ($state in @($states)) { [void]$referenceStates.Add($state) }
        if (-not ((Test-Property $context.State 'stale') -and @($context.State.stale) -contains 'metadata')) {
            try {
                $metadata = Find-Snapshot @{ session = $context.Session; area = 'metadata' }
                foreach ($dataset in @($metadata.Datasets)) {
                    $schema = Get-DatasetSchema $metadata $dataset
                    $records = @(Read-SnapshotRecords $metadata $dataset)
                    [void]$referenceStates.Add([pscustomobject]@{
                        Area = 'metadata'
                        Dataset = $dataset
                        Schema = $schema
                        RecordType = Get-ValidationRecordType $dataset $schema
                        Baseline = $records
                        Pending = @()
                        Effective = $records
                        OverlayError = $null
                    })
                }
            }
            catch {
                if ($_.Exception.Message -cne 'Expected exactly one unzipped metadata Snapshot; found 0.') { throw }
            }
        }
        Add-ModelValidationIssues @($states) $issues @($referenceStates)
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
    $output = [ordered]@{
        valid = $issues.Count -eq 0
        issues = @($issueOutput)
        repairs = @($repairs)
        truncated = $issues.Count -gt 200
        digest = Get-WorkspaceDigest $context
    }
    $reportIssues = New-Object Collections.ArrayList
    foreach ($repair in @($repairs)) {
        [void]$reportIssues.Add([ordered]@{
            severity = 'error'
            dataset = [string]$repair.dataset
            record = $repair.record
            code = [string]$repair.code
            fields = @($repair.fields)
            message = [string]$repair.message
        })
    }
    $revision = if (Test-Property $context.Manifest 'model_revision') { $context.Manifest.model_revision } else { $null }
    $report = [ordered]@{
        schema_version = '1.0'
        area = [string]$context.Area
        run_by = 'agent'
        generated_at = [DateTimeOffset]::UtcNow.ToString('o', [Globalization.CultureInfo]::InvariantCulture)
        digest = [string]$output.digest
        snapshot = [ordered]@{
            id = [string]$context.Manifest.snapshot_id
            revision = $revision
            manifest_digest = Get-Sha256Digest (Join-Path $context.Root 'manifest.json')
        }
        valid = [bool]$output.valid
        issue_count = [int]$issues.Count
        truncated = [bool]$output.truncated
        issues = @($reportIssues)
    }
    Write-JsonAtomic (Get-ValidationReportPath $context) $report
    return $output
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

function Get-JsonByteCount($Value) {
    return $script:Utf8NoBom.GetByteCount((ConvertTo-StableJson $Value))
}

function Get-ByteDigest([byte[]]$Bytes) {
    $sha = [Security.Cryptography.SHA256]::Create()
    try { return ([BitConverter]::ToString($sha.ComputeHash($Bytes))).Replace('-', '').ToLowerInvariant() }
    finally { $sha.Dispose() }
}

function Merge-StageDocuments($Context, $Pending, $Server) {
    $documents = [ordered]@{}
    foreach ($name in @($Pending.Keys | Sort-Object)) {
        $dataset = $Context.ByName[$name]
        $records = @{}
        $serverRecords = @()
        if (Test-Property $Server $name) { $serverRecords = @((Get-Property $Server $name)) }
        foreach ($record in @($serverRecords) + @($Pending[$name])) {
            $records[(Get-CanonicalKey $Context.Area $dataset $record)] = $record
        }
        $orderedRecords = New-Object System.Collections.ArrayList
        foreach ($key in @($records.Keys | Sort-Object)) { [void]$orderedRecords.Add($records[$key]) }
        $documents[$name] = @($orderedRecords)
    }
    return $documents
}

function Get-DirectStageDocument($Names, $DirectNames, $Documents) {
    $changes = New-Object System.Collections.ArrayList
    foreach ($name in @($Names)) {
        if ($DirectNames.ContainsKey([string]$name)) {
            [void]$changes.Add([ordered]@{ dataset = [string]$name; records = @($Documents[$name]) })
        }
    }
    return ,@($changes)
}

function Get-RecordChunks($Records, [int]$MaximumBytes) {
    $chunks = New-Object System.Collections.ArrayList
    $current = @()
    foreach ($record in @($Records)) {
        $candidate = @($current) + @($record)
        if ($candidate.Count -le $script:StageChunkMaxRecords -and
            (Get-JsonByteCount $candidate) -le $MaximumBytes) {
            $current = @($candidate)
            continue
        }
        if ($current.Count -eq 0) { return [ordered]@{ fits = $false; chunks = @() } }
        [void]$chunks.Add(@($current))
        $current = @($record)
        if ((Get-JsonByteCount $current) -gt $MaximumBytes) {
            return [ordered]@{ fits = $false; chunks = @() }
        }
    }
    if ($current.Count -gt 0) { [void]$chunks.Add(@($current)) }
    return [ordered]@{ fits = $true; chunks = @($chunks) }
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
        [void]$lines.Add("  \"__conceptual_key\" conceptual_key [pk, not null, note: 'Visualization-only endpoint; not a modeled Attribute.']")
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
    $pending = Read-Pending $context
    $loaded = [ordered]@{}
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

    $directory = Join-Path $context.Session 'model-dbml'
    if (-not (Test-Path -LiteralPath $directory)) { [void](New-Item -ItemType Directory -Path $directory -ErrorAction Stop) }
    $directory = Resolve-RegularDirectory $directory 'Generated DBML directory'
    $manifestPath = Join-Path $directory 'manifest.json'
    $previousFiles = @()
    if (Test-Path -LiteralPath $manifestPath -PathType Leaf) {
        $previous = Read-Json $manifestPath 'Generated DBML manifest'
        if ((Get-Property $previous 'files') -is [Array]) {
            $previousFiles = @((Get-Property $previous 'files') | ForEach-Object { [string](Get-Property $_ 'path') } | Where-Object { $_ -match '^[A-Za-z0-9_][A-Za-z0-9_.-]*\.dbml$' })
        }
    }
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
    foreach ($name in $previousFiles) {
        if ($names.ContainsKey($name.ToLowerInvariant())) { continue }
        $stalePath = Join-Path $directory $name
        if (-not (Test-Path -LiteralPath $stalePath)) { continue }
        $item = Get-Item -LiteralPath $stalePath -Force -ErrorAction Stop
        if ($item.PSIsContainer -or ($item.Attributes -band [IO.FileAttributes]::ReparsePoint)) { Fail 'Stale DBML member must be a regular file.' }
        [IO.File]::Delete($item.FullName)
    }
    $manifest = [ordered]@{
        schema_version = '1.0'; snapshot_kind = 'dbml'; source = 'local_effective_model'
        model = [ordered]@{ id = Get-Property $model 'model_id'; name = Get-Property $model 'model_name'; revision = Get-Property $model 'model_revision' }
        draft_digest = Get-WorkspaceDigest $context; model_type = $modelType
        include_submodels = $includeSubmodels; files = @($files)
    }
    Write-JsonAtomic $manifestPath $manifest
    return [ordered]@{
        directory = $directory; manifest = $manifestPath; file_count = $files.Count
        draft_digest = [string]$manifest.draft_digest; files = @($files | ForEach-Object { [string](Get-Property $_ 'path') })
    }
}

function Prepare-Stage([hashtable]$Options) {
    $reconciliation = Reconcile-Changes $Options
    if (-not [bool](Get-Property $reconciliation 'ready')) {
        Fail 'Resolve reconciliation conflicts before preparing Stage.'
    }
    if (-not [bool](Get-Property $reconciliation 'cache_bound')) {
        Fail 'Cached server draft is not bound to the accepted local Change Set digest.'
    }
    $context = Get-ChangeContext $Options
    $cs = Get-Property $context.State 'cs'
    $draft = @((Get-Property $cs $context.Area))
    if ($draft.Count -lt 5 -or [string]$draft[2] -cne 'active') {
        Fail "Cached $($context.Area) server draft must be active."
    }
    $pending = Read-Pending $context
    if ($pending.Count -eq 0) { Fail 'Local Change Set has no affected datasets.' }
    $server = Parse-Object $Options 'server'
    $documents = Merge-StageDocuments $context $pending $server
    $maximumRecords = if ($context.Area -ceq 'metadata') { 50000 } else { 20000 }
    foreach ($name in $documents.Keys) {
        if (@($documents[$name]).Count -gt $maximumRecords) {
            Fail "$name exceeds the $maximumRecords-record dataset limit."
        }
    }

    $names = @($documents.Keys | Sort-Object)
    $directNames = @{}
    foreach ($name in $names) { $directNames[[string]$name] = $true }
    while ((Get-JsonByteCount (Get-DirectStageDocument $names $directNames $documents)) -gt
        $script:DirectStageMaxBytes) {
        $removable = @(
            foreach ($name in $names) {
                if ($directNames.ContainsKey([string]$name) -and @($documents[$name]).Count -gt 0) {
                    [pscustomobject]@{ Name = [string]$name; Bytes = Get-JsonByteCount @($documents[$name]) }
                }
            }
        ) | Sort-Object @{ Expression = 'Bytes'; Descending = $true }, @{ Expression = 'Name' }
        if (@($removable).Count -eq 0) { Fail 'Direct Stage envelope exceeds its safe byte limit.' }
        [void]$directNames.Remove([string]$removable[0].Name)
    }

    $taskId = [string]$context.Current[0]
    $stageDirectory = Join-Path (Join-Path $context.Session 'tasks') ($taskId + '.stage')
    if (Test-Path -LiteralPath $stageDirectory) {
        $item = Get-Item -LiteralPath $stageDirectory -Force
        if (-not $item.PSIsContainer -or ($item.Attributes -band [IO.FileAttributes]::ReparsePoint)) {
            Fail 'Stage plan path must be a regular directory.'
        }
        Remove-Item -LiteralPath $stageDirectory -Recurse -Force
    }
    [void](New-Item -ItemType Directory -Path $stageDirectory)

    $directChanges = @(Get-DirectStageDocument $names $directNames $documents)
    $direct = $null
    if ($directChanges.Count -gt 0) {
        $directPath = Join-Path $stageDirectory 'direct.json'
        Write-JsonAtomic $directPath $directChanges
        $direct = [ordered]@{
            file = $directPath
            datasets = @($directChanges | ForEach-Object { [string](Get-Property $_ 'dataset') })
            bytes = Get-JsonByteCount $directChanges
        }
    }

    $recordChunkBytes = if ($context.Area -ceq 'metadata') {
        $script:MetadataStageChunkMaxBytes
    } else {
        $script:ModelStageRecordChunkMaxBytes
    }
    $batches = New-Object System.Collections.ArrayList
    foreach ($name in $names) {
        if ($directNames.ContainsKey([string]$name)) { continue }
        $records = @($documents[$name])
        $recordChunkResult = Get-RecordChunks $records $recordChunkBytes
        $chunks = @((Get-Property $recordChunkResult 'chunks'))
        $payloadMode = 'records'
        $totalPayloadBytes = $null
        if (-not [bool](Get-Property $recordChunkResult 'fits') -or
            $chunks.Count -gt $script:StageMaxChunks) {
            if ($context.Area -cne 'model' -or [string]$name -cne 'generated_code') {
                Fail "$name cannot fit within $($script:StageMaxChunks) bounded record chunks."
            }
            $payloadMode = 'json_fragments'
            [byte[]]$payload = $script:Utf8NoBom.GetBytes((ConvertTo-StableJson $records))
            $totalPayloadBytes = $payload.Length
            $fragments = New-Object System.Collections.ArrayList
            for ($offset = 0; $offset -lt $payload.Length; $offset += $script:ModelStageFragmentMaxBytes) {
                $length = [Math]::Min($script:ModelStageFragmentMaxBytes, $payload.Length - $offset)
                $fragment = New-Object byte[] $length
                [Array]::Copy($payload, $offset, $fragment, 0, $length)
                [void]$fragments.Add($fragment)
            }
            $chunks = @($fragments)
            if ($chunks.Count -gt $script:StageMaxChunks) {
                Fail "generated_code exceeds the $($script:StageMaxChunks) MiB fragment limit."
            }
        }

        $batchDirectory = Join-Path $stageDirectory ([string]$name)
        [void](New-Item -ItemType Directory -Path $batchDirectory)
        $chunkDocuments = New-Object System.Collections.ArrayList
        for ($index = 0; $index -lt $chunks.Count; $index++) {
            $chunk = $chunks[$index]
            $chunkPath = Join-Path $batchDirectory ('chunk-{0:D2}.json' -f ($index + 1))
            if ($payloadMode -ceq 'records') {
                $canonicalBytes = $script:Utf8NoBom.GetBytes((ConvertTo-StableJson @($chunk)))
                Write-JsonAtomic $chunkPath @($chunk)
                $recordCount = @($chunk).Count
            }
            else {
                [byte[]]$canonicalBytes = $chunk
                Write-JsonAtomic $chunkPath ([Convert]::ToBase64String($canonicalBytes))
                $recordCount = 0
            }
            [void]$chunkDocuments.Add([ordered]@{
                index = $index + 1
                file = $chunkPath
                records = $recordCount
                bytes = $canonicalBytes.Length
                sha256 = Get-ByteDigest $canonicalBytes
            })
        }
        $hashText = (@($chunkDocuments) | ForEach-Object { [string](Get-Property $_ 'sha256') }) -join ''
        $batch = [ordered]@{
            dataset = [string]$name
            payload_mode = $payloadMode
            total_record_count = $records.Count
            total_chunk_count = $chunkDocuments.Count
            batch_sha256 = Get-ByteDigest ([Text.Encoding]::ASCII.GetBytes($hashText))
            chunks = @($chunkDocuments)
        }
        if ($null -ne $totalPayloadBytes) { $batch['total_payload_bytes'] = $totalPayloadBytes }
        [void]$batches.Add($batch)
    }

    $strategy = if ($null -ne $direct -and $batches.Count -gt 0) {
        'mixed'
    } elseif ($null -ne $direct) {
        'direct'
    } else {
        'batched'
    }
    $operations = New-Object System.Collections.ArrayList
    $expectedRevisionFrom = 'manifest.starting_revision'
    if ($null -ne $direct) {
        [void]$operations.Add([ordered]@{
            sequence = $operations.Count + 1
            tool = 'stage_' + [string]$context.Area + '_change_set'
            payload_file = [string]$direct.file
            expected_revision_from = $expectedRevisionFrom
            returns_revision_for = 'next operation'
        })
        $expectedRevisionFrom = 'operation ' + $operations.Count + ' response draft_revision'
    }
    foreach ($batch in @($batches)) {
        $beginSequence = $operations.Count + 1
        $begin = [ordered]@{
            sequence = $beginSequence
            tool = 'begin_' + [string]$context.Area + '_stage_batch'
            dataset = [string]$batch.dataset
            total_record_count = [int]$batch.total_record_count
            total_chunk_count = [int]$batch.total_chunk_count
            payload_mode = [string]$batch.payload_mode
            batch_sha256 = [string]$batch.batch_sha256
            expected_revision_from = $expectedRevisionFrom
            returns_stage_batch_id_for = 'following Put and Commit operations'
        }
        if (Test-Property $batch 'total_payload_bytes') {
            $begin['total_payload_bytes'] = [int]$batch.total_payload_bytes
        }
        [void]$operations.Add($begin)
        foreach ($chunk in @($batch.chunks)) {
            [void]$operations.Add([ordered]@{
                sequence = $operations.Count + 1
                tool = 'put_' + [string]$context.Area + '_stage_chunk'
                dataset = [string]$batch.dataset
                chunk_index = [int]$chunk.index
                payload_mode = [string]$batch.payload_mode
                payload_file = [string]$chunk.file
                chunk_sha256 = [string]$chunk.sha256
                stage_batch_id_from = 'operation ' + $beginSequence + ' response stage_batch_id'
            })
        }
        [void]$operations.Add([ordered]@{
            sequence = $operations.Count + 1
            tool = 'commit_' + [string]$context.Area + '_stage_batch'
            dataset = [string]$batch.dataset
            expected_revision_from = 'matching begin operation'
            stage_batch_id_from = 'operation ' + $beginSequence + ' response stage_batch_id'
            returns_revision_for = 'next operation'
        })
        $expectedRevisionFrom = 'operation ' + $operations.Count + ' response draft_revision'
    }
    $manifest = [ordered]@{
        schema_version = '1.0'
        area = $context.Area
        task = $taskId
        digest = [string](Get-Property $reconciliation 'digest')
        change_set_id = [string]$draft[0]
        starting_revision = [int64]$draft[1]
        strategy = $strategy
        limits = [ordered]@{
            direct_bytes = $script:DirectStageMaxBytes
            chunk_bytes = $recordChunkBytes
            chunk_records = $script:StageChunkMaxRecords
            chunks_per_batch = $script:StageMaxChunks
        }
        revision_rule = 'Use the returned draft_revision after direct Stage and after every batch commit.'
        direct = $direct
        batches = @($batches)
        operations = @($operations)
    }
    $manifestPath = Join-Path $stageDirectory 'manifest.json'
    Write-JsonAtomic $manifestPath $manifest
    return [ordered]@{
        strategy = $strategy
        manifest = $manifestPath
        direct_datasets = if ($null -eq $direct) { @() } else { @($direct.datasets) }
        batch_datasets = @($batches | ForEach-Object { [string](Get-Property $_ 'dataset') })
        operation_count = $operations.Count
        next_operation = $operations[0]
    }
}

try {
    $options = Parse-Options $RemainingArguments
    switch ($Command) {
        'command-contract' { $output = Get-CommandContract $options }
        'session-init' { $output = Initialize-Session $options }
        'status' { $output = Get-SessionStatus $options }
        'sql-policy' { $output = Set-SqlPolicy $options }
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
        'generate-dbml' { $output = Generate-LocalDbml $options }
        'accept' { $output = Accept-Changes $options }
        'snapshot-refresh' { $output = Accept-RefreshedSnapshot $options }
        'reconcile' { $output = Reconcile-Changes $options }
        'prepare-stage' { $output = Prepare-Stage $options }
        default { Fail "Unknown command: $Command." }
    }
    [Console]::Out.WriteLine((ConvertTo-GdsJson $output))
    exit 0
}
catch {
    [Console]::Error.WriteLine('gds-local: ' + $_.Exception.Message)
    exit 1
}
