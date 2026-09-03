---
name: gds
description: Govern GDS metadata, models, bindings, mappings, code, and validations from signed Snapshots and Change Sets. Use for GDS Workbench sessions, inspection, workflows, or Grill With Docs design.
---

# GDS router

Answer reads directly. Writes require a session.
Plugin owns interaction and lifecycle; server instructions only constrain operations.

## Start or resume

1. Read `references/session.md`. Create or resume one Tenant-bound session and optional Model. Ask for the directory only when unknown.
2. Open Workbench only when the session is first created or the user asks. Later results need only Refresh.
3. Infer mode, target, and Full/Selected scope; ask only decisions that change the result. Read `references/workflow-targets.md` and only the active guide. For Automatic, also read `references/automatic-journey.md`.
4. For targets that may query, set SQL policy: `never` uses existing evidence; `essential` queries a blocking gap; `as_needed` permits useful bounded queries. Ask once and persist it.
5. Run local `readiness` once for a known target without first running the local helper's `inspect` command. Install missing/stale Snapshots per `session.md`, then rerun. Use focused MCP `inspect_metadata` or `read_model_section`; never load a complete Snapshot into context.
6. Before the first local write, read `references/change-sets.md` and `references/local-helper.md`, then request the compact dataset schema with `describe_metadata_dataset` or `describe_model_dataset`.

Trust MCP tool schemas dynamically. There is no packaged server-contract hash preflight. Never use removed specialized Mapping or Code context tools.

For every `execute_databricks_sql` call, default `environment_code` to lowercase `dev` unless the user explicitly requests another registered Environment.

## Interaction modes

- **Quick**: bounded explanation, inspection, or small change. Mutations keep normal governance.
- **Guided**: pause at useful user decisions.
- **Automatic**: make supportable decisions and finish the current target without optional pauses. Required governance remains.
- **Custom**: follow an explicitly requested exception while preserving governance.
- **Grill With Docs**: deep collaborative exploration, not a Workflow Target. Read `references/grill-with-docs.md` only when requested.

Full covers every eligible input. Selected covers only named eligible inputs. A requested count is never an output quota.

## User-visible lifecycle

1. Author complete local records with coverage loops; keep supported records `active`.
2. Run `validate` on the effective graph before notifying the user. Do not run `review` unless the user asks for an action summary. When valid, say it is ready and ask them to Refresh Workbench.
3. Any unambiguous positive acknowledgement—“proceed”, “OK”, or “looks good”—accepts the exact current digest and authorizes an ordinary free Tenant Lock, reconciliation, Stage, and server validation. Never ask separately for review acceptance and handoff approval.
4. Check the Tenant Lock. If another Principal owns it, stop. Lock override always requires separate explicit authorization and a reason; the acknowledgement authorizes ordinary acquisition only when the Tenant is unlocked.
5. Before reconciliation, compare the authoritative Model revision for Model work. If it changed, refresh the Model Snapshot and reassess. Metadata has no tenant-wide revision: require its local Snapshot to be non-stale, then rely on the Tenant Lock and server validation; never invent a Metadata revision. Keep the acknowledgement only when local content is byte-identical after reassessment.
6. After reconciliation, read `references/staging.md`; run `prepare-stage` once and execute its ordered `operations` exactly. After server validation, show the authoritative actions and ask separately for Apply approval.
7. Apply once, mark that Snapshot area stale, release a lock acquired here, and automatically refresh the written area before any dependent target.

DBML is a display export, not validation or review evidence. Never generate, regenerate, read, or inspect DBML unless the user explicitly asks.

## References

- Session and lifecycle: `references/session.md`, `references/workbench.md`, `references/server-handoff.md`
- Targets and platform: `references/workflow-targets.md`, `references/platform-lifecycle.md`
- Local records: `references/change-sets.md`, `references/local-helper.md`; Stage only: `references/staging.md`
- Active authoring guide: `references/workflows/`
