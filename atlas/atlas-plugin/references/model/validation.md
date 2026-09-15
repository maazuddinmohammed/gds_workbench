# Validation records

Owns `validation_group`, `validation_check` and their storage contract. Use [check design](../validation/check-design.md) for coverage and independent expectations, [Model Change Set authoring](change-sets.md) for local records/MCP schema discovery, and [record state](../record-state.md) for protection. These records store definitions, never execution results.

## Identity and field shape

Both datasets belong to Model section `validation`. Write complete changed arrays to `model-change-set/validation_group.json` and `model-change-set/validation_check.json`. Every listed field is required, including nullable fields; the record schema supplies no defaults. New approved definitions use `is_active:true`, `is_locked:false`; preserve existing state.

Group natural key, within the owning Model: `tenant_code` + `system_code` + `validation_group_name`.

| Field | Accepted value / meaning |
|---|---|
| `tenant_code` | Nonblank string, 1–100 characters; **Model-owning Tenant**, not a SQL relation's physical GDS Tenant. |
| `system_code` | Nonblank string, 1–100 characters; active originating System with relevant Mapping. This association does not automatically filter SQL rows. |
| `validation_group_name` | Nonblank string, 1–200 characters; distinguish layer, target/feature and purpose when needed. |
| `validation_group_description` | Nonblank text up to 16,384 UTF-8 bytes, or `null`; concise scope/purpose, including population where necessary. |
| `is_active` | Boolean. |
| `is_locked` | Boolean. |

Check natural key: the Group's three fields + `validation_check_name`. Repeat the complete Group identity in every Check.

| Field | Accepted value / meaning |
|---|---|
| `tenant_code` | Nonblank string, 1–100 characters; same Model Tenant as its Group. |
| `system_code` | Nonblank string, 1–100 characters; same originating System as its Group. |
| `validation_group_name` | Nonblank string, 1–200 characters; existing or locally authored parent Group. |
| `validation_check_name` | Nonblank string, 1–200 characters; one recognizable assertion. |
| `validation_check_description` | Nonblank text up to 16,384 UTF-8 bytes, or `null`; expected behavior and relevant scope/null/empty-input meaning. |
| `validation_category_code` | String matching `^[a-z][a-z0-9_.-]{0,99}$`; descriptive lower-case category, not a fixed reference-table enum. |
| `validation_severity` | `blocking`, `warning` or `informational`; records intended significance, not a demonstrated pipeline-control action. |
| `validation_query_sql` | Required nonblank Query A; at most 100,000 UTF-8 bytes. |
| `validation_comparison_query_sql` | Nonblank Query B up to 100,000 UTF-8 bytes, or `null`; present only for a query operand. |
| `validation_result_data_type` | `boolean`, `integer`, `decimal`, `text`, `date`, `timestamp`, or `null` only for `executes_successfully`. |
| `validation_comparison_operator` | One operator from the table below. |
| `validation_comparison_value_type` | `none`, `literal`, `literal_list` or `query`; must agree with the operator. |
| `validation_comparison_value` | Typed JSON scalar, typed JSON array or `null`, as below; at most 65,536 serialized UTF-8 bytes. No object or null list item. |
| `is_active` | Boolean. |
| `is_locked` | Boolean. |

No Model/database IDs, Entity/Object keys, artifact links, Connection IDs, environment, batch parameters, execution order, severity action, result status, timestamps or digest fields are accepted. Target/population belong in explicit SQL and concise descriptions; these are not structured target assignments. Referencing a table in SQL does not establish a Model relationship or mutate Input Scope.

## Operators and typed operands

Query A means the final result of its own SQL batch. Query B is a separate self-contained batch; it cannot depend on temporary relations created by A, another Check or a Code artifact.

| Operator | Result type | Value type / required operand |
|---|---|---|
| `executes_successfully` | `null` | `none`; value and Query B both `null`. Execution success is the intended assertion; result shape is ignored. |
| `is_null`, `is_not_null` | Any declared type | `none`; value and Query B both `null`. |
| `is_true`, `is_false` | `boolean` | `none`; value and Query B both `null`. |
| `equal`, `not_equal` | Any declared type | `literal` with one matching scalar and Query B `null`, or `query` with value `null` and Query B populated. |
| `greater_than`, `greater_than_or_equal`, `less_than`, `less_than_or_equal` | `integer`, `decimal`, `date` or `timestamp` | Same scalar-literal/query alternatives as equality. |
| `in`, `not_in` | Any declared type | `literal_list`; 1–10,000 matching values, Query B `null`. Query-based membership is not supported. |

