# Silver or Gold Target Registration

`silver` requires applied active Logical; `gold` requires applied active Dimensional. Use fresh
Snapshots.

Load each compact Metadata dataset contract only immediately before that dataset's first batch.

Automatic uses one Object per active Entity and one target Attribute per modeled Attribute. Reuse
compatible targets; splits, merges, and exceptions use Custom.

Resolve destination Object Tenant, System, Connection, schema, and Object Type from one pattern. For
a global GDS destination, use one active `tenant_metadata_discovery_scope`: set
`tenant_code=scope_tenant_code`, `system_code=connection_system_code`, and its exact Connection/schema.
The Object Tenant may differ from the Connection owner. If no unambiguous pattern exists, ask once;
never substitute the session, Model, or source Tenant/System. Allow explicit target overrides.

Model policy fields are independently optional. Apply present `silver_model_naming_instructions` or `gold_model_naming_instructions` in agent naming work. Add every configured audit/technical column exactly from `silver_model_audit_columns_template`, `gold_model_technical_columns_template`, or `gold_model_audit_columns_template` for its route. Missing policy fields never block Target Registration; never invent their contents.

Project one in-memory target definition directly into:

- Databricks DDL with deterministic Databricks types, nullability, and dependency order.
- Complete Metadata pending records.

Always ask whether to include `process_group` and `process` in the same Metadata task. Include them only
when the exact Copy Group, Process type, execution order, location, and executable are known, and
bind each Process to its target Object. Otherwise register targets only; never invent runtime
metadata or postpone target registration behind future Code.

Never parse DDL into Metadata. Preserve existing fields. New records default active, unlocked, and unmapped. Propagate source masking. Without evidence, leave batch, purge, frequency, custom, and transformation controls null/false. Never narrow types silently.

Emit PK/FK clauses only from complete active model keys/relationships and use `NOT ENFORCED NORELY`. Never guess UNIQUE/CHECK or emit RELY.

Review DDL and Metadata together, but Apply only the Metadata Change Set. DDL stays local. After Metadata Apply mark Metadata stale and stop. Target Registration never creates or stages `model_scope`; an authorized owner handles later scope activation through the separate governed path. Mapping remains a separate later task with fresh readiness after that activation is applied and the Model Snapshot is replaced.
