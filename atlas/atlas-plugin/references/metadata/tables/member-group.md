# Member group — `core.member_group`

A named Tenant/System member grouping referenced by Copy Group Control records, with optional initial-load date.

A Member Group applies an optional filter to a Copy Group through Copy Group Control in the same Tenant/System. Its [Members](member.md) specify filter codes and Attribute names. Use this configuration only when explicitly requested; ordinary Copy Groups default is_member_group_required=false.

**Datasets:** `member_group`.
**Change Set:** editable.

## Keys

- Natural key: `tenant_code`, `system_code`, `member_group_name`.
- No additional unique tuple is published in the Snapshot registry.
- Use the published key normalization. Database IDs are not authoring fields.

## Fields

Every field is listed explicitly. Exact current MCP/Snapshot schemas remain authoritative if the contract changes.

| Field | Accepted value / presence | Meaning and use |
|---|---|---|
| `value` | any valid JSON; optional; null allowed | Optional additional details. Preserve existing JSON; populate only when requested. No implied execution behavior. |
| `tenant_code` | string; minLength=1; maxLength=100; pattern=\S; required | Owning Tenant code for this group/record; match the selected Change Set Tenant. Reference: [tenant](../read-only/tenant.md). |
| `system_code` | string; minLength=1; maxLength=100; pattern=\S; required | Stable code identifying the System. Reference: [system](../read-only/system.md). |
| `member_group_name` | string; minLength=1; maxLength=200; pattern=\S; required | Name identifying the Member Group. |
| `member_group_description` | string; required; null allowed | Plain-language description of the Member Group. Provide concise business or operational context; use null when no description is available. |
| `member_group_initial_load_date` | string; format=date; required; null allowed | Optional initial-load date attached to the Member Group. ISO date or null; precedence relative to the control-level date needs runtime confirmation. |
| `is_active` | `false`, `true`; required | Default true if a new record is explicitly requested; preserve existing values on unrelated edits. Control state and parent Copy Group activation are separate. |

## References and dependencies

- `tenant_code` → [tenant](../read-only/tenant.md): `tenant_code`. Required reference.
- `system_code` → [system](../read-only/system.md): `system_code`. Required reference.
- Referenced by: [copy group control](copy-group-control.md).

## Making changes

- Create Member Groups only when the user explicitly requests Member filtering. Preserve existing configuration in unrelated edits.
- The Member Group and referencing Copy Group Control must share Tenant and System.
- Preserve existing initial-load dates unless the requested operational change requires another value.
- Do not infer date precedence or consumer-specific SQL from this optional filter. The external orchestration framework owns execution.
- Follow [shared editing rules](../editing.md); validate the complete effective result and preserve unrelated fields.

## Validation checklist

Enforcement is explained in [common checks](../validation.md#interpreting-table-checklists); run the local validator, then review anything marked for you.

These describe the existing dataset contract. They do not require creating Member Group records or enabling Member filtering automatically.

| Rule | Check / why | Enforced by |
|---|---|---|
| `member_group.shape` | Tenant/System/name required; name nonblank <=200; optional date/description; explicit active boolean. Reject malformed complete records before staging. | Local validator + server |
| `member_group.unique` | Tenant + System + normalized Member Group name unique. Prevent duplicate identity; inactive rows still reserve their keys. | Local validator + server |
| `member_group.references` | Tenant and System must exist. Resolve dependencies using snapshot plus pending rows. | Local validator + server |
| `member_group.scope` | Record tenant_code must match selected change-set Tenant. Keep edits in the authorized Tenant. | Local validator + server |
| `member_group.date` | Initial load date is a valid calendar date or null. Avoid ambiguous or impossible dates. | Local validator + server |
| `member_group.live-dependencies` | Re-resolve dependencies at Apply; reject unexpected affected-row count. Snapshot checks cannot guarantee current server state. | Server only, at Apply |

[All metadata tables](../index.md) · [Common validation](../validation.md)
