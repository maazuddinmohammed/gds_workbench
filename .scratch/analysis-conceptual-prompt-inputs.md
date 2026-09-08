# Analysis and Conceptual named Prompt inputs

Read-only follow-up after the Model review Tenant-fence gate. This supplements
`prompt-normalization-audit.md`; no production changes or stored request content.
Reviewed actual stage builders and validators, including current Conceptual
whole-graph repair and the new Metadata `PromptInputContract` foundation.

## Smallest extension of the Metadata contract

Keep its explicit `(workflow, mode, stage, resolver_key)` registry and projection.
Use existing canonical record models for value schemas. Add compact assignment
values separately from evidence collections; default templates inline assignment
references only and point to the existing structured evidence or bounded tools.
Preserve legacy `stage_context` and resolver values exactly. Do not treat dotted
names as arbitrary selectors or fetch additional evidence during rendering.

For the tables below, each proposed name is a separate registered variable, not
one new all-purpose context document. `C` means already delivered in
`context.original_context`; `I` means a small inline projection; `T` means a typed
retrievable dataset, not a claim that its records are inline. Large C collections
should remain structured by default. Do not duplicate them in template text.
A missing collection on a compact/fragment page is **unavailable**, not empty.
Where two existing shapes deliver different information, document a precise union
or nullable availability; never pretend compact records satisfy the full schema.

A shared descriptor may document existing delivery, but a new variable must only
be registered when runtime can supply its promised shape for that exact stage.

## Common source and schema facts

`workflows/authoring/context.py` owns the immutable `AgentAuthoringContext`:

- `selected_objects`: `SelectedObjectContext[]` containing selection order,
  `ObjectRecord` and `AttributeRecord[]`.
- `profiles`: `ProfilingProfileRecord[]`.
- `analysis_relationships`: `AnalysisResultRecord[]`; these are existing applied
  Analysis evidence, not the new candidate currently being authored.
- `assertion`: `AssertionSection {documents, records}`.
- `applied.conceptual`: `ConceptualSection | null`.
- `model_details`: `ModelDetailsRecord`; provider one-shot context excludes
  internal Run/Model IDs. Conceptual detailed model context currently includes
  Model ID and existing business-model guidance; do not copy this difference into
  an invented generic identity schema.

One-shot supplies these records inline. Tool-assisted supplies `_context_manifest`
(or its compact variant), and two local tools. Dataset names are fixed:
`model_details`, `selected_object`, `selected_attribute`, `profiling_profile`,
`analysis_result`, `modeling_assertion_document`, `modeling_assertion_record`, plus
`conceptual_object`/`conceptual_relationship` when applicable. Selected Object
and Attribute tool records are flattened and include `selection_order`; they do
not use the one-shot nested `SelectedObjectContext` shape.

Tool counts distinguish retrieval items from source records. Pages can stop
before requested limit; continue at returned `next_offset`. Tool fragments use
zero-based indices and SHA-256 verification. Detailed Analysis/Conceptual fragments
use **one-based** indices; do not reuse the tool fragment schema or instructions.
Detailed fragments have no retrieval tool and can span independent stage calls.
An incomplete local fragment set cannot be described as a complete source record.

## Analysis stage contracts

| Stage | Proposed compact assignment / evidence names | Actual source, schema and availability |
|---|---|---|
| one-shot `relationship_inference` | I `model_brief`; C `selected_metadata`, `profile_evidence`, `applied_relationships`, `modeling_assertions` | Project model name/revision/description and the canonical collections above from the one-shot context. All collections exist; empty means no evidence collected in this frozen context. No source sample collection occurs here. |
| tool-assisted `relationship_inference` | I `model_identity`, `evidence_datasets`; T selected metadata, profiles, applied Analysis and Assertions | Project identity from manifest fields. `evidence_datasets` is a fixed array of dataset name, source-record count, retrieval-item count and fragmented-record count. Full item schemas belong in descriptor help. Dataset records remain behind `get_agent_context_dataset`; do not return the full collections as replacement variables. Manifest compact mode omits selected-object overview entirely. |
| detailed `candidate_finder` | I `slice_assignment`; C `selected_metadata`, `profile_evidence`, `applied_relationships`, `modeling_assertions`, `evidence_fragments` | `_candidate_finder_slices` / `_candidate_evidence_pages`, `analysis/service.py:1055–1296`. Small form has full selected records, profiles, Assertions and `{applied_record_ref, relationship}`. Large form has selected physical identities plus `evidence_manifest`, `evidence_fragments` and `page`. Full metadata/profile/assertion variables must be unavailable on that form unless a complete local fragment set is reconstructed safely. Slice assignment needs the actual left/right identity sets and candidate bound; see verified gap below. |
| detailed `relationship_resolver` | I `assigned_candidate_refs`; C `endpoint_candidates`, `prior_evidence_availability` | `_resolver_batch_context:1390`. Candidates are `DetailedAnalysisEndpointCandidate[]` under `candidate_finder_result.candidates`; each has two exact physical keys and 1–20 typed evidence signals. Remaining inputs are a source-evidence digest/count manifest, an applied-Analysis manifest and `applied_analysis_deferred_to_reconciliation`. No source profiles/Assertions/full prior relationships are delivered here. |
| detailed `whole_slice_reconciler` | I `assigned_candidate_refs`, `assigned_applied_refs`; C `resolution_work_items`, `work_manifest` | `_reconciliation_batches:1477`. Each work item is a resolution fragment or applied-Analysis fragment with `review_ref`, typed endpoint/status summary, fragment fields and JSON text. Assigned refs are the page's **fragment review refs**, not original candidate IDs or every global manifest record. Manifest contains counts/digest only. |
| detailed `analysis_reviewer` | I `assigned_relationship_refs`, `assigned_applied_refs`; C `review_work_items`, `work_manifest` | `_review_batches:1574`. Discriminated relationship/applied fragment items with `review_ref` and relationship summary. Summary includes endpoint keys, kind/confidence, basis digest/byte count, optional prior status/lock; it does not expose the full basis text. |

