# Connection — `core.connection`

Registered physical access or placement context joining a Tenant, System, and Connection Type.

**Datasets:** `connection`.
**Change Set:** read-only; cannot be staged.

## Keys

- Natural key: `tenant_code`, `system_code`, `connection_code`.
- No additional unique tuple is published in the Snapshot registry.
- Use the published key normalization. Database IDs are not authoring fields.

## Fields

Every field is listed explicitly. Exact current MCP/Snapshot schemas remain authoritative if the contract changes.

| Field | Accepted value / presence | Meaning and use |
|---|---|---|
| `tenant_code` | string; minLength=1; maxLength=100; pattern=\S; required | Stable code identifying the Tenant. Reference: [tenant](tenant.md). |
| `system_code` | string; minLength=1; maxLength=100; pattern=\S; required | Stable code identifying the System. Reference: [system](system.md). |
| `connection_code` | string; minLength=1; maxLength=100; pattern=\S; required | Stable code identifying the Connection. |
| `connection_name` | string; minLength=1; maxLength=200; pattern=\S; required | Name identifying the Connection. |
| `connection_description` | string; optional field; null allowed | Plain-language description of the Connection. |
| `connection_type_code` | string; minLength=1; maxLength=100; pattern=\S; required | Stable code identifying the Connection Type. Reference: [connection type](connection-type.md). |
| `has_foreign_catalog` | `false`, `true`; required | Whether the Connection exposes its Objects through a foreign catalog. |
| `foreign_catalog` | string; maxLength=255; required; null allowed | Optional external catalog associated with the Connection. |
| `is_global_data_store` | `false`, `true`; required | Whether the Connection is the governed global data-store Connection. |
| `is_active` | `false`, `true`; required | Whether the record is active for normal governed use. |

## References and dependencies

- `tenant_code` → [tenant](tenant.md): `tenant_code`. Required reference.
- `system_code` → [system](system.md): `system_code`. Required reference.
- `connection_type_code` → [connection type](connection-type.md): `connection_type_code`. Required reference.
- Referenced by: [tenant](tenant.md).
- Objects also resolve their complete Connection key through placement checks and database FKs; this dependency is not expressed as an Object registry reference tuple.

## How authoring uses these values

Identify Object placement using the complete (tenant_code, system_code, connection_code) key. Source uses its actual source Connection; Bronze/Silver/Gold use the owner's explicitly associated GDS Connection. Copy and ingestion endpoints and Process Object references use the same physical keys.

- Foundational, operator-managed context; not editable through Metadata Change Sets.
- connection_code alone is insufficient; resolve the complete three-part key.
- connection_type_code is an existing lookup code, not an inferred connection capability.
- has_foreign_catalog and foreign_catalog describe foreign-catalog access; Source evidence queries also need the Object and Attribute foreign-catalog names.
- is_global_data_store alone does not identify the selected Tenant's configured GDS Connection.
- Connection catalog or type metadata does not provide credentials or grant execution permissions.

## Checks before reuse

Apply the [shared read-only checks](../index.md#using-read-only-tables) to the exact Keys, Fields, and dependencies above. Resolve table-specific conditions under “How authoring uses these values.”

## Source pointers

Development provenance; these source files are not runtime dependencies of the packaged skill.

- `mcp_server/gds_etl_workbench/domain/metadata_records.py:77`.
- `database/02_core.sql:80`.
- `mcp_server/gds_etl_workbench/domain/snapshots/metadata.py:157,277`.
- `mcp_server/gds_etl_workbench/domain/snapshots/metadata_guidance.py:397`.
- `plugins/v2/gds/skills/gds/references/workflows/metadata-authoring.md:13`.

[All metadata tables](../index.md) · [Common validation](../validation.md)
