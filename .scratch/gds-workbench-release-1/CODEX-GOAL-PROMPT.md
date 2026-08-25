# GDS Workbench Release 1 — Codex goal prompt

Copy everything from `## Goal` onward into the same Codex task as one `/goal`
request. Keeping it in this task gives the goal access to the full design
conversation. If a new task is used, attach this file and the handoff named under
“Read first”; a new task does not automatically inherit this conversation.

## Goal

/goal Complete GDS Workbench Release 1 in `/Users/maazuddinmohammed/main/projects/gds_workbench_v2` without stopping until the canonical database, MCP compatibility, GDS V2 plugin, V2 local Workbench redesign, modular FastAPI backend, modular React frontend, portable workflow Module, Databricks notebook Adapters, local containers, documentation, and complete automated verification satisfy every stopping condition below.

## Outcome and phase order

Deliver one coherent, locally testable Release 1 in this strict order:

1. Finish and verify canonical greenfield database SQL.
2. Update and fully regression-test the existing MCP server for database compatibility.
3. Update and fully regression-test the existing GDS V2 plugin.
4. Restyle only the V2 plugin’s local Workbench using the approved prototype visual language.
5. Finish the production FastAPI backend, React frontend, portable workflow
   Module, and thin Databricks notebook Adapters.
6. Run complete cross-layer, browser, package, and container verification.

Do not start a later phase until the current phase passes its acceptance gate.
Continue automatically after each successful gate. Stop only when every required
condition passes, or when progress truly requires new user authority for an
external or destructive action.

This repository already contains substantial uncommitted and partially completed
work. Do not assume a blank starting point. Inspect the worktree, identify what is
complete, preserve user changes, and continue from the current state. Never reset,
clean, overwrite unrelated edits, or recreate intentionally removed legacy plugin
files. Do not redo a completed slice merely because this prompt describes it.

Do not deploy, push, open a pull request, connect to a populated/local-service/
staging/production database, execute Databricks, invoke a live model provider,
change Azure configuration, or write to any external system. Azure-ready images
and documentation are required; a live deployment is not.

## Read first

Read these completely before implementation:

- `AGENTS.md`; it is mandatory and overrides this prompt on execution or safety.
- The complete conversation in this Codex task. Later decisions override earlier exploration.
- `/private/tmp/gds_workbench_web_app_handoff_2026-08-22.md` as historical context; its old “Exact next question” is obsolete.
- `CONTEXT.md` and every ADR under `docs/adr/`.
- `docs/agent-product-blueprint/`, all workflow documents, `docs/architecture/`,
  `docs/security.md`, `docs/design/RELEASE-1-DECISIONS.md`, and `docs/traceability.md`.
- Every numbered file and README under `database/`.
- The complete MCP implementation and `tests/mcp/`.
- `plugins/v2/gds/`, `plugins/build_gds_v2_plugin_zip.py`, and `tests/plugin_v2/`.
- V1 plugin visuals only as a design reference; V2 remains the functional source.
- `web_app/prototypes/model-workflow/README.md` and the complete interactive prototype.
- Existing `web_app/backend/`, `web_app/frontend/`, and their tests before adding or reorganizing code.

Before editing, update `.scratch/gds-workbench-release-1/TRACEABILITY.md` with a
concise matrix mapping each requirement to its database objects, MCP contracts,
plugin behavior, backend routes/services, frontend routes/screens, and tests. Keep
the matrix current after every slice.

### Decision precedence and required reconciliation

Some canonical documents still contain earlier exploratory decisions. Do not
silently choose between contradictions. Before Phase 1 implementation:

1. Create `.scratch/gds-workbench-release-1/DECISION-SUPERSESSION.md` with one row
   for every conflict, the old source, the final Release 1 rule below, affected
   contracts, and the canonical documents that must change.
2. Update `CONTEXT.md`, the relevant ADRs, `docs/design/RELEASE-1-DECISIONS.md`,
   workflow documents, architecture/security documents, and `docs/traceability.md`
   so they agree with the final rules below.
   Add one accepted ADR for portable application Workflow execution covering the
   Module/Adapter boundary, notebook PostgreSQL transport, workload identity,
   exact-Run claims, Tenant Lock/Apply limits, packaging, and secret handling.
3. Treat the scratch traceability file as the live execution ledger. Treat
   `docs/traceability.md` as the canonical released-invariant record. Synchronize
   proven final behavior into the canonical record at every phase gate.

For this Release 1 goal, these later decisions supersede older conflicting text:

- Profiling uses SQL Warehouse connector execution and one optional explicit Batch
  ID; it does not require environment/mode fields, Connection batch arrays,
  Spark, Databricks Jobs, or automatic batch discovery. The web backend never
  launches a notebook. An optional thin Databricks notebook Adapter may invoke
  the same portable Profiling Module used by the backend worker.
- Mapping is either free-form or validated by a dynamically selected Output
  Template. Do not freeze Mapping to `mapping.standard@1.0.0`,
  `GeneratorDocumentV1`, or a fixed artifact-type document. Code Generation is a
  separate workflow that reads applied Mapping.
- Naming is agent-controlled through injected Model naming instructions. Do not
  deterministically rename or perform a deterministic naming-policy projection.
- Agentic authoring produces a validated candidate and explicit Model Change Set
  handoff. It never immediately applies authoritative Model records.
- `application.replace_model_scope` is the explicit web-only governed exception
  for atomic Model Scope membership replacement. It is not exposed through MCP
  and is not implemented as ordinary direct DML. Update the older statement that
  every Scope membership change must use a Model Change Set.
- Mapping Code Generation is read-only with respect to applied Model and Mapping
  state, physical platforms, and deployment. Persisting application Workflow Run
  and SQL artifact state in `application` is allowed and is not a Model mutation.
- The new Databricks notebooks are application execution Adapters, not the older
  MCP-based jobs design and not a second workflow implementation. Older documents
  that forbid every notebook or require every Databricks workflow to execute
  through MCP are superseded only for these application-owned notebook Adapters.
  MCP architecture and public behavior remain unchanged.
- An approved notebook Adapter may connect directly to PostgreSQL using validated
  deployment configuration solely to call governed application repository/
  database Interfaces for an exact frozen Run. It has no arbitrary SQL or direct
  table-write Interface. Narrow `docs/traceability.md` statements that say
  Databricks can never connect to metadata PostgreSQL so they continue to forbid
  MCP/jobs/agent access while documenting this one application Adapter exception.
- “V2 Local Workbench” means the plugin’s local-only HTML/CSS/JavaScript review
  interface. “GDS Workbench Web Application” means the FastAPI/React product.
  Never use the unqualified name when authority could be confused.
- Local synthetic identity still enforces the selected synthetic Principal’s real
  database role, visibility, Tenant Lock, revision, idempotency, and audit rules.
  This supersedes ADR 001 text that allowed local mode to skip role/visibility checks.

## Working method

- Implement one coherent change at a time. Run the narrowest test first, then the phase suite.
- Use TDD for database contracts, authorization, state transitions, workflow orchestration, and API behavior.
- Fix root causes. Never weaken assertions, skip failures, add fake production handlers, or leave disconnected controls.
- Preserve existing domain language exactly: Tenant, Principal, Tenant Lock, Model,
  Model Scope, Section, Change Set, Workflow Run, Target Registration, Mapping, and Code Generation.
