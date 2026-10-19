# Copy group — `core.copy_group`

A Tenant/System ingestion group containing Copy entries and associated execution control state.

**Datasets:** `copy_group`.
**Change Set:** editable.

## Keys

- Natural key: `tenant_code`, `system_code`, `copy_group_name`.
- No additional unique tuple is published in the Snapshot registry.
- Use the published key normalization. Database IDs are not authoring fields.

## Fields

Run `describe --dataset copy_group` for every field's type, limits, required and null rules, description and population guidance. This table lists only fields with rules that `describe` does not state.

| Field | Meaning and use |
|---|---|
| `value` | Optional additional details. Preserve existing JSON; populate only when requested. No implied execution behavior. |
| `tenant_code` | Tenant owning the Copy Group; must be the locked Tenant. Reference: [tenant](../read-only/tenant.md). |
| `system_code` | Source System whose ingestion this group organizes; use the registered System code. Reference: [system](../read-only/system.md). |
| `is_member_group_required` | Default false on new records. Member Group filtering is optional and explicit; preserve existing values during unrelated edits. |
| `is_active` | Default true for new records unless requested otherwise; preserve existing values on unrelated edits. False skips all Copies belonging to this group regardless of child active flags; their stored flags remain unchanged. |

## References and dependencies

- `tenant_code` → [tenant](../read-only/tenant.md): `tenant_code`. Required reference.
- `system_code` → [system](../read-only/system.md): `system_code`. Required reference.
- Referenced by: [copy group control](copy-group-control.md), [copy](copy.md), [process group](process-group.md).

## Making changes

- Use the locked Tenant as owner and an existing System; reuse the actual ingestion group where appropriate.
- One System commonly uses one group; split groups select different ingestion/processing sets and require dependency review.
- A null trigger Copy Group selector means all applicable groups for the selected Tenant and Systems; a supplied name selects that group. A selector is not a stored group identity.
- Default new groups to is_member_group_required=false. Initialize Member Groups and Members only when the user requests that filter. Preserve existing member configuration during unrelated edits.
- An inactive Copy Group skips all its Copies. With an active group, Copy and Object Mapping must also be active; see the [selection check](ingestion-object-mapping.md#validation-checklist).
- Renaming requires the user's [manual database correction](../editing.md#manual-natural-key-changes). Instructions must account for child Copy, Copy Group Control, and Process Group references.
- Follow [shared editing rules](../editing.md); validate the complete effective result and preserve unrelated fields.

## Pipeline selection

User-confirmed framework behavior; trigger inputs are separate from Change Set fields.

| Trigger input | Meaning |
|---|---|
| Tenant name | One Tenant for the run. Resolve its registered identity for metadata references. |
| System names | One or multiple comma-separated System names. Select applicable groups across those Systems. |
| Copy Group | Null selects all applicable Copy Groups; a supplied name selects that group within the Tenant/System scope. |
| Member Group | Optional Copy Group filter; use supplied Member Groups only when explicitly requested. |

Selection does not override activation gates. A System may have several Copy Groups; do not impose a one-to-one constraint. An omitted trigger Member Group adds no requested Member filter; [Copy Group Control](copy-group-control.md) member_group_name=null identifies a control without a Member Group. Do not conflate them or enable member-based execution by default.

Selected Copies load Source → landing → Bronze, followed by [Process Group selection](process-group.md#pipeline-sequence).

## Validation checklist

Enforcement is explained in [common checks](../validation.md#interpreting-table-checklists); run the local validator, then review anything marked for you.

| Rule | Check / why | Enforced by |
|---|---|
| `copy_group.shape` | Tenant/System/name required; name nonblank <=200; description nullable; two explicit booleans. Reject malformed complete records before staging. | Local validator + server |
| `copy_group.unique` | Tenant + System + normalized Copy Group name unique. Prevent duplicate identity; inactive rows still reserve their keys. | Local validator + server |
| `copy_group.references` | Tenant and System must exist. Resolve dependencies using snapshot plus pending rows. | Local validator + server |
| `copy_group.scope` | Record tenant_code must match selected change-set Tenant. Keep edits in the authorized Tenant. | Local validator + server |
| `copy_group.member-required` | Default false; enable only for an explicitly requested Member filter. Preserve existing true values. | Runtime framework (context only) |
| `copy_group.live-dependencies` | Re-resolve dependencies at Apply; reject unexpected affected-row count. Snapshot checks cannot guarantee current server state. | Server only, at Apply |

[All metadata tables](../index.md) · [Common validation](../validation.md)
