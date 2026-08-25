# Silver or Gold Target Registration

Route `silver` requires an applied active Logical model. Route `gold` requires an applied active Dimensional model. Use fresh Metadata and Model Snapshots.

Automatic defaults to one Object per active route Entity and one target Attribute per modeled Attribute. Reuse compatible active targets; splits, merges, and exceptions use Custom.

Resolve destination System, Connection, schema, and Object Type from one consistent target pattern. Never infer it from a source System. Ask once if absent; allow per-target overrides.

Model policy fields are independently optional. Apply present `silver_model_naming_instructions` or `gold_model_naming_instructions` in agent naming work. Add every configured audit/technical column exactly from `silver_model_audit_columns_template`, `gold_model_technical_columns_template`, or `gold_model_audit_columns_template` for its route. Missing policy fields never block Target Registration; never invent their contents.

Project one in-memory target definition directly into:

- Databricks DDL with deterministic Databricks types, nullability, and dependency order.
- Complete Metadata pending records.

Never parse DDL into Metadata. Preserve existing fields. New records default active, unlocked, and unmapped. Propagate source masking. Without evidence, leave batch, purge, frequency, custom, and transformation controls null/false. Never narrow types silently.

Emit PK/FK clauses only from complete active model keys/relationships and use `NOT ENFORCED NORELY`. Never guess UNIQUE/CHECK or emit RELY.

Review DDL and Metadata together, but Apply only the Metadata Change Set. DDL stays local. After Metadata Apply mark Metadata stale and stop. Target Registration never creates or stages `model_scope`; an authorized owner handles later scope activation through the separate governed path. Mapping remains a separate later task with fresh readiness after that activation is applied and the Model Snapshot is replaced.
