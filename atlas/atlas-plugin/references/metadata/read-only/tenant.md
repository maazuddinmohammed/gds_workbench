# Tenant — `core.tenant`

Ownership and authorization scope for metadata, Models, and principals; belongs to a Project.

**Datasets:** `tenant`.
**Change Set:** read-only; cannot be staged.

## Keys

- Natural key: `tenant_code`.
- No additional unique tuple is published in the Snapshot registry.
- Use the published key normalization. Database IDs are not authoring fields.

## Fields

Every field is listed explicitly. Exact current MCP/Snapshot schemas remain authoritative if the contract changes.

| Field | Accepted value / presence | Meaning and use |
|---|---|---|
| `tenant_code` | string; minLength=1; maxLength=100; pattern=\S; required | Stable code identifying the Tenant. |
| `project_code` | string; minLength=1; maxLength=100; pattern=\S; required | Stable code identifying the Project. Reference: [project](project.md). |
| `tenant_name` | string; minLength=1; maxLength=200; pattern=\S; required | Name identifying the Tenant. |
| `tenant_description` | string; required; null allowed | Plain-language description of the Tenant. |
| `tenant_catalog` | string; minLength=1; maxLength=255; required | Primary data catalog assigned to the Tenant. |
| `gds_admin_catalog` | string; minLength=1; maxLength=255; required | Catalog containing administrative GDS metadata for the Tenant. |
| `gds_connection_tenant_code` | string; minLength=1; maxLength=100; pattern=\S; required; null allowed | Tenant code owning the optional GDS data-store Connection. Reference: [connection](connection.md). |
| `gds_connection_system_code` | string; minLength=1; maxLength=100; pattern=\S; required; null allowed | System code of the optional GDS data-store Connection for the Tenant. Reference: [connection](connection.md). |
| `gds_connection_code` | string; minLength=1; maxLength=100; pattern=\S; required; null allowed | Connection code of the optional GDS data-store Connection for the Tenant. Reference: [connection](connection.md). |
| `tenant_visibility` | `"global"`, `"private"`; required | Visibility boundary of the Tenant. |
| `is_active` | `false`, `true`; required | Whether the record is active for normal governed use. |

## References and dependencies

- `project_code` → [project](project.md): `project_code`. Required reference.
- `gds_connection_tenant_code`, `gds_connection_system_code`, `gds_connection_code` → [connection](connection.md): `tenant_code`, `system_code`, `connection_code`. Nullable reference; use the full declared key when populated.
- Referenced by: [connection](connection.md), [object](../tables/object.md), [copy group](../tables/copy-group.md), [member group](../tables/member-group.md), [process group](../tables/process-group.md).

## How authoring uses these values

Use the selected Tenant for metadata ownership. Object.source_tenant_code identifies the data owner; Object.tenant_code belongs to physical Connection placement. Copy Group, Member Group, Copy Group Control, Copy, Process Group, and Process use their own tenant_code for ownership.

- Foundational, operator-managed context; not editable through Metadata Change Sets.
- tenant_code is a registered natural key, distinct from Tenant ID and display name.
- tenant_visibility is a fixed field enum: global or private. Visibility does not grant write authority.
- The optional gds_connection_tenant_code, gds_connection_system_code, and gds_connection_code identify one configured Connection; all three are present together or null together.
- Bronze/Silver/Gold placement uses the owner's configured active GDS Connection, even when its placement Tenant differs from the owner.

## Checks before reuse

Apply the [shared read-only checks](../index.md#using-read-only-tables) to the exact Keys, Fields, and dependencies above. Resolve table-specific conditions under “How authoring uses these values.”

## Source pointers

Development provenance; these source files are not runtime dependencies of the packaged skill.

- `mcp_server/gds_etl_workbench/domain/metadata_records.py:42`.
- `CONTEXT.md:7,11,20,45`.
- `mcp_server/gds_etl_workbench/application/change_sets/metadata_validation.py:394`.
- `mcp_server/gds_etl_workbench/domain/snapshots/metadata.py:243`.

[All metadata tables](../index.md) · [Common validation](../validation.md)