- Keep MCP architecture and coding style unchanged except where compatibility requires a focused edit.
- Do not force the web application into the MCP file structure. The web application
  must use a simple industry-standard modular monolith: cohesive vertical feature
  modules, explicit core/integration boundaries, low coupling, clear dependency
  direction, and no microservices or abstraction explosion.
- Prefer readable, local execution flow. Extract modules only for real feature,
  domain, database, authorization, validation, or external-I/O boundaries.
- FastAPI and MCP are separate adapters. FastAPI must never call MCP over HTTP.
  Share domain/application behavior only where it is genuinely common.
- The web backend owns one transport-neutral workflow application Module.
  FastAPI routes/workers and Databricks notebooks are thin Adapters to the same
  public Interface. Orchestration, eligibility, prompt resolution, validation,
  repair, reconciliation, authorization checks, persistence, idempotency, and
  safe event production exist once in that Module.
- The portable workflow Module imports no FastAPI, HTTP/SSE, notebook, `dbutils`,
  widget, Spark, or environment-file APIs. Those belong only to composition-root
  Adapters. MCP neither imports nor uses this Module.
- The backend is authoritative for identity, Tenant/Model derivation,
  authorization, locks, eligibility, validation, normalization, digests,
  reconciliation, workflow state, idempotency, and atomic writes.
- The frontend owns presentation, interaction, and temporary unsaved state. It may
  mirror bounded validation for feedback, but the backend always revalidates.
- Update canonical documentation and traceability with each implemented behavior.
- Do not commit or push unless separately requested.

### Durable run authority

- The authenticated human Principal must have `workbench.access` and is the run
  initiator. At run creation the
  backend derives that Principal, verifies Model/Tenant authorization, verifies
  that the initiator owns the active Tenant Lock, and freezes the initiator ID,
  expected Model revision, selections, prompts, and configuration. Before the Run
  becomes claimable, the backend also server-selects and immutably freezes the
  exact expected workload executor Principal. A claim may never first-assign,
  replace, or rebind that executor.
- A separately registered active Super Admin workload Principal with the existing
  `workbench.workflow` operation is the executor. It may claim/renew/release only
  Workflow Run leases and execute the bounded workflow selected by the run.
- The executor never impersonates the initiator and never stores or reuses the
  human bearer token. Audit both initiator and executor identities.
- The executor may persist safe run events, the explicitly allowed per-Object
  deterministic Profile result, one fully validated immutable candidate, and a
  validated Generated SQL artifact attached to the Workflow Run. It may not use
  the human’s Tenant Lock, create/apply an authoritative Model Change Set as that
  human, or mutate applied Model/Mapping records.
- Candidate review and Model Change Set handoff/Apply require a fresh
  human-authenticated request. In one transaction the backend derives that human,
  verifies `workbench.access`, verifies that the same human currently owns the
  unexpired Tenant Lock, rechecks Model revision/eligibility/candidate digest, and
  records the reviewer/apply actor separately from the run initiator and executor.
  A different authorized human may review/apply only while owning the lock; the
  change audit must preserve all three identities.
- If authority, lock ownership, revision, eligibility, digest, or claim changes,
  fail safely before its respective boundary. The worker never acquires/overrides
  a lock, switches actors, partially writes business rows, or uses stored human authority.

### Databricks notebook execution authority

- Release 1 notebooks are a worker-failover execution path for an existing,
  human-authorized, frozen Workflow Run. A notebook receives only a bounded
  Workflow Run ID and loads every business/configuration value from that exact
  frozen Run. It never accepts a Principal ID, Tenant role, policy, claim token,
  database role, lock ownership, or workflow override as input.
- Add one governed operation that lets the verified registered workload
  Principal claim one exact eligible Workflow Run ID. It must verify the Run's
  workflow kind, state, Model/Tenant binding, frozen revision/configuration,
  workload Principal, lease, and expiry before returning an opaque rotated claim.
  It must never claim another Run merely because that Run is older.
- The notebook uses the same claim, heartbeat, recovery, retry, event, candidate,
  and terminal-state services as the normal backend worker. A browser-issued or
  notebook-issued Run ID is only a lookup handle and never authority.
- Production notebook PostgreSQL authentication uses the Databricks cluster/task
  managed identity through the approved Azure credential chain. The identity
  Adapter requests a short-lived Azure Database for PostgreSQL Entra token;
  PostgreSQL validates it and establishes the unique Entra-bound `session_user`.
  Caller-controlled Python never declares or proves the Principal by itself.
- The governed claim maps exact `session_user` to the active registered Super
  Admin workload Principal and compares it to the Run's frozen executor. For this
  direct-database notebook Adapter only, current membership in the NOLOGIN
  `gds_notebook_runtime` grant role is the canonical database-side enforcement of
  the existing `workbench.workflow` operation. Web/backend Entra authorization is
  unchanged. The server-side identity mapping plus current role membership is the
  notebook authorization boundary. It never
  supplies a human initiator, grants a Tenant role, owns/borrows a Tenant Lock, or
  permits Change Set Apply. Missing, inactive, ambiguous, password-authenticated,
  or mismatched identity fails before a claim/workflow call. Tokens and claims are
  never logged or stored.
- Treat the managed identity's Azure PostgreSQL login and existing
  `workbench.workflow` provisioning as deployment prerequisites. Document them
  with placeholders only; do not create/change Azure identity, app roles,
  PostgreSQL resources, or policy in this goal.
- Notebooks never impersonate the human initiator, acquire/renew/release/override
  a Tenant Lock, create or Apply an authoritative Change Set, mutate Model Scope,
  or expose direct business-table DML. Candidate review and Apply remain fresh
  human-authenticated, owned-lock actions.
- Cold-starting a brand-new Run while both frontend and backend are unavailable is
  outside this safe Release 1 notebook Adapter until a separate governed
  automation-initiation policy defines initiator identity, lock ownership, audit,
  and Apply authority. Do not use a PostgreSQL admin credential to bypass that
  missing policy.

## Non-negotiable domain and security invariants

### Identity, authorization, and Tenant Lock

- Azure Easy Auth/Entra `(tid, oid)` maps server-side to `security.principal`.
  Never accept actor, Tenant role, Model ownership, or policy from the client.
- A synthetic identity is allowed only in an explicit local-test mode.
- Active Tenant is the only global app context. Select a Model only inside Model routes.
- A Model belongs to one owner Tenant while its Model Scope may contain Objects from multiple source Tenants.
- Preserve existing role and Tool Policy semantics. Reads require visibility/access;
  metadata writes require the metadata-write capability and an owned Tenant Lock;
  Model/workflow writes require model-write capability and an owned Tenant Lock.
- Tenant Lock actions are explicit: acquire, renew/extend, release, and authorized
  override/revoke. Override force-releases; it never silently acquires the lock.
- Never auto-acquire, auto-override, broaden authority, or make an agent manage locks.
- Super Admin does not bypass another Principal’s lock, revision fence, audit, or operation boundary.
- Recheck actor, authorization, owned lock, Model revision, eligibility, and digest
  in the same transaction immediately before any authoritative commit.

