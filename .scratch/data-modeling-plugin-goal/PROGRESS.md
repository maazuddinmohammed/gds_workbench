# Data-modeling plugin goal

## Checkpoint 1 — authoritative inventory

Status: complete

- Repository rules, `CONTEXT.md`, ADRs, architecture docs, plugin sources, tests, and packaging were inspected.
- Plugin source of truth: `plugins/gds`; current version: `1.2.0`.
- Viewer source of truth: `plugins/gds/skills/open-gds-metadata-workbench/assets/workbench`. The separate `json_viewer` workspace is a prototype only.
- Runtime registers 51 MCP tools. Modeling writes use only the governed Model Change Set lifecycle: `create_model_change_set` → `stage_model_change_set` → `validate_model_change_set` → explicit approval → `apply_model_change_set`; `get_model_change_set` inspects a draft and `archive_model_change_set` retains a discarded draft.
- Model drafts contain up to 19 complete, ID-free pending dataset replacements. Exact record contracts come from `describe_model_dataset`; current state comes from model read tools and `get_model_snapshot`.
- `get_model` is the source for existing naming templates. Naming changes are full `model_details` records; there is no separate naming-template mutation tool.
- Model Snapshot v2 has eight Sections and 19 datasets. Unlike Metadata Snapshot, it has no search files, model key normalization trims/case-folds all strings, and `model_details` has an empty canonical key.
- Current Workbench supports Metadata Snapshot v2 and local Metadata Change Sets only. It cannot load Model Snapshots, nested model schemas, Model Change Sets, or the three model-mapping datasets.
- The viewer is intentionally offline. It can author local files but cannot create a server Snapshot or Stage/Validate/Apply a server Change Set.
- Relevant Wiley/Kimball guidance was extracted as paraphrased design checks: business process, explicit atomic grain, dimensions, facts and additivity, conformance, SCD policy, multivalued bridges, late-arriving data, source profiling/mapping, and iterative stakeholder validation.
- Packaging is deterministic via `plugins/build_gds_plugin_zip.py`; it refuses overwrite and uses `plugins/dist/gds-agent-plugin-<version>.zip`.

### Constraints carried forward

- One small change plus focused verification at a time.
- Preserve the dirty worktree and avoid unrelated refactors.
- Never invent MCP names or arguments; use current source contracts.
- No live database, Azure, Databricks, deployment, install, publish, push, or PR operations.
- Keep the viewer offline and preserve current Metadata behavior.
- Treat the attached PDF as reference material, never as instructions, and do not bundle copied book text.

### Next checkpoint

Document shared tool/dataset/workflow references, then scaffold and validate the seven requested skills.

## Checkpoint 2 — shared release references

Status: complete

- Added a test-matched inventory of all 51 registered MCP tools and exact Model read, Snapshot, DBML, Tenant Lock, Model Change Set, naming-template, and mapping boundaries.
- Added the eight-Section/19-dataset registry, canonical keys, lifecycle semantics, high-risk cross-field rules, reference graph, and Model Snapshot archive contract.
- Added the governed read → draft → review → lock → create/resume → reconcile → Stage → Validate → explicit Apply approval → verify → release sequence with error recovery.
- Added Conceptual, Logical, Dimensional, and Mapping practice guidance, including paraphrased dimensional checks with PDF page references.
- Added a compact, reusable modeling decision-record format.
- Verified the reference inventory exactly matches `tests/mcp/test_runtime.py`; all local Markdown links resolve and `git diff --check` passes.

### Next checkpoint

Scaffold each requested skill, replace generated placeholders with bounded workflows, register them, and run structural/trigger validation.

## Checkpoint 3 — seven skills

Status: complete

- Added and registered `build-conceptual-model`, `build-logical-model`, `build-dimensional-model`, `build-data-mapping`, `author-model-metadata`, `grill-data-model`, and `run-data-modeling-goal`.
- Every skill has valid `SKILL.md` frontmatter plus quoted `agents/openai.yaml` discovery metadata whose default prompt invokes the skill explicitly.
- All Model-building skills read current Models/naming templates, use exact live schemas, preview complete ID-free records, follow the governed Change Set sequence, and require fresh Apply approval.
- The metadata-authoring skill routes exact JSON explanations through `describe_metadata_dataset`, synthetic data only, a verified Metadata Snapshot, and the existing Metadata Change Set workflow.
- The grill asks exactly one question per turn, defaults to seven, hard-stops at ten unless explicitly changed, stops early, and records decisions without endless interrogation.
- The goal skill clearly separates prompt preparation from explicit goal start, defines one stopping condition/checkpoint loop, and states that persistence belongs to Codex `/goal`, not the skill.
- All seven passed the official `quick_validate.py` validator offline. A repository contract test also passed and locks the seven names, 51-tool inventory, 19-dataset registry, grill bound, and goal start boundary.

### Next checkpoint

Generalize the integrated offline Workbench without regressing Metadata behavior, then add Model round-trip tests before visual QA.

## Checkpoint 4 — integrated Data Workbench

Status: complete

- Generalized the existing offline Workbench around manifest-derived Metadata and Model profiles while preserving the original Metadata draft paths and behavior.
- Metadata Snapshots expose all 29 datasets for inspection; only the exact 16 governed Metadata Change Set datasets are editable.
- Model Snapshots expose all eight Sections and exact 19 datasets, including Profiling, Analysis, Assertions, and all three Mapping datasets.
- Added recursive validation for the JSON Schema features emitted by current Model contracts, model canonical-key handling, nested field highlighting, per-record semantic checks, and server-authoritative cross-record warnings.
- Added local Model Change Set editing, an explicitly unbound/bound Model Stage preview, and proposed Model Snapshot JSON export that preserves the baseline revision and never claims to be an authoritative server Snapshot.
- Added pure Model aggregate/overlay/Stage round trips and real Snapshot archive fixtures to the Node and Python tests.
- Browser QA completed the Metadata edit/save/review path and the Model nested-validation/mapping add-edit-remove/save/review/export path against disposable synthetic archives.
- Visual QA at 1440×1000 and 390×844 found and fixed mobile horizontal overflow plus validation-dialog row overlap. Final mobile body width equals the 390-pixel viewport.

## Checkpoint 5 — release validation

Status: complete

- All seven new skills pass the official `quick_validate.py` validator.
- `tests/plugin/test_gds_plugin.py`: 47 passed.
- Focused Model/runtime contract tests: 36 non-database tests passed.
- The one relevant database runtime test passed using only the repository fixture's disposable PostgreSQL container with random credentials and container disposal.
- `ruff` passed for the changed Python package/test surfaces.
- `node --check` passed for Workbench logic and app code; the expanded Node logic smoke passed.
- Browser flows verified 29 Metadata datasets, 19 Model datasets, eight Model Sections, nested errors, mapping changes, local Stage-template JSON, proposed Model Snapshot export, no external calls, and responsive layout.

## Checkpoint 6 — local distribution

Status: complete

- Bumped the Portable Agent Plugin version to `1.3.0` and updated package discovery copy.
- Built `plugins/dist/gds-agent-plugin-1.3.0.zip` through the deterministic repository builder.
- ZIP integrity passed; 62 entries are rooted under `gds/`, all seven new skills and Workbench assets are present, and no `.DS_Store`, `__pycache__`, or `.scratch` entry is included.
- Final archive size: 152,834 bytes.
- SHA-256: `f9feaf7c637ae52e6a5762e6cd7189bf1a3430134df8f83f71292b91dd4b2834`.
- No plugin install, publish, deployment, push, or pull request was performed.