- Boolean uses JSON `true`/`false`; integer uses an integer, excluding booleans. Decimal accepts an integer or finite decimal number, excluding booleans and NaN/infinity.
- Text uses a JSON string; an empty text comparison value is allowed. Date and timestamp use strings accepted by Python's `date.fromisoformat` / `datetime.fromisoformat`; use explicit ISO dates/timestamps. Do not assume timezone normalization or cross-zone comparison semantics.
- Lists contain values matching the declared result type; JSON arrays become tuples internally. `false`, `0`, `""` and `null` are different. Null is not a literal comparison value; use a null operator or explicit SQL handling.
- Scalar assertions require exactly one row and one column from A and, when used, B. Zero/multiple rows or columns are a query-contract error, not a business assertion failure. `COUNT` can deliberately produce zero for empty input; do not hide an undefined expectation with a default passing value.
- The repository defines this scalar contract but does not implement the external orchestration comparator here. Ordinary null equality/ordering/membership, decimal tolerance and timezone behavior are not established by record validation. Resolve them explicitly; never assume SQL or Python comparator semantics.

## SQL, eligibility and protection

- Current active-Check validation uses governed Databricks SQL: at most 25 statements per A/B batch; reads and unqualified temporary view/table declarations, no persistent DDL or DML. Declare temporary relations before use in that batch. Scalar assertions must end in a row-returning statement.
- **Save Validation definitions with `catalog.schema.table` for persistent relations.** This first-release contract preserves the current parser. Resolve exact catalog/schema/Object/Attribute coordinates through [query scope](../query-scope.md); quote components separately. Framework transformation Code retains its two-part runtime references. A transformation-output Check or optional probe uses a separately prepared qualified query, not blind text replacement or a rewrite of the saved Code.
- Saved Validation SQL is bound to the actual coordinates resolved for its environment. Reuse in another environment requires coordinate resolution and review; no hidden catalog-suffix or substitution convention is assumed. Missing coordinates leave the affected definition unresolved, not all authoring blocked.
- The Model owner and active System are checked for Groups and Checks, including inactive records. Every Check requires its Group; an active Check requires an active Group. An active Group requires active Mapping for its System.
- Author against applied, complete Mapping/Binding context and current relevant Code when the check tests that implementation. Code is optional for Mapping-derived/loaded-data definitions. Group Apply resolves complete active Mapping context for its System; broader generic effective-graph acceptance is not a substitute for those prerequisites.
- Record existence, parser safety and Group/System association do not prove SQL relation/column existence, authorized modeling scope, correct System filters or valid batch/window boundaries. Apply [check design](../validation/check-design.md) and [query scope](../query-scope.md) to each actual population.
- Group and Check locks protect their own records independently; generic Model validation establishes no blanket Group-to-Check lock cascade. Preserve protected work, parent activity and unrelated checks; do not use a new name to bypass a lock. Inactive records retain their canonical identities.

## Freshness, partial updates and Apply

Apply stores Groups/Checks and advances Model revision; it does not execute SQL, compare results, deploy files or schedule checks. Model Snapshots include saved definitions/SQL, not execution evidence. Use the shared [review/Stage/Validate/Apply lifecycle](../change-set-lifecycle.md), then refresh the Model Snapshot.

The first release does not implement a separate external comparator or execution service. Author meaningful scalar outcomes with explicit agreed SQL semantics; keep checks unexecuted unless actual evidence exists. Request a consumer contract only where the specific requested comparison depends on otherwise unknown null, tolerance, timezone or runtime behavior.

The server derives Group `mapping_context_digest` and nullable `code_context_digest` from relevant System context. These are not authorable fields and are absent from public Snapshot records. A timestamp or unchanged SQL does not establish freshness. Current context readers may expose current/stale information; do not invent a plugin reader or author a digest.

Group digests cover System-level context rather than an individual Check target. A Group-only refresh can stamp fresh context without proving every retained Check was reconsidered; a Check-only update does not itself refresh the Group digest. Review relevant changes before refreshing currentness, and report unresolved stale/protected definitions.

