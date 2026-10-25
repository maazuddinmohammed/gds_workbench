# Subject Area modeling: execution plan

Status: draft for review, 2026-10-25. Nothing implemented.

This plan hands the work to an implementation session. Read it fully, then start with
Phase 0. Companion material:

- Flow page (pictures of the whole idea): https://claude.ai/artifact/5zrRpve39bnhGHrbQ7Q3US
- DDL drafts and the AI output shape: `ddl/` next to this file. `ddl/README.md` explains
  the column rule.

## Brief for the implementation session

- Follow `AGENTS.md`. One phase per PR. Within a phase, one cohesive change at a time,
  each verified before the next. Do not deploy, push, or open PRs without the user's OK.
- The user knows Python and SQL and is new to web/MCP code. Explain in those terms.
- Every phase must leave a fresh install working: the numbered SQL sequence, seeds,
  `20_verify_install.sql`, the three test suites and the packaging checks.
- Change the DDL by editing the numbered install files. Never write migrations.
- Keep the Change Set, Snapshot and Stage contracts the same across web, MCP, the
  Atlas plugin and the VS Code extension. When a dataset changes, change all four in the
  same phase and regenerate `atlas/atlas-vs-code/test/fixtures/server-contract.json`
  with `tests/atlas/test_stage_contract.py --write`.
- Prompt changes go to seed 05 and its variable rows in seed 04 together, with the
  variable contracts in `features/workflows/authoring/context_contracts.py`.
- Before each phase, ask the user the questions listed under that phase. Do not reopen
  the decisions in the next section.

## Decisions already made (do not reopen)

1. There is one Logical model. A subject area is a focus window that keeps each AI call
   small. It is not a separate model. A table may belong to several areas.
2. The Conceptual section is replaced by subject areas: `workflow.subject_area` and
   `workflow.subject_area_table` (one row per area, one row per area/table).
   Concept relationships, concept types, grain, aliases and the ConceptID DDL download go.
3. Logical becomes three runs: Build (per selected areas), Optimize (whole model),
   Validate (deterministic, Databricks). Dimensional later gets the same three.
4. Build processes the selected areas one after another in one run. Each call sees the
   entities already built from its tables and reuses or updates them. One draft per run.
5. Every run returns only changes. Omission is not deletion; the AI retires records by
   listing them, it never deletes. Locked records never change. Nothing reaches the
   model until Apply.
6. Optimize reads the model (compact), the Analysis relationships, and full detail only
   for the entities it changes. It does not re-read the input scope.
7. Dimensional reuses the same subject areas; no separate grouping step.
8. Minimal fields: a column exists only if a later step reads it. The backend fills in
   everything it can work out: ids, surrogate keys, audit columns, column order,
   dependency order, the parent key of a relationship, lock flags.
9. Keep `logical_entity_grain` (Mapping and Dimensional read it; reviewers check it).
10. Type lists the backend does not branch on (Logical entity type, fact type) move to
    reference tables so a new value is one INSERT. Lists the backend branches on
    (fact/dimension/bridge, cardinality, check codes) stay as CHECK constraints.
11. Relationships are child → parent: from the foreign-key attribute to the parent
    entity. Many-to-many becomes an association entity.
12. The AI writes short table ids (`t1`, `t1.order_no`); the backend expands them to full
    physical keys before validation.
13. Defer cosmetic schema churn: `status` → `is_active`, dropping `support_source_type`,
    source order, `agent_run_id`, `created_by`, `updated_by`. Do them only when the
    phase rewrites that table anyway (see Phase 4 and 7).

## Target picture in one table

| Step | Run | Unit of one AI call | Reads | Writes |
|---|---|---|---|---|
| Subject areas | `subject_area` | whole scope, compact | tables, descriptions, table-level Analysis links, existing areas | areas + memberships → draft |
| Logical Build | `logical` / `build` | one subject area | area tables in full; entities already built from them; neighbours; directory; filtered Context | entity/attribute/relationship changes → one draft |
| Logical Optimize | `logical` / `optimize` | whole model, compact | model summary, unlinked Analysis edges, type/name conflicts, check results | changes + retirements → draft |
| Logical Validate | `logical` / `validate` | per entity/relationship | source tables on Databricks | `workflow.model_check_result`, saved directly |
| Dimensional Build/Optimize/Validate | `dimensional` / same three | one area / whole / per entity | Logical entities of the area, existing dims | same pattern on Gold tables |

