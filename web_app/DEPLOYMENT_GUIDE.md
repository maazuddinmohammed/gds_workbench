# Databricks App deployment

This runbook covers the web App: React, FastAPI and its durable worker in one
supervised process. MCP is a separate Azure App Service. Source manifests/configuration
are authoritative; this document explains operator steps and failure boundaries.
Deployment requires explicit approval and a compatible, already-installed database.
It performs no schema migration, backfill or direct Model-data update.

## Required configuration

Use the checked-in `databricks.yml`, `app.yaml`, Python/Node manifests and lock files.
The bundle defines development/production targets; the manual-upload builder includes
the same canonical App manifest. Never modify files inside a checksummed artifact.

1. Ensure Databricks Apps, user authorization and the identity scopes
   `iam.access-control:read` and `iam.current-user:read` are available and permitted.
   The authorized workspace group receives App `CAN_USE`.
2. Install the matching PostgreSQL release and required seeds following
   [database instructions](../database/README.md). Do not replay schema DDL on an
   existing database. Verify readiness against this release's code, not historical
   stage/table counts.
3. Register each user's Entra identity and required Tenant access. The backend resolves
   the forwarded Databricks user token through `current_user.me()`; the active SCIM
   user's `externalId` must be the nonzero Entra object UUID. The configured Entra
   tenant should match the directory used by existing PostgreSQL identities.
4. Configure approved network paths to PostgreSQL, registered Databricks SQL, Foundry,
   and package registries. Do not expose the FastAPI port separately.
5. Store sensitive values in an app-scoped secret store. Use read-only App secret
   resources, never literal secrets in source, shell commands, logs or override files.

| App resource | Meaning |
| --- | --- |
| `postgres-dsn` | TLS PostgreSQL connection using only `gds_web_runtime`. |
| `cursor-signing-key` | Approved random cursor signing value, within runtime bounds. |
| `entra-tenant-id` | Directory UUID used to resolve the human Principal. |
| `databricks-environment-code` | Existing governed SQL Environment code. |
| `foundry-openai-base-url` | Resource OpenAI v1 URL accepted by backend configuration. |
| `foundry-api-key` | Foundry resource API key for the canonical deployment. |

`app.yaml` owns exact environment-to-resource mappings. `databricks.yml` declares
required non-secret bundle variable names. Configure their values in ignored
`.databricks/bundle/<target>/variable-overrides.json`; store resource/key names only,
never their values. Databricks owns its injected host, port and OAuth credentials;
do not copy them into application or Foundry settings.

For PostgreSQL, prefer `sslmode=verify-full` with the DNS hostname. The App uses its
pinned CA bundle when the CA source is omitted or `system`. Explicit `sslmode=require`
is an encrypted development fallback without hostname verification. Plaintext modes
and a production login other than `gds_web_runtime` are rejected.

## Foundry

The registry `web_app/backend/gds_workbench_api/config/agent_capabilities.json` owns
model codes, actual deployment names, execution modes and reasoning choices. Configure
only combinations verified for the destination resource, then rebuild. There is no
per-model environment override. Historical Run selections remain immutable.

The SDK adapter selects Responses for requests with tools and Chat Completions for
requests without tools. Do not remove reasoning merely to fit a different transport.
Backend configuration rejects unsupported model/mode/reasoning combinations.

Canonical App configuration uses secret resources:

   ```yaml
   - name: GDS_WEB_FOUNDRY_OPENAI_BASE_URL
     valueFrom: foundry-openai-base-url
   - name: GDS_WEB_FOUNDRY_API_KEY
     valueFrom: foundry-api-key
   ```

Alternatively replace the API-key setting and bundle resource with all three Entra
client credential settings before rebuilding:

   ```yaml
   - name: GDS_WEB_FOUNDRY_ENTRA_TENANT_ID
     valueFrom: foundry-entra-tenant-id
   - name: GDS_WEB_FOUNDRY_CLIENT_ID
     valueFrom: foundry-client-id
   - name: GDS_WEB_FOUNDRY_CLIENT_SECRET
     valueFrom: foundry-client-secret
   ```