Use [existing work and update scope](../working-method.md#existing-work-and-update-scope). Ordinary Model Change Set records overlay by canonical key; omitted applied definitions remain. The existing backend agent reconciler instead expects a **complete System ledger** and deactivates omitted unlocked active Groups/Checks. Never send a selected/affected subset to that reconciler as a complete ledger. Atlas's selected-update handling must preserve unselected definitions explicitly.

## Validation record checks

| Rule | Check / reason | Current coverage |
|---|---|---|
| `validation.shape` | Exact 6/15 fields, canonical keys, enums, required nulls and byte limits. | Record schema, duplicate-key checks and database constraints. |
| `validation.operands` | Operator/type/value/Query B agree; scalar literal versus nonempty typed list. | Generic schema has a gap: it accepts a list with `literal` for equality/ordered operators; database requires the scalar shape. Add an explicit local check. |
| `validation.parents` | Model-owning Tenant, active System, real Group and applicable active Mapping. | Graph checks; Group Apply resolves complete Mapping context. |
| `validation.sql` | Safe self-contained A/B, fully qualified persistent relations, correct final statement. | Current active-Check parser; prepare a separate qualified query when testing two-part framework Code. Inactive SQL is not parsed by this graph check. |
| `validation.meaning` | Real target/columns, matched population, independent expected behavior, useful assertion and deliberate null/empty behavior. | Additional workflow/local checks; schema/SQL parsing does not prove these. |
| `validation.scalar` | Exactly one row/column with declared compatible type, except execution-only A. | Runtime contract; not statically proved or executed by Change Set validation. |
| `validation.protection` | Preserve independent locks, active parents and unselected definitions. | Direct locks/graph checks; partial candidate must not use complete-ledger retirement behavior. |
| `validation.freshness` | Relevant applied inputs reviewed; no misleading Group digest refresh. | Server-managed digests; the agent compares the current Mapping context and selected input evidence; no automatic business-impact proof. |

Schema counts/operand and SQL parser checks below are local verification only. They do not demonstrate database results or an implemented external comparator.

## Complete synthetic examples

Assume Model Tenant `demo`, active System `CRM`, complete applied Customer Mapping and current registered targets. The selected population is the **entire current CRM customer set**: no batch/history or incremental window; `atlas_demo.bronze.crm_customer` contains one row per current CRM customer with no Mapping row filters. `atlas_demo.silver.Customer` can also contain other Systems, so both target checks explicitly use the confirmed synthetic CRM `SourceSystemID = 7`. Catalog `atlas_demo` is synthetic, not a default to copy into real work.

`model-change-set/validation_group.json`:

```json
[
  {
    "tenant_code": "demo",
    "system_code": "CRM",
    "validation_group_name": "SilverCustomerTechnicalIdentity",
    "validation_group_description": "Current CRM customers only (SourceSystemID 7); key uniqueness and full-population row reconciliation.",
    "is_active": true,
    "is_locked": false
  }
]
```

`model-change-set/validation_check.json`:

```json
[
  {
    "tenant_code": "demo",
    "system_code": "CRM",
    "validation_group_name": "SilverCustomerTechnicalIdentity",
    "validation_check_name": "NoDuplicateCustomerKeys",
    "validation_check_description": "No CRM CustomerCode occurs more than once. Empty input returns zero duplicate groups; completeness and null keys need their own checks.",
    "validation_category_code": "technical.uniqueness",
    "validation_severity": "blocking",
    "validation_query_sql": "SELECT COUNT(*) AS DuplicateKeyGroups FROM (SELECT CustomerCode FROM atlas_demo.silver.Customer WHERE SourceSystemID = 7 GROUP BY CustomerCode HAVING COUNT(*) > 1) AS duplicates;",
    "validation_comparison_query_sql": null,
    "validation_result_data_type": "integer",
    "validation_comparison_operator": "equal",
    "validation_comparison_value_type": "literal",
    "validation_comparison_value": 0,
    "is_active": true,
    "is_locked": false
  },
  {
    "tenant_code": "demo",
    "system_code": "CRM",
    "validation_group_name": "SilverCustomerTechnicalIdentity",
    "validation_check_name": "CustomerCountMatchesSource",
    "validation_check_description": "All current CRM rows are retained once by this Mapping. Counts of zero are allowed; equal counts alone do not prove identical keys or values.",
    "validation_category_code": "technical.reconciliation",
    "validation_severity": "blocking",
    "validation_query_sql": "SELECT COUNT(*) AS CustomerCount FROM atlas_demo.silver.Customer WHERE SourceSystemID = 7;",
    "validation_comparison_query_sql": "SELECT COUNT(*) AS CustomerCount FROM atlas_demo.bronze.crm_customer;",
    "validation_result_data_type": "integer",
    "validation_comparison_operator": "equal",
    "validation_comparison_value_type": "query",
    "validation_comparison_value": null,
    "is_active": true,
    "is_locked": false
  }
]
```

These are complete records, not a required coverage checklist or evidence that fictional relations exist. Reuse exact existing names/identities in real updates.

## Source contract

- `mcp_server/gds_etl_workbench/domain/modeling_records.py`: `ValidationGroupRecord`, `ValidationCheckRecord`, literal checks and limits; `domain/snapshots/model.py`: canonical keys and section.
- `application/change_sets/model_validation.py`: ownership, active dependencies, independent locks and active SQL checks; `application/change_sets/model_apply.py`: Group/Check upserts and server-derived currentness.
- `domain/databricks_sql.py`: statement policy/qualification; `application/model_snapshot.py`: exported saved definitions. All four paths above are under `mcp_server/gds_etl_workbench/`.
- `database/10_workflow_code_validation.sql`: storage constraints and uniqueness, including scalar-literal shape.
- `web_app/backend/gds_workbench_api/features/validation/{context,candidate,service}.py`: applied/current authoring inputs, complete-ledger reconciliation and definition generation; not an external comparison executor.
- `docs/adr/004-code-generation-and-validation-model-sections.md` and `docs/workflow-code-validation-design.md`: authoring/execution boundary and scalar consumer contract.
