# Metadata Snapshot

Shared format and editing guide for workflows using physical metadata. Read [working method](../working-method.md#snapshot-use) for freshness, batching and recovery; [table references](../metadata/index.md) explain field meanings.

Atlas preserves the verified Snapshot format. Use the [runtime guide](../../docs/runtime-guide.md) for installation and bounded reads/writes.

## Files and purpose

```text
<working-directory>/
  metadata/metadata-snapshot/
    manifest.json
    catalog.json
    schemas/<dataset>.schema.json
    data/<section>/<dataset>/
      rows.jsonl
      lookup.jsonl                  # only where catalog declares it
  metadata-change-set/<dataset>.json
```

Sections are foundational, reference and operational. Follow the catalog's actual paths; do not construct paths from table names.

The layout above shows the primary owner root. For Model-derived work with other Metadata owners, resolve the owner's root through the [workspace contract](../workspace-contract.md#model-derived-metadata-owners), then use these same relative paths. Keep each owner's Snapshot, pending records, digest and report separate; selecting an owner does not switch the active Model.

| File | Read it for |
|---|---|
| manifest.json | Snapshot ID, owning Tenant code, format version and member integrity information. Format version 2.0 is not a metadata revision; the manifest does not list every included Source Tenant. |
| catalog.json | Dataset inventory, counts, canonical keys, rows_file, search_file, schema_file and search_result_complete. Search may point to a compact lookup or the rows file itself. |
| Dataset schema | Required fields, types, nullability and x-gds authoring rules: change-set eligibility, keys, normalization, uniqueness, references and fixed values. |
| rows.jsonl | Complete flat metadata records, one JSON object per line. Record references use published natural keys rather than database IDs. |
| lookup.jsonl | Compact key/search fields and a one-based line pointing into rows_file. A search hit may not be a complete record. |
| metadata-change-set/<dataset>.json | JSON array of complete proposed records for that dataset. This is editable local intent; Snapshot files stay unchanged. |

## Read only what is needed

1. Verify installed Snapshot kind, identity and owning Tenant through the supported installer/reader. Read the catalog inventory, then select affected datasets and their schemas; check required Source Tenant/Object coverage separately from the owning Tenant header.
2. Filter by known complete Object/group keys or a bounded set of related records. Use declared lookup files to locate rows when useful; if search_result_complete=false, retrieve the full rows_file record.
3. Include pending records when asking what the workspace currently means. A baseline-only query does not include new Objects or earlier edits.
4. Load referenced records as needed. Consulting a foreign key does not require opening every linked reference document or all Snapshot files.

Atlas `inspect` lists datasets/counts; `describe` defaults to compact schemas; `select --view snapshot` returns baseline records; `--view effective` overlays pending changes using the same canonical merger as validation. Both use normalized AND-equality filters. Its default limit is 50, maximum 200, with truncated but no cursor/offset. Narrow incomplete results by known keys; use paginated inventory only when needed to discover missing keys. A larger helper scan can stay inside the program without flooding agent context.

## Edit complete records in the draft

1. Read the effective record: its pending version if present, otherwise the baseline version. Preserve every unrelated supported field.
2. Update that complete record in the local Change Set using its canonical key. New records use the schema and registered references; existing natural-key changes follow the [manual correction rule](../metadata/editing.md#manual-natural-key-changes).
3. Preserve other pending records. A dataset file contains all pending intent for that dataset, not the whole baseline dataset or a field-level patch. Omitted baseline records remain unchanged.
4. Validate the effective result across all related pending datasets. Continue accumulating local edits until the outcome is ready for review/submission.

For example, updating one description retains the Object's complete key, flags and other fields in its pending record. Adding its Attributes can reference the pending Object in the same Change Set; no intervening Apply is needed merely to author those related records.

Atlas `copy` imports baseline records while preserving matching pending proposals. `upsert`/`upsert-batch` merge complete records by key and guard the expected draft digest. The current batch call accepts at most 200 records across datasets; several local calls can build one larger Change Set without remote submission. A batch call is not a cross-file transaction.

## Runtime reuse and refresh

- Atlas helpers share normalization, canonical-key overlay, serialization and validation with Workbench. Do not recreate them in a workflow.
- Use `select --view effective` for current intent and `--view snapshot` for applied prerequisites.
- Use create_metadata_snapshot and a verified archive installer for a fresh baseline. The installer checks returned archive identity/size/digest and scope; retain the snapshot identity in task inputs.
- Metadata has no Tenant-wide revision counter. Entry freshness, known invalidation, Tenant Lock and authoritative validation still apply to a locally accumulated batch.
- Preserve unapplied drafts on refresh. After verified Apply, install fresh applied context and retire only confirmed applied intent. Atlas `snapshot-install` performs verified installation/retirement; Workbench Reload only rereads local files.

## Source pointers

Current implementation evidence, not runtime imports for this reference:

- mcp_server/gds_etl_workbench/tools/snapshots/metadata/archive.py
- mcp_server/gds_etl_workbench/domain/snapshots/metadata.py
- plugins/v2/gds/skills/gds/contracts/local-helper.json
- plugins/v2/gds/skills/gds/scripts/gds-local.js
- plugins/v2/gds/skills/gds/workbench/core.js
