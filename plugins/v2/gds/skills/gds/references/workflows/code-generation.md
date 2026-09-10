# Logical or Dimensional Code Generation

Require active applied Mapping and Binding; follow `../session.md` for reads/revisions. Never use removed generator-document tools.

Before authoring code, present artifact/file names, combined/separate source Systems, SQL pattern and a small representative preview; wait for user confirmation. Read `../examples/staged-target-query.sql`; combined multi-System targets also require `../examples/multi-system-target.sql`. Confirm once per shared layout, list exceptions and reconfirm if the layout changes. Existing explicit acknowledgement satisfies this gate in every interaction mode.

Code Generation decides artifact/file grouping. Use simple file names. Separate files when requested; otherwise use isolated temporary-view branches in one file. An aligned `UNION ALL` requires Mapping's disjoint target keys. Otherwise implement its evidenced identity reconciliation. Separate files also require a cross-System collision policy. Never invent `DISTINCT`, System precedence, prior-target fallbacks, lookups or parameters. Examples establish structure, not business rules.

Generated SQL contains code only: no prose, Markdown or comments. Reference comments are teaching notes; keep explanations outside artifacts.

Each transformation artifact is one target's ordered SQL batch:

1. Translate meaningful Object steps into successive `CREATE OR REPLACE TEMPORARY VIEW` statements. Each view implements its own preparation, join/filter or projection step; later stages reuse earlier views. Never repeat the entire pipeline or full source query in every statement/artifact, or include unrelated targets. A simple Mapping needs only one temporary view and final SELECT.
2. Keep temporary names unqualified, target/System-specific and unique within the batch. Declare before use in that batch; never depend on another artifact/session. Carry only needed join/transformation columns forward.
3. Apply Attribute Mapping expressions at the appropriate stage. Project explicit SQL-populated target columns in bound order according to `../orchestration-rules.md`; omit the own generated surrogate and framework audit columns; no `SELECT *`. Align System branches by alias/type. Preserve leading-zero identifiers, exact decimals, nullability/timezones and specified invalid-value behavior; do not silently convert failures to null.
4. Finish with one target-column SELECT from prepared views. The final query returns the exact runtime input shape. Runtime performs loading/merge; do not emit persistent target DDL, INSERT/MERGE/UPDATE/DELETE, deployment or orchestration. Preserve artifact schema and approved file grouping.

Unresolved or contradictory Mapping blocks the target. Report the gap, correct Mapping through governed Apply, refresh and resume. Never redesign Mapping inside SQL or invent missing joins, grain, filters or keys. Resolve conflicting guide requirements explicitly.

Reuse unchanged artifacts and update only affected work. Before local validation, review actual SQL statement by statement: trace Object step → view → downstream reference and Attribute rule → target column. Check grain, join cardinality, filter placement, conversions, nulls, aggregation/reconciliation and dependency order. Reject repeated whole-query stages, missing prerequisites, unresolved placeholders and absent references. Every active Mapping System needs exactly one active artifact assignment. Describe unverified assumptions; schema/syntax passes do not prove functional correctness.

Static review is default. Optional `execute_databricks_sql` preflight follows saved SQL policy/current authorization; resolve specific gaps without repeating unchanged checks. Use lowercase `dev` unless another registered Environment was requested. Empty results prove no business outcome. Never create Validation records or start Validation Authoring automatically. Store Code through a Model Change Set; never guess/recompute server digests.

After Apply, ask what to do next unless the journey already specifies it. Validation can follow Logical code directly; Dimensional work is optional.
