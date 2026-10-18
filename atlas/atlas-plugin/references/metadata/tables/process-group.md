# Process group — `core.process_group`

A Tenant/System/Zone processing group linked to the actual Copy Group whose ingestion precedes relevant processing.

**Datasets:** `process_group`.
**Change Set:** editable.

## Keys

- Natural key: `tenant_code`, `system_code`, `zone_code`, `process_group_name`.
- No additional unique tuple is published in the Snapshot registry.
- Use the published key normalization. Database IDs are not authoring fields.

## Fields

Every field is listed explicitly. Exact current MCP/Snapshot schemas remain authoritative if the contract changes.

| Field | Accepted value / presence | Meaning and use |
|---|---|---|
| `value` | any valid JSON; optional; null allowed | Optional additional details. Preserve existing JSON; populate only when requested. No implied execution behavior. |
| `tenant_code` | string; minLength=1; maxLength=100; pattern=\S; required | Owning Tenant code for this group/record; match the selected Change Set Tenant. Reference: [tenant](../read-only/tenant.md), [copy group](copy-group.md). |
| `system_code` | string; minLength=1; maxLength=100; pattern=\S; required | Stable code identifying the System. Reference: [system](../read-only/system.md), [copy group](copy-group.md). |
| `zone_code` | string; minLength=1; maxLength=30; required | Registered Zone identifying the group and its execution phase: selected Silver groups finish before Gold starts. Not automatically derived from the target Object. Reference: [zone](../read-only/zone.md). |
| `process_group_name` | string; minLength=1; maxLength=200; pattern=\S; required | Name identifying the Process Group. |
| `process_group_description` | string; required; null allowed | Plain-language description of the Process Group. Provide concise business or operational context; use null when no description is available. |
| `copy_group_name` | string; minLength=1; maxLength=200; pattern=\S; required | Actual Copy Group in this group's Tenant/System; ties processing selection to relevant ingestion. Reference: [copy group](copy-group.md). |
| `process_group_dependency_order` | integer; 1–2147483647; required | Default 1 for new groups; mutable outside the natural key. Equal levels permit concurrent groups in one Zone phase; lower levels complete successfully before higher levels. |
| `is_active` | `false`, `true`; required | Default true for new records unless requested otherwise. False retains the existing record and identity. Preserve existing values on unrelated edits. |

## Dependency order

The field is implemented in fresh-install SQL, backend records/Apply, Snapshot schemas and web API reads. Write it explicitly in every complete Process Group payload. The default 1 is for new groups; never infer historical dependencies or silently replace an existing value.

The field belongs to Process Group. Systems select groups; they do not carry this ordering. Groups at the same level and Zone phase pool their Processes by process_execution_order; see [execution behavior](process.md#execution-behavior). Metadata records this schedule; execution remains the orchestration framework's responsibility.

Existing installations require the separately reviewed backend/database upgrade and operator review of historical group orders. Readiness rejects the old schema; refreshing a Snapshot cannot upgrade it. Fresh-install scripts are not an upgrade path; review any existing database transition separately.

## References and dependencies

- `tenant_code` → [tenant](../read-only/tenant.md): `tenant_code`. Required reference.
- `system_code` → [system](../read-only/system.md): `system_code`. Required reference.
- `zone_code` → [zone](../read-only/zone.md): `zone_code`. Required reference.
- `tenant_code`, `system_code`, `copy_group_name` → [copy group](copy-group.md): `tenant_code`, `system_code`, `copy_group_name`. Required reference.
- Referenced by: [process](process.md).

## Making changes

- The referenced Copy Group must have the same Tenant and System.
- Reuse the actual ingestion group identity. A null trigger selector selects applicable groups; it is not a stored Copy Group name.
- Review ingestion prerequisites and Process dependencies before splitting groups or changing the Copy Group link. Moving existing Processes between groups changes their keys and requires manual database correction.
- Changing the Copy Group link updates the existing group. Changing Tenant/System/Zone/name requires the user's [manual database correction](../editing.md#manual-natural-key-changes).
- Changing dependency order is an ordinary update to the existing group; review scheduling impact. It does not change the group's natural key or the keys of its Processes.
- Group Zone controls the pipeline phase. Normally use target Objects from that Zone, but allow cross-Zone cases without an equality constraint, warning or automatic correction.
- Follow [shared editing rules](../editing.md); validate the complete effective result and preserve unrelated fields.

## Pipeline sequence

1. Resolve the trigger's Tenant, Systems and group selectors; see [pipeline selection](copy-group.md#pipeline-selection).
2. Select the applicable Copy Groups and Copies, respecting activation gates.
3. Load Source → landing → Bronze.
4. Select Process Groups linked to those Copy Groups, then their Processes.
5. Run selected Silver Process Groups to successful completion before Gold. Within each Zone phase, schedule by Process Group dependency order, then Process execution order across groups at that level; see [execution behavior](process.md#execution-behavior).

The Copy Group link therefore affects which processing follows ingestion. Do not select unrelated Process Groups merely because they share a Tenant or System.

## Validation checklist

Enforcement is explained in [common checks](../validation.md#interpreting-table-checklists); run the local validator, then review anything marked for you.

| Rule | Check / why | Enforced by |
|---|---|---|
| `process_group.shape` | Tenant/System/Zone/name and Copy Group required; name nonblank <=200; nullable description; active boolean. Reject malformed complete records before staging. | Local validator + server |
| `process_group.unique` | Tenant + System + Zone + normalized Process Group name unique. Prevent duplicate identity; inactive rows still reserve their keys. | Local validator + server |
| `process_group.references` | Tenant/System/Zone exist; Copy Group matches the same Tenant/System. Resolve dependencies using snapshot plus pending rows. | Local validator + server |
| `process_group.scope` | Record tenant_code must match selected change-set Tenant. Keep edits in the authorized Tenant. | Local validator + server |
| `process_group.live-dependencies` | Re-resolve dependencies at Apply; reject unexpected affected-row count. Snapshot checks cannot guarantee current server state. | Server only, at Apply |
| `process_group.dependency-order` | Required positive int32; default 1 for new groups; outside natural key; repeated levels allowed. | Local validator + server |

[All metadata tables](../index.md) · [Common validation](../validation.md)
