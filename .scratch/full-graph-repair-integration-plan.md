# Full Model validation inside authoring repair

Read-only source audit, 2026-09-05. No production changes in this slice. Root is
sequencing materializer order, native structured output, then canonical history
echo fixes before this work.

## Implemented checkpoint

Conceptual now runs frozen full-graph validation inside one-shot/tool-assisted
repair and after each complete detailed reconciliation pass. Native detailed
coverage/evidence pages remain fixed; only reconciliation repeats, with bounded
feedback included in both stage context and prompt resolver values. A later
malformed response cannot replace the last complete rejected draft retained for
governed review. Fourteen new regressions cover new/applied Relationships,
multi-page repair/exhaustion and prompts without the feedback placeholder.
Owned backend gate: 130 passed; Python 3.12 source/notebook execution: 53 passed.
Root separately verified real database repaired-draft Apply and rejected retention.

Analysis remains unchanged: with a valid frozen baseline, production eligibility
and its local endpoint/field-ownership checks did not expose a candidate-caused
whole-graph defect. Do not add a native Analysis rerun based on an impossible
selected-but-ineligible fixture. Its final handoff still validates the full graph.
The remaining sections below record the original broader investigation, not a
claim that every proposed integration was implemented.

## Existing mechanism to reuse

`workflows/authoring/stage_runner.py::AgentStageRunner.run` already accepts
`final_validation`. `repair.py::ValidationRepairRunner.run` invokes it only after
the stage output schema and candidate validator pass, feeds safe issues into the
bounded next attempt, and attaches a complete rejected candidate on exhaustion.
It does not retry authorization/revision/finalization failures. Keep this behavior.

Only `logical/service.py` currently wires the complete graph callback:
`execute_started` lines451–469 projects audit columns, checks `validate_future_graph`,
and passes the callback to both one-shot/tool-assisted and detailed paths. Detailed
reconciliation lines935–1095 retains native partitions, materializes the complete
candidate, validates it, and reruns those partitions with bounded diagnostics.
Exhaustion recovery lines570 onward retains a complete projected rejected draft.
The final handoff still validates again inside its current transaction.

All six remaining families call final handoff after their stage repair ends. A
schema-valid candidate can therefore encounter its first full Model graph failure
too late for another authoring attempt. Existing failed-draft retention improves
inspection but does not repair that output.

## Required validation context

- Shared `workflows/authoring/context.py::PostgresAgentContextRepository.load`
  already loads a full snapshot for Analysis/Conceptual/Logical/Dimensional, but
  loads `physical_scope` only for Logical (around line599). Load the same catalog
  for the three other shared-context workflows, inside that immutable fenced
  context read. Keep both values server-only in `AgentContextBundle`.
- `logical_model_dependencies` (line884) exposes bounded reference records without
  Mapping documents/Code bodies, only for Logical. Dimensional authoring needs its
  own equivalent layer-filtered Binding/dependency evidence; a diagnostic saying
  “Binding coverage missing” is insufficient if the author cannot see required
  bound names. Reuse the existing projection with an explicit modeled-layer
  argument, preserving every dependency and existing context/tool byte limits.
- Mapping uses `readiness.py::MappingReadinessService.prepare`, a separate
  repeatable-read preparation. `MappingPreparation` has no snapshot/catalog.
  Load and retain them there alongside the plan/readiness context, server-only.
- Code and Validation contexts also lack a full snapshot/catalog. Load both with
  their existing authorized repeatable-read plan/context transaction in their
  executor or repository; preserve the frozen Model revision. Do not issue a new
  database read for every model response, serialize the snapshot into agent input,
  or silently use an empty catalog in production. Update protocol/fake fixtures
  to match the real validation context.

Construct exactly the changes that final handoff will stage, including policy
projection, reconciliation and lifecycle retirement of prior outputs. Validate
existing Model Change Set record/section-byte bounds as well as the future graph.
Candidate-dependent projection/bounds errors must become safe bounded candidate
issues; do not accidentally bypass repair by throwing an uncaught Pydantic error
while constructing `StageModelChange`. Keep infrastructure, authorization and
revision failures outside paid retries.

## Family integration points

| Family | One-shot/tool-assisted callback | Detailed repair boundary |
| --- | --- | --- |
| Analysis | `analysis/service.py::execute_started`, `relationship_inference` call around line421: parse normalized changes, then full graph. No policy projection. | `_execute_detailed` lines786–990: keep finder/resolver coverage; wrap native whole-slice reconciliation batches, their merged candidate, graph validation and reviewer in a bounded outer pass. Feed diagnostics to the reconciler, not the review-only response schema. Reviewer blockers currently abort at line953; route their bounded findings back to reconciliation too. |
| Conceptual | `conceptual/service.py::execute_started`, `candidate_authoring` around line424: parse changes, then full graph. | `_execute_detailed` lines922–1037: wrap existing reconciliation contexts/partitions plus merged candidate validation in an outer pass. Keep contributions/consolidation/details/refinements stable. Whole-model reconciliation can author Object/Relationship records and is the appropriate repair stage. |
| Dimensional | `dimensional/service.py::execute_started`, `candidate_authoring` around line474: call `_project_dimensional_changes` (line2272) before graph validation; this includes technical/audit and foreign-key projection. | Existing reconciliation retry loop around line893 handles relationship receipts only. Add the graph gate after complete materialization/projection (lines987–1004), but Entity/Attribute repairs need a native authoring rerun; see the specific limitation below. |
| Mapping | `mapping/service.py::execute_started`, `mapping_authoring` around line350: `CompleteMappingCandidateValidator.parse_validated(value).changes`, then full graph/bounds. | `_run_detailed` lines479–692: assemble all header/Attribute partitions, run native `target_validator` review partitions, then validate the complete Mapping. Repeat a bounded review pass with latest partition bodies and diagnostics. Rebuild existing adaptive partitions with the same request/result limits and exact actionable-Attribute coverage. Do not run the full candidate against a one-partition schema. |

