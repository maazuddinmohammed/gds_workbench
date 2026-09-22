# Agent failure audit / implementation

2026-09-21. Local source + installed SDK only. No provider calls, external writes, database connections, or secret inspection.

## Implemented

- `web_app/backend/gds_workbench_api/features/workflows/authoring/agent_execution.py:224`: fixed public failure codes/messages for context exhaustion, output truncation, timeout, rate limit, authentication/access rejection, unavailable provider, rejected provider request, tool failure, turn limit, and refusal. Unknown failures keep `agent_execution_failed`. Prompt fields retain nonblank/NUL validation but no character ceiling; optional tool result budget supports `None`.
- `web_app/backend/gds_workbench_api/integrations/agents/adapters.py:202`: classify concrete exception types and exact structured provider codes. Never inspect/display provider message text, body, request, credentials, or SDK run dumps. Preserve usage-recording failures. Unlimited catalogs bypass the budget wrapper; explicitly bounded catalogs retain cumulative enforcement.
- `web_app/backend/gds_workbench_api/integrations/agents/usage.py:19`: always observe nonstreaming finish reasons, even without a usage recorder. `length` and `content_filter` become fixed errors; counters remain recordable. HTTP hooks retain an error instead of raising on an already paid response. Next request/tool callback is blocked; no partial candidate is accepted. Removed response-size conditional around metadata parsing so large responses cannot bypass finish-reason handling.
- `adapters.py:373`: local callback stores only safe tool errors before the SDK wraps them. Unexpected callback errors are replaced before SDK handling. Valid safe tool failures keep their original public code.

## Verified SDK behavior

Installed `openai-agents==0.22.0`, `openai==3.3.1`.

- `.venv/lib/python3.14/site-packages/agents/models/openai_chatcompletions.py:219` uses `chat.completions.create` (`:734`), then converts message content. Nonstreaming `finish_reason="length"` is not raised/preserved as a length exception. Catching `LengthFinishReasonError` alone is insufficient. New real-SDK transport tests cover syntactically valid JSON, incomplete JSON, and tool calls with this finish reason.
- `agents/exceptions.py` defines `ModelTimeoutError`, `MaxTurnsExceeded`, `ModelRefusalError`, `ToolTimeoutError`. `openai/_exceptions.py` defines HTTP auth/rate/status/connection/timeout exceptions. `APITimeoutError` subclasses `APIConnectionError`; timeout classification must precede connection classification.
- `agents/run_internal/tool_execution.py:1839` wraps non-Agents exceptions as `UserError`. Safe local-tool errors otherwise lose their identity at the adapter's generic catch. The callback side channel now preserves only sanitized errors.
- SDK errors can retain provider requests/responses and `AgentsException.run_data`; do not stringify/log these objects. SDK `_debug.py` defaults model/tool payload logging off. Existing run tracing remains disabled with sensitive trace data disabled.

## Failure -> run -> UI trace

1. HTTP/tool failure reaches adapter and becomes a fixed `WorkbenchError`.
2. `features/workflows/authoring/agent_execution.py:303` router preserves it; stage/repair execution lets it escape without a schema-repair retry.
3. Seven authoring services preserve `WorkbenchError` through `_safe_execution_error`, e.g. `features/conceptual/service.py:416` / `:529`. Before handoff they call lifecycle.fail; after uncertain handoff they intentionally leave recovery pending.
4. `features/workflows/authoring/lifecycle.py:204` validates failure metadata and calls governed SQL. Claim/revision protection remains intact.
5. `database/13_application_workflow_runs.sql:3742` stores failure code/message and terminal run state. The terminal event at `:3755` uses stage `workflow_run` and highest previously persisted attempt.
6. `features/workflows/runs/service.py:76` reads stored metadata; frontend `web_app/frontend/src/features/workflows/WorkflowRunMonitor.tsx:506` displays code/message verbatim as text in the failure alert. No frontend change required for new codes.

Remaining precision gap: UI's “Last stage” selects the last failed/blocked event (`WorkflowRunMonitor.tsx:485`), normally the generic terminal `workflow_run` event, so it need not identify the actual agent stage. Terminal attempt is highest persisted progress attempt, not necessarily the currently executing repair attempt. Do not claim exact per-stage/attempt failure observability from the current SQL event alone.

## Metadata enrichment exception

`features/metadata_enrichment/service.py:374` catches `WorkbenchError` per Object description unit, marks affected fields unavailable, continues remaining units, and completes with warnings. This deliberate partial-success behavior means provider failures do not reach failed-run metadata/UI for enrichment.

Recommended compatible change sent to root: preserve partial success; append one `candidate_authoring` warning event with the fixed public failure code/message and affected-field count, rather than marking that unit completed successfully. Parent/prompt agent owns this file. Test one failed unit followed by a successful unit: unavailable/applied fields, warning contains safe diagnostic, successful metadata retained. No schema/migration needed.

