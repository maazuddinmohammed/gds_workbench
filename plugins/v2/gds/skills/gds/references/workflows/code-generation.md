# Logical or Dimensional Code Generation

Require active applied Mapping and Binding. Read them from the Model Snapshot with focused `read_model_section` calls. Generate complete code; never use removed specialized generator-document tools.

Code Generation decides artifact/file grouping. Use the simple user-facing artifact or file name. For multiple source Systems:

- create separate SQL files when the user requests separate orchestration artifacts; or
- in one SQL file, create one isolated temporary-view branch per System and finish with one aligned `UNION ALL`.

For a combined multi-System SQL artifact, read `../examples/multi-system-target.sql` for the required branch-and-final-query layout. Treat it as structure only; every name and expression still comes from applied Mapping or user evidence.

The final query returns the exact target shape. Runtime performs loading/merge; generated code does not deploy, schedule, or run orchestration. Require complete joins, filters, expressions, dependency order, and natural-key behavior; unresolved executable logic blocks.

Preflight syntax only with governed `execute_databricks_sql` when useful and authorized. Default `environment_code` to lowercase `dev` unless the user explicitly requests another registered Environment. Empty results are acceptable before upstream loads. Store generated Code through a Model Change Set; server-generated digests must never be guessed or recomputed by the agent.
