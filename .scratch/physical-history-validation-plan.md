# Physical lifecycle and retained Model history

Read-only diagnosis, 2026-09-05. No production changes in this checkpoint.

## Reproduced

Pure canonical fixture/catalog reproduction through `validate_future_graph`:

| Case | Result |
| --- | --- |
| Complete applied graph, current physical catalog | Valid |
| Source Object removed from catalog/eligibility as physical deactivation does | Invalid Input Scope, Profile, Analysis, Conceptual and Logical physical references |
| Same physical deactivation; all Model lifecycle flags and nested supports/sources inactive | Same physical reference failures |
| Restore all-history Object/Attribute existence but keep active eligibility filtered | Same failures; existence catalog alone is insufficient |
| Deactivate one bound Silver physical Attribute | Both ineligible Attribute Binding and binding_coverage_missing |

The reproduction printed only validity, phase and deduplicated code/dataset pairs.
No physical rows or prompts were retained. These cases need permanent tests in
the implementation slice, including actual fixture SQL catalog loading.

Cause: `_MODEL_PHYSICAL_SCOPE_SQL` excludes inactive Object/Attribute records.
`_validate_physical_scope` checks ALL existing Input Scope, Profile, Analysis,
Conceptual support, Logical/Dimensional source and Binding references against
current active eligibility, independent of their own status. Profiling has no
lifecycle status. Whole-graph validation runs on every ordinary Model write or
review, so unrelated changes can become blocked. Model datasets are upserts;
omitting a historical row does not remove the failure. Physical reactivation
restores validation, so this is recoverable but not through ordinary Model
lifecycle cleanup alone.

## Recommended next slice

Keep physical availability separate from retained Model evidence. Existing
Model lineage remains inspectable when a physical record is inactive; new
authoring and workflow execution still require current eligible inputs.

1. Make `PhysicalModelCatalog.objects` and `.attributes` mean **all existing
   Source Tenant-owned physical keys**, including inactive Object/Attribute
   records. Remove only their lifecycle filters from the catalog loader; keep
   Source Tenant ownership and existing Connection/System/Tenant authorization.
   The four eligibility Object/Attribute sets continue to mean current active
   eligibility and still come from governed SQL eligibility functions. Do not
   broaden workflow context, candidate selection, or credential queries.

2. Pass the already available effective baseline records into physical-scope
   validation. Identify retained records by existing canonical dataset keys.
   A record qualifies as retained history when it is exactly the prior record,
   or differs only by explicit lock/unlock and/or deactivation flags, including
   existing nested supports/sources. Never treat reactivation as retention.
   Never treat a new record, changed natural reference, added nested edge,
   altered definition, or changed measurement as retained unchanged evidence.
   This gives ordinary lock/unlock/inactive review a coherent result after a
   physical deactivation, without allowing an author to forge new inactive
   references to bypass current eligibility.

3. Validate every retained physical reference against the complete owned
   Object/Attribute sets. Missing/reowned references still fail. Apply existing
   active eligibility and Model Input Scope checks to new/reactivated/authored
   records. New inactive records also require legitimate current references:
   an inactive flag cannot manufacture historical provenance. Existing exact
   Profile rows use historical existence; new/changed Profile rows still need
   active selected scope, since Profile has no status. Keep Tenant/System
   authorization, cross-model natural-key uniqueness and all schema checks.

4. Binding coverage needs an explicit historical set as well. An active bound
   modeled Attribute remains represented by its retained active Attribute
   Binding even when the physical Attribute becomes inactive. For each Object
   Binding, expected physical Attribute coverage is the current eligible
   Attributes **plus retained active historical Attribute-Binding targets**.
   Validate every such target's present Source ownership/existence first.
   New/changed/reactivated bindings must pass current layer eligibility.
   Keep active modeled Attribute coverage, duplicate-target checks, active
   Object/Attribute Binding dependencies and reference checks unchanged.

5. Guard Dimensional source derivation: future active Logical Mappings currently
   augment eligible Silver source sets from `bindings[0/1]`. Historical active
   bindings may now point at inactive Silver metadata. Only add a future mapped
   Object/Attribute to current Dimensional eligibility if it also occurs in the
   current active Logical target eligibility set. Otherwise an old active
   Mapping could incorrectly authorize a NEW inactive Silver source reference.
   Existing Dimensional history instead passes through the existence check.

6. Canonical active Model-layer dependencies remain global: active Conceptual
   Relationships need active Objects; active modeled Attributes need active
   Entities; active modeled Relationships need active Attributes and Entities.
   The physical-history allowance does not change those Model graph rules.
   No silent scope reattachment, parent/child cascade, physical reactivation,
   metadata creation, Model revision bump or populated-DB migration/backfill.

The retained-history classifier is a domain rule worth one shared helper; avoid
scattered `if old_record` bypasses. Preserve identity/content equality, inspect
status direction explicitly, and treat only known lifecycle fields specially.
Return or pass explicit sets of retained dataset canonical keys into scope and
Binding validation, so checks remain readable and testable. Existing helpers
already provide canonical keys and current/future datasets. Do not rely on
caller-supplied flags to assert historical provenance.

## UX behavior

Physical deactivation updates shared metadata and removes it from new workflow
selection. Applied results retain their references and remain readable and
lockable. Show current physical status in relevant source/provenance detail.
Reactivating a Model result that requires a currently inactive physical input
should return an actionable eligibility conflict, with a route to metadata
review, rather than generic backend validation failure. Physical reactivation
does not change an explicitly inactive Model Input Scope row. Ordinary Model
reactivation still checks all modeled parent/endpoint dependencies.

## Verification gate

- Loader: all-history existence includes inactive owned Objects/Attributes,
  still excludes reowned/foreign records; active eligibility remains filtered.
- Existing complete Model graph survives Source Object, source Attribute,
  Silver bound Object and bound Attribute deactivation. No-change validation,
  unrelated Model edit, lock/unlock and deactivation review remain usable.
- Full new/reactivated/authored records cannot introduce inactive physical
  refs; new inactive records cannot forge history; changed Profile metrics
  require current eligibility. Newly added nested refs do not inherit history.
- Historical binding coverage remains exact; a new Binding to inactive target
  fails. New Dimensional source cannot inherit eligibility from inactive
  historical Silver Mapping. Parent/model dependency validation still rejects
  invalid active graph shapes.
- Retained missing/reowned refs fail; physical reactivation restores eligibility
  without altering Model scope. Immutable prior evidence remains unchanged.
- JS plugin uses the same all-existing versus active-eligibility distinction and
  retained-baseline classifier; PS fallback does not claim broader parity than
  it actually implements. Rebuild ZIP after parity changes.
- Actual disposable SQL -> snapshot -> catalog -> validation and review tests;
  no existing database, migration or external Databricks run.
