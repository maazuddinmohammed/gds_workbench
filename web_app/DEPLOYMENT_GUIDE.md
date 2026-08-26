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
            -> one direct agent model provider per deployment:
                 -> Databricks Model Serving (checked-in default), or
                 -> Microsoft Foundry OpenAI endpoint
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
| Query the agent model | The deployment selects exactly one provider. Databricks uses the app service principal and an attached endpoint with `CAN_QUERY`. Foundry uses a separate Entra service principal with inference-only Azure RBAC. End users receive neither credential. |
| Run profiling and analysis validation | The existing registered GDS Databricks environment and governed connection remain unchanged. |
| Use MCP | The separate MCP server and its Azure authentication remain unchanged. |

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
| `databricks.yml` | Creates or updates the default Databricks-model deployment, grants the user group `CAN_USE`, attaches four secret resources and one serving endpoint with `CAN_QUERY`, and defines `development` and `production` targets. |
| `app.yaml` | Starts `uv run --frozen python -m gds_workbench_api.app_process`, explicitly selects provider `databricks`, and maps resource keys to runtime variables. |
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
documentation, generated artifacts, and the separately deployed MCP plugin.
It includes only the root build manifests, `app.yaml`, the MCP Python package
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
- The runtime DSN uses the least-privilege `gds_web_runtime` account and includes
  a host, database, and `sslmode=verify-full`. Production startup rejects every
  other database login name.
- The required application reference seed is installed from
  `database/seed/04_application_reference.sql`. Readiness requires exactly 47
  active workflow stages and 78 active backend-resolved variables; missing,
  inactive, or additional reference rows keep the App unavailable.
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

- For the checked-in Databricks-model deployment, one standard,
  non-route-optimized Model Serving endpoint in the same workspace,
  in `READY` state, compatible with OpenAI Chat Completions, tool calls, JSON
  responses, and the configured `low`, `medium`, and `high` reasoning effort
  values. This release uses the workspace `/serving-endpoints` OpenAI-compatible
  API; route-optimized endpoint URLs require a different authentication flow.
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
| `model_endpoint_name` | Existing `READY` Model Serving endpoint name. |

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
  "model_endpoint_name": "<ready-serving-endpoint-name>"
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
| `GDS_WEB_AGENT_PROVIDER=databricks` | Fixed provider selection for the checked-in bundle. |
| `GDS_WEB_DATABRICKS_EXECUTION_MODE=remote` | Fixed app setting. |
| `GDS_WEB_DATABASE_DSN` | `postgres-dsn` secret resource. |
| `GDS_WEB_CURSOR_SIGNING_KEY` | `cursor-signing-key` secret resource. |
| `GDS_WEB_ENTRA_TENANT_ID` | `entra-tenant-id` secret resource. |
| `GDS_WEB_DATABRICKS_ENVIRONMENT_CODE` | `databricks-environment-code` secret resource. |
| `GDS_WEB_DATABRICKS_MODEL_ENDPOINT` | `agent-model-endpoint` serving resource. |

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

### Microsoft Foundry deployment variant

Provider choice is deployment configuration, not a user-facing runtime toggle.
The backend accepts one `GDS_WEB_AGENT_PROVIDER` value: `databricks` or
`microsoft_foundry`. It rejects settings from the unselected provider and the
API exposes only the selected provider's capability set.

The checked-in manifests remain the least-privilege, deployment-ready
Databricks default. To produce a Foundry-specific release manifest from the same
application source:

1. Create a dedicated Microsoft Entra application/service principal. For a
   Foundry Models project route, assign `Cognitive Services User` on the target
   Foundry resource. For the Azure OpenAI resource route, assign
   `Cognitive Services OpenAI User`. Create and rotation-manage one client
   secret.
2. Store the Foundry OpenAI base URL, model deployment name, Entra tenant UUID,
   client UUID, and client secret as five app-scoped Databricks secret values.
   The client secret is the only credential; never put it in source, a bundle
   variable file, a shell command, or logs.
3. In the Foundry deployment's `app.yaml`, keep all common variables, change
   `GDS_WEB_AGENT_PROVIDER` to `microsoft_foundry`, remove
   `GDS_WEB_DATABRICKS_MODEL_ENDPOINT`, and add these resource-backed variables:

   ```yaml
   - name: GDS_WEB_FOUNDRY_OPENAI_BASE_URL
     valueFrom: foundry-openai-base-url
   - name: GDS_WEB_FOUNDRY_MODEL_DEPLOYMENT
     valueFrom: foundry-model-deployment
   - name: GDS_WEB_FOUNDRY_ENTRA_TENANT_ID
     valueFrom: foundry-entra-tenant-id
   - name: GDS_WEB_FOUNDRY_CLIENT_ID
     valueFrom: foundry-client-id
   - name: GDS_WEB_FOUNDRY_CLIENT_SECRET
     valueFrom: foundry-client-secret
   ```

