# Ingestion object mapping — `core.ingestion_object_mapping`

A registered Source-to-Bronze Object link used by Copy selection and as ingestion provenance. Multiple Source Objects may feed the same Bronze Object.

**Datasets:** `ingestion_object_mapping`.
**Change Set:** editable.

## Keys

- Natural key: `source_tenant_code`, `source_system_code`, `source_connection_code`, `source_object_schema`, `source_object_name`, `target_tenant_code`, `target_system_code`, `target_connection_code`, `target_object_schema`, `target_object_name`.
- No additional unique tuple is published in the Snapshot registry.
- Use the published key normalization. Database IDs are not authoring fields.

## Fields

Run `describe --dataset ingestion_object_mapping` for every field's type, limits, required and null rules, description and population guidance. This table lists only fields with rules that `describe` does not state.

| Field | Meaning and use |
|---|---|
| `source_tenant_code` | Tenant component of the source Object's physical Connection key; not a substitute for the Object's source-owner field. Reference: [object](object.md). |
| `source_system_code` | System code of the source physical endpoint; resolve the complete referenced key. Reference: [object](object.md). |
| `source_connection_code` | Connection code of the source physical endpoint; resolve the complete referenced key. Reference: [object](object.md). |
| `source_object_schema` | Object schema of the source physical endpoint; resolve the complete referenced key. Reference: [object](object.md). |
| `source_object_name` | Object name of the source physical endpoint; resolve the complete referenced key. Reference: [object](object.md). |
| `target_tenant_code` | Tenant component of the target Object's physical Connection key; Bronze normally uses the selected source Tenant's configured GDS placement. Reference: [object](object.md). |
| `target_system_code` | System code of the target physical endpoint; resolve the complete referenced key. Reference: [object](object.md). |
| `target_connection_code` | Connection code of the target physical endpoint; resolve the complete referenced key. Reference: [object](object.md). |
| `target_object_schema` | Object schema of the target physical endpoint; resolve the complete referenced key. Reference: [object](object.md). |
| `target_object_name` | Object name of the target physical endpoint; resolve the complete referenced key. Reference: [object](object.md). |
| `is_active` | Default true for new records unless requested otherwise. Copy selection requires an active Copy Group, Copy and this mapping. False skips the pair without changing other stored flags. Preserve existing values on unrelated edits. |

## References and dependencies

- `source_tenant_code`, `source_system_code`, `source_connection_code`, `source_object_schema`, `source_object_name` → [object](object.md): `tenant_code`, `system_code`, `connection_code`, `object_schema`, `object_name`. Required reference.
- `target_tenant_code`, `target_system_code`, `target_connection_code`, `target_object_schema`, `target_object_name` → [object](object.md): `tenant_code`, `system_code`, `connection_code`, `object_schema`, `object_name`. Required reference.
- Referenced by: [ingestion attribute mapping](ingestion-attribute-mapping.md), [copy](copy.md).

## Making changes

- Resolve both complete physical Object keys; their source_tenant_code ownership must match the locked Tenant.
- Endpoints must differ. Existing DB uniqueness is for the complete source/target pair, not one target per source.
- Multiple Source Objects may feed the same Bronze Object. Check each incoming structure against the Bronze projection; do not impose one-to-one mapping or target-only uniqueness.
- Copy selection requires CopyGroup.is_active AND Copy.is_active AND ObjectMapping.is_active. Any false skips the Copy; all true satisfy this activation gate, while other execution prerequisites still apply. An intentionally disabled configuration is valid metadata.
- Bronze Attributes and their custom code determine loaded columns. Source extraction may contain extra columns; Attribute Mapping records are optional and do not drive ingestion. See [Bronze projection](attribute.md#custom-select-expressions).
- Changing either endpoint of an existing mapping requires the user's [manual database correction](../editing.md#manual-natural-key-changes); the agent supplies instructions only.
- Copy records and any supplied Attribute Mapping records depend on this exact pair; assess affected records when changing or deactivating the link. Do not create Attribute Mappings merely to complete ingestion setup.
- Follow [shared editing rules](../editing.md); validate the complete effective result and preserve unrelated fields.

## Validation checklist

Enforcement is explained in [common checks](../validation.md#interpreting-table-checklists); run the local validator, then review anything marked for you.

| Rule | Check / why | Enforced by |
|---|---|
| `ingestion_object_mapping.shape` | Complete source and target Object keys; required is_active boolean. Reject malformed complete records before staging. | Local validator + server |
| `ingestion_object_mapping.unique` | Source Object + target Object pair unique. Prevent duplicate identity; inactive rows still reserve their keys. | Local validator + server |
| `ingestion_object_mapping.references` | Both Object endpoints must resolve. Resolve dependencies using snapshot plus pending rows. | Local validator + server |
| `ingestion_object_mapping.distinct` | Source and target Object must differ after key normalization. Prevent a self-copy mapping. | Local validator + server |
| `ingestion_object_mapping.scope` | Both Objects must belong to selected Tenant; Connections must be owned or configured GDS. Keep edits in the authorized Tenant. | Local validator + server |
| `ingestion_object_mapping.selection` | Copy Group, Copy and Object Mapping must all be active to pass selection. Explain which flag causes skipping; intentional inactivity is valid metadata. | Your review (no automated check) |
| `ingestion_object_mapping.target-shape` | Each incoming dataset must support the Bronze fields/expressions actually used. Allow extra source columns, shared targets, and constants; identify missing inputs or incompatible outputs. | Your review (no automated check) |
| `ingestion_object_mapping.live-dependencies` | Re-resolve dependencies at Apply; reject unexpected affected-row count. Snapshot checks cannot guarantee current server state. | Server only, at Apply |

## Confirmed behavior

Several Source Objects may share one Bronze target, and Bronze metadata selects the loaded columns. This does not establish every possible Object Mapping cardinality or connector behavior.

[All metadata tables](../index.md) · [Common validation](../validation.md)
