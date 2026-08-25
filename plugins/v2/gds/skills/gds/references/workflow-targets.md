# Workflow target router

Choose one target per task, one Build mode, and Full or Selected scope. Each target has one plan and at most one Apply.

1. **Logical Build** — build selected Analysis/Conceptual support and Logical model; Model Apply ends it.
2. **Silver Target Registration** — project applied Logical into local DDL and a Silver Metadata Change Set; Metadata Apply ends it.
3. **Logical Mapping** — map applied Logical entities to registered Silver targets by target Object plus source System; Model Apply ends it.
4. **Logical Code Generation** — generate local Databricks SQL from selected applied, `active` Logical Mapping.
5. **Dimensional Build** — optionally build Dimensional from applied Logical Mapping and evidence; Model Apply ends it.
6. **Gold Target Registration** — project applied Dimensional into local DDL and a Gold Metadata Change Set; Metadata Apply ends it.
7. **Dimensional Mapping** — map Silver sources to registered Gold targets; Model Apply ends it.
8. **Dimensional Code Generation** — generate local Databricks SQL from selected applied, `active` Dimensional Mapping.

Dimensional is optional: create no task or skip flag unless requested. A later request starts at Dimensional Build and reruns readiness. Gold targets, Mapping, and Code need an applied active Dimensional model. Applied Logical Mapping unlocks Logical Code Generation and Dimensional Build; Logical code is not a Dimensional prerequisite.

Never cross an Apply boundary automatically. Stop, show only eligible targets, and let the user choose whether to continue.

## Common readiness

- One Model per session.
- Mutation needs fresh required Snapshots, a task, and an ordered plan.
- Inputs must be `active`; `needs_review`, inactive, and deprecated records unlock nothing downstream.
- Fresh Model Snapshot `model_scope` flags are canonical: `is_bronze_source_eligible` means active scoped Bronze Profile/Analysis/Conceptual/Logical source; `is_dimensional_source_eligible` means active scoped Silver source with an active applied Logical Mapping contribution; `is_logical_mapping_target_eligible` means active scoped Silver target; `is_dimensional_mapping_target_eligible` means active scoped Gold target. Never infer eligibility from `zone_code` alone.
- Target Registration writes Metadata only. Mapping first needs the separate web-governed Model Scope path outside public MCP and this plugin. If its target flag is false/absent, wait: “Ask the authorized scope owner to add and apply this target to Model Scope, download a fresh Model Snapshot, replace `model/`, then resume this task.” Never mutate Model Scope through this plugin.
- A `needs_review` Mapping may be applied after explicit local override, but it does not unlock code generation or Dimensional work.
- A requested number defines input scope (for example, 40 Objects), never an output quota. Report supported design, splits, consolidations, exclusions, and blockers.

## Optional assertion preparation

Assertion capture is the one pre-process, non-target Model custom task, not a target/stage. Persist only user-supplied evidence via Model Change Set; stop after Apply. Assertions inform reasoning, especially Mapping, but never become executable lineage.

## Load only the active target

- Logical Build: `workflows/logical-build.md`
- Silver Target Registration: `workflows/target-registration.md` with route `silver`
- Logical Mapping: `workflows/mapping.md` with route `logical`
- Logical Code Generation: `workflows/code-generation.md` with route `logical`
- Dimensional Build: `workflows/dimensional-build.md`
- Gold Target Registration: `workflows/target-registration.md` with route `gold`
- Dimensional Mapping: `workflows/mapping.md` with route `dimensional`
- Dimensional Code Generation: `workflows/code-generation.md` with route `dimensional`
