# Connection type — `reference.connection_type`

Operator-registered classification of a Connection's technology or connection mechanism.

**Datasets:** `connection_type`.
**Change Set:** read-only; cannot be staged.

## Keys

- Natural key: `connection_type_code`.
- No additional unique tuple is published in the Snapshot registry.
- Use the published key normalization. Database IDs are not authoring fields.

## Fields

Every field is listed explicitly. Exact current MCP/Snapshot schemas remain authoritative if the contract changes.

| Field | Accepted value / presence | Meaning and use |
|---|---|---|
| `connection_type_code` | string; minLength=1; maxLength=100; pattern=\S; required | Stable code identifying the Connection Type. |
| `connection_type_name` | string; minLength=1; maxLength=200; pattern=\S; required | Name identifying the Connection Type. |
| `connection_type_description` | string; required; null allowed | Plain-language description of the Connection Type. |
| `is_active` | `false`, `true`; required | Whether the record is active for normal governed use. |

## References and dependencies

- No outbound reference is declared in this Snapshot dataset.
- Referenced by: [connection](connection.md).

## How authoring uses these values

Connection.connection_type_code selects the type. Workflows resolve its description through the Connection associated with the selected Object or source context.

- Read-only reference context for Metadata Change Sets; use an existing active registered code.
- Allowed codes come from current reference records, not a fixed enum.
- DEMO_POSTGRESQL is a test-only seed example.
- A type label alone does not establish foreign-catalog availability, credentials, or supported execution behavior.

## Checks before reuse

Apply the [shared read-only checks](../index.md#using-read-only-tables) to the exact Keys, Fields, and dependencies above. Resolve table-specific conditions under “How authoring uses these values.”

## Source pointers

Development provenance; these source files are not runtime dependencies of the packaged skill.

- `mcp_server/gds_etl_workbench/domain/metadata_records.py:77,97`.
- `database/01_reference.sql:54`.
- `database/seed/01_metadata_snapshot_demo.sql:12`.
- `mcp_server/gds_etl_workbench/domain/snapshots/metadata.py:288,301`.
- `docs/workflow-evidence-design.md:1822`.

[All metadata tables](../index.md) · [Common validation](../validation.md)
