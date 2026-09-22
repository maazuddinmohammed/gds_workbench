# Agent prompt / variable audit

Source audit and focused fixes, 2026-09-21. Reviewed workflows sequentially: Analysis,
Conceptual, Logical, Dimensional, Mapping, Code Generation, Validation, Metadata
Enrichment. Initial audit was read-only; verification subsequently used only
fixture-created disposable PostgreSQL containers. No provider, Azure, Databricks,
or existing database calls. No stored customer templates inspected. No rendered
prompts included here.

## Implemented and verified

All six confirmed fixes below are implemented, one at a time:

1. Object Enrichment requests clear `selected_attribute_names`; Attribute requests
   replace it with exact writable names. Both retain sibling evidence. Executor
   regression verifies each request against its dynamic description output schema.
2. Enrichment contract examples use one Object. Attribute examples show a writable
   subset and contextual sibling; Object examples have no Attribute write targets.
   Seed-04 examples are synchronized.
3. Shared assertion description now says applicable to this workflow; all eight
   seed-04 registrations agree. Applicability filtering is unchanged.
4. Dimensional Attribute reader prose describes owning Entity selection, in the
   tool proposal, default export, and seed 05.
5. Mapping one-shot omits reader-only paging instructions; tool-assisted retains
   them. Default export and seed 05 agree.
6. Implemented default/contract exports no longer claim implementation is deferred
   or merely authorized. Synthetic examples remain explicitly synthetic.

Additional requested fix: a failed enrichment Object unit now emits a warning
with the safe public error code/reason, progress counts, and unavailable-field
count. Successful later units continue. Failed units no longer emit a false
completion event. Regression covers first-unit context exhaustion, later success,
partial applied/unavailable results, and final warning count.

Verification: 78 prompt-input/static tests passed; 16 disposable database seed /
enrichment tests passed. New `test_default_prompt_contracts.py` renders all 14
defaults against canonical typed examples and checks example JSON Schemas,
seed/export equality without logging text, tool inventories, and metadata target
semantics. Focused Ruff and Pyright checks pass. This validates contracts and
rendering, not model-generated semantic quality. Output candidate behavior remains
covered by existing workflow validators; no execution mode was added.

Essential evidence means evidence needed to achieve the default's intended
quality, not mandatory inclusion imposed on custom templates:

| Workflow | Why the default includes its evidence |
|---|---|
| Analysis | Physical scope/endpoints + source identity + metadata/Profile/assertion meaning + existing edges/locks establish supported new relationships. |
| Conceptual | Analysis evidence + current business definitions/supports prevent table-copy models and duplicate concepts; compact directories are alternative navigation. |
| Logical | Physical/Assertion evidence + upstream Conceptual/current Logical meaning establish grain/determinants; naming and audit settings reserve policy-owned fields. |
| Dimensional | Actual Silver evidence + Logical bindings/meaning + current Dimensional design establish analytic grain; naming/audit/technical settings preserve backend ownership. |
| Mapping | Route/operation/readiness define exact actionable coverage; bindings, source evidence, policy and selected document templates make transformations implementable. |
| Code Generation | Handle/guide + actual metadata/System assignments + applied Object/Attribute transformations support complete target SQL and exact assignment coverage. |
| Validation | Handle/scope + Mapping + optional current Code + existing complete Group/Check ledger support independent checks without unintended omission retirements. |
| Metadata Enrichment | Source business context + actual single Object/sibling evidence + documented ingestion links support descriptions; write selection differs by Object versus Attribute task. |

The original findings below retain rationale and remaining application/evidence
limitations; the six confirmed fixes are resolved as described above.

### Unlimited context follow-up

Independent review added `test_unlimited_agent_context.py`: 14 passing synthetic
cases verify complete >1 MiB Object/Attribute descriptions in both delivery modes,
whole-record reader paging, repeatable cursors, rejected cross-reader/run cursors,
no cumulative byte wrapper, and deep/high-node-count ordinary provider JSON.
Forbidden fields still fail without disclosing their values. Explicit
`reject_sensitive_values=True` filtering remains effective. Bounded Assertion
validation and the shared MCP record contracts retain their existing byte,
string, depth, and node restrictions.

