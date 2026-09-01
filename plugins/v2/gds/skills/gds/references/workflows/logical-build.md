# Logical Build

## Inputs

Require fresh Snapshots. Scope is active Objects with `is_bronze_source_eligible=true`, plus active
Attributes, Profile, Analysis, Conceptual, and Logical work. This flag is authoritative; Bronze
labels are insufficient. Support cannot override physical grain or fabricate evidence.

For every physical Object support, preserve `tenant_code`, `system_code`, `connection_code`, `object_schema`, and `object_name`;
copy them exactly from the eligible `model_scope` record and the matching Bronze Object/Attribute.
They may differ from the session/Model Tenant and upstream source System.

Choose Build mode, Full/Selected, and Analysis → Conceptual → Logical; first two are optional,
Logical mandatory. Ask when unspecified; Automatic never selects silently. Full covers every
eligible item; Guided pauses by Object group; Custom preserves coverage.

Load each compact Model dataset contract only immediately before that dataset's first batch.

Before selected sections, report Profile readiness as
`scoped_attributes`, `profiled_attributes`, and `unprofiled_attributes`. For each scoped Object,
use bounded Attribute/Profile selections for gaps. Missing Profile evidence is a quality warning
and never blocks Logical Build by itself. Profiling remains web/notebook-governed; SQL policy may
add bounded evidence, never fabricated or authoritative Profile records.

Coverage uses scoped physical Objects; Profile Attribute counts are evidence, not the denominator.
At each selected-section checkpoint and batch, save complete records, run local `review`, and update the persisted
Loop counts/next key. A write sets task state `review`; while coverage remains, Automatic must
transition `review` → `doing` and continue in the same turn; do not ask the user at a section checkpoint.
Guided pauses only at its chosen group, then resumes `doing`. Only the final complete digest is a human review boundary.
After approval, perform promotion, validation, acceptance, Stage, Validate, and Apply.

## Analysis loop

Use only Snapshot profile, Analysis, physical-key, and Assertion evidence. An Analysis row may be inference-only: record endpoints, relationship kind, basis, confidence, and status with all nine validation fields absent. Deterministic measured validation uses all nine fields together; a partial group is invalid. Never fabricate validation evidence or run SQL. Missing validation alone does not block a supportable inference; a separate deterministic validation step may populate the group later.

## Conceptual loop

Group selected physical Objects into concepts without changing coverage. Each Conceptual Object/Relationship needs definition, grain/cardinality basis, confidence, and active Object or Assertion support. Mark each covered, excluded with reason, or blocked. Conceptual improves language/boundaries; Conceptual never drives Logical structure.

## Logical loop

For each scoped physical Object:

1. Record evidence-backed grain and purpose.
2. Split mixed grains; consolidate only demonstrably same-grain structures.
3. Build third-normal-form Entities and Attributes.
4. Derive keys/relationships only from physical/profile/analysis/assertion evidence.
5. Allow policy-driven technical/audit Attributes but label their policy source.
6. Attach support, rationale, and confidence. Evidence-supported results are `active`; only a
   complete proposal with one unresolved semantic decision is `needs_review`. Missing grain,
   lineage, or keys blocks the item.
7. Mark the Object covered, excluded with reason, or blocked. Never silently skip it.

For every active Logical Entity/Attribute, retain physical or Assertion sources with rationale. Conceptual results improve names/boundaries but do not drive structure.

Perform one final review, then one Stage, server Validate, and Apply; mark Model stale and stop.
