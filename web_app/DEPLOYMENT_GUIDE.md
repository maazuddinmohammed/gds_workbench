# GDS Workbench local and Azure deployment guide

This guide covers:

1. starting the complete Workbench safely on a local computer;
2. checking the application before release; and
3. deploying the frontend, API, worker, and PostgreSQL database to Azure.

It does not deploy the MCP server. `docs/AZURE_FRESH_DEPLOYMENT.md` is the MCP
App Service runbook and must not be used for the Workbench web application.

## Deployment status and safety

The supported Azure shape is:

```text
Browser
  -> Azure Container Apps HTTPS ingress + Microsoft Entra authentication
     -> frontend container :8080
        -> /api/* over localhost
           -> API container :8000
              -> private PostgreSQL / Databricks / enabled Agent provider

Worker Container App, no ingress
  -> backend image running gds-workbench-worker
     -> same private PostgreSQL / Databricks / enabled Agent provider
```

The frontend and API are two containers in one Container App. They share a
network and revision lifecycle. The worker is a separate, ingress-disabled
Container App. Azure supports this tightly coupled sidecar pattern; see
[Containers in Azure Container Apps](https://learn.microsoft.com/azure/container-apps/containers).

The repository does not yet contain reviewed Bicep, Terraform, or Container
Apps YAML. Therefore:

- use this manual procedure first in a non-production Azure environment;
- record every selected value outside the repository;
- do not place credentials or connection values in source control, commands,
  build arguments, deployment manifests, screenshots, or logs; and
- convert the proven configuration to reviewed infrastructure as code before
  declaring the deployment production-ready.

No command in this document should be run against an existing populated
database. The current SQL is fresh-install DDL, not a migration system.

---

# Part 1: Run locally

## 1. Install the local prerequisites

Required for the complete stack:

- Docker Desktop or Docker Engine;
- Docker Compose, either `docker compose` or `docker-compose`;
- a local Unix Docker socket or Windows named pipe; and
- Python 3.10 or newer for the safe local runner.

Docker performs the PostgreSQL, Python, Node, API, worker, and frontend setup.
Python 3.14 and Node 24 are needed on the host only for direct development
commands, not for the normal Docker startup.

Confirm Docker is running:

```bash
docker version
docker compose version
```

Run all commands below from the repository root:

```bash
cd /path/to/gds_workbench_v2
```

## 2. Start the complete disposable stack

```bash
python3 web_app/local/run.py
```

Wait for the frontend to become available, then open:

- Workbench: <http://127.0.0.1:8080>
- API documentation: <http://127.0.0.1:8000/docs>
- API liveness: <http://127.0.0.1:8000/healthz>
- API readiness: <http://127.0.0.1:8000/readyz>

The runner intentionally:

- creates random local database and application credentials;
- starts a fresh PostgreSQL 18 database in Docker;
- installs and verifies the canonical database from scratch;
- loads only demo, reference, and local-identity seed data;
- keeps PostgreSQL private to the Docker network;
- runs the Agent and Databricks integrations as local fakes; and
- removes the containers, network, database volume, and its two exact generated
  application image tags when stopped.

It does not contact Azure, Databricks, an Agent provider, or another external
runtime service.

## 3. Stop the local stack

In the terminal running the stack, press `Ctrl-C` once. Wait until the runner
reports that Compose resources were removed.

The local database is disposable. Starting the runner again creates a new one.
Do not use this runner for persistent development data.

## 4. Use different local ports

If ports `8080` or `8000` are occupied:

```bash
python3 web_app/local/run.py --frontend-port 9080 --api-port 9000
```

Then open `http://127.0.0.1:9080`.

## 5. Optional frontend development mode

Keep the complete Docker stack running in the first terminal. In a second
terminal:

```bash
npm --prefix web_app/frontend ci
npm --prefix web_app/frontend run dev
```

Open <http://127.0.0.1:5173>. Vite proxies `/api` to the Docker API on port
`8000`.

The repository does not currently support a separate native PostgreSQL/API/
worker startup. Use the disposable Docker stack as the database and backend
boundary.

## 6. Local verification commands

Backend install and checks require Python 3.14 and `uv`:

```bash
uv sync --project web_app/backend --frozen
uv run --project web_app/backend python -m pytest -c web_app/backend/pyproject.toml tests/web_backend
uv run --project web_app/backend python -m pytest -c web_app/backend/pyproject.toml tests/web_packaging
uv run --project web_app/backend ruff format --check web_app/backend/gds_workbench_api tests/web_backend tests/web_packaging
uv run --project web_app/backend ruff check web_app/backend/gds_workbench_api tests/web_backend tests/web_packaging
uv run --project web_app/backend pyright --project web_app/backend
uv build web_app/backend
```

Frontend checks require Node 24 and npm 11.6:

```bash
npm --prefix web_app/frontend ci
npm --prefix web_app/frontend run check
```

Build both release-shaped images locally:

```bash
docker build --file web_app/backend/Dockerfile --tag gds-workbench-backend:local .
docker build --file web_app/frontend/Dockerfile --tag gds-workbench-frontend:local web_app/frontend
```

## 7. Local troubleshooting

| Symptom | What to do |
|---|---|
| The runner rejects an environment setting | Remove only the setting named in the error. The guard intentionally rejects ambient Azure, database, Databricks, Docker-network, GDS, OpenAI, PostgreSQL, and Compose configuration. |
| Docker cannot be reached | Start Docker Desktop/Engine. Do not point the runner at a remote TCP Docker daemon. |
| A port is already in use | Use `--frontend-port` and `--api-port` with two different free ports from `1024` through `65535`. |
| First startup is slow | The first run downloads pinned images and dependencies and builds both application images. |
| API readiness returns `503` | Read the safe readiness code, then inspect container status. Do not dump environment variables or database values. |
| The stack stops after one service fails | Preserve the bounded error, fix that cause, then start a fresh stack. The runner removes the failed disposable stack. |

---

# Part 2: Prepare the Azure deployment

## 1. Required Azure access

The deployment operator needs approved permission to:

- create resources in the target subscription and resource group;
- create role assignments for managed identities;
- create or configure a Microsoft Entra application registration;
- create a VNet and delegated subnets;
- create Azure Database for PostgreSQL Flexible Server;
- write approved secrets to Azure Key Vault; and
- create Azure Container Registry and Azure Container Apps resources.

Use separate non-production and production resource groups. Do not use a
personal subscription for production.

Install current Azure CLI and PostgreSQL client tools, then prepare the CLI:

```bash
az login
az account set --subscription <subscription-id>
az extension add --name containerapp --upgrade
```

Register the required resource providers once per subscription:

```bash
az provider register --namespace Microsoft.App
az provider register --namespace Microsoft.ContainerRegistry
az provider register --namespace Microsoft.DBforPostgreSQL
az provider register --namespace Microsoft.KeyVault
az provider register --namespace Microsoft.ManagedIdentity
az provider register --namespace Microsoft.Network
az provider register --namespace Microsoft.OperationalInsights
```

## 2. Choose names and capacity

Choose and record these values in an approved private operator record:

- Azure subscription and region;
- resource group;
- Container Registry;
- Key Vault;
- VNet and its address range;
- Container Apps infrastructure subnet;
- PostgreSQL delegated subnet;
- Container Apps environment;
- PostgreSQL server and database;
- web Container App;
- worker Container App;
- web managed identity;
- worker managed identity;
- registered Databricks environment code; and
- immutable release tag, normally a commit SHA or release version.

Do not use `latest` as an image tag. Azure recommends a unique tag for each
deployment so revisions remain traceable.

## 3. Run the release gate locally

Before building an Azure image:

1. start the complete local stack;
2. test login simulation, Tenant selection, metadata, Models, Mapping, Code
   Generation, and each workflow page;
3. run both backend test commands, including `tests/web_packaging`;
4. run the frontend `check` command;
5. build both Docker images; and
6. confirm no secret, connection value, rendered prompt, provider output,
   physical row, or raw tool output appears in logs or image layers.

Stop if any gate fails.

---

# Part 3: Create the Azure foundation

Use the Azure portal for the networking and first manual deployment. The exact
configuration can then be converted to infrastructure as code.

## 1. Create the resource group

```bash
az group create --name <resource-group> --location <azure-region>
```

## 2. Create the VNet and two dedicated subnets

In **Azure portal -> Virtual networks -> Create**:

1. Create one VNet in the same region as Container Apps and PostgreSQL.
2. Create a dedicated Container Apps subnet.
3. Size the Container Apps subnet at `/27` or larger for a workload-profiles
   environment.
4. Delegate it to `Microsoft.App/environments`.
5. Create a separate PostgreSQL subnet.
6. Size the PostgreSQL subnet at `/28` or larger.
7. Delegate it to `Microsoft.DBforPostgreSQL/flexibleServers`.
8. Confirm neither subnet overlaps another VNet, on-premises network, service
   CIDR, or Docker bridge CIDR.

The subnets must not contain other resource types. Microsoft documents the
Container Apps subnet rules in
[VNet integration](https://learn.microsoft.com/azure/container-apps/vnet-custom)
and the PostgreSQL rules in
[PostgreSQL private networking](https://learn.microsoft.com/azure/postgresql/network/concepts-networking-private).

## 3. Create the Container Apps environment

In **Azure portal -> Container Apps environments -> Create**:

1. Select the resource group and region.
2. Use the workload-profiles environment type.
3. Enable Azure Log Analytics as the logs destination.
4. Create or select a Log Analytics workspace.
5. Select **Use your own virtual network**.
6. Select the VNet and the Container Apps delegated subnet.
7. Use an external environment because the Workbench web app needs HTTPS
   ingress. Only the web Container App will expose ingress.
8. Finish creation and record the environment default domain.

## 4. Create private PostgreSQL 18

In **Azure portal -> Azure Database for PostgreSQL flexible servers -> Create**:

1. Select PostgreSQL major version `18`.
2. Select production-appropriate compute, storage, backup retention, and high
   availability. Size these from measured workload rather than copying demo
   values.
3. Create a dedicated empty Workbench database.
4. Under networking, select **Private access (VNet integration)**.
5. Select the Workbench VNet and PostgreSQL delegated subnet.
6. Create or select the PostgreSQL private DNS zone and link it to the VNet.
7. Leave public network access disabled from the start.
8. Record the PostgreSQL fully qualified domain name. Never use its current IP
   address in a connection string.

PostgreSQL 18 is supported by Azure Flexible Server. Verify the current minor
version before release in
[Azure PostgreSQL release notes](https://learn.microsoft.com/azure/postgresql/release-notes/release-notes).

## 5. Install the canonical database

Use an approved bootstrap host that can resolve the private DNS name and reach
the VNet, such as an organization-managed VPN-connected workstation or private
administration VM. Do not temporarily enable public PostgreSQL access.

From a clean repository checkout, connect as the PostgreSQL server
administrator. Let `psql` prompt for the password:

```bash
psql "host=<postgres-fqdn> port=5432 dbname=<workbench-database> user=<server-admin> sslmode=verify-full sslrootcert=system"
```

If the approved client cannot use the system CA store, provide the current
Azure root CA file explicitly instead. Do not pin an intermediate or individual
server certificate. See
[Azure PostgreSQL TLS connections](https://learn.microsoft.com/azure/postgresql/security/security-tls-how-to-connect).

Run the read-only preflight first:

```bash
psql "<admin-dsn-without-password>" -X -v ON_ERROR_STOP=1 \
  -f database/00_preflight.sql
```

Stop if it fails. A failure means the database is not a safe fresh-install
target.

Run the canonical files in this exact order:

```bash
for file in database/{01_reference,02_core,03_security,04_model,05_workflow_analysis,06_workflow_conceptual,07_workflow_logical,08_workflow_dimensional,09_workflow_mapping,10_application,10_mcp,10_workflow_eligibility,11_mcp_metadata_apply,11_runtime_account,12_runtime_integrity}.sql
do
  psql "<admin-dsn-without-password>" -X -v ON_ERROR_STOP=1 \
    --single-transaction -f "$file" || exit 1
done
```

Do not rerun the sequence after a failure. Preserve the error and investigate.
Never drop, truncate, reset, backfill, or repair the target with an ad hoc
script.

While connected interactively as the administrator, set the web runtime
password:

```text
\password gds_web_runtime
```

The command prompts twice without putting the password in SQL or shell history.
The API and worker must use `gds_web_runtime`; they must never use the server
administrator or `gds_mcp_runtime`.

Verify the installation:

```bash
psql "<admin-dsn-without-password>" -X -v ON_ERROR_STOP=1 \
  -f database/13_verify_install.sql
```

The final result must show `schema_version = 1.0.0` and
`verification_status = passed`.

Load stable application workflow stages and allowed prompt variables:

```bash
psql "<admin-dsn-without-password>" -X -v ON_ERROR_STOP=1 \
  --single-transaction -f database/seed/04_application_reference.sql
```

Create approved human Entra Principal/Tenant access rows from
`database/seed/02_human_principal_access.template.sql`. Edit a copy outside the
repository. The template grants viewer access only. Provision any higher
production role through the separately approved administrative bootstrap
process; do not improvise direct grants. Do not run the demo or
local-super-admin seed in production.

The complete database procedure and its safety rules are in
[`database/README.md`](../database/README.md).

## 6. Create Key Vault and managed identities

In Azure portal:

1. Create a Key Vault with Azure RBAC authorization enabled.
2. Enable soft delete and purge protection according to organization policy.
3. Create one user-assigned managed identity for the web Container App.
4. Create a different user-assigned managed identity for the worker Container
   App.
5. On Key Vault, grant each identity `Key Vault Secrets User` only for the
   secrets it needs.

Apply the organization's Key Vault network policy. If public access is
disabled, create and validate its private endpoint and private DNS path before
starting the Container Apps. Apply the equivalent approved policy to ACR when
it is created.

## 7. Store the runtime secrets

Add these values to Key Vault through an approved secret-entry process:

| Secret | Requirement |
|---|---|
| Web database DSN | Uses `gds_web_runtime`, the PostgreSQL FQDN, the dedicated database, `sslmode=verify-full`, and an approved root-CA configuration such as PostgreSQL 18's `sslrootcert=system`. |
| Cursor-signing key | Random UTF-8 value from 32 through 4096 bytes. Use the same value for API and worker. |
| Microsoft Foundry API key | Required only when that provider is enabled. |
| OpenAI API key | Required only when that provider is enabled. |

At least one complete provider URL/key pair is required in production. Never
store Databricks host, HTTP path, or token as browser or frontend settings.
Those values continue to resolve through the existing governed GDS connection
mechanism.

Use Container Apps Key Vault references rather than copying secret values into
ordinary environment variables. This requires the managed identity and `Key
Vault Secrets User` role described above. See
[Manage secrets in Azure Container Apps](https://learn.microsoft.com/azure/container-apps/manage-secrets).

## 8. Create Azure Container Registry and build images

Create the registry if the approved resource group does not already have one:

```bash
az acr create \
  --resource-group <resource-group> \
  --name <registry-name> \
  --sku <approved-sku>
```

On the registry's **Access control (IAM)** page, grant the web and worker
managed identities pull-only access: `AcrPull` for a normal RBAC registry, or
`Container Registry Repository Reader` for an ABAC-enabled registry. Do not
enable the registry admin account. Microsoft recommends this managed-identity
pull pattern; see
[Container Apps image pull with managed identity](https://learn.microsoft.com/azure/container-apps/managed-identity-image-pull).

From the repository root, build and push immutable images with Azure Container
Registry Tasks. Do not pass a secret as a build argument.

```bash
az acr build \
  --registry <registry-name> \
  --image gds-workbench/backend:<release-tag> \
  --file web_app/backend/Dockerfile \
  .

az acr build \
  --registry <registry-name> \
  --image gds-workbench/frontend:<release-tag> \
  --file Dockerfile \
  web_app/frontend
```

Record the resulting image digests. Production deployment should reference the
reviewed digest or its unique immutable tag. Azure documents this build command
under [`az acr build`](https://learn.microsoft.com/cli/azure/acr#az-acr-build).

Before deploying containers, confirm the Container Apps subnet can reach:

- PostgreSQL privately on TCP `5432`;
- Key Vault and ACR through the approved Azure paths;
- the selected Databricks SQL Warehouse endpoint over HTTPS; and
- each enabled Agent provider endpoint over HTTPS.

If an Azure Firewall or other egress appliance is present, add only the
approved service tags and FQDNs required by those dependencies.

---

# Part 4: Deploy the Container Apps

## 1. Determine the exact public host

The backend requires its exact HTTPS origin before it starts. For the Azure
default domain, obtain the Container Apps environment default domain:

```bash
az containerapp env show \
  --resource-group <resource-group> \
  --name <container-apps-environment> \
  --query properties.defaultDomain \
  --output tsv
```

The initial web host is:

```text
https://<web-container-app-name>.<environment-default-domain>
```

Use this same exact origin for `GDS_WEB_PUBLIC_URL`,
`GDS_WEB_FRONTEND_ORIGIN`, and the initial Entra redirect URI. If a custom
domain is added later, update all three together in a new reviewed revision.

## 2. Backend configuration matrix

Set these values on the API container and worker container.

| Setting | API | Worker | Secret | Rule |
|---|---:|---:|---:|---|
| `GDS_WEB_ENVIRONMENT=production` | Yes | Yes | No | Enables Easy Auth identity parsing, HTTPS enforcement, and production validation. |
| `GDS_WEB_PUBLIC_URL` | Yes | Yes | No | Exact public HTTPS origin, with no path. |
| `GDS_WEB_FRONTEND_ORIGIN` | Yes | Yes | No | Same exact frontend origin. |
| `GDS_WEB_DATABASE_DSN` | Yes | Yes | Yes | Key Vault-backed; must use `sslmode=verify-full` plus an approved root CA. |
| `GDS_WEB_CURSOR_SIGNING_KEY` | Yes | Yes | Yes | Same Key Vault-backed value for both processes. |
| `GDS_WEB_DATABRICKS_ENVIRONMENT_CODE` | Yes | Yes | No | Exact active registered Environment code. |
| `GDS_WEB_DATABRICKS_EXECUTION_MODE=remote` | Yes | Yes | No | Fake mode is rejected in production. |
| `GDS_WEB_AGENT_EXECUTION_MODE=remote` | Yes | Yes | No | Fake mode is rejected in production. |
| `GDS_WEB_AGENT_TIMEOUT_SECONDS` | Optional | Optional | No | Integer from `1` through `600`; default `120`. |
| `GDS_WEB_FOUNDRY_BASE_URL` | Conditional | Conditional | No | HTTPS URL; set together with its API key. |
| `GDS_WEB_FOUNDRY_API_KEY` | Conditional | Conditional | Yes | Key Vault-backed. |
| `GDS_WEB_OPENAI_BASE_URL` | Conditional | Conditional | No | HTTPS URL; set together with its API key. |
| `GDS_WEB_OPENAI_API_KEY` | Conditional | Conditional | Yes | Key Vault-backed. |
| `GDS_WEB_WORKFLOW_LEASE_SECONDS` | Optional | Optional | No | Integer `1` through `300`; default `30`; keep heartbeat shorter. |
| `GDS_WEB_WORKFLOW_HEARTBEAT_SECONDS` | Optional | Optional | No | Positive number below the lease; default `10`. |
| `GDS_WEB_WORKFLOW_IDLE_POLL_SECONDS` | Optional | Optional | No | Number from `0.05` through `60`; default `1`. |
| `GDS_WEB_WORKFLOW_ERROR_POLL_SECONDS` | Optional | Optional | No | Number from `0.05` through `300`; default `5`. |

Set only the providers that are enabled. At least one complete provider pair is
mandatory. Unknown `GDS_WEB_*` settings fail startup. Never set
`GDS_WEB_LOCAL_ENTRA_TENANT_ID` or `GDS_WEB_LOCAL_PRINCIPAL_OBJECT_ID` in
production.

The frontend container receives only:

```text
API_UPSTREAM=http://127.0.0.1:8000
```

## 3. Create the web Container App

For the first manual non-production deployment, create both containers in one
Container App revision:

> The portal-first procedure can expose the ingress before Easy Auth is fully
> configured. Use it only in isolated non-production. A production deployment
> must apply authentication atomically through reviewed infrastructure as code
> or an approved equivalent control.

### Frontend container

- Name: `frontend`
- Image: `gds-workbench/frontend:<release-tag>`
- Port: `8080`
- Environment: `API_UPSTREAM=http://127.0.0.1:8000`
- Starting resources: `0.25` vCPU and `0.5 GiB` memory

### API container

- Name: `api`
- Image: `gds-workbench/backend:<same-release-tag>`
- Port: `8000`
- Command: keep the Docker image default
- Environment: use the API column of the configuration matrix
- Starting resources: `0.75` vCPU and `1.5 GiB` memory

These resource values are only a valid initial Consumption-plan combination.
Load test and resize them before production.

Attach the web user-assigned identity. Configure both ACR image pulls to use
that identity. Add Key Vault-backed Container Apps secrets, then reference them
from the API environment variables.

Configure ingress:

- external ingress enabled;
- target port `8080` only;
- HTTPS only; disable insecure HTTP;
- no separate API ingress; and
- single-revision mode for the first deployment.

The API must remain reachable only through frontend NGINX at localhost port
`8000`. Do not create another Container App or public endpoint for the API.

### Web probes

Configure probes explicitly on both containers:

| Container | Startup | Liveness | Readiness |
|---|---|---|---|
| Frontend | HTTP `/healthz`, port `8080` | HTTP `/healthz`, port `8080` | HTTP `/healthz`, port `8080` |
| API | HTTP `/healthz`, port `8000` | HTTP `/healthz`, port `8000` | HTTP `/readyz`, port `8000` |

A practical starting policy is a five-second period, a generous startup failure
threshold, and a three-failure liveness threshold. Tune it from measured cold
starts. Azure treats only HTTP `200` through `399` as probe success; see
[Container Apps health probes](https://learn.microsoft.com/azure/container-apps/health-probes).

### Web scaling

Start non-production with:

- minimum replicas: `1`;
- maximum replicas: `3`; and
- the default HTTP concurrency rule until load testing establishes a better
  threshold.

Each API replica can open up to five PostgreSQL connections. Include every web
and worker maximum when checking the database connection budget:

```text
(maximum web replicas + maximum worker replicas) * 5
```

Leave headroom for PostgreSQL administration, maintenance, and other approved
clients.

## 4. Configure Microsoft Entra authentication

Configure authentication before giving users the web URL.

### App registration

In **Microsoft Entra ID -> App registrations**:

1. Create or select a single-Tenant registration for the Workbench web app.
2. In the manifest, use access-token version `2`.
3. Under **Expose an API**, set an approved Application ID URI.
4. Add a delegated scope named exactly `workbench.access`.
5. Under **Token configuration**, add the `idtyp` optional claim to access
   tokens and configure it to include user tokens. The backend explicitly
   requires `idtyp=user` for a human request.
6. Add the callback URI:
   `https://<workbench-host>/.auth/login/aad/callback`.
7. Grant the required organizational consent.
8. If policy requires assignment, configure the Enterprise Application to
   require assignment and assign only approved users or groups.

Microsoft documents `idtyp` and optional access-token claims under
[Configure optional claims](https://learn.microsoft.com/entra/identity-platform/optional-claims).
When editing the app manifest, merge this entry into any existing
`optionalClaims.accessToken` array rather than replacing other approved claims:

```json
{
  "name": "idtyp",
  "source": null,
  "essential": false,
  "additionalProperties": ["include_user_token"]
}
```

### Container Apps Easy Auth

In **web Container App -> Authentication -> Add identity provider**:

1. Choose Microsoft.
2. Use the single-Tenant registration above.
3. Require authentication for all external requests.
4. Redirect unauthenticated browser requests to Microsoft rather than returning
   a bare `401`; the SPA has no separate sign-in screen.
5. Request the `workbench.access` delegated scope.
6. Restrict the allowed issuer/Tenant and token audience to the registration.
7. Leave the token store disabled; the backend uses only protected identity
   claims.

Container Apps inserts the protected `X-MS-CLIENT-PRINCIPAL` header after
authentication and prevents external callers from setting it. The backend then
requires one Tenant ID, one Object ID, a user identity type, and
`workbench.access`. See
[Container Apps authentication](https://learn.microsoft.com/azure/container-apps/authentication)
and
[Microsoft Entra setup](https://learn.microsoft.com/azure/container-apps/authentication-entra).

After login, the browser request to `/api/v1/session` must return `200`. If it
returns `401` or `403`, inspect the bounded application error and the app
registration. Do not print the principal header or token.

## 5. Create the worker Container App

Create a separate Container App in the same environment:

- Name: the approved worker app name
- Image: `gds-workbench/backend:<same-release-tag>`
- Ingress: disabled
- Command override: `gds-workbench-worker`
- Environment: use the worker column of the configuration matrix
- Identity: the worker user-assigned identity
- Starting resources: `1` vCPU and `2 GiB` memory
- Minimum replicas: `1`
- Maximum replicas: `2` until load tests and provider limits justify more

Do not add an HTTP probe to the worker. It is a long-running non-HTTP process.
Minimum replicas must remain at least one unless workflows are intentionally
paused; an ingressless app without another scaler does not wake itself from
zero. Azure documents the minimum-replica behavior in
[Container Apps scaling](https://learn.microsoft.com/azure/container-apps/scale-app).

The worker claims durable runs through PostgreSQL leases and fencing. Multiple
replicas are safe, but increasing replicas also increases PostgreSQL and Agent
provider load.

## 6. Register runtime data

Before running a real workflow, confirm the database contains approved active
records for:

- the human Entra Principal and Tenant access;
- the Tenant and its current lock policy;
- required Systems, Connections, Objects, Attributes, and discovery scopes;
- the selected Databricks Environment code;
- governed Databricks connection values through the existing GDS mechanism;
- published prompt versions and Model-stage bindings where required;
- published Mapping output templates where required; and
- a published SQL Generation Guide for Code Generation.

Databricks host, HTTP path, and token do not belong in the browser, frontend
container, or normal Container Apps environment settings.

---

# Part 5: Validate and release

## 1. Infrastructure checks

- Both images resolve from ACR through managed identity.
- Web and worker secret references show healthy synchronization.
- PostgreSQL public access is disabled.
- Private DNS resolves the PostgreSQL FQDN from both backend processes.
- Only frontend port `8080` has external ingress.
- Port `8000` has no independent ingress.
- Insecure HTTP is disabled.
- API `/readyz` succeeds inside the web revision.
- The worker has at least one running replica.

## 2. Authentication and authorization checks

Using an approved test user:

1. Open the HTTPS Workbench URL in a private browser window.
2. Confirm Azure redirects to Microsoft sign-in.
3. Confirm `/api/v1/session` succeeds after login.
4. Confirm only authorized Tenants appear.
5. Confirm a viewer cannot perform protected writes.
6. Confirm Tenant Lock acquisition, renewal, release, and explicit override obey
   database roles and ownership rules.
7. Confirm a user without `workbench.access` receives a bounded denial.

Do not test by forging Easy Auth headers against the public endpoint.

## 3. Workflow smoke test

Use a small, non-sensitive test Model:

1. add a small eligible Scope;
2. run Profiling on selected objects without direct raw-row output;
3. confirm the worker claims the run;
4. confirm safe Run Events reach the UI;
5. run Analysis inference and validation;
6. test one identity-authoring workflow in each explicit execution mode;
7. review and apply an atomic change set;
8. run Mapping for one target;
9. generate and inspect one stored SQL artifact; and
10. confirm no generated SQL is executed automatically.

Check that failures are explicit, no partial result is committed, and retry
attempts remain within the selected run settings.

## 4. Logging and redaction check

Container Apps and Log Analytics must not contain:

- database or provider credentials;
- Key Vault values or references copied from configuration;
- raw prompts or provider responses;
- physical data rows;
- raw Databricks output;
- workflow claim tokens;
- generated SQL bodies; or
- unredacted request/response dumps.

Log only bounded codes, identifiers allowed by policy, safe progress, timing,
and correlation information.

## 5. Release traffic

For later releases, use a unique image tag and a new revision. Prefer multiple
revision mode for controlled rollout:

1. deploy the new web revision with no production traffic;
2. wait for every explicit readiness probe;
3. run the authentication and smoke checks against the revision label URL;
4. move a small percentage of traffic;
5. monitor errors, latency, restarts, database pool use, and worker runs;
6. move the remaining traffic only when healthy; and
7. update the worker to the matching backend version.

Container Apps revisions are immutable snapshots and support traffic splitting;
see [Container Apps revisions](https://learn.microsoft.com/azure/container-apps/revisions).

Rollback only to an application revision compatible with the installed
database schema. The repository currently has no populated-database migration
or downgrade system.

---

# Part 6: Operations

## Update the application

1. Complete the local release gate.
2. Build new backend and frontend images with one new immutable release tag.
3. Review image scan results.
4. Create a new web revision containing both new images.
5. Validate readiness and authentication before shifting traffic.
6. Update the worker to the same backend tag.
7. Monitor safe workflow events and database capacity.

Never overwrite an existing image tag.

## Rotate a secret

1. Add a new approved Key Vault secret version.
2. Confirm the web and worker identities can read it.
3. Update or refresh both Container Apps secret references together.
4. Wait for both apps to restart or deploy a new revision.
5. Re-run readiness, login, and one small workflow smoke test.
6. Revoke the old credential only after both apps use the new value.

Container Apps can refresh an unversioned Key Vault reference automatically;
pin a version when change control requires an explicit rollout.

## Minimum monitoring

Create alerts for:

- unhealthy or failed revisions;
- repeated container restarts;
- API readiness failures;
- PostgreSQL connection-pool exhaustion;
- worker runs stuck beyond their lease/recovery policy;
- repeated workflow failures;
- authentication or authorization failure spikes; and
- Key Vault or ACR managed-identity failures.

The worker currently has no positive HTTP readiness signal. Monitor its replica
state plus durable run progress.

---

# Part 7: Known release gates

Close or explicitly accept these before a production launch:

1. **Infrastructure as code:** no reviewed Bicep/Terraform/Container Apps YAML
   currently enforces the manual configuration.
2. **End-to-end browser automation:** the repository does not yet include a
   production-shaped browser E2E suite.
3. **Import size:** frontend NGINX currently permits `20 MiB`, while higher
   layers accept larger workbooks. Treat `20 MiB` as the deployed limit until
   all layers use one agreed value.
4. **HTTPS proxy smoke test:** confirm `/api/*` has no redirect loop behind
   Container Apps TLS termination before shifting traffic.
5. **Worker health:** the worker has no positive readiness endpoint and can
   continue polling after persistent dependency errors; alert on durable run
   progress.
6. **Portable Databricks notebooks:** notebook wrapper deployment/failover is
   not part of the current web container images and must not be claimed until
   the shared workflow package and wrappers exist and pass their own gate.

The shorter immutable topology contract remains in
[`AZURE_CONTAINER_APPS.md`](AZURE_CONTAINER_APPS.md).