4. In that deployment's `databricks.yml`, remove `model_endpoint_name` and the
   `agent-model-endpoint` serving resource. Add five read-only secret resources
   with the exact resource keys above; bundle variables contain only their key
   names. Do not grant the app `CAN_QUERY` on an unused Databricks endpoint.
5. Allow outbound HTTPS from Databricks Apps only to the selected Foundry host
   and Microsoft Entra token endpoint, in addition to the application's existing
   approved destinations. Validate and deploy this manifest as its own release.

Use either the resource route
`https://<resource>.openai.azure.com/openai/v1/` or the current project route
`https://<resource>.services.ai.azure.com/api/projects/<project>/openai/v1/`.
The application requests `https://ai.azure.com/.default` with
`ClientSecretCredential`; it never uses an API key.

`DATABRICKS_CLIENT_ID` and `DATABRICKS_CLIENT_SECRET` identify the app only to
Databricks. They are not Azure credentials and must not be copied into the
Foundry settings. Databricks Apps does not document an assignable Azure managed
identity for this host, so this release intentionally does not rely on
`DefaultAzureCredential` discovering one. This is why the Foundry variant needs
the explicit Entra client credential above.

Switching provider requires no table, function, trigger, migration, or backfill.
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
uv run --project web_app/backend ruff format --check web_app/backend/gds_workbench_api tests/web_backend tests/web_packaging
uv run --project web_app/backend ruff check web_app/backend/gds_workbench_api tests/web_backend tests/web_packaging
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
provider selected for this deployment.
Each remote deployment exposes only its selected pair:

```text
databricks         / databricks-primary
microsoft_foundry / foundry-primary
```

Before production acceptance, an authorized operator must audit active
`model.model` defaults. Do not run direct SQL and do not change them as part of
deployment. If incompatible active defaults exist:

1. report the exact affected Models without exposing other row data;
2. obtain explicit user and data-owner approval;
3. use the existing governed Model update API/workflow to change only active
   defaults to the pair selected by that deployment; and
4. leave every historical `application.workflow_run` provider/model value
   unchanged because it is immutable execution provenance.

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

The App bundle deliberately excludes `databricks_notebooks/`. Deploy and start
the App first, then upload the notebook source folders to an access-controlled
Workspace user folder. The notebooks import the sibling Python client through
`sys.path`, collect non-secret widgets, and call the deployed App API; they do
not duplicate workflow logic, connect directly to PostgreSQL, or need an
`.env` file. The App and notebooks therefore use the same authorization,
validation, tenant-wide running-workflow guard, and worker implementation.

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
10. For Databricks, the attached endpoint is standard, non-route-optimized, and
    `READY`, and the app service principal has `CAN_QUERY`, not `CAN_MANAGE`.
    For Foundry, no Databricks serving endpoint is attached; the separate Entra
    service principal has only the route-appropriate inference RBAC on the
    selected resource.
11. Run one approved smoke workflow through each supported agent SDK. Then cover
    analysis, conceptual, logical, dimensional, mapping, and code-generation
    paths, including each applicable execution mode and reasoning effort.
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
6. If only the model endpoint failed, restore the previously approved endpoint
   configuration for the selected provider, redeploy, and rerun the app. It must
   still implement that provider's logical-model contract.

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
| React returns “built frontend unavailable” | Confirm the root Node build ran and produced `web_app/frontend/dist/index.html` plus `assets/`. |
| API returns `401` | User authorization is enabled, both default identity scopes are granted, the forwarded token is present, and SCIM `externalId` is the Entra object UUID. |
| API returns `403` | App `CAN_USE`, active SCIM user, PostgreSQL Principal mapping, Tenant access, Model ownership, and Tenant Lock. |
| Readiness returns `503` | PostgreSQL network path, TLS verification, runtime account, and canonical database revision. Do not print the DSN. |
| Databricks agent workflow fails | Endpoint `READY` state, app service-principal `CAN_QUERY`, `databricks-primary` selection, timeout, and endpoint model feature compatibility. |
| Foundry agent workflow fails | Foundry URL/deployment, Entra tenant/client configuration, secret rotation, route-appropriate inference RBAC, permitted egress, `foundry-primary` selection, and model feature compatibility. |
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
- [Microsoft Foundry OpenAI-compatible project endpoint](https://learn.microsoft.com/en-us/azure/foundry/foundry-models/how-to/generate-responses)
- [Microsoft Foundry Entra inference setup and RBAC](https://learn.microsoft.com/en-us/azure/foundry/foundry-models/how-to/configure-entra-id)
- [Microsoft Foundry Entra authentication](https://learn.microsoft.com/en-us/azure/foundry-classic/openai/how-to/managed-identity)
- [Azure Identity `ClientSecretCredential`](https://learn.microsoft.com/en-us/python/api/azure-identity/azure.identity.clientsecretcredential)
