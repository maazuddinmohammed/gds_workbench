# Workflow target router

Choose one target, one Build mode, and Full or Selected scope per task. Each target has at most one
Apply:

1. **Logical Build** — selected Analysis/Conceptual support and Logical model.
2. **Silver Target Registration** — applied Logical to local DDL and Silver Metadata.
3. **Logical Mapping** — applied Logical to registered Silver targets by target/source System.
4. **Logical Code Generation** — governed Code from applied active Logical Mapping.
5. **Dimensional Build** — optional Dimensional model from applied Logical Mapping and evidence.
6. **Gold Target Registration** — applied Dimensional to local DDL and Gold Metadata.
7. **Dimensional Mapping** — eligible Silver contributions to registered Gold targets.
8. **Dimensional Code Generation** — governed Code from applied active Dimensional Mapping.
9. **QA** — Validation Groups/Checks for exact selected source System codes.

The numbers catalog targets; they are not a forced linear run. Applied Logical Mapping unlocks
Logical Code, optional Dimensional Build, and QA. Any other applied Mapping unlocks its Code and QA.
Code may be absent; current relevant Code must inform QA. Dimensional is optional. Never cross an Apply boundary automatically: stop and show only eligible next targets.

## Common readiness

- Use one Model per session and fresh required Snapshots. Mutation needs a task and plan; only
  `active` inputs unlock downstream work.
- Model Snapshot flags are authoritative: `is_bronze_source_eligible` selects scoped Bronze
  Profile/Analysis/Conceptual/Logical sources; `is_dimensional_source_eligible` selects scoped
  Silver contributions from an active applied Logical Mapping contribution;
  `is_logical_mapping_target_eligible` and `is_dimensional_mapping_target_eligible` select
  Silver/Gold Mapping targets. Never infer eligibility from `zone_code` alone.
- Target Registration writes Metadata, not Model Scope. Mapping waits for the separate web-governed Model Scope path outside public MCP and this plugin. If its flag is false/absent:
  “Ask the authorized scope owner to apply this target to Model Scope, download a fresh Model
  Snapshot, replace `model/`, then resume.”
- Applied `needs_review` Mapping unlocks nothing. A requested number defines input scope, never an output quota; report splits, exclusions, and blockers.

Assertion capture is the one pre-process, non-target Model custom task. Persist only user-supplied
evidence and stop after Apply; Assertions never become executable lineage.

## Load only the active target

- Logical Build: `workflows/logical-build.md`
- Silver/Gold Target Registration: `workflows/target-registration.md`
- Logical/Dimensional Mapping: `workflows/mapping.md`
- Logical/Dimensional Code Generation: `workflows/code-generation.md`
- Dimensional Build: `workflows/dimensional-build.md`
- QA: `workflows/qa.md`
