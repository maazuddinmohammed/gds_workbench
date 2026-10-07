# Backend constant registries

`workflow_execution.json` defines bounded lease, heartbeat, idle-poll, and
error-poll defaults for the durable Workflow worker. `app_process` runs the HTTP
server and worker together; the worker also has a standalone CLI. Deployment
environment overrides must remain within backend-validated bounds.

`agent_capabilities.json` declares supported providers, models, execution modes,
reasoning options and run limits. `agent_execution.json` leaves request/context
byte ceilings unset (`null`): complete rendered prompts, selected evidence, tool
results, and repair feedback reach the provider without an application size cap.
Providers determine supported input capacity; their failures become safe workflow
diagnostics. Candidate validation and persistence limits remain separate. `analysis_validation.json` controls bounded
relationship validation queries and progress reporting. `profiling.json` bounds
Profiling query size, concurrency, and execution time.

The default model deployments use these reasoning settings in both execution modes:

| Deployment | Explicit reasoning efforts |
| --- | --- |
| `gpt-6.1-sol` | `low`, `medium`, `high`, `xhigh`, `max` |
| `gpt-6-luna` | `none`, `low`, `medium`, `high`, `xhigh`, `max` |

`default` omits the setting; both models default to `medium`. Neither supports
`minimal` or `ultra`. See the official [GPT-6.1 Sol](https://developers.openai.com/api/docs/models/gpt-6.1-sol)
and [GPT-6 Luna](https://developers.openai.com/api/docs/models/gpt-6-luna) contracts.
Foundry must have the configured deployment names available. Tool calls use
Responses; calls without tools use Chat Completions.

Internal keys remain `foundry-primary` and `foundry-gpt-5.6-luna` so saved Model
defaults and operator pricing retain their selected tier. The historical Luna key
now selects GPT-6 Luna. New runs with an unsupported saved effort use the existing
provider-default fallback; this includes Sol's former `none` setting. Stored
defaults and frozen run selections are not rewritten. The request/transport timeout
defaults to 120 minutes (7200 seconds); an explicit `GDS_WEB_AGENT_TIMEOUT_SECONDS`
override still wins. This is a per-model-call timeout, not a total Workflow Run
deadline. Provider credentials refresh before every HTTP request, including retries
and tool turns. Worker claims renew independently every 10 seconds by default.
Tenant Locks remain separate: their default is 60 minutes, and a long run needs a
lock lasting through completion (up to 240 minutes, or explicit renewal).

Mapping stores flexible transformation documents. Output templates provide
advisory field guidance; the backend derives Entity identity, provenance,
lifecycle status and integrity constraints. New runs use the seeded global
Object and Attribute templates unless custom IDs are supplied, then freeze
those IDs and schema digests. Existing runs retain their frozen selections.
