# Tenant — `core.tenant`

Ownership and authorization scope for metadata, Projects, and principals; belongs to a Lane.

**Datasets:** `tenant`.
**Change Set:** read-only; cannot be staged.

## Keys

- Natural key: `tenant_code`.
- No additional unique tuple is published in the Snapshot registry.
- Use the published key normalization. Database IDs are not authoring fields.

## Fields

Run `describe --dataset tenant` for every field's type, limits, required and null rules, description and population guidance. This table lists only fields with rules that `describe` does not state.

| Field | Meaning and use |
|---|---|
| `value` | Optional additional details. Preserve existing JSON; populate only when requested. No implied execution behavior. |
| `tenant_catalog` | Target data catalog assigned to this Tenant. Used in qualified Databricks evidence queries for its owned Bronze/Silver/Gold Objects. |

## References and dependencies

- `lane_code` → [lane](lane.md): `lane_code`. Required reference.
- `gds_connection_tenant_code`, `gds_connection_system_code`, `gds_connection_code` → [connection](connection.md): `tenant_code`, `system_code`, `connection_code`. Nullable reference; use the full declared key when populated.
- Referenced by: [connection](connection.md), [object](../tables/object.md), [copy group](../tables/copy-group.md), [member group](../tables/member-group.md), [process group](../tables/process-group.md).

## How authoring uses these values

Use the selected Tenant for metadata ownership. Object.source_tenant_code identifies the data owner; Object.tenant_code belongs to physical Connection placement. Copy Group, Member Group, Copy Group Control, Copy, Process Group, and Process use their own tenant_code for ownership.

- Foundational, operator-managed context; not editable through Metadata Change Sets.
- tenant_code is a registered natural key, distinct from Tenant ID and display name.
- tenant_visibility is a fixed field enum: global or private. Visibility does not grant write authority.
- The optional gds_connection_tenant_code, gds_connection_system_code, and gds_connection_code identify one configured Connection; all three are present together or null together.
- Bronze/Silver/Gold placement uses the owner's configured active GDS Connection, even when its placement Tenant differs from the owner.
- For Databricks evidence SQL, match the Object's `source_tenant_code` to this Tenant and use `tenant_catalog`, not `gds_admin_catalog` or the shared Connection Tenant's catalog. Source uses its foreign catalog. Follow [query scope](../../query-scope.md#resolve-coordinates-and-access).

## Checks before reuse

Apply the [shared read-only checks](../index.md#using-read-only-tables) to the exact Keys, Fields, and dependencies above. Resolve table-specific conditions under “How authoring uses these values.”

[All metadata tables](../index.md) · [Common validation](../validation.md)
