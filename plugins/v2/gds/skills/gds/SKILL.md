---
name: gds
description: Govern GDS metadata, models, bindings, mappings, code, and validations from signed Snapshots and Change Sets. Use for GDS Workbench sessions, inspection, workflows, or Grill With Docs design.
---

# GDS router

Reads need no session; writes do. Read-only reviews use relevant evidence without setup or writes; cross-layer reviews may load several guides. Server constraints remain authoritative.

## Authoring: start or resume

1. Infer goal/mode; ask unresolved decisions only. Read `references/workflow-targets.md` and only the active guide. Guided also reads `references/guided-journey.md`; Custom gets plan approval.
2. Read `references/session.md` and `references/local-helper.md`. Create/resume the Tenant session and optional Model; reuse paths. Open Workbench only when the session is first created or the user asks.
3. At Guided entry, persist SQL policy once: `never` uses existing evidence; `essential` resolves blocking gaps; `as_needed` permits useful bounded queries. Install Metadata and the selected Model Snapshot before choosing work.
4. Run local `readiness` once for a known target without first running the local helper's `inspect` command. Install missing/stale Snapshots, then rerun. Use bounded `select`; `inspect_metadata`/`read_model_section` read live data. Follow session revision rules; never load a complete Snapshot into context.
5. Before authoring, read `references/change-sets.md` and applicable [orchestration rules](references/orchestration-rules.md). Request compact schemas with `describe_metadata_dataset`/`describe_model_dataset`; discover helper flags through command contracts.

Trust MCP schemas dynamically. There is no packaged server-contract hash preflight. Never use removed specialized Mapping/Code context tools. For `execute_databricks_sql`, default `environment_code` to lowercase `dev` unless another registered Environment is requested.

Metadata Enrichment selects Model inputs but updates physical Metadata; load its guide.

## Interaction modes

- **Guided**: follow the selected workflow and approved prerequisites; reuse answers.
- **Custom**: clarify the goal, approve a focused plan, then execute.
- **Grill With Docs**: investigate and question through `references/grill-with-docs.md`; execute the approved plan.

Full considers every eligible input; Selected covers named inputs. Counts are never output quotas.

## User-visible lifecycle

1. Author complete records; supported results stay `active`. Functionally review the actual result using `references/change-sets.md`.
2. Run `validate` on the effective graph. Do not run `review` unless the user asks for an action summary. Separate structural validity from modeling evidence and unresolved decisions; follow `references/modeling-quality.md` when `validate` returns `quality`. Ask them to Refresh Workbench after affected decisions are supported.
3. Any unambiguous positive acknowledgement of the presented result accepts the exact current digest and authorizes an ordinary free Tenant Lock, Stage, and server validation. Design-question answers do not. Never ask separately for review acceptance and handoff approval.
4. Discover Tenant Lock operations and check ownership. Another Principal's lock stops handoff; override requires separate explicit authorization and a reason. Acknowledgement authorizes ordinary unlocked-Tenant acquisition.
5. Compare Model revision; changes require `references/workflows/revision-recovery.md`. Metadata has no tenant-wide revision: require Snapshot freshness, lock and server validation. Retain acknowledgement only for byte-identical reassessed content.
6. Follow `references/server-handoff.md` and `references/staging.md`: bind draft cache, run `prepare-stage-request`, then `gds_stageApprovedManifest` with path/digest only. Never read Stage payloads or pending server rows. Show authoritative actions; ask separately for Apply approval.
7. Apply once, mark Snapshot stale, release a lock acquired here, and refresh before dependent work.

DBML is a display export, not validation or review evidence. Never generate, regenerate, read, or inspect DBML unless the user explicitly asks.

Workbench: `references/workbench.md`. Platform boundaries: `references/platform-lifecycle.md`.
