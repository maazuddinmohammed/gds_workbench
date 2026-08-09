# Release 1 decisions

**Decision record version:** 1.0.0  
**Approved:** 2026-08-04 through the unchanged Section 1 goal  
**Authority:** `IMPLEMENTATION_PLAN.md` Section 7

The approved text is reproduced verbatim below.

## 7. One-shot decisions for the three open design gates

Feature 001 deliberately leaves DD-108, DD-109, and DD-110 open and forbids
dependent implementation from guessing. This section freezes complete v1
defaults. Submitting the Section 1 goal unchanged explicitly approves these
exact contracts; copy them verbatim to
`docs/design/RELEASE-1-DECISIONS.md`. An edited replacement in the submitted
goal has higher authority. Without either approval, finish independent work and
stop before T03/T05/T18/T21/T22/T23.

### 7.1 DD-108 — exact Profiling development/test batch contract

Add these four nullable columns directly to the writable target copy of
`core.connection`:

```sql
profiling_development_initial_batch_id BIGINT,
profiling_development_incremental_batch_ids BIGINT[],
profiling_test_initial_batch_id BIGINT,
profiling_test_incremental_batch_ids BIGINT[],
```

Arrays use PostgreSQL `BIGINT[]`, preserve arbitrary signed `BIGINT` source
keys, and when non-null must be one-dimensional, lower-bound 1, sorted
ascending, duplicate-free, contain no null, and contain at most 1,000 values.
Each non-null initial ID must not occur in its environment's incremental array.
An immutable, schema-qualified
`core.is_canonical_batch_id_array(BIGINT[])` helper plus exact per-environment
CHECK constraints enforces this. `NULL` and an explicit empty array are
intentionally distinct.
The external Excel/bootstrap loader must emit blank/SQL NULL for unconfigured
values and canonical PostgreSQL array values such as `{}` or `{-2,7,9}`; JSON
or comma-delimited strings are rejected.

The strict request extension is:

```text
batch_environment: Literal["development", "test"]
batch_mode: Literal["initial", "incremental"]
```

Both fields are required for Profiling and are forbidden on Analysis. For each
selected Object, common code applies these exact rules:

1. If `batch_attribute_name IS NULL`, ignore all four Connection fields and
   perform the ordinary bounded unfiltered read.
   T03 constrains the stored value to null or nonblank.
2. Otherwise resolve that exact case-sensitive name to one active Attribute of the
   same Object. A missing, ambiguous, or inactive Attribute blocks readiness.
3. `initial` selects the one environment-specific initial ID and generates an
   equality predicate. A null ID is unconfigured and blocks that Object.
4. `incremental` selects the environment-specific array and generates a
   membership predicate over every configured value. A null array is
   unconfigured and blocks; `{}` is a configured deterministic no-op for that
   Object and never falls back to a full scan.
5. There is no development↔test, initial↔incremental, or missing↔unfiltered
   fallback for an Object that declares a batch Attribute.
6. Mixed-Connection selection resolves the applicable field independently for
   each Object's own Connection; one Connection's IDs never filter another.
7. Readiness requires the batch Attribute metadata type to be Spark
   byte/short/integer/long or `DECIMAL(p,0)`, and proves every configured ID fits
   that exact type. Spark builds predicates with column/literal APIs and casts
   only the already range-checked literal to the declared physical type; it
   never casts the data column or interpolates SQL. String, floating, scaled
   decimal, unknown, or incompatible types block before Spark, so filtering
   cannot silently discard an uncastable value.
8. Empty incremental configuration contributes no success/failure rows. If all
   selected batched Objects are explicit no-ops and no unbatched Object remains,
   finalization records a successful no-op and advances no Model revision.

Readiness reports every affected Connection/Object and correction in one pass.
The Profiling Run records the selected environment/mode and resolved per-Object
batch values in immutable request context; Attribute Profile identity remains
`(model_id, attribute_id)` rather than adding batch history.

### 7.2 DD-109 — exact combined Mapping persistence

