# Entity ownership and physical handoff

Model schema configuration is stored in `logical_schemas` and `dimensional_schemas`.
Each entry has required `schema_name` and nullable `description`. Entity schema
names must resolve against their layer's configured list. Compare names using the
published Model normalization; preserve their actual spelling.

Logical identity is `logical_entity_schema_name` + `logical_entity_name`.
Dimensional identity is `dimensional_entity_schema_name` + `dimensional_entity_name`.
Every Attribute and relationship endpoint repeats its owning Entity schema.
Mapping and Code repeat `modeled_entity_type`, `modeled_entity_schema_name` and
`modeled_entity_name`; Attribute Mapping also identifies `modeled_attribute_name`.
Two Entities with the same name in different schemas are different records.

Mapping and Code belong directly to the modeled Entity. No Model Object Binding,
Model Attribute Binding or Model Binding dataset is authored. Target registration
is not required to model, map, or generate Code. Logical Mapping consumes eligible
physical Source/Bronze inputs; Dimensional design and Mapping consume Logical
Entities/Attributes through complete schema-qualified identities.

Mapping must cover all active modeled Attributes for each contributing System,
including keys, audit columns, constants and generated values. Code still requires
complete applied Mapping and explicit Source System assignments. Retain locks,
revision fences, source provenance and existing artifact digests.

Entity schema/name supplies the planned SQL coordinates. Registration and Process
metadata remain a separate operational handoff. When requested, export the applied
design and register the actual physical Objects/Attributes through a Metadata
Change Set. Resolve placement and verify types, nullability, keys, audit roles,
masking and complete column coverage before that handoff. Do not invent database
IDs, execute DDL, or treat exported metadata as evidence of deployment.
