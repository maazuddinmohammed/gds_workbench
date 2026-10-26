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

Both execution modes allow 1–100 agent turns per authoring attempt and 0–25
validation retries. Defaults are 50 turns and 5 retries; saved user selections
take precedence. A retry creates another
authoring attempt with the same selected turn limit; usage and event tracking
support all 26 attempts. The frontend reads these bounds from the capability API.
Matching limits also exist in the fresh-install SQL constraints; changing this
registry alone does not update an installed database or an already-frozen Run.

The default model deployments use these reasoning settings in both execution modes:

| Deployment | Explicit reasoning efforts |
| --- | --- |
| `gpt-6.1-sol` | `low`, `medium`, `high`, `xhigh`, `max` |
| `gpt-6-luna` | `none`, `low`, `medium`, `high`, `xhigh`, `max` |
| `claude-opus-5-5` | `low`, `medium`, `high`, `xhigh`, `max` |

`default` omits the setting; these models default to `medium`. None supports
`minimal` or `ultra`. See the official [GPT-6.1 Sol](https://developers.openai.com/api/docs/models/gpt-6.1-sol)
and [GPT-6 Luna](https://developers.openai.com/api/docs/models/gpt-6-luna) contracts.
Foundry must have the configured deployment names available. OpenAI tool calls use
Responses; OpenAI calls without tools use Chat Completions. Both use JSON mode, which
rejects input messages without the word "JSON"; Responses ignores instructions for
that check, so the backend input always carries `response_format: "JSON object"`.

Claude uses the native Messages API through a custom model in the same Agents SDK
loop. `api_protocol` binds each registry model to its transport. Opus 5.5 always
uses adaptive thinking; `none` and manual thinking budgets are unsupported. Effort
is sent as `output_config.effort`, with `default` omitted. The native assistant
blocks/signatures stay in memory for the current invocation and are replayed
unchanged across tool turns, then discarded. Tools, turn limits, JSON instructions,
and backend candidate validation/repair remain shared; Claude does not receive
OpenAI JSON-mode parameters. Output is capped at its documented 128,000 tokens.
The numeric usage recorder combines Claude's uncached, cached, and cache-write
input counts; missing counters remain unknown. See
[Microsoft's Claude API contract](https://learn.microsoft.com/en-us/azure/foundry/foundry-models/concepts/claude-models)
and [Anthropic's exact effort levels](https://platform.claude.com/docs/en/build-with-claude/effort).
Local fake mode includes Claude. Remote mode exposes it only when its separate
Foundry Anthropic endpoint is configured. The canonical app sets
`GDS_WEB_FOUNDRY_ANTHROPIC_BASE_URL=auto`, which derives the same resource's
Anthropic route from the validated OpenAI endpoint. Custom deployments may supply
the explicit endpoint or omit the setting to exclude Claude; see the deployment guide.

Internal keys remain `foundry-primary` and `foundry-gpt-5.6-luna` so saved Project
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