Use exactly three tables. Add no environment, contributor, materialization,
Relationship-mapping, or orchestration-process table/column.

Every table uses the common Feature 001 envelope: generated `BIGINT` ID,
`model_id BIGINT`, nullable `agent_run_id VARCHAR(500)`, prefixed lifecycle
`VARCHAR(20)` default `active`, prefixed lock Boolean default false,
`created_time/updated_time TIMESTAMPTZ` default current timestamp, and
`created_by/updated_by VARCHAR(255)` default current user. Lifecycle is exactly
`active|needs_review|inactive|deprecated`; all FKs use `ON DELETE NO ACTION`.

#### `workflow.mapping_source_system_dependency`

One row controls each `(model_id, modeled_entity_type, source_system_id)`
execution wave. Equal dependency orders may run in parallel; lower orders
complete before higher orders.

#### `workflow.object_mapping`

| Column | Type/null/default |
|---|---|
| `object_mapping_id` | `BIGINT GENERATED ALWAYS AS IDENTITY PRIMARY KEY` |
| `model_id` | `BIGINT NOT NULL` |
| `agent_run_id` | `VARCHAR(500) NULL` |
| `modeled_entity_type` | `VARCHAR(30) NOT NULL`, `logical_entity|dimensional_entity` |
| `logical_entity_id` | `BIGINT NULL` |
| `dimensional_entity_id` | `BIGINT NULL` |
| `target_object_id` | `BIGINT NOT NULL` |
| `source_system_id` | `BIGINT NOT NULL` |
| `object_dependency_order` | `INTEGER NOT NULL DEFAULT 0`, non-negative |
| `artifact_type` | `VARCHAR(30) NULL`, `sql_file|python_file|python_notebook` |
| `artifact_generation_instructions` | `TEXT NULL`, nonblank and at most 32,768 characters when present |
| `mapping_profile_key` | `VARCHAR(100) NULL`, pattern `[a-z][a-z0-9_.-]{0,99}` |
| `mapping_profile_version` | `VARCHAR(50) NULL`, SemVer `major.minor.patch` |
| `mapping_profile_schema_digest` | `CHAR(64) NULL`, lowercase SHA-256 |
| `mapping_package_document` | `JSONB NULL`, object root |
| `mapping_package_digest` | `CHAR(64) NULL`, lowercase SHA-256 |
| `object_mapping_transformation_document` | `JSONB NULL`, object root |
| `object_mapping_status` | common lifecycle |
| `object_mapping_is_locked` | common lock |
| common audit fields | exact common envelope above |

Exactly one typed Entity ID must be non-null and agree with
`modeled_entity_type`. Composite FKs bind that Entity to the same Model;
an FK binds the exact Mapping Source System Dependency row, and an ordinary FK
binds the target Object. Add unique witness
`(object_mapping_id, model_id, modeled_entity_type, target_object_id)`. Preserve
binding identity across every lifecycle state with two partial unique indexes:

```text
(model_id, logical_entity_id, target_object_id, source_system_id)
  WHERE modeled_entity_type = 'logical_entity'
(model_id, dimensional_entity_id, target_object_id, source_system_id)
  WHERE modeled_entity_type = 'dimensional_entity'
```

A pre-registered binding has all eight authored fields null: artifact type,
instructions, profile key/version/schema digest, package document/digest, and
Object transformation. An authored header has all eight non-null. Null
transformation therefore means “binding exists but is not script-ready”; a
completed no-expression header explicitly stores `transformation_kind=direct`.

#### `workflow.attribute_mapping`

| Column | Type/null/default |
|---|---|
| `attribute_mapping_id` | `BIGINT GENERATED ALWAYS AS IDENTITY PRIMARY KEY` |
| `model_id` | `BIGINT NOT NULL` |
| `agent_run_id` | `VARCHAR(500) NULL` |
| `object_mapping_id` | `BIGINT NOT NULL` |
| `modeled_entity_type` | `VARCHAR(30) NOT NULL`, same discriminator as parent |
| `target_object_id` | `BIGINT NOT NULL`, repeated parent witness |
| `logical_attribute_id` | `BIGINT NULL` |
| `dimensional_attribute_id` | `BIGINT NULL` |
| `target_attribute_id` | `BIGINT NOT NULL` |
| `attribute_mapping_transformation_document` | `JSONB NULL`, object root |
| `attribute_mapping_status` | common lifecycle |
| `attribute_mapping_is_locked` | common lock |
| common audit fields | exact common envelope above |