## Run identity

Add to `application.workflow_run`:

```sql
workflow_operation VARCHAR(20)   -- 'build' | 'optimize' | 'validate'
-- required when project_workflow IN ('logical', 'dimensional'), NULL otherwise
-- 'validate'  => workflow_execution_mode IS NULL and no agent columns (like Analysis validation)
-- 'build' | 'optimize' => workflow_execution_mode IN ('one_shot', 'tool_assisted')
```

`project_workflow` values: replace `'conceptual'` with `'subject_area'`. Keep the others.
Every CHECK list in `13_application_workflow_runs.sql`, `14_application_workflow_execution.sql`,
`12_application_configuration.sql` (`workflow_stage`), the Python `ProjectWorkflow`
literals and the frontend types change together.

Workflow stages (`application.workflow_stage`, seed 04):

| project_workflow | mode | stage_code | agentic |
|---|---|---|---|
| subject_area | one_shot / tool_assisted | candidate_authoring | yes |
| subject_area | NULL | backend_validation | no |
| logical | one_shot / tool_assisted | build_authoring | yes |
| logical | one_shot / tool_assisted | optimize_authoring | yes |
| logical | NULL | policy_projection, backend_validation | no |
| logical | NULL | model_validation | no (Validate run) |
| dimensional | same shape as logical, later | | |

`application.snapshot_workflow_run_prompts` (13 file, line ~980) freezes every active
agentic stage for the run's workflow and mode; today it has no way to pick one of
several. Add: for logical/dimensional, only the stage whose code is
`workflow_operation || '_authoring'`. `features/workflows/authoring/plan.py` (lines
~100-112, `expected_stage_count`) mirrors that join and must apply the same filter.
`uq_workflow_stage_order` is per (workflow, mode), so `build_authoring` takes order 10 and
`optimize_authoring` order 20. The alternative, pseudo-workflows `logical_build` /
`logical_optimize` as Metadata Enrichment does, was rejected: it would multiply every
`project_workflow` CHECK list and frontend type. The seed-05 inventory check (`14` seeds
must equal the agentic stage count) changes with every stage added or removed; update
both. `20_verify_install.sql` pins 17 `application` tables; the new selection table makes
it 18.

Selected areas:

```sql
CREATE TABLE application.workflow_run_subject_area_selection (
    workflow_run_id  BIGINT NOT NULL,
    project_id       BIGINT NOT NULL,
    subject_area_id  BIGINT NOT NULL,
    selection_order  INTEGER NOT NULL,   -- processing order
    PRIMARY KEY (workflow_run_id, subject_area_id),
    FOREIGN KEY (workflow_run_id, project_id) REFERENCES application.workflow_run (workflow_run_id, project_id),
    FOREIGN KEY (subject_area_id, project_id) REFERENCES workflow.subject_area (subject_area_id, project_id),
    UNIQUE (workflow_run_id, selection_order)
);
```

`create_workflow_run` also fills today's `workflow_run_object_selection` with the distinct
union of the selected areas' active tables, so the selection digest, count, coverage and
`_SELECTED_OBJECTS_SQL` keep working unchanged. Area → table grouping is read at execution
time from `workflow.subject_area_table` at the run's frozen Project revision; a changed
revision already fails the run, so membership is effectively frozen.

Default processing order for "Build all": areas that share the most tables with other
areas first (shared entities get designed in context), then the rest by table count
descending. The user can reorder in the dialog.

## What each AI call receives

The names below are prompt variables. Each needs: a contract in `context_contracts.py`,
a row in seed 04 (`workflow_stage_variable`), a resolver in `prompt_inputs.py` /
`context_inputs.py`, and a reader spec in `context_readers.py` for tool-assisted mode.
Existing variables are reused where noted.

### Subject-area run (replaces Conceptual)

Input, compact on purpose. Must fit 500 tables in one call.

