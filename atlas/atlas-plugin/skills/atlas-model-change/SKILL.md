---
name: atlas-model-change
description: Safely coordinate a requested change to an existing Atlas model and its affected dependencies. Use for model modifications, impact analysis or updates spanning modeling, mapping and generated artifacts.
---

# Change an existing model safely

Own the requested difference and dependency review; use the relevant modeling skill for design. A broad change request is not permission to regenerate every artifact.

1. Follow [working context](../../references/working-method.md). Resolve the requested behavior and exact affected Model/Entities. If the request includes “why,” use [investigation](../atlas-investigate/SKILL.md) first and carry forward actual evidence and unknown history.
2. Inspect current applied records, pending edits, input bindings and authoritative freshness information with [focused reads](../../references/tools/reads.md). Read [record state](../../references/record-state.md) and [impact/update scope](../../references/methods/change-impact.md). Preserve protected records and existing manual decisions; a lock may block modification without blocking explanation.
3. Establish the before/after change: grain, identity, type, nullability, relationship, history or business rule. Trace real dependencies through source supports, neighboring relationships, Mapping target/System branches, Code assignments, Validation definitions and relevant registrations. Names and a changed Model revision do not prove dependency or staleness.
4. Classify definite effects, possible effects, reusable work and blocked/unknown dependencies. Missing references/history make the impact account incomplete; do not claim an exhaustive automated graph. Use the optional [impact format](../../templates/change-impact.md) in existing task evidence, not a second status ledger.
5. Follow explicit user scope. Explain necessary dependency consequences; ask only when a material addition or conflicting intent needs a decision. Do not bypass locks by renaming/recreating records. Metadata natural-key changes remain [manual corrections](../../references/metadata/editing.md#manual-natural-key-changes), not replacement-and-deactivation workarounds.
6. Enter the owning skill: [conceptual](../atlas-conceptual-model/SKILL.md), [logical](../atlas-logical-model/SKILL.md), [dimensional](../atlas-dimensional-model/SKILL.md), [mapping](../atlas-mapping/SKILL.md), [code](../atlas-code-generation/SKILL.md) or [metadata](../atlas-metadata/SKILL.md). Make and check one coherent change at a time. Keep required applied-input boundaries; pending upstream changes cannot be treated as applied inputs.
7. Run [verification](../atlas-verify/SKILL.md) on the changed records and relevant neighbors. Identify affected downstream artifacts requiring review; repair them only within authorized scope. Report unresolved/protected dependencies without marking them current.

Finish with the requested change, evidence, checks, preserved/affected scope and remaining prerequisites. Use the shared [Change Set lifecycle](../../references/change-set-lifecycle.md) for the complete related batch. After verified Apply, reconcile refreshed context and confirm saved results. Report drafted, validated and applied states accurately; intent or task text cannot authorize a retry of an uncertain Stage outcome.