## Coverage inventory

- **Real installed SDK + fake in-memory HTTP:** `tests/web_backend/test_agent_usage.py:260` (usage survives failed later turn), `:291` (repair), `:324` (recording failure does not retry a paid response), `:348` (retry/missing usage). New `test_agent_provider_failures.py` covers provider HTTP status/structured code, transport timeout/connection, truncation with and without metering, tool safe/unknown error, turn cap, SDK timeout, Entra exception, refusal, unlimited tool catalog, large prompt acceptance.
- **Actual workflow/stage/repair + fake persistence and injected agent failure:** new 84-case matrix in `test_agent_provider_failures.py`: seven failure categories × 12 supported configurations. Analysis, conceptual, logical, dimensional, mapping each cover one-shot + tool-assisted; code generation and validation cover their canonical no-user-mode plan with internal tool-assisted stage. Asserts exact safe failure persistence, one model invocation, and no partial handoff.
- **Existing fake success/repair paths:** `test_conceptual_executor.py:659/:874`; `test_logical_executor.py:848/:992`; `test_dimensional_executor.py:1021/:1082`; `test_mapping_executor.py:228` both modes; `test_analysis_executor.py:609/:669` both modes; `test_code_generation_executor.py:822/:1309`; `test_validation_executor.py:477`. `test_agent_runtime.py:699` onward also exercises deterministic local fake adapters/catalogs.
- **Disposable PostgreSQL integration, synthetic agent:** `test_database_metadata_enrichment_executor.py:152`, including descriptions, repair, invalid response, lock handling, selected-attribute regeneration. Existing DB lifecycle/claim/change-set tests cover governed state/persistence separately. None were executed by this agent.
- **Frontend mocked API:** `WorkflowRunMonitor.test.tsx:473` covers safe failure alert, agent identity, and event stage/attempt. Frontend tests use Vitest/jsdom; no full browser-to-live-provider E2E suite was found.
- **Live provider:** none executed and no live-provider integration suite identified. Existing transport tests do not prove actual Foundry model JSON/latency/capacity behavior. Live smoke tests require the configured direct endpoint/model deployment, authorized API-key or Entra authentication, and explicit permission for provider I/O. Do not inspect or print credentials; retain only safe run status and numeric usage. Live Databricks stages separately require explicit approval.

## Verification

- 67 tests passed across adapter, usage, local-tool, execution-router, and initial provider-failure suites.
- Expanded provider-failure suite: **109 passed**, including the 84 workflow/mode/category matrix cases.
- Focused Ruff and Pyright: clean.
- No SQL, frontend, or metadata-enrichment source changed by this agent.

## Independent execution verification (follow-up)

- Concrete executor suites for analysis, conceptual, logical, dimensional, mapping, code generation, validation, safe provider failures, and draft recovery: **201 passed, 1 stale default-limit assertion failed**. The failure was `test_mapping_description_limits_follow_the_bounded_request[True]` at `tests/web_backend/test_mapping_executor.py:260`; it still expected the removed implicit limit. Root notified to update it to an explicit configured limit or assert full preservation under defaults. No source changed in this follow-up.
- **48 disposable-PostgreSQL integration tests passed**: `test_database_metadata_enrichment_executor.py`, `test_database_seeded_analysis_conceptual.py`, `test_database_model_change_sets.py`, `test_database_failed_workflow_draft.py`. Initial sandbox Docker socket access failed; approved escalation reran successfully. Captured database output remained hidden. Fixtures in `tests/mcp/conftest.py:142` reject external/default environment connections before Docker, generate random credentials/database, verify the per-run sentinel, and dispose only their labeled container.
- **23 WorkflowRunMonitor frontend tests passed**. `WorkflowRunMonitor.tsx:514` formats any public failure code with underscore replacement; `:516` renders the fixed message as React text. `runs/contracts.py:76` accepts bounded strings, without a hardcoded code enum; new failure codes pass through existing API/UI. Existing test at `WorkflowRunMonitor.test.tsx:473` confirms alert, stage, attempt, provider identity and usage. It still uses an older sample code; no new-code-specific branches exist to break.

### What “end-to-end” currently covers

| Workflow | Both supported modes through real executor/stage/repair | Installed defaults exercised | Actual PostgreSQL terminal/draft/apply path |
| --- | --- | --- | --- |
| Analysis inference | Yes, synthetic provider | Yes, both + repair | One-shot |
| Conceptual | Yes, synthetic provider | Yes, both + repair | One-shot |
| Logical | Yes, synthetic provider | Yes, both + repair | One-shot |
| Dimensional | Yes, synthetic provider | Yes, both + repair | One-shot |
| Mapping | Yes, local fake | Yes, both | Full executor persistence not covered by selected tests |
| Code generation | Canonical plan; internal tool-assisted stage | Yes, normal + repair, real repository context projection | Handoff/lifecycle mocked in executor tests |
| Validation generation | Canonical plan; internal tool-assisted stage | Yes, real repository context projection with/without generated code | Handoff/lifecycle mocked in executor tests |
| Metadata enrichment | One-shot description units; deterministic type evidence | Installed prompt exercised by actual database executor | Yes; success, repair, invalid response, locks, regeneration variants |