No new correctness regression found in the reviewed unlimited loader/readers.
Scope/revision fences and cursor checks remain. The shared provider projection's
sensitive-value scan is opt-in as before; this change does not expand it. Persisted
Model policy templates still have an independent 256 KiB domain contract.
Large evidence also increases memory/serialization work because full frozen
datasets, projections, and reader values coexist; no new streaming architecture
was introduced or claimed.

Default prompt/seed-05/tool prose now describes record-count cursor paging with
whole Object groups and no default application response/cumulative byte ceiling.
Configured execution turns and provider context/output limits remain explicit.
Actual output-contract counts/bytes remain documented where their validators
still enforce them. Existing synthetic partial-group examples are labeled as
explicitly bounded compatibility examples. Stored custom templates remain untouched.

## Sources and ownership

- Reviewed default text: `docs/workflow-prompts/{workflow}.{mode}.json`
  (`code` filename corresponds to `code_generation`).
- Installable defaults: `database/seed/05_global_prompt_defaults.template.sql`,
  `$workflow_defaults$`. All 14 system/instruction pairs exactly match exports.
- Variable registration: `database/seed/04_application_reference.sql`.
- Typed upstream variable contracts: `features/workflows/authoring/context_contracts.py`
  (`WORKFLOW_INPUTS`, `INPUT_SHAPES`, `INPUT_EXAMPLES`). Values:
  `context_inputs.py:project_context_inputs`.
- Typed downstream contracts: `features/workflows/authoring/downstream_contracts.py`
  (`CONTRACTS`). Values/readers: `downstream_inputs.py`.
- Discovery/compatibility: `features/workflows/authoring/prompt_inputs.py`.
  Tool inventory/filter semantics: `context_readers.py`, `tool_configuration.py`.
- Runtime selects frozen persisted versions through `authoring/plan.py`;
  `stage_runner.py` projects variables and calls `prompt_rendering.py:render_prompt`.
  Runtime JSON output constraints come from each feature's candidate validator,
  plus `agent_execution.py:AGENT_OUTPUT_CONTRACT_INSTRUCTION`; defaults do not own
  the authoritative schema.

Paths starting `features/` above are relative to
`web_app/backend/gds_workbench_api/`.

Repository edits affect proposed defaults. Existing published global versions,
Tenant-owned templates, Model defaults, run overrides, and frozen runs do not
automatically change. Do not overwrite custom templates or require default
variable selections. The governed seed publishes a new global default version
when explicitly run; it is not a migration or permission to write a database.

## Supported mode inventory

| Workflow | One-shot | Tool-assisted | Stage |
|---|---|---|---|
| Analysis | Yes | Yes, 6 default readers | relationship_inference |
| Conceptual | Yes | Yes, 10 default readers | candidate_authoring |
| Logical | Yes | Yes, 18 default readers | candidate_authoring |
| Dimensional | Yes | Yes, 21 default readers | candidate_authoring |
| Mapping | Yes | Yes, 3 default readers | mapping_authoring |
| Code Generation | No separate stage | Yes, 5 readers; database mode null | sql_generation |
| Validation | No separate stage | Yes, 4 readers; database mode null | validation_generation |
| Object Enrichment | Yes | No | candidate_authoring |
| Attribute Enrichment | Yes | No | candidate_authoring |

Code/Validation services explicitly convert their null database mode to
tool-assisted execution. Missing opposite modes are unsupported capabilities,
not missing prompt exports.

## Sequential findings

### 1. Analysis

Default variables are all relevant: `source_context`, `gds_context`,
`object_context`, `object_attribute_context`, `ingestion_mapping`,
`object_relationship_context`, `modeling_assertions`. One-shot embeds all seven;
tool-assisted embeds ingestion links and reads the rest. No duplicate inline
evidence bundle is needed.

Strong existing instructions: actual physical keys versus originating Source,
Profile denominators/time/batch scope, composite identity, high-confidence gate,
directional-view deduplication, immutable locks, changed-only output, abstention,
and repair. Output `relationships` matches candidate ownership. No material
workflow-specific prompt defect found.

### 2. Conceptual

Adds current `conceptual_objects` and `conceptual_relationships`; compact
`conceptual_object_list` / `conceptual_relationship_list` are optional discovery
alternatives. Defaults correctly avoid embedding both full and compact forms.
Keep both advertised options: compact keys do not replace definitions or locks.

