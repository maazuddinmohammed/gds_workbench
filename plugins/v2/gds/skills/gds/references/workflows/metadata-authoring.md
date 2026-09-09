# Metadata Authoring

Use `inspect_metadata` for focused current context, a fresh Metadata Snapshot for local work, and only Metadata Change Sets for registration.

## Intake

Resolve missing owning Tenant and registered System/Connection. Ask Source-only or Source-plus-Bronze. Use whatever definitions the user has: DDL, schema export, documentation, registered metadata, or authorized data evidence. Extract supported fields into the required datasets; ask precise gaps and explain what the user must obtain. Physical rows are unnecessary when definitions suffice.

For Source-plus-Bronze, deliver Objects/Attributes on both sides, Bronze DDL, ingestion Object/Attribute Mapping, and Copy configuration together. Verify that metadata, names, expressions, DDL, and Copy agree.

## Foundational prerequisite

Tenant, System, and Connection registration must already be complete through the operator/web workflow. It is not a plugin target and is not eligible for an MCP Metadata Change Set. Download a fresh Metadata Snapshot before Metadata Authoring. Reuse active System Type, Connection Type, Object Type, Zone, and other reference records; never invent a reference code.

When assigning the Tenant's GDS placement Connection, use the exact documented association. For an existing Tenant, `get_tenant_details` identifies it with `is_tenant_gds_connection=true`; require that Connection to be active and `is_global_data_store=true`. Never choose a Connection merely because it is a global data store.

## Ownership and placement

- `source_tenant_id` is always the Tenant whose data the Object contains. It is mandatory; never use the GDS Tenant merely because GDS stores the table.
- A Source Object uses its actual source Connection.
- Bronze, Silver, and Gold use the active Connection identified by `is_tenant_gds_connection=true`. That Connection determines physical Tenant/System placement while `source_tenant_id` remains the data owner.
- Source/Bronze retain their Source Tenant. Multiple Systems or Connections for that owner are allowed. Common Silver/Gold targets use Model Tenant ownership; follow Target Registration.
- The Metadata Change Set Tenant and Tenant Lock are always the data-owning Tenant, never the GDS placement Tenant.
- In ingestion Mapping and Copy natural keys, `source_*` and `target_*` Tenant/System/Connection fields identify each Object's physical key. The referenced Objects must both have the locked Tenant as `source_tenant_id`.
- Copy Group, Copy, Process Group, and Process ownership fields use the locked Tenant. Process `object_*` fields use the referenced Object's physical key, which may identify the configured GDS Connection.

## Source and Bronze

Source foreign-catalog metadata records the Connection catalog plus Object schema/name and Attribute foreign-catalog names. Follow the [shared ingestion orchestration rules](../orchestration-rules.md#ingestion-orchestration-pipeline) for one-to-one Source/Bronze correspondence, lowercase snake_case Bronze names, `STRING` storage, extraction aliases, and custom-code casting. Retain actual Source physical types. Copy and ingestion metadata determine append, overwrite, and batching; never infer those behaviors from type conversion.

Loop through selected Objects and Attributes. Classify each represented, excluded with reason, or blocked. Load each compact dataset schema immediately before its first write, preserve unknown fields, and apply once.
