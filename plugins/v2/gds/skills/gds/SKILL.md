---
name: gds
description: Govern GDS metadata, models, bindings, mappings, code, and validations from signed Snapshots and Change Sets. Use for GDS Workbench sessions, inspection, workflows, or Grill With Docs design.
---

# GDS router

Reads need no session; writes do. Read-only reviews use relevant guides and supplied evidence without setup/writes; cross-layer review may load several guides. Plugin owns lifecycle; server instructions constrain operations.

## Authoring: start or resume

1. Read `references/session.md`. Create/resume one Tenant session and optional Model; ask for the directory only when unknown.
2. Open Workbench only when the session is first created or the user asks. Later results need only Refresh.
3. Infer mode, target, and Full/Selected scope; ask only decisions that change the result. Read `references/workflow-targets.md` and only the active guide. For Automatic, also read `references/automatic-journey.md`.
4. In Automatic mode, follow `automatic-journey.md`: require and persist the user's policy before any subagent; never choose or substitute its model.
5. For query targets, ask/persist SQL policy once: `never` uses existing evidence; `essential` resolves a blocking gap; `as_needed` permits useful bounded queries.
6. Run local `readiness` once for a known target without first running the local helper's `inspect` command. Install missing/stale Snapshots, then rerun. Use bounded Snapshot `select`; `inspect_metadata`/`read_model_section` read live data. See `references/session.md`; never load a complete Snapshot into context.
7. Before the first local write, read `references/change-sets.md` and `references/local-helper.md`, then request the compact dataset schema with `describe_metadata_dataset` or `describe_model_dataset`.

Trust MCP tool schemas dynamically. There is no packaged server-contract hash preflight. Never use removed specialized Mapping or Code context tools.

For every `execute_databricks_sql` call, default `environment_code` to lowercase `dev` unless the user explicitly requests another registered Environment.

Metadata Enrichment selects Model inputs but updates physical Metadata; load its dedicated guide.

## Interaction modes

- **Quick**: bounded explanation, inspection, or small governed change.
- **Guided**: pause at useful decisions.
- **Automatic**: finish the target without optional pauses; preserve governance.
- **Custom**: follow a bounded requested exception.
- **Grill With Docs**: deep collaborative exploration, not a Workflow Target. Read `references/grill-with-docs.md` only when requested.

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
