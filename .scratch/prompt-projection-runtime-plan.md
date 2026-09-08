# Prompt projection: runtime census and bounded implementation plan

Read-only follow-up to `prompt-normalization-audit.md`, 2026-09-05.
No production changes. No prompts, context values, provider output, credentials,
or physical sample rows retained. The older enrichment resolver defect in that
audit is fixed; the fresh installed defaults resolve successfully now.

## Measured checkpoint

`prompt_context_census.py` installed SQL04 reference data and SQL05 defaults via
the guarded disposable PostgreSQL fixture, loaded the real 37 seed definitions
into memory, then ran the seven executor suites and the real enrichment DB
executor suite. A new synthetic Conceptual test supplies an Analysis relationship
to reach actual relationship derivation, refinement context construction, stage
execution, candidate validation, reconciliation and handoff.

- 111 tests passed; 37 stage identities; 873 actual StageRunner calls.
- Each call's real resolver values rendered its matching installed seed in
  memory: no missing required variables, unknown placeholders, warnings or
  rendering errors.
- 89 distinct context shapes, including small/full and large/fragmented forms.
- Maximum combined template text: 264,508 bytes, Code Generation with a large
  guide. Next largest: 3,189 bytes. The existing defaults mostly reference
  structured evidence instead of copying it into prose; preserve that property.
- Code and Validation stage registry mode is NULL/common even when a test Run
  plan carries detailed_coverage. Catalog lookup must use registered identity.

Reports contain only field names, primitive types, counts and byte sizes:
`prompt-stage-context-shapes.json`, `prompt-seed-context-render-report.json`.
`test_prompt_refinement_census.py` is the missing synthetic executor case.

Limits of this evidence: installed templates were rendered beside the real
runner; the runner still executed each test's existing frozen test plan. Most
contexts came from typed synthetic bundles. Code/Validation test bundles include
minimal dictionaries, so this census alone does not establish complete repository
context coverage or model-output quality. No external model was called.

## Fixed catalog contract

Keep one explicit Python catalog keyed by registered workflow/mode/stage and
variable name. Do not add a configurable resolver language, JSONPath evaluator,
SQL resolver, second source query, or generic object-to-dictionary copier.

The new catalog entry describes:

| Field | Meaning |
| --- | --- |
| name / resolver_key | User-facing name and fixed backend identifier. Existing meanings remain unchanged. |
| description | Decision supported, not a repeated field name. |
| data_type / value_schema | Existing rendering primitive plus reusable Pydantic/TypeAdapter JSON schema. |
| source | Selected physical metadata, applied records, prior validated stage, configured policy, or retrieval manifest. |
| availability | Always, current partition only, nullable when delivered as fragments, or retrieved dataset. |
| delivery | Inline variable, structured request field, or named bounded tool dataset. |
| example | Small synthetic value validated against its real schema. |

Expose catalog documentation through the existing Prompt stage-variable DTO;
no documentation-only SQL columns are necessary. The SQL registry remains the
allowlist. Unknown legacy resolver definitions retain their stored help and
original rendering behavior, with no invented schema claim.

Projection runs once before `render_prompt` in AgentStageRunner, using only the
already-bounded context and existing resolver values. The Logical, Dimensional
and Mapping direct byte-fit render probes must call the same projection.
Keep old resolver values verbatim. Add only fixed fields needed by registered
new variables; no normalized clone of the whole context beside the old context.
The provider still receives original_context once. Default prose can reference
the documented exact path of large evidence; custom templates may inline a
named collection within current byte limits.

Do not call a fragment page a list of complete records. Normalize assignment
keys separately from physical metadata. For stages with both full and fragmented
representations, expose a fixed `evidence_delivery` enum and distinct contracts:
`selected_object_keys` always contains actual assigned keys; complete-record
collections are nullable when represented by `evidence_fragments`. Null means
unavailable in this representation, [] means inspected and empty. Document
fragment record_ref/index/count/hash and reconstruction; never parse incomplete
JSON as a complete record or synthesize missing values. Tool manifests likewise
carry retrieval-item counts and source-record counts separately.

Compact common controls can reuse names with the same shape:

- `model_summary`: name, nullable description, revision, workflow/layer; no
  entire ModelDetails object, selected records, private snapshot or catalog.
- Existing `naming_instructions`, audit/technical templates and
  `sql_generation_guide`: preserve exact configured value and delivery.
- `page`: actual current page index/count only where the stage is paginated.
- Explicit stage reference and coverage variables below; no generic
  `coverage_requirements` blob with a different undocumented shape per stage.
- Legacy `validation_failures` stays outer reconciliation feedback. Current
  repair issues are under context.repair, updated after rendering; describe
  that structured envelope separately until rendering actually moves per retry.

New optional registrations must not make an old frozen prompt fail: renderer
eagerly checks every required variable even when its placeholder is unused.
Conditional availability must be encoded deliberately, not caught with a broad
exception and converted to an empty dictionary.

## Exact stage catalog proposed from observed constructors

Names below are meaningful projections, not whole-context aliases. Collections
remain typed evidence; default templates should not interpolate them a second
time. Corresponding actual field paths are listed where the name changes.

