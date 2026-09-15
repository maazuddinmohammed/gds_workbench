# Target definition and projection

Owns registration-specific projection from an applied modeled Entity to Metadata records and optional local DDL. The [skill](../SKILL.md) owns intake and sequence; shared [Object](../../../references/metadata/tables/object.md) and [Attribute](../../../references/metadata/tables/attribute.md) pages own exact fields/defaults, and the [Change Set lifecycle](../../../references/change-set-lifecycle.md) owns submission.

## Resolve placement and ownership

1. Begin with selected active applied Logical records for Silver or Dimensional records for Gold. Reuse recorded schema choices. Resolve one schema for all Entities by default, or a complete explicit Entity/group-to-schema assignment when the user requests a split. A separate default is unnecessary when every Entity is assigned explicitly.
2. Trace each Entity's contributing Objects to their actual `source_tenant_code`. Single-origin target ownership is that source/data owner, not automatically the Model owner or physical Connection Tenant. Several contributing Systems may still have one owner.
3. For mixed owners, use the explicit agreed target owner under [Object ownership](../../../references/metadata/tables/object.md#ownership-and-physical-identity), including a configured GDS Tenant when selected. Generated/standalone designs require a user-supplied owner when it cannot be established. Preserve provenance; do not attach a fictitious physical source.
4. Read the chosen owner's Metadata Tenant record and its complete `gds_connection_tenant_code`, `gds_connection_system_code`, `gds_connection_code`. Resolve that exact active Connection and verify `is_global_data_store:true`. Copy its full placement key, then add the target schema/Object name. Missing configuration is not permission to choose another globally marked Connection.
5. If read-only discovery is needed, `get_tenant_details` identifies `is_tenant_gds_connection:true`. Its current Connection summary lacks physical `tenant_code`; use the Snapshot's full configured key/Connection record, never the requested Tenant header as a substitute. Follow the actual exposed tool contract; no new registration-specific MCP tool is assumed.

Each Object's `source_tenant_code` is its chosen owner; its `tenant_code`, `system_code` and `connection_code` are physical GDS placement. Attribute keys inherit that placement from the target Object. Partition Metadata drafts into [owner roots inside the same working directory](../../../references/workspace-contract.md#model-derived-metadata-owners), without changing the owning Model context used to read design inputs.

Current Binding accepts only targets owned by the Model Tenant. Report a different valid target owner as a Binding limitation; registration cannot grant broader Binding eligibility or silently relabel ownership.

## One definition, two outputs

Build one consistent local target definition containing the selected Entity identity/revision, zone, owner, physical placement, schema/name, complete ordered Attributes and relevant modeled constraints. Reuse the task's work/evidence for material decisions; this is not a mandatory second handoff file or a new persistent schema.

Project this definition independently into the requested outputs:

- Complete changed Metadata record arrays under `metadata-change-set/` for the registration scope, using the selected zone's datasets.
- Optional local Databricks creation DDL for the DDL scope, using the same names, types, nullability, order and own-key generation policy.

Never parse generated DDL back into Metadata or maintain independent definitions that can drift. Check each requested output against the same target definition before review; declining DDL does not block Metadata registration.

| Target decision | Projection rule |
|---|---|
| Object identity | Physical GDS Connection key + confirmed schema + modeled/explicitly selected target name. Preserve exact existing identity on updates. |
| Ownership and zone | Owner goes in `source_tenant_code`; Silver/Gold must match the dataset's zone. Owner/zone are not extra identity components. |
| Object kind | Resolve an active registered Object Type suitable for the physical target; do not invent a `table` lookup code. |
| Definitions | Use applicable modeled business definitions/grain and Attribute meanings. Avoid Zone/storage boilerplate. |
| Attribute inventory | Include every selected active modeled Attribute, including generated keys, constants, technical and audit fields. Preserve approved names and order. |
| Physical types/nullability | Use the applied modeled type with a verified Databricks representation; preserve capacity and semantics. Unknown/unsupported conversion needs resolution, not silent narrowing. |
| Surrogate and natural keys | Follow [keys and audit columns](../../../references/model/keys-and-audit.md). Logical flags project to their Metadata counterparts. Dimensional own-surrogate/business roles inform `is_surrogate_key`/`is_natural_key`; foreign keys are mapped values, not generated identities. |
| Audit/technical fields | Use the approved layer policy for names, exact types, nullability and order. Set operational-metadata classification from field meaning; do not infer a business key from audit membership. |
| Masking | Trace actual physical Attribute contributors and existing protection, including transformations where applicable. Preserve protection unless evidence establishes the output no longer requires it. Missing lineage is not proof of an unprotected field. Resolve unclear protection before finalizing. |
| Batch column | Set `batch_attribute_name` only to the actual active batch Attribute established by the target policy; null when none exists. Column names alone do not establish batch semantics. |
| Remaining fields | Follow published Object/Attribute schemas and shared defaults; preserve unrelated existing values. Silver/Gold unused transformation fields do not carry Mapping logic. |

The Metadata schema has no primary-key constraint field, relationship graph or Entity dependency-order field. Keep these in the Model/target-definition context and applicable DDL design; do not add properties to Metadata records. Likewise, surrogate metadata alone does not create a database-generated identity.

`attribute_inferred_data_type` remains distinct from physical type. Preserve applicable existing values and follow its shared field rules; registration is not an excuse to overwrite inferred types or launch unrelated enrichment.

## Existing targets

Compare desired target definitions with the effective Metadata Snapshot-plus-pending view by full normalized physical identity. Match meaning, owner, zone, complete column inventory, names, types/capacity, nullability, order and key/audit/protection policy. Similar names at another Connection/schema are not the same target.

- Compatible existing active target: reuse it; author only changed unlocked Metadata records. Supported compatible metadata updates belong here and need not start another workflow.
- Extra/inactive/protected existing records: retain them; show differences and their impact on later Binding. Do not discard them to obtain an exact match.
- Conflicting owner/zone/meaning or ambiguous target: resolve the specific conflict before authoring affected records. Ordinary Apply does not transfer ownership or rename natural keys.
- Actual-table changes: present known mismatches and user-operated resolution separately. Do not implement migration/backfill/destructive helpers or fabricate replacement tables. A metadata type/name correction is not evidence that the deployed table changed.

## Choose DDL output

Keep the registration Entity set and DDL Entity set explicit and separate. First follow [existing work and update scope](../../../references/working-method.md#existing-work-and-update-scope). For change-driven work, offer DDL only for affected targets or a selected subset unless the user explicitly requests a wider scope. Otherwise use the [skill's question](../SKILL.md#choose-ddl-output) when the choice is missing:

- **No DDL:** generate no SQL artifact; continue requested Metadata registration.
- **All registration targets:** generate DDL for every Entity in the resolved registration scope, including unchanged existing targets.
- **Selected tables:** resolve the listed Entities/targets to exact applied Model identities. Do not match ambiguous names across schemas or Models automatically.
- **Entire model:** use all active applied Entities in the chosen Model and layer: Logical for Silver, Dimensional for Gold. Reuse the current Model unless another is explicitly selected; resolve an ambiguous Model or layer before generation.

For a DDL scope beyond registration, load the relevant authorized applied Model inputs and resolve ownership, GDS placement and schema assignments using the same rules above. Preserve the registration scope. DDL-only Entities do not create Metadata edits, registration tasks, Stage requests or Applies. Do not mutate session context or existing pending work merely to read another Model.

Record the confirmed choice and resolved Model/layer/Entity list in the existing task. If the requested scope changes, update that selection; do not silently broaden it. Table selection always means the complete table definition, including keys, constants and audit columns.

## DDL generation

Generate complete creation DDL only for the selected DDL targets using the current framework convention `CREATE TABLE IF NOT EXISTS schema.table` without catalog; execution context supplies the catalog. Quote each identifier correctly and use the [key/audit policy](../../../references/model/keys-and-audit.md): only the target's own surrogate receives `BIGINT GENERATED ALWAYS AS IDENTITY`; foreign keys are ordinary typed columns. Every intended modeled column remains in DDL, including framework-populated fields.

Do not claim primary/foreign-key enforcement from a modeled relationship or emit unsupported constraints. Resolve target-platform/version-specific syntax when needed; output generation is not execution. Registered Metadata may not match actual deployed tables, and `IF NOT EXISTS` does not alter an existing definition. State this baseline/limitation with the handoff rather than requiring live SQL for every target.

Persistent target DDL is outside `execute_databricks_sql`'s allowed read/temporary-object operations. Keep it local; do not attempt execution, deployment or an alternate bypass. Read-only evidence queries, when useful and permitted, follow the shared [query scope](../../../references/query-scope.md).

## Registration checks

Run the shared [local validation sequence](../../../references/local-validation.md). Its Metadata validators check field shape, keys, references, ownership and locks. The workflow also reviews complete target projection, DDL selection and deployed-table limitations below; local validation does not prove deployed compatibility.

| Rule | Check / reason |
|---|---|
| `registration.inputs` | Selected records are active applied Logical/Silver or Dimensional/Gold inputs; chosen Model revision and schema assignments still apply. |
| `registration.placement` | Actual source/data owner is resolved; physical target uses that owner's exact configured active GDS Connection, and each Metadata draft uses its owner context. |
| `registration.projection` | Each requested output matches its complete target definition; no missing audit/constant/generated columns, narrowed types, invented schema fields or ordinal collisions. |
| `registration.ddl-scope` | DDL follows the user's resolved table/Model selection or is explicitly not requested; wider DDL coverage does not expand Metadata edits. Every emitted table includes all modeled columns. |
| `registration.protection` | Existing parent/Attribute locks, inactive identities and source-derived masking are preserved; unsupported changes remain explicit. |
| `registration.existing` | Exact target matching and compatible changes are justified; existing-table differences, ownership conflicts and manual-key changes are not hidden by creation DDL. |
| `registration.binding` | Intended downstream targets meet current ownership/layer requirements or the specific Binding limitation is reported. Do not author Binding here. |

Recheck required freshness before handoff/Apply through the shared lifecycle. If a new baseline is needed, reconcile pending edits first. After confirmed Metadata Apply, install fresh Metadata and verify registered targets; do not treat a pre-Apply refresh as proof that proposed changes were applied.

## Source pointers

Existing flow: `plugins/v2/gds/skills/gds/references/workflows/target-registration.md`; DDL conventions: `references/orchestration-rules.md` and `references/model-conventions.md` beneath that GDS skill. These documents specify agent-authored DDL; Atlas retains that approach with the complete-column and optional-output rules above. Field contracts: `mcp_server/gds_etl_workbench/domain/metadata_records.py`; owner placement: `application/change_sets/metadata_validation.py`; Connection discovery: `tools/tenants/get_tenant_details.py`; Binding eligibility: `application/change_sets/model.py`, `model_validation.py` and `database/11_workflow_eligibility.sql`. The old guide's Model-owner default and automatic DDL generation are superseded by the source/data-owner and optional-output rules above.
