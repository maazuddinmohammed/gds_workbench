# Logical Build

## Inputs

Require fresh Snapshots. Scope is active Objects with `is_bronze_source_eligible=true`, plus active
Attributes, Profile, Analysis, Conceptual, and Logical work. This flag is authoritative; Bronze
labels are insufficient. Support cannot override physical grain or fabricate evidence.

Choose Build mode, Full/Selected, and Analysis → Conceptual → Logical; first two are optional,
Logical mandatory. Ask when unspecified; Automatic never selects silently. Full covers every
eligible item; Guided pauses by Object group; Custom preserves coverage.

Before writing, load each selected Model output dataset contract.

Before selected sections, report Profile readiness as
`scoped_attributes`, `profiled_attributes`, and `unprofiled_attributes`. For each scoped Object,
use bounded Attribute/Profile selections for gaps. Missing Profile evidence is a quality warning
and never blocks Logical Build by itself. Profiling remains web/notebook-governed; SQL policy may
add bounded evidence, never fabricated or authoritative Profile records.

Coverage uses scoped physical Objects: Analysis assesses candidate relationships for each Object;
Conceptual and Logical classify each Object. Profile Attribute counts are evidence, never the
denominator. Do not create a coverage file. At each selected-section checkpoint, batch-save complete records, run `review`, show counts/items, then update one plan line: `Coverage <section>: scope=<n>; covered=<n>; excluded=<n>; blocked=<n>` plus unresolved identifiers. A checkpoint never accepts, Stages, or Applies. The final review covers the digest; reuse it and do not call `review` again. Then validate, accept, and Stage once.

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
6. Attach support, rationale, and confidence; unresolved claims become `needs_review`.
7. Mark the Object covered, excluded with reason, or blocked. Never silently skip it.

For every active Logical Entity/Attribute, retain physical or Assertion sources with rationale. Conceptual results improve names/boundaries but do not drive structure.

Reuse the last review; validate/accept its digest. Perform one Stage, server Validate, and Apply; mark Model stale and stop.
