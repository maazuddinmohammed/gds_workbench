# System — `core.system`

Registered named system providing business and technical context; classified by a System Type.

**Datasets:** `system`.
**Change Set:** read-only; cannot be staged.

## Keys

- Natural key: `system_code`.
- No additional unique tuple is published in the Snapshot registry.
- Use the published key normalization. Database IDs are not authoring fields.

## Fields

Run `describe --dataset system` for every field's type, limits, required and null rules, description and population guidance. This table lists only fields with rules that `describe` does not state.

| Field | Meaning and use |
|---|---|
| `value` | Optional additional details. Preserve existing JSON; populate only when requested. No implied execution behavior. |

## References and dependencies

- `system_type_code` → [system type](system-type.md): `system_type_code`. Required reference.
- Referenced by: [connection](connection.md), [object](../tables/object.md), [copy group](../tables/copy-group.md), [member group](../tables/member-group.md), [process group](../tables/process-group.md).

## How authoring uses these values

Resolve system_code for Object placement and Copy/Process group ownership keys. Connections associate a System with a Tenant. Source workflows use the System's description and type as context.

- Foundational, operator-managed context; not editable through Metadata Change Sets.
- system_code is a registered global natural key; the System record itself has no tenant_code.
- system_type_code must resolve to an existing System Type.
- Use the System selected through actual Connection placement or source context; do not infer it from a name.
- Systems determine group selection. The agreed dependency order belongs to [Process Group](../tables/process-group.md#dependency-order); no System execution-order field is needed for this design.

## Checks before reuse

Apply the [shared read-only checks](../index.md#using-read-only-tables) to the exact Keys, Fields, and dependencies above. Resolve table-specific conditions under “How authoring uses these values.”

[All metadata tables](../index.md) · [Common validation](../validation.md)
