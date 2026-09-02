# Silver or Gold Target Registration

Silver requires applied Logical; Gold requires applied Dimensional. Generate one consistent in-memory target definition, then project it into local Databricks DDL and complete Metadata Change Set records. Never parse DDL back into Metadata.

Use PascalCase model-derived Object and Attribute names by default. Include every modeled Attribute, including audit, technical, and constants. Preserve types, nullability, keys, relationships, masking, and dependency order; never narrow or invent them.

For every Bronze/Silver/Gold target:

- `source_tenant_id` is the Model/data-owning Tenant.
- Connection is the active `is_tenant_gds_connection=true` Connection returned for the Model Tenant; require `is_global_data_store=true`. Its Tenant/System identify placement. Never choose a Connection using the global flag alone.
- Reuse only an exact compatible active target. Otherwise register it.

Apply Metadata only. DDL stays local for user handoff. After Metadata Apply, stop and request a fresh Metadata Snapshot before Model Binding. Do not create Binding, Mapping, Process, or Code in this task.
