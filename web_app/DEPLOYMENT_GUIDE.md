# GDS Workbench deployment on Azure Databricks Apps

This is the deployment runbook for the Workbench web application. The supported
production shape is one Azure Databricks App containing:

```text
Browser
  -> Databricks Apps OAuth and CAN_USE
  -> one Python process
       -> FastAPI: /api/*
       -> FastAPI: built React application and assets
       -> durable workflow worker
            -> existing PostgreSQL database
            -> existing governed Databricks SQL connection
            -> OpenAI Agents SDK
            -> Microsoft Foundry resource and its registered deployments
```

The frontend and API share the Databricks App origin. The worker runs beside the
HTTP server in the same app process. If either required runtime stops, the app
process stops so Databricks can report and restart the failed app.

This deployment does **not** deploy or change the MCP server. MCP remains a
separate Azure-authenticated service and keeps its existing authentication and
Databricks connection behavior. Use
[`docs/AZURE_FRESH_DEPLOYMENT.md`](../docs/AZURE_FRESH_DEPLOYMENT.md) only for
that service.

This runbook performs no database DDL, migration, backfill, or direct data edit.
It requires an already installed, compatible PostgreSQL database.

## 1. Identity and authorization boundaries

| Operation | Identity and authorization |
|---|---|
| Open the app | Databricks OAuth plus app `CAN_USE` permission. |
| Resolve the web user | Databricks forwards `X-Forwarded-Access-Token`. The backend calls `current_user.me()` with that user token and accepts only an active SCIM user whose `externalId` is a nonzero Entra object UUID. |
| Authorize application actions | The backend combines the configured Entra tenant UUID with the resolved object UUID. Existing PostgreSQL Principal, Tenant, role, Tenant Lock, Model ownership, and revision rules remain authoritative. |
| Query the agent model | OpenAI Agents SDK calls Microsoft Foundry using a dedicated Entra application or API key. End users receive neither credential. |
| Run profiling and analysis validation | The existing registered GDS Databricks environment and governed connection remain unchanged. |
| Use MCP | The separate MCP server and its Azure authentication remain unchanged. |

The web App and MCP server should normally use the same Entra directory/Tenant
ID so the same human `(tenant ID, object ID)` resolves to the same PostgreSQL
Principal. They do **not** share an OAuth application/client identity. The MCP
App Service has its own Entra API app registration, audience, scopes, and app
roles. Databricks creates a different, non-reusable service principal for this
App and handles its user OAuth. The web App therefore needs the shared Entra
Tenant ID, but no MCP client ID or MCP client secret.

Only `/api/*` requires the backend identity resolver. Databricks still protects
the entire app URL before a request reaches FastAPI. Never expose the FastAPI
port separately or accept identity from a browser-provided body or query value.

