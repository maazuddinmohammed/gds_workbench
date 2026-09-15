# Process — `core.process`

One executable registration associated with a target Object and Process Group; registration does not deploy or run it.

Use the [Process metadata workflow](../../../skills/atlas-process-metadata/SKILL.md) for artifact selection, missing runtime details and assignment review. This page owns the field, key and execution rules.

**Datasets:** `process`.
**Change Set:** editable.

## Keys

- Natural key: `tenant_code`, `system_code`, `zone_code`, `process_group_name`, `process_execution_order`, `process_location`, `process_executable`.
- No additional unique tuple is published in the Snapshot registry.
- Target Object and Process Type are not key fields. The same group/order/location/executable identifies one registration even if two candidates name different targets; do not overwrite one while treating them as separate invocations.
- Use the published key normalization. Database IDs are not authoring fields.
- `process_location` and `process_executable` retain exact case/spaces; order alone is not unique.
- The stored Process has no independent Zone column. Snapshot/Change Set zone_code identifies its Process Group; it is not the target Object's Zone.

## Fields

Every field is listed explicitly. Exact current MCP/Snapshot schemas remain authoritative if the contract changes.

| Field | Accepted value / presence | Meaning and use |
|---|---|---|
| `tenant_code` | string; minLength=1; maxLength=100; pattern=\S; required | Owner of the Process Group context; use the locked Tenant. Reference: [process group](process-group.md). |
| `system_code` | string; minLength=1; maxLength=100; pattern=\S; required | System component of the Process Group identity; may differ from the target Object's physical GDS System. Reference: [process group](process-group.md). |
| `zone_code` | string; minLength=1; maxLength=30; required | Zone component of the referenced Process Group key, not an independent Process Zone or the target Object's Zone. Resolve the exact group before authoring. Reference: [process group](process-group.md). |
| `process_group_name` | string; minLength=1; maxLength=200; pattern=\S; required | Name identifying the Process Group. Reference: [process group](process-group.md). |
| `process_execution_order` | integer; maximum=2147483647; exclusiveMinimum=0; required | Positive execution stage within a Process Group dependency level. Equal orders across eligible groups run together; all resulting invocations must succeed before advancement. Part of identity; changing it requires manual correction. |
| `process_location` | string; minLength=1; pattern=\S; required | Path to the logic file in the framework's expected form. Part of identity; preserve case/spaces and the supplied path convention. |
| `process_executable` | string; minLength=1; pattern=\S; required | Actual file name including its extension: .sql for SQL or .python for Python in the confirmed framework. Part of identity; preserve the exact name. |
| `object_tenant_code` | string; minLength=1; maxLength=100; pattern=\S; required | Tenant component of the target Object's physical Connection key; may be the configured GDS Tenant. Reference: [object](object.md). |
| `object_system_code` | string; minLength=1; maxLength=100; pattern=\S; required | System component of the target Object's physical Connection key; distinct from the Process Group System. Reference: [object](object.md). |
| `object_connection_code` | string; minLength=1; maxLength=100; pattern=\S; required | Stable code identifying the Object Connection. Reference: [object](object.md). |
| `object_schema` | string; minLength=1; maxLength=400; pattern=\S; required | Schema containing the Object. Reference: [object](object.md). |
| `object_name` | string; minLength=1; maxLength=400; pattern=\S; required | Name identifying the Object. Reference: [object](object.md). |
| `process_type_name` | string; minLength=1; maxLength=200; pattern=\S; required | File's logic type: SQL or Python in the confirmed framework. Use the corresponding registered Process Type name from the Snapshot. Reference: [process type](../read-only/process-type.md). |
| `is_active` | `false`, `true`; required | Default true for new records unless requested otherwise. False retains the existing record and identity. Preserve existing values on unrelated edits. |

## References and dependencies

- `tenant_code`, `system_code`, `zone_code`, `process_group_name` → [process group](process-group.md): `tenant_code`, `system_code`, `zone_code`, `process_group_name`. Required reference.
- `object_tenant_code`, `object_system_code`, `object_connection_code`, `object_schema`, `object_name` → [object](object.md): `tenant_code`, `system_code`, `connection_code`, `object_schema`, `object_name`. Required reference.
- `process_type_name` → [process type](../read-only/process-type.md): `process_type_name`. Required reference.
- Referenced by: no direct published metadata reference.

## Making changes

- Use applied Code/Mapping/Metadata for known artifacts and targets; obtain unknown locations, types, and dependency order from the user.
- Do not invent triggers, schedules, paths, or file grouping. Several System-specific Process records may refer to the same confirmed artifact.
- Natural key includes execution order, location, and executable. Changing any requires the user's [manual database correction](../editing.md#manual-natural-key-changes); the agent provides instructions and does not stage a replacement.
- Adding an intentional additional invocation at another execution order is ordinary new-record authoring: retain the existing record and add the distinct key. Do not reject or collapse it merely because the executable repeats.
- Order alone is not unique: distinct location/executable pairs can share it and run in parallel within the same Process Group dependency level. Read-tool sorting by process_id does not define execution order.
- process_location and process_executable keep exact case and spaces for identity; lowercase normalization used for name/code/schema fields does not apply.
- Normally choose a target Object in the Process Group's Zone. Cross-Zone references remain allowed: do not add an equality constraint, validation error/warning or automatic correction. Group Zone controls scheduling; target Object Zone does not override it. Group System and Object placement System may differ.
- Follow [shared editing rules](../editing.md); validate the complete effective result and preserve unrelated fields.

## Execution behavior

