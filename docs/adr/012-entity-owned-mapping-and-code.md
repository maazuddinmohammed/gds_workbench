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

Each selected Entity/System pair runs independently. The partial-application
policy confirmed on 2026-09-28 permits partial output within a pair: a valid Object
transformation **or** any valid Attribute transformation retains the pair. Missing
transformations are blank; unsupported rules or joins must never be invented to
satisfy a coverage count. An Entity with ten active modeled Attributes and five
Attribute mappings shows all ten Attributes, with five blank transformations.
Missing Attribute rows are derived by the backend from modeled Attributes and
have no Mapping record ID. Attribute-only output leaves the Object document blank.

For selected, unlocked records, omitted or null output clears the saved document
on regeneration. Locked and unselected mappings are preserved. Existing Object
logic is also preserved when any Attribute is locked or unselected, so changing
joins or grain cannot silently change protected Attribute behavior. A new pair
with neither Object nor Attribute output creates no empty parent or child records.
An existing pair cleared of all output keeps its record identities and history;
its detail URLs remain readable, but the Entity ledger hides the empty pair.

Valid partial pairs and valid sibling pairs form one draft, revalidated against
the entire future Model graph before ordinary review and Apply. Recoverable
provider, evidence-access or candidate-integrity failures affect only their pair;
failed pairs remain unchanged or absent. With no successful changes, any true
failed pair fails the Run, not a successful no-op. Authorization, Tenant Lock,
worker claim, revision and finalization failures remain fatal. No-source and
empty-output outcomes remain distinct from failed pairs.

Typed per-pair terminal events distinguish completed, partial, preserved,
no-source, empty and failed outcomes. Their one-based position identifies the
immutable ordered Run target selection; it is not execution progress. Read
projections attach frozen Entity schema/name and System identity without parsing
event messages. A completed Run with incomplete or failed pairs shows **Partial
results**, including after Apply. The web app reports incomplete counts separately
from the failed-pair issue list and explains that missing selected transformations
will become blank before Apply. All-failed Runs expose diagnostics without an
applicable draft. Legacy Runs without these events retain their recorded status.
The validated draft retains ownership, lock, revision, digest, expiry, idempotency
and Apply validation. Retrying after Apply requires a new Run.

Partial Mapping is saved authoring progress, not downstream readiness. Code and
Validation retain complete Mapping eligibility, source-reference and coverage
checks. Applying Mapping neither generates nor executes Code or Validation.

Models may choose an existing active System with an active Connection in their
Tenant as `default_mapping_source_system_id`. It supplies one Mapping pair only
for an Entity supported by active Assertions, with no active physical or Logical
Entity/Attribute source support. Explicit Assertion document Tenant/System scope
must match the Model/default or be unspecified. This cannot relabel known source
provenance or bypass unavailable upstream Mapping. The server marks the pair
`source_system.is_default=true` and supplies no physical/peer source candidates.
Authoring requires explicit rules for each transformation it returns. Missing
rules leave the corresponding transformation blank while retaining supported
output; they do not justify invented data or a different source System. Generated
Code retains the ordinary source-System coverage checks.

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