### Existing metadata ownership rule

- `core.tenant.gds_connection_id` remains the designated GDS connection.
- `core.tenant_metadata_discovery_scope` remains the sole Connection + Zone +
  normalized schema-to-Tenant assignment rule. It supports multiple schemas.
- Do not replace, duplicate, or reinterpret that rule. Do not add schema or Tenant columns to Model Scope.
- Databricks connection values are resolved only by the existing secure application
  integration mechanism used by both approved execution Adapters.
  Host, HTTP path, token, DSN, secret name/reference, or credentials must never
  reach browsers, prompts, normal logs, events, or API responses.

### Governed records and workflow provenance

- Preserve Metadata Change Sets, Model Change Sets, staged chunks/batches, server
  validation, action review, revision fencing, idempotency, and atomic Apply.
- No autosave or direct authoritative per-cell write. UI edits/imports become
  complete pending records, are reviewed, server-validated, and explicitly applied.
- Agentic authoring has no partial business writes. Persist a candidate only after
  the complete contract passes backend validation. Repair exhaustion fails
  explicitly and writes nothing partial. Deterministic Profiling uses the separate
  per-Object atomicity rule under “Required screens and flows.”
- Agents never delete, unlock, acquire a lock, deactivate, or silently replace locked authored values.
- Preserve nullable `agent_run_id`. All application `workflow_run_id` provenance
  columns are nullable because MCP/manual governed paths remain valid without an
  application Run.
- Workflow provenance never determines structural validity or insertability.
- Use `model.model_event_log` as the broad append-only safe event stream. Store only
  bounded stage/status/count/error summaries; never raw context, prompts, output, SQL, rows, or tool dumps.
- Direct physical-row access by agents is off in Release 1. No vectors/RAG in Release 1.

## Phase 1 — canonical greenfield PostgreSQL

Audit and complete the canonical numbered SQL directly. This is a fresh PostgreSQL
18 deployment contract, not a migration. Add no migration, hotfix, backfill,
compatibility, reset, drop, truncate, or destructive cleanup helper.

Run `database/00_preflight.sql`, install `01_reference.sql` through
`12_runtime_integrity.sql` in documented lexical order, then run
`13_verify_install.sql`. When a contract changes, update its owning SQL,
`10_workflow_eligibility.sql`, runtime grants, integrity checks, install
verification, README, safe seed, and tests together.

Follow existing database conventions exactly:

- singular lowercase `snake_case` tables and columns;
- `<entity>_id` identifiers and fully descriptive foreign-key names;
- neighboring-schema identity-key, bounded `VARCHAR`, `TEXT`, `JSONB`, digest,
  status, active/audit, composite witness, and index patterns;
- `pk_`, `fk_`, `uq_`, `ck_`, `ix_`, and `ux_` naming;
- `created_time`, `created_by`, `updated_time`, `updated_by` where applicable;
- `ON DELETE NO ACTION`;
- fixed-signature governed mutations using `SECURITY DEFINER`, safe fixed
  `search_path`, PUBLIC revocation, and exact runtime grants;
- bounded `STABLE SECURITY INVOKER` read helpers where appropriate.

Preserve separate runtimes: `gds_mcp_runtime → gds_app_write` and
`gds_web_runtime → gds_web_write`. The `application` schema is application-owned;
approved FastAPI/worker and notebook Adapters may reach it only through their
governed Interfaces. It must not become a new MCP public surface.

Add a dedicated NOLOGIN `gds_notebook_runtime` grant role with only the exact
read, claim/heartbeat, safe-event, validated-result/artifact, and terminal-state
function grants needed by notebook failover. It must be a non-owner,
non-superuser, non-`BYPASSRLS` role with no broad web/MCP role membership, direct
business-table DML, arbitrary SQL function, or Change Set Apply authority.
An operator provisions one dedicated LOGIN role for each approved workload
Principal and grants it only `gds_notebook_runtime`. Extend the canonical Entra
Principal identity record with nullable unique
`notebook_database_role_name VARCHAR(63)` for this server-owned binding; require a
trimmed valid PostgreSQL identifier and allow it only for an active service
Principal.
Governed notebook functions derive the executor from exact `session_user` through
that binding and compare it to the Run's immutable expected executor. They never
accept or trust a Principal ID, `(tid, oid)`, actor kind, role, GUC, or notebook
assertion. Every claim, heartbeat, safe-event, result/artifact, recovery, and
terminal-state function must recheck active Principal/Super Admin status, exact
executor binding, and current `gds_notebook_runtime` membership; revocation must
stop an already-open session before its next write. Connection readiness must
reject a PostgreSQL administrator/superuser,
object owner, `BYPASSRLS`, role creation, any membership beyond the one notebook
grant role, or the ability to switch to any privileged/unexpected role before the
first workflow read/write. An administrator credential is not an accepted Release
1 notebook configuration even when supplied through an environment file. The
production notebook connection must use server-validated Entra authentication;
reject a configured static PostgreSQL password.

The final `application` contract uses these 15 existing singular table names;
audit/complete them rather than inventing parallel tables:

1. `principal_preference`
2. `workflow_stage`
3. `workflow_stage_variable`
4. `prompt_template`
5. `prompt_template_version`
6. `prompt_assignment`
7. `output_template`
8. `output_template_field`
9. `sql_generation_guide`
10. `sql_generation_guide_version`
11. `workflow_run`
12. `workflow_run_object_selection`
13. `workflow_run_mapping_target_selection`
14. `workflow_run_prompt_snapshot`
15. `generated_sql_artifact`

Required semantics:

- Principal preference stores only last-accessed Tenant and time.
- Workflow stages define workflow, explicit execution mode where relevant, order,
  and agentic/deterministic classification.
- Stage variables define allowed placeholder, resolver key, type, required flag,
  description, example, and order.
- Prompt templates have stable identity plus immutable numbered versions containing
  system, instruction, optional tool instructions, safe digest, and
  draft/published/retired lifecycle. Published versions are never edited in place.
- Prompt ownership is global or Tenant-owned. A Tenant prompt may be assigned only
  to a Model owned by that Tenant. Cross-source-Tenant scope does not change prompt ownership.
- Prompt resolution is `explicit run override → Model assignment → global default`.
  Resolve and snapshot every exact version/digest atomically when the run is created.
  Publishing later cannot alter an active run or repair attempt.
- Unknown/unregistered placeholders remain literal and produce a safe warning.
  Missing required registered variables fail before provider invocation.
- Output templates are globally reusable headers plus ordered typed fields for
  structured Mapping Object/Attribute output. Null means free-form. Keep them
  separate from prompt templates and SQL generation guides.
- SQL generation guides are globally reusable, versioned/audited application
  configuration managed through the web UI and consumed by the portable Module.
- The provider/SDK/model/reasoning registry is validated JSON packaged with the
  portable workflow distribution, not database metadata.
- One Model-level default stores SDK/provider/model/reasoning/max-turn/repair-retry
  codes. There is one default for the whole Model, not per workflow. Every run may override it explicitly.