| Variable | Content | Source |
|---|---|---|
| `table_index` | `[{id:"t1", tenant_code, system_code, connection_code, object_schema, object_name}]` for every scope table | project_input_scope |
| `scope_tables` | per table: `id, description, column_names[], row_count, zone_code` | enrichment description (fallback registered description), attribute names, max profile row_count |
| `table_links` | table-level Analysis edges, deduped: `{from:"t1", to:"t4", validation_result}` | analysis_result |
| `existing_subject_areas` | `{name, definition, is_locked, tables:["t1",...]}` | subject_area, subject_area_table |
| `context_records` | all active records (compact: id, type, text) | context |
| `source_context`, `gds_context` | existing variables | existing |

Output:

```json
{"areas": [{"name": "Sales", "definition": "...", "tables": ["t1","t2"]}],
 "unassigned": ["t9"], "retire": ["OldAreaName"]}
```

Backend checks: unique names; every `t` id exists; each table in at least one area or in
`unassigned`; no area over the size cap (`max_subject_area_columns`, config, default 300;
repair feedback: "split Sales (412 columns)"); locked areas and locked memberships
unchanged. Unassigned is not stored; it is every scope table with no active membership.

### Logical Build, one call per area

| Variable | Content | Notes |
|---|---|---|
| `subject_area_context` | `{name, definition, table_count}` | new |
| `table_index` | short ids for the area's tables and for neighbour tables that appear in Analysis edges | new; neighbours flagged `in_area:false` |
| `object_context`, `object_attribute_context`, `object_relationship_context`, `ingestion_mapping`, `source_context`, `gds_context` | existing variables, filtered to the area's tables; relationships include edges whose other end is outside the area | existing, filtered |
| `existing_entities` | full records for every active Logical entity with an active object source in the area's tables: entity, nested attributes with sources, relationships where either endpoint is one of these entities | new; replaces today's full `logical_entities/attributes/relationships` dump |
| `neighbor_entities` | compact: `{schema, name, type, grain, key_attributes:[{name,type}], linked_via}` for entities at the other end of those relationships, plus entities built from neighbour tables | new |
| `entity_directory` | `{schema, name, definition}` one line for every other active entity | new; prevents duplicates |
| `context_records` | records whose group has no System or a System among the area's tables' Systems, plus records already cited by `existing_entities` | existing variable, filtered |
| `naming_instructions`, `schemas`, `logical_entity_scd_type`, `audit_columns`, `coverage_threshold_percent` | existing | |
| `logical_entity_types` | active rows of `reference.logical_entity_type` with descriptions | new |

Tool-assisted readers: `get_objects`, `get_object_details`, `get_object_relationships`,
`get_context_records` (existing, scoped to the area bundle), `get_logical_entities`,
`get_logical_attributes`, `get_logical_relationships` (existing, over the whole model, so
the AI can inspect a directory entry). Remove `list_*` readers and all submodel readers.

Output: the trimmed shape in `ddl/05_ai_output.md`. The backend expands it into today's
full `StageProjectChange` records (`logical_entity`, `logical_attribute`,
`logical_relationship`) before `validate_future_graph`, so Change Set validation, Apply,
MCP and the plugin keep today's record contracts (minus submodels).

Per-area loop inside `LogicalWorkflow.execute_started`:

1. Load the run plan and the full context bundle once (existing).
2. For each selected area in order: build the area bundle (filters above, including
   changes accumulated from earlier areas in this run, applied in memory on top of the
   snapshot); run the stage with the existing `AgentStageRunner` (repair loop included);
   expand the output; project audit policy; `validate_future_graph` over snapshot +
   accumulated changes; record progress "Building Sales (2 of 5)".
3. Coverage: existing `validate_coverage` over the run's full selection after the last
   area; per-area coverage is advisory feedback only.
4. One `finalize` with the union of changes (existing handoff). No-op path as today.

Resumability: an area that fails after retries fails the run (as today). Later: retain
completed areas' changes as a rejected draft for review (existing
`retain_failed_candidate`).

### Logical Optimize, one call over the model

| Variable | Content |
|---|---|
| `model_summary` | per active entity: `schema, name, type, grain, subject_areas (derived), keys:[{name,type}], attribute_count, sources:["t1"]`; relationships: `child.attr → parent` |
| `unlinked_analysis_edges` | Analysis edges (validated `supported` or unvalidated) between tables whose entities have no relationship between them |
| `type_conflicts` | relationship endpoints whose attributes differ in data type; attributes with the same name and different types across entities |
| `name_variants` | names differing only by case, underscore or a known suffix (`CustID`/`CustomerID`) |
| `check_results` | latest failed `model_check_result` rows, if Validate has run |
| `context_records` | all active records |
| settings | as Build |