Exactly one typed modeled Attribute is non-null and agrees with the parent's
layer. A composite FK to the Object Mapping witness carries Model/layer/target
Object; a `(target_attribute_id, target_object_id)` FK uses a required
`core.attribute(attribute_id, object_id)` unique witness. Two partial unique
indexes preserve `(model_id, object_mapping_id, typed_attribute_id,
target_attribute_id)` identity across lifecycle. A target Attribute may have
multiple contributor bindings, but an existing binding can never be repointed.
Null transformation is an unauthored registered binding; completed direct
content explicitly stores `transformation_kind=direct`.

A transaction-deduplicated deferred graph validator enforces all cases
ordinary FKs cannot express:

- the typed modeled Attribute belongs to the exact typed Entity on its header;
- effective child, typed parents, and target parent are effective/valid;
- Logical headers target registered Silver and Dimensional headers registered
  Gold, using externally bootstrapped normalized `zone_code` values
  `bronze|silver|gold`;
- every effective header in one
  `(model_id, modeled_entity_type, target_object_id, source_system_id)` package
  has byte-equivalent artifact/profile/instruction fields and equal
  canonical package JSON as well as equal digest;
- one source System/layer has one controlled dependency row;
- one target Object/layer has one `object_dependency_order`;
- parent/child binding identity columns are immutable after insert;
- locked rows and locked-header descendants are immutable, and ordinary DML
  cannot toggle lock flags.

To make that route check declarative, T03 adds
`reference.zone.zone_code VARCHAR(30) NOT NULL`, with case-insensitive
uniqueness. Release fixtures/bootstrap use the exact codes `bronze`,
`silver`, and `gold`; display names remain independent.

The supporting indexes cover Model/package/status, Model/layer/System and both
wave orders, each typed Entity/Attribute, target Object/Attribute, source
System, parent traversal, and partial locked-row lookup. Catalog tests assert
the exact indexes rather than treating this list as query-planner advice.

### 7.3 DD-109 — exact Mapping JSON/Pydantic profile

Freeze one allowlisted profile:

```text
key: mapping.standard
version: 1.0.0
classes: HeaderMapperOutputV1, AttributeMapperBatchOutputV1,
         GeneratorDocumentV1
```

Every model has an object root, `extra="forbid"`, required nullable fields
instead of omitted ambiguity, no arbitrary dictionaries, JSON-mode
serialization, and strict Structured Outputs preflight. Stable database IDs are
allowed in the two agent-stage contracts; `GeneratorDocumentV1` contains names
and provenance but no database IDs.

The schema digest is SHA-256 of the T02 canonical JSON bundle containing the
three generated JSON Schemas in class-name order. Registry key+SemVer+digest
must resolve exactly before a run. A registered version is immutable and every
version referenced by an effective row remains deployed/readable. Build may
author a previously unauthored binding/package only with the selected profile
and must match any already-authored header in that package. Extend may upgrade a
complete unlocked target/System
package atomically to another allowlisted version; partial/mixed upgrade or an
unavailable stored version blocks. A locked row blocks a required upgrade.

`MappingPackageDocumentV1` has exactly:

- `schema_version: Literal["1.0"]`;
- unique stable `package_ref`,
  `route=logical_to_silver|dimensional_to_gold`, `target_object_id`,
  `source_system_id`, `artifact_type`, nonblank
  `artifact_generation_instructions`, and exact
  `pydantic_profile(key, version, schema_digest)`;
- `executable_sources[1..128]`: `object_id`, unique identifier `alias`, nonblank
  `role`, and nullable `batch_rule(attribute_id, values: list[BIGINT])`;
