# Prompt input contracts and lifecycle audit

Read-only checkpoint, 2026-09-05. No production edits. Synthetic metadata only;
no real rows, rendered prompts, provider output, or credentials retained.

## Verified defects and existing protections

1. Enrichment has a concrete resolver mismatch: seed04 registers
   `workflow.metadata_enrichment.one_shot.candidate_authoring.context` and
   `workflow.validation_failures`; `metadata_enrichment/service.py:322` supplies
   only `stage_context` and `validation_failures`. `render_prompt` resolves by
   resolver key and eagerly requires every required variable even when unused
   by the template. This can make every description batch unavailable before
   contacting the provider. Reported to root for the current enrichment slice.
   Test must load the actual installed seeded plan, not construct variables with
   a convenient test-only resolver. Keep direct physical completion unchanged.

2. Catalog calls almost every payload `stage_context`, generic `json`, with an
   example `{schema_version, items}` that does not describe the delivered shape.
   The same apparent variable means a full authoring context, a retrieval
   manifest, one Object contribution, one entity-detail partition, a review
   package, or a digest-only Code manifest. Users cannot infer collection or
   required fields from that definition. Validation has the same issue under
   `validation_context`.

3. API already returns `example`, but `PromptTemplateDetail.tsx::AllowedVariables`
   discards it. Resolver implementation keys dominate the table; no structure,
   source/availability, pagination meaning, insertion control, or empty-value
   semantics are shown. Fixing the table alone does not fix the input contract.

4. Seed05 currently has 37 stage-specific objectives/methods and deliberately
   obtains large evidence from `context.original_context`. Most allowed
   variables are unused. Do not regress to embedding the full same context in
   both template text and request JSON. Code/Validation explicitly use tiny
   context manifests to avoid duplication. Existing tests assert prompt length,
   duplicate sentences and allowed names, not that each actual stage context
   supplies every documented variable or that schemas/examples agree.

5. `validation_failures` is OUTER reconciliation feedback in the only two seeded
   templates that use it (Analysis whole-slice, Logical whole-model). Inner
   repair feedback is separately updated under `context.repair` by
   `ValidationRepairRunner`; templates are rendered once before that loop.
   Do not relabel the mostly-empty legacy variable as current repair feedback.
   Document the two origins, and expose current inner feedback separately only
   if it is genuinely resolved for each attempt.

6. Concrete typed source objects already exist. Reuse `AgentAuthoringContext`,
   `SelectedObjectContext`, canonical modeling records, Mapping preparation
   models, and each detailed stage result model. Avoid a second generic data
   model or arbitrary JSONPath/query resolver. Output schemas already come from
   validators, including dynamic per-call coverage; they remain authoritative.

7. Tool-assisted context is a manifest, not complete evidence. It has
   `dataset_counts` (retrieval items), `dataset_record_counts` (source records),
   optional fragment metadata, and bounded dataset tools. These counts differ
   when a large record is fragmented. Schema/help must explicitly explain this,
   pagination, reassembly, and that missing retrieval is not negative evidence.

## Smallest cohesive design

Use a backend-owned, fixed stage input catalog that describes and projects the
existing bounded context. Keep SQL as the allowed-variable/stage registry and
the existing frozen Prompt Version snapshot. No variable-authoring CRUD,
arbitrary JSONPath, new SQL resolver, or new context query layer is needed.

Each registered variable needs an explicit contract:

- `name`: readable domain name, same meaning and shape wherever reused.
- `resolver_key`: fixed backend implementation identifier, secondary in UI.
- `data_type`: existing scalar/json type, plus `value_schema` for JSON shape.
- `description`: what decision this input supports.
- `source`: selected physical metadata, applied Model records, previous stage,
  configured naming/template/guide, tool manifest, or current repair feedback.
- `availability`: always, empty when absent, current partition only, or retrieved
  through named bounded tools. An absent input is different from an empty list.
- `example`: small synthetic example conforming to `value_schema`; never real
  metadata. Reference shared Pydantic schemas instead of copying field lists.
- `delivery`: literal variable value versus structured evidence path and tool
  dataset. Show both honestly; a digest/manifest must not masquerade as rows.

New descriptors can be computed in the Prompt service from an allowlisted
resolver catalog, retaining stored descriptions/examples for legacy resolvers.
This avoids adding several database columns just for documentation. Actual
projection happens in the shared stage runner (and the few direct-render paths)
before rendering; no frontend derivation. Strictly validate projected values
against reused schemas. Use explicit stage adapters where contexts differ;
one silent fallback that returns `{}`/`[]` for any missing key hides defects.

