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
            -> every JSON-registered Databricks Model Serving endpoint
            -> optional Microsoft Foundry OpenAI resource and its
               JSON-registered deployments
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
| Query the agent model | The app can expose both providers. Databricks uses the app service principal with `CAN_QUERY` on every registered endpoint. When configured, Foundry uses a separate Entra service principal or API key. End users receive neither credential. |
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
| `databricks.yml` | Creates or updates the App, grants the user group `CAN_USE`, attaches four secret resources, and defines `development` and `production` targets. Grant the App service principal `CAN_QUERY` on every registered Databricks endpoint separately. |
| `app.yaml` | Starts `uv run --frozen python -m gds_workbench_api.app_process` with every registered Databricks model and maps resource keys to runtime variables. The manual-upload builder selects this file before hashing. |
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
the MCP Python package
needed as an internal dependency, and the web backend/frontend production
source. This prevents legacy MCP deployment configuration from entering the
Databricks App while leaving MCP runtime behavior unchanged.

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
- That revision also includes the Code Generation and QA Model Sections from
  [`ADR 004`](../docs/adr/004-code-generation-and-qa-model-sections.md),
  including their Model Change Set, Model Snapshot, and frozen QA System
  selection contracts.
- The runtime DSN uses the least-privilege `gds_web_runtime` account and includes
  a host, database, and TLS. `sslmode=verify-full` is the recommended default;
  when its CA source is omitted or set to `system`, the App supplies the pinned
  `certifi` CA bundle containing the Azure PostgreSQL roots. An explicit
  `sslmode=require` is accepted as a development fallback but encrypts without
  authenticating the server. Production startup rejects every other database
  login and rejects `disable`, `allow`, and `prefer`.
- The required application reference seed is installed from
  `database/seed/04_application_reference.sql`. Readiness requires exactly 49
  active workflow stages and 80 active backend-resolved variables; missing,
  inactive, or additional reference rows keep the App unavailable.
- For an upgrade to this release, replay that reference seed, then replay the
  prepared `database/seed/05_global_prompt_defaults.template.sql` copy. These
  replay-safe seed operations add the current workflow stages, including QA,
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

- The checked-in registry uses the Databricks-hosted pay-per-token endpoints
  `databricks-gpt-oss-120b` and `databricks-claude-opus-5`. Confirm both are
  available in the target Azure region and grant the App service principal
  `CAN_QUERY` on both. This release uses the workspace `/serving-endpoints`
  OpenAI-compatible API; Unity AI Gateway model-service names and
  route-optimized endpoints require a different base URL or authentication
  flow.
- One registered GDS Databricks environment code already present in the existing
  application data. Profiling and analysis validation continue using that
  environment's existing governed connection.
- If serverless egress is restricted, allow the approved PostgreSQL destination
  and the package registries needed during builds. Do not broadly allow all
  outbound traffic.

