# Foundry / OpenAI SDK / Run consumption inventory

Read-only inventory, 2026-09-05. No production edits or external calls.

## Confirmed requested scope

- OpenAI Agents SDK plus Microsoft Foundry only; remove LangChain and Databricks AI Model Serving integration/choices.
- Preserve Databricks SQL, source inspection, notebooks, and application authentication.
- Show Model and reasoning effort as the agent choices. Execution mode remains a workflow choice.
- Record actual input/output/cached tokens across **every workflow Run**, stages, tools, and repairs, including failed Runs, in the web application and notebooks.
- Label cost as estimated or unpriced unless actual billing evidence exists. No additional Tenant aggregate requested.

## Current integration / selection paths

| Boundary | Files and current behavior |
| --- | --- |
| Public capability contract | `web_app/backend/gds_workbench_api/capabilities.py`, `config/agent_capabilities.json`: SDK/provider lists and per-model SDK/mode/reasoning profiles. Preserve tested mode/reasoning combinations while narrowing SDK/provider. |
| Runtime integration | `integrations/agents/adapters.py`, `composition.py`, `configuration.py`, `__init__.py`: both SDK adapters, Databricks model authentication, and direct Foundry API key / Entra authentication. Remote composition adds Databricks deployments without requiring Foundry configuration. |
| Durable selection | `features/workflows/commands/{contracts,service}.py`, `authoring/plan.py`, `features/models/{command_contracts,contracts,command_service}.py`, `database/13_application_workflow_runs.sql`: Model defaults and frozen Run SDK/provider/model. Reject unsupported new selections; retain historical Run identity. Existing Model defaults may reference removed providers, so new default resolution needs explicit handling. |
| Shared web Run dialog | `features/workflows/WorkflowRunDialog.tsx`: Analysis inference, Conceptual, Logical, Dimensional, enrichment. SDK, provider, model, reasoning, turns and retries are currently user controls. Enrichment mode fixed one-shot; other supported mode restrictions must survive. |
| Other web dialogs | `features/mapping/MappingRunDialog.tsx`, `code_generation/CodeGenerationRunDialog.tsx`: duplicated SDK/provider/model/reasoning/limit controls. `validation/ValidationRunDialog.tsx` currently chooses all agent settings from defaults and displays facts; it needs actual model/effort controls if the same user choice applies to Validation. |
| Web selection helpers | `features/workflows/api.ts`: selection DTO; `resolveDefaultAgent`, `resolveAgentProfileSelection`, `listCompatibleExecutionModes`, `findAgentExecutionProfile`. Fixed SDK/provider should be resolved consistently rather than retaining multiple fallback loops. |
| Notebook widgets | `databricks_notebooks/src/gds_workbench_notebooks/notebook.py`: exposes AgentSDK, AgentProvider, AgentModel, ReasoningEffort, MaxTurns, ValidationRetryCount; capability filter and parser explicitly allow only Databricks. |
| Notebook runtime | `workflow_execution.py::_notebook_agent_configuration`, `runtime.py`, `preflight.py`: explicitly constructs Databricks-only model authentication and rejects Foundry. A registry/UI-only change would break independent notebooks. Wire Foundry configuration/authentication without changing SQL principal or SQL connection boundaries. |
| Dependencies / artifacts | `web_app/backend/pyproject.toml`, backend/root lock files, `databricks_notebooks/requirements.txt`, notebook dependency/source tests, independent upload artifacts. Remove LangChain dependencies after references are removed; rebuild relevant artifacts and probe Python 3.12 imports. **Keep databricks-sdk**: web `authentication.py` still uses WorkspaceClient independently of model serving. |

Model ledger has no editable agent-default form. Model defaults exist in API contracts and are consumed by Run dialogs. Plugin local authoring helpers do not contain these provider/SDK integrations in the inspected source.

## Current consumption path and loss points

