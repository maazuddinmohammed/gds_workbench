# Metadata dataset guide

Use this guide for business meaning and dependency direction. The validated
Snapshot's `catalog.json` and `schemas/<dataset>.schema.json` are authoritative
for current fields, types, canonical keys, unique constraints, fixed values,
and references.

## Key shorthand

- `C`: Tenant + System + Connection codes.
- `O`: `C` + Object schema + Object name.
- `A`: `O` + Attribute name.
- `OM`: complete Source `O` + Target `O` pair.
- `AM`: complete Source `A` + Target `A` pair.
- `CG`: Tenant + System + Copy Group name.
- `MG`: Tenant + System + Member Group name.
- `PG`: Tenant + System + Zone + Process Group name.

Keys are ID-free. Trust the live schema's `x-gds-key-normalization`. Only
string fields ending `_code`, `_name`, or `_schema` trim U+0020 spaces and
lowercase. Other key values are exact; notably, `process_location` and
`process_executable` remain case-sensitive. Always confirm the expanded key and
references in the live dataset schema.

## Foundational datasets

These five describe ownership and connectivity. They are read-only in Metadata
Change Sets.

| Dataset | Meaning | Key and parents |
|---|---|---|
| `project` | Top-level grouping that owns Tenants. | Project code; no parent. |
| `tenant` | Governed metadata and authorization boundary. It also holds catalog placement and optional GDS Connection selection. | Tenant code; Project and optional Connection. |
| `system` | Named source, platform, or application identity shared by Connections and execution groups. | System code; System Type. |
| `connection` | Tenant-specific logical connection to a System. Snapshot rows contain classification and catalog behavior, never credentials. | `C`; Tenant, System, Connection Type. |
| `tenant_metadata_discovery_scope` | Declares which Connection, Zone, and object schema a Tenant may use for metadata discovery. | Scope Tenant + `C` + Zone + object schema; Tenant, Connection, Zone. |

## Reference datasets

These eight are allowed classification values. They are read-only in Metadata
Change Sets; use them to choose existing codes/names for operational rows.

| Dataset | Meaning | Key |
|---|---|---|
| `system_type` | Classifies Systems. | System Type code. |
| `connection_type` | Classifies Connection technology or protocol. | Connection Type code. |
| `object_type` | Classifies physical Objects, such as a table-like object. | Object Type code. |
| `zone` | Defines available GDS zones. Zone name is also unique. | Zone code. |
| `chunk_type` | Defines supported Copy chunking strategies. | Chunk Type name. |
| `file_type` | Defines supported source file formats. | File Type name. |
| `data_operation` | Defines supported source and target Copy operations. | Data Operation name. |
| `process_type` | Classifies Process execution behavior. | Process Type name. |

## Operational datasets

These 16 may be staged. Every staged item is a complete row, not a patch.

| Dataset | Meaning | Key and parents |
|---|---|---|
| `source_object` | Physical Object classified in the Source zone. | `O`; Connection, Object Type, Source Zone. |
| `source_attribute` | Ordered column/field belonging to a Source Object. | `A`; Source Object. Ordinal is unique within its Object. |
| `bronze_object` | Physical Object classified in the Bronze zone. | `O`; Connection, Object Type, Bronze Zone. |
| `bronze_attribute` | Ordered column/field belonging to a Bronze Object. | `A`; Bronze Object. Ordinal is unique within its Object. |
| `silver_object` | Physical Object classified in the Silver zone. | `O`; Connection, Object Type, Silver Zone. |
| `silver_attribute` | Ordered column/field belonging to a Silver Object. | `A`; Silver Object. Ordinal is unique within its Object. |
| `gold_object` | Physical Object classified in the Gold zone. | `O`; Connection, Object Type, Gold Zone. |
| `gold_attribute` | Ordered column/field belonging to a Gold Object. | `A`; Gold Object. Ordinal is unique within its Object. |
| `ingestion_object_mapping` | Configured Source Object to Target Object lineage edge. | `OM`; both Objects. |
| `ingestion_attribute_mapping` | Configured Source Attribute to Target Attribute lineage edge inside an Object mapping. | `AM`; Object Mapping and both Attributes. |
| `copy_group` | Tenant/System grouping of Copy work. It declares whether a Member Group is required. | `CG`; Tenant and System. |
| `member_group` | Named Tenant/System member partition with an optional initial-load date. | `MG`; Tenant and System. |
| `copy_group_control` | Runtime checkpoint for a Copy Group, optionally per Member Group. | `CG` + nullable Member Group name; Copy Group and optional Member Group. |
| `copy` | Execution configuration for one Object Mapping inside a Copy Group: order, limits, chunk/file settings, SQL, and source/target operations. | `CG` + `OM`; Copy Group, Object Mapping, and reference values. Order is unique within the Copy Group. |
| `process_group` | Zone-specific processing group connected to a Copy Group. | `PG`; Tenant, System, Zone, Copy Group. |
| `process` | Ordered executable associated with one Object inside a Process Group. | `PG` + execution order + location + executable; Process Group, Object, Process Type. |

## How to interpret fields

- `is_active=false` is lifecycle deactivation where that field exists. An empty
  staged list does not deactivate applied rows.
- `is_locked` exists only on Objects. A locked Object blocks changes to that
  Object and its Attributes; never toggle it automatically.
- Object `zone_code` is fixed by its dataset. Do not copy a Source row into a
  Bronze/Silver/Gold file without changing and validating its full natural key,
  parent Connection, and intended fields.
- `fc_*`, transformation, batch, custom-code, masking, purge, runtime checkpoint,
  SQL, file, and executable fields carry project-specific behavior. Preserve
  existing values unless the user gives the intended value; ask instead of
  deriving business logic from the field name.
- `copy_group_control` has no `is_active` field. Its values are runtime control
  state; do not reset them as a side effect of another change.

## Dependency direction for changes

Build and stage parents before children:

1. Zone Objects.
2. Zone Attributes.
3. Ingestion Object Mappings.
4. Ingestion Attribute Mappings.
5. Copy Groups and Member Groups.
6. Copy Group Controls and Copies.
7. Process Groups.
8. Processes.

Foundational/reference parents must already exist in the Snapshot. If a needed
parent is absent, stop: this Metadata Change Set cannot create it.