- Profiling and Analysis validation are deterministic and have no prompt.
- Workflow Run stores safe configuration, frozen Model revision, explicit mode,
  selected/all coverage, selections/digests/counts, state, attempts, correlation,
  claim/lease/recovery data needed for multi-replica execution, and bounded safe failure metadata.
- Workflow Run separately records the human initiator and workload executor. A
  workload claim never changes, aliases, or impersonates the human initiator.
- Add an exact-Run governed claim operation for notebook failover. It accepts a
  Run lookup handle only, derives the workload executor from the database session
  binding, checks that it equals the Run's non-null immutable expected executor,
  then checks the expected workflow kind and every ordinary claim invariant,
  and issues the same opaque rotated claim used by the backend worker. PUBLIC and
  MCP runtimes receive no access to this operation.
- Analysis inference and validation remain one `workflow.analysis_result` row.
  Inference and validation provenance are independently nullable; validation grouping
  is nullable with all-or-none integrity. Do not add a second analysis result table.
- Preserve normalized Conceptual, Logical, Dimensional, support/source/submodel,
  Mapping Object, Mapping Attribute, and Mapping source-System dependency tables.
- Mapping may be free-form or output-template validated; preserve normalized business rows.
- Generated SQL identity is exactly `Model + modeled layer + target Object`, not
  source System. One artifact aggregates all active contributing source Systems,
  Mapping/source-context digests, frozen guide/version/digest, and Model revision.
  A failed regeneration never destroys the previous successful artifact. Stale
  artifacts remain readable to authorized users and are clearly marked stale.
- Extend `model.model_event_log` only with minimal nullable Workflow Run,
  sequence, stage, attempt, and ordering fields; keep it append-only and safe.
- Seed only stable stage/variable/non-sensitive reference rows in
  `database/seed/04_application_reference.sql`. Never seed real prompt/guide bodies,
  secrets, connection values, or physical/business rows.

Database tests may use only the fixture-created disposable PostgreSQL 18 Docker
container with random credentials, random database, per-run sentinel, canonical
install, verification, and container disposal. Reject supplied/environment/default/
local-service/Azure/staging/production DSNs before connection.

Phase 1 gate:

- clean canonical install and `13_verify_install.sql` pass;
- exact tables/counts/docs/grants match;
- prompt versioning, assignment, ownership, resolution, freezing, and placeholder behavior pass;
- lock/role/revision/idempotency/tenant-isolation negative tests pass;
- nullable provenance permits MCP/manual records;
- Mapping templates, Workflow Run lifecycle/lease, event ordering, and target-first artifact replacement/staleness pass.
- Workflow Run initiator/executor separation and the exact-Run notebook claim
  operation pass workload-identity, wrong-workflow, wrong-Run, lease rotation,
  expiry, replay, PUBLIC/MCP denial, and audit tests.
- Run creation rejects a null/unregistered/inactive/non-workload expected executor;
  executor binding is immutable. Direct SQL using one valid notebook login cannot
  supply forged identity data or claim a Run bound to another executor.
- `gds_notebook_runtime` install/grant verification proves it is non-owner,
  non-superuser, non-`BYPASSRLS`, cannot switch to any role other than its one
  NOLOGIN notebook grant role, cannot directly mutate any business table, cannot
  manage Tenant Locks or Apply Change Sets, and can execute only its exact
  allowlisted governed functions.
- An active bound Super Admin without current `gds_notebook_runtime` membership
  cannot claim. Revoking that membership after connection prevents the next
  heartbeat, event, candidate/profile/artifact, recovery, or terminal write.

## Phase 2 — MCP compatibility, not MCP redesign

MCP does not use the application prompt library, application Workflow Runs,
output templates, SQL guides, or generated-artifact APIs. Add no MCP prompt CRUD,
application Workflow Run tools, or application-schema public tools.

Change MCP only where canonical database compatibility requires it. Preserve its
architecture, public tools, Tool Policies, governed operations, Change Sets,
snapshots, authorization, local/package behavior, and coding style.

Required alignment:

- active Bronze Model Scope Objects feed Profiling, Analysis, Conceptual, and Logical;
- Dimensional uses eligible active Silver Objects whose applied Logical Mapping establishes contribution;
- Logical Mapping targets registered active Silver Objects/Attributes in Model Scope;
- Dimensional Mapping targets registered active Gold Objects/Attributes in Model Scope;
- Target Registration and adding/reactivating that target in Model Scope are two
  separate explicit Change Sets; neither happens automatically;
- Logical SQL generation is optional for Dimensional eligibility;
- MCP-authored Profile, Analysis, Assertion, Conceptual, Logical, Dimensional, and Mapping rows remain valid with null application provenance;
- existing schema/Zone Tenant discovery rule is unchanged;
- every registered MCP tool still registers, authorizes, validates, returns its
  documented shape, redacts errors, and has contract coverage;
- preserve the current public inventory exactly at 57 tools, 2 prompts, and 0
  resources unless an already-documented Release 1 contract proves a deliberate
  change; application-schema features alone are not such a reason;
- preserve the governed `execute_databricks_sql` exception exactly: multi-statement
  Databricks SQL; reads and unqualified temporary views/tables only; no persistent
  DDL or DML; at most 50 final rows; never reveal credentials.

Do not expose foundational CRUD, direct scope mutation, arbitrary graph mutation,
delete, direct lock-table toggles, upload, arbitrary code execution, secret return,
or any broader arbitrary-SQL capability.

Phase 2 gate:

- full MCP pytest suite passes, including disposable-database tests;
- Ruff format/check and strict Pyright pass;
- complete MCP tool inventory/public-schema/security coverage passes;
- Databricks/provider tests use fakes only;
- existing MCP package/App Service build succeeds with no secret or public-surface regression.

## Phase 3 — GDS V2 plugin compatibility

Update `plugins/v2` only as the current functional plugin. Preserve V1 unless a
shared build/test dependency requires a minimal focused correction. Never resurrect
the deleted legacy `plugins/gds` tree.

- Align V2 skills, contracts, helper scripts, local validation, flows, references,
  packaging, and tests with the finalized database/MCP contracts.
- Preserve the governed human-reviewed local workflow and local-only authority.
- Understand Bronze/Silver/Gold eligibility and the explicit target-registration-then-scope sequence.
- Keep Mapping separate from Model authoring and Code Generation.
- Code Generation consumes applied Mapping, not the Model directly.
- Preserve plugin output choices; web SQL-only scope must not remove plugin capabilities.
- The local Workbench cannot Stage, server-Validate, Apply, deploy, execute code,
  mutate server state, or make network calls.
- Preserve sessions, snapshots/freshness, local Change Sets, review, digest-bound
  overrides, validation, handoff, and one-Apply-boundary behavior.

Phase 3 gate:

- all Python and Node tests under `tests/plugin_v2/` pass;
- existing V1 plugin regression tests remain green without converting V1 into the
  current functional plugin;
- local-helper parity, Unicode, PowerShell fallback where supported, security/
  network blocking, contracts, instruction size, and packaging tests pass;
- `plugins/build_gds_v2_plugin_zip.py` creates a reproducible complete V2 archive.

## Phase 4 — V2 local Workbench visual redesign

