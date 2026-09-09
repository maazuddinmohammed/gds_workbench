# Silver or Gold Target Registration

Silver requires applied Logical; Gold requires applied Dimensional. Generate one consistent in-memory target definition, then project it into local Databricks DDL and complete Metadata Change Set records. Never parse DDL back into Metadata.

Resolve the exact target schema for Silver or Gold before authoring. Reuse an already confirmed assignment; otherwise ask, proposing a schema only when evidence supports it. For multiple schemas, confirm the complete Entity-to-schema assignment together. Reconfirm changed assignments in every mode.

Use PascalCase model-derived Object and Attribute names by default. Include every modeled Attribute, including audit, technical, and constants. Preserve types, nullability, keys, relationships, masking, and dependency order; never narrow or invent them.

For every selected Silver/Gold target:

- Preserve the registered/user-selected `source_tenant_id`. For new targets, propose the Model Tenant as the default; resolve a different requested owner explicitly.
- Connection is the active `is_tenant_gds_connection=true` Connection returned for that chosen Source Tenant; require `is_global_data_store=true`. Its Tenant/System identify placement. Never choose a Connection using the global flag alone.
- Author the Metadata Change Set in that Source Tenant's session and lock. Populate Object `tenant_code`, `system_code`, and `connection_code` from the physical GDS Connection, and `source_tenant_code` from the chosen metadata owner. Use `../session.md` for separate-owner sessions.
- Reuse only an exact compatible active target. Otherwise register it.

Current Model Binding accepts Silver/Gold only when `source_tenant_id` equals the Model Tenant. This is a workflow restriction, not a physical-registration rule. Surface an incompatible owner choice before preparing targets for Binding; never silently relabel the Object or imply another owner's target can currently bind.

Read `../orchestration-rules.md` and `../model-conventions.md`. Create complete `CREATE TABLE IF NOT EXISTS schema.table` DDL for every selected target without catalog. Declare only the target's own surrogate as BIGINT GENERATED ALWAYS AS IDENTITY; foreign keys are ordinary typed columns. All modeled audit columns remain in DDL.

Compare desired definitions with the current Metadata Snapshot, and supply explicit migration statements separately for known existing-table changes. New targets need creation; unchanged ones need no migration. Do not require a live schema lookup. If changes are unclear, ask; if unanswered, deliver complete creation DDL plus known migrations and list unresolved migration work. Never imply CREATE IF NOT EXISTS alters an existing table or invent unsupported ALTER syntax. Scripts assume the physical baseline matches registered metadata. Identity changes or other nontrivial migrations need an explicit supported plan, not a guessed destructive replacement.

Targets can consolidate inputs across authorized Source Tenants. Apply Metadata only. DDL stays local for user handoff. After Metadata Apply, automatically create and install a fresh Metadata Snapshot, then stop before Model Binding. Do not create Binding, Mapping, Process, or Code in this task.
