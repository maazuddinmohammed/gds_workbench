# Logical or Dimensional Code Generation

Require active applied Mapping and Binding. Read the installed Model Snapshot with bounded local `select`; `read_model_section` reads live applied state. Refresh/reassess a changed revision before using it. Generate complete code; never use removed specialized generator-document tools.

Before authoring code, present the proposed artifact/file names, whether source Systems are combined or separate, the SQL pattern, and a small representative preview; then wait for user confirmation. For a combined multi-System target, read `../examples/multi-system-target.sql` first. Confirm once for a shared layout, list exceptions, and reconfirm if the layout changes. An existing explicit acknowledgement of this layout satisfies the gate; do not ask again. This gate is required in every interaction mode.

Code Generation decides artifact/file grouping. Use the simple user-facing artifact or file name. For multiple source Systems:

- create separate SQL files when the user requests separate orchestration artifacts; or
- use isolated temporary-view branches in one file. An aligned `UNION ALL` may be the final query only when Mapping establishes disjoint target keys. Otherwise implement Mapping's supported identity reconciliation after combining branches, preserving the target grain.

Separate files also need Mapping's cross-System collision policy. Never add `DISTINCT`, a preferred System, prior-target values, lookups or runtime parameters to repair missing decisions. Treat the example as structure only; every authored name and expression still comes from applied Mapping or user evidence.

The final query returns the exact target shape. Runtime performs loading/merge; generated code does not deploy, schedule, or run orchestration. Require complete joins, filters, expressions, dependency order, and natural-key behavior. Unresolved or contradictory Mapping blocks code for the affected target: report the exact gap, return to Mapping for correction and governed Apply, refresh, then resume. Do not redesign applied Mapping inside SQL.

Project explicit target columns in bound order; no `SELECT *`. Align every System branch by alias and target type. Implement Mapping's casts and invalid-value policy without silently replacing failures with nulls. Preserve leading-zero identifiers, exact decimals, nullability, and timezone decisions. Reject unresolved placeholders and references absent from applied context. Check every active Mapping System has exactly one active artifact assignment.

Before local validation, review the actual SQL statement by statement against applied Mapping. Resolve aliases and columns, trace every target expression, and check grain, join cardinality, filter placement, nulls, conversions, aggregation, reconciliation and final column order. Describe any unverified assumption; a schema pass or plausible-looking query does not prove functional correctness.

Use static review by default. Optional preflight through governed `execute_databricks_sql` is external execution: obey the saved SQL policy and current authorization, query only to resolve a specific uncertainty, and avoid repeated tests without a changed query or new concern. Default `environment_code` to lowercase `dev` unless the user explicitly requests another registered Environment. Empty results are acceptable before upstream loads but prove no business outcome. Do not create Validation records or start Validation Authoring automatically. Store generated Code through a Model Change Set; server-generated digests must never be guessed or recomputed by the agent.