- `non_executable_provenance[0..128]`: items with
  `lineage_kind=original_ingestion|prior_mapping`, `source_system_id`,
  `source_object_id`, `ingestion_object_mapping_ids[0..16]`,
  `prior_object_mapping_ids[0..16]`, and nonempty unique
  `executable_source_aliases[1..16]`, never executable FQNs. Original ingestion
  requires at least one ingestion ID and zero prior-Mapping IDs; prior Mapping
  requires the inverse. Every ID/path must resolve in frozen lineage.
- `runtime_parameters[0..128]`: unique identifier `name`, nonblank `data_type` and
  `purpose`, and nullable string/integer/Boolean `default_value` (no float);
- `source_system_dependencies[0..256]`:
  `predecessor_source_system_id`, nonblank `reason`;
- `target_dependencies[0..256]`: `predecessor_target_object_id`, nonblank `reason`;
- `steps[1..256]`: unique identifier `name`, unique `depends_on`, unique `inputs`,
  unique output `output`, and nonblank free-text `logic`;
- nonblank `grain_and_deduplication`;
- `load`: `write_mode=append|overwrite|merge`, unique `merge_keys` target
  Attribute IDs, nullable nonblank `partition_basis`,
  `concurrent_system_write_mode=disjoint_partitions|idempotent_merge|serialized`,
  and nonblank `concurrent_write_basis`.

`ObjectMappingTransformationDocumentV1` has exactly:

- `schema_version: Literal["1.0"]`;
- `transformation_kind: direct|derived`;
- nonempty unique `source_aliases` drawn from the package;
- typed `joins[]` (`left_alias`, `right_alias`, `join_type`, nonblank
  `condition`), `unions[]` (`input_aliases`, `all`, nonblank `alignment`),
  `filters[]` (nonblank expressions), and `aggregations[]` (`output_name`,
  nonblank expression, unique grouping inputs);
- nonblank `entity_contribution_logic` and `rationale`.

`AttributeMappingTransformationDocumentV1` has exactly:

- `schema_version: Literal["1.0"]`;
- `transformation_kind: direct|expression`;
- `source_columns[]` of package `source_alias` plus `source_attribute_id`;
- nullable `step_output`, nullable `expression`, and nonblank `logic`.

`direct` requires exactly one source column and null expression. `expression`
requires a nonblank expression and may have zero sources for a constant/system
expression. A step output must exist in the named DAG. All aliases/Attributes
must resolve to executable lineage for the declared business System.

`HeaderMapperOutputV1` has `schema_version`, one exact `package`, a nonempty
`headers[]` of `(object_mapping_id, transformation)`, and `coverage` containing
unique nonempty expected and returned Object Mapping ID lists.

`AttributeMapperBatchOutputV1` has `schema_version`, `package_ref`, target and
source-System IDs, `chunk_index`/`chunk_count` in `1..100`, the 64-character
package digest, `coverage_manifest_digest`, `attribute_mappings[]`,
`target_attribute_dispositions[]`, and `coverage`. Each mapping contains parent
ID, exactly one existing
`attribute_mapping_id` or new `local_ref`, layer discriminator, exactly one
typed modeled Attribute ID, target Attribute ID,
`disposition=create|update|unchanged`, and complete transformation. Target
disposition is `mapped|already_mapped|intentionally_unmapped` with a reason
required only for intentionally unmapped. Coverage contains unique expected and
returned target Attribute IDs plus expected and returned existing child IDs.
Common code requires contiguous chunks, disjoint owned target/child IDs, one
final exact coverage manifest, and the same Header/package digest before
publishing the combined batch.

`GeneratorDocumentV1` is derived after commit. Its exact name-based nested
models are:

- `schema`: `document_version="1.0"`, profile key/version/schema digest;
- `applied_model`: nonblank Model name, positive revision, 64-hex source-context
  digest;
- `route: logical_to_silver|dimensional_to_gold`;
- `source_system`: nonblank code/name, non-negative dependency order, and
  `predecessors[0..64]` of nonblank code/name/reason;
