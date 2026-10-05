# Fresh Azure MCP deployment

This guide deploys the current repository as a new application. It assumes no
existing GDS database. It uses the simplest supported Azure setup first, then
lists production hardening at the end.

Do not run the numbered SQL files against a populated database. They are a
fresh-install schema, not migrations.

## 1. What you will deploy

| Service | Why it is needed |
|---|---|
| Resource group | Holds the Azure resources |
| Azure Database for PostgreSQL Flexible Server 18 | GDS application database |
| Linux Azure App Service plan and web app | Runs the Python 3.14 MCP server |
| Azure Key Vault | Holds the database DSN and cursor-signing key |
| Azure Storage account and private Blob container | Stores temporary Metadata and Model ZIP snapshots |
| Microsoft Entra app registration and App Service Authentication | Authenticates VS Code and other MCP clients |

Databricks is optional. Deploy/configure it only if you intend to use
`execute_databricks_sql`. Application Insights is also optional.

## 2. Before starting

You need:

1. An Azure subscription.
2. Permission to create Azure resources and role assignments.
3. Permission to create/configure a Microsoft Entra app registration.
4. This repository checked out locally.
5. Azure CLI, `psql`, Python 3.14, `uv`, and VS Code with GitHub Copilot and
   Agent Plugins enabled.
6. The current deployment ZIPs:

   ```text
   mcp_server/dist/<current-MCP-release>.zip
   atlas/dist/<current-Atlas-release>.zip
   ```

If the MCP ZIP is missing, build it from the repository root:

```bash
uv run --project mcp_server python mcp_server/build_zip.py
```

Choose unique names before continuing:

```text
Resource group:        <RESOURCE_GROUP>
Azure region:          <REGION>
PostgreSQL server:     <POSTGRES_SERVER>
Database:              gds_workbench
PostgreSQL admin:      <POSTGRES_ADMIN>
App Service plan:      <APP_SERVICE_PLAN>
Web app:               <WEB_APP>
Storage account:       <STORAGE_ACCOUNT>
Blob container:        snapshots
Key Vault:             <KEY_VAULT>
MCP URL:               https://<WEB_APP>.azurewebsites.net/mcp
```

Names in angle brackets are placeholders. Never paste passwords, tokens, or
connection strings into this file, source control, terminal history, or chat.

## 3. Create and configure resources in Azure Portal

### Step 1: create the resource group

