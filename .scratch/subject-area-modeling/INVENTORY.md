# Cleanup inventory

Produced by a code scan on 2026-10-25. Line numbers drift; use them as pointers, then
grep. Each Phase 3 and Phase 4 PR must leave `grep -ri conceptual` and `grep -ri submodel`
clean for its surface. Frozen workflow-run history and seed-05 version history stay.

Pinned counts that move (update the test on purpose, never loosen it):

| Pin | Where | Today | After |
|---|---|---|---|
| Agentic stages = prompt seeds | `tests/mcp/test_database_global_prompt_seed.py:230`, `test_database_application_reference_seed.py:287`, seed 05 line ~443 | 14 | 14 after Phase 3 (−2 conceptual, +2 subject_area); 16 after Phase 6 (+2 optimize); 18 after Phase 7 |
| Snapshot datasets | `tests/mcp/test_modeling_snapshot_contracts.py:74,480-483`, `atlas/atlas-plugin/references/snapshots/project.md:29`, `tests/atlas/test_instructions.py` | 25 | 25 after Phase 3 (−2 +2); 24 after Phase 4 (−logical_submodel); 23 after Phase 7 |
| `application` schema table count | `database/20_verify_install.sql:262` | 17 | 18 after Phase 4 (`workflow_run_subject_area_selection`) |
| Agentic stages for analysis+conceptual+logical+dimensional | `tests/web_backend/test_database_seeded_analysis_conceptual.py:130` | 12 | rename the test; recount |
| Plugin skill list | `tests/atlas/test_packaging.py:141-153` | includes `atlas-conceptual-model` | `atlas-subject-areas` |
| Skill template | `tests/atlas/test_instructions.py:177-186` | 6 sections, ≤450 words, 3–9 steps | unchanged |

## 1. Frontend (`web_app/frontend/src`)

Delete: `features/conceptual/` (screens, api, tests).

Conceptual references to edit:
- `app.tsx`: imports 32-36; routes 313-331 registered at 428-430; components 1046-1140 (`dataset={\`conceptual_${kind}\`}` at 1126). `app.test.tsx` 576, 610, 929.
- `features/projects/ProjectWorkspaceShell.tsx` 11, 22 (+ test 37, 47, 147); `features/projects/api.ts` 66, 106.
- `api.ts` barrel 18-20, 99-113, 298, 320; `api.test.ts` 399-420.
- `features/workflows/api.ts` 8, 364, 522-529; `WorkflowRunDialog.tsx` 31, 111-113; `WorkflowRunMonitor.tsx` 42 (+ `workflowLabel()` 989, `runKind()` 996); tests `WorkflowRunMonitor.test.tsx` 53, 110-140, 350-470, `features/workflows/api.test.ts` 26-28, 86-99; `features/workflows/presentation.tsx:93`.
- `features/project_record_review/api.ts` 6, 19, 73; `ProjectRecordReview.tsx` 10, 219-220; `ProjectLayerActions.tsx` 8, 15; `ProjectRecordEditor.tsx` 38; `ProjectRecordReview.test.tsx` 14-246.
- `features/project_targets/DdlExportButton.tsx` 9, 25; `features/project_targets/api.ts` 11; `exports.test.tsx` 14.
- `features/prompts/PromptsScreen.tsx` 33; `PromptVariables.tsx` 20.
- `styles/analysis-context-modeled.css`: all `.conceptual-*` rules.

Submodel references to edit:
- `features/logical/api.ts` 19, 41-45, 98, 206-240, 280-291, 335+; `LogicalScreen.tsx` 15-225 (submodels view); `LogicalLedgers.tsx` 183-240; `LogicalDetail.tsx` 96-115, 161-176, 281-323; tests `LogicalScreen.test.tsx`, `features/logical/api.test.ts`.
- `app.tsx` route `/logical/submodels/$submodelId` 362-366, 435; component 1242-1305.
- `features/dimensional/api.ts` 44-48, 97; `DimensionalScreen.tsx` 24, 74-80, 111, 130, 160-162; `DimensionalDetail.tsx` 162-176; `DimensionalScreen.test.tsx` 28-62, 401-405.
- `features/project_record_review/api.ts` 7-8; `ProjectRecordReview.tsx` 146; `api.ts` 133, 158-162.

