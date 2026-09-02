# Validation Authoring

Validation is the name of this workflow; do not call it QA. Create `validation_group` and `validation_check` Model records for exact selected source Systems and targets.

Set the task boundary to Logical or Dimensional Validation before authoring. Do not mix layers implicitly in one task.

Use applied Mapping as required context and current relevant Code when it exists. Cover technical checks and functional/business Assertions. Each Check stores its SQL and assertion contract; it never stores execution results.

Query checks must follow the current dataset schema. Except for `executes_successfully`, scalar comparisons return exactly one row by one column with the declared result type. Other cardinality is a query-contract error, not an assertion failure. Fully qualify persistent relations; only temporary relations declared earlier in the same SQL batch may be unqualified.

Optional SQL Preflight is local and separate from Validation records. Syntax may be checked before data is loaded; no-result output is not a failure. Apply complete Groups/Checks through a Model Change Set and stop.