- `OpenAIAgentsSdkAdapter.execute` calls installed `openai-agents==0.22.0` using `Runner.run` and `OpenAIChatCompletionsModel`. It returns candidate, turn count, and tool call count only.
- `AgentExecutionResult` (`authoring/agent_execution.py`), `AgentAuthoringResult` (`repair.py`), and `AgentStageOutcome` (`stage_runner.py`) contain no usage. Repair accumulates turns/tools across calls only on successful return; failures can exit before any outcome is returned.
- `application.workflow_run`, shared `WorkflowRunDetail` (`features/workflows/runs/contracts.py`), Run read SQL (`runs/service.py`), and frontend `WorkflowRunDetail` (`features/workflows/api.ts`) contain no token or cost fields.
- `WorkflowRunMonitor.tsx` is the shared Run detail entrypoint; a bounded consumption summary there covers all workflow screens, including failed/retained drafts. Refresh is manual. A separate dashboard per workflow is unnecessary.
- Notebook `NotebookWorkflowExecutionResult`, `_execution_result`, and `as_dict` in `workflow_execution.py` produce the display-safe result. Add the shared durable summary there so replayed Runs also report usage.

## Installed SDK evidence and traps

Inspected local `web_app/backend/.venv/lib/python3.14/site-packages/agents/` only; no assumptions about an uninstalled API:

- `result.py::RunResultBase.context_wrapper.usage` contains totals; `usage.py::Usage` contains `input_tokens`, `output_tokens`, `total_tokens`, `input_tokens_details.cached_tokens`, reasoning output details, and per-request entries.
- `exceptions.py::AgentsException.run_data.context_wrapper.usage` can preserve completed calls when a later turn fails. `run_data` also contains prompts/tool output; extract numeric fields only and never serialize/log the container.
- `models/openai_chatcompletions.py` maps a completed response whose `usage` is absent to `Usage(requests=1)`. Missing cache/reasoning details normalize to zero in `usage.py`. Therefore SDK numeric totals **alone cannot establish completeness** or distinguish missing data from actual zero. Capture bounded presence flags before that normalization.
- Count usage before candidate parsing/validation. Malformed output, bounded-output rejection, repair exhaustion, tool failure, and maximum turns can all consume tokens.
- Cache counts are part of input tokens, not additional input; reasoning counts are part of output. Cost calculation must not double-count them. Retain per-request pricing basis if rates vary by prompt size or deployment.
- Record successful provider calls once. Aggregate totals must survive claim retries and completed-Run replay without either duplicating persisted calls or pretending repeated paid attempts never occurred. Unknown transport outcomes must remain incomplete, not free.
- Do not equate a deterministic workflow's known zero agent calls with an older Run lacking telemetry, or with an agentic Run whose provider omitted usage. Expose a completeness/status distinction.
- No existing actual billing integration or rate configuration was found. A configured Foundry rate yields an **estimate**, not actual invoice cost. Missing rates/cached breakdown should yield unpriced or partially priced output instead of invented zero.

## Bounded verification plan

1. Narrow backend integration and capability/runtime tests; ensure unsupported SDK/provider requests fail, Foundry authenticates via fakes, all retained workflow modes work, and Databricks SQL/auth imports remain.
2. Update web dialogs/helpers and notebook widget/runtime/preflight tests together: only model/effort agent choices; limits resolve from backend/default policy; unsupported former defaults cannot silently dispatch to a removed provider. Preserve stable create idempotency and exact frozen selections.
3. Usage adapter tests with numeric-only fake responses: cache details, absent usage, actual zero, multiple tool turns, final malformed output, exception after a completed call, max-turn exhaustion.
4. Shared stage/repair tests: multiple repairs and detailed stages accumulate exactly once even when final handoff fails; no raw response/prompt/tool/sample data in persisted/read DTOs.
5. Disposable database tests: owner/claim-fenced usage writes, replay/idempotency, failed Run reads, numeric bounds and decimal pricing, read authorization. No external billing/model invocation needed.
6. Web Run summary tests for complete/partial/unpriced/estimated/known-zero/legacy-unavailable states; notebook result/replay tests return the same summary. Types/build and Python 3.12 packaged probes.
