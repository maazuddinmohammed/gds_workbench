# File type — `reference.file_type`

Operator-registered physical file format classification.

**Datasets:** `file_type`.
**Change Set:** read-only; cannot be staged.

## Keys

- Natural key: `file_type_name`.
- No additional unique tuple is published in the Snapshot registry.
- Use the published key normalization. Database IDs are not authoring fields.

## Fields

Every field is listed explicitly. Exact current MCP/Snapshot schemas remain authoritative if the contract changes.

| Field | Accepted value / presence | Meaning and use |
|---|---|---|
| `file_type_name` | string; minLength=1; maxLength=200; pattern=\S; required | Name identifying the File Type. |
| `file_type_description` | string; required; null allowed | Plain-language description of the File Type. |
| `is_active` | `false`, `true`; required | Whether the record is active for normal governed use. |

## References and dependencies

- No outbound reference is declared in this Snapshot dataset.
- Referenced by: [copy](../tables/copy.md).

## How authoring uses these values

Copy.source_file_type_name references the registered format used by the applicable framework step. Resolve the actual representation from its consumer. Copy filename/pattern fields separately describe [landing naming](../tables/copy.md#landing-names).

- Read-only reference context for Metadata Change Sets; use an existing active registered name, or null when a source-file type does not apply.
- Allowed names come from registered records, not a fixed enum.
- Parquet is a test seed example; csv in generated guidance is illustrative, not proof of a registered option.
- Current confirmed ingestion guidance says registered RDBMS extraction writes Parquet; this does not make every Copy a Parquet source.
- When original and landing formats differ, confirm which representation the consuming step expects. A field prefix or filename extension alone does not resolve that distinction.
- Specific behavior for other file formats is unknown without the applicable connector or consumer rule.

## Checks before reuse

Apply the [shared read-only checks](../index.md#using-read-only-tables) to the exact Keys, Fields, and dependencies above. Resolve table-specific conditions under “How authoring uses these values.”

## Source pointers

Development provenance; these source files are not runtime dependencies of the packaged skill.

- `mcp_server/gds_etl_workbench/domain/metadata_records.py:127,315`.
- `database/01_reference.sql:144`.
- `database/seed/01_metadata_snapshot_demo.sql:43`.
- `mcp_server/gds_etl_workbench/domain/snapshots/metadata.py:342,513`.
- `mcp_server/gds_etl_workbench/domain/snapshots/metadata_guidance.py:291`.
- `plugins/v2/gds/skills/gds/references/orchestration-rules.md:8`.

[All metadata tables](../index.md) · [Common validation](../validation.md)
