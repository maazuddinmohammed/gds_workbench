# atlas metadata authoring — design ledger

Design only. No plugin, database, backend, or Workbench implementation.

Historical planning checkpoint. The current skill documentation and complete table references now live in [atlas metadata references](../../atlas/atlas-plugin/references/metadata/index.md). Use those pages for the maintained documentation draft; this note preserves the earlier first-table review.

## Scope

- Author additions and changes across the Tenant's editable metadata.
- Includes Source/Bronze/Silver/Gold Objects and Attributes, ingestion mappings, Copy configuration, and Process configuration.
- Metadata enrichment remains a separate workflow.
- Specialized workflows can reuse these definitions and validators.
- Foundational and reference datasets remain read-only through the current MCP change-set surface.
- User intent determines which records are in scope; choosing this workflow does not imply populating every table.

## Reuse decisions

| Knowledge or output | Home |
|---|---|
| Canonical terms and distinctions | Shared `references/terminology.md`. |
| Table meaning, population guidance, examples | Shared `references/metadata/`, one page per physical table. |
| General edit procedure | Shared `references/metadata/editing.md`. |
| Common validation rules | Shared metadata validation reference; linked by table pages. |
| Table-specific validation rules | Short checklist on that table's page. |
| Exact fields, types, keys, references, fixed values | Existing dataset registry, generated Snapshot schema, and `describe_metadata_dataset`. |
| Repeatable local checks | Reuse shared validation code through CLI and Workbench when implementation is authorized. |
| Findings from a particular task | Task evidence/progress and referenced durable artifacts in its workspace. |

Task findings do not automatically become permanent plugin rules. Promote a finding only when its meaning and general applicability are established.

Use small table-focused modules. Do not create a file or helper for every individual check. Reuse current diagnostic codes where suitable; design labels below are not a new executable rule language.

## Current editable inventory

Registry: [metadata.py](/Users/maazuddinmohammed/main/projects/gds_workbench_v2/mcp_server/gds_etl_workbench/domain/snapshots/metadata.py:372).

There are 16 editable Snapshot datasets representing 10 physical tables. Object and Attribute each have four zone-specific datasets. Those datasets share the same physical-table rules.

| Table | Short meaning | Natural key in Snapshot records |
|---|---|---|
| `core.object` | A physical Object's identity, placement, owner, and configuration. | Connection key + schema + Object name. |
| `core.attribute` | A field/column belonging to an Object. | Object key + Attribute name. |
| `core.ingestion_object_mapping` | Links a Source Object to its ingestion target Object. | Full Source Object key + full target Object key. |
| `core.ingestion_attribute_mapping` | Links Source and target Attributes within an ingestion mapping. | Full Source Attribute key + full target Attribute key. |
| `core.copy_group` | Groups Copy operations within a Tenant/System. | Tenant + System + Copy Group name. |
| `core.member_group` | Names a grouping referenced by Copy Group control records. | Tenant + System + Member Group name. |
| `core.copy_group_control` | Stores a Copy Group's control state for an optional Member Group. | Copy Group key + nullable Member Group name. |
| `core.copy` | Configures a Source-to-target copy within a Copy Group. | Copy Group key + Source Object key + target Object key. |
| `core.process_group` | Groups Processes for a Tenant/System/Zone and associates a Copy Group. | Tenant + System + Zone + Process Group name. |
| `core.process` | Describes an ordered executable and its associated Object. | Process Group key + execution order + location + executable. |

Connection key: `tenant_code`, `system_code`, `connection_code`.
Object key adds `object_schema`, `object_name`; Attribute key adds `attribute_name`.
Exact prefixed key fields come from [the registry](/Users/maazuddinmohammed/main/projects/gds_workbench_v2/mcp_server/gds_etl_workbench/domain/snapshots/metadata.py:154).

The meanings above are initial summaries. Only Object has received the detailed review below. Other table fields, runtime meanings, extra unique constraints, and validation coverage remain to be reviewed individually.

## General change procedure

1. Identify the requested outcome and affected table/records.
2. Read the current dataset contract and required Snapshot context.
3. Resolve records using complete natural keys and published normalization.
4. Read the complete existing record; change requested fields and preserve other supported fields.
5. For new records, supply required fields and resolve references from real records.
6. Inspect dependencies affected by identity, placement, zone, activity, or ordering changes.
7. Validate the effective result: Snapshot records overlaid with all pending changes.
8. Present additions, changes, unresolved gaps, and validation results in Workbench.
9. Use governed submission and Apply procedures; recheck server-only conditions there.

- Same natural key normally means an update; changing the key is not an automatic rename.
- No invented reference codes or caller-supplied database IDs.
- A reference may resolve to another pending record; checking drafts in isolation is insufficient.
- Local validation uses Snapshot evidence. It cannot establish current authorization, Tenant Lock ownership, or unchanged server state.
- Required unresolved inputs are reported as missing checks or blockers, not treated as passed.

## First table: Object

**Meaning:** a registered physical Object at a Connection, owned by a Source Tenant, classified into a Zone. Its Attributes are separate records.

**Datasets:** `source_object`, `bronze_object`, `silver_object`, `gold_object`.

**Natural key:** `tenant_code + system_code + connection_code + object_schema + object_name`.

- `tenant_code/system_code/connection_code` identify physical placement.
- `source_tenant_code` identifies the data/metadata owner.
- Owner and Zone are not part of the natural key.
- Uniqueness spans all four Object datasets, including inactive Objects.
- Database key uses `connection_id + lower(btrim(object_schema)) + lower(btrim(object_name))`.
- Snapshot normalization trims U+0020 spaces and lowercases key strings. Use the published helper; do not introduce different normalization.

