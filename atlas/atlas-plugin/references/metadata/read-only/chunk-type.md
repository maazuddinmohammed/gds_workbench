# Chunk type — `reference.chunk_type`

Registered framework logic that splits a large initial extraction into smaller independent source queries. Logic may be specific to a table or reusable across a System.

**Datasets:** `chunk_type`.
**Change Set:** read-only; cannot be staged.

## Keys

- Natural key: `chunk_type_name`.
- No additional unique tuple is published in the Snapshot registry.
- Use the published key normalization. Database IDs are not authoring fields.

## Fields

Every field is listed explicitly. Exact current MCP/Snapshot schemas remain authoritative if the contract changes.

| Field | Accepted value / presence | Meaning and use |
|---|---|---|
| `chunk_type_name` | string; minLength=1; maxLength=200; pattern=\S; required | Registered name selecting the framework's implemented chunking logic. |
| `chunk_type_description` | string; required; null allowed | Explains table-specific or reusable scope, applicability and how the chunking logic is used. Missing details require clarification before selection. |
| `is_active` | `false`, `true`; required | Whether the record is active for normal governed use. |

## References and dependencies

- No outbound reference is declared in this Snapshot dataset.
- Referenced by: [copy](../tables/copy.md).

## How authoring uses these values

Copy.chunk_type_name optionally selects this logic. Default new records to null; configure chunking only for large tables when the user explicitly requests it.

- Use existing active registered logic whose description supports the selected table/System. Do not invent chunk queries, function names or registrations.
- A general request to register or optimize a large table does not itself request chunking. Preserve existing chunk settings during unrelated edits.
- Allowed values are registered names, not a fixed enum.
- Full is a test-only seed example described as a full-load chunk; date_range in generated guidance is illustrative, not proof of a registered option.
- Descriptions define the actual splitting technique, required inputs and scope. A label alone does not establish boundaries, retry behavior or support for incremental extraction.
- Copy.copy_source_record_limit and Copy.copy_source_record_limit_attribute are inputs to that logic. The description/code defines their meaning and permitted values; do not assume a row cap, watermark, positive-only value or mandatory source-column reference. Leave unused inputs null on new records.
- If the description is incomplete, custom usage is requested or evidence conflicts, use the [framework-dependent value procedure](../editing.md#framework-dependent-values) and request the relevant orchestration code.
- A Chunk Type label does not by itself establish target append/overwrite behavior.

## Checks before reuse

Apply the [shared read-only checks](../index.md#using-read-only-tables) to the exact Keys, Fields, and dependencies above. Resolve table-specific conditions under “How authoring uses these values.”

## Source pointers

Development provenance; these source files are not runtime dependencies of the packaged skill.

User-confirmed behavior: chunking splits a large initial extraction through existing framework logic and is opt-in. Schema examples below do not define the available techniques.

- `mcp_server/gds_etl_workbench/domain/metadata_records.py:121,312`.
- `database/01_reference.sql:183`.
- `database/seed/01_metadata_snapshot_demo.sql:36`.
- `mcp_server/gds_etl_workbench/domain/snapshots/metadata.py:332,512`.
- `mcp_server/gds_etl_workbench/domain/snapshots/metadata_guidance.py:290`.
- `plugins/v2/gds/skills/gds/references/orchestration-rules.md:12`.

[All metadata tables](../index.md) · [Common validation](../validation.md)
