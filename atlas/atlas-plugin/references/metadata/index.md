# Metadata table index

Shared domain documentation: table meanings, fields, keys, and rules live here once so workflows can reuse them. Actual Tenant-specific records and registered values come from the Snapshot. Workflow steps and intake belong in the skill.

Read the pages for tables being changed. Open other table pages only when a relationship, field meaning, or failed check needs explanation. Checking a referenced record does not require reading every linked document; do not follow links recursively.

For the Snapshot's file layout, targeted reads and complete-record draft updates, use the shared [Metadata Snapshot guide](../snapshots/metadata.md). Table pages below contain domain meanings rather than repeat those mechanics.

For descriptions and inferred types, use [enrichment quality](enrichment-quality.md): evidence steps, examples and six workflow-specific checks. These supplement the table contracts without changing their field limits.

## Editable tables

All 16 currently accepted Metadata Change Set datasets are listed below, grouped by their 10 physical tables.

| Table reference | Accepted datasets | Purpose |
|---|---|---|
| [object](tables/object.md) | `source_object`, `bronze_object`, `silver_object`, `gold_object` | A physical Object registered at a Connection, owned by a Source Tenant and classified into a Zone; its Attributes are separate records. |
| [attribute](tables/attribute.md) | `source_attribute`, `bronze_attribute`, `silver_attribute`, `gold_attribute` | A physical field/column of an Object, with source/storage type, ordinal, optional expression, and metadata flags. |
| [ingestion object mapping](tables/ingestion-object-mapping.md) | `ingestion_object_mapping` | Source-to-Bronze link used by Copy selection and provenance; multiple Sources may share a Bronze target. |
| [ingestion attribute mapping](tables/ingestion-attribute-mapping.md) | `ingestion_attribute_mapping` | Optional reference correspondence, usually empty. Current ingestion uses Bronze metadata/custom code, not these records, to select columns. |
| [copy group](tables/copy-group.md) | `copy_group` | A Tenant/System ingestion group containing Copy entries and associated execution control state. |
| [member group](tables/member-group.md) | `member_group` | Existing named member grouping. Member-based execution is deferred; preserve records and default new Copy Groups to member-required=false. |
| [copy group control](tables/copy-group-control.md) | `copy_group_control` | Stored ingestion progress for one Copy Group and an optional Member Group. |
| [copy](tables/copy.md) | `copy` | Extraction filters, landing naming/format, order, optional chunking and target loading function for an Object Mapping within a Copy Group. |
| [process group](tables/process-group.md) | `process_group` | A Tenant/System/Zone processing group linked to the actual Copy Group whose ingestion precedes relevant processing. |
| [process](tables/process.md) | `process` | One executable registration associated with a target Object and Process Group; registration does not deploy or run it. |

## Read-only foundational tables

These establish ownership and physical placement. Consult only the page needed to resolve the request; Project is usually unnecessary for a metadata edit.

| Table reference | Read-only dataset | How it is used |
|---|---|---|
| [project](read-only/project.md) | `project` | Registered organizational grouping to which Tenants belong. |
| [tenant](read-only/tenant.md) | `tenant` | Ownership and authorization scope for metadata, Models, and principals; belongs to a Project. |
| [system](read-only/system.md) | `system` | Registered named system providing business and technical context; classified by a System Type. |
| [connection](read-only/connection.md) | `connection` | Registered physical access or placement context joining a Tenant, System, and Connection Type. |

## Read-only lookup tables

Choose actual registered codes/names and read their descriptions. Demo seed values and schema examples are illustrative, not closed allowed lists. Object zone and Tenant visibility have separate field-level enums.

| Table reference | Read-only dataset | Meaning |
|---|---|---|
| [system type](read-only/system-type.md) | `system_type` | Operator-registered classification of a System, with a code, name, and explanatory description. |
| [connection type](read-only/connection-type.md) | `connection_type` | Operator-registered classification of a Connection's technology or connection mechanism. |
| [object type](read-only/object-type.md) | `object_type` | Operator-registered classification of the kind of physical Object. |
| [zone](read-only/zone.md) | `zone` | Registered physical data classification. Current Object datasets separate source, raw Bronze, conformed Silver, and presentation Gold metadata. |
| [chunk type](read-only/chunk-type.md) | `chunk_type` | Registered table-specific or reusable logic for splitting a large initial extraction; opt-in by user request. |
| [file type](read-only/file-type.md) | `file_type` | Operator-registered physical file format classification. |
| [data operation](read-only/data-operation.md) | `data_operation` | Registered target loading function. Source operation remains a required, currently unused reference. |
| [process type](read-only/process-type.md) | `process_type` | Registered file logic type; the confirmed framework uses SQL and Python. |

## Using read-only tables

- Resolve the complete registered key from the Snapshot. Read its description when choosing or interpreting a value; examples are not allowed-value lists.
- Verify activity and consumer support where required. Existence alone does not prove suitability.
- Missing or inconsistent required registrations block the dependent change; use the operator workflow to correct them. These tables cannot be staged in Metadata Change Sets.
- Keep definitions here and live values in Snapshots. Request-specific findings belong with the task; promote a general rule only after confirming its scope.

For example, changing a Copy landing-name pattern needs the Copy page and relevant records. Open File Type documentation if the change raises a format question. Read Tenant or Connection documentation only if ownership or placement is unclear.

Use [editing](editing.md) before constructing records and [validation](validation.md) before reporting results. Current tool contracts and matching Snapshot schemas remain the contract evidence.

## Documentation coverage

- 10 editable physical tables / 16 datasets.
- 4 foundational tables and 8 lookup tables, each with an explicit page.
- 184 current field entries across the 22 table contracts; one proposed Process Group field documented separately.
- 80 table-specific checklist entries, including observed checks, proposed checks, review items, deferred rules, server-only conditions and runtime-only behavior.
- Runtime meanings not established in current source are identified rather than invented.

## Deferred additions

- Copy order compatibility: default copy_source_order=1 is agreed. Current DB/backend/local contracts require unique order within a group; the proposed compatibility change is to [remove that separate uniqueness requirement](tables/copy.md#copy-order-and-default). Copy natural keys stay unchanged; this does not introduce runtime dependency stages.
- `process_group_dependency_order`: agreed new Process Group field for ordering groups across selected Systems within each Zone phase, then pooling their Processes by execution order. See its [proposed contract and implementation coverage](tables/process-group.md#dependency-order). It is not accepted by current payload schemas.
- `member`: new support is deferred from the first release. No Member table or dataset contract was found in the current repository SQL, Snapshot registry or Change Set allowlist. Obtain its actual fields, keys and Member Group relationship before defining database, Snapshot, Change Set, tool and validation support. Do not stage an invented `member` dataset. Preserve existing Member Group records; member-based execution remains deferred.