Normalize identity/configuration into a compact `model_context` object (name,
revision, description, workflow/layer) rather than today's `model_name`, `model`,
or `run` variants. Keep physical Object/Attribute natural keys and opaque stage
references unchanged. Separate storage and inferred type in every physical
Attribute description; inferred type is semantic evidence, not permission to
change Bronze storage. Do not expose internal full snapshots used for final
graph validation or reintroduce forbidden identifiers/raw physical rows.

Use literal variables for compact meaningful controls and assigned work:
`model_context`, `naming_instructions`, `audit_columns`, `coverage_requirements`,
`source_object`, `entity_topology`, `mapping_partition`, `target_ref`,
`system_ref`, `sql_generation_guide`. Expose large evidence blocks with their
real schema and exact structured delivery path; defaults should reference those
blocks once instead of interpolating duplicate copies of whole arrays. If a
custom template chooses to inline a large block, keep the existing total
request-byte check. Do not replace `stage_context` with several equally opaque
untyped `context_*` blobs.

Keep `stage_context`, `validation_context` and all existing resolver keys as
legacy aliases with their original values. New variables must not make old
frozen/custom prompts depend on missing inputs. Stage variable definitions are
currently joined live by `authoring/plan.py`; Prompt Version contents/digests
are frozen, but variable definitions are not separately snapshotted. Therefore
do not alter existing resolver meaning or make new conditionally available
variables globally required. Fresh seed defaults may use new definitions;
never mutate published/custom Prompt Versions or add a populated-DB backfill.

## Concrete stage inputs and outputs

The table names usable inputs, not additional backend queries. Each comes from
an already assembled context or the immediately preceding validated stage.
Shared `model_context`, optional naming/audit guidance, exact output schema and
repair envelope apply where relevant.

| Stage | Distinct useful inputs | Required output and decision |
| --- | --- | --- |
| Metadata / candidate_authoring | `description_requests`: target_ref, kind, name, parent/related metadata and typed evidence available in that request | Exactly `descriptions` keyed by assigned refs; string or null. Types remain deterministic backend work. |
| Analysis / one-shot relationship_inference | `selected_objects`, `profiles`, `applied_relationships`, `modeling_assertions` | Exact physical endpoint relationships, evidence basis, direction/kind/confidence; permitted empty list. |
| Analysis / tool-assisted | `context_manifest`, typed selected-object/profile/assertion/applied datasets, retrieval instructions | Same candidate schema; distinguish actual metadata from manifest counts. |
| Analysis / candidate_finder | `slice_ref`, `left_attributes`, `right_attributes`, `evidence_fragments`, `coverage_requirements` | Slice coverage plus unique slice-prefixed candidate_refs and endpoint pairs; no final direction. |
| Analysis / relationship_resolver | `source_slice_ref`, `endpoint_candidates`, source evidence manifest, applied evidence availability | Each candidate_ref exactly once, relationship/no_relationship/needs_review with matching nullable payload. |
| Analysis / whole_slice_reconciler | `reconciliation_work_items`, `work_manifest`, `outer_validation_findings` | Candidate/applied coverage and relationships, preserve required applied refs, resolve actual conflicts. |
| Analysis / analysis_reviewer | `review_work_items`, `work_manifest` | Every assigned review ref and only supported findings, without candidate mutation. |
| Conceptual / one-shot or tool-assisted | Selected metadata or manifest, profiles, Analysis, Assertions, applied Conceptual, naming | Objects + relationships over valid business concepts; grain and exact supports. |
| Conceptual / object_contribution | `contribution_ref`, `source_object`, assigned Attribute evidence, relevant profiles/Assertions/Analysis | One contribution with explicit disposition; represented iff proposals nonempty. |
| Conceptual / entity_consolidation | `entity_proposals`, exact proposal coverage | Canonical entities/discards partition proposal refs once; names derive from members. |
| Conceptual / entity_attribute_detail | `canonical_entity_ref`, `entity_proposals`, exact support set, naming | One complete Conceptual Object; despite stage name this is not physical Attribute authoring. |
| Conceptual / relationship_cardinality_refinement | `relationship_package`, endpoint Conceptual Objects, signal evidence | Package disposition/rationale and nullable relationship, cardinality only when supported. |
| Conceptual / whole_model_reconciliation | Detail records, relationship decisions, applied records and required ref sets | Objects/relationships plus entity/input/package/applied coverage arrays. |
| Logical + Dimensional / one-shot | Selected metadata (Source/Bronze for Logical, eligible Silver for Dimensional), prior evidence, applied same layer, naming/policy | Complete four-dataset candidate with explicit source mappings and policy fields. |
| Logical + Dimensional / tool-assisted | Layer-specific manifest/dataset contracts | Same candidate as one-shot; retrieve exact source and applied dependencies before deciding. |
| Logical + Dimensional / topology_builder | `contribution_ref`, `source_object`, `source_attributes`, `coverage_requirements`, supporting evidence | One classification/contribution; represented proposals partition assigned Attribute keys exactly once. |
| Logical + Dimensional / topology_reconciler | `topology_contributions`, `coverage_requirements`, applied topology | Canonical submodels/entities and explicit discards partition proposals once. |
| Logical + Dimensional / entity_detail_builder | `entity_topology`, `topology_contributions`, exact selected Object/Attribute slices, audit/policy fields | One entity-detail partition with explicit Attribute definitions, types, keys, nullability and source maps. |
| Logical / whole_model_reconciliation | Required topology/detail records, relationship signals, applied records, batch coverage, outer findings | Full assigned four-dataset partition + exact reviewed_* references. |
| Dimensional / whole_model_reconciliation | `partition_ref`, `review_manifest`, assigned `relationship_signals`, endpoint evidence | Receipt only: partition_ref, unchanged manifest, ordered reviewed_relationship_signal_refs, relationships. Do not copy Logical's full-candidate output. |
| Logical + Dimensional / validator_worker | `validation_package`, `package_manifest` | Package_ref, exact reviewed_record_refs, errors/warnings citing only package records. |
| Logical + Dimensional / validator_lead | `worker_results`, `worker_result_manifest` | Exact reviewed packages/findings, all-and-only blocking errors, nullable repair_brief. No new candidate or findings. |
| Mapping / mapping_authoring | `mapping_pair`, `target`, `source_objects`, `modeled_records`, readiness, dependency graphs, selected templates | schema_version, nullable object_mapping, actionable attribute_mappings only; backend owns identities. |
| Mapping / header_mapper | `mapping_partition`, target/source metadata, Object readiness/template | Object transformation only; empty Attribute mappings. |
| Mapping / attribute_mapper | `mapping_partition`, exact assigned Attribute names, reviewed/preserved Object transformation, source evidence/template | Null Object mapping; each assigned Attribute once, concrete expressions/casts/null handling. |
| Mapping / target_validator | Same assigned partition evidence + `candidate_mapping` | Corrected same partition/envelope, no added outside records or manifests. |
| Code / sql_generation | `target_ref`, `target_metadata`, `source_metadata`, applied Object/Attribute mappings, selected Systems/dependencies, `sql_generation_guide` | Exact per-target artifact schema; guide content delivered once, no execution claims. |
| Validation / validation_generation | `system_ref`, `mapping_targets`, current generated Code, applied Validation groups/checks | Per-System full replacement definitions; explicit checks/query comparison semantics. Authoring is distinct from actual execution. |