Agreed scheduling design; the [Process Group dependency-order field](process-group.md#dependency-order) still needs implementation.

1. Start with the selected Silver Process Groups. All their work must succeed before the selected Gold Process Groups start.
2. Within the current Zone phase, take groups at the lowest remaining dependency order across the selected Systems.
3. Pool their Processes by process_execution_order and take the lowest remaining Process order.
4. Run eligible executables in parallel. References to the same executable within this Zone phase, dependency level and Process execution order produce one invocation; later stages may run it again.
5. Wait for every invocation in that Process-order stage to succeed, then advance to the next Process order across those groups.
6. After every Process-order stage in the dependency level succeeds, advance to the next dependency level. Finish all selected Silver levels before starting Gold, regardless of Gold's order numbers.

For example, Silver groups A and B at dependency level 1 run A1/B1 together, then A2/B2 together. Silver group C at dependency level 2 starts afterward; Gold begins only after all selected Silver work succeeds. If five invocations run and one fails, four successes do not permit advancement. Do not infer retry, cancellation or rollback behavior. Other Process Group Zones require their applicable framework contract; do not invent a phase order for them.

Shared executable means the same runnable artifact, not merely two files in the same directory. Reuse is limited to one execution stage in one pipeline run; it does not carry forward across Zone phases, Process orders or dependency levels. For example, the same file may run at order 1 to populate IDs and again at order 3 to resolve a self-lookup after the intervening work succeeds. Both invocations are intentional.

Preserve all Process registrations and target references. Metadata authoring records the intended schedule; orchestration performs execution and stage-local reuse. Do not delete repeated registrations, enforce global executable uniqueness or cache success across stages. Exact artifact matching and any differing invocation context come from the framework contract; do not invent additional authoring restrictions.

These are runtime scheduling rules, not existing database or offline-validator guarantees. Atlas-compatible contracts include Process Group dependency order; orchestration must consume that field according to this schedule. Model mapping_dependency source_system_dependency_order is separate and is not a substitute for the new field.

## Validation checklist

Source-review coverage only; see [status meanings and common checks](../validation.md).

| Rule | Check / why | Database | MCP backend | Local | Status |
|---|---|---|---|---|---|
| `process.shape` | Complete Process Group/Object keys; positive int32 order; nonblank location/executable; Process Type; active boolean. Reject malformed complete records before staging. | Column types, nullability and selected CHECKs; not exact JSON shape. | Strict Pydantic record; unknown fields forbidden. | Published JSON Schema and portable record rules. | Existing; not parity-tested |
| `process.unique` | Process Group + order + exact location + exact executable unique; order alone need not be unique. Same executable at different orders is valid. Existing key changes follow the manual database-change rule. | Unique constraint/index. | Staged and effective uniqueness. | Pending/effective and cross-dataset uniqueness. | Existing; not parity-tested |
| `process.references` | Process Group and Type exist; Object belongs to specified Connection. Resolve dependencies using snapshot plus pending rows. | FK/composite FK and Apply joins. | Effective reference validation. | Effective natural-key reference validation. | Existing; not parity-tested |
| `process.scope` | Process belongs to selected Tenant; referenced Object owner matches and placement is permitted. Keep edits in the authorized Tenant. | Apply joins owner and permitted Object connections. | Tenant-scope validation. | Snapshot-based Tenant-scope validation. | Existing; not parity-tested |
| `process.executable-semantics` | Confirmed convention: SQL/.sql or Python/.python, path plus actual filename. Preserve actual registered type and file spelling; no new global enum or extension rejection rule. | Nonblank CHECKs and Process Type FK. | Text shape and reference checks only. | Show the actual values; runtime artifact existence not proved. | Review; consumer convention, not new enforcement |
| `process.zone-alignment` | Same Object/Process Group Zone is the normal convention; cross-Zone references remain allowed. Group Zone determines execution phase. | No equality constraint. | Keep group/Object references and ownership checks; no Zone-equality rule. | No Zone-equality warning, error or automatic rewrite. | Deferred by user; equality intentionally unenforced |
| `process.live-dependencies` | Re-resolve dependencies at Apply; reject unexpected affected-row count. Snapshot checks cannot guarantee current server state. | Atomic Apply dependency/row-count check. | Server Apply result; do not infer success locally. | Cannot prove offline; retain server result. | Server-only |
| `process.shared-execution` | Reuse applies within one Zone phase, dependency level and Process order in one run. Intentional repetition at later stages is valid; preserve all registrations. | No global executable uniqueness constraint. | Metadata checks must allow distinct keys at different orders; runtime owns reuse. | May preview stages; do not reject repeated executables or claim runtime enforcement. | Runtime-only; not an authoring rejection |

## Source pointers

Development provenance; these source files are not runtime dependencies of the packaged skill.

- `mcp_server/gds_etl_workbench/domain/metadata_records.py:29,343,349`.
- `mcp_server/gds_etl_workbench/domain/snapshots/metadata.py:51,182,544`.
- `database/02_core.sql:465,479,487,490`.
- `database/16_mcp_metadata_apply.sql:1008,1043,1052,1059`.
- `mcp_server/gds_etl_workbench/tools/processing/process_groups.py:110`.
- `plugins/v2/gds/skills/gds/references/workflows/process-registration.md:3`.
- `CONTEXT.md:442`.
- `plugins/v2/gds/skills/gds/workbench/validation/common.js:357,525`.
- `mcp_server/gds_etl_workbench/application/change_sets/metadata_validation.py:354,474,533`.
- `plugins/v2/gds/skills/gds/workbench/validation/metadata.js:11,177,241`.
- `mcp_server/gds_etl_workbench/domain/snapshots/metadata_guidance.py:249`.

[All metadata tables](../index.md) · [Common validation](../validation.md)
