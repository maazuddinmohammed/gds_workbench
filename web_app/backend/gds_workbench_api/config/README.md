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

Mapping stores flexible transformation documents. Output templates provide
advisory field guidance; the backend derives binding identity, provenance,
lifecycle status and integrity constraints. New runs use the seeded global
Object and Attribute templates unless custom IDs are supplied, then freeze
those IDs and schema digests. Existing runs retain their frozen selections.
