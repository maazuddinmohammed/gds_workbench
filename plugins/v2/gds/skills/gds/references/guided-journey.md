# Guided journey

Reuse clear intent; otherwise show the three modes or relevant Workflow Targets. At entry resolve missing session/Tenant/Model context, select `sql-policy` once, open Workbench once, and install Metadata plus the selected Model Snapshot using `session.md`. Metadata-only work needs no Model. Then resolve the next target and scope.

Read only its guide. State the missing human decision, reuse its answer throughout the journey, and proceed with supported work. Queue prerequisites without silently broadening scope. Custom follows an approved goal-specific plan; Grill With Docs develops that plan more thoroughly.

Logical Build invokes Metadata Enrichment for missing descriptions/types before Profiling. Dimensional Build also checks required enrichment, using upstream registered lineage for Silver evidence rather than treating Silver as Source/Bronze input. Reuse completed enrichment and saved description policy; Apply physical Metadata and refresh before dependent modeling. Enrichment has its own Metadata boundary, not a mixed Model draft.

For existing models, resolve additions, refinement, or requested rebuild once. Reuse unaffected Analysis, Conceptual, Logical, Dimensional, Mapping, Code, and Validation results. Preserve locks and inspect downstream impacts.

After each complete draft, follow the router lifecycle: functional review, local validation, Workbench Refresh, acknowledgement, governed Stage/server validation, separate Apply approval, then fresh Snapshot. Resume queued work only after its prerequisites are applied. Never cross Input Scope→modeling, Metadata→Binding, or Binding→Mapping early.

After Code Generation ask what the user wants next unless already specified: Validation, optional Dimensional work, Process Registration, another applicable workflow, or finish. Logical alone is a valid outcome. Validation can cover Silver, Gold, or both; never start it just because code review finished.

## Optional delegation

Only delegate when authorized and useful. Read `status.subagent_policy` first. If absent, resolve and persist the user's choice: **Inherit current model** (omit a model override), **Disable subagents**, or **Fixed model** (exact user-supplied name). Never infer a fixed model, substitute, or silently fall back. If unavailable, ask for a revised choice. Delegation does not change Stage, lock, or Apply boundaries.
