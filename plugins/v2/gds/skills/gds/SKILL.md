---
name: gds
description: Govern GDS metadata, models, bindings, mappings, code, and validations from signed Snapshots and Change Sets. Use for GDS Workbench sessions, inspection, workflows, or Grill With Docs design.
---

# GDS router

Reads need no session; writes do. Read-only reviews use relevant guides/evidence without setup/writes; cross-layer reviews may load several guides. Plugin owns lifecycle within server constraints.

## Authoring: start or resume

1. Infer the goal and mode; ask only unresolved decisions. Read `references/workflow-targets.md` and only the active guide. Guided also reads `references/guided-journey.md`; Custom gets plan approval before execution.
2. Read `references/session.md` and `references/local-helper.md`. Create/resume the Tenant session and optional Model; reuse known paths. Open Workbench only when the session is first created or the user asks.
3. At Guided entry, ask/persist SQL policy once: `never` uses existing evidence; `essential` resolves a blocking gap; `as_needed` permits useful bounded queries. Install Metadata and, when a Model is selected, Model Snapshots before choosing the next workflow.
4. Run local `readiness` once for a known target without first running the local helper's `inspect` command. Install missing/stale Snapshots, then rerun. Use bounded Snapshot `select`; `inspect_metadata`/`read_model_section` read live data. See `references/session.md`; never load a complete Snapshot into context.
5. Before local authoring, read `references/change-sets.md` and applicable [orchestration rules](references/orchestration-rules.md). Request compact dataset schemas with `describe_metadata_dataset` or `describe_model_dataset`; use helper command contracts for exact flags.

Trust MCP tool schemas dynamically. There is no packaged server-contract hash preflight. Never use removed specialized Mapping or Code context tools.

For `execute_databricks_sql`, default `environment_code` to lowercase `dev` unless another registered Environment is explicitly requested.

Metadata Enrichment selects Model inputs but updates physical Metadata; load its dedicated guide.


## Interaction modes

- **Guided**: enter the selected orchestrated workflow; reuse answers and advance through approved prerequisites.
- **Custom**: clarify the goal, ask focused questions, propose a plan, obtain approval, then execute with existing tools/workflows.
- **Grill With Docs**: deeper investigation and questioning; read `references/grill-with-docs.md`. Finish with an approved plan and execute through appropriate workflows.

Full covers every eligible input. Selected covers only named eligible inputs. A requested count is never an output quota.

## User-visible lifecycle

1. Author complete local records; keep supported records `active`. Reconcile the actual result using the functional review in `references/change-sets.md`.
2. Run `validate` on the effective graph before notifying the user. Do not run `review` unless the user asks for an action summary. When valid, say it is ready and ask them to Refresh Workbench.
3. Any unambiguous positive acknowledgement of the presented result accepts the exact current digest and authorizes an ordinary free Tenant Lock, Stage, and server validation. Design-question answers do not. Never ask separately for review acceptance and handoff approval.
4. Check the Tenant Lock. If another Principal owns it, stop. Lock override always requires separate explicit authorization and a reason; the acknowledgement authorizes ordinary acquisition only when the Tenant is unlocked.
5. Compare Model revision; if changed, use `references/workflows/revision-recovery.md`. Metadata has no tenant-wide revision: require a non-stale Snapshot, Tenant Lock, and server validation. Keep acknowledgement only when reassessed content is byte-identical.
6. Follow `references/server-handoff.md` and `references/staging.md`: bind the draft cache, run `prepare-stage-request`, then `gds_stageApprovedManifest` with path/digest only. Never read Stage payloads or server pending rows. Show authoritative actions; ask separately for Apply approval.
7. Apply once, mark its Snapshot stale, release a lock acquired here, and refresh before dependent work.

DBML is a display export, not validation or review evidence. Never generate, regenerate, read, or inspect DBML unless the user explicitly asks.

## References

- Workbench: `references/workbench.md`
- Targets and platform: `references/workflow-targets.md`, `references/platform-lifecycle.md`
- Active authoring guide: `references/workflows/`
