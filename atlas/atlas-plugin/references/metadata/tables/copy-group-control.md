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
- Cursor format and inclusive/exclusive filter boundaries depend on the consumer. Member/date-precedence rules remain deferred; they do not block the default non-member setup.
- Follow [shared editing rules](../editing.md); validate the complete effective result and preserve unrelated fields.

## Validation checklist

Source-review coverage only; see [status meanings and common checks](../validation.md).

| Rule | Check / why | Database | MCP backend | Local | Status |
|---|---|---|---|---|---|
| `copy_group_control.shape` | Complete Copy Group key; nullable Member Group; date/time nullable; watermark null or nonblank. Reject malformed complete records before staging. | Column types, nullability and selected CHECKs; not exact JSON shape. | Strict Pydantic record; unknown fields forbidden. | Published JSON Schema and portable record rules. | Existing; not parity-tested |
| `copy_group_control.unique` | Copy Group + Member Group unique; null Member Group counts as one group-level identity. Existing controls retain their keys regardless of parent activity. | Unique constraint/index. | Staged and effective uniqueness. | Pending/effective and cross-dataset uniqueness. | Existing; not parity-tested |
| `copy_group_control.references` | Copy Group and optional Member Group must share supplied Tenant/System. Resolve dependencies using snapshot plus pending rows. | FK/composite FK and Apply joins. | Effective reference validation. | Effective natural-key reference validation. | Existing; not parity-tested |
| `copy_group_control.scope` | Record tenant_code must match selected change-set Tenant. Keep edits in the authorized Tenant. | Apply joins owner and permitted Object connections. | Tenant-scope validation. | Snapshot-based Tenant-scope validation. | Existing; not parity-tested |
| `copy_group_control.member-required` | Member-based execution deferred. New default controls have a null Member Group; preserve existing member references without inventing additional requirements. | Nullable Member Group FK still applies. | Existing shape/reference rules still apply. | No new member-required semantic check. | Deferred by user; not a pending check |
| `copy_group_control.watermark` | New controls use null; framework maintains subsequent values. For explicit corrections, verify extraction-specific serialization; nonblank alone does not prove validity. | Nonblank CHECK; no extraction-specific semantics. | Nonblank shape only. | Nonblank shape; semantic review only when supplying/correcting a value. | Review |
| `copy_group_control.timestamp-offset` | Use an explicit offset for last-run timestamps. Avoid timezone-dependent interpretation. | TIMESTAMPTZ accepts offset-free input using session timezone. | datetime accepts naive values; offset requirement not located. | Date-time parser permits missing offset. | Review |
| `copy_group_control.live-dependencies` | Re-resolve dependencies at Apply; reject unexpected affected-row count. Snapshot checks cannot guarantee current server state. | Atomic Apply dependency/row-count check. | Server Apply result; do not infer success locally. | Cannot prove offline; retain server result. | Server-only |

## Source pointers

Development provenance; these source files are not runtime dependencies of the packaged skill.

- `mcp_server/gds_etl_workbench/domain/metadata_records.py:29,284,290,291`.
- `mcp_server/gds_etl_workbench/domain/snapshots/metadata_guidance.py:74,79,84,204`.
- `database/02_core.sql:348,349,352,356,362,380,382`.
- `database/16_mcp_metadata_apply.sql:747,767,781`.
- `plugins/v2/gds/skills/gds/workbench/validation/common.js:26,357,525`.
- `mcp_server/gds_etl_workbench/domain/snapshots/metadata.py:181,493,495`.
- `mcp_server/gds_etl_workbench/application/change_sets/metadata_validation.py:103,354,474,533`.
- `plugins/v2/gds/skills/gds/workbench/validation/metadata.js:11,177,241`.

[All metadata tables](../index.md) · [Common validation](../validation.md)
