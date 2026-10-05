# Working context

Use this shared entry contract once per task, including direct skill entry. Load only the selected workflow and the references needed for its next decision. Reading another skill changes instructions in the same conversation; it is not a portable skill-call API.

## Initialize or resume

1. Identify the requested outcome before setup. General Atlas explanations and supplied-code discussion need no Tenant, Model, workspace or Workbench.
2. Resolve verified Tenant and Model identity only when records are needed, using [available reads](tools/initialization.md). Reuse explicit or valid saved selections; ask only for missing or ambiguous identity.
3. For local work, resolve an absolute directory. Reuse the saved directory; otherwise announce and use the actual current directory. An invalid supplied path needs correction. Preserve existing drafts and bindings. A different primary Tenant or Model needs a separate directory.
4. Inspect the active task and relevant unfinished work. Follow clear intent; ask about resuming only when it is ambiguous. Create one task per meaningful authoring outcome, not per tool call. Use [state and evidence](platform/state.md) for bindings and refresh decisions.
5. Resolve SQL policy/environment only when evidence execution is relevant. Never prohibits execution; Essential resolves blocking gaps; Proactive permits useful investigation within authorized scope. All queries follow [query scope](query-scope.md). Preparing SQL does not execute it or authorize execution.
6. Open/reuse Workbench when local authoring or review needs it, or when requested; use the [verified launcher](tools/initialization.md). A read-only explanation needs no browser setup.

Use the [interview method](modeling-interview.md#interaction-mode) for requested Grill Me discussion or consequential unresolved decisions. Otherwise explain and work through coherent parts without a mode-selection questionnaire. Load [delegation policy](tools/delegation.md) only before useful, authorized delegation.

Before authoring, read [record state](record-state.md) and [governance](platform/governance.md). Existing-output changes use [impact and update scope](methods/change-impact.md). Backend authorization remains authoritative. Missing capabilities follow the [capability boundaries](platform/capabilities.md); never invent a tool or substitute a different record meaning.
