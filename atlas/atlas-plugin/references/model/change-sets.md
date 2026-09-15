# Model Change Set authoring

Shared record-authoring procedure. Workflows decide what to model; dataset guides define the fields. The [Model Snapshot guide](../snapshots/model.md) owns archive reading and freshness; the [Change Set lifecycle](../change-set-lifecycle.md) owns review, staging, validation and Apply. Use the [runtime guide](../../docs/runtime-guide.md) for actual commands.

## Resolve the contract and identities

1. Read the bound Model Snapshot catalog and the affected dataset's schema. Check its canonical key, eligibility, required fields, nullable fields, nested shapes and section prerequisites.
2. Read only the affected dataset guide: [Profiling Profile](profiling-profile.md), [Analysis Result](analysis-result.md), [Conceptual](conceptual.md), [Logical](logical.md), [Dimensional](dimensional.md), [Assertions](assertions.md), [Binding](binding.md), [Mapping](mapping.md), [Generated Code](generated-code.md) or [Validation](validation.md). Use the live schema to verify the current machine contract; report conflicts with documented behavior instead of inventing fields or silently changing scope.
3. Resolve physical references using the dataset's eligibility rules and bound Metadata. Profiling/Analysis and Logical physical sources use eligible Model inputs; Bindings use eligible registered Silver/Gold targets, not Input Scope membership. Copy complete registered physical keys. Follow [ownership and physical identity](../metadata/tables/object.md#ownership-and-physical-identity); do not substitute the Model's Tenant or an Object's source owner into its physical key.
4. Bind the owning Model ID and revision in session/task/Change Set context. Record payloads contain database IDs only if their published schema explicitly permits them; the datasets documented above contain none. Follow [query scope](../query-scope.md) for measurement bindings; SQL execution Connection IDs are not record key fields.

If the installed schema is missing or an exact field needs clarification, the current read-only MCP call is:

```json
{"dataset":"analysis_result","detail":"full","schema_version":"1.0"}
```

Pass that object to `describe_model_dataset`. Use `detail:"compact"` for the canonical key, authoring schema and rules; `full` additionally returns per-column guidance and full JSON Schema. This tool returns no records and needs no Model ID. Replace `dataset` with the exact name from the applicable guide, for example `logical_entity` or `modeling_assertion_record`. Describing a schema does not refresh the bound Model Snapshot.

## Author complete local records

1. Read the affected baseline records and existing pending records. Build the effective view by canonical-key overlay; a pending record takes precedence over its baseline version.
2. Follow [record state](../record-state.md) before editing. For an existing key, edit that complete effective record and preserve unrelated fields, nested members and locks. For a new key, populate all required fields and explicit nulls where appropriate. Unknown, false and zero are different values.
3. Save JSON arrays under `model-change-set/<dataset>.json`. Profiling and Analysis records are flat; other Model datasets may contain nested arrays. Do not add a section wrapper, Model ID, database row IDs or task evidence to a record.
4. Merge changes by the dataset's canonical key through the supported local upsert. Keep earlier pending edits and unrelated records. Changing a key creates different pending intent; it does not rename or remove the original record.
5. Run [local validation](../local-validation.md) against the effective Model graph, including the workflow's semantic checks. Resolve failures before dependent work; structural validity does not prove a modeling conclusion.
6. Continue related local work where prerequisites allow. At the completion/dependency boundary, follow the shared [Change Set lifecycle](../change-set-lifecycle.md).

Each dataset guide includes a complete synthetic array that illustrates the file format. Arrays hold complete changed records, not patches or the entire applied Model. Omitted applied keys remain unchanged.

Local upsert merges complete records into the existing pending dataset. Server staging instead replaces the complete pending list for each supplied dataset; omitted datasets remain pending as before, and an empty list clears only that pending dataset. Let the approved extension transport the prepared draft; do not pass a partial local edit as a full pending replacement.

## Atlas helpers

Run these Atlas commands through `node scripts/atlas-local.js`; `--session` is the directory containing `.atlas`. Read `command-contract --command <name>` before use.

| Helper | Purpose and limitation |
|---|---|
| `inspect --session <path> --area model` | Local dataset inventory. |
| `describe --session <path> --area model --dataset <name> --detail compact` | Local contract; request `full` only when needed. |
| `select --session <path> --area model --dataset <name> --where <JSON-object> --limit <1..200>` | Bounded records; add `--view effective` to include pending proposals. No paging; narrow truncated selections. |
| `upsert --session <path> --area model --dataset <name> --record <JSON-object> --expected-digest <digest-or-empty>` | Merge one complete pending record using the actual expected local digest. |
| `upsert-batch --session <path> --area model --changes <dataset-to-record-array-JSON> --expected-digest <digest-or-empty>` | Merge complete pending records; use the helper's current limits and returned digest. Multiple calls can build one draft. |
| `validate --session <path> --area model` | Validate the local effective Model; server checks still follow the shared lifecycle. |

Use safe argument passing for JSON. Do not hand-roll key normalization, guess digests, copy baseline records over pending edits or invent an unavailable Atlas helper.

## Source and contract corrections

Current sources: `domain/modeling_records.py`, `domain/snapshots/model.py`, `application/change_sets/model.py`, `application/change_sets/model_validation.py` and `tools/snapshots/model/describe_model_dataset.py` under `mcp_server/gds_etl_workbench/`; `plugins/v2/gds/skills/gds/contracts/local-helper.json`.

Known guidance corrections for later implementation: `domain/snapshots/model_guidance.py` still describes single-source-Tenant scope, while governed selection supports additionally authorized Source/Bronze source Tenants. It also describes Analysis findings too broadly for the exact endpoint record shape. Use authorized scope and the dataset contract; do not reproduce those stale descriptions as new restrictions or payload fields.