One-shot adds full detail for the entities named in the deterministic findings only.
Tool-assisted readers: `get_logical_entities`, `get_logical_attributes`,
`get_logical_relationships`, `get_object_details`, `get_object_relationships`,
`get_context_records`.

Output: same trimmed shape plus `retire`. A merge is: retire one entity, add its sources
to the surviving entity, re-point relationships. Backend validation catches dangling
references, as today.

Scale rule: if `model_summary` exceeds the one-shot context budget, Optimize splits the
model into connected groups (entities joined by relationships or unlinked edges) and runs
one call per group. Implement the single call first; add grouping only when a real
project needs it.

### Logical Validate, deterministic

Mirrors `features/analysis/validation_service.py` and `validation_execution.py`:
Databricks connection resolution, bounded parallel queries, policy version, results
saved directly, run completed without a draft.

| Check | For | Query shape | Reuse |
|---|---|---|---|
| `key_unique` | each active entity with natural-key attributes, per active object source | `SELECT count(*), count(DISTINCT (c1, c2))` over the mapped source columns | single-column keys: `attribute_profile.distinct_count` vs `non_null_count` when `row_scope = all_rows` |
| `parent_found` | each active relationship whose endpoints both map to single physical columns | left anti-join count child → parent | an Analysis result on the same column pair: reuse `validation_source_missing_target_count` |
| `required_filled` | each non-nullable attribute with a physical source | null count | `attribute_profile.null_count` when available |

Anything that cannot be mapped to physical columns (Context-only, consolidated keys
across tables) records `inconclusive`. Results go to `workflow.model_check_result`
(`ddl/04_runs_and_checks.sql`). A new Validate run replaces the earlier result of the
same check on the same record.

### Dimensional Build, one call per area (Phase 7)

Same shape as Logical Build with the Logical layer as input:

| Variable | Content |
|---|---|
| `subject_area_context` | as Logical |
| `logical_entities` | full records for active Logical entities with a source in the area's tables (the Dimensional "tables") |
| physical cards | existing `object_attribute_context`, profiles, `object_relationship_context` for those entities' sources |
| `existing_dimensional_entities` | full records for Dimensional entities with a source among those Logical entities |
| `neighbor_dimensional_entities` | compact; e.g. shared dimensions linked to them |
| `dimensional_directory` | one line per other Dimensional entity, so `Date` is reused |
| `context_records` | same filter as Logical Build |
| Gold settings | existing |
| `dimensional_fact_types` | active rows of `reference.dimensional_fact_type` |

Dimensional Optimize: conformed dimensions (one `User`, one `Date`), role names,
type conflicts. Dimensional Validate: fact grain unique, every fact row finds its
dimension rows.

## Phases

Each phase lists: goal, changes, tests, done criteria, questions for the user.

### Phase 0: baseline (no code)

- Rerun the 91-table project with today's Logical (tool-assisted, then one-shot in
  batches of ~10 Objects as the workaround). Record: wall time, tokens, coverage %,
  entity count, duplicate entities (same source table in two entities), Analysis edges
  turned into relationships, reviewer notes on quality.
- Store the numbers in `.scratch/subject-area-modeling/baseline.md`.
- Done: the numbers exist. Every later phase compares against them.

### Phase 1: trim the Logical AI output; the backend fills the rest (web only)

Goal: 6–12× smaller answers with no contract change outside the web app.

Changes:
- `features/logical/candidate.py`: new output schema (trimmed shape from
  `ddl/05_ai_output.md`, still with the four arrays minus `submodels`; keep `grain`).
  New expansion step: short ids → physical keys; nested attributes → flat
  `logical_attribute` records; defaults for the fields the AI no longer sends (status
  active, locks false, audit false, surrogate false, ordinal from order); missing
  attribute definition → source column description; parent key of a relationship →
  the parent's surrogate attribute. Output `StageProjectChange` records exactly as today.
- `features/logical/policy.py`: unchanged behaviour (surrogate/audit projection), check
  it accepts the expanded records.