| Registered stages | Compact controls / exact assigned work | Typed evidence and existing source |
| --- | --- | --- |
| Metadata one_shot candidate_authoring | assigned_description_refs | description_requests: existing Object/Attribute discriminated request shapes; backend inference is read-only evidence |
| Analysis one_shot relationship_inference | model_summary, selected_object_keys | selected_objects, profiles, analysis_relationships, assertion, applied |
| Analysis tool_assisted relationship_inference | model_summary, selected_object_keys, dataset counts with semantics | Actual catalog datasets; do not expose synthetic empty profiles/assertions |
| Analysis detailed candidate_finder | slice_ref, page, selected_object_keys | selected_objects in full form; otherwise key-only selection plus evidence_fragments and evidence_manifest; profiles/assertions/applied_records only in full form |
| Analysis detailed relationship_resolver | source_slice_ref, candidate_refs | endpoint_candidates from candidate_finder_result.candidates; source_evidence_manifest; applied_analysis_manifest and applied_analysis_deferred_to_reconciliation |
| Analysis detailed whole_slice_reconciler | page, candidate_review_refs, applied_review_refs from work_manifest | reconciliation_work_items, a typed union of resolution_fragment and applied_analysis_fragment |
| Analysis detailed analysis_reviewer | page, relationship_review_refs, applied_review_refs from work_manifest | review_work_items, a typed union of relationship_fragment and applied_analysis_fragment |
| Conceptual one_shot candidate_authoring | model_summary, naming_instructions, selected_object_keys | selected_objects, profiles, analysis_relationships, assertion, applied.conceptual |
| Conceptual tool_assisted candidate_authoring | same compact Model controls and retrieval counts | Actual bounded catalog datasets; applied and dependency evidence must be retrievable |
| Conceptual detailed object_contribution | contribution_ref, source_object key, page, evidence_delivery | Full selected_object/profiles/assertions/Analysis/applied_conceptual, or source_object key plus evidence_fragments and global_evidence_included |
| Conceptual detailed entity_consolidation | proposal_refs, page | Complete contributions or compact contribution_proposals; normalize proposal identity, source supports and candidate-name fields, not missing discarded content |
| Conceptual detailed entity_attribute_detail | canonical_entity_ref, proposal_refs, page | entity (consolidated topology); contributions or compact contribution_proposals; selected_objects only where actually supplied |
| Conceptual detailed relationship_cardinality_refinement | package_ref, from_entity_ref, to_entity_ref | endpoint_entity_details; relationship_package.signals in full form or separate relationship_signals in paged form |
| Conceptual detailed whole_model_reconciliation | required_entity_refs, required_input_contribution_refs, required_relationship_package_refs, required_applied_review_refs, page | Small form entity_details/relationship_packages/relationship_refinements/applied_conceptual; large form reconciliation_work_items typed by work_item_type |
| Logical one_shot candidate_authoring | model_summary, naming/audit policy, selected_object_keys | selected_objects, profiles, analysis_relationships, assertion, applied.logical, read_only_dependencies |
| Logical tool_assisted candidate_authoring | Model controls and explicit retrieval counts | Actual selected/profile/assertion/applied/dependency catalogs |
| Logical detailed topology_builder | contribution_ref, batch manifest's exact assigned keys | selected_object, profiles, analysis_relationships, assertions, applied_logical |
| Logical detailed topology_reconciler | exact proposal refs and batch coverage | topology_contributions from contributions; applied_logical |
| Logical detailed entity_detail_builder | entity_topology from entity, exact batch Attribute keys | topology, contributions, selected_objects |
| Logical detailed whole_model_reconciliation | reviewed entity/contribution/applied/signal refs from existing batch manifest and required_applied_record_refs | topology, entity_details, relationship_signal_ledger, applied_logical, read_only_dependencies; complete four-dataset output remains required |
| Logical detailed validator_worker | package_ref, exact record refs from package_manifest | validation_package: typed records plus coverage |
| Logical detailed validator_lead | exact package/finding refs from worker_result_manifest | worker_results: typed worker results; no new errors outside those results |
| Dimensional one_shot candidate_authoring | model_summary, naming/audit policy, selected_object_keys | selected_objects, profiles, Analysis, assertion, applied.dimensional, read_only_dependencies |
| Dimensional tool_assisted candidate_authoring | Model controls and explicit retrieval counts | Actual eligible Silver datasets and applied/dependency catalogs |
| Dimensional detailed topology_builder | contribution_ref, batch, authoritative_selection_manifest | selected_object and support; support has a different contract from Logical's top-level evidence |
| Dimensional detailed topology_reconciler | exact proposal refs from contribution_manifest | contributions, applied_dimensional |
| Dimensional detailed entity_detail_builder | entity_topology, contribution_manifest | topology, contributions, assertions |
| Dimensional detailed whole_model_reconciliation | partition_ref, exact review_manifest, relationship signal refs | relationship_signals, validation_failure_summary; output is a receipt plus relationships, NOT a Logical four-dataset candidate |
| Dimensional detailed validator_worker | package_ref and contained record refs | validation_package; no separate package_manifest is currently delivered |
| Dimensional detailed validator_lead | package/finding refs derived from worker_results | worker_results; no separate worker_result_manifest is currently delivered |
| Mapping one_shot mapping_authoring | mapping_pair, modeled_entity_type, naming/audit/technical policy | target, sources, headers, readiness, source_system, dependency graphs, output_templates |
| Mapping tool_assisted mapping_authoring | mapping_pair from pair, dataset manifest from datasets | Exact bounded Mapping tool datasets; distinct from authoring-context catalog counts |
| Mapping detailed header_mapper | mapping_partition: include_object=true, attribute_names=[] | Same target/source/header/readiness/template evidence; object transformation only |
| Mapping detailed attribute_mapper | mapping_partition: include_object=false, exact attribute_names | Same evidence with current headers; Attribute transformations only |
| Mapping detailed target_validator | exact same mapping_partition | candidate_mapping from candidate plus same preparation evidence; repair within assigned partition |
| Code common sql_generation | target_ref, selected source-system codes, sql_generation_guide | targets[0].context.target/object_mappings/attribute_mappings/source_systems; guide metadata excludes content already delivered through variable |
| Validation common validation_generation | system_ref, tenant/system scope | mapping_targets, generated_code, applied_validation_groups/checks from real context repository; executor fake scope-only context is not the documentation schema |

