# Repository execution rules

These rules apply to every file and command in this repository.

## Strict Rules

- Be extremely concise. Sacrifice grammar for the sake of consision.
- I haven't developed an mcp server or web applications before. I know python and sql. So when explaining anything I want you to do that accordingly.
- I want you to implement slowly one chnage at a time never build a feature in one go.

## Database and external safety

- Local and CI database tests may use only a fixture-created disposable PostgreSQL container with random credentials, a random database, and a per-run sentinel. Reject user-supplied, environment, default, local-service, Azure, staging, and production DSNs before any connection.
- Never add drop, truncate, reset, destructive cleanup, migration, or backfill helpers for populated databases. Container disposal is the only local database cleanup.
- Do not deploy, push, open a pull request, alter cloud identity/policy, run Databricks, or write to Azure/external systems without explicit approval.

## Security and public surface

- Never commit or log secrets, connection values or strings, bearer/workflow tokens, secret names or references, raw prompts, raw physical rows, raw tool output, or unredacted run dumps.
- MCP must not expose foundational CRUD, Model Scope mutation, direct lock-table toggles, individual graph mutation, arbitrary SQL, delete, secret-returning, file-upload, or code-execution tools. The only arbitrary-SQL exception is the governed `execute_databricks_sql` tool: it may accept multi-statement Databricks SQL, allow reads and unqualified temporary views/tables only, reject persistent DDL and all DML, never return or log credentials, and return at most 50 rows from the final statement. Any future Tenant Lock tool must call only the governed acquire, renew, release, or explicit override operations and preserve their role, ownership, duration, reason, and audit rules.
- Derive actor, Tenant, Model ownership, and authorization server-side. Preserve least privilege, redaction, Tenant Lock protection, revision fencing, and idempotency.

### Code Structure and Abstraction

Optimize for readability, locality, and traceability, not maximum decomposition.

- Prefer fewer, cohesive, moderately larger functions when the logic naturally belongs together.
- A primary function should expose enough of the execution flow that a developer can understand it without repeatedly jumping between helpers/files.
- Do not create helpers merely to shorten a function or abstract a few simple lines.
- Avoid trivial wrappers, pass-through functions, one-use helpers, excessive call depth, and abstractions based only on hypothetical future reuse.
- Keep logic inline when it is simple, used once, and clearer in context.
- Extract logic when it provides meaningful value: reuse, substantial complexity, a clear domain operation, independent testing, or an architectural boundary such as database access, authentication, validation, or external I/O.
- Do not use function length as the primary metric. A larger cohesive function is preferable to many tiny functions when it improves understanding.
- Before creating an abstraction, ask: --Does this reduce cognitive load, or does it just make the reader navigate elsewhere?--
- During refactoring, actively look for unnecessary indirection and consolidate it where doing so improves readability without introducing meaningful duplication.
- Make fewer, more meaningful abstractions—not simply fewer functions.

## Agent skills

### Issue tracker

Local Markdown under `.scratch/`. See `docs/agents/issue-tracker.md`.

### Triage labels

Default five-label vocabulary. See `docs/agents/triage-labels.md`.

### Domain docs

Single-context: root `CONTEXT.md`, with ADRs under `docs/adr/`. See
`docs/agents/domain.md`.
