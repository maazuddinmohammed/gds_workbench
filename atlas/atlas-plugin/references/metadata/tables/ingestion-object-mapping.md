# Ingestion object mapping — `core.ingestion_object_mapping`

A registered Source-to-Bronze Object link used by Copy selection and as ingestion provenance. Multiple Source Objects may feed the same Bronze Object.

**Datasets:** `ingestion_object_mapping`.
**Change Set:** editable.

## Keys

- Natural key: `source_tenant_code`, `source_system_code`, `source_connection_code`, `source_object_schema`, `source_object_name`, `target_tenant_code`, `target_system_code`, `target_connection_code`, `target_object_schema`, `target_object_name`.
- No additional unique tuple is published in the Snapshot registry.
- Use the published key normalization. Database IDs are not authoring fields.

## Fields

Every field is listed explicitly. Exact current MCP/Snapshot schemas remain authoritative if the contract changes.

| Field | Accepted value / presence | Meaning and use |
|---|---|---|
| `source_tenant_code` | string; minLength=1; maxLength=100; pattern=\S; required | Tenant component of the source Object's physical Connection key; not a substitute for the Object's source-owner field. Reference: [object](object.md). |
| `source_system_code` | string; minLength=1; maxLength=100; pattern=\S; required | System code of the source physical endpoint; resolve the complete referenced key. Reference: [object](object.md). |
| `source_connection_code` | string; minLength=1; maxLength=100; pattern=\S; required | Connection code of the source physical endpoint; resolve the complete referenced key. Reference: [object](object.md). |
| `source_object_schema` | string; minLength=1; maxLength=400; pattern=\S; required | Object schema of the source physical endpoint; resolve the complete referenced key. Reference: [object](object.md). |
| `source_object_name` | string; minLength=1; maxLength=400; pattern=\S; required | Object name of the source physical endpoint; resolve the complete referenced key. Reference: [object](object.md). |
| `target_tenant_code` | string; minLength=1; maxLength=100; pattern=\S; required | Tenant component of the target Object's physical Connection key; Bronze normally uses the selected source Tenant's configured GDS placement. Reference: [object](object.md). |
| `target_system_code` | string; minLength=1; maxLength=100; pattern=\S; required | System code of the target physical endpoint; resolve the complete referenced key. Reference: [object](object.md). |
| `target_connection_code` | string; minLength=1; maxLength=100; pattern=\S; required | Connection code of the target physical endpoint; resolve the complete referenced key. Reference: [object](object.md). |
| `target_object_schema` | string; minLength=1; maxLength=400; pattern=\S; required | Object schema of the target physical endpoint; resolve the complete referenced key. Reference: [object](object.md). |
| `target_object_name` | string; minLength=1; maxLength=400; pattern=\S; required | Object name of the target physical endpoint; resolve the complete referenced key. Reference: [object](object.md). |
| `is_active` | `false`, `true`; required | Default true for new records unless requested otherwise. Copy selection requires an active Copy Group, Copy and this mapping. False skips the pair without changing other stored flags. Preserve existing values on unrelated edits. |

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

Source-review coverage only; see [status meanings and common checks](../validation.md).

| Rule | Check / why | Database | MCP backend | Local | Status |
|---|---|---|---|---|---|
| `ingestion_object_mapping.shape` | Complete source and target Object keys; required is_active boolean. Reject malformed complete records before staging. | Column types, nullability and selected CHECKs; not exact JSON shape. | Strict Pydantic record; unknown fields forbidden. | Published JSON Schema and portable record rules. | Existing; not parity-tested |
| `ingestion_object_mapping.unique` | Source Object + target Object pair unique. Prevent duplicate identity; inactive rows still reserve their keys. | Unique constraint/index. | Staged and effective uniqueness. | Pending/effective and cross-dataset uniqueness. | Existing; not parity-tested |
| `ingestion_object_mapping.references` | Both Object endpoints must resolve. Resolve dependencies using snapshot plus pending rows. | FK/composite FK and Apply joins. | Effective reference validation. | Effective natural-key reference validation. | Existing; not parity-tested |
| `ingestion_object_mapping.distinct` | Source and target Object must differ after key normalization. Prevent a self-copy mapping. | source_object_id <> target_object_id CHECK. | Pydantic model validator. | Portable ingestion_object_endpoints rule. | Existing; not parity-tested |
| `ingestion_object_mapping.scope` | Both Objects must belong to selected Tenant; Connections must be owned or configured GDS. Keep edits in the authorized Tenant. | Apply joins owner and permitted Object connections. | Tenant-scope validation. | Snapshot-based Tenant-scope validation. | Existing; not parity-tested |
| `ingestion_object_mapping.selection` | Copy Group, Copy and Object Mapping must all be active to pass selection. Explain which flag causes skipping; intentional inactivity is valid metadata. | Boolean storage; no cross-record activation constraint required. | Metadata validation does not prove external selection. | Proposed readiness explanation, not an inactive-record error. | Proposed; user-confirmed consumer rule |
| `ingestion_object_mapping.target-shape` | Each incoming dataset must support the Bronze fields/expressions actually used. Allow extra source columns, shared targets, and constants; identify missing inputs or incompatible outputs. | No physical payload/expression compatibility constraint. | Compatibility check not located. | Proposed per-input check using definitions and permitted evidence. | Proposed; user-confirmed consumer rule |
| `ingestion_object_mapping.live-dependencies` | Re-resolve dependencies at Apply; reject unexpected affected-row count. Snapshot checks cannot guarantee current server state. | Atomic Apply dependency/row-count check. | Server Apply result; do not infer success locally. | Cannot prove offline; retain server result. | Server-only |

## Source pointers

Development provenance; these source files are not runtime dependencies of the packaged skill.

User-confirmed framework behavior supersedes the older one-Source/one-Bronze convention: shared Bronze targets and target-driven column selection are supported. This does not establish every possible Object Mapping cardinality or connector behavior.

- `mcp_server/gds_etl_workbench/domain/metadata_records.py:29,189,190,203`.
- `CONTEXT.md:135`.
- `mcp_server/gds_etl_workbench/domain/snapshots/metadata.py:178,427,436`.
- `mcp_server/gds_etl_workbench/application/change_sets/metadata_validation.py:354,425,474,533`.
- `database/02_core.sql:237,246,250,258`.
- `plugins/v2/gds/skills/gds/references/orchestration-rules.md:7`.
- `plugins/v2/gds/skills/gds/workbench/validation/common.js:203,357,525`.
- `plugins/v2/gds/skills/gds/workbench/validation/metadata.js:11,177,241`.
- `database/16_mcp_metadata_apply.sql:507,550`.

[All metadata tables](../index.md) · [Common validation](../validation.md)
