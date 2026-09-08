# Automatic journey

Ask once for missing session, target/scope, output choices, SQL policy, and subagent policy. Infer supplied answers. Logical Build includes Profiling, Analysis, Conceptual, and Logical.

Before any subagent, read `status.subagent_policy`. If null, ask the user to choose:

1. **Inherit current model** (default): omit VS Code's subagent `model` argument.
2. **Disable subagents**: use only the main agent.
3. **Fixed model**: use the exact user-supplied VS Code model name.

Persist with `subagent-policy`. Never infer a fixed model, raise cost, substitute, or silently fall back. If unavailable/refused, ask again. Reuse until the user changes it or materially different work requires a new choice.

Queue requested targets by dependency. Work one at a time using supported decisions, complete records, and coverage loops.

When requested, run Metadata Enrichment after Input Scope Apply and before dependent modeling; use its physical Metadata Change Set, then refresh Metadata before continuing.

When a target is complete:

1. Validate the effective graph; review only when the user requests actions.
2. Notify the user to Refresh the already-open Workbench.
3. Treat a clear positive acknowledgement as acceptance of the exact digest.
4. Follow `server-handoff.md` and `staging.md` for revision recovery, draft-cache binding, Stage, bounded proof, and server validation. Do not abbreviate this sequence or create dependent drafts early.
5. Ask separately before Apply.
6. Apply once and stop. Install the required fresh Snapshot; leave dependent work queued.

Never cross Input Scope→modeling, Metadata→Binding, or Binding→Mapping until prerequisite Apply and fresh Snapshot succeed.