This is 37 registered stages, not 37 invented universal input schemas. Unify
fields only when their meaning is actually identical. Keep generated receipt
refs and physical natural keys unchanged.

## Reuse schemas and add only genuine missing boundary types

Reuse `SelectedObjectContext`, `ObjectRecord`, `AttributeRecord`, `PhysicalObjectKey`,
`PhysicalAttributeKey`, profiling/Analysis/assertion records, existing layer
sections, and `AgentModelDependency` from shared authoring/domain modules.
Each already distinguishes storage type and inferred type. Private original
snapshot/catalog used by full-graph validation must not appear in schemas or
projected values.

Reuse detailed models for validated prior-stage payloads:
`DetailedAnalysisCandidateFinderResult`, resolution/review models;
Conceptual contribution/consolidation/detail/package/refinement models;
Logical and Dimensional topology/contribution/detail/signal/validation models.
Do NOT reuse an entire output model for a compact input projection that omits
fields; define that small projected shape honestly.

Mapping already has typed `MappingRunContext`, `MappingPairIdentity`,
`MappingPhysicalObject`, `MappingSource`, `ExistingMappingHeader`,
`MappingReadiness`, output-template and dependency models. Reuse their schemas,
with deliberate smaller projection models if internal-only fields are excluded.

Missing boundary types worth introducing: compact model summary; evidence
fragment/page manifests; each compact Conceptual proposal/detail form; typed
work-item discriminated unions; metadata description-request union. Most are
currently JsonValue dictionaries. Code source_context and Validation
agent_context/source_context are also JsonValue; their inner dictionaries need
documented fixed schemas from actual repository builders, not fake test shapes.
`CodeGenerationArtifactContext` includes private IDs/digests and is NOT itself
the provider payload schema. `ValidationSystemAuthoringContext` is likewise a
wrapper, not the exact provider dictionary.

## Small implementation/checkpoint sequence

1. Shared fixed catalog/DTO plus one small family (Metadata description requests)
   proves runtime projection, API help, synthetic example/schema validation and
   old custom-template compatibility. Keep the evidence request shape unchanged.
2. Analysis + Conceptual stage variants: full versus fragments, explicit coverage,
   honest input-output objectives. Promote missing Conceptual refinement test.
3. Logical + Dimensional, including all three direct byte-fit render users where
   applicable; keep their different reconciliation/validator contracts visible.
4. Mapping + Code + Validation, including real repository-built contexts and
   output-template/guide delivery exactly once. Then frontend variable dictionary.

For every family, update default prose only after its projected input contract
is tested. Install SQL04+05 in disposable DB and resolve actual seeded plans;
inject those frozen stages into the existing synthetic service fixtures and
run the real StageRunner, rather than merely rendering in a side probe as this
census does. Assert expected stage coverage and no missing/unknown variables.
Capture only schemas/counts in failures; never stringify the frozen plans or
rendered Prompt objects.

Permanent tests should cover every documented example and advertised optional
variable (a custom test template actually uses it); complete, empty, unavailable,
fragmented and tool-retrieved evidence; byte bounds without duplicate guide or
whole-context text; applied records outside current selected subset; lock and
dependency preservation; current inner versus outer repair feedback; exact
partition/receipt coverage; previous published versions remain byte-identical.
For Code/Validation, first replace scope-only fake documentation assumptions
with contexts from actual `PostgresCodeGenerationContextRepository` and
`PostgresValidationContextRepository` builders using synthetic returned rows.
Their existing context tests supply a reusable narrow seam.

Fresh seed changes do not update an already-published assigned version. Existing
deployments therefore need a documented authorized publish/reassign step using
the existing governed Prompt API. No silent backfill, migration, or mutation of
published Prompt versions is included in this design.
