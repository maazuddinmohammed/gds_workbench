# Profiling

Produce Attribute measurements for selected Model inputs. Prefer the deterministic SQL generator; if it fails, the agent may write equivalent Databricks SQL using this guide. Guided or Grill Me workflows decide when to start, reuse or redo profiling.

Atlas reuses the verified aggregate SQL with explicit batch lists, deterministic bounded groups and result import. Use the [runtime guide](../../docs/runtime-guide.md#profiling-and-analysis-files) for exact file/command shapes.

Read in order for new measurements: [inputs](profiling.md#resolve-inputs) → [batch selection](profiling.md#resolve-batch-selection) → [generator](profiling.md#deterministic-generator-contract) → [execution](profiling.md#files-and-execution) → [results](profiling.md#results-checks-and-reuse). Load the [fallback](profiling.md#agent-written-sql-fallback) only when needed; use [measurement definitions](profiling.md#measurement-fields) when authoring or checking SQL/results.

## Resolve inputs

1. Read the selected Model's active applied Input Scope and resolve its exact Objects and active Attributes in the bound Metadata Snapshot. Use the shared [Metadata](../snapshots/metadata.md) and [Model](../snapshots/model.md) guides. Preserve the user's selected subset.
2. Inspect existing effective profiles and available evidence. Reuse only for the applicable Object/Attribute selection, environment and batch scope, with known measurement context. Existing rows alone do not establish freshness or comparable scope. Follow the workflow's reuse/redo choice.
3. Follow shared [query scope](../query-scope.md) for coordinates, execution Connection, SQL policy and protection. Do not reapply ingestion custom code while profiling already stored values. Use verified physical types for SQL operations.
4. Inspect each Object's batch_attribute_name and resolve batch selections below. Show the resulting grouped scope before execution; supplied choices need no repeated approval.

## Resolve batch selection

Follow the shared [query-scope guide](../query-scope.md#batch-selection) for System/Object assignments, batched versus unbatched Objects, IN predicates and literal encoding. Reuse applicable choices, ask grouped questions for missing IDs and preserve explicit overrides.

The profiling selection and manifest record each Object's resolved scope. The common guide owns those rules for both profiling and analysis; do not keep a separate profiling batch policy.

## Deterministic generator contract

Use the runtime input wrapper `{selections, execution_connections}`. `selections` holds optional `systems`, `objects` and `selected_objects`; each batch assignment has `batch_ids`. The helper resolves Snapshot paths and saved environment from the workspace. Do not use scalar `batch_id` or `default_batch_id`.

Illustrative System assignment. Omit selected_objects only when the parent workflow selected the entire active applied Input Scope; otherwise supply the selected complete Object keys:

```json
{
  "systems": [
    {
      "source_tenant_code": "demo",
      "system_code": "crm",
      "batch_ids": ["10", "11"]
    }
  ]
}
```

Object overrides use all five physical Object key fields plus batch_ids. Any selected batched Object left without an assignment must be reported unresolved before its queries can run. Resolve all missing choices together; do not quietly omit unresolved Objects from coverage.

Invoke `profile-plan --session <working-directory> --plan-file <input.json>` through `scripts/atlas-local.js` (or the native PowerShell helper). It returns the exact output directory/manifest path. The [runtime guide](../../docs/runtime-guide.md#profiling-and-analysis-files) defines the wrapper and result import. If generation is unavailable or fails after valid inputs, follow the fallback below.

The generator:

1. Validates keys, physical types and the shared query-scope rules. Profile active permitted Attributes; identify excluded or blocked coverage explicitly, including unresolved expression protection.
2. Uses the fixed type-appropriate aggregate templates below. Order Objects by canonical keys, Attributes by ordinal then a locale-independent key, and batch values as a stable deduplicated set without altering their meaning. Identical bound input and generator version produce identical SQL and chunk membership.
3. Builds one standalone query per Object and bounded Attribute group: a filtered `scoped` CTE, a shared aggregate `summary`, then UNION ALL projections returning one aggregate row per Attribute. Every group for an Object uses the same resolved batch predicate. Unbatched Objects have no batch WHERE/IN clause.
4. Groups Attributes to fit the shared execution limits: one returned row per Attribute, reducing the group for SQL length or a lower configured row limit. Keep each Object's entire resolved batch set in every query group.
5. Writes SQL files and a JSON manifest. It generates files only; the agent performs permitted execution through the governed tool.

## Agent-written SQL fallback

Use this when the generator is unavailable, fails, or produces invalid SQL despite resolved inputs. Record the failure briefly and continue without repeatedly invoking a broken helper. Missing batch IDs, unresolved coordinates/types, masking gaps or denied execution are input/access problems; writing SQL cannot resolve them by itself.

1. Retain the resolved selection, query bindings and successful unaffected groups. The agent may create or repair only the affected SQL files using the [fixed query shape](profiling.md#deterministic-generator-contract) and [measurement definitions](profiling.md#measurement-fields). Inspect the existing template when available; the fallback must also work from this reference when it is unavailable.
2. Preserve type handling, literal/identifier encoding and the exact batched/unbatched scope. Use one Object per query and split Attribute groups for limits; never split the selected batch set, add sampling or omit supported metrics to make a query fit.
3. Produce the same SQL files, result columns, Attribute-index mapping and manifest bindings. Identify affected queries as agent-written and retain the reason in task evidence. Compute real file hashes with available local hashing facilities; do not invent digests or claim generator provenance. If the manifest helper is missing, write the required bindings below directly to JSON; use the published schema whenever a runtime helper consumes that manifest.
4. Before execution, check every replacement's relation, Connection/environment, batch predicate, selected Attributes, formulas, output types, indexes and size against the resolved plan and schema. Update its manifest/hash. A static check is preparation, not a successful Databricks execution.
5. Use the same governed [execution](profiling.md#files-and-execution) and [result checks](profiling.md#results-checks-and-reuse). SQL policy and authorization still apply. Failed or incomplete results remain unresolved.

## Files and execution

Use the existing manifest-plus-SQL pattern under the task's temporary workspace:

```text
.atlas/temp/<task-id>/profiling/<run-id>/
  plan.json
  0001.sql
  0002.sql
```

`plan.json` contains `schema_version`, `kind:"profiling"`, `task`, verified `inputs`, `environment`, `selections`, `queries` and `coverage`. Each query contains `object`, `source_tenant_code`, `source_system_codes`, `batch_ids`, `batch`, `relation`, `attributes`, `file`, `sha256`, `origin`, `generator_version`, `environment`, `connection_id` and `expected_row_count`. The agent reads this manifest, then one SQL file at a time. Preserve the original input file where useful; the generator does not copy it automatically.

The manifest binds Snapshot IDs, Model revision, environment, selected scope and coverage. Identify each query's origin (generator with its actual version, or agent-written), Object, actual relation, originating System context, resolved non-GDS execution Connection ID/key, batch column and selected IDs (or explicitly unbatched), file/hash, expected row count, and attribute_index-to-complete-Attribute-key mapping. Query identity plus attribute_index identifies a returned measurement; the index is not a database ID. Resolve Connection bindings before preparing SQL; the server still revalidates access at execution.

Follow shared [Databricks execution](../query-scope.md#execute-bounded-sql): verify the file and bindings, pass the SQL text through the governed tool, and inspect its complete result before continuing. A profiling query group returns one row per planned Attribute; require each expected attribute_index exactly once.

If a lower row limit truncates the result, discard that group's partial measurements and prepare smaller Attribute groups under the same Object/batch scope. Use the generator or its documented fallback, updating hashes and expected indexes. Preserve successful unaffected groups. Do not split the selected batch set or concatenate independent queries into one tool call.

## Measurement fields

The shared [Profiling Profile record](../model/profiling-profile.md) owns all 19 fields, metric formulas, denominators, rounding, supported-type null behavior and SQL result types. Use it when generating fallback SQL or converting results; do not redefine those calculations here.

Return one complete set of documented metrics per Attribute, plus the temporary attribute_index used to recover its physical key. Profile measurements alone do not establish a relationship or inferred business type.

## Results, checks and reuse

Match result columns by name and map aggregates through the query's Attribute index. Remove the transport index, preserve metric precision and follow [Model Change Set authoring](../model/change-sets.md) to validate/upsert complete profiling_profile records locally. Preserve unrelated work.

| Check | Purpose |
|---|---|
| profiling.scope | Selected active applied inputs, exact keys, environment and explicit batched/unbatched scope agree with the plan. |
| profiling.protection | Known masking and expression lineage are respected; the SQL execution tool does not enforce these metadata rules for the agent. |
| profiling.transport | SQL fits limits; response is complete with expected unique indexes and no truncation. |
| profiling.metrics | Apply the exact [Profile record checks](../model/profiling-profile.md#record-checks-and-interpretation) and verify calculations against the result. |
| profiling.consistency | Attribute groups for one Object use the same batch set. Different row counts indicate inconsistent measurements; resolve rather than combine them silently. Equal counts alone do not prove unchanged data. |
| profiling.coverage | Report reused, measured, excluded, unresolved and failed coverage accurately. Generated SQL is not an executed profile. |

Atlas planning/result helpers implement the checks described below; semantic interpretation remains agent review. The profile key is the physical Attribute key: reprofiling updates its current profile, not a batch-history record. Batch IDs, environment, measurement time and Snapshot IDs are not profile fields.

Keep concise scope, execution time, actual environment/Connection binding, query hashes and coverage in durable task evidence before temporary cleanup. Do not save raw tool envelopes or physical rows. Reuse depends on this evidence and the user's choice, not merely the presence of a profile row. Related analysis/modeling may use validated local results where catalog prerequisites allow; use the shared [Change Set lifecycle](../change-set-lifecycle.md) at the appropriate completion/dependency boundary.

## Existing implementation to reuse

Current GDS sources: scripts/profiling.js (templates and planning), scripts/gds-local.js (manifest/files), domain/modeling_records.py (Profile contract), and tools/databricks/execute_sql.py (execution contract). Preserve their verified encoding, type handling and schema behavior. Atlas implements batch-ID lists/IN, mandatory batch resolution, stable ordering, conservative masking-lineage exclusions and scope-bound evidence through `profile-plan` and `profile-results`.