Installed-default tests for mapping/code generation/validation are integration tests, but must not be described as full persistent workflow executions: `test_database_seeded_analysis_conceptual.py:282/:328/:430` load real defaults/repository evidence and then use the synthetic service factories.

**Precise next test for gaps:** parameterize a disposable-database workflow test over mapping both modes, code generation canonical mode, validation canonical mode, and tool-assisted analysis/conceptual/logical/dimensional. Seed each workflow's required applied graph through existing fixture helpers; start/claim using governed operations; execute the actual assembled service with the existing local fake adapter; read terminal run/draft using `DatabaseWorkflowRunService`; assert one validated unapplied draft, correct scope/provenance, unchanged Model revision until explicit apply, and exactly one application on retry. This requires more fixture assembly than a test-name change and should be a separate cohesive test addition.

A single browser -> HTTP API -> worker -> real provider -> PostgreSQL -> browser test is not present or executed. Real-SDK/MockTransport tests and fake workflow/DB tests provide complementary local evidence; they do not establish live model quality, provider context capacity, or external latency.

## Gaps filled after independent audit

The earlier success-persistence gaps are now closed for the currently supported agent workflows/modes; the live-provider/browser boundary remains untested.

- `tests/web_backend/test_database_model_change_sets.py`: existing Analysis, Conceptual, Logical and Dimensional draft/apply/provenance tests now run both `one_shot` and `tool_assisted`. Real local readers must be invoked in tool-assisted mode. Existing guarded apply, materialized provenance, revision and replay assertions remain intact.
- `tests/web_backend/test_database_agent_workflow_pipeline.py`: two complete fixture-only pipelines (Mapping one-shot/tool-assisted) run **Mapping → Code Generation → Validation** sequentially. Each uses governed run creation, real installed prompt defaults, real mapping output templates, real source/context repositories, assembled runtime and claim dispatcher, shared stage/repair validation, real run-history reads, a validated unapplied draft, guarded apply, and idempotent replay. Model revision stays unchanged until apply. Each draft records exactly one applied event. Code/Validation use their supported canonical modes and actually invoke enabled named readers.
- Existing metadata-enrichment disposable executor tests cover its supported one-shot path, per-unit repair/unavailability and guarded completion. This workflow completes metadata directly rather than creating a Model change-set draft.

### Defects uncovered by the new real-persistence tests

1. Local fake authoring still depended on legacy generic context tools while actual catalogs publish named readers. `integrations/agents/fake_shared.py` now follows cursor pages through `get_objects` / `get_object_details` and derives source identities from returned metadata. The old branch remains for existing legacy fixture catalogs.
2. Local fake Code Generation/Validation did not invoke their optional readers. `integrations/agents/composition.py` now uses `get_code_source_systems` results for artifact assignments and observed `get_mapping_evidence` / `get_current_code` counts for its synthetic validation description. Disabled readers remain optional; four focused tests assert disabled behavior and that actual returned evidence affects output.
3. Non-null installed Mapping output-template schemas failed root `$ref` resolution because `$defs` lived inside `anyOf[0]`. Prompt-audit agent hoisted both template definitions to each schema root, added nonempty examples, and owns the associated regression. The new pipeline passes against that actual source fix.

Final verification at source freeze: **24 changed disposable-database tests passed**, **129 fake/runtime/provider tests passed**, focused project-configured Ruff/Pyright clean. No real providers, Azure, physical Databricks execution, non-fixture database, or external mutations used.

## Local review seed regression

Fresh preview Conceptual execution exposed three preexisting Validation checks with two-part table names. The governed Databricks SQL validator correctly requires catalog.schema.table; the complete future-graph gate therefore rejected the Conceptual candidate. `database/seed/08_local_workbench_review.sql` now derives the catalog from DEMO_GDS Connection's Tenant and formats all three checks with qualified names. The SQL validator and local-only seed guard are unchanged.

`tests/web_backend/test_database_local_review_seed.py` installs the actual review seed in a sentinel-verified disposable fixture (test-only exact database guard substitution), creates/starts/claims a tool-assisted Conceptual run with installed defaults, exercises real local readers and shared stage/repair/full-graph validation, and verifies a completed run with a validated draft plus three accepted governed queries. Confirmed red with `AgentCandidateValidationError`, then green after the seed correction: **1 passed**; focused Ruff/Pyright clean. Existing preview databases were never connected to or altered by this agent.