Use the API key or the three Entra client credential variables, never both.
Entra uses an explicitly configured application with inference permission and the
`https://cognitiveservices.azure.com/.default` token audience. Databricks App OAuth
credentials are not Foundry credentials; implicit host managed-identity discovery is
not used. Entra accepts `https://<resource>.openai.azure.com/openai/v1/`; API-key
configuration also accepts the resource `.services.ai.azure.com/openai/v1/` route.
Project routes under `/api/projects/` are rejected.

Model-call timeout, worker lease/heartbeat and SQL limits are independent. Their
current defaults/bounds are in backend config and settings; do not copy deployment
specific limits into prompts. Missing/partial credentials fail startup. Disable raw
model payload tracing.

Optional `GDS_WEB_FOUNDRY_PRICING_JSON` supplies approved token rates by registered
model code. The runtime schema validates rates and applicability. Unset rates mean
Unpriced; missing provider usage stays unknown. Each request freezes its applicable
rate before execution. Estimates exclude other platform/contract charges.

## Build and release

Run the checks in root `AGENTS.md`, including disposable database tests, frontend
build and packaging. For local UI review use:

```bash
python3 web_app/local/run.py
```

It uses a new disposable PostgreSQL container, local identity and fake external
adapters. Stop with Ctrl-C. Never substitute a deployed database or production
credentials into local tests.

Build a manual-upload artifact with:

```bash
python3 deployment/databricks_ui/build_uploads.py
```

Use `--replace` only to replace that builder's previous output. Upload the expanded
`artifacts/databricks-ui/gds-workbench-app-source` directory, preserving nesting;
see [upload mechanics](../deployment/databricks_ui/README.md). The ZIP is transport,
not a Databricks notebook import. Managed deployment installs dependencies, builds
React into `web_app/frontend/dist`, then runs canonical `app.yaml`.

For an approved bundle deployment, authenticate the operator and use the intended
profile/target:

```bash
databricks auth login --host <workspace-url> --profile <profile>
databricks bundle validate -t development -p <profile>
databricks bundle deploy -t development -p <profile>
databricks bundle run -t development -p <profile> workbench
databricks apps get <app-name> --profile <profile>
```

`workbench` is the bundle resource key. Deploy uploads source; Run starts/restarts it.
Wait for Running. Promote the same verified source and locks using the production
target/profile only after acceptance. Never record secret references or values in a
release record.

Before rollout, check active Model agent defaults against the current registry.
Incompatible defaults need an approved governed Model update, not direct SQL or
historical Run rewrites. Code/schema compatibility is a separate gate from replaying
prompt/reference seeds.

## Acceptance and rollback

Verify in the intended environment using authorized data:

- `/healthz` and `/readyz`; React assets and deep-link reload; same-origin API.
- App group access, valid mapped identity and bounded unauthorized denials.
- Tenant roles, owned lock, revision conflict and idempotent retries.
- Worker claim/heartbeat/completion and safe failure reporting.
- Representative workflows with actual Foundry deployments, both supported modes,
  required reasoning and governed Databricks data access.
- No credentials, raw prompts, rows, tool output or stack traces in logs/telemetry.

Local synthetic checks do not certify live-provider quality or production networking.
Rollback redeploys a known-good compatible source revision using validate/deploy/run;
it never resets PostgreSQL or invokes `bundle destroy`. Recheck active Model default
compatibility and preserve immutable historical provenance.

| Failure | Check |
| --- | --- |
| Build/startup failure | Lock files, approved registry egress, App resource resolution and bounded logs. |
| Frontend unavailable | Root Node build produced `web_app/frontend/dist/index.html` and assets. |
| 401 | User authorization/scopes, forwarded token, active SCIM user and Entra `externalId`. |
| 403 | App `CAN_USE`, registered Principal, Tenant role, ownership and lock. |
| Readiness 503 | Database network/TLS/runtime role and exact installed release/reference metadata. |
| Foundry failure | Accepted URL, exact registry deployment, one complete authentication method, inference permission, egress and mode/reasoning support. |
| Queue stalled | Supervised worker, claims, lock/revision state and bounded workflow events. |

Platform reference: [Databricks Apps](https://learn.microsoft.com/en-us/azure/databricks/dev-tools/databricks-apps/),
[bundle App deployment](https://learn.microsoft.com/en-us/azure/databricks/dev-tools/bundles/apps-tutorial).
Check platform prerequisites at deployment time; repository manifests define this
release's runtime contract.
