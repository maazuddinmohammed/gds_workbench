# Object type — `reference.object_type`

Operator-registered classification of the kind of physical Object.

**Datasets:** `object_type`.
**Change Set:** read-only; cannot be staged.

## Keys

- Natural key: `object_type_code`.
- No additional unique tuple is published in the Snapshot registry.
- Use the published key normalization. Database IDs are not authoring fields.

## Fields

Every field is listed explicitly. Exact current MCP/Snapshot schemas remain authoritative if the contract changes.

| Field | Accepted value / presence | Meaning and use |
|---|---|---|
| `object_type_code` | string; minLength=1; maxLength=100; pattern=\S; required | Stable code identifying the Object Type. |
| `object_type_name` | string; minLength=1; maxLength=200; pattern=\S; required | Name identifying the Object Type. |
| `object_type_description` | string; required; null allowed | Plain-language description of the Object Type. |
| `is_active` | `false`, `true`; required | Whether the record is active for normal governed use. |

## References and dependencies

- No outbound reference is declared in this Snapshot dataset.
- Referenced by: [object](../tables/object.md).

## How authoring uses these values

Each Source/Bronze/Silver/Gold Object supplies object_type_code referencing this table. Use its description when interpreting the Object.

- Read-only reference context for Metadata Change Sets; use an existing active registered code.
- The Object contract requires a code reference, not an Object Type name or database ID.
- TABLE is seeded as a test example meaning a relational table; it is not the complete allowed type list.
- Additional types and their runtime implications must be resolved from actual registered descriptions and consumer requirements.

## Checks before reuse

Apply the [shared read-only checks](../index.md#using-read-only-tables) to the exact Keys, Fields, and dependencies above. Resolve table-specific conditions under “How authoring uses these values.”

## Source pointers

Development provenance; these source files are not runtime dependencies of the packaged skill.

- `mcp_server/gds_etl_workbench/domain/metadata_records.py:104,157`.
- `database/01_reference.sql:70`.
- `database/seed/01_metadata_snapshot_demo.sql:20`.
- `mcp_server/gds_etl_workbench/domain/snapshots/metadata.py:311,394`.
- `docs/workflow-evidence-design.md:1855`.

[All metadata tables](../index.md) · [Common validation](../validation.md)
