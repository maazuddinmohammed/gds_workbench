# Entity-owned modeling implementation contracts

Approved scope: Model schema configuration, schema-qualified Entity identities,
Entity-owned Mapping/Code, Logical-based Dimensional lineage, binding removal,
all Web/MCP/Atlas consumers and governed lifecycle/deletion. Cardinality/SCD
changes are separate. Fresh-install SQL only; no populated-database migration.

## Names

- Model: `logical_schemas`, `dimensional_schemas`, arrays of objects with required
  `schema_name` and nullable `description`. Default empty arrays; layer generation
  requires configuration. Maximum schema-name length 400, nonblank, unique using
  existing name normalization. Descriptions bounded to 2000 characters.
- Entity and owning-Entity references: `logical_entity_schema_name` /
  `dimensional_entity_schema_name`, required; schema is part of natural identity.
- Relationship endpoints: `from_logical_entity_schema_name`,
  `to_logical_entity_schema_name`, dimensional equivalents.
- Mapping and Code public records: `modeled_entity_schema_name`, required along
  with existing modeled_entity_type/name. Public record IDs remain absent.
- Snapshot schema version 2.0; remove ModelBindingSection and binding datasets.
- Physical source keys retain object_schema/object_name and existing ownership.
- Dimensional source keys become logical_entity_schema_name/logical_entity_name,
  plus logical_attribute_name for attribute support; keep assertion support.

## Live database references

Mapping Object: model_id, modeled_entity_type, logical_entity_id or
 dimensional_entity_id (exactly one), source_system_id. Composite same-Model FKs.
Mapping Attribute: mapping_object_id, model_id, typed Entity and Attribute IDs;
composite FKs must prove same parent Entity AND Model, using existing Attribute
witness constraints. Uniqueness one Attribute per parent Mapping.
Generated Code: model_id, modeled_entity_type, exactly one typed Entity ID;
unique artifact name per Entity. Source-System assignment remains Code-owned.

Dimensional entity/attribute source mappings use source_logical_entity_id and
source_logical_attribute_id; same-Model and parent-witness constraints preserved.
Logical source support remains physical Source/Bronze plus Assertions.

## Run selections

Add application.workflow_run_entity_selection: immutable Run+Model FK,
modeled_entity_type/id/schema_name/name, selection_order; no FK to live Entity.
Unique per Run+type+id and Run+order. Mapping target selections reference this
frozen Entity selection plus source System and frozen selected Attribute scope.
Keep physical Object selections for physical-source workflows. Preserve revision,
locks, immutable history, request/scope digests and idempotency. Prefer canonical
entity fields in target context; physical SQL context may project saved schemas
and names into target_metadata.object_schema/object_name without physical IDs.

## Ownership

Root: mcp_server/**, tests/mcp/** (except database agent's new dedicated test),
root docs and integration. Database agent: database/**. Web agent: web_app/**,
tests/web_backend/**, tests/web_packaging/**. Atlas agent: atlas/**, tests/atlas/**.
Coordinate interface changes; no broad rewrites of another owner's files.

Lookup preservation: Logical Mapping accepts optional source_logical_entities /
source_logical_attributes beside physical inputs. Dimensional Mapping accepts
optional source_dimensional_entities / source_dimensional_attributes beside its
Logical inputs. Modeled context sources carry entity_type, schema and name; peer
lookups require active same-Model, same-System applied Mapping. Code currentness
includes resolved lookup coordinates and Attributes.
