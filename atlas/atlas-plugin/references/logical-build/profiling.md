# Profiling

Measure selected active, applied Model Input Scope Objects through backend runs.
Python builds aggregate SQL, executes it through the registered GDS Connection values,
validates results, and saves Attribute Profiles directly. The agent selects scope,
starts/monitors the run, and refreshes the Model Snapshot.

## Resolve inputs

1. Bind the Model and current Snapshot revision. Resolve selected numeric Object IDs using
   `get_model_input_scope`; preserve the user's subset. Pending Input Scope must Apply first.
2. Reuse applicable profiles when their measurement scope is known. Missing profiles during
   an authorized profiling task can trigger a run; missing rows alone are not permission to
   run unrelated work. Respect the user's saved SQL execution policy and selected environment.
3. Inspect selected Objects' batch metadata. Supply one shared list of explicit batch IDs
   for all batched Objects in this run. Use separate runs for different batch selections.
   Unbatched Objects receive no filter. Never infer the latest batch or use an empty list
   to mean all batches. Ask the user for missing batch choices.
4. Hold the owning Tenant Lock. A locked Model cannot be profiled; an agent cannot unlock it.

## Start and monitor

Call `start_profiling_run` with:

- `model_id` and `selected_object_ids` (1–500 IDs).
- `expected_model_revision` from current Model context.
- `request_id`: a newly generated UUID, retained for identical transport retries.
- `batch_ids`: optional list of strings; required if any selected Object has a batch Attribute.
- `environment_code`: the selected environment; default `dev`.

Batch values retain their exact meaning. The backend rejects unsupported/lossy batch
conversions before execution and generates `IN` even for one ID. Source queries use the
Connection foreign catalog and foreign schema/table/column names. Bronze queries use the
Object owner's `tenant_catalog` and registered physical names, never `gds_admin_catalog`.
The server enforces source access and masking/lineage protection. A protected or incomplete
selection fails explicitly; do not work around it with custom SQL.

Save the returned Run ID and request inputs as concise task evidence; never store credentials,
raw rows, or raw tool envelopes. Retry an uncertain start with the same request ID and inputs.
A new measurement request requires a new request ID. Revision conflict requires a fresh
Snapshot and reassessment; do not automatically merge pending changes.

Poll `get_profiling_run_status(run_id)` with reasonable spacing. Report completed/selected
Objects and state. `completed` means all results were validated and saved atomically;
`failed` or `cancelled` does not replace existing profiles. Model writes remain fenced
against concurrent edits and changed physical metadata. Runs are persisted and recoverable
after an MCP restart; do not create a second run merely because one request timed out.

Use `cancel_profiling_run(run_id)` when the user requests cancellation. It requires the run
owner and Tenant Lock, immediately revokes permission to save, and requests cancellation
of active Databricks statements. Statement termination is best effort; status reports the
Workbench run state, not a guarantee that Databricks has already stopped its statement.

## Refresh and reuse

After completion, create and install a fresh Model Snapshot using the existing
[Snapshot workflow](../snapshots/model.md). Preserve unrelated local proposals. If the
installer detects a baseline conflict, reconcile explicitly; never discard pending work.
The refreshed `profiling_profile` records are the measured results used by downstream modeling.

Do not create Profiling SQL files, call `execute_databricks_sql` for Profiling, import local
aggregate results, or create a Profiling Change Set. Backend failure stays explicit;
there is no agent SQL fallback. Analysis and other evidence queries keep their existing tools.

Reprofiling replaces the selected Attributes' current measurements, not a per-batch history.
Multiple IDs measure their combined stored population; they do not deduplicate repeated loads.
Read [Profile metrics](../model/profiling-profile.md) for field meanings.