Strong instructions: business grain rather than table copying, meaningful
supports, distinct concepts, association versus cardinality confidence, unknown
cardinality, nondeleting merge, and locked nested supports. Output `objects` /
`relationships` correctly differs from variable names.

**Fix shared variable description:** `context_contracts.py:412`,
`INPUT_SHAPES['modeling_assertions'].description`, says Analysis-applicable.
Conceptual, Logical, and Dimensional reuse it, and seed 04 repeats the error.
`context_inputs.py` actually filters by the current workflow. Use workflow-neutral
wording or workflow-specific descriptions; retain filtering. Update prompt-input
catalog tests and seed/export description fixtures.

### 3. Logical

Relevant variables: Analysis evidence, upstream Conceptual records, current
Logical submodels/entities/attributes/relationships, `naming_instructions`,
`audit_columns`; compact directories remain optional. Defaults embed full
records only in one-shot and settings/ingestion only in tool-assisted.

Strong instructions: normalization, determinants, source identity namespace,
composite-key limits, no speculative fields, precise typed sources, strict
relationship cardinality, backend-owned audit projection, and supported empty
output. No extra Conceptual/Analysis source variants should be invented.

Fix the shared assertion description above. No additional material Logical
prompt defect found.

### 4. Dimensional

The 24 available variables are relevant to Silver/Logical meaning, current Gold
design, and policy. Absence of Bronze `source_context`, ingestion links, and
Analysis edges is deliberate; `logical_bindings` connects actual Silver keys to
Logical names. Default full and compact variables are not redundantly embedded.

Strong instructions: fact grain, additivity, temporal lookups, conformed identity,
bridge evidence, optionality, actual Silver supports, and technical/audit field
ownership. Output matches existing four-array contract.

**Fix reader prose:** `dimensional.tool_assisted.json.system_prompt`, readers
`list_logical_attributes` and `list_dimensional_attributes`, incorrectly describe
relationship endpoint matching. Same text exists in
`dimensional.tools.proposal.json`. Attributes are selected by their owning Entity
names; endpoint matching applies only to relationship lists. Update both exports
and seed 05. Test selector behavior in `test_dimensional_prompt_inputs.py`.

**Existing application restriction, not a prompt bug:**
`features/dimensional/candidate.py:_DimensionalCandidate.validate_size` requires
1–20,000 records. The default consequently explains an unchanged-record workaround
or intentional validation failure for abstention. If empty/no-op results should
work like Logical, change the validator and no-op behavior first, then simplify
both mode prompts; do not merely promise empty success in text.

### 5. Mapping

All ten variables have distinct uses: route, operation, target, source evidence,
existing binding/mapping, authoring policy, readiness, source System, and Object /
Attribute output templates. `operation` also appears in `readiness`; harmless
small overlap, useful as a standalone author choice. Do not delete availability.

Strong instructions: readiness-driven exact coverage, modeled versus physical
Attribute names, preserve/lock actions, Object relational steps versus field
expressions, concrete joins/grain/null semantics, and fixed outer schema.

**Remove irrelevant instructions:** `mapping.one_shot.json.system_prompt` includes
the full TOOLS AND BOUNDS reader/pagination section despite explicitly having no
tools. Remove reader-specific directions in one-shot only. Retain evidence limits,
no fabrication, correction, and output rules. Sync seed 05 and static default
prompt tests. Tool-assisted version still needs paging instructions.

### 6. Code Generation

Seven variables are useful: target/source metadata, source Systems, Object and
Attribute transformations, `target_ref`, `sql_generation_guide`. Default embeds
only the handle and guide; five readers retrieve evidence. Source-System
assignments and repeated modeled names are linkage, not accidental duplicates.

Strong instructions: Mapping preservation, staged temporary views, explicit final
projection, same-batch prerequisites, one assignment per System, independent
artifacts, no execution/load, and fixed SQL-only envelope. Opaque handles correctly
serve output reconciliation, not SQL identity. No material prompt defect found.

### 7. Validation

Six relevant variables: `system_ref`, `system_scope`, `mapping_evidence`, optional
`current_code`, `applied_groups`, `applied_checks`. Default embeds the first two
and reads the other four. Mapping and Code overlap is intentional: authored intent
versus its implementation.

