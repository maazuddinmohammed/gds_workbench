# QA

QA covers 1..1000 exact nonempty pipeline/source System codes, case-insensitively unique. Never
broaden or infer them.

Each System needs active applied Mapping. Code may be absent; when current relevant active `generated_code` exists, QA must use it. Read exact `qa_authoring_context`; copy both derived
digests into every `validation_group` and never recompute either digest. Its references are the
authoritative allowlist: join Code by complete target key, modeled type, artifact type, and digest;
ignore every unreferenced or stale artifact. Empty references/null Code digest means Mapping-only.
The context is Snapshot-only and must never be staged.

Before writing, load all QA authoring and output dataset contracts.

Follow each Snapshot schema's assertion contract when constructing one or more complete
`validation_group` parents and their `validation_check` children.

Each Check stores Query A, optional query-operand Query B, and one schema assertion.
`executes_successfully` requires null result type/Query B/value and operand `none`; completion passes
even without rows. Other operators obey declared types: Query A and query-valued Query B each end
with exactly one row by one column, interpreted as `validation_result_data_type`. Other cardinality
is a query-contract execution error, not an assertion failure. Authoring checks shape; the future
runner checks cardinality. QA SQL permits reads and temporary-object DDL. Every physical relation
must be `catalog.schema.table`; only a temporary relation declared earlier in the same SQL batch may
be unqualified. Apply never runs it. An alternate engine requires explicit schema/orchestrator
support; otherwise block.

When policy permits, sample only through existing `execute_databricks_sql`; combine bounded reads.
A declined/failed sample never blocks authoring.

Use stable names. Stage a new parent with children or reference the same applied Tenant/System/name.
Write complete `is_active=false` records for intended deactivation; omission is unchanged. Stage
after Mapping and relevant Code Apply, follow Model gates, and stop after Apply.