User authorization is currently a Databricks Public Preview feature. The bundle
requests only its two default identity scopes: `iam.access-control:read` and
`iam.current-user:read`. Before deployment, a workspace administrator must
enable user authorization, allow both scopes in the app OAuth policy, and
restart an existing app before adding the scopes. See
[Configure authorization in a Databricks app](https://learn.microsoft.com/en-us/azure/databricks/dev-tools/databricks-apps/auth).

## 2. Deployment files

Run bundle commands from the repository root. Databricks uses these files:

| File | Purpose |
|---|---|
| `databricks.yml` | Creates or updates the App, grants the user group `CAN_USE`, attaches six read-only secret resources including Foundry configuration, and defines `development` and `production` targets. |
| `app.yaml` | Starts `uv run --frozen python -m gds_workbench_api.app_process` with registered Foundry models and maps resource keys to runtime variables. The manual-upload builder includes this canonical file before hashing. |
| `pyproject.toml` and `uv.lock` | Install the pinned Python 3.14 application and local package dependencies. |
| `package.json` and `package-lock.json` | Install Node 22 dependencies and build React into `web_app/frontend/dist`. |

During deployment, Databricks detects both root dependency manifests, runs the
Node build, installs Python with `uv`, then runs `app.yaml`. See
[Databricks Apps deployment logic](https://learn.microsoft.com/en-us/azure/databricks/dev-tools/databricks-apps/deploy#deployment-logic)
and
[Manage app dependencies](https://learn.microsoft.com/en-us/azure/databricks/dev-tools/databricks-apps/dependencies).

Docker is used for the disposable local stack only. No container image or Azure
Container Apps resource is part of this deployment.

The bundle source boundary excludes tests, database installers, local tooling,
unrelated documentation, generated artifacts, and the separately deployed MCP
plugin.
It includes only the root build manifests, `app.yaml`, this deployment guide,
the shared `gds_etl_workbench` application/domain Python source needed in
process, and the web backend/frontend production source. The App neither starts
nor calls the MCP server. This prevents MCP deployment configuration from
entering the Databricks App while leaving the separate MCP runtime unchanged.

## 3. Prerequisites

### Workspace and operator

- An Azure Databricks workspace with Databricks Apps enabled.
- User authorization enabled by a workspace administrator. This feature is
  Public Preview; restart an existing app before adding its scopes.
- A workspace app OAuth scope policy that permits `iam.access-control:read` and
  `iam.current-user:read`.
- A deployment operator allowed to create or update Apps, app permissions, app
  resources, and the app service principal's resource grants.
- Databricks CLI `0.294.0` or newer, as required by `databricks.yml`.
- The managed runtime currently supplies `uv` 0.10.2 and Node 22.16. The lock
  files and CI are verified against those versions.
- OAuth user-to-machine authentication for interactive deployment. Use a
  dedicated OAuth service principal for production CI/CD; do not use a PAT.
- A workspace group whose members may use the app. The bundle grants that group
  `CAN_USE`.

### Existing PostgreSQL database

- The canonical database is already installed and at the revision expected by
  this release.
- That revision includes the accepted tenant-wide Workflow Run contract from
  [`ADR 003`](../docs/adr/003-tenant-wide-workflow-run-exclusivity.md): the
  immutable `application.workflow_run.tenant_id` witness, its composite Model
  foreign key, the one-running-Run-per-Tenant partial unique index, and the
  updated `application.start_workflow_run` conflict behavior. A fresh install
  from this revision includes them. For an existing populated database, do not
  rerun the fresh-install scripts; an authorized DBA must release the equivalent
  reviewed, non-destructive schema/function change before this App revision is
  deployed.
- That revision also includes the Code Generation and Validation Model Sections from
  [`ADR 004`](../docs/adr/004-code-generation-and-validation-model-sections.md),
  including their Model Change Set, Model Snapshot, and frozen Validation System
  selection contracts.
- The runtime DSN uses the least-privilege `gds_web_runtime` account and includes
  a host, database, and TLS. `sslmode=verify-full` is the recommended default;
  when its CA source is omitted or set to `system`, the App supplies the pinned
  `certifi` CA bundle containing the Azure PostgreSQL roots. An explicit
  `sslmode=require` is accepted as a development fallback but encrypts without
  authenticating the server. Production startup rejects every other database
  login and rejects `disable`, `allow`, and `prefer`.
- The required application reference seed is installed from
  `database/seed/04_application_reference.sql`. Readiness requires exactly 50
  active workflow stages and 82 active backend-resolved variables; missing,
  inactive, or additional reference rows keep the App unavailable.
- For an upgrade to this release, replay that reference seed, then replay the
  prepared `database/seed/05_global_prompt_defaults.template.sql` copy. These
  replay-safe seed operations add the current workflow stages, including Validation,
  and publish their governed global defaults; they are not schema installation
  or data cleanup.
- Every intended user has an active `security.entra_principal_identity` for the
  configured Entra tenant and object UUID, plus the required active Tenant role.
- Databricks Apps serverless compute can reach PostgreSQL. Configure an approved
  Network Connectivity Configuration, egress policy, firewall rule, or outbound
  Private Link path as required by the environment. See
  [Configure networking for Databricks Apps](https://learn.microsoft.com/en-us/azure/databricks/dev-tools/databricks-apps/networking).

Do not point local runners or automated tests at this database. Local and CI
database tests may use only the disposable PostgreSQL container created by the
test fixture or local runner.

### Existing Databricks resources

- One registered GDS Databricks environment code already present in the existing
  application data. Profiling and analysis validation continue using that
  environment's existing governed connection.
- If serverless egress is restricted, allow the approved PostgreSQL destination
  and the package registries needed during builds. Do not broadly allow all
  outbound traffic.

See
[Add resources to a Databricks app](https://learn.microsoft.com/en-us/azure/databricks/dev-tools/databricks-apps/resources).

### Secret scope

Create a dedicated Databricks secret scope for this app. The checked-in
bundle needs these six values:

| Bundle variable points to | Required secret value |
|---|---|
| `database_dsn_secret_key` | Verified PostgreSQL runtime DSN. |
| `cursor_signing_key_secret_key` | Random 32-4096 byte cursor-signing value. |
| `entra_tenant_id_secret_key` | Entra tenant UUID used by existing PostgreSQL identities. |
| `databricks_environment_code_secret_key` | Existing registered GDS environment code. |
| `foundry_openai_base_url_secret_key` | Microsoft Foundry resource OpenAI v1 URL. |
| `foundry_api_key_secret_key` | API key for that Foundry resource. |

Enter secret values through the approved secret-management UI or secret-input
workflow. Never place a value in source, a shell command, a bundle variable
file, a screenshot, or logs. Secret permissions apply at scope level, so do not
mix unrelated secrets into this scope. See
[Add a secret resource to a Databricks app](https://learn.microsoft.com/en-us/azure/databricks/dev-tools/databricks-apps/secrets).

## 4. Required bundle variables

`databricks.yml` requires these non-secret references:

| Variable | Value |
|---|---|
| `app_name` | Unique lowercase app name containing only letters, numbers, and hyphens. |
| `user_group_name` | Existing Databricks group to receive `CAN_USE`. |
| `secret_scope` | Dedicated existing secret scope. |
| `database_dsn_secret_key` | Key name, not its DSN value. |
| `cursor_signing_key_secret_key` | Key name, not its secret value. |
| `entra_tenant_id_secret_key` | Key name, not its tenant value. |
| `databricks_environment_code_secret_key` | Key name, not its environment value. |
| `foundry_openai_base_url_secret_key` | Key name, not its Foundry URL value. |
| `foundry_api_key_secret_key` | Key name, not its API-key value. |

Keep per-target values in the CLI's ignored local override file. For production,
create `.databricks/bundle/production/variable-overrides.json` locally:

```json
{
  "app_name": "<production-app-name>",
  "user_group_name": "<authorized-group-name>",
  "secret_scope": "<app-secret-scope>",
  "database_dsn_secret_key": "<database-dsn-key-name>",
  "cursor_signing_key_secret_key": "<cursor-key-name>",
  "entra_tenant_id_secret_key": "<tenant-id-key-name>",
  "databricks_environment_code_secret_key": "<environment-code-key-name>",
  "foundry_openai_base_url_secret_key": "<foundry-url-key-name>",
  "foundry_api_key_secret_key": "<foundry-api-key-name>"
}
```

Use the corresponding
`.databricks/bundle/development/variable-overrides.json` for the development
target. `.databricks/` is ignored by Git. These files contain names only, never
secret values. See
[Bundle variables and overrides](https://learn.microsoft.com/en-us/azure/databricks/dev-tools/bundles/variables).

## 5. Runtime variables

`app.yaml` supplies the following values; operators do not set them manually:

| Variable | Source |
|---|---|
| `NODE_ENV=production` | Fixed setting that omits frontend test dependencies during the managed build. |
| `GDS_WEB_ENVIRONMENT=production` | Fixed app setting. |
| `GDS_WEB_STATIC_DIR=web_app/frontend/dist` | Fixed app setting. |
| `GDS_WEB_AGENT_EXECUTION_MODE=remote` | Fixed app setting. |
| `GDS_WEB_DATABRICKS_EXECUTION_MODE=remote` | Fixed app setting. |
| `GDS_WEB_DATABASE_DSN` | `postgres-dsn` secret resource. |
| `GDS_WEB_CURSOR_SIGNING_KEY` | `cursor-signing-key` secret resource. |
| `GDS_WEB_ENTRA_TENANT_ID` | `entra-tenant-id` secret resource. |
| `GDS_WEB_DATABRICKS_ENVIRONMENT_CODE` | `databricks-environment-code` secret resource. |
| `GDS_WEB_FOUNDRY_OPENAI_BASE_URL` | `foundry-openai-base-url` secret resource. |
| `GDS_WEB_FOUNDRY_API_KEY` | `foundry-api-key` secret resource. |

Databricks supplies `DATABRICKS_HOST`, `DATABRICKS_APP_NAME`,
`DATABRICKS_WORKSPACE_ID`, `DATABRICKS_APP_PORT`, `DATABRICKS_CLIENT_ID`, and
`DATABRICKS_CLIENT_SECRET`. Do not add, copy, or log them. The app listens on
`0.0.0.0:$DATABRICKS_APP_PORT` and uses unified authentication for the app
service principal. See
[Databricks Apps system environment](https://learn.microsoft.com/en-us/azure/databricks/dev-tools/databricks-apps/system-env).

The application also supports reviewed timing overrides, but the manifest uses
safe defaults: agent timeout 120 seconds; workflow lease 30 seconds; heartbeat
10 seconds; idle poll 1 second; error poll 5 seconds. Change these only through a
reviewed `app.yaml` update, never as an untracked ambient variable.

### Agent context modes

For workflows with execution modes, the UI and independent notebooks default
agentic authoring to `tool_assisted`. Analysis, Conceptual, Logical,
Dimensional, and Mapping expose both modes allowed by the selected model
profile:

- `one_shot` sends the complete frozen context once. It intentionally rejects a
  scope that exceeds the one-shot request bound; there is no hidden fallback.
- `tool_assisted` sends a compact manifest and serves immutable, byte-bounded
  local pages. Each provider conversation also has one cumulative tool-result
  allowance, reset for a validation-repair attempt.
A provider profile must explicitly register the chosen mode; the UI hides and
the backend rejects unsupported combinations.

Code Generation and Validation are mode-independent agent workflows. Their requests
store a null execution mode; the UI and notebooks do not expose a mode picker.

### Microsoft Foundry models and authentication

All agent workflows use OpenAI Agents SDK with Microsoft Foundry. Users choose
a model and reasoning effort; execution mode remains a workflow choice.
Remote startup requires the Foundry resource URL and one complete authentication
method. Missing or partial configuration fails startup.

The non-secret deployment registry is
`web_app/backend/gds_workbench_api/config/agent_capabilities.json`. Each entry
contains a stable model `code`, display `name`, exact Foundry `deployment_name`,
and verified execution-mode/reasoning combinations. The web application and
notebooks use this registry, and the backend revalidates each selection.
Change deployments in this JSON and rebuild; no per-model environment variable
is used. The checked-in deployment names are `gpt-5.6-sol` and `gpt-5.6-luna`.
Set them to the actual names in your Foundry resource if those differ.

Keep provider `microsoft_foundry` and SDK `openai_agents_sdk` on every new model
entry. Register only modes and reasoning values verified for that deployment.
The current registry exposes `default`, `none`, `low`, `medium`, `high`, and
`xhigh` for one-shot, and only `none` for tool-assisted
execution. `default` omits the reasoning parameter; `none` explicitly disables
reasoning. The retained SDK adapter uses Chat Completions, so preserve these
mode restrictions when configuring deployments.

Build the single source artifact with:

```bash
python3 deployment/databricks_ui/build_uploads.py
```

Upload `artifacts/databricks-ui/gds-workbench-app-source`. Canonical `app.yaml`
is included before the tree manifest and checksums are generated. Do not swap
manifests inside a generated artifact.

1. Choose exactly one Foundry authentication method. The generated manual-upload
   artifact uses an API-key secret resource. The backend also supports Microsoft
   Entra client credentials configured in canonical source before rebuilding.
   For Entra, create a dedicated application/service principal and rotation-managed
   client secret, then assign the route-appropriate inference role on the target
   Foundry resource.
2. Store the Foundry OpenAI base URL as an app-scoped Databricks resource. Store
   each model deployment name in `agent_capabilities.json`. For the generated
   manual-upload artifact, also store its API key. For Entra authentication, store
   the Entra tenant UUID, client UUID, and client secret instead. Never put a credential
   in source, a bundle variable value, a shell command, or logs.

   For temporary development, the backend also reads a literal process
   environment value named `GDS_WEB_FOUNDRY_API_KEY`. Set it only in an
   untracked local environment or the Databricks App resource UI. Do not place
   the real key in this repository or a checked-in `app.yaml`; the resource-backed
   form below works for development as well as production.
3. Canonical `app.yaml` includes the Foundry resource settings:

   ```yaml
   - name: GDS_WEB_FOUNDRY_OPENAI_BASE_URL
     valueFrom: foundry-openai-base-url
   ```

   It also contains the API-key resource:

   ```yaml
   - name: GDS_WEB_FOUNDRY_API_KEY
     valueFrom: foundry-api-key
   ```

   For Entra authentication, replace the API-key variable in source `app.yaml`
   with these three variables and update the corresponding bundle resources
   before rebuilding; never edit a generated artifact:

   ```yaml
   - name: GDS_WEB_FOUNDRY_ENTRA_TENANT_ID
     valueFrom: foundry-entra-tenant-id
   - name: GDS_WEB_FOUNDRY_CLIENT_ID
     valueFrom: foundry-client-id
   - name: GDS_WEB_FOUNDRY_CLIENT_SECRET
     valueFrom: foundry-client-secret
   ```

   Use the API key or the three Entra client credential variables, never both.
   Additional registered Foundry deployments on the same Foundry resource need
   only another JSON model entry; the base URL and authentication remain shared.

4. Add read-only App resources for the Foundry base URL and selected
   authentication method, using the exact resource keys above. Bundle variables
   contain only secret key names. Preserve existing governed Databricks SQL
   permissions; model calls authenticate directly with Foundry.
5. Allow outbound HTTPS from Databricks Apps to the selected Foundry host. Only
   Entra authentication also needs the Microsoft Entra token endpoint. Validate
   and deploy this configuration as its own release.

This integration uses Chat Completions. With Entra authentication, configure
only `https://<resource>.openai.azure.com/openai/v1/`; the application requests
`https://cognitiveservices.azure.com/.default` with `ClientSecretCredential`.
Microsoft's current direct Chat Completions example documents that exact host,
route, and token audience. The API-key variant also accepts the configured
resource `https://<resource>.services.ai.azure.com/openai/v1/` route. Project
routes under `/api/projects/` are a different API shape and are rejected.

`DATABRICKS_CLIENT_ID` and `DATABRICKS_CLIENT_SECRET` identify the app only to
Databricks. They are not Azure credentials and must not be copied into the
Foundry settings. Databricks Apps does not document an assignable Azure managed
identity for this host, so this release intentionally does not rely on
`DefaultAzureCredential` discovering one. Entra authentication therefore uses
the explicit application credentials above.

This provider cleanup requires no schema migration or backfill. Check existing
Model defaults as described below.

### Run tokens and estimated model cost

Every newly executed workflow records model request usage across stages, tool
turns, retries and repairs. The web Run detail and notebook result show the same
summary, including failed runs. Missing provider counters or an interrupted
request remain unknown; earlier runs without tracking remain unavailable.
Deterministic workflows report zero model requests once tracking starts.

Cost is **Unpriced** until an operator supplies the deployment's token rates in
`GDS_WEB_FOUNDRY_PRICING_JSON`. Notebooks use the same JSON through
`GDS_NOTEBOOK_FOUNDRY_PRICING_JSON` in their uploaded root `.env`. Keys are the
registered model codes. Replace the placeholders below with confirmed USD rates
per million tokens; this example deliberately is not a usable price schedule:

```json
{"foundry-primary": {
  "basis": "Your approved rate schedule",
  "input_usd_per_million": "<input rate>",
  "cached_input_usd_per_million": "<cached input rate>",
  "cache_write_input_usd_per_million": "<cache write rate>",
  "output_usd_per_million": "<output rate>",
  "valid_from": null,
  "valid_until": null,
  "max_input_tokens": null
}}
```

Use a single line when placing JSON in an environment file. Each rate must be
between 0 and 1,000,000, with at most eight decimal places. Set timezone-aware
validity bounds and the maximum input size when the schedule has time or context
restrictions; null means no restriction. The end time is exclusive. All four
rates are required: cache tokens are part of input, and reasoning tokens are
part of output. If different cache rates require a breakdown the provider omits,
that request stays unpriced.

Each request saves its rates before calling Foundry. Refresh and replay use
those saved rates, including after configuration changes. Partial estimates sum
only priced requests and show missing usage, unsupported token categories or
inapplicable rates. These are model token estimates, excluding provisioned
capacity, contractual adjustments, Databricks compute and other services. Leave
rates unset when token pricing does not match the deployment's billing basis.

## 6. Local verification

Required local tools:

- Docker Desktop or Docker Engine with Compose;
- Python 3.14 and `uv` for backend checks;
- Node 22.16 through 22.x and npm for frontend checks.

From the repository root, verify the release source and lock files:

```bash
uv sync --frozen
uv run --project web_app/backend python -m pytest -c web_app/backend/pyproject.toml tests/web_backend
uv run --project web_app/backend python -m pytest -c web_app/backend/pyproject.toml tests/web_packaging
uv run --project web_app/backend ruff format --check web_app/backend/gds_workbench_api web_app/backend/gds_workbench_runtime
uv run --project web_app/backend ruff check web_app/backend/gds_workbench_api web_app/backend/gds_workbench_runtime
uv run --project web_app/backend pyright --project web_app/backend
npm ci
npm run check
```

Run the complete disposable application locally:

```bash
python3 web_app/local/run.py
```

Open <http://127.0.0.1:8080>. The local runner creates random credentials and a
fresh PostgreSQL container, loads only local fixtures, uses explicit local user
identity, uses fake Databricks and agent adapters, and disposes the database on
exit. Stop it with `Ctrl-C`.

This runner deliberately makes no Azure, Databricks, Foundry, MCP, or
persistent database call. Do not use `databricks apps run-local` with production
secret values as a substitute for the disposable runner.

## 7. Data compatibility release gate

An existing database may contain active Model defaults that do not match the
exact model deployments registered for this release. The default JSON exposes:

```text
provider            model code                     deployment_name
microsoft_foundry   foundry-primary                 gpt-5.6-sol
microsoft_foundry   foundry-gpt-5.6-luna            gpt-5.6-luna
```

Additional Foundry entries add their logical model codes to the runtime set.
Audit active `model.model` defaults. Do not run direct SQL or change them as part of
deployment. If incompatible active defaults exist:

1. report the exact affected Models without exposing other row data;
2. obtain explicit user and data-owner approval;
3. use the existing governed Model update API/workflow to change only active
   defaults to OpenAI Agents SDK, Microsoft Foundry, and a registered model; and
4. leave every historical `application.workflow_run` provider/model value
   unchanged because it is immutable execution provenance.

Also audit any active Model whose reasoning default is the legacy value `none`.
This release gives that code its provider-native meaning: explicitly disable
reasoning. If the Model should instead inherit its provider default, use the
governed Model update path to change only its active default to `default`.
Historical Workflow Run values remain unchanged.

Provider selection itself requires no additional table, function, trigger,
migration, or backfill beyond the database revision required above. Without an
approved governed Model-default update, affected new workflows can fail
capability validation even when the app itself is healthy.

## 8. Deploy through the bundle

The following commands change Databricks resources. Run them only after the
target deployment has been separately approved.

### Authenticate the operator

```bash
databricks -v
databricks auth login --host <workspace-url> --profile <profile-name>
databricks auth describe --profile <profile-name>
```

OAuth is preferred to a PAT. For CI/CD, configure a dedicated service principal
with only the deployment permissions it needs. See
[Databricks CLI authentication](https://learn.microsoft.com/en-us/azure/databricks/dev-tools/cli/authentication).

### Deploy development first

Use the development override file and a development workspace/profile:

```bash
databricks bundle validate -t development -p <development-profile>
databricks bundle deploy -t development -p <development-profile>
databricks bundle run -t development -p <development-profile> workbench
databricks bundle summary -t development -p <development-profile>
```

`workbench` is the bundle resource key, not the physical app name. Bundle deploy
uploads and updates the source, but the subsequent bundle run is required to
start or restart the app with that source. `bundle run` returns before startup
is necessarily complete.

Check status and bounded logs without dumping the environment:

```bash
databricks apps get <development-app-name> --profile <development-profile>
databricks apps logs <development-app-name> --profile <development-profile> --tail-lines 200
```

Wait for `Running`, then complete the acceptance checklist below.

### Promote the same revision to production

Use the exact tested commit and lock files. Create the production override file
with production resource names, then run:

```bash
databricks bundle validate -t production -p <production-profile>
databricks bundle deploy -t production -p <production-profile>
databricks bundle run -t production -p <production-profile> workbench
databricks bundle summary -t production -p <production-profile>
databricks apps get <production-app-name> --profile <production-profile>
```

Do not deploy from an unreviewed working tree. Record the commit SHA, bundle
target, app name, endpoint name, deployment time, and operator in the approved
release record. Do not record secret names, references, or values.

Current bundle/app commands are documented in
[Manage Databricks Apps with bundles](https://learn.microsoft.com/en-us/azure/databricks/dev-tools/bundles/apps-tutorial)
and the
[bundle command reference](https://learn.microsoft.com/en-us/azure/databricks/dev-tools/cli/bundle-commands).

### Upload the optional interactive notebooks separately

The App bundle deliberately excludes `databricks_notebooks/`. Upload the
notebook artifact separately to an access-controlled Workspace user folder.
These notebooks are an independent entry point: they load their own `.env`,
connect directly to PostgreSQL, resolve the database-owned notebook workload
identity, and run the shared workflow implementation in-process. They do not
call the App API or require the App or MCP server to be running. The App and
notebooks share source and authoritative database controls, but have separate
deployment, configuration, identity, and process lifecycles.

Follow [`databricks_notebooks/README.md`](../databricks_notebooks/README.md) for
the exact CLI upload commands, compute requirements, widget list, run order,
retry behavior, and manual Apply gates.

## 9. Production acceptance

Complete every check in development, then repeat the security and smoke checks
in production:

1. App status reaches `Running`; no startup error appears in bounded app or
   system logs.
2. In an authenticated browser, `/healthz` returns success and `/readyz` reports
   the canonical database ready without revealing connection details.
3. React loads from the app origin, a deep client-side route refresh succeeds,
   hashed assets load, and `/api/*` remains same-origin.
4. A user outside the configured group cannot open the app. A group member can
   open it and consent only to `iam.access-control:read` and
   `iam.current-user:read`.
5. Missing, invalid, inactive, or malformed forwarded user identity is rejected.
   The app never accepts a caller-supplied substitute identity.
6. An active mapped user sees only the Tenants and Models allowed by existing
   PostgreSQL RBAC. An unmapped or unauthorized user receives a bounded denial.
7. Tenant Lock, revision fencing, idempotency, and role checks still reject
   unauthorized state changes.
8. A queued workflow is claimed by the in-app worker, heartbeats, finishes, and
   records bounded failure information when deliberately given invalid input.
9. Profiling and analysis validation use the existing registered GDS Databricks
   environment without any MCP or credential change.
10. Each registered Foundry deployment is available, and its dedicated Entra
    application has the required inference permission or its API key is held
    only in the configured secret resource.
11. Run an approved smoke workflow through OpenAI Agents SDK. Then cover Metadata
    Enrichment, analysis, conceptual, logical, dimensional, mapping, Code Generation, and
    Validation paths, including each applicable execution mode and reasoning effort.
12. Verify timeouts, endpoint throttling, authentication failure, dependency
    failure, and validation repair return bounded errors without raw prompts,
    physical rows, tool output, tokens, credentials, or stack traces.
13. Confirm app logs and any enabled platform telemetry contain no secret,
    database DSN, bearer token, raw prompt, raw physical row, or raw model/tool
    response. Keep model payload logging disabled for this application.

Live PostgreSQL, Databricks SQL, and Foundry acceptance is a production-like
deployment activity, not an automated database test. It requires separate
approval and approved test data.

## 10. Rollback

Rollback redeploys a previously validated source revision. It does not alter the
database or MCP server.

1. Stop promotion and record the failed deployment ID, app status, and only the
   bounded error needed for diagnosis.
2. Check out the last known-good immutable commit. Confirm its lock files and
   target override references.
3. Run the local verification commands from that commit.
4. With the same target and profile, run:

   ```bash
   databricks bundle validate -t production -p <production-profile>
   databricks bundle deploy -t production -p <production-profile>
   databricks bundle run -t production -p <production-profile> workbench
   databricks apps get <production-app-name> --profile <production-profile>
   ```

5. Wait for `Running`, then repeat health, authentication, authorization, worker,
   and model smoke checks.
6. If only a model deployment failed, restore the previously approved JSON
   registry entry, redeploy, and rerun the app. It must still implement that
   provider/model contract.

Do not run `databricks bundle destroy`; it deletes managed resources and is not
a rollback mechanism. A code rollback does not reverse an approved governed
Model-default update. If old code requires different active defaults, obtain
new approval and use the governed Model update workflow. Historical Workflow Run
provenance is never rewritten.

The Databricks App details page exposes status, deployment history, resources,
and bounded logs. See
[View Databricks App details](https://learn.microsoft.com/en-us/azure/databricks/dev-tools/databricks-apps/view-app-details)
and
[Logging and monitoring](https://learn.microsoft.com/en-us/azure/databricks/dev-tools/databricks-apps/monitor).

## 11. Common failures

| Symptom | Check |
|---|---|
| Build fails before startup | Root `package-lock.json`, `uv.lock`, Python 3.14 compatibility, and restricted-egress access to approved npm/PyPI domains. |
| App is `Crashed` | `app.yaml` resource resolution, dependency installation, and bounded app/system logs. |
| Crash says `production database DSN requires sslmode=require or verify-full` | Replace the value stored behind the `postgres-dsn` App resource with the exact `gds_web_runtime` DSN shape documented above and one accepted TLS mode. Keep the DSN out of `app.yaml`. |
| Connection says `root certificate file ... does not exist` or `certificate verify failed` | Upload the current App source. It supplies the pinned CA bundle when `sslrootcert` is omitted or says `system`. Use the Azure PostgreSQL DNS hostname, not an IP address. For development only, `sslmode=require` is an accepted encrypted fallback. |
| Crash says `DATABRICKS_HOST must be a valid HTTPS origin` | Upload the current App source. It safely normalizes a platform-supplied bare workspace hostname to HTTPS. Do not add or override the Databricks-managed `DATABRICKS_HOST` setting in `app.yaml`. |
| React returns “built frontend unavailable” | Confirm the root Node build ran and produced `web_app/frontend/dist/index.html` plus `assets/`. |
| API returns `401` | User authorization is enabled, both default identity scopes are granted, the forwarded token is present, and SCIM `externalId` is the Entra object UUID. |
| API returns `403` | App `CAN_USE`, active SCIM user, PostgreSQL Principal mapping, Tenant access, Model ownership, and Tenant Lock. |
| Readiness returns `503` | PostgreSQL network path, TLS verification, runtime account, and canonical database revision. Do not print the DSN. |
| Foundry agent workflow fails | Foundry URL, actual Sol/Luna deployment names, exactly one configured authentication method, API-key or client-secret rotation, inference RBAC for Entra, permitted egress, and selected mode/reasoning compatibility. |
| Queue does not drain | The app process and embedded worker are running; inspect only bounded workflow state and logs. |
| Deployment cannot download packages | Databricks Apps egress policy allows the exact required package registries. |

## Official Azure Databricks references

- [Deploy a Databricks app](https://learn.microsoft.com/en-us/azure/databricks/dev-tools/databricks-apps/deploy)
- [Configure `app.yaml`](https://learn.microsoft.com/en-us/azure/databricks/dev-tools/databricks-apps/app-runtime)
- [Databricks Apps resources](https://learn.microsoft.com/en-us/azure/databricks/dev-tools/databricks-apps/resources)
- [Databricks Apps authorization](https://learn.microsoft.com/en-us/azure/databricks/dev-tools/databricks-apps/auth)
- [Databricks Apps networking](https://learn.microsoft.com/en-us/azure/databricks/dev-tools/databricks-apps/networking)
- [Databricks Apps environment](https://learn.microsoft.com/en-us/azure/databricks/dev-tools/databricks-apps/system-env)
- [Manage Apps with Declarative Automation Bundles](https://learn.microsoft.com/en-us/azure/databricks/dev-tools/bundles/apps-tutorial)
- [Databricks CLI authentication](https://learn.microsoft.com/en-us/azure/databricks/dev-tools/cli/authentication)
- [Microsoft Foundry endpoints and API-key authentication](https://learn.microsoft.com/en-us/azure/foundry/foundry-models/concepts/endpoints)
- [Microsoft Foundry direct Chat Completions integration](https://learn.microsoft.com/en-us/azure/foundry/how-to/integrate-with-other-apps)
- [Microsoft Foundry Entra inference setup and RBAC](https://learn.microsoft.com/en-us/azure/foundry/foundry-models/how-to/configure-entra-id)
- [Azure Identity `ClientSecretCredential`](https://learn.microsoft.com/en-us/python/api/azure-identity/azure.identity.clientsecretcredential)