- `artifact`: `type=sql_file|python_file|python_notebook` and nonblank
  generation instructions;
- `dependency_waves`: non-negative target order and
  `target_predecessors[0..128]` of target FQN/reason;
- `target`: catalog, schema, object name, FQN, `zone=silver|gold`, nullable
  nonblank description, nonblank grain/deduplication, and `columns[1..5000]`;
- each target column: name, data type, nullable Boolean, positive unique ordinal,
  and nullable nonblank definition;
- `executable_sources[1..128]`: unique alias, `zone=bronze|silver|gold`, catalog,
  schema, object name, FQN, `used_columns[1..10000]` of unique name, data type,
  nullable Boolean, and nullable nonblank definition/meaning, plus nullable
  `batch_rule(attribute_name, values[0..1000] BIGINT)`;
- `original_source_provenance[0..128]`: source System code/name, Connection code,
  source Object name, `lineage_kind`, `lineage_path[1..32]` human-readable named
  edges, and nonempty executable aliases; it contains no executable original-
  source FQN;
- `runtime_parameters[0..128]`: unique name, data type, purpose, and nullable
  string/integer/Boolean default;
- `named_steps[1..256]`: unique name, unique dependencies/inputs, unique output,
  and nonblank logic, all using names rather than IDs;
- `load`: write mode, merge-key target column names, nullable partition basis,
  concurrent-system-write mode/basis, and nonblank grain/deduplication;
- `entity_contributions[1..64]`: `layer=logical|dimensional`, Entity name,
  definition, unique source aliases, and the exact name-materialized
  `ObjectMappingTransformationDocumentV1` fields/cardinalities plus rationale;
- `target_columns[1..5000]`: target column name, disposition,
  `contributors[0..32]` of Entity/Attribute/source-alias/source-column names,
  `kind=direct|expression`, nullable step-output/expression, and nonblank logic/
  rationale. Disposition is `mapped|already_mapped|intentionally_unmapped`, with
  a nonblank reason required only for intentionally unmapped. Direct has exactly
  one contributor and no expression; expression requires an expression.

Every code/name/FQN/alias refers to the same committed package and is validated
against authoritative named metadata. Ordinary strings and lists use the limits
below, used source columns total at most 10,000 across all sources, FQNs are at
most 1,024 characters, ordinals are complete/unique, and the
target-column list covers every registered target column exactly once. No
database ID or secret field exists and no follow-up metadata lookup is required.

Contract limits are exact v1 values:

| Limit | Value |
|---|---:|
| entire `mapping.json` section | 16 MiB canonical UTF-8 |
| package / Object transform / Attribute transform JSON | 512 / 256 / 64 KiB |
| generator document | 4 MiB |
| packages per run | 1,000 |
| headers / sources / runtime parameters per package | 64 / 128 / 128 |
| dependencies / named steps per package | 256 / 256 |
| target Attributes per package | 5,000 |
| Attribute Mapper items per deterministic chunk | 500 |
| identifier / ordinary text / logic / instructions | 128 / 2,000 / 16,384 / 32,768 characters |

Oversize input blocks before model invocation and is never silently truncated.
The package digest is lowercase SHA-256 over contract-canonical JSON v1: strict
JSON-mode data only; UTF-8; object keys lexicographically sorted; array order as
contract-normalized; compact `,`/`:` separators; no insignificant whitespace,
NaN, Infinity, floats, or duplicate keys. Lists declared as sets are sorted by
their documented stable key before serialization. T02 supplies golden vectors
used by PostgreSQL/application/jobs tests.

### 7.4 DD-110 — exact Silver/Gold naming and policy storage

Use runtime-compatible `*_template` terminology and remove the current
`*_naming_rules` aliases. The fresh `model.model` has exactly:

```sql
silver_model_naming_template JSONB,
silver_model_audit_columns_template JSONB,
gold_model_naming_template JSONB,
gold_model_technical_columns_template JSONB,
gold_model_audit_columns_template JSONB,
```