See
[Model Serving resources for Databricks Apps](https://learn.microsoft.com/en-us/azure/databricks/dev-tools/databricks-apps/model-serving)
and
[Add resources to a Databricks app](https://learn.microsoft.com/en-us/azure/databricks/dev-tools/databricks-apps/resources).

### Secret scope

Create a dedicated Databricks secret scope for this app. The checked-in
Databricks-model bundle needs only these four values:

| Bundle variable points to | Required secret value |
|---|---|
| `database_dsn_secret_key` | Verified PostgreSQL runtime DSN. |
| `cursor_signing_key_secret_key` | Random 32-4096 byte cursor-signing value. |
| `entra_tenant_id_secret_key` | Entra tenant UUID used by existing PostgreSQL identities. |
| `databricks_environment_code_secret_key` | Existing registered GDS environment code. |

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
  "databricks_environment_code_secret_key": "<environment-code-key-name>"
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
Dimensional, and Mapping expose all three modes allowed by the selected model
profile:

- `one_shot` sends the complete frozen context once. It intentionally rejects a
  scope that exceeds the one-shot request bound; there is no hidden fallback.
- `tool_assisted` sends a compact manifest and serves immutable, byte-bounded
  local pages. Each provider conversation also has one cumulative tool-result
  allowance, reset for a validation-repair attempt.
- `detailed_coverage` runs deterministic bounded stages and merges their exact
  coverage server-side before the existing complete backend validator and
  draft handoff.

Use `detailed_coverage` for the largest scopes or when every selected record
must be processed. A provider profile must explicitly register the chosen mode;
the UI hides and the backend rejects unsupported combinations.

Code Generation and QA are mode-independent agent workflows. Their requests
store a null execution mode; the UI and notebooks do not expose a mode picker.

### Agent model registry and optional Microsoft Foundry connection

Provider, SDK, and model are user-facing runtime selections. One deployed app
always exposes every registered Databricks model. When the complete Foundry
resource/authentication settings are present, that same app also exposes every
registered Foundry model. Any partial Foundry configuration fails startup.

The non-secret model compatibility registry is
`web_app/backend/gds_workbench_api/config/agent_capabilities.json`. Every model
entry represents one physical deployment contract: its stable dropdown `code`,
display `name`, provider, exact `deployment_name`, and operator-verified SDK,
execution-mode, and reasoning combinations. Add, change, or remove model
deployments only in this JSON, then rebuild and redeploy. There is no per-model
environment variable. The UI and notebooks consume the same registry, and the
backend validates the exact combination again before calling a provider.

For Databricks, `deployment_name` is the fixed Model Serving endpoint name. For
Foundry, it is the user-created deployment name passed to the OpenAI-compatible
API. The checked-in Foundry values assume the deployments kept the portal's
default model-ID names, `gpt-5.6-sol` and `gpt-5.6-luna`; edit only those two
`deployment_name` values if your deployment names differ. `code` may remain a
stable application alias when a physical deployment is replaced. Model codes
are globally unique; deployment names are unique within their provider.

To add a custom deployment, copy one model entry, assign a unique `code`, set
its exact provider and `deployment_name`, and keep only verified
`execution_profiles`. Each profile is one SDK + execution-mode contract with
its accepted reasoning values. JSON can register deployments for the existing
`langchain_create_agent` and `openai_agents_sdk` adapters. A genuinely new SDK
requires an implemented and tested backend adapter before it can be registered.

Do not treat the file as a universal vendor catalog: availability and feature
support vary by workspace, region, deployment type, model version, and API
surface. `default` omits the reasoning parameter, while `none` sends an explicit
provider value that disables reasoning. The checked-in profiles expose:

- `databricks-primary` -> `databricks-gpt-oss-120b`, with `default`, `low`,
  `medium`, and `high`;
- `databricks-claude-opus-5` -> `databricks-claude-opus-5`, with `default`
  only because the current adapters do not translate Databricks Claude
  `thinking` and `budget_tokens` controls;
- `foundry-primary` -> `gpt-5.6-sol`; and
- `foundry-gpt-5.6-luna` -> `gpt-5.6-luna`.

The two Foundry entries expose `default`, `none`, `low`, `medium`, `high`, and
`xhigh` for non-tool modes. `max` is not exposed because it requires the
Responses API, and `minimal` is unsupported by GPT-5.6. These entries are
configuration assertions, not availability guarantees; verify regional access
before deployment.

Both current Agent adapters use Chat Completions. Microsoft documents that
GPT-5.6 and later cannot combine Chat Completions tools with reasoning unless
`reasoning_effort` is explicitly `none`; merely omitting the parameter can still
use the model's reasoning default and fail. Therefore a GPT-5.6 Foundry
`tool_assisted` profile must expose only `none` until that adapter is deliberately
migrated to the Responses API. The checked-in Foundry primary profile is
narrowed accordingly. Databricks reasoning settings are also
model-specific: GPT OSS accepts `low`, `medium`, and `high`, while other model
families use different controls. Verify and narrow each concrete deployment
entry before building the artifact.

After adding a Databricks entry, grant the App service principal `CAN_QUERY` on
that entry's `deployment_name`. No `app.yaml` model variable is required.

The checked-in manifests remain the least-privilege, Databricks-only default.
To build a Foundry-enabled source that keeps Databricks models available and
whose selected `app.yaml`, tree manifest, ZIP, and SHA-256 checksum agree, run:

```bash
python3 deployment/databricks_ui/build_uploads.py \
  --agent-provider microsoft_foundry
```

Upload the resulting
`artifacts/databricks-ui-foundry/gds-workbench-app-source` folder. Do not copy
or replace `app.yaml` after the build. The selected manifest already contains
the API-key resource variant below, without a literal credential.

1. Choose exactly one Foundry authentication method. The generated manual-upload
   artifact uses an API-key secret resource. The backend also supports Microsoft
   Entra client credentials for a separately reviewed provider manifest. For
   Entra, create a dedicated application/service principal and rotation-managed
   client secret, then assign the route-appropriate inference role on the target
   Foundry resource.
2. Store the Foundry OpenAI base URL as an app-scoped Databricks resource. Store
   each model deployment name in `agent_capabilities.json`. For the generated
   manual-upload artifact, also store its API key. For an Entra manifest, store the Entra
   tenant UUID, client UUID, and client secret instead. Never put a credential
   in source, a bundle variable value, a shell command, or logs.

   For temporary development, the backend also reads a literal process
   environment value named `GDS_WEB_FOUNDRY_API_KEY`. Set it only in an
   untracked local environment or the Databricks App resource UI. Do not place
   the real key in this repository or a checked-in `app.yaml`; the resource-backed
   form below works for development as well as production.
3. The generated Foundry `app.yaml` keeps all common Databricks behavior and
   adds this Foundry resource setting:

   ```yaml
   - name: GDS_WEB_FOUNDRY_OPENAI_BASE_URL
     valueFrom: foundry-openai-base-url
   ```

   It also contains the API-key resource:

   ```yaml
   - name: GDS_WEB_FOUNDRY_API_KEY
     valueFrom: foundry-api-key
   ```

   A separately reviewed Entra source manifest uses these three variables
   instead of the API-key variable. Select and package that source manifest
   before checksums are generated; never edit a generated artifact:

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
   contain only secret key names. Separately grant `CAN_QUERY` on every
   registered Databricks `deployment_name`.
5. Allow outbound HTTPS from Databricks Apps to the selected Foundry host. Only
   the Entra variant also needs the Microsoft Entra token endpoint. Validate and
   deploy this manifest as its own release.

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
`DefaultAzureCredential` discovering one. This is why the Foundry variant needs
the explicit Entra client credential above.

Enabling Foundry requires no table, function, trigger, migration, or backfill.
It changes only deployment configuration and may require the governed Model
default update described below.

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

This runner deliberately makes no Azure, Databricks, Model Serving, MCP, or
persistent database call. Do not use `databricks apps run-local` with production
secret values as a substitute for the disposable runner.

## 7. Data compatibility release gate

An existing database may contain active Model defaults that do not match the
exact model deployments registered for this release. The default JSON exposes:

```text
provider            model code                     deployment_name
databricks          databricks-primary              databricks-gpt-oss-120b
databricks          databricks-claude-opus-5        databricks-claude-opus-5
microsoft_foundry   foundry-primary                 gpt-5.6-sol
microsoft_foundry   foundry-gpt-5.6-luna            gpt-5.6-luna
```

Additional registry entries add their logical model codes to the runtime set.
Foundry entries become available when the complete Foundry connection is
configured. Before production acceptance, an
authorized operator must audit active
`model.model` defaults. Do not run direct SQL and do not change them as part of
deployment. If incompatible active defaults exist:

1. report the exact affected Models without exposing other row data;
2. obtain explicit user and data-owner approval;
3. use the existing governed Model update API/workflow to change only active
   defaults to the pair selected by that deployment; and
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
10. Every registered Databricks endpoint is standard, non-route-optimized, and
    `READY`, and the app service principal has `CAN_QUERY`, not `CAN_MANAGE`.
    When Foundry is enabled, its separate Entra service principal has only the
    route-appropriate inference RBAC on the selected resource, or its API key is
    held only in the configured secret resource.
11. Run one approved smoke workflow through each supported agent SDK. Then cover
    analysis, conceptual, logical, dimensional, mapping, Code Generation, and
    QA paths, including each applicable execution mode and reasoning effort.
12. Verify timeouts, endpoint throttling, authentication failure, dependency
    failure, and validation repair return bounded errors without raw prompts,
    physical rows, tool output, tokens, credentials, or stack traces.
13. Confirm app logs and any enabled platform telemetry contain no secret,
    database DSN, bearer token, raw prompt, raw physical row, or raw model/tool
    response. Do not enable Model Serving payload logging or inference tables for
    this application.

Live PostgreSQL, Databricks SQL, and Model Serving acceptance is a production-like
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
| Databricks agent workflow fails | Regional availability, App service-principal `CAN_QUERY` on `databricks-gpt-oss-120b` and `databricks-claude-opus-5`, selected model/reasoning compatibility, and timeout. |
| Foundry agent workflow fails | Foundry URL, actual Sol/Luna deployment names, exactly one configured authentication method, API-key or client-secret rotation, inference RBAC for Entra, permitted egress, and selected mode/reasoning compatibility. |
| Queue does not drain | The app process and embedded worker are running; inspect only bounded workflow state and logs. |
| Deployment cannot download packages | Databricks Apps egress policy allows the exact required package registries. |

## Official Azure Databricks references

- [Deploy a Databricks app](https://learn.microsoft.com/en-us/azure/databricks/dev-tools/databricks-apps/deploy)
- [Configure `app.yaml`](https://learn.microsoft.com/en-us/azure/databricks/dev-tools/databricks-apps/app-runtime)
- [Databricks Apps resources](https://learn.microsoft.com/en-us/azure/databricks/dev-tools/databricks-apps/resources)
- [Databricks Apps authorization](https://learn.microsoft.com/en-us/azure/databricks/dev-tools/databricks-apps/auth)
- [Databricks Apps Model Serving resources](https://learn.microsoft.com/en-us/azure/databricks/dev-tools/databricks-apps/model-serving)
- [Databricks Apps networking](https://learn.microsoft.com/en-us/azure/databricks/dev-tools/databricks-apps/networking)
- [Databricks Apps environment](https://learn.microsoft.com/en-us/azure/databricks/dev-tools/databricks-apps/system-env)
- [Manage Apps with Declarative Automation Bundles](https://learn.microsoft.com/en-us/azure/databricks/dev-tools/bundles/apps-tutorial)
- [Databricks CLI authentication](https://learn.microsoft.com/en-us/azure/databricks/dev-tools/cli/authentication)
- [Microsoft Foundry endpoints and API-key authentication](https://learn.microsoft.com/en-us/azure/foundry/foundry-models/concepts/endpoints)
- [Microsoft Foundry direct Chat Completions integration](https://learn.microsoft.com/en-us/azure/foundry/how-to/integrate-with-other-apps)
- [Microsoft Foundry Entra inference setup and RBAC](https://learn.microsoft.com/en-us/azure/foundry/foundry-models/how-to/configure-entra-id)
- [Azure Identity `ClientSecretCredential`](https://learn.microsoft.com/en-us/python/api/azure-identity/azure.identity.clientsecretcredential)