## Prompt writing and UI gate

Rewrite each default around the actual stage: one outcome sentence; precise
assigned inputs; three to five decision steps; exact expected envelope and
coverage; explicit permitted insufficient-evidence outcome. Shared system text
owns authority and data-as-data rules once. Tool text names allowed tools,
necessary datasets, paging completion and missing-evidence behavior. Keep
implementation digests out of prose except receipt/coverage stages that actually
must echo or verify them. Do not impose a universal full-output rule on partition
or reviewer stages. Schema stays supplied by the validator, not hardcoded again
in prose. Avoid claims of guaranteed correctness or bypassing validation.

Prompt editor should show purpose and stage input/output summary beside the
editor, then a searchable variable dictionary. Each entry shows readable name,
type, source/availability and insertion action; expand for schema fields and a
synthetic example. Distinguish inline variables from structured evidence and
retrieved datasets. Resolver key belongs in secondary technical detail. Show
unknown/unavailable placeholders before save, with backend revalidation. Preserve
immutable versions, permission/lock fences and manual Refresh.

Required verification before calling this complete:

1. Actual fresh installed reference + prompt seeds -> public run creation ->
   frozen plan -> each real context constructor -> renderer/stage execution.
   Cover all 37 stages and all three modes; no test-only resolver naming.
2. Each catalog example validates its schema, each required projection exists,
   each default variable is registered/resolved, and each advertised variable
   can be used in a custom template with representative stage contexts.
3. Distinguish complete metadata, compact/projected evidence, fragmented tool
   manifests, empty evidence and unavailable evidence; prove no silent fallback.
4. Repair test makes attempt one invalid and verifies attempt two receives the
   current issues and previous candidate or omission marker. Outer findings and
   inner repair must not be confused; preserve original evidence/valid work.
5. Large multi-object/multi-partition synthetic fixtures exercise true byte and
   coverage boundaries, inferred-vs-storage types, locks and parent dependencies.
   Check structural output, schema validation and meaningful repair behavior;
   do not assert only prose lengths or fake provider call counts.
6. Legacy/custom/frozen stage_context still renders its exact old value. No
   raw rendered content or provider output in captures/artifacts. UI tests verify
   examples/schema/insertion, keyboard use and narrow layout.