The two Silver documents are either both null or both non-null. The three Gold
documents are either all null or all non-null. Null groups let external
foundational bootstrap create an incomplete Model; workflow readiness blocks
the affected layer. Every non-null value is an object with
`schema_version="1.0"`; Pydantic/JSON Schema performs the full shape check and
PostgreSQL CHECKs enforce group completeness, root type, version, and required
array keys.

`NamingTemplateV1`, used for both layers, has exactly:

```json
{
  "schema_version": "1.0",
  "default_style": "PascalCase",
  "submodel_style": "PascalCase",
  "entity_style": "PascalCase",
  "attribute_style": "PascalCase",
  "relationship_style": "PascalCase",
  "acronyms": {"id": "ID"},
  "max_length": 255,
  "reserved_words": []
}
```

V1 supports only `PascalCase`. Tokenization and rendering are the characterized
reference algorithm: replace non-ASCII-alphanumeric separators with spaces,
split acronym/camel/number words, lowercase lookup keys, apply configured
acronym spellings, capitalize other words, and concatenate. The result must
start with A–Z, contain only ASCII alphanumerics, fit `1..255`, and not equal a
reserved word case-insensitively. Acronym keys are unique canonical lowercase;
values and reserved words are nonblank; each collection has at most 256 items.
Unknown fields/styles fail readiness. Collision or overlength is an error—never
automatic suffixing or truncation.

`AuditColumnsTemplateV1`, used for Silver and Gold, is:

```text
schema_version: Literal["1.0"]
columns: list[1..32] of {
  semantic_name: nonblank string[1..255]
  data_type: nonblank string[1..100]
  nullable: boolean
  definition: nullable nonblank string[1..2000]
}
```

List order is final order after all business/technical Attributes. Derived
names must be unique after naming normalization. The document stores no role,
artifact ID, proposed/final name, or absolute ordinal. Logical projection sets
only `logical_attribute_is_audit_column=true`, creates no source mapping, and
matches existing audit rows by normalized name plus compatible type/nullability;
an ambiguous rename blocks.

`GoldTechnicalColumnsTemplateV1` is:

```text
schema_version: Literal["1.0"]
dimension_surrogate_key: {
  semantic_name_template: "{entity_name} key"
  data_type: string[1..100]
  nullable: false
  definition_template: string[1..2000]
}
fact_bridge_foreign_key: {
  with_role_semantic_name_template: "{role_name} key"
  without_role_semantic_name_template: "{entity_name} key"
  definition_template: string[1..2000]
}
type_2: {
  effective_from: PolicyColumnV1
  effective_to: PolicyColumnV1
  is_current: PolicyColumnV1
}
```

`PolicyColumnV1` is the audit-column shape without `schema_version`.
`effective_from` is non-nullable, `effective_to` nullable, and `is_current`
non-nullable. Only `{entity_name}` and `{role_name}` placeholders are accepted.
Fact/Bridge foreign-key data type is not independently configurable: it is
copied exactly from the referenced Dimension surrogate-key policy/Attribute;
its nullability is derived from final Relationship optionality. A mismatched
existing endpoint blocks readiness/projection rather than coercing a type.
The canonical fixture/bootstrap example uses `effective from time`
(`TIMESTAMPTZ`, non-null), `effective to time` (`TIMESTAMPTZ`, nullable), and
`is current` (`BOOLEAN`, non-null); production Models may supply different
values that validate against the same immutable shape.
The first Gold projection reuses/creates Entity-local surrogate, Type 2, and
audit Attributes; the second projects role-aware Fact/Bridge foreign keys after
Relationships settle. Agents never author or rename these policy rows.

Actual acronym/reserved-word lists, data types, names, and definitions are
external per-Model bootstrap data—not implementation guesses. Fixtures use the
examples above. A future incompatible shape/style is a new schema version,
never a silent v1 reinterpretation.

If the user edits any approved default, update every affected DDL, Pydantic/
JSON Schema, fixture, readiness rule, digest golden, task, and traceability row
before dependent code. Do not change unrelated accepted architecture.

---
