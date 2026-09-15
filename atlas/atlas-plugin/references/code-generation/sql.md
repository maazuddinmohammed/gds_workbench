# SQL transformation generation

Shared by Code Generation and its later review/Validation. The [Code Generation skill](../../skills/atlas-code-generation/SKILL.md) owns intake and sequence; [Code records](../model/generated-code.md) owns payloads/assignments; [Mapping documents](../model/mapping-documents.md) owns transformation intent and the complete consumer context. This guide owns SQL file structure and translation checks.

## Translate Mapping without redesigning it

1. Read one complete target Mapping view, including all assigned Systems, actual input/lookup metadata and ordered target columns. No extra modeling traversal should be required. Resolve missing context before generating the affected target.
2. Translate substantial Object steps into successive `CREATE OR REPLACE TEMPORARY VIEW` statements. Each stage implements preparation, joins/filters or projection and consumes earlier results where needed. A simple direct branch needs only one view and a final SELECT; do not create a view per sentence or repeat the full pipeline in every stage.
3. Use unique unqualified temporary names including target/System context as needed. Declare every temporary dependency before use in the same artifact. Carry all needed later join/expression columns forward; drop unnecessary intermediates from the final result.
4. Apply Attribute Mapping expressions at their specified stage. Use resolved SQL source names and exact physical target aliases; modeled names may differ. Preserve identifiers, decimal capacity, timezone, nullability and invalid-value behavior. Do not add DISTINCT, TRY_CAST, rounding, COALESCE, deduplication or defaults unless Mapping requires them.
5. Finish with one explicit target-column SELECT. Use the exact mapped column order through `SourceSystemID`; omit the own generated surrogate, nine framework audit fields and applicable framework-populated Type 2 fields per the [population contract](../model/keys-and-audit.md#population-boundary-and-implementation-alignment). Supply mapped natural-key values, foreign keys and optional Source audit fields. Do not generate history-maintenance SQL. No final `SELECT *`.

Framework SQL uses resolved `schema.table` references, with the catalog supplied by runtime. Quote physical identifiers correctly using Databricks syntax; temporary views remain unqualified. Preserve cross-placement requirements and reject unsupported access rather than silently redirecting a source. Governed evidence queries use their separate registered coordinates.

The transformation returns rows. It contains no persistent CREATE/ALTER, INSERT/MERGE/UPDATE/DELETE, loading operation or deployment command. Metadata registration supplies DDL separately; the framework owns target writes.

SQL artifacts contain code only, without Markdown, prose or explanatory comments. Keep rationale and validation findings in the review/task. Teaching explanations below are not content to copy into output files.

## Combined or separate Systems

| Chosen layout | Generation rule |
|---|---|
| One file per target | Build isolated System branches in the file. Align physical aliases, types and order. Combine only according to Mapping's disjoint-key or explicit reconciliation policy; final result is for one target. |
| Separate System/target files | Each file includes its own preparation and final projection. Assign each mapped System exactly once. No cross-file temporary state; the mapped collision/dependency policy must still work with separate executions. |

Distinct source files do not make overlapping identities safe. A rule needing joint System comparison cannot be replaced by separate unrelated SELECTs. Do not duplicate the same System into two active artifacts or create an extra active reconciliation/helper artifact without a supported assignment/consumer contract. Code record assignments, not filenames, identify contributing Systems.

Mapping carries System/Object dependency orders; no new order property belongs on Code records. Use those orders when assessing grouping and later Process handoff. An earlier target's persisted lookup is different from a temporary result in another artifact.

## Runtime parameters and optional preflight

Use only Mapping's confirmed runtime parameters and population rules. The existing batch placeholder example is `wid_GDSBatchID`; it is not a universal required filter. Keep production placeholders in generated content. Never substitute profiling batch selections, create an automatic latest-batch rule or filter an entire historical lookup merely because it has a batch column.

Static review is the default. If a permitted execution probe is useful, follow [query scope](../query-scope.md): authorized Connection/environment, actual evidence coordinates, masking, approved row/batch scope, bounds and exact evidence recording. Keep concrete test substitutions and diagnostic queries separate from the production artifact; describe any scope difference. SQL Never permits generation and static review, not execution.

Each `execute_databricks_sql` call has independent temporary state and bounded statements/text/results. Do not split a view chain across calls or append independent final queries expecting multiple result sets. Use a self-contained bounded probe, or report that the artifact cannot be preflighted under the current tool limits. Do not weaken Mapping or truncate production SQL to fit. Prefer aggregates for evidence; never persist raw rows or claim that a successful/empty sample proves correctness.

## Staged example

Fictional Mapping: posted Order Lines, grain `(OrderID, LineNumber)`. Posted headers are unique by source System/order code; the Silver Order lookup has exactly one match on `(SourceSystemID, OrderCode)`. LineNumber is a significant STRING identifier. Quantity is a valid whole number; price and resulting amount fit DECIMAL(18,2). SourceSystemID values are valid, non-null BIGINT. No batch filtering or deduplication applies; the generated OrderLineID and framework fields are omitted.

```sql
CREATE OR REPLACE TEMPORARY VIEW temp_order_line_erp_posted AS
SELECT h.order_code, h.source_system_id
FROM `bronze`.`order_headers` AS h
WHERE h.status = 'posted';

CREATE OR REPLACE TEMPORARY VIEW temp_order_line_erp_joined AS
SELECT o.OrderID, l.line_number, l.quantity, l.unit_price,
       h.source_system_id AS SourceSystemID
FROM `bronze`.`order_lines` AS l
INNER JOIN temp_order_line_erp_posted AS h
  ON l.order_code = h.order_code
 AND l.source_system_id = h.source_system_id
INNER JOIN `silver`.`Order` AS o
  ON o.OrderCode = h.order_code
 AND o.SourceSystemID = h.source_system_id;

CREATE OR REPLACE TEMPORARY VIEW temp_order_line_erp_projected AS
SELECT j.OrderID,
       j.line_number AS LineNumber,
       CAST(CAST(j.quantity AS BIGINT) * CAST(j.unit_price AS DECIMAL(18,2)) AS DECIMAL(18,2)) AS Amount,
       j.SourceSystemID
FROM temp_order_line_erp_joined AS j;

SELECT OrderID, LineNumber, Amount, SourceSystemID
FROM temp_order_line_erp_projected;
```

This demonstrates read/preparation → joins → field projection → final output. The actual Mapping determines predicates, joins and type rules; none of these business choices is a default for other targets.

## Local content checks

| Rule | Check / reason |
|---|---|
| `code.mapping-input` | Complete applied Mapping context and correct revision; no unresolved transformation assumptions or missing lookup metadata. |
| `code.statements` | Parse as Databricks SQL; only the agreed temporary-view preparation and final query. No persistent writes/DDL, prose or repeated complete pipelines. |
| `code.stage-flow` | Temporary names are unique/unqualified, declared before use and self-contained; later stages receive needed columns. |
| `code.translation` | Every Mapping step and Attribute rule is implemented at the right stage, preserving join/filter semantics, grain, keys and value behavior. |
| `code.projection` | Final names/types/order match Mapping; SourceSystemID last, own surrogate/framework columns omitted, mapped FKs retained. |
| `code.systems` | Chosen grouping implements mapped cross-System policy; each mapped System has exactly one active artifact assignment. |
| `code.parameters` | Only confirmed runtime placeholders; production content contains no profiling/test batch substitutions. |
| `code.content-sync` | Local file text equals the generated_code_content being reviewed/staged; protected and unaffected content is preserved. |

Current generic record validation checks field shape, references, locks and assignment coverage; it does not establish SQL semantics. Existing backend SQL parsing accepts a broader statement set than this transformation contract, including writes. A parser pass therefore cannot replace the explicit statement/content checks above. Atlas's shared `validation/sql.js` additionally checks transformation statement classes, temporary stages, explicit final projection and runtime coordinate shape. It is not a complete SQL parser or proof of transformation fidelity.

Review with Mapping as the source of expected behavior. Formal Validation definitions belong to the later Validation workflow; local checking here does not create them automatically.

## Source pointers

Existing GDS: `references/workflows/code-generation.md`, `references/examples/staged-target-query.sql`, `references/examples/multi-system-target.sql` and the Mapping/code chapter of `references/orchestration-rules.md`. Backend contracts: `mcp_server/gds_etl_workbench/domain/modeling_records.py`, `application/change_sets/model_validation.py`; workflow authoring: `web_app/backend/gds_workbench_api/features/workflows/authoring/`.

Preserve confirmed Atlas runtime coordinates over incompatible catalog-qualified seed examples. Python record storage is distinct from actual authoring, download and runtime support; no Python execution contract is invented in this guide.
