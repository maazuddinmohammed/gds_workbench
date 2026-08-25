# Azure Container Apps deployment shape

This is the Release 1 deployment contract, not a deployment script. It creates
or changes no Azure resource. Use [`DEPLOYMENT_GUIDE.md`](DEPLOYMENT_GUIDE.md)
for the verified local startup and step-by-step Azure operator procedure.

## Container topology

Build the two images documented in `web_app/README.md`.

| Container App | Containers | Ingress | Purpose |
|---|---|---|---|
| Workbench web | Frontend image on `8080`; backend image on `8000` | External HTTPS to `8080` | NGINX serves React and proxies `/api/` to `http://127.0.0.1:8000`. The API is not exposed separately. |
| Workbench worker | Backend image with command `gds-workbench-worker` | Disabled | Claims and executes durable Workflow Runs. Multiple replicas are safe because claims are database-leased and fenced. |

Keeping frontend and API in one Container App preserves one browser origin and
one Easy Auth boundary while retaining independently buildable containers. The
worker uses the same backend image but runs as a separate, non-HTTP process.

## Authentication boundary

Enable Microsoft Entra authentication on the Workbench web ingress and reject
unauthenticated requests. The API accepts only the bounded
`X-MS-CLIENT-PRINCIPAL` claims document produced by Easy Auth. Its existing
identity parser requires one `tid`, one `oid`, `idtyp=user`, and the
`workbench.access` scope. Do not expose port `8000` through a second ingress and
do not allow a proxy to replace or synthesize identity headers.

Azure Container Apps documents that authenticated claims are injected into
request headers and that external callers cannot set those protected headers:
<https://learn.microsoft.com/azure/container-apps/authentication>.

## Runtime settings

Set these non-secret production values on both backend processes unless noted:

```text
GDS_WEB_ENVIRONMENT=production
GDS_WEB_PUBLIC_URL=https://<workbench-host>
GDS_WEB_FRONTEND_ORIGIN=https://<workbench-host>
GDS_WEB_AGENT_EXECUTION_MODE=remote
GDS_WEB_DATABRICKS_EXECUTION_MODE=remote
GDS_WEB_DATABRICKS_ENVIRONMENT_CODE=<registered-environment-code>
GDS_WEB_FOUNDRY_BASE_URL=https://<foundry-endpoint>  # when enabled
GDS_WEB_OPENAI_BASE_URL=https://<openai-endpoint>    # when enabled
API_UPSTREAM=http://127.0.0.1:8000                 # frontend container only
```

Optional bounded worker timing and agent timeout settings are listed in
`gds_workbench_api/configuration.py`. Do not set local identity variables in
production.

Reference these values from Container Apps secrets or Azure Key Vault; never
place them in an image, source file, or ordinary environment manifest:

```text
GDS_WEB_DATABASE_DSN
GDS_WEB_CURSOR_SIGNING_KEY
GDS_WEB_FOUNDRY_API_KEY                            # when enabled
GDS_WEB_OPENAI_API_KEY                             # when enabled
```

The production PostgreSQL DSN must identify a host and database, use
`sslmode=verify-full`, and select an approved root CA such as PostgreSQL 18's
`sslrootcert=system`. Set only enabled providers, but production requires at
least one complete provider base-URL/API-key pair. Databricks host, HTTP path,
and token continue to resolve through the existing secure GDS connection
mechanism; they are never browser settings.

Container Apps supports secret-backed environment variables and Key Vault
references: <https://learn.microsoft.com/azure/container-apps/manage-secrets>.

## Probes and rollout

Configure explicit HTTP probes:

| Container | Liveness | Readiness |
|---|---|---|
| Frontend | `GET /healthz` on `8080` | `GET /healthz` on `8080` |
| API | `GET /healthz` on `8000` | `GET /readyz` on `8000` |

`/healthz` proves the process responds. `/readyz` also checks the canonical
database contract and least-privilege runtime readiness. Shift revision traffic
only after readiness succeeds. The worker has no ingress and no HTTP probe; its
long-running process exits on unrecoverable startup failure so the platform can
restart it.

Azure Container Apps supports startup, liveness, and readiness probes, and uses
non-2xx/3xx HTTP responses as failures:
<https://learn.microsoft.com/azure/container-apps/health-probes>.

## Scaling and network

- Web replicas are stateless. Frontend and API scale together.
- Keep at least one worker replica unless an intentional pause is required.
  Database claim leases, heartbeats, fencing, and recovery coordinate multiple
  worker replicas; in-process memory is never the durable queue.
- Give both backend processes private network access to PostgreSQL and the
  registered Databricks/provider endpoints they require. Do not make PostgreSQL
  publicly reachable for this application.
- Use the same canonical database revision for web and worker deployments.
- Deploy a new revision for image or environment changes and wait for readiness
  before moving traffic.

Container Apps scaling and revision behavior are documented at
<https://learn.microsoft.com/azure/container-apps/scale-app> and
<https://learn.microsoft.com/azure/container-apps/revisions>.

## Pre-deployment gate

Before any separately authorized Azure deployment:

1. Run the complete disposable local stack and browser E2E suite.
2. Build and scan both images; verify their configured non-root users.
3. Confirm production mode rejects fake adapters and local identities.
4. Confirm no secret, rendered prompt, provider output, physical row, or
   Databricks credential appears in images, logs, or API responses.
5. Confirm the API has no independent public ingress and Easy Auth rejects
   unauthenticated traffic.
6. Confirm the worker and API use `gds_web_runtime`, not an owner/admin database role.
