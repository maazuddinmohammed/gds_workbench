# Metadata Authoring

Use `inspect_metadata` for focused current context, a fresh Metadata Snapshot for local work, and only Metadata Change Sets for registration.

## Tenant intake

For a new Tenant, author complete Tenant, System, and Connection records from user-supplied or documented facts. Reuse active System Type, Connection Type, Object Type, Zone, and other reference records; never invent a reference code. Related foundational datasets may be staged together because the server resolves their natural-key references against the complete future graph.

When assigning the Tenant's GDS placement Connection, use the exact documented association. For an existing Tenant, `get_tenant_details` identifies it with `is_tenant_gds_connection=true`; require that Connection to be active and `is_global_data_store=true`. Never choose a Connection merely because it is a global data store.

## Ownership and placement

- `source_tenant_id` is always the Tenant whose data the Object contains. It is mandatory; never use the GDS Tenant merely because GDS stores the table.
- A Source Object uses its actual source Connection.
- Bronze, Silver, and Gold use the active Connection identified by `is_tenant_gds_connection=true`. That Connection determines physical Tenant/System placement while `source_tenant_id` remains the data owner.
- No Object may contain data from multiple source Tenants. Multiple Systems or Connections for the same source Tenant are allowed.

## Source and Bronze

Source foreign-catalog metadata records the Connection catalog plus Object schema/name and Attribute foreign-catalog names. Bronze normally converts source values to strings; retain actual source types on Source metadata and ordinary Bronze types on Bronze metadata. Copy and ingestion metadata determine append, overwrite, and batching; never infer those behaviors from type conversion.

Loop through selected Objects and Attributes. Classify each represented, excluded with reason, or blocked. Load each compact dataset schema immediately before its first write, preserve unknown fields, and apply once.
