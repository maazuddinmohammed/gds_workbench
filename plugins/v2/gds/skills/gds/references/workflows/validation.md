# Validation Authoring

Validation is the name of this workflow; do not call it QA. Create `validation_group` and `validation_check` Model records for exact selected source Systems and targets.

Enter this workflow only when Validation Authoring is selected or explicitly included in the agreed journey; ordinary Mapping/Code review does not create Validation records. Set the task boundary to Logical or Dimensional Validation before authoring. Do not mix layers implicitly in one task.

Before authoring Groups or Checks, present the selected Systems/targets and a broad validation coverage plan, then wait for user confirmation. Propose only applicable categories:

- **Technical** — execution, required columns/types, nullability, keys, uniqueness, and referential integrity.
- **Reconciliation** — source-to-target counts, control totals, mapping coverage, and transformation consistency.
- **Functional/business** — confirmed Assertions, domain rules, and expected business outcomes.

Give representative examples, not every final query. Identify excluded categories or known evidence gaps. One confirmation may cover the complete selected boundary; a material coverage change requires confirmation again. An existing explicit acknowledgement of this coverage satisfies the gate; do not ask again. This gate is required in every interaction mode.

Use applied Mapping as required context and current relevant Code when it exists. Read frozen Snapshot records with bounded local `select`; `read_model_section` reads live applied records, requiring refresh/reassessment if the revision changed. Generated Code and Validation are Snapshot-only. Cover applicable technical checks and confirmed functional/business Assertions. Each Check stores its SQL and assertion contract; it never stores execution results. Resolve contradictory Mapping before deriving checks from it.

Derive expected results independently from Mapping and confirmed rules, not by copying generated SQL. Check failed conversions, unintended join multiplication, lost keys, and precision loss when applicable. Use identical scope, batch, and filter boundaries for comparisons. Define empty-input and null behavior explicitly; never assume empty input passes. A permitted syntax preflight is not proof that a business assertion passed.

Query checks must follow the current dataset schema. Except for `executes_successfully`, scalar comparisons return exactly one row by one column with the declared result type. Other cardinality is a query-contract error, not an assertion failure. Fully qualify persistent relations; only temporary relations declared earlier in the same SQL batch may be unqualified.

Review each actual check statically before local validation: trace its independent expected value, scope, null behavior and failure condition. Reject constant passing checks and assertions unsupported by evidence.

Optional SQL Preflight is separate from Validation records. Governed `execute_databricks_sql` performs external execution; obey saved SQL policy and current authorization, using it only to resolve a specific uncertainty. Do not repeat unchanged checks routinely. Syntax may be checked before data is loaded; no-result output is not a failure of syntax or evidence that an assertion passed. Report the distinction. Apply complete Groups/Checks through a Model Change Set and stop.