## Separate graph lifecycle reproduction

Initial scratch reproduction: 6 passed, pure Python; now promoted into
`tests/mcp/test_model_change_set_validation.py` and the throwaway removed. Three
baseline stage graphs are valid. Staging an inactive Conceptual Object while its
Relationship stays active is still accepted. Staging inactive Logical and
Dimensional Entities while Attributes/Relationships remain active is also
accepted. Tests isolate these stages from Bindings so later Binding checks do
not conceal the gap. Each changed graph returns complete with zero issues.

`model_validation.py::_validate_references` checks endpoint existence without
status; `_validate_active_dependencies` starts at Object/Attribute Bindings and
never checks active Conceptual endpoints or active modeled Attribute parents.
The next lifecycle slice should add these checks, then test active modeled
Relationship endpoints and active nested submodel memberships as appropriate.
Explicit review must validate the resulting whole graph and return actionable
dependency conflicts; do not silently cascade/deactivate children.

Enrichment read aggregate verified by inspection: all three `applied_field_counts`
keys are always emitted with whole-run applied-only counts. Read DTO requires
those exact keys and reconciles to applied status. Both fresh and replay
completion strip the read-only aggregate; no completion contract drift found.

## Render-path and lifecycle implementation handoff

All provider execution passes through `AgentStageRunner.run` ->
`ValidationRepairRunner.run` -> adapter. The additional direct `render_prompt`
calls are production byte-budget probes, and must use the identical new
projection contract:

- Logical `service.py::_detailed_stage_fits` (around 1430).
- Dimensional `service.py::_detailed_stage_fits` (around 1680).
- Mapping `service.py::_detailed_request_bytes` (around 698).

Analysis and Conceptual construct/partition different contexts but execute
through the shared runner. Code and Validation use common SQL stage identities
(`workflow_execution_mode` null in the registered stage) while execution uses
one-shot; derive resolver scope from frozen stage identity, not request mode
alone. Metadata uses one-shot explicitly. The three probes wrap their context
with original_context/repair before computing envelope size, as the repair
runner does; mismatched projection here causes false fitting or rejection.

Canonical lifecycle implementation should extend `_validate_active_dependencies`
using existing `_active_invalid` (`active_dependency_invalid`),
`normalize_model_key_value`, `_entity_key` and `_attribute_key` conventions.
Only active child/edge records require active parents/endpoints; inactive
historical records remain valid when referenced records still exist. Locks do
not imply activity and must not enter these checks.

- Conceptual: `conceptual_relationship_status`,
  `from_conceptual_object_name`, `to_conceptual_object_name`; active Object set
  uses `conceptual_object_status` and normalized `conceptual_object_name`.
- Logical/Dimensional Attribute: `{layer}_attribute_status`,
  `{layer}_entity_name` must resolve in active `{layer}_entity_status` set.
- Logical/Dimensional Relationship: `{layer}_relationship_status`; both
  `from_{layer}_entity_name` / `from_{layer}_attribute_name` and
  `to_{layer}_entity_name` / `to_{layer}_attribute_name` must resolve to active
  Attributes AND active parent Entities. Check both explicitly so invalid
  applied Attribute state cannot let an active Relationship pass indirectly.
- Existing `reference_not_found` checks stay separate; preserve full graph
  validation and stage repair feedback. No deactivation cascade.

Plugin parity: `workbench/validation/model.js::validateActiveDependencies`
mirrors the backend and has the same gap; add exactly these checks using its
`active`, `normalized`, `tuple`, `entityKey` and `attributeKey` helpers. Existing
Python/Node parity suite is `tests/plugin_v2/test_local_validation_parity.py`.
PowerShell fallback `gds-local.ps1::Add-ModelValidationIssues` currently checks
locks and declared references only; explicitly implement the same bounded
active-parent checks against EffectiveRecords, with its normalizers, rather
than claiming it already mirrors the whole Python graph validator. Add PS5.1
execution cases to existing Windows tests; runtime unavailable locally must be
reported. Rebuild matching plugin ZIP after parity changes; no VSIX change
unless extension source is touched.

Canonical implementation checkpoint: shared active-dependency checks added for
the three proven rules above. Promoted tests exercise parent deactivation,
child/Relationship reactivation, both endpoints, case/space-normalized names,
both modeled layers, and active/inactive records independently of lock flags.
All 65 canonical validation tests pass; Ruff and production Pyright are clean.
Logical full-graph repair regression retains its original inactive-Entity
candidate and now expects both Attribute-parent and Object-Binding findings;
all 27 Logical executor tests pass, including successful repaired final graph.
No submodel-membership rule added without a separate proven contract.