- Prompt variable `table_index` (new) for Logical; `context_contracts.py`, seed 04 row,
  `prompt_inputs.py`.
- Seed 05 Logical prompts (both modes): describe the new output; remove Submodel planning
  from the design order; keep everything else.
- Repair feedback: issues must reference the AI's shape (`entities[2].attributes[5]`),
  not the expanded shape. Map paths in the expansion step.
- `max_candidate_bytes` stays 2 MiB; measure actual sizes.

Tests: `tests/web_backend/test_logical_candidate.py`, `test_logical_executor.py`,
`test_logical_prompt_inputs.py`, `test_logical_prompt_guidance.py`,
`tests/mcp/test_database_global_prompt_seed.py` (prompt digests), `test_default_prompt_contracts.py`.
Add: expansion unit tests (short id resolution, missing definition default, surrogate
endpoint, path mapping), a synthetic full-graph round trip with the trimmed shape.

Done: the 91-table project completes in one or two one-shot calls, or tool-assisted
without the 2 h timeout; quality not worse than baseline on the recorded measures.

Questions for the user: confirm the attribute-definition default (copy the source
column's description); confirm dropping relationship names and `cardinality_basis`
(merge into `basis`) from the AI output now, with the DDL change deferred to Phase 4.

### Phase 2: send each Logical run only the relevant slice of the model (web only)

Goal: input stops growing with the model.

Changes:
- `features/workflows/authoring/context.py` `_applicable_applied_records` /
  `_assemble_context`: for Logical, replace the full `snapshot.logical` with
  `existing_entities` (entities sourced from the selected tables),
  `neighbor_entities`, `entity_directory`. Keep the full snapshot private for
  `validate_future_graph` (it already is).
- Context record filter (System of the selected tables + already cited).
- New variables and contracts: `existing_entities`, `neighbor_entities`,
  `entity_directory`; remove `logical_submodels`, `logical_entities`,
  `logical_attributes`, `logical_relationships` as prompt variables; keep the
  `get_logical_*` readers for tool-assisted.
- Seed 04/05 updates.

Tests: `test_agent_context.py`, `test_database_agent_context.py`,
`test_context_selection.py`, `test_workflow_context_readers.py`, `test_conceptual_isolation.py`
(still holds: Conceptual is not an input until Phase 3 removes the section).
Add: slice selection unit tests (entity from a selected table is full; a linked one is
compact; others are one line).

Done: input bytes for a 10-table run stay flat as the applied model grows (measure
with two runs on the 91-table project).

### Phase 3: subject areas replace Conceptual (all four surfaces)

Goal: the `subject_area` section exists end to end; Conceptual is gone.

3a. Database and shared contracts
- `database/06_workflow_conceptual.sql` → `06_workflow_subject_area.sql` from
  `ddl/01_subject_areas.sql` (keep today's column style for now: `status`, audit columns;
  cosmetic trims deferred).
- `15_mcp_change_sets.sql`: `conceptual_document` → `subject_area_document`.
- `19_runtime_integrity.sql`, `20_verify_install.sql`: table, trigger and grant
  expectations.
- MCP `domain/snapshots/project.py`: datasets `subject_area` (key `subject_area_name`)
  and `subject_area_table` (key `subject_area_name` + physical object key) replace
  `conceptual_object`/`conceptual_relationship`; dataset count becomes 25 again
  (−2 +2). `domain/modeling_records.py`: record classes. `application/change_sets/
  project_validation.py` and `project_apply.py`: validate names, scope membership, locks;
  upsert. `application/modeling/conceptual.py` → `subject_area.py`.
  `project_guidance.py`, `tools/snapshots/project/archive.py`, `read_project_section.py`.
- VS Code `src/stage-contract.ts` allowlist; regenerate `server-contract.json`.
- Plugin: dataset docs in `references/snapshots/project.md` (count check in
  `tests/atlas/test_instructions.py`), `workbench/*.js` quality metrics.

3b. Web backend
- `features/conceptual/` → `features/subject_areas/`: run service (prompt variables
  above, output validation, size cap), read service and routes (areas, memberships,
  unassigned list), `candidate.py`.
- Run identity: `project_workflow = 'subject_area'`; `runs/contracts.py`,
  `commands/`, `execution/dispatcher.py`, `assembly.py`, `runtime.py`, `main.py`,
  `overview/`.
- `project_targets/ddl.py` and `service.py`: remove the ConceptID export.
- Manual review (`project_record_review` backend): `subject_area` and
  `subject_area_table` datasets editable; moving a table between areas is a manual edit.
- Seed 04 stages/variables and seed 05 prompts for `subject_area` (one_shot,
  tool_assisted); seed 08 local review data.
- `tool_configuration.py`, `context_readers.py`: readers for the new variables; remove
  conceptual readers; `12_application_configuration.sql` tool allowlist.

3c. Frontend
- `features/conceptual/` → `features/subject_areas/`: list of areas with table counts,
  area detail with its tables, Unassigned list, run dialog (whole scope, no table
  picker), manual move/add/remove through the review editor.
- Routing, navigation, overview, `WorkflowRunDialog`, `WorkflowRunMonitor` labels,
  `project_record_review` dataset types.

3d. Plugin
- `skills/atlas-conceptual-model` → `skills/atlas-subject-areas` (same step template,
  ≤450 words, 3–9 steps; fixed skill list in `tests/atlas/test_packaging.py`).
- References: remove `conceptual-build/`, `project/conceptual.md`; add
  `project/subject-areas.md`. Remove the "Conceptual never feeds Logical" rule from
  `working-method.md` and everywhere the inventory lists; replace with: "Subject areas
  decide which tables a Logical Build works on; they are not modeling evidence."
- Eval scenarios in `tests/atlas/eval/scenarios.json` and the shared-rules test.
- Rebuild the plugin ZIP and VSIX; packaging tests compare them with source.

3e. Docs
- `CONTEXT.md`, `docs/workflows.md`, `docs/architecture/decisions.md`,
  `docs/architecture/overview.md`, `atlas/README.md`, `docs/agents/*` where they
  describe Conceptual.

Tests: delete the `test_conceptual_*` and `test_database_conceptual*` files; add
`test_subject_areas*` equivalents (candidate validation incl. size cap, executor,
record review, prompt inputs, isolation test replaced by "subject areas select tables
but are not prompt evidence"). MCP: change set round trip, snapshot schema, apply.
Atlas: instructions, packaging, stage contract, workspace, eval harness.

Done: a fresh install passes `20_verify_install.sql`; a subject-area run on the
91-table project produces areas you can review, edit and Apply; the plugin can read and
stage the two datasets; Conceptual no longer appears anywhere (grep is clean).

Questions for the user: area size cap default (300 columns?); whether to keep a
`reason` text per membership (currently dropped); whether the subject-area run should
read column names for all tables (fits ~500 tables) or only descriptions.

### Phase 4: Logical Build by subject area

Goal: "Run Logical" becomes "Build" over selected areas; submodels removed.

Changes:
- Run identity: `workflow_operation`, `workflow_run_subject_area_selection`,
  `snapshot_workflow_run_prompts` stage filter, `create_workflow_run` filling the object
  selection from the areas; `commands/contracts.py` (`subject_area_ids`,
  `workflow_operation`), `runs/contracts.py`, `plan.py` (`_validate_plan` expects
  `build_authoring`).
- `database/07_workflow_logical.sql` rewritten from `ddl/02_logical.sql`: drop
  `logical_submodel`, `logical_entity_submodel`; `logical_entity_type` → FK to
  `reference.logical_entity_type` (`ddl/00_reference_lists.sql` into `01_reference.sql`);
  keep `logical_entity_grain`; relationship table loses name/definition/cardinality_basis
  if Phase 1 confirmed it. Decide here whether to take the cosmetic trims for this table
  family (status → is_active, drop agent_run_id/created_by/updated_by) since the file is
  rewritten anyway; if yes, do it for the Logical tables only and update MCP record
  classes, snapshot datasets, Apply, plugin references and the VS Code allowlist in the
  same PR.
- `features/logical/service.py`: the per-area loop described above; progress events per
  area; coverage over the union.
- Context: `existing_entities` etc. computed per area from the one loaded bundle;
  `InMemoryAgentContextToolCatalog` built per area so tool-assisted readers scope to it.
- Seed 04: stages `build_authoring` (both modes); variables `subject_area_context`,
  `logical_entity_types`; seed 05 Build prompts.
- Remove submodel readers, variables, contracts, read routes, frontend Submodels ledger
  and filters, DBML per-submodel export (`workbench/dbml.js` → one file per subject
  area derived from sources), plugin references to Submodels.
- Frontend: Logical screen gets Build / Optimize / Validate buttons; Build dialog lists
  subject areas with table counts, "All" with the default order, drag or number to
  reorder; draft review filter by area (derived from sources).
- Remove the table picker for Logical runs.

Tests: logical candidate/executor/policy/coverage tests updated for areas; new tests for
area ordering, per-area accumulation (area 2 sees area 1's entity), shared-table reuse
(no duplicate entity), locked entity untouched, run fails cleanly when an area exhausts
retries; MCP apply/snapshot tests without submodels; frontend dialog tests.

Done: Build all on the 91-table project completes within the Tenant Lock window
(240 min max; measure); one draft; no duplicate entities for shared tables; quality
not worse than baseline.

Questions for the user: cosmetic trims now or later; default order rule; whether a
single-area Build may create a relationship to an entity that does not exist yet
(answer so far: no; Optimize adds it later).

### Phase 5: Logical Validate

Changes: `workflow.model_check_result` (`ddl/04_runs_and_checks.sql`), stage
`model_validation`, `features/logical/validation_service.py` modelled on
`features/analysis/validation_service.py` and `validation_execution.py`, config
`logical_validation.json` (parallel queries, statement timeout, policy version), SQL
functions for execution context and persistence in `14_application_workflow_execution.sql`,
results on the Logical screen (per entity, per relationship), MCP read-only dataset
`model_check_result` in Snapshots (optional; ask).

Tests: SQL builder unit tests (composite keys, quoting, inconclusive cases), database
round trip with the disposable container, service tests with a fake connector.

Done: Validate on the 91-table project runs on Databricks within the statement timeout
and shows pass/fail per key and relationship.

### Phase 6: Logical Optimize

Changes: stage `optimize_authoring` (both modes); deterministic finders in the backend
(`unlinked_analysis_edges`, `type_conflicts`, `name_variants`); variables and prompts;
`features/logical/service.py` branch on `workflow_operation`; output expansion shared
with Build; frontend button and monitor labels.

Tests: finder unit tests with synthetic models; executor test with a fake agent that
returns a merge; full-graph validation of re-pointed relationships.

Done: Optimize on the built 91-table model proposes only cross-area fixes; review
shows before/after per change.

### Phase 7: Dimensional

Same three operations. `08_workflow_dimensional.sql` from `ddl/03_dimensional.sql`
(drop submodels, fact type FK to `reference.dimensional_fact_type`, child → parent
relationships; take the cosmetic trims if Phase 4 took them for Logical). Build by area
over Logical entities; Optimize for conformed dimensions; Validate for fact grain and
dimension lookups. Mapping/Code/Validation consumers of Dimensional records
(`features/mapping`, `code_generation`, `validation`, `project_targets`) adapt to the
removed fields (`kind`, `is_optional`, `cardinality` → derived).

### Phase 8: housekeeping

Whatever cosmetic trims were deferred; `reference.domain` cleanup if unused; docs pass.

## Cleanup inventory

See `INVENTORY.md` next to this file: every file that references Conceptual or
Submodels, grouped by surface, produced from the code on 2026-10-25, plus the table of
pinned counts (prompt seeds, snapshot datasets, application tables, skill list) that
each phase moves. Each Phase 3 and 4 PR must leave `grep -ri conceptual` and
`grep -ri submodel` clean for its surface, except history in frozen workflow runs and
seed 05 version history, which stay.

## Risks to watch

- Tenant Lock: a Build-all run must finish within 240 minutes. Trimmed output makes each
  call much faster; measure in Phase 4 before adding parallel area calls.
- First-touch bias: the first area to build a shared table shapes its entity. Default
  order (most-shared first) and Optimize mitigate it; watch in review.
- Prompt digests: every seed 05 edit publishes a new version; frozen runs keep theirs.
- Fixed counts in tests: 14 prompt seeds, 25 snapshot datasets, the plugin skill list,
  450-word skill limit. Update deliberately, never by loosening the test.
- Review load: a Build-all draft can be large. The draft screen must filter by area.