Precedents: `features/workflows/api.ts:90` `mapping_operation` (for `workflow_operation`); `shared/ProjectLayerTabs.tsx` (logical/dimensional tabs).

## 2. Web backend (`web_app/backend/gds_workbench_api`)

Delete: `features/conceptual/` (seven modules). It imports `ConceptualSection` from MCP
`domain/snapshots/project.py`, so the MCP change lands first or together.

Wiring: `main.py` 37-40, 181-182, 388-399; `runtime.py` 25, 226-231;
`features/workflows/execution/assembly.py` 24, 88, 106, 155, 228; `execution/dispatcher.py`
27, 54-55; `execution/contracts.py` 15, 56; `database.py:360` (readiness check on
`workflow.conceptual_object` privilege).

Workflow literals: `features/workflows/runs/contracts.py:17`; `overview/contracts.py` 13, 28;
`overview/service.py` 89-102, 386, 402; `features/projects/contracts.py:16`;
`features/prompts/contracts.py:22`; `authoring/plan.py:23`; `authoring/no_op.py:30`;
`authoring/change_set_apply.py:37`; `authoring/change_set_handoff.py:64`.

Run creation: `features/workflows/commands/contracts.py` (`validate_workflow_shape`,
`requires_mode` at 167; `mapping_operation` at 37 is the precedent); `commands/service.py`
~200 (parameters to `application.create_workflow_run`).

Authoring:
- `authoring/context.py` 229, 288 (`WHERE %s IN ('analysis','conceptual',...)`), 433, 761, 1360-1381, 1589-1592, 1881-1883; submodels 1595, 1601.
- `context_contracts.py`: conceptual shapes 514-1147, `WORKFLOW_INPUTS["conceptual"]` 3824, examples 4098, 4301, loop 5556; `logical_submodel_list/s` 1156-1227, `dimensional_submodel_list/s` 2127-2199, examples 3581-5425.
- `context_inputs.py` 40-47, 179-202; submodels 50-51, 188.
- `context_readers.py` 46-56, 169; submodels 65-80.
- `prompt_inputs.py` 61, 76-77, 140, 290-305, 447, 455, 1101-1106, 1255; submodels 78, 82, 319-324, 371-374.
- `agent_execution.py` 32, 57-60; submodels 61-70. `tool_configuration.py:66`. `naming.py` 7-10, 19. `downstream_contracts.py:355` (prose).
- Fakes: `integrations/agents/composition.py` 43-48, 304-336; `fake_shared.py` 65-380; `fake_logical.py` 52, 100; `fake_dimensional.py` 79, 140.

DDL download (ConceptID): `features/project_targets/contracts.py:51`; `ddl.py` 97, 110, 128; `service.py` 108-113, 360-391.

Record review (`features/project_change_sets`): `contracts.py` 47, 75, 96-97, 114 (submodels 101, 105); `review.py` 26-27, 44, 55-58, 144, 177-179 (submodels 28, 32, 69); `editor.py` 19-20, 101-108 (submodels 21, 25); `deletion.py` 37 (submodels 42, 111); `repository.py` 64-76, 399, 659-660 (submodels 87-125); `service.py` 970, 1088.

Submodels in features: `features/logical/__init__.py` 36-41, 99-104; `candidate.py` 47, 68, 265, 296-477; `policy.py` 37, 152; `read_contracts.py` 45-364; `read_router.py` 237, 258; `read_service.py` 37-1074. `features/dimensional/__init__.py` 42, 93; `candidate.py` 55, 76, 287; `policy.py` 68, 249, 286, 522; `read_contracts.py` 52-56, 105; `read_service.py` (18 hits).

## 3. SQL (`database/`)