1. Open [Azure Portal](https://portal.azure.com).
2. Search for **Resource groups**.
3. Select **Create**.
4. Choose the subscription, name, and region.
5. Select **Review + create**, then **Create**.

### Step 2: create PostgreSQL 18

1. Select **Create a resource**.
2. Search for **Azure Database for PostgreSQL flexible server**.
3. Select **Create**.
4. Choose the resource group and region.
5. Set **PostgreSQL version** to **18**.
6. Choose a small Burstable SKU for development. Choose an appropriate
   General Purpose/HA configuration for production.
7. Select password authentication and create the administrator login.
8. Under **Networking**, choose **Public access** for this simple first
   deployment.
9. Add your current public IP address so local `psql` can connect.
10. Enable **Allow public access from Azure services** so App Service can
    connect. This is broad; replace it with private networking before production.
11. Create the server.

### Step 3: create the empty database

1. Open the PostgreSQL server.
2. Select **Databases**.
3. Select **Add**.
4. Create `gds_workbench`.

### Step 4: install the database and defaults

Follow [database/README.md](../database/README.md) for the single maintained
installation sequence: read-only preflight, numbered files 01–19 once, distinct
runtime passwords, verification, then required reference/prompt/template seeds.
Follow [seed instructions](../database/seed/README.md) for approved identity
placeholders and replay behavior. Stop on any failure; do not rerun schema DDL.

Production needs approved Tenant/metadata/Entra Principal access. Demo/local seeds
belong only in disposable development databases. Authentication alone does not grant
application access. This repository supplies no populated-database upgrade helper.

### Step 5: create private snapshot storage

1. Create a **Storage account** in the same region/resource group.
2. Use StorageV2, Standard LRS for development, TLS 1.2 or later.
3. Disable anonymous Blob access.
4. Open **Containers** and create `snapshots` with **Private** access.
5. Under **Lifecycle management**, add deletion rules for `metadata/` and
   `model/` after at least 24 hours.

Keep the account network-accessible to the web app. Snapshot download URLs are
short-lived, read-only user-delegation SAS URLs; the container itself stays
private.

### Step 6: create Key Vault

1. Create a **Key vault** in the resource group.
2. Use the Azure RBAC permission model.
3. Add two secrets through the portal:
   - the complete runtime PostgreSQL DSN;
   - a random cursor-signing value of at least 32 bytes.

The DSN must use the runtime login and the `gds_workbench` database. Use
`sslmode=verify-full` for certificate and hostname verification:

```text
host=<POSTGRES_SERVER>.postgres.database.azure.com port=5432 dbname=gds_workbench user=gds_mcp_runtime password=<RUNTIME_PASSWORD> sslmode=verify-full
```

For deployments awaiting database CA trust configuration, an explicit
`sslmode=require` is also accepted. It requires encryption but skips hostname
verification and may skip certificate verification. Keep `GDS_ENVIRONMENT=production`.
Remove the `PGSSLROOTCERT=system` App Service setting and any `sslrootcert=system`
DSN parameter before using this mode; PostgreSQL rejects that combination.
Return to `verify-full` once certificate trust is configured.

### Step 7: create the Linux web app

1. Create **Web App**.
2. Choose **Code**, **Linux**, and **Python 3.14**.
3. Create/select the App Service plan. B1 is adequate for a small development
   deployment; size production from actual load.
4. Create the web app.
5. Open **Settings > Configuration > General settings**.
6. Set **Startup Command** to `startup.sh`.
7. Turn on **HTTPS Only** and **Always On**.
8. Open **Identity** and enable the system-assigned managed identity.

### Step 8: grant the web app access

Grant the web app's system-assigned identity:

1. **Key Vault Secrets User** on the Key Vault.
2. **Storage Blob Data Contributor** on only the `snapshots` container.
3. **Storage Blob Delegator** on the storage account.

The first role lets App Service resolve Key Vault references. The storage roles
let the app create/read private snapshot blobs and mint read-only user-delegation
SAS URLs.

### Step 9: configure App Service settings

Open **Web App > Settings > Environment variables** and add:

| Setting | Value |
|---|---|
| `SCM_DO_BUILD_DURING_DEPLOYMENT` | `1` |
| `GDS_ENVIRONMENT` | `production` |
| `GDS_DATABASE_DSN` | Key Vault reference to the runtime DSN |
| `GDS_CURSOR_SIGNING_KEY` | Key Vault reference to the cursor key |
| `GDS_MCP_PUBLIC_URL` | `https://<WEB_APP>.azurewebsites.net/mcp` |
| `GDS_ENTRA_TENANT_ID` | Your Entra Directory/Tenant ID |
| `GDS_ENTRA_API_CLIENT_ID` | Add after Step 10 creates the app registration |
| `GDS_METADATA_SNAPSHOT_STORAGE_ACCOUNT_URL` | `https://<STORAGE_ACCOUNT>.blob.core.windows.net` |
| `GDS_METADATA_SNAPSHOT_STORAGE_CONTAINER` | `snapshots` |

Do not add `GDS_METADATA_SNAPSHOT_MANAGED_IDENTITY_CLIENT_ID` when using the
system-assigned identity. Save the settings and confirm both Key Vault
references show a resolved/healthy status.

### Step 10: configure Microsoft Entra and Easy Auth

1. Open **Web App > Settings > Authentication**.
2. Select **Add identity provider > Microsoft**.
3. Choose **Workforce configuration**, current tenant, and **Create new app
   registration**.
4. Require authentication and return **HTTP 401** for unauthenticated requests.
5. Add the provider.
6. Open the newly created app registration from the Authentication page.
7. In **Manifest**, set `api.requestedAccessTokenVersion` to `2` and save.
8. In **Expose an API**, set the Application ID URI to the exact MCP URL:

   ```text
   https://<WEB_APP>.azurewebsites.net/mcp
   ```

9. Add delegated scope `workbench.access`. Allow admins and users to consent,
   subject to your organization's policy.
10. Under **Authorized client applications**, add the Visual Studio Code client
    ID and select `workbench.access`:

    ```text
    aebc6443-996d-45c2-90f0-388ff96faa56
    ```

11. In **Token configuration**, add the `idtyp` optional claim to access tokens.
12. If workload/service-principal calls are needed, add an application role
    named `workbench.workflow`, allowed for **Applications**.
13. Return to the web app's Microsoft authentication provider. Set:
    - allowed client application: the VS Code client ID above;
    - tenant: only your intended tenant;
    - allowed token audiences: the API client ID and exact MCP URL.
14. Copy the app registration's **Application (client) ID** into the
    `GDS_ENTRA_API_CLIENT_ID` App Service setting.

The application itself publishes OAuth protected-resource metadata. Keep these
paths anonymous while keeping `/mcp` protected:

```text
/health/live
/health/ready
/.well-known/oauth-protected-resource
/.well-known/oauth-protected-resource/mcp
```

If the portal does not show excluded paths, open **Cloud Shell** in Azure Portal
and run:

```bash
az webapp auth update \
  --resource-group "<RESOURCE_GROUP>" \
  --name "<WEB_APP>" \
  --enabled true \
  --unauthenticated-client-action Return401 \
  --require-https true \
  --excluded-paths \
    /health/live \
    /health/ready \
    /.well-known/oauth-protected-resource \
    /.well-known/oauth-protected-resource/mcp
```

### Step 11: deploy the MCP ZIP

Azure's Kudu drag-and-drop ZIP page does not support Linux App Service. Use
Azure Cloud Shell in the portal or a local authenticated Azure CLI instead.
Upload/select the ZIP in Cloud Shell, then run:

```bash
az webapp deploy \
  --resource-group "<RESOURCE_GROUP>" \
  --name "<WEB_APP>" \
  --src-path "<current-MCP-release>.zip" \
  --type zip \
  --restart true \
  --track-status true
```

If running locally from the repository root, use:

```text
mcp_server/dist/<current-MCP-release>.zip
```

If Windows Azure CLI fails before upload with
`Permission denied: .azure\\msal_token_cache.bin.lockfile`, the ZIP has not
reached App Service. Do not change the ZIP or delete the existing Azure CLI
profile. Open a new PowerShell window and use a fresh writable CLI profile:

```powershell
$gdsAzureConfigDir = Join-Path $env:TEMP ("gds-azure-cli-" + [guid]::NewGuid())
New-Item -ItemType Directory -Path $gdsAzureConfigDir -ErrorAction Stop | Out-Null
$env:AZURE_CONFIG_DIR = $gdsAzureConfigDir
az login
az account set --subscription "<SUBSCRIPTION_ID>"
```

Keep that PowerShell window open and rerun the `az webapp deploy` command above.
The isolated profile avoids the locked or inaccessible cache without modifying
the original credentials directory.

### Step 12: verify the deployment

Open or call these URLs:

```text
GET https://<WEB_APP>.azurewebsites.net/health/live
GET https://<WEB_APP>.azurewebsites.net/health/ready
GET https://<WEB_APP>.azurewebsites.net/.well-known/oauth-protected-resource
GET https://<WEB_APP>.azurewebsites.net/mcp
```

Expected results:

1. `/health/live`: HTTP 200 and `{"status":"live"}`.
2. `/health/ready`: HTTP 200, `status=ready`, `schema_version=1.0.0`.
3. OAuth metadata: HTTP 200 and the exact Entra authorization server/scope.
4. `/mcp` without a token: HTTP 401.

If liveness is 200 but readiness is 503, check App Service Log Stream, Key
Vault reference status, PostgreSQL firewall access, DSN TLS mode, schema
verification, and runtime-role posture.

## 4. Package and install Atlas in VS Code

The Atlas MCP endpoint is declared in `atlas/atlas-plugin/mcp.json`. Set it to
the reviewed deployed `/mcp` URL before building a release archive. Build a
new archive from the repository root:

```bash
python3 atlas/build_plugin.py --output atlas/dist/atlas-agent-plugin-release.zip
```

The builder refuses to overwrite an existing archive and prints its SHA-256
digest. Inspect the archive before distribution; its root must contain
`atlas/plugin.json`, `atlas/mcp.json`, and `atlas/skills/atlas/SKILL.md`.
Unzip it through an approved internal channel and register the `atlas`
directory that contains `plugin.json` in VS Code. The repository marketplace
entry in `.github/plugin/marketplace.json` also points to the Atlas source.

Install the matching Atlas Stage Runner VSIX from `atlas/dist/`. Confirm the
`atlas` skill and `gds-workbench` MCP server appear in VS Code, then perform a
read-only `list_tenants` call to verify client-managed Microsoft Entra sign-in
and Tenant authorization.

## 5. Production readiness

1. Replace PostgreSQL's broad Azure-service firewall rule with App Service VNet
   integration and private PostgreSQL access.
2. Restrict Key Vault and Storage networking to approved private paths.
3. Add a custom domain before production if your organization requires one;
   then update the MCP URL, App ID URI, Easy Auth audiences, app setting, and
   plugin URL together.
4. Use production App Service/PostgreSQL sizing, backups, HA, alerts, and
   diagnostic retention.
5. Rotate the PostgreSQL runtime password, cursor key, and Easy Auth app
   credential under an approved process.
6. Keep the Blob lifecycle rule enabled. The application never performs broad
   storage cleanup.
7. Do not enable Databricks SQL until its governed global Connection is loaded
   and its access token has the intended least privilege.
8. Do not deploy older application code against a newer/incompatible database.

## 6. References

- [Create Azure Database for PostgreSQL Flexible Server](https://learn.microsoft.com/en-us/azure/postgresql/flexible-server/quickstart-create-server)
- [PostgreSQL firewall rules](https://learn.microsoft.com/en-us/azure/postgresql/security/security-firewall-rules)
- [Configure Python on Linux App Service](https://learn.microsoft.com/en-us/azure/app-service/configure-language-python)
- [Deploy an App Service ZIP](https://learn.microsoft.com/en-us/azure/app-service/deploy-zip)
- [Azure CLI configuration options](https://learn.microsoft.com/en-us/cli/azure/azure-cli-configuration)
- [Use Key Vault references in App Service](https://learn.microsoft.com/en-us/azure/app-service/app-service-key-vault-references)
- [Secure an App Service MCP server for VS Code](https://learn.microsoft.com/en-us/azure/app-service/configure-authentication-mcp-server-vscode)
- [Configure Microsoft Entra authentication for App Service](https://learn.microsoft.com/en-us/azure/app-service/configure-authentication-provider-aad)
- [Agent Plugins 1.0 specification](https://agent-plugins.org/specification)
- [Agent Plugins MCP configuration](https://agent-plugins.org/plugin-authors/mcp-servers)
- [Agent plugins in VS Code](https://code.visualstudio.com/docs/agent-customization/agent-plugins)

Repository-specific sources:

- `database/README.md`
- `mcp_server/README.md`
- `atlas/atlas-plugin/plugin.json`
- `atlas/atlas-plugin/mcp.json`
- `atlas/atlas-plugin/docs/usage-guide.md`
- `docs/security.md`