Restyle `plugins/v2/gds/workbench/` using the visual language of
`web_app/prototypes/model-workflow/` and the approved V1-inspired contrast:
restrained layout, compact ledgers, clear central focus, strong typography, dark
governed-action surfaces, orange primary actions, blue selections/links,
consistent spacing, reduced clutter, accessible focus, and restrained motion.

This is presentation only. Preserve every dataset, label meaning, local action,
keyboard behavior, validation result, state transition, and security restriction.
Do not copy server-authoritative web controls into the local Workbench. Keep its
classic local HTML/CSS/JavaScript and no-network behavior. Support desktop,
narrow screens, keyboard use, focus visibility, and reduced motion.

Phase 4 gate:

- all existing Workbench behavior tests stay green;
- focused DOM/visual-contract tests avoid brittle pixel matching;
- browser verification covers major screens and interactions at desktop and narrow widths;
- zero console errors and no content/authority regression.

## Phase 5 — production web application

Complete:

```text
web_app/
  backend/    FastAPI + Pydantic + Psycopg
  frontend/   React + TypeScript + TanStack
```

Both applications must be independently installable, testable, buildable, and
containerized, and must run together locally.

### Web architecture

- Backend: simple modular monolith organized by cohesive vertical features, with
  explicit shared `core` concerns and `integrations` for PostgreSQL, identity,
  agent providers, Databricks, files, and event delivery. Within a feature, use
  router/contracts/service/repository modules only when each boundary adds value.
- Frontend: feature-oriented modules containing route/screen, API/query hooks,
  tables/forms/components, and tests; a small shared design system; application
  shell/routing at the top. Avoid global component dumping and duplicated state.
- Do not imitate MCP’s physical file organization. Preserve MCP unchanged except Phase 2 compatibility work.
- Prefer clear, moderately sized modules over giant catch-all files or hundreds of trivial wrappers.
- No microservices, generic workflow framework, repository-per-table ceremony, or speculative provider abstraction.
- Use shared Pydantic/domain contracts only where MCP and FastAPI truly share the
  same business record. Keep web DTOs web-specific.
- Treat architecture as a tested contract, not a subjective cleanup:
  - root frontend client and app files are composition/routing only;
  - production feature modules never import root `api.ts`;
  - feature contracts, transports, query keys, and characterization tests live
    with their owning feature;
  - `shared` and `core` never import a feature;
  - backend and frontend production dependency graphs are acyclic;
  - static deletion/dependency tests prevent retired catch-all modules from
    returning; do not split a cohesive module merely because it is long.

### Portable workflow Module and Databricks Adapters

- Keep the portable Module inside `web_app/backend/`, but make it independently
  importable from the built Python distribution. Do not copy workflow source into
  notebooks and do not make notebooks import FastAPI route modules.
- Preserve feature locality. A workflow feature may own cohesive contracts,
  service/Module logic, repository access, and its FastAPI Adapter. Extract a
  shared workflow abstraction only when it reduces real duplication; do not add
  a generic base-class framework or one repository per table.
- Use composition roots for environment loading and concrete Implementations.
  The FastAPI app/worker composition root and the Databricks bootstrap construct
  the same workflow Interface with the appropriate PostgreSQL, SQL Warehouse,
  agent, clock, and event Implementations.
- Build one versioned wheel that contains the portable Module, its typed contracts,
  and required validated JSON configuration. The notebooks install/import that
  exact wheel; they do not use an editable checkout or depend on MCP internals.
- Select and document one Python-version range supported by both the production
  backend and the target Databricks Runtime. Prove a clean wheel install and import
  under both interpreters before claiming lift-and-shift portability. Do not
  preserve a backend-only Python pin if Databricks cannot run it.
- Add `web_app/backend/databricks_notebooks/` containing:
  - one shared bootstrap/composition helper;
  - `profiling.py`;
  - `analysis_inference.py`;
  - `analysis_validation.py`;
  - `conceptual.py`;
  - `logical.py`;
  - `dimensional.py`;
  - `mapping.py`; and
  - `code_generation.py`.
- Add a concise notebook README and one committed empty/safe example environment
  file. No real environment file is part of the source or wheel.
- Use reviewable Databricks-source Python notebook files. Each wrapper declares
  its one expected workflow kind, loads typed configuration, accepts the exact
  frozen Workflow Run ID, constructs approved Adapters, claims/heartbeats/executes
  that Run, emits only a bounded safe summary, and closes resources.
- A wrapper contains no prompt assembly, SQL construction rules, eligibility,
  authorization, validation, repair, reconciliation, business-table DML, or
  workflow state machine. It must reject a Run whose frozen workflow kind does
  not match the wrapper.
- Do not add notebooks for Metadata, Assertions authoring, Scope mutation, Tenant
  Lock management, Change Set review/Apply, generic CRUD, arbitrary SQL, physical
  deployment, or automatic downstream execution.
- The backend worker remains the normal production executor. Databricks notebooks
  are manually invoked failover Adapters; the web backend does not launch them and
  Release 1 does not require Databricks Jobs or Asset Bundles.

### Backend behavior

- FastAPI, Pydantic, Psycopg, repository-compatible Python tooling, stable error envelopes, OpenAPI, bounded pagination/filtering, health/readiness, and safe structured logs.
- Explicit small adapter contract for the finalized agent paths, including the
  supported Create Agent/provider path and OpenAI Agents SDK path. Do not build a framework for hypothetical providers.
- Direct SQL Warehouse connector execution through an outward integration
  Interface. The FastAPI worker and Databricks notebook Adapter both call the
  same workflow Module. Do not duplicate logic and do not make the web backend
  launch Databricks Jobs in Release 1.
- Durable database-backed run claim/lease/retry/recovery suitable for Azure Container
  Apps multi-replica operation. Do not rely on in-process background tasks as the sole production executor.
- SSE is the default one-way event stream. Add WebSockets only if a proven requirement exists.
- Dependency-injected fake agent and Databricks adapters for local/test mode.
- One failed run must fail gracefully without crashing the app or corrupting prior results.
- The web application exposes no arbitrary-SQL endpoint. Profiling and Analysis
  validation accept typed bounded inputs and build fixed parameterized SQL
  server-side. Generated SQL is stored/downloaded only and is never executed.
- SSE authorization is checked on initial connect and reconnect. Enforce exact
  Tenant/Model/Run isolation, bounded signed cursors, monotonic event ordering,
  bounded redacted payloads, and stable terminal-run reconnect behavior.
- Run claims use rotated opaque digests, never bearer tokens. Reject expired,
  superseded, or mismatched claims and prove that claim loss cannot duplicate or
  partially commit. “Cancellation” means claim loss or orderly worker shutdown in
  Release 1; do not invent a user cancellation route.

### Configuration

- Put bounded non-secret constants in `web_app/backend/gds_workbench_api/config/`
  as separate purpose-specific JSON files, validated at startup with typed models.
- The supported SDK/provider/model/reasoning capability registry has one
  authoritative JSON source packaged with the portable workflow distribution and
  a read-only FastAPI endpoint for the frontend.
- Clients submit only registered SDK/provider/model/reasoning codes. Never accept
  an endpoint, secret reference, SDK implementation path, arbitrary tool, or
  provider configuration from a browser request.
