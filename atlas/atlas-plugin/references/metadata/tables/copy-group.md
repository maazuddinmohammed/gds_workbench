# Copy group — `core.copy_group`

A Tenant/System ingestion group containing Copy entries and associated execution control state.

**Datasets:** `copy_group`.
**Change Set:** editable.

## Keys

- Natural key: `tenant_code`, `system_code`, `copy_group_name`.
- No additional unique tuple is published in the Snapshot registry.
- Use the published key normalization. Database IDs are not authoring fields.

## Fields

Every field is listed explicitly. Exact current MCP/Snapshot schemas remain authoritative if the contract changes.

| Field | Accepted value / presence | Meaning and use |
|---|---|---|
| `tenant_code` | string; minLength=1; maxLength=100; pattern=\S; required | Tenant owning the Copy Group; must be the locked Tenant. Reference: [tenant](../read-only/tenant.md). |
| `system_code` | string; minLength=1; maxLength=100; pattern=\S; required | Source System whose ingestion this group organizes; use the registered System code. Reference: [system](../read-only/system.md). |
| `copy_group_name` | string; minLength=1; maxLength=200; pattern=\S; required | Name identifying the Copy Group. |
| `copy_group_description` | string; required; null allowed | Plain-language description of the Copy Group. Provide concise business or operational context; use null when no description is available. |
| `is_member_group_required` | `false`, `true`; required | Default false on new records. Member-based execution is deferred; preserve existing values during unrelated edits and do not enable it automatically. |
| `is_active` | `false`, `true`; required | Default true for new records unless requested otherwise; preserve existing values on unrelated edits. False skips all Copies belonging to this group regardless of child active flags; their stored flags remain unchanged. |

## References and dependencies

- `tenant_code` → [tenant](../read-only/tenant.md): `tenant_code`. Required reference.
- `system_code` → [system](../read-only/system.md): `system_code`. Required reference.
- Referenced by: [copy group control](copy-group-control.md), [copy](copy.md), [process group](process-group.md).

## Making changes

- Use the locked Tenant as owner and an existing System; reuse the actual ingestion group where appropriate.
- One System commonly uses one group; split groups select different ingestion/processing sets and require dependency review.
- A null trigger Copy Group selector means all applicable groups for the selected Tenant and Systems; a supplied name selects that group. A selector is not a stored group identity.
- Default new groups to is_member_group_required=false. Do not initialize Member Groups for ordinary ingestion; their behavior and the requested Member table will be designed later. Preserve existing member configuration during unrelated edits.
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
| Member Group | Null selects all applicable Member Groups; a supplied name narrows selection. Member execution details remain deferred. |

Selection does not override activation gates. A System may have several Copy Groups; do not impose a one-to-one constraint. Trigger Member Group null means an unrestricted selector, while [Copy Group Control](copy-group-control.md) member_group_name=null identifies a control without a Member Group. Do not conflate them or enable member-based execution by default.

Selected Copies load Source → landing → Bronze, followed by [Process Group selection](process-group.md#pipeline-sequence).

## Validation checklist

Source-review coverage only; see [status meanings and common checks](../validation.md).

| Rule | Check / why | Database | MCP backend | Local | Status |
|---|---|---|---|---|---|
| `copy_group.shape` | Tenant/System/name required; name nonblank <=200; description nullable; two explicit booleans. Reject malformed complete records before staging. | Column types, nullability and selected CHECKs; not exact JSON shape. | Strict Pydantic record; unknown fields forbidden. | Published JSON Schema and portable record rules. | Existing; not parity-tested |
| `copy_group.unique` | Tenant + System + normalized Copy Group name unique. Prevent duplicate identity; inactive rows still reserve their keys. | Unique constraint/index. | Staged and effective uniqueness. | Pending/effective and cross-dataset uniqueness. | Existing; not parity-tested |
| `copy_group.references` | Tenant and System must exist. Resolve dependencies using snapshot plus pending rows. | FK/composite FK and Apply joins. | Effective reference validation. | Effective natural-key reference validation. | Existing; not parity-tested |
| `copy_group.scope` | Record tenant_code must match selected change-set Tenant. Keep edits in the authorized Tenant. | Apply joins owner and permitted Object connections. | Tenant-scope validation. | Snapshot-based Tenant-scope validation. | Existing; not parity-tested |
| `copy_group.member-required` | Member-based execution deferred. Default new groups to false; do not infer required control membership or reset existing true values. | Boolean field; existing default false. | Boolean shape still applies; member semantics not finalized. | Preserve existing values; no new member-consistency rule. | Deferred by user; not a pending check |
| `copy_group.live-dependencies` | Re-resolve dependencies at Apply; reject unexpected affected-row count. Snapshot checks cannot guarantee current server state. | Atomic Apply dependency/row-count check. | Server Apply result; do not infer success locally. | Cannot prove offline; retain server result. | Server-only |

## Source pointers

Development provenance; these source files are not runtime dependencies of the packaged skill.

- `mcp_server/gds_etl_workbench/domain/metadata_records.py:29,266`.
- `mcp_server/gds_etl_workbench/domain/snapshots/metadata_guidance.py:204`.
- `database/02_core.sql:303,309,315,352,518`.
- `database/16_mcp_metadata_apply.sql:656,673,686`.
- `plugins/v2/gds/skills/gds/references/orchestration-rules.md:30`.
- `plugins/v2/gds/skills/gds/workbench/validation/common.js:357,525`.
- `mcp_server/gds_etl_workbench/domain/snapshots/metadata.py:160,465`.
- `mcp_server/gds_etl_workbench/application/change_sets/metadata_validation.py:103,354,474,533`.
- `plugins/v2/gds/skills/gds/workbench/validation/metadata.js:11,177,241,282`.

[All metadata tables](../index.md) · [Common validation](../validation.md)
