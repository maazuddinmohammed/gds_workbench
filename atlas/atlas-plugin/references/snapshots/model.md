# Model Snapshot

Shared format and reading guide for workflows using Model state. Read [working method](../working-method.md#snapshot-use) for freshness/recovery and [Model Change Set authoring](../model/change-sets.md) for record construction, local writes and helper contracts. Workflow references provide modeling decisions and prerequisites.

Atlas preserves the verified Model Snapshot format and uses the shared [runtime](../../docs/runtime-guide.md).

## Files and purpose

```text
<working-directory>/
  model/model-snapshot/
    manifest.json
    catalog.json
    schemas/model/<dataset>.schema.json
    data/<section>/<dataset>/rows.jsonl
  model-change-set/<dataset>.json
```

| File | Read it for |
|---|---|
| manifest.json | Snapshot identity, owning Model identity/revision and member integrity information. |
| catalog.json | Model/Tenant scope, dataset sections/counts, keys, editability, schema/data paths and section authoring prerequisites. |
| Dataset schema | Record fields, nested members, natural keys, normalization, references, constraints and authoring guidance. |
| rows.jsonl | One complete Model record per line. Records may contain nested objects/arrays; preserve their complete structure. |
| model-change-set/<dataset>.json | JSON array of complete pending records, overlaid by canonical key onto the unchanged Snapshot. |

Follow catalog rows_file/schema_file paths. Archive format version 2.0, Snapshot ID, Model revision and server Change Set draft revision identify different things: file format, export, applied Model state and pending server edits. Model ID/revision belong to the Snapshot context; do not invent model_id fields on records whose schema omits them.

## Targeted reading and local changes

1. Verify Model/Tenant identity and installed revision. Select only relevant sections, such as logical, dimensional, model_binding, mapping, code_generation or validation; the catalog is the full inventory.
2. Read the affected schemas and exact records, including their pending versions and required dependencies. Workflows specify which Metadata Snapshot records are also needed.
3. Use canonical keys and their published Model normalization. Update complete effective records, preserving unaffected nested members. Avoid copying baseline content over earlier pending edits.
4. Accumulate related records in the Model Change Set and validate the effective graph. Omitted applied records remain unchanged; the draft is not a replacement for the entire Model.

Logical and Dimensional datasets are distinct. Shared Binding/Mapping/Code datasets use modeled_entity_type=logical_entity or dimensional_entity; filter by that discriminator when relevant. Model details is a singleton with an empty canonical key, not a missing-key error. Follow the dataset schema in both cases.

Use the bounded read/write [helper contracts](../model/change-sets.md#atlas-helpers). `select --view effective` includes pending records; `--view snapshot` reads baseline only. Narrow truncated selections by known keys; neither view adds an offset/cursor.

## Saved code and local files

The Model Snapshot exports existing **saved/applied** Code; it does not synthesize transformation SQL from Metadata/Mapping or execute it. Complete text is in `generated_code_content`, accompanied by artifact names/types/status/locks and separate System assignments:

```text
model/model-snapshot/data/code_generation/generated_code/rows.jsonl
model/model-snapshot/data/code_generation/generated_code_source_system/rows.jsonl
```

Follow the catalog's actual paths. Stored SQL/Python content is part of JSONL records; current snapshot creation/install does not also emit standalone `.sql`, `.python` or notebook files. Metadata Snapshots do not generate target creation DDL; optional DDL belongs to Target Registration.

Atlas snapshot installation replaces only the selected snapshot area and leaves the separate workspace `code/` directory untouched. It does not synchronize those files with Code records. Pending Change Set JSON has replacement/reconciliation protections; a loose edited code file is not automatically covered by that guard.

Before reusing or regenerating Code, compare saved Snapshot content with existing pending records and relevant local files under [existing work and update scope](../working-method.md#existing-work-and-update-scope). Preserve unsubmitted/manual edits and resolve conflicts before producing a replacement. Extracting saved code into a reviewable local file is separate from regenerating its logic; it must preserve exact content and avoid overwriting a differing file. File extraction is an agent action: compare bytes before writing and verify equality with the complete Code record. No automatic file synchronization is implied.

## Applied prerequisites and revision boundaries

- Read section prerequisites from the catalog and applicable workflow. Local draft records support local reasoning, but do not satisfy a requirement for applied state.
- Current Code generation and Validation authoring require applied Mapping. Complete that upstream batch, Apply and refresh before consuming it as an applied prerequisite.
- Code/Validation records are included in Model Snapshots; the live read_model_section tool does not return those sections. Generated files under code/ are artifacts, not a substitute for registered Model records.
- Before governed Model submission, compare the installed revision with authoritative state. On mismatch, preserve the draft and resolve baseline/current/proposed differences before proceeding; do not overwrite or automatically merge pending work.
- After successful Apply, install fresh Model context before dependent work and retain operation receipts. Local reads and task creation do not require a new Snapshot by themselves.
- Follow [Object ownership and physical identity](../metadata/tables/object.md#ownership-and-physical-identity) for Model ownership, source-data ownership and endpoint keys. Authorized inputs may span Source Tenants; read access does not authorize metadata writes for them. Keep Metadata and Model Change Sets separate.

## Runtime reuse

Use `create_model_snapshot` and Atlas `snapshot-install` to acquire context. The installer checks archive integrity, identity and nondecreasing Model revision; it refuses unsafe replacement over unapplied work. After confirmed Apply it retires only matching local proposals. See the [runtime guide](../../docs/runtime-guide.md).

## Source pointers

Current implementation evidence, not runtime imports for this reference:

- mcp_server/gds_etl_workbench/tools/snapshots/model/archive.py
- mcp_server/gds_etl_workbench/application/model_snapshot.py
- mcp_server/gds_etl_workbench/domain/snapshots/model.py
- mcp_server/gds_etl_workbench/domain/modeling_records.py
- mcp_server/gds_etl_workbench/application/change_sets/model.py
- plugins/v2/gds/skills/gds/scripts/gds-local.js
- plugins/v2/gds/skills/gds/workbench/core.js
