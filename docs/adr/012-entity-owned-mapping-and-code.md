# ADR 012: Entity-owned Mapping and Code

- Status: accepted
- Date: 2026-09-27
- Supersedes: Binding and physical target prerequisites in ADR 004; Object selection
  and Silver source identity in ADRs 008–011. Their unaffected governance decisions remain.

## Decision

A Model owns its Logical and Dimensional Entities, their Mapping, and generated
Code before physical target registration. The authoring path is Model Input Scope,
Profiling/Analysis/Assertions, Conceptual, Logical, optional Dimensional, Mapping,
Code, and optional Validation. Applied Entity and Mapping prerequisites still
apply; Target Registration and Model Binding are no longer intervening steps.

Models configure `logical_schemas` and `dimensional_schemas`, each a bounded list
of schema names and nullable descriptions. Entity identity includes Model, layer,
schema, and name. Attribute identity extends that Entity key. Relationship
endpoints, support references, Mapping, Code, snapshots, and Workbench use the
same complete identity. Equal names in different schemas remain independent.

Mapping Object records reference exactly one typed Logical or Dimensional Entity
and one contributing source System. Mapping Attribute records reference the
corresponding typed Attribute. Composite foreign keys prove Model ownership,
parent Entity, and parent Mapping; mutually exclusive checks prevent mixing layers.
Generated Code references exactly one typed Entity. Artifact names are unique
within that Entity; source-System assignments retain their existing coverage rules.
The Model Object Binding and Model Attribute Binding tables and public datasets
are removed.

Logical source support remains physical Source/Bronze metadata plus Assertions.
Dimensional support uses same-Model Logical Entity and Attribute references plus
Assertions. Dimensional authoring can therefore start from applied Logical state
without registering Silver Objects. Dimensional Mapping considers Logical Entities
with active Logical Mapping for the selected source System and records complete
Logical keys in its transformation source references. Logical Mapping also exposes
eligible Logical peer lookups; Dimensional Mapping exposes eligible Dimensional
peer lookups. These use typed, schema-qualified `source_logical_*` and
`source_dimensional_*` lists with aliases. During generation, peers require active
same-Model Mapping for the selected source System. SQL context resolves their
planned Silver/Gold names without registration. A saved Mapping referencing an
unready peer leaves consumer context incomplete and blocks Code generation.

Runs freeze typed Entity identity, schema/name, order, and selected Attributes in
`application.workflow_run_entity_selection` and Mapping target selection records.
Historical selections have no foreign key to live Entity rows, so Entity deletion
does not erase run history. Physical-input workflows retain Object selections.
Entity deletion follows direct Mapping/Code dependencies and typed cross-layer
Logical source references. Locks, atomic preview/apply, and governed deletion rules
remain authoritative.

SQL generation projects planned target coordinates from the Entity schema/name
and the Model Tenant's configured GDS placement. Consumer context version
`entity-3` distinguishes this context from registered physical target context and
the earlier context carrying source-System dependency order.
Mapping coverage and server-derived currentness digests still gate generated
Code. Model-owned Validation groups/checks retain their System/layer context.
Applying any Model section stores authored state; it does not execute a load.

Target export is an optional separate handoff from applied Entities to governed
Silver/Gold Object and Attribute metadata. Metadata Change Set validation and
Apply remain required. Process registration continues to reference registered
physical Objects, Attributes, and explicit external artifact paths. Deployment,
file placement, and orchestration execution remain separate authorized actions.

## Mapping coverage and Assertion fallback

Each selected Entity/System pair runs independently and must cover every
actionable Attribute. The Run produces a successful draft only when every pair
succeeds or has a valid no-applicable-source outcome. A provider, evidence, or
validation failure in any pair fails the Run; other successful pairs cannot
silently complete a partial draft. Existing Mapping or known source support
prohibits skipping a pair as inapplicable.

Models may choose an existing active System with an active Connection in their
Tenant as `default_mapping_source_system_id`. It supplies one Mapping pair only
for an Entity supported by active Assertions, with no active physical or Logical
Entity/Attribute source support. Explicit Assertion document Tenant/System scope
must match the Model/default or be unspecified. This cannot relabel known source
provenance or bypass unavailable upstream Mapping. The server marks the pair
`source_system.is_default=true` and supplies no physical/peer source candidates.
Authoring requires explicit generation rules for every actionable Attribute;
missing rules fail validation instead of generating invented data or skipping
the pair. Generated Code retains the ordinary source-System coverage checks.

## Compatibility and verification

Model Snapshot payload version is 2.0. Catalogs reject removed Binding and Mapping
System-dependency datasets
and Entity keys missing schema fields. Metadata snapshots and transport/session
schemas retain their independent versions. Plugin guides, Workbench validation,
DBML, JavaScript/PowerShell helpers, and the Stage extension use this contract.
Existing Entity records without schemas and saved Binding candidates require
reauthoring; this release supplies no populated-database migration or backfill.

Authorization, Source Tenant checks, Tenant Locks, Model revision fences,
idempotency, record locks, and immutable workflow provenance remain unchanged.
The SQL sequence is for fresh installs only. Database verification uses fixture-
created disposable PostgreSQL containers; packaging checks compare rebuilt local
plugin ZIP and extension VSIX artifacts with source.

## Follow-up: runtime ordering

Mapping stores only Object and Attribute records. The separate Mapping
System-dependency table, dataset, editor and agent context are removed. Code
source-System context carries resolved identity without an execution-order
property. Stable sorting makes context reproducible; it never establishes
business precedence. Object dependency order, modeled lookup prerequisites,
SQL stage order and explicit cross-System reconciliation remain part of the
transformation design. Process Group dependency order and Process execution
order configure the external runtime schedule.

## Follow-up: inferred Analysis cardinality

Analysis now stores `inferred_cardinality` independently of measured validation:
`one_to_one`, `one_to_many`, `many_to_one`, `many_to_many`, or `unknown`.
Generation supplies the value explicitly and explains its reasoning in the
existing `relationship_basis`; omitted stored values default to `unknown`.
Validation preserves the inferred value. Readers derive observed cardinality
from measured endpoint uniqueness and flag disagreements for review without
rewriting either conclusion or blocking solely on that difference. Conceptual
and Logical relationships still assess cardinality at their own grains.

Further SCD attribute-policy changes remain separate work.