- Frontend JSON may contain presentation-only labels/options, never an authoritative model registry.
- Never put secrets, connection values/references, mutable database metadata, raw
  prompts, SQL artifacts, authorization policy, workflow state, or authoritative validation in JSON.
- Deployment-specific endpoints/secret references come from environment settings;
  no environment-specific hardcoding.
- Add a typed notebook configuration loader at the Databricks composition root.
  It reads one operator-supplied, Git-ignored environment file containing the
  PostgreSQL transport settings and required integration settings. The loader
  constructs concrete PostgreSQL, identity, provider, and SQL Warehouse Adapters.
  The workflow Module receives those ports plus bounded non-secret workflow
  configuration; it never receives connection material or reads the file/process
  environment itself.
- Commit only an example environment file with empty generic placeholders and
  safe non-secret defaults. Ensure real environment files are ignored by Git and
  excluded from wheels, containers, notebook archives, tests, and documentation.
- Never hardcode or display a database username/password, DSN, token, endpoint,
  secret name/reference, workload identity, or environment-specific value in
  Python, JSON, notebook cells/widgets, examples, logs, events, exceptions, or
  result output. This remains true even if an operator plans to use a PostgreSQL
  administrator account.
- Validate required fields, TLS mode, bounded connect/statement timeouts, and
  deployment-owned host/database allowlists before connecting. Redact the entire
  connection configuration on every failure path. Database credentials provide
  transport access only and never replace application authorization.

### Frontend stack and quality

- React and TypeScript.
- TanStack Router, Query, Table, and stable TanStack Form.
- Use the approved prototype as the UX/content contract; absorb its structure and tokens rather than shipping the prototype file.
- Query/cache owns authoritative remote data. Forms/components own only temporary UI state.
- Implement accessible semantic controls, keyboard navigation, focus management,
  loading/empty/error/denied states, responsive layouts, and reduced motion.
- Every visible action must call a real backend contract or be visibly disabled for a real authorization/state reason.

### Required screens and flows

Implement the approved prototype end to end:

- Tenant chooser: search, last accessed, explicit entry, prominent Switch Tenant.
- Tenant Home: Tenant Lock is the focus; correct state-dependent acquire, renew,
  release, explicit override/revoke-then-acquire, and history. Show registered Systems;
  do not restore the removed GDS connection panel.
- Metadata: complete Reference, Foundational, and Operational normalized sheets.
  Reference/Foundation read-only. Operational sheets use sheet-specific filters,
  normalized columns, on-demand details, lock-gated Add/Edit, `.xlsx` Import, and orange Export.
- Excel: canonical sheets/fields, hidden manifest, `.xlsx` only, no macro/formula/
  external link, transient parse, complete pending records, backend diff/validation,
  selected/all operational export, and Change Set review/apply.
- Bound hostile XLSX input before parsing: validate file signature and media type;
  reject encryption, macros, formulas, external links, traversal/duplicate ZIP
  entries, and excessive compressed bytes, expanded bytes, entry count, sheets,
  rows, columns, or cells; enforce parse timeout and guaranteed temporary cleanup.
  Hard ceilings are 25 MiB compressed, 200 MiB expanded, 512 ZIP entries, 64
  worksheets, 100,000 rows per sheet, 512 columns per sheet, 5,000,000 total
  cells, and 64 KiB serialized content per cell, with lower dataset-specific
  limits allowed in typed backend JSON. Ignore client paths, reduce the display
  filename to a 255-scalar basename, use a server-generated isolated temporary
  name, and finish parsing/cleanup within 30 seconds.
- Models ledger, Model create/settings/archive, Model overview/workflow ledger,
  Scope, Profiling, Analysis, Assertions, Conceptual, Logical, and Dimensional.
- Scope Add Objects: source Tenant, System, Zone, Object filters; search/select all;
  governed bulk addition/replacement through the existing web-only
  `application.replace_model_scope` command. The command must derive authorization,
  require the owned Tenant Lock, fence on `model_revision`, audit the revision, and
  keep direct Model Scope DML unavailable. Do not expose this mutation through MCP.
  Only active scope drives downstream work.
- Scope Remove selected computes the complete remaining active Object-ID set
  server-side from an expected revision and submits that full replacement through
  the same `application.replace_model_scope` command. It requires current human
  authorization and owned Tenant Lock; stale or hidden membership fails atomically.
- Profiling: selected/all active Bronze Objects; optional explicit Batch ID; group
  system-coherent execution; add the batch predicate only when both Batch ID and
  Object batch Attribute exist; history, safe events, Attribute results, Run
  details, and an explicit Refresh control.
- The Batch ID request value is trimmed text of 1–256 Unicode scalar values. With
  a Batch ID, the selected Objects must belong to exactly one System. The backend
  validates/converts the value against each Object’s normalized batch Attribute
  type and uses bound parameters only; an unsupported type, conversion failure,
  missing selected Object, or mixed System fails before Databricks execution.
  Without a Batch ID, selections may span Systems and no batch predicate is added.
- Supported normalized batch Attribute families are string, signed 16/32/64-bit
  integer, fixed-precision decimal, date, and timestamp. Parse integers as base-10
  ASCII with exact range checks; decimals as finite base-10 values that fit the
  declared precision/scale with no exponent; dates as exact `YYYY-MM-DD` calendar
  dates; timestamps as RFC 3339 with an explicit offset and normalized to UTC;
  strings preserve the trimmed 1–256-scalar value. Reject booleans, floating
  special values, binary/complex types, lossy conversion, overflow, invalid
  calendar/time values, and metadata without an allowlisted normalized type.
- Profiling atomicity is per Object: publish all Attribute profiles for one Object
  together only after that Object succeeds. A bulk run may complete with bounded
  warnings for failed Objects; never publish a partial set of Attributes and never
  erase the previous successful profile for a failed Object.
- Analysis: separate explicit agentic inference and deterministic validation;
  selected/all active Bronze Objects; from/to Object filter; locks, inactive view,
  history, validation evidence, inference-before-validation support, explicit
  Refresh, inference Run launch, validation Run launch, lifecycle actions, Run
  events, candidate review, and Change Set handoff/Apply. Inference has no Batch
  predicate; deterministic validation may use the same bounded Batch contract.
- Assertions: normalized ledger/detail, governed create/update/activate/inactivate
  authoring, validation, revision fencing, and Change Set review/Apply.
- Conceptual, Logical, Dimensional: ledgers plus dedicated full-page details for
  large normalized support/source/submodel arrays, shared Run history/events,
  candidate review/Apply, lifecycle actions, and explicit Refresh controls.
  Entity/Submodel is many-to-many.
- Mapping: enter through a Model; Dependencies, Object Mapping, Attribute Mapping,
  output-template selection, runs/history/events/governance, Model/type/System
  filters, and dedicated full-page dynamic Mapping-document review. Mapping is
  separate from Model authoring and Code Generation. Include Run history/events,
  candidate review/Apply, lifecycle actions, and explicit refresh.
- Code Generation: enter through a Model and drive primarily by applied Mapping
  target Objects. Filter Model, target Object first, modeled layer/type, and
  contributing Systems. Show stored SQL and current/stale state; regenerate;
  selected/all targets; artifact/run history; individual target-named `.sql` and
  bounded path-safe `.zip`.