Analysis output schemas already exist in `analysis/detailed.py` and must remain
authoritative: finder coverage plus unique slice-prefixed candidates; resolver
one decision per assigned candidate (`relationship`, `no_relationship`,
`needs_review`); reconciliation candidate/applied coverage plus relationships;
reviewer exact reviewed refs plus bounded findings. One-shot output is the
existing `AnalysisInferenceCandidateValidator` schema, including legitimate empty
relationship output.

Default instruction priorities, in execution order:

1. Find plausible endpoint pairs from exact selected physical identities. Prefer
   supported type/key/profile/assertion evidence; name similarity alone is weak.
   Use `attribute_inferred_data_type` when present as available type evidence;
   preserve the registered storage type separately.
2. Finder reports candidates only within its assigned pair boundary, without
   inventing direction. Resolver decides every assigned candidate once, using
   its actual signals; a manifest is not proof of a relationship. Use
   `needs_review` when evidence is insufficient.
3. Reconciler resolves duplicate/conflicting proposals and accounts for every
   assigned review ref. Preserve applied evidence and locked content through the
   canonical merge rules. Do not invent missing fragment text.
4. Reviewer audits its assigned rows only and returns findings, not replacement
   relationships. Emit a blocker only for a supported contradiction; separate
   uncertainty from proven invalidity.

### Verified Analysis assignment gap

For a same-Object pair of different Attribute chunks, `_DetailedFinderSlice`
retains `left_attributes` and `right_attributes` for the validator, but delivered
`selected_objects[0].attributes` merges both chunks. Neither side membership nor
an equivalent permitted-pair constraint is in the context. A synthetic 20-Attribute
probe at an 8 KiB context bound reached disjoint chunks and verified this exact
loss without recording values. A named variable cannot recover that partition
from the merged list.

Smallest prerequisite for that stage: supply `slice_assignment` explicitly from
`finder_slice.left_attributes`, `right_attributes`, `slice_ref` and the actual
configured candidate bound at its call site. Keep the legacy context unchanged.
Do not infer sides from list order or replicate the chunker in prompt projection.
This is a concrete later stage change, not required for the Metadata slice.

## Conceptual stage contracts

All stages also receive effective `model.naming_instructions` through the current
resolver helper. Keep that actual Model policy separate from evidence; naming
instructions do not establish business facts or permission to change locks.

