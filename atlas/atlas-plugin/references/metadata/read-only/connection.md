# Connection — `core.connection`

Registered physical access or placement context joining a Tenant, System, and Connection Type.

**Datasets:** `connection`.
**Change Set:** read-only; cannot be staged.

## Keys

- Natural key: `tenant_code`, `system_code`, `connection_code`.
- No additional unique tuple is published in the Snapshot registry.
- Use the published key normalization. Database IDs are not authoring fields.

## Fields

Run `describe --dataset connection` for every field's type, limits, required and null rules, description and population guidance. This table lists only fields with rules that `describe` does not state.

| Field | Meaning and use |
|---|---|
| `value` | Optional additional details. Preserve existing JSON; populate only when requested. No implied execution behavior. |

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

[All metadata tables](../index.md) · [Common validation](../validation.md)