- Prompts: global/Tenant visibility, workflow/mode/stage filters, allowed variables,
  system/instruction/tool editor, drafts, immutable publishing, retirement,
  version history, assignment visibility, and safe validation.
- Model Settings → Prompts: effective prompt/version/source by workflow/stage;
  use-global or select allowed Tenant prompt; Model assignment management.
- Administration → Output Templates: Super Admin creates one complete globally
  reusable Object- or Attribute-level template plus all ordered fields atomically,
  including field name, description, typed data type, required flag, and example.
  Code, target type, digest, and fields are immutable; name, description, and
  active state may change. A schema/field change creates a new template with a new
  code/digest. Templates and fields are never deleted.
- Administration → SQL Generation Guides: Super Admin create draft, edit draft,
  publish immutable version, retire version, choose the global default, inspect
  history, and validate rules/examples. No Tenant Lock is required for global-only
  administration because no Tenant-owned state is changed.
- Run dialogs: effective Model agent configuration and prompt configuration;
  explicit per-run provider/model/reasoning/max-turn/repair-retry and prompt overrides.

### Workflow rules

- Every workflow is explicit and user-driven. Earlier artifacts improve quality
  and produce warnings, not blockers, except finalized Dimensional Silver eligibility.
- Profiling, Analysis Inference, Analysis Validation, Conceptual, Logical,
  Dimensional, Mapping, and Code Generation each have one authoritative workflow
  Module implementation. Backend-worker and notebook execution must produce the
  same validated contracts, state transitions, safe events, retry behavior,
  idempotency result, and error codes for the same frozen Run.
- Notebook wrappers never change frozen coverage, selection, mode, model/provider,
  reasoning, prompts, retries, repair count, target list, guide, or template. A
  requested mismatch fails before any external call or persistence.
- Every workflow supports all eligible Objects or an explicit selected subset.
- Profiling is deterministic bulk Databricks SQL and has no prompt.
- Analysis inference is agentic. Analysis validation is deterministic batch-aware SQL and has no prompt.
- Conceptual, Logical, and Dimensional expose exactly three explicit modes:
  One-shot, bounded local Tool-assisted, and Detailed Coverage.
- Never auto-switch modes or silently fall back. Oversized One-shot returns a loud safe error.
- Every mode returns the identical normalized candidate/change-set contract and passes the same backend validation.
- Naming remains agent-controlled through injected Model naming instructions at
  every relevant stage/reconciliation. Do not deterministically rename or block solely on an unmet naming instruction.
- The orchestrator adds configured audit columns to every authored target table exactly as configured.
- Detailed loops follow the finalized workflow documents, including immutable
  original context, coverage stages, deterministic relationship candidates where
  appropriate, agent refinement, submodel reconciliation, whole-model reconciliation,
  final backend validation, and atomic Change Set handoff.
- Validation repair uses the same run, frozen original context, frozen prompt
  versions, prior failures, explicit attempt history, and user-selected retry count.
- Locked rows are protected from agent replacement. Agents never delete. User
  lifecycle actions are separate explicit governed operations. A user with the
  existing Model-write capability and owner Tenant Lock may lock/unlock and
  activate/inactivate eligible Analysis, Conceptual, Logical, Dimensional, and
  Mapping rows through revision-fenced audited operations. Inactive rows remain
  viewable when requested. Hard delete and dependency-tree delete are explicitly
  outside Release 1.
- Mapping supports free-form or selected output-template validation; its document
  must contain enough normalized information for SQL generation.
- Web Code Generation is SQL-only, validates Databricks SQL syntax, persists one
  latest-successful artifact per Model + layer + target Object, never executes or
  deploys SQL, and preserves the old artifact after failure.
- Code Generation context aggregates all current applied Mapping source Systems.
  Generate one target per provider call or a bounded orchestrated batch; do not
  ask one provider response to return an unbounded collection.
- No automatic downstream run, automatic Apply, implicit fallback, hidden state
  transition, or partial agentic business write. The only bounded bulk exception
  is deterministic Profiling’s explicitly defined per-Object atomic publish.

### Prompt behavior

- Backend assembles bounded metadata-only context from active Model Scope,
  Profiles, Analysis, Assertions, and applicable applied Model records. No raw rows.
- Prompt variables are stage-allowlisted and backend-resolved.
- Placeholder rendering is bounded literal substitution only. Support the one
  documented placeholder syntax and maximum placeholder/template/rendered sizes;
  do not use Jinja or any evaluator and do not permit expressions, property/index
  access, function calls, includes, loops, conditionals, filters, code execution,
  or recursive expansion. Unknown placeholders stay literal with a safe warning.
- Prompt library/assignment is application-owned and web-managed. The portable
  workflow Module resolves it identically for backend-worker and notebook
  execution. MCP does not consume it.
- Tenant readers can view usable prompts. Tenant prompt mutation and Model
  assignment require existing model-write authorization plus the owner Tenant Lock.
  Global prompt mutation is Super Admin-only and needs no Tenant Lock because it
  changes no Tenant-owned state. Per-run override accepts only a compatible
  published Prompt Template Version ID visible to the Model owner Tenant; never
  accept inline prompt text, a draft version, or a version for another stage/mode.
- Each run freezes exact effective prompt versions/digests before provider invocation.
- Never persist/log rendered prompts, raw provider envelopes/responses, raw tool
  dumps, or hidden reasoning. Persisting only a contract-validated normalized
  candidate, safe validation findings, and the final generated SQL artifact is
  required and is not considered persistence of raw provider output.

## Local and Azure Container Apps readiness

- Separate backend and frontend Dockerfiles with pinned deterministic installs,
  small non-root runtime images, health checks, and no embedded credentials.
- Frontend production container may use a simple static server/reverse proxy.
  Backend remains a separate container.
- Provide one simple local orchestration path using the real React app, real
  FastAPI app, disposable PostgreSQL, and fake agent/Databricks adapters.
- Synthetic identity is permitted only when the exact validated setting is
  `GDS_ENVIRONMENT=local`. Local mode still enforces real role, Tenant Lock,
  revision, idempotency, audit, and business rules; it changes only the identity
  source and external adapters.
- Local and CI test paths must reject real DSNs and external endpoints before
  connection. Production composition roots may accept only their validated,
  operator-supplied environment configuration.
- Document Azure Container Apps shape only: Easy Auth expectations, ingress,
  frontend/backend URLs, CORS/reverse proxy choice, probes, PostgreSQL and secret
  references, stateless scaling, durable run worker/lease behavior, and replica assumptions.
- Azure documentation may use placeholders and integration patterns only. Never
  include a real secret name/reference, connection value, Tenant identifier, or endpoint.
- Do not create or change Azure resources.

## Phase 5 gate

- Every required backend route and frontend control is implemented, connected,
  authorized, validated, and covered; no placeholder or in-memory production state.