Sources: [Object DDL](/Users/maazuddinmohammed/main/projects/gds_workbench_v2/database/02_core.sql:166), [unique index](/Users/maazuddinmohammed/main/projects/gds_workbench_v2/database/02_core.sql:510), [normalization](/Users/maazuddinmohammed/main/projects/gds_workbench_v2/mcp_server/gds_etl_workbench/domain/snapshots/metadata.py:39).

### What goes in its fields

| Fields | Population guidance |
|---|---|
| `tenant_code`, `system_code`, `connection_code` | Exact codes identifying the registered placement Connection. |
| `source_tenant_code` | The owning Tenant's code. |
| `object_schema`, `object_name` | Actual physical schema and Object name. |
| `object_type_code` | Existing applicable Object Type code. |
| `zone_code` | `source`, `bronze`, `silver`, or `gold`; must match the dataset. |
| `fc_object_schema`, `fc_object_name` | Foreign-catalog coordinates when applicable; otherwise `null`. |
| `object_transformation` | Governed consumer-specific transformation text, or `null`. Detailed allowed usage still needs consumer review. |
| `object_description` | Supported description, or `null`; enrichment remains separate. |
| `batch_attribute_name` | Attribute belonging to this Object, or `null`. |
| `is_locked`, `is_active` | Boolean state fields; existing lock protections govern allowed changes. |

All 15 current contract fields are required to be present; nullable fields may contain `null`. Exact lengths/types come from the current generated schema. Database IDs and audit fields are server-owned.

Sources: [ObjectRecord](/Users/maazuddinmohammed/main/projects/gds_workbench_v2/mcp_server/gds_etl_workbench/domain/metadata_records.py:145), [field guidance builder](/Users/maazuddinmohammed/main/projects/gds_workbench_v2/mcp_server/gds_etl_workbench/domain/snapshots/metadata_guidance.py:297).

### Validation ledger — first pass

Coverage means observed in source, not runtime-tested parity. `Review` means incomplete or different enforcement needs assessment. `Server` means an offline check cannot guarantee the current condition.

| Rule | Check / reason | Database | MCP backend | Local |
|---|---|---|---|---|
| `common.shape` | Required fields, types, nullability, limits; reject malformed records. | Column constraints | Schema | Generated schema |
| `object.key` | Full normalized key unique across zones; prevent duplicate identity. | Unique index | Staged + effective checks | Effective checks |
| `object.references` | Placement Connection, owner, Object Type, Zone exist; prevent broken references. | FKs + Apply resolution | References + placement | References + placement |
| `object.zone` | Zone matches dataset; prevent staging under the wrong zone. | Apply/Zone reference | Fixed value | Schema constant |
| `object.owner` | Owner matches Change Set Tenant; preserve ownership. | Apply check | Scope check | Scope check |
| `object.placement` | Source uses owned non-GDS Connection; other zones use owner's configured GDS Connection. | Apply checks flags + association | Association; flag parity review | Association; flag parity review |
| `object.lock` | Existing locked Object blocks changes to itself and its Attributes. | Apply live check | Baseline check | Baseline check |
| `object.batch-attribute` | Non-null batch Attribute belongs to Object; prevent unusable batch configuration. | No direct FK found | Review: no rule found here | Review: no rule found here |
| `object.foreign-catalog` | Required coordinates exist when a workflow uses foreign-catalog access. | Contextual | Workflow prerequisite review | Contextual check to define |
| `object.active-references` | Check activity where required by the operation; existence alone is insufficient. | Operation-specific review | Reviewed references test existence | Reviewed references test existence |
| `common.live-state` | Authorization, owned Tenant Lock, draft revision/digest, current dependencies still valid. | Server | Server integration | Cannot guarantee offline |

Coverage sources:

- [Backend phase sequence](/Users/maazuddinmohammed/main/projects/gds_workbench_v2/mcp_server/gds_etl_workbench/application/change_sets/metadata_validation.py:103).
- [Backend locks and ownership](/Users/maazuddinmohammed/main/projects/gds_workbench_v2/mcp_server/gds_etl_workbench/application/change_sets/metadata_validation.py:270).
- [Local references and locks](/Users/maazuddinmohammed/main/projects/gds_workbench_v2/plugins/v2/gds/skills/gds/workbench/validation/metadata.js:11).
- [Local ownership/placement](/Users/maazuddinmohammed/main/projects/gds_workbench_v2/plugins/v2/gds/skills/gds/workbench/validation/metadata.js:132).
- [Local cross-zone uniqueness](/Users/maazuddinmohammed/main/projects/gds_workbench_v2/plugins/v2/gds/skills/gds/workbench/validation/metadata.js:241).
- [Apply locks](/Users/maazuddinmohammed/main/projects/gds_workbench_v2/database/16_mcp_metadata_apply.sql:140), [placement and update](/Users/maazuddinmohammed/main/projects/gds_workbench_v2/database/16_mcp_metadata_apply.sql:305).

### Items to settle before finalizing Object

- Batch Attribute membership: promote existing population guidance into an explicit check; choose enforcement layers after checking consumers.
- Connection activity/GDS flags: align operation-specific local/backend checks with authoritative behavior.
- Foreign-catalog coordinates: require them only for operations that need them; do not make optional Object fields universally mandatory.
- Identity, owner, or Zone changes: define supported user actions and dependency review. Ordinary upsert does not implement a rename or ownership transfer.
- No general Object description byte limit exists in the reviewed schema; do not copy enrichment-specific limits into this workflow by assumption.

## Review order

Object → Attribute → ingestion Object Mapping → ingestion Attribute Mapping → Copy Group → Member Group → Copy Group Control → Copy → Process Group → Process.

For each table, finish meaning, field population, natural/extra unique keys, references, change behavior, and short validation entries before proceeding. Add reusable terms or rules to shared references as they are agreed.
