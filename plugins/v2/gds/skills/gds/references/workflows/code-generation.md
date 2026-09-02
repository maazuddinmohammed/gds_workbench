# Logical or Dimensional Code Generation

Require active applied Mapping and Binding. Read them from the Model Snapshot with focused `read_model_section` calls. Generate complete code; never use removed specialized generator-document tools.

Before authoring code, present the proposed artifact/file names, whether source Systems are combined or separate, the SQL pattern, and a small representative preview; then wait for user confirmation. For a combined multi-System target, read `../examples/multi-system-target.sql` first and default the preview to one `CREATE OR REPLACE TEMPORARY VIEW` branch per System followed by one aligned `UNION ALL` final query. Confirm once for a shared layout, list exceptions, and reconfirm if the layout changes. This gate is required in every interaction mode.

Code Generation decides artifact/file grouping. Use the simple user-facing artifact or file name. For multiple source Systems:

- create separate SQL files when the user requests separate orchestration artifacts; or
- in one SQL file, create one isolated temporary-view branch per System and finish with one aligned `UNION ALL`.

Treat the example as structure only; every authored name and expression still comes from applied Mapping or user evidence.

The final query returns the exact target shape. Runtime performs loading/merge; generated code does not deploy, schedule, or run orchestration. Require complete joins, filters, expressions, dependency order, and natural-key behavior; unresolved executable logic blocks.

Preflight syntax only with governed `execute_databricks_sql` when useful and authorized. Default `environment_code` to lowercase `dev` unless the user explicitly requests another registered Environment. Empty results are acceptable before upstream loads. Store generated Code through a Model Change Set; server-generated digests must never be guessed or recomputed by the agent.
