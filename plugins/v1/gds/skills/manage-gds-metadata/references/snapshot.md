# Metadata snapshot

Use a snapshot for broad metadata discovery or as the base for a change. It is
an immutable, ID-free view; it is not the Change Set.

Commands assume this skill directory is the process working directory and
`<absolute-GDS-path>` is resolved before execution.

## Obtain and place it

1. Call `get_metadata_snapshot(tenant_id, schema_version="2.0")`.
2. Do not repeat its `download_url`. The full SAS query string is a temporary
   read credential for one private Blob.
3. Ask the user to use the original link, extract the ZIP, and place its
   `metadata-snapshot` folder directly under `GDS`.
4. Wait until the user says the folder is ready. Do not create, move, replace,
   delete, or repair it.
5. If the ZIP file is locally available, compare its byte count and SHA-256 with
   the MCP result before extraction. Never invent a successful ZIP check.

## Validate the dropped folder

Resolve the validator from this skill's `scripts` directory. Pass the exact
Tenant code and Snapshot ID returned by the MCP tool. On Windows PowerShell 5.1:

```powershell
powershell.exe -NoProfile -File ".\scripts\validate-metadata-snapshot.ps1" -SnapshotPath "<absolute-GDS-path>\metadata-snapshot" -ExpectedTenantCode "<tenant-code>" -ExpectedSnapshotId "<snapshot-id>"
```

On macOS:

```sh
"./scripts/validate-metadata-snapshot.sh" "<absolute-GDS-path>/metadata-snapshot" "<tenant-code>" "<snapshot-id>"
```

Completion criterion: the validator exits successfully with `ok=true`, the
expected Tenant and Snapshot ID, 29 logical datasets, and verified member
hashes/sizes. It prints control values and counts, never metadata rows.

For a user-approved reused Snapshot, there is no current MCP Snapshot ID to
compare. Omit only the expected Snapshot ID argument, keep the exact selected
Tenant code, and record the validator's Snapshot ID in `change-set.json`.

On failure, stop. Report the compact error and ask the user to replace the
folder with the correct extraction. Never modify the Snapshot to make it pass.

The SAS expiry limits downloading. The extracted Snapshot remains a local
baseline. Recommend a fresh Snapshot for changes; if the user insists on reuse,
warn that it may be outdated and record their acceptance in `change-set.json`.

## Archive shape

```text
metadata-snapshot/
├── manifest.json
├── catalog.json
├── schemas/<dataset>.schema.json
└── data/
    ├── foundational/<dataset>/rows.jsonl
    ├── reference/<dataset>/rows.jsonl
    └── operational/<dataset>/{rows.jsonl,lookup.jsonl}
```

There are 29 logical datasets: 5 foundational, 8 reference, and 16
operational. Only the operational datasets are Change Set eligible.

## Read without filling context

Follow [catalog-navigation.md](catalog-navigation.md).

1. Read `catalog.json` only.
2. Pick the exact dataset from its canonical key and search fields.
3. Search the catalog-provided `search_file` with an exact natural-key value.
4. For a wide dataset, `lookup.jsonl` returns compact fields plus a one-based
   `line`; read only that line from `rows.jsonl`.
5. For a compact dataset, the search file is already `rows.jsonl`.
6. Read `schemas/<dataset>.schema.json` only when constructing or checking a
   record.
7. Use `manifest.json` for integrity checks, not normal navigation.

Never recursively read or paste all JSONL files. Use filesystem search and
line-bounded reads. Keep only the chosen natural keys, counts, and file paths in
chat context.

## Schema meaning

The JSON Schema contains normal field validation plus:

- `x-gds-change-set-eligible`: whether it may be staged.
- `x-gds-canonical-key`: fields that identify one record.
- `x-gds-unique-constraints`: uniqueness groups to check locally.
- `x-gds-references`: natural-key foreign references.
- `x-gds-fixed-values`: values fixed by the logical dataset, such as Zone.

Rows are flat and ID-free. Foreign references use the target's natural-key
columns. Apply the schema's `x-gds-key-normalization`; only `_code`, `_name`,
and `_schema` string fields trim U+0020 spaces and lowercase. Use
[datasets.md](datasets.md) for business meaning and dependency direction.
