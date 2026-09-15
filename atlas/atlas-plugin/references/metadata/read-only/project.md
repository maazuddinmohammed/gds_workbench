# Project — `core.project`

Registered organizational grouping to which Tenants belong.

**Datasets:** `project`.
**Change Set:** read-only; cannot be staged.

## Keys

- Natural key: `project_code`.
- No additional unique tuple is published in the Snapshot registry.
- Use the published key normalization. Database IDs are not authoring fields.

## Fields

Every field is listed explicitly. Exact current MCP/Snapshot schemas remain authoritative if the contract changes.

| Field | Accepted value / presence | Meaning and use |
|---|---|---|
| `project_code` | string; minLength=1; maxLength=100; pattern=\S; required | Stable code identifying the Project. |
| `project_name` | string; minLength=1; maxLength=200; pattern=\S; required | Name identifying the Project. |
| `project_description` | string; required; null allowed | Plain-language description of the Project. |
| `is_active` | `false`, `true`; required | Whether the record is active for normal governed use. |

## References and dependencies

- No outbound reference is declared in this Snapshot dataset.
- Referenced by: [tenant](tenant.md).

## How authoring uses these values

Resolve tenant.project_code to understand the selected Tenant's project. Editable operational metadata does not directly reference project_code.

- Foundational, operator-managed context; not editable through Metadata Change Sets.
- Use an existing project_code; codes are registered values, not a closed enum.
- DEMO_PROJECT is a test-only seed example, not an available production option.

## Checks before reuse

Apply the [shared read-only checks](../index.md#using-read-only-tables) to the exact Keys, Fields, and dependencies above. Resolve table-specific conditions under “How authoring uses these values.”

## Source pointers

Development provenance; these source files are not runtime dependencies of the packaged skill.

- `mcp_server/gds_etl_workbench/domain/metadata_records.py:35`.
- `database/02_core.sql:5,34`.
- `mcp_server/gds_etl_workbench/domain/snapshots/metadata.py:232,251`.
- `database/seed/01_metadata_snapshot_demo.sql:66`.

[All metadata tables](../index.md) · [Common validation](../validation.md)
