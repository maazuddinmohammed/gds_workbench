# System type — `reference.system_type`

Operator-registered classification of a System, with a code, name, and explanatory description.

**Datasets:** `system_type`.
**Change Set:** read-only; cannot be staged.

## Keys

- Natural key: `system_type_code`.
- No additional unique tuple is published in the Snapshot registry.
- Use the published key normalization. Database IDs are not authoring fields.

## Fields

Every field is listed explicitly. Exact current MCP/Snapshot schemas remain authoritative if the contract changes.

| Field | Accepted value / presence | Meaning and use |
|---|---|---|
| `system_type_code` | string; minLength=1; maxLength=100; pattern=\S; required | Stable code identifying the System Type. |
| `system_type_name` | string; minLength=1; maxLength=200; pattern=\S; required | Name identifying the System Type. |
| `system_type_description` | string; required; null allowed | Plain-language description of the System Type. |
| `is_active` | `false`, `true`; required | Whether the record is active for normal governed use. |

## References and dependencies

- No outbound reference is declared in this Snapshot dataset.
- Referenced by: [system](system.md).

## How authoring uses these values

System.system_type_code selects the type. Workflows resolve its description to understand source business and technical context; editable operational records use it indirectly through their Systems.

- Read-only reference context for Metadata Change Sets; use an existing active registered code.
- Allowed codes come from the current reference records, not a fixed enum.
- DEMO_DATABASE is a test-only seed example.
- Do not infer extraction syntax or all runtime capabilities from the type label alone.

## Checks before reuse

Apply the [shared read-only checks](../index.md#using-read-only-tables) to the exact Keys, Fields, and dependencies above. Resolve table-specific conditions under “How authoring uses these values.”

## Source pointers

Development provenance; these source files are not runtime dependencies of the packaged skill.

- `mcp_server/gds_etl_workbench/domain/metadata_records.py:90`.
- `database/01_reference.sql:26`.
- `database/seed/01_metadata_snapshot_demo.sql:4`.
- `mcp_server/gds_etl_workbench/domain/snapshots/metadata.py:274,291`.
- `docs/workflow-evidence-design.md:1822`.
- `plugins/v2/gds/skills/gds/references/orchestration-rules.md:12`.

[All metadata tables](../index.md) · [Common validation](../validation.md)