| Stage | Proposed compact assignment / evidence names | Actual source, schema and availability |
|---|---|---|
| one-shot `candidate_authoring` | I `model_brief`; C `selected_metadata`, `profile_evidence`, `analysis_evidence`, `modeling_assertions`, `applied_conceptual` | Canonical collections from `AgentAuthoringContext`, plus existing naming policy. Applied Conceptual may be null; use empty output collections only according to the existing candidate schema. |
| tool-assisted `candidate_authoring` | I `model_identity`, `evidence_datasets`; T the same evidence domains | Same manifest/tool contracts as Analysis, with typed Conceptual Object/Relationship datasets. No inline collection promise; compact manifest lacks selected Object overview. |
| detailed `object_contribution` | I `contribution_assignment`; C `source_metadata`, `profile_evidence`, `analysis_evidence`, `global_evidence`, `evidence_fragments` | `_object_contribution_contexts:1222` and `_object_contribution_context:1343`. Full form occurs only for a single selected Object that fits. Otherwise source is a `PhysicalObjectKey`, one-based fragments and `global_evidence_included`. Assertions/applied Conceptual are assigned only to the first selected Object's pages. Analysis evidence is owned by the lower selected-object order among its endpoints, avoiding duplicate delivery. Assignment includes exact contribution ref and source key. |
| detailed `entity_consolidation` | I `assigned_proposal_refs`; C `entity_proposals` | `_consolidation_contexts:1414`: either complete `DetailedObjectContribution[]` or `contribution_proposals` compact records. Normalize an explicitly compact proposal view in both branches if chosen: proposal/local ref, candidate name/definition/type/grain, limited aliases with total count, physical support sources, assertion-support count. It cannot claim complete support rationale or full definitions when truncated. |
| detailed `entity_attribute_detail` | I `entity_assignment`; C `entity_proposals`, `supporting_objects` | `_detail_contexts:1548`. Full form includes consolidated entity, full contributions and selected Objects. Compact form has canonical ref/preferred candidate name and compact proposals, each with Object metadata and Attribute count. Attributes themselves are not delivered on the compact form. Assignment/support coverage comes from this page's scoped proposals. Despite its code name, output is a Conceptual Object, not physical Attributes. |
| detailed `relationship_cardinality_refinement` | I `relationship_assignment`; C `endpoint_concepts`, `relationship_signals` | `_refinement_contexts:1708`. Always two compact Conceptual endpoint details; signals either nested in full package or separate partition list. Normalize by selecting the actual branch without changing evidence. Signal schema is `DetailedRelationshipSignal`: matching Attribute or Analysis relationship, exact endpoints, optional kind/confidence/validation result. Endpoints include truncated definitions/grain, limited aliases/supports with total counts. |
| detailed `whole_model_reconciliation` | I `assigned_entity_refs`, `assigned_input_refs`, `assigned_package_refs`, `assigned_applied_refs`; C `reconciliation_work_items`, `outer_repair_findings` | `_reconciliation_contexts:1830`. Full form has consolidation, entity details, packages/refinements, input coverage and applied Conceptual. Compact form uses discriminated entity/input/refinement/applied-fragment work items and four explicit required-ref arrays. Applied refs in the compact form are fragment review refs; full form refs identify records. Inner output coverage must match that form exactly. Outer repair appears as `reconciliation_repair` only on a later complete pass. |

Conceptual output models already provide the real contracts:
`DetailedObjectContribution`, `DetailedEntityConsolidation`, `DetailedEntityDetail`,
`DetailedRelationshipRefinement`, `DetailedReconciliationCandidate`. Reuse their
schemas, including the current provider normalization. Output key shapes,
coverage requirements and backend no-agent-lock rules are not template choices.

Default instruction priorities:

1. Contribution identifies important business concepts, definition and grain;
   multiple physical Objects may support one concept. Account for the exact
   assigned contribution as represented/context-only/excluded/blocked. A
   represented contribution requires proposals; other dispositions forbid them.
2. Consolidation partitions every supplied proposal ref exactly once between a
   canonical concept and discard; merge by business meaning/grain, not spelling
   alone. Candidate names must come from the actual member proposals.
3. Detail produces one complete Conceptual Object for its assigned entity with
   exact permitted support. Avoid physical column design, primary keys or a
   duplicate Logical schema. Consider changing the user-facing label to
   “Conceptual Entity Definition” later; preserve the frozen stage code.
4. Relationship refinement decides the exact package and its two endpoints;
   prefer business/assertion/validated Analysis evidence. Matching physical
   names alone do not justify cardinality. Null relationship is required for
   no-relationship/needs-review dispositions.
5. Reconciliation returns business concepts/relationships plus exact assigned
   coverage. Preserve compatible applied history and active dependencies; use
   `reconciliation_repair` to repair the complete candidate in its native stage.
   Do not assume global evidence absent merely because it was assigned elsewhere.

## Repair and schema boundaries

`StageRunner` renders once before `ValidationRepairRunner`. Inner repair feedback
is supplied under `context.repair` on subsequent model requests, not through a
variable re-render. In current Analysis, `_detailed_resolver_values` always gives
legacy `workflow.validation_failures=[]`; do not market it as current feedback.
Conceptual outer reconciliation separately passes bounded validation failures to
its resolver and `reconciliation_repair` to its context on a later pass. Preserve
this distinction in catalog help/default instructions.

Use fixed strict input models for actual page/fragment/manifests that lack models
now; reuse canonical output/evidence models where possible. Never label a digest
manifest as data, a truncated compact record as complete, or a detailed fragment
as a tool page. Avoid adding another generic workflow-wide schema to conceal
these meaningful differences.

## Bounded implementation sequence and checks

After Metadata's installed catalog/runtime/default-template gate, do Analysis
one-shot/tool-assisted together with matching descriptors, then its detailed
finder/resolver, then reconciliation/reviewer. Conceptual one-shot/tool-assisted
can follow the same established descriptors; its detailed stages each need
full/compact fixtures before replacing defaults. This is a sequence of actual
stage contracts, not a broad prompt-engine framework.

For each slice, load actual installed allowed-variable definitions and exercise
the real builder/StageRunner. Check documented schema against values for both
small and fragmented contexts, exact assignment refs, empty versus unavailable,
tool fragmentation/page counts, naming-policy provenance, native repair feedback,
legacy frozen/custom rendering, and unchanged context/request byte bounds.
Use synthetic metadata only; report counts/contract failures, not rendered prompts.
