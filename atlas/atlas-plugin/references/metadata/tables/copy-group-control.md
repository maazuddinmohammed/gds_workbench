# Copy group control — `core.copy_group_control`

Stored ingestion progress for one Copy Group and an optional Member Group.

**Datasets:** `copy_group_control`.
**Change Set:** editable.

## Keys

- Natural key: `tenant_code`, `system_code`, `copy_group_name`, `member_group_name`.
- No additional unique tuple is published in the Snapshot registry.
- Use the published key normalization. Database IDs are not authoring fields.
- A null `member_group_name` is the group-level control identity; it must not be duplicated.

## Fields

Every field is listed explicitly. Exact current MCP/Snapshot schemas remain authoritative if the contract changes.

| Field | Accepted value / presence | Meaning and use |
|---|---|---|
| `tenant_code` | string; minLength=1; maxLength=100; pattern=\S; required | Owning Tenant code for this group/record; match the selected Change Set Tenant. Reference: [copy group](copy-group.md), [member group](member-group.md). |
| `system_code` | string; minLength=1; maxLength=100; pattern=\S; required | Stable code identifying the System. Reference: [copy group](copy-group.md), [member group](member-group.md). |
| `copy_group_name` | string; minLength=1; maxLength=200; pattern=\S; required | Name identifying the Copy Group. Reference: [copy group](copy-group.md). |
| `member_group_name` | string; minLength=1; maxLength=200; pattern=\S; required; null allowed | Null for new controls under the default non-member setup. Preserve existing identities. A supplied Member Group must share Tenant/System. Reference: [member group](member-group.md). |
| `copy_group_control_initial_load_date` | string; format=date; required; null allowed | Optional initial-load filter date supplied to the framework when the load configuration needs it. Default null; populate only the established filter value, never today's date by assumption. |
| `copy_group_control_last_run_time` | string; format=date-time; required; null allowed | Framework-maintained last-run timestamp. Default null on new controls; preserve existing values during unrelated edits. |
| `copy_group_control_last_run_value` | string; minLength=1; pattern=\S; required; null allowed | Framework-maintained run value/cursor. Default null on new controls; preserve existing serialized values. Its format depends on the extraction contract. |

## References and dependencies

- `tenant_code`, `system_code`, `copy_group_name` → [copy group](copy-group.md): `tenant_code`, `system_code`, `copy_group_name`. Required reference.
- `tenant_code`, `system_code`, `member_group_name` → [member group](member-group.md): `tenant_code`, `system_code`, `member_group_name`. Optional member name; Tenant/System still identify the Copy Group scope.
- Referenced by: no direct published metadata reference.

## Making changes

- When a new control is needed, use null for member_group_name, last-run time and last-run value under the default non-member setup. The framework maintains run values afterward; authoring does not simulate a completed run.
- Initial-load date is an optional framework filter value. Leave it null unless the configured load needs a specific date; do not infer a date or filter operator.
- The framework uses control state to choose the initial or incremental [Copy filter](copy.md#initial-and-incremental-filters). Use its confirmed switching and substitution rules; do not derive them from field names alone.
- Preserve existing dates and run state during unrelated edits. Changing or clearing progress requires an explicit correction request and verified intended values.
- member_group_name=null identifies the unpartitioned control; only one such null-member control is permitted per group.
- Changing Member Group, including null to/from a named group, requires the user's [manual database correction](../editing.md#manual-natural-key-changes). The agent supplies instructions; it does not move progress to a replacement record.
- Cursor format and inclusive/exclusive filter boundaries depend on the consumer. A Member Group identifies the optional filter for this Copy Group; date precedence remains consumer-specific.
- Follow [shared editing rules](../editing.md); validate the complete effective result and preserve unrelated fields.

## Validation checklist

Enforcement is explained in [common checks](../validation.md#interpreting-table-checklists); run the local validator, then review anything marked for you.

| Rule | Check / why | Enforced by |
|---|---|---|
| `copy_group_control.shape` | Complete Copy Group key; nullable Member Group; date/time nullable; watermark null or nonblank. Reject malformed complete records before staging. | Local validator + server |
| `copy_group_control.unique` | Copy Group + Member Group unique; null Member Group counts as one group-level identity. Existing controls retain their keys regardless of parent activity. | Local validator + server |
| `copy_group_control.references` | Copy Group and optional Member Group must share supplied Tenant/System. Resolve dependencies using snapshot plus pending rows. | Local validator + server |
| `copy_group_control.scope` | Record tenant_code must match selected change-set Tenant. Keep edits in the authorized Tenant. | Local validator + server |
| `copy_group_control.member-required` | Default null; set only for an explicitly requested Member filter. | Runtime framework (context only) |
| `copy_group_control.watermark` | New controls use null; framework maintains subsequent values. For explicit corrections, verify extraction-specific serialization; nonblank alone does not prove validity. Validator note: Nonblank shape; semantic review only when supplying/correcting a value. | Your review |
| `copy_group_control.timestamp-offset` | Use an explicit offset for last-run timestamps. Avoid timezone-dependent interpretation. Validator note: Date-time parser permits missing offset. | Your review |
| `copy_group_control.live-dependencies` | Re-resolve dependencies at Apply; reject unexpected affected-row count. Snapshot checks cannot guarantee current server state. | Server only, at Apply |

[All metadata tables](../index.md) · [Common validation](../validation.md)
