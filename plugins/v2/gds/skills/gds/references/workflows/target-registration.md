# Silver or Gold Target Registration

Silver requires applied Logical; Gold requires applied Dimensional. Generate one consistent in-memory target definition, then project it into local Databricks DDL and complete Metadata Change Set records. Never parse DDL back into Metadata.

Before building any Silver target definition, DDL, or Metadata record, ask the user to confirm the exact target schema name. Propose the expected schema when evidence supports one; otherwise ask for it. If selected targets use different schemas, present the complete Entity-to-schema assignment together. Do not begin authoring until the user confirms, and ask again if that assignment changes. This gate is required in every interaction mode.

Use PascalCase model-derived Object and Attribute names by default. Include every modeled Attribute, including audit, technical, and constants. Preserve types, nullability, keys, relationships, masking, and dependency order; never narrow or invent them.

For every Bronze/Silver/Gold target:

- `source_tenant_id` is the Model/data-owning Tenant.
- Connection is the active `is_tenant_gds_connection=true` Connection returned for the Model Tenant; require `is_global_data_store=true`. Its Tenant/System identify placement. Never choose a Connection using the global flag alone.
- Create and lock the Metadata Change Set under the Model/data-owning Tenant. Populate Object `tenant_code`, `system_code`, and `connection_code` from the physical GDS Connection, and populate `source_tenant_code` from the Model Tenant.
- Reuse only an exact compatible active target. Otherwise register it.

Apply Metadata only. DDL stays local for user handoff. After Metadata Apply, stop and request a fresh Metadata Snapshot before Model Binding. Do not create Binding, Mapping, Process, or Code in this task.