Conceptual:
- `06_workflow_conceptual.sql`: replace with the subject-area file.
- `04_project.sql:201` `ck_project_event_log_workflow`.
- `12_application_configuration.sql`: 543 `ck_workflow_stage_workflow`; 889 tool allowlist in `guard_prompt_template_version()` (890-891 hold the logical/dimensional lists, including submodel readers).
- `13_application_workflow_runs.sql`: 119, 143 CHECKs; 365, 371 no-op CHECK; 794-807 FKs to conceptual tables (submodel FKs 812-867); 1987 `create_workflow_run` eligibility CASE; 2306 `lock_authoring_workflow_run`; 3583 `complete_authoring_workflow_run_no_op`; `snapshot_workflow_run_prompts` at 980 (add the operation filter); `uq_workflow_stage_order` means `build_authoring` and `optimize_authoring` need distinct orders.
- `14_application_workflow_execution.sql:3447-3451` `delete_project_records` table list.
- `15_mcp_change_sets.sql`: 22 `conceptual_document` column, CHECKs 71, 82; 165-168 `ck_project_stage_batch_dataset`; 313 `ck_change_set_event_section`.
- `19_runtime_integrity.sql`: 416-428, 787-799 (`mcp.runtime_readiness()`); GRANT lists 1176-1192, 1251-1267.
- `20_verify_install.sql`: 1150-1166 privilege lists; 262 application table count.
- Seed 04: stage rows 47-62 (conceptual), 63-82 (logical); variable rows 188-211 (conceptual), 279-300 (logical submodels), 218-257 (dimensional submodels).
- Seed 05: `05_global_prompt_defaults.template.sql` 123-146 and `.v2.sql` 126-149 (conceptual payloads); submodel text v1 153-217, v2 156-220.
- Seed 08: 46-48, 350-390 (conceptual); 49, 60, 394-418, 526-548 (submodels).
- Install lists: `database/README.md:20`, `web_app/local/install_database.sh:63`. Tests glob `[0-9][0-9]_*.sql` (`tests/mcp/conftest.py:27`, `test_database_catalog_integrity.py:25`), so a renamed 06 file is picked up automatically.

Submodel tables: `07_workflow_logical.sql` 3, 83-116; `08_workflow_dimensional.sql` 3, 115-153.

## 4. MCP (`mcp_server/gds_etl_workbench`)

- `domain/snapshots/project.py`: `ProjectSection` 51; `ProjectDataset` 69-75; `ProjectChangeSetDataset` 96-102; `PROJECT_SECTIONS` 120; `ConceptualSection` 174; `LogicalSection.submodels` 180, `DimensionalSection.submodels` 187; `conceptual` field 221; row mapping 246-252; `DATASETS` 307 (conceptual 404-416, `logical_submodel` 420, `dimensional_submodel` 456).
- `domain/modeling_records.py`: `ConceptualObjectRecord` 477, `ConceptualRelationshipRecord` 497, `SubmodelMembershipRecord` 529, `LogicalSubmodelRecord` 629, `DimensionalSubmodelRecord` 756; membership fields 663, 671, 787, 800.
- `domain/portable_validation.py` 23-24; `domain/snapshots/project_guidance.py` 86-98, 124.
- `application/modeling/conceptual.py`: delete (becomes `subject_area.py`). `modeled_layer.py` 18, 46, 150 (submodel SQL); 302-319 already filter entities by source Object ids (reuse for `existing_entities`).
- `application/change_sets/project_apply.py`: `_apply_conceptual_objects` 1322, `_apply_conceptual_relationships` 1364, `_upsert_conceptual_support` 1415, `resolve_conceptual_object` 1476, `_upsert_submodel` 1562, `resolve_submodel` 2190, `_submodel_cache` 2274.
- `application/change_sets/project_validation.py`: 485, 642, 748, 877, 1241, 1508-1529.
- `application/change_sets/project.py:64`; `tools/change_sets/project.py:353` (`conceptual_document`).
- `application/project_snapshot.py`: ~10, 249, 387, 548.
- `tools/modeling/read_project_section.py` 20-35, 59-65, 113, 220-236; `tools/snapshots/project/archive.py` 40-42.

## 5. Atlas (`atlas/`)

Skills: delete `atlas-plugin/skills/atlas-conceptual-model/`; add `atlas-subject-areas`; edit SKILL.md in atlas, atlas-logical-model, atlas-dimensional-model, atlas-code-generation, atlas-mapping, atlas-project-change, atlas-source-analysis, atlas-verify.

References: delete `references/conceptual-build/business-concepts.md`, `references/project/conceptual.md`; add `references/project/subject-areas.md`. Edit: `local-validation.md`, `modeling-interview.md`, `terminology.md`, `working-method.md` (golden rule 6), `record-state.md`; `dimensional-build/context.md`, `design.md`; `logical-build/context.md`, `find-relationships.md`, `logical-design.md`; `methods/change-impact.md`; `platform/architecture.md`, `readiness.md`; `project/analysis-result.md`, `change-sets.md`, `context.md`, `dimensional.md`, `enrichment.md`, `logical.md`, `naming.md`; `snapshots/project.md`; `tools/reads.md`; `docs/usage-guide.md`.