Analysis `_detailed_resolver_values` around line1661 and Conceptual's equivalent
around line1093 currently insert empty validation failures. Give these helpers
the actual bounded feedback for the retry stage; include feedback in its context
and request-byte calculation, because custom frozen prompts may omit that
placeholder. Count attempts monotonically and retain one warning/progress trail.
Do not erase original evidence to squeeze in a full previous candidate: reuse
the existing bounded repair diagnostics/omitted-candidate-digest convention.

### Dimensional: receipt retry cannot change base records

`dimensional/detailed.py::DetailedDimensionalReconciliationReceipt` (line262) has
only partition ref, draft manifest, reviewed relationship refs and relationships.
`materialize_dimensional_reviewed_candidate` (line1499) copies Submodels from
topology and Entities/Attributes from entity-detail outputs. The workers and lead
also only return findings. Repeating the current receipt loop cannot correct a
bad Entity status or an extra Attribute that violates an existing Binding.

Smallest correct fallback: bounded outer detailed-authoring pass, preserving the
native topology/detail/reconciliation/worker/lead schemas and partition helpers.
Feed the safe graph failures into stages able to change the affected record,
rebuild the relationship ledger and manifest whenever base details change, and
invalidate downstream receipts. Relationship-only repairs may retain the existing
inner reconciliation path. A pass counter shared across graph/worker repair must
respect the frozen retry count; do not add an unbounded second loop or claim that
receipt retries repair immutable Entity/Attribute content. No projected technical
columns become agent-authored.

## Code and Validation: complete selected-set boundary

These workflows use fixed common execution plans, not the three selectable modes.
Code `service.py` lines361–417 runs `sql_generation` once per selected target;
Validation lines344–383 runs `validation_generation` per selected System. Each
stage already has schema/candidate repair, but the full change set exists only
after all units return.

`code_generation/service.py::_generated_code_changes` (line559) requires exact
target coverage, and reconciles/deactivates old artifacts AND source assignments.
`validation/candidate.py::reconcile_validation_candidates` (line369) requires exact
System coverage, and reconciles/deactivates prior Groups AND Checks. Calling
either with only the latest response and every frozen context fails coverage;
using a partial accumulated prefix as a complete Run result is also incorrect.

Smallest robust repair boundary: retain the per-target/System stage loops inside
a bounded complete-pass loop. After all units return, build the real aggregate
changes and run graph/bounds validation. On failure rerun the same native unit
stages with bounded feedback and each unit's own prior candidate; preserve all
frozen identities/guide/context, never send the whole aggregate through the last
unit's schema. Keep the last complete rejected aggregate for governed retention
if repair exhausts; do not replace it with an incomplete later response. A later
optimization can retry only proven affected units, but should not add a dependency
router before correctness is demonstrated.

A possible smaller callback for per-unit checks is an accepted-prefix + current
response with matching prefix contexts; unprocessed units remain applied in the
snapshot. This can detect failures early but does not by itself supply complete
Run retention or prove final aggregate bounds. Prefer the complete-pass boundary
for the first reliable implementation. Both code and Validation can exceed
aggregate limits despite each local candidate fitting: Code batch allows 50,000
artifacts while Stage records cap at 20,000; Validation permits 10,000 Checks/System
while pending Model changes cap at 50,000. Keep exact global bounds and give
actionable shortening feedback inside the bounded repair path.

## Gates before calling a family fixed

Use the real canonical graph fixture, not only a handoff fake that invents an
exception. A first locally-valid/full-graph-invalid candidate must get one native
repair attempt, then stage a corrected graph. Assert original context/selection,
stage schema, exact partition coverage, authority/locks and input/result-byte
limits on every attempt. Include no-change, immutable history, policy projection,
exhaustion retaining only a complete candidate, rejected-draft replay, and no paid
retry for stale revision/auth/claim/finalization errors.

Detailed tests must span multiple partitions. Include a Dimensional base-record
failure that cannot be repaired by a relationship receipt, and Mapping header plus
multiple Attribute partitions. Code/Validation need at least two units, aggregate
coverage/retirement checks, aggregate bounds and last-complete-candidate retention.
Existing `tests/web_backend/test_logical_executor.py` full-graph and detailed
partition tests (around 1152,1300,1422) provide the tested pattern. Run each family's
candidate/executor/detailed/context tests, then real handoff DB checks; preserve
shared notebook execution parity. No new MCP endpoint or provider call is needed.
