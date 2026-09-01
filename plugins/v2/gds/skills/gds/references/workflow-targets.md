# Workflow targets

Choose one target, Build mode, and Full/Selected scope per task; each target has at most one Apply:

1. **Logical Build** — Analysis/Conceptual support and Logical.
2. **Silver Target Registration** — applied Logical to local DDL and Silver Metadata.
3. **Logical Mapping** — Logical to Silver target/source pairs.
4. **Logical Code Generation** — Code from applied active Logical Mapping.
5. **Dimensional Build** — optional model from applied Logical Mapping/evidence.
6. **Gold Target Registration** — Dimensional to local DDL and Gold Metadata.
7. **Dimensional Mapping** — eligible Silver contributions to Gold targets.
8. **Dimensional Code Generation** — Code from applied active Dimensional Mapping.
9. **QA** — Validation Groups/Checks for selected source System codes.

Numbers catalog targets; they do not force a run. An Automatic journey may queue an ordered subset,
but executes one target at a time. Applied Logical Mapping unlocks Logical Code, optional
Dimensional Build, and QA; other applied Mapping unlocks its Code and QA. Code is optional, but
current relevant Code informs QA. Dimensional is optional. Never cross an Apply boundary automatically.

## Common readiness

Use one Model and fresh required Snapshots. Mutation needs task/plan; only `active` inputs unlock
downstream work. Model Snapshot flags are authoritative:

- `is_bronze_source_eligible`: Bronze Profile/Analysis/Conceptual/Logical sources.
- `is_dimensional_source_eligible`: Silver sources with an active applied Logical Mapping contribution.
- `is_logical_mapping_target_eligible` / `is_dimensional_mapping_target_eligible`: Silver/Gold targets.

Never infer eligibility from `zone_code` alone. Target Registration writes Metadata, not Model
Scope. Mapping waits for the separate web-governed Model Scope path outside public MCP and this plugin.
If its flag is false/absent, ask the authorized scope owner to activate it, download a fresh
Model Snapshot, replace `model/`, and resume.

Applied `needs_review` Mapping unlocks nothing; local task state is unrelated to record status. A
requested number defines input scope, never an output quota; report splits, exclusions, blockers.

Assertion capture is the one pre-process, non-target Model custom task. Persist only user-supplied
evidence and stop after Apply; Assertions never become executable lineage.

## Load only the active target

- Logical: `workflows/logical-build.md`; Dimensional: `workflows/dimensional-build.md`
- Registration: `workflows/target-registration.md`; Mapping: `workflows/mapping.md`
- Code: `workflows/code-generation.md`; QA: `workflows/qa.md`