- Backend unit plus disposable-PostgreSQL integration tests pass.
- Ruff format/check and strict Pyright pass.
- Frontend typecheck, unit/component tests, and production build pass.
- Static architecture/deletion tests prove every dependency rule under “Web architecture.”
- The backend wheel installs and imports cleanly under both selected backend and
  Databricks Python interpreters, contains every required validated JSON asset,
  and contains no secret/environment file or editable MCP dependency.
- All eight required notebook wrappers import and smoke-run with fakes without
  import-time external access. Static tests prove they contain no business logic
  and the portable Module imports no FastAPI, HTTP/SSE, notebook, `dbutils`,
  widget, Spark, or environment-loading API.
- Identity-Adapter tests prove managed-workload Azure PostgreSQL token acquisition
  with fakes, correct resource/audience request, token-acquisition/expiry failure,
  server-derived session mapping, inactive/unregistered/non-Super-Admin or
  wrong-operation Principal, and proof that environment/widgets/naked IDs cannot
  select the Principal. Production static-password configuration is rejected.
- Adapter-parity tests feed the same frozen Runs through backend-worker and
  notebook Adapters and prove identical Module calls, safe events, terminal
  outcomes, error codes, retry behavior, and no-partial-write behavior.
- Disposable-PostgreSQL tests prove exact-Run notebook claims cannot select a
  different Run or workflow, cannot derive authority from a DSN/widget, rotate
  opaque claims, honor heartbeat/expiry/takeover, and preserve lock, revision,
  eligibility, digest, and idempotency fences.
- Notebook readiness rejects administrator/superuser, owner, `BYPASSRLS`,
  role creation, privileged/unexpected role-switch capability, and unexpected
  membership configurations before any workflow query; tests use fixture-created
  disposable roles only.
- API tests prove Tenant isolation, roles/locks, stale revisions, idempotency,
  bounded pagination/filter/download behavior, redacted errors, and no secrets.
- UI tests prove routing, tables, forms, query invalidation, permissions, detail
  routes, loading/empty/error/denied states, and critical accessibility behavior.

## Phase 6 — end-to-end verification

Create a deterministic verification path using only disposable/test components.
Use mocks/fakes only at true external agent, Databricks, Easy Auth, Azure, and
secret-provider boundaries. Do not mock FastAPI away in browser E2E: run the real
frontend, real backend, and disposable canonical PostgreSQL together.

Required proof:

- clean database install, constraints, secure functions, grants, seed, integrity, and verification;
- every MCP tool contract and existing MCP regression;
- every V2 plugin flow, helper, Workbench validation/security boundary, and package;
- backend unit and disposable-database integration;
- portable Module unit tests, backend/notebook Adapter parity, wheel inspection,
  and every notebook import/smoke test;
- frontend unit/component tests;
- browser E2E for Tenant selection and every lock state; Metadata view/edit/
  import/export/review; Model Scope; all workflow launch/history/result/detail;
  row locks/lifecycle; prompt draft/publish/assign/run override; Mapping review;
  target-first stored SQL generate/regenerate/stale/download; denied states;
- event ordering, reconnect, retry/repair, cancellation/timeout, and safe failures;
- initial and reconnect SSE authorization, exact Run/Tenant isolation, bounded
  cursor behavior, monotonic sequence, terminal reconnect, and payload redaction;
- expired/rotated/mismatched run-claim rejection, lease takeover, duplicate-commit
  prevention, initiator/executor separation, and safe failure after lock/role/revision loss;
- exact-Run notebook claim rejection for wrong workflow, Tenant, Model, state,
  revision, workload Principal, lease, or expiry; notebook input and PostgreSQL
  credentials never select actor/role/policy/lock ownership;
- human initiators require `workbench.access`; executors require active Principal
  registration, Super Admin, and `workbench.workflow`; worker-produced candidates
  cannot use a human lock, and only a fresh human-authenticated owned-lock request
  can create/review/apply the authoritative Change Set;
- every Conceptual/Logical/Dimensional support record references an applicable
  source in the same Model and identifies exactly one physical or Assertion source
  as required by ADR 002; when the source is an Assertion, its Document/Record is
  active, applicable to that layer, and uses a valid bounded path;
- lock default duration, allowed minimum/maximum duration, database-time expiry,
  exact owner enforcement, renew/release ownership, audited override reason, and
  proof that Super Admin/workload status never bypasses ownership or revision fences;
- XLSX filename/path isolation and every archive/workbook/sheet/row/column/cell/
  timeout ceiling, including failures before database staging;
- both Docker images build, run non-root, and pass health/readiness smoke tests;
- browser console has no errors on tested screens;
- secret/raw-content scan finds no credential, raw prompt, physical row, raw
  provider response, or unredacted dump;
- DSN and external-endpoint rejection happens before every local/CI test
  connection attempt; production configuration validation and redaction are
  covered without making a real connection;
  secret scans report only file/rule identifiers and never print matched content;
- no automated command contacts a real database, Azure, Databricks, or model provider.
- no verification step executes a real Databricks notebook; notebook behavior is
  proven through import, static-boundary, fake-Adapter, and disposable-database tests.

Use the repository’s authoritative commands after inspecting current tooling. At minimum run:

```bash
uv run --project mcp_server ruff format --check mcp_server tests/mcp
uv run --project mcp_server ruff check mcp_server tests/mcp
uv run --project mcp_server pyright
uv run --project mcp_server pytest tests/mcp
uv run --project mcp_server python mcp_server/build_zip.py

uv run --project mcp_server pytest tests/plugin tests/plugin_v2
node --test tests/plugin_v2/workbench_logic.test.mjs \
  tests/plugin_v2/workbench_ui_state.test.mjs \
  tests/plugin_v2/workbench_workspace.test.mjs

uv run --project web_app/backend ruff format --check web_app/backend/gds_workbench_api tests/web_backend
uv run --project web_app/backend ruff check web_app/backend/gds_workbench_api tests/web_backend
uv run --project web_app/backend pyright
uv run --project web_app/backend pytest

cd web_app/frontend
npm run check
```

Also run the current V2 Python/Node package suites, browser E2E suite, canonical
database verification, and backend/frontend container builds/smokes. Record exact
commands and results in traceability; do not hide skipped tests.

## Final stopping condition and report

Mark the goal complete only when:

- all six ordered phases and their gates pass;
- all required format, lint, type, unit, integration, contract, package, browser
  E2E, accessibility-critical, and container smoke checks pass;
- docs and traceability describe actual implemented behavior;
- no required TODO, placeholder, fake production handler, disconnected control,
  skipped failing test, or unfinished Release 1 feature remains;
- no secret/raw prompt/raw row/raw provider output was committed or logged;
- no migration/hotfix/destructive database helper was added;
- no external deployment or live-system call occurred;
- the final diff was reviewed against the initial dirty worktree so user-owned changes were preserved.

The final report must list:

1. Changed areas by phase.
2. Exact verification commands and pass counts/results.
3. Local backend/frontend/container run instructions plus wheel build/install and
   safe Databricks notebook-wrapper usage instructions.
4. Any explicitly approved deferred item; do not defer a required Release 1 feature on your own.
5. Confirmation that no external system was contacted and no deployment occurred.
6. Final goal token usage if the goal has a token budget.

Do not declare success because a subset of tests passes or the UI renders. The
stopping condition is the complete verified Release 1 contract above.
