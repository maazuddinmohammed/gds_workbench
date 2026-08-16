# Catalog navigation

Use this only after the Snapshot validator returns `ok=true`. The catalog is a
map; it is not metadata row content.

Commands assume this skill directory is the process working directory and
`<absolute-GDS-path>` is resolved before execution.

## List available datasets

Resolve the script from this skill's `scripts` directory. Windows PowerShell
5.1:

```powershell
powershell.exe -NoProfile -File ".\scripts\inspect-metadata-catalog.ps1" -SnapshotPath "<absolute-GDS-path>\metadata-snapshot"
```

macOS:

```sh
"./scripts/inspect-metadata-catalog.sh" "<absolute-GDS-path>/metadata-snapshot"
```

Completion criterion: `ok=true`, `dataset_count=29`, and one compact line per
dataset containing section, name, row count, and whether its search result is a
complete row.

## Inspect one dataset

Pass one exact catalog dataset name. Do not guess a path.

PowerShell 5.1:

```powershell
powershell.exe -NoProfile -File ".\scripts\inspect-metadata-catalog.ps1" -SnapshotPath "<absolute-GDS-path>\metadata-snapshot" -Dataset "source_object"
```

macOS:

```sh
"./scripts/inspect-metadata-catalog.sh" "<absolute-GDS-path>/metadata-snapshot" "source_object"
```

The result gives the exact canonical key, search fields, schema file, search
file, rows file, and `search_result_complete` flag. Resolve those paths under
the validated `metadata-snapshot` directory only.

## Find candidate rows

Search one distinctive natural-key value in the returned `search_file`. Limit
candidate output to 20 lines. PowerShell 5.1:

```powershell
Select-String -LiteralPath "<search-file>" -SimpleMatch -Pattern "<key-value>" |
    Select-Object -First 20 |
    ForEach-Object { $_.Line }
```

macOS:

```sh
grep -i -F -- "<key-value>" "<search-file>" | head -n 20
```

Compare canonical-key components using the live schema's
`x-gds-key-normalization`. Only string fields ending `_code`, `_name`, or
`_schema` trim U+0020 spaces and lowercase; other fields, including Process
location and executable, compare exactly. Do not select a row from a partial
name match alone.

- `search_result_complete=true`: each match is already the full row.
- `search_result_complete=false`: each match is a compact lookup containing a
  one-based `line`. Read only that exact line from `rows_file`.

PowerShell 5.1:

```powershell
$Line = <one-based-line>
Get-Content -LiteralPath "<rows-file>" | Select-Object -Index ($Line - 1)
```

macOS:

```sh
sed -n '<one-based-line>p' "<rows-file>"
```

Completion criterion: the selected full row matches every canonical-key field.
Read its `schema_file` only when field, type, fixed-value, uniqueness, or
reference information is needed.

## Context limits

- Never recursively read the Snapshot.
- Never print an entire rows or lookup file.
- Do not run unbounded `Get-Content`, `cat`, `grep`, or filesystem searches.
- Keep only dataset names, counts, paths, keys, and the few selected rows in
  working context.
- For summaries, aggregate locally and return counts; do not paste raw rows.