Workbench JS: `workbench/dbml.js` 113-361 (one DBML file per submodel → per subject area derived from sources); `project-quality.js` 12-353; `ui/records.js` 37-43; `validation/common.js` 109-271; `validation/project-policy.js` 44-68; `validation/project.js` 143-565; `app.js` 339-340; `workspace.js` 832-857.

Scripts: `scripts/atlas-local.js` 753-784; `atlas-local.ps1` 1713-2438; `project-policy.ps1` 48-79; `project-quality-files.js:8`; `project-quality.ps1` 2-614. Each Node command has a PowerShell twin; change both.

Contracts: `atlas-vs-code/src/stage-contract.ts` 53-59; `test/fixtures/server-contract.json` 131-144, 169-234 (regenerate with `tests/atlas/test_stage_contract.py --write`).

Tests (`tests/atlas`): agent_scenarios.md; entity-ownership.test.mjs; entity-record-validation.test.mjs; eval/README.md, eval/build_fixtures.py, eval/fixtures/world.json, eval/scenarios.json; test_eval_harness.py; test_native_parity.py; test_packaging.py; test_policy_projection.py; test_shared_modeling_rules.py; test_workspace.py; workbench-app/-dbml/-logic/-policy/-quality/-workspace .test.mjs.

## 6. Tests (`tests/web_backend`, `tests/mcp`, `tests/web_packaging`)

Delete and replace with subject-area equivalents: test_conceptual.py, test_conceptual_candidate.py, test_conceptual_executor.py, test_conceptual_full_graph_repair.py, test_conceptual_isolation.py, test_conceptual_prompt_inputs.py, test_conceptual_record_review.py, test_conceptual_workflow_router.py, test_database_conceptual.py, test_database_conceptual_graph_repair.py, test_database_conceptual_record_review.py, test_database_seeded_analysis_conceptual.py.

web_backend with conceptual content (~60 files; key): test_workflow_commands, test_workflow_overview, test_runtime_wiring, test_workflow_execution_dispatcher, test_workflow_execution_assembly, test_project_ddl, test_default_prompt_contracts (parametrize at 152), test_agent_local_tools, test_agent_context, test_modeled_record_review, test_database_project_record_deletion, test_database_project_change_sets, test_database_local_review_seed, test_authoring_naming, test_authoring_no_op.

web_backend with submodel content: test_logical, test_logical_candidate, test_logical_policy, test_logical_executor, test_logical_prompt_guidance, test_dimensional, test_dimensional_candidate, test_dimensional_policy, test_dimensional_executor, test_dimensional_full_graph_repair, test_database_modeled_layers, test_project_source_coverage, test_web_project_snapshot_limits, test_candidate_history, test_agent_output_schema_guidance, test_agent_context, test_database_project_record_deletion, test_database_project_change_sets, mapping_fixtures.py.

mcp: test_database_workflow_run_lifecycle (logical stage count 2404-2416), test_database_authorization, test_project_change_set_validation, test_database_local_workbench_seed, test_database_project_snapshot_history, test_modeling_snapshot_contracts, test_database_nullable_workflow_provenance, test_database_application, test_database_prompt_mutations, project_test_fixtures.py, test_database_application_reference_seed (EXPECTED_STAGES 23-32, variables 90-93, 112), test_project_change_set_workflow_binding, test_database_global_prompt_seed, test_database_project_change_set_round_trip, test_database_authoring_no_op, test_database_project_entity_order.

web_packaging: `test_databricks_ui_artifacts.py:397` (service names include `conceptual`).

Also: `tests/web_backend/test_agent_run_plan.py` `expected_stage_count` 42, 153.

## 7. Docs and packaging

`CONTEXT.md` 48, 77, 140; `docs/workflows.md` 32-33, 58, 64-65; `docs/architecture/overview.md` 46-47; `docs/architecture/decisions.md` 79, 101, 147, 150, 293; `docs/architecture/atlas-reference-sources.md` 13, 214-216; `docs/design-system.md` 107, 109, 236; `web_app/DEPLOYMENT_GUIDE.md:184`; `database/README.md:20`; `web_app/local/install_database.sh:63`. Build scripts have no references. `web_app/frontend/prototype-atlas-*/prototype.js` hold stale mentions (low priority).
