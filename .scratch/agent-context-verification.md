# Agent context changes and verification

## Request policy

Web agent execution has no default application byte ceiling for raw templates,
rendered prompts, selected context, individual tool results, cumulative tool
results, or repair feedback. Context settings are `null`, not a larger arbitrary
number. Prompt and SQL-guide authoring endpoints and workflow commands also bypass
the general upload-body limit. Provider capacity determines whether an otherwise
valid request can execute.

Removed input collection ceilings from workflow selections, Mapping preparation,
Code Generation, Validation, and enrichment. Tool readers still page records with
stable cursors; pagination does not discard records. Enrichment still processes
description units/batches rather than combining unrelated write targets.

Authorization, tenant isolation, selected-scope identity, revisions, locks,
idempotency, prohibited-content checks, and output/persistence validation remain.
Configured turn/retry budgets and deterministic SQL execution safeguards remain.
Stored field constraints and bounded MCP snapshot/export APIs are distinct from
the web agent request policy. Explicit bounded configurations remain testable.

## Failure behavior

Provider context exhaustion, output truncation/refusal, rate limits, timeout,
authentication/access rejection, unavailable providers, invalid provider requests,
tool failures, and turn exhaustion produce fixed public diagnostics. Provider
response bodies, prompts, credentials, and tool dumps are not exposed. Truncated
responses cannot become accepted candidates or trigger subsequent tool execution.
Enrichment preserves successful units and records safe warnings for failed units.

## Mode coverage

| Workflow | Supported execution |
|---|---|
| Analysis, Conceptual, Logical, Dimensional, Mapping | One-shot and tool-assisted |
| Code Generation, Validation | Tool-assisted |
| Object and Attribute Enrichment | One-shot |

This change preserves mode availability; it does not add opposite modes to the
last two groups. Profiling and Analysis validation are deterministic SQL tasks.

## Verification boundaries

Tests use synthetic input and fixture-created disposable PostgreSQL containers
with random credentials and per-run sentinels. Actual SDK transport tests use
in-memory HTTP responses. Workflow integration tests use the local fake agent.
These prove request delivery, tool contracts, failure handling, workflow state,
draft validation, and governed apply; they do not establish live-model output
quality or a provider's maximum usable context.

Prompt details and field rationale: [prompt audit](agent-prompt-quality-audit.md).
SDK and failure details: [failure audit](agent-failure-audit.md).

Database function changes and revised seeded defaults are fresh-install source.
Existing populated databases and custom/published prompt versions have not been
rewritten. No migration, backfill, external deployment, or live provider call was
performed.

## Final results

- Full MCP, backend, SQL, packaging, and plugin Python suite: **3,041 passed,
  89 skipped** (213.68 seconds). Platform-specific skips remain; they are not
  counted as executed tests.
- Frontend: **406 passed**, TypeScript and production build passed.
- Plugin JavaScript: **95 passed**. VS Code extension: **92 passed**, types and
  bundle passed.
- Backend and MCP Ruff and Pyright passed. Relevant diff whitespace checks passed.
- Web source ZIP and MCP ZIP rebuilt locally; MCP manifest matched all 94 packaged
  source files. Nothing published.
- Disposable PostgreSQL integration tests exercised Analysis, Conceptual, Logical,
  and Dimensional in both supported modes; Mapping in both modes through downstream
  Code Generation and Validation. Tests cover real readers, draft validation,
  apply, replay, revision checks, and safe failure handling with fake agents.
- Browser verification on the refreshed local preview completed a tool-assisted
  Conceptual run and applied its draft successfully. The temporary Tenant Lock
  was released afterward. Preview: <http://127.0.0.1:9083>.

The browser run exposed invalid two-part target names in the local demo Validation
queries. The seed now derives the configured catalog and builds governed
three-part names; a disposable-database regression test covers the full Conceptual
run against this seed. The existing preview and data on port 9082 were preserved.

All implementation and audit agents used Astra. Local fake-agent responses and
in-memory SDK transport tests made no live provider requests; live model output
quality and provider capacity remain unverified.