Strong instructions: independent expected results, comparable populations,
standalone Query A/B prerequisites, scalar result shape, typed comparisons,
optional Code, and no fabricated execution outcomes. The default correctly warns
that omission retires unlocked active definitions: this is a complete desired
ledger, unlike nondeleting upstream candidates.

Preserve that warning when simplifying. Partial custom inputs must not be described
as a complete existing ledger. Empty Group output remains an application restriction;
do not solve it by asking the model for a dummy check.

### 8. Metadata Enrichment

Five relevant variables shared by both workflows: source context, GDS context,
single Object context, sibling Attribute/Profile context, Object ingestion links.
Object and Attribute tasks are separate. Backend owns inferred types; AI writes
only descriptions, with null accepted for unsupported meaning. Dynamic
`DescriptionValidator.output_schema` supplies exact natural-key-string keys.

**Confirmed payload/prompt mismatch:** Object default says
`object_attribute_context[*].selected_attribute_names` is empty.
`database/14_application_workflow_execution.sql:2704` populates active Attribute
names. `features/metadata_enrichment/service.py` copies that context into the
Object unit without clearing them; only Attribute units overwrite the selection.
Clear names on the Object unit copy while retaining all sibling evidence. Add an
assertion to `test_database_metadata_enrichment_executor.py` distinguishing Object
versus Attribute calls; existing `test_database_metadata_prompt_inputs.py` checks
the shared raw SQL context and should keep its active-name expectation.

**Fix examples:** `context_contracts.py:4942-4954` reuses Analysis examples for
both Enrichment workflows: two Objects and nonempty Attribute selections.
Provide one-Object examples; Object selection empty, Attribute selection a
nonempty writable subset. Keep siblings as context. Update seed-04 examples and
metadata prompt-input schema tests. This is documentation, not a schema expansion.

**Evidence limitation to record, not silently expand:** registered Source
Attribute descriptions exist in internal enrichment evidence, but the five
advertised variables expose only target Attributes and Object-level ingestion
links. Attribute defaults cannot see a renamed Source Attribute's description
through an exact Attribute mapping. They correctly prohibit guessing those
mappings. If direct source-description propagation is intended, it needs a
deliberate natural-key Attribute-lineage contract change, not stronger prompting
or a hidden extra payload. Existing backend type inference remains independent.

## Cross-cutting maintenance / verification

- Several exported defaults retain `status=approved_design; implementation_deferred`
  although seeded and implemented. Update status metadata without changing runtime
  contracts.
- Keep optional variables/readers optional. Remove redundant selected evidence
  from defaults; do not remove capabilities merely because one default omits them.
- Static regression verifies 14/14 default system/instruction pairs match the SQL
  seed and render canonical examples; disposable seed/executor checks also passed.
- Relevant checks: `test_analysis_prompt_inputs.py`,
  `test_conceptual_prompt_inputs.py`, `test_logical_prompt_inputs.py`,
  `test_dimensional_prompt_inputs.py`, `test_mapping_prompt_inputs.py`,
  `test_downstream_prompt_inputs.py`, `test_metadata_prompt_inputs.py`,
  `test_prompt_rendering.py`; seed parity in
  `tests/mcp/test_database_global_prompt_seed.py` (disposable fixture only).
- Make one coherent change at a time. None of these findings authorizes replacing
  persisted custom prompts or running seeds against an existing database.

## Mapping selected-template regression fixed

`downstream_contracts.py` nested `$defs` inside each optional template's `anyOf`
branch while field/example `$ref` paths addressed the schema root. Non-null
installed templates therefore failed validation before the provider ran. Hoisted
both definition sets to the root without changing allowed fields. Canonical
Object/Attribute examples now contain actual seed-07 nested field guidance;
`mapping.context.json` and fresh-install seed-04 examples match. Stored custom
prompt text is untouched.

`test_default_prompt_contracts.py` additionally builds actual Mapping preparation
with both seeded templates, projects and renders both execution modes, verifies
nullable selection remains valid, and rejects malformed nested field metadata.
22 focused default/Mapping tests passed; full backend Pyright and focused Ruff
passed. This closes the prior coverage gap where null examples never exercised
nested references. The disposable end-to-end pipeline is owned by the provider
review agent.
