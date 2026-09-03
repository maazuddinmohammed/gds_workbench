# Fresh Azure deployment: database, MCP server, and GDS Agent Plugin

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
| Azure Storage account and private Blob container | Stores temporary Metadata, Model, and DBML ZIP snapshots |
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
   mcp_server/dist/gds-mcp-appservice-0.2.0.zip
   plugins/v2/dist/gds-agent-plugin-0.4.9.zip
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

## 3. Path A: create and configure resources in Azure Portal

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

### Step 4: install the database schema

From the repository root, set only non-secret connection values:

```bash
export PGHOST="<POSTGRES_SERVER>.postgres.database.azure.com"
export PGPORT="5432"
export PGDATABASE="gds_workbench"
export PGUSER="<POSTGRES_ADMIN>"
export PGSSLMODE="verify-full"
```

Run the read-only preflight. Enter the administrator password only at the
`psql` prompt:

```bash
psql -X -v ON_ERROR_STOP=1 -f database/00_preflight.sql
```

Stop if preflight fails. For a new empty database, install files `01` through
`12` exactly once and in this exact order:

`00_preflight.sql` also contains a disabled whole-server cleanup reference.
Never uncomment it during installation, retry, or migration. It is only for a
separate, backup-approved DBA retirement of the complete GDS server environment.

```bash
for file in \
  database/01_reference.sql \
  database/02_core.sql \
  database/03_security.sql \
  database/04_model.sql \
  database/05_workflow_analysis.sql \
  database/06_workflow_conceptual.sql \
  database/07_workflow_logical.sql \
  database/08_workflow_dimensional.sql \
  database/09_workflow_mapping.sql \
  database/10_workflow_code_validation.sql \
  database/11_workflow_eligibility.sql \
  database/12_application_configuration.sql \
  database/13_application_workflow_runs.sql \
  database/14_application_workflow_execution.sql \
  database/15_mcp_change_sets.sql \
  database/16_mcp_metadata_apply.sql \
  database/17_mcp_tool_call_log.sql \
  database/18_runtime_account.sql \
  database/19_runtime_integrity.sql
do
  psql -X -v ON_ERROR_STOP=1 --single-transaction -f "$file" || break
done
```

If a file fails, save the error and stop. Do not rerun earlier files and do not
drop, truncate, or reset the database.

Set distinct runtime login passwords interactively:

```bash
psql -X
```

Then run these commands inside `psql`:

```text
\password gds_mcp_runtime
\password gds_web_runtime
\quit
```

Store both generated passwords in your approved password manager. Finally,
verify the installation:

```bash
psql -X -v ON_ERROR_STOP=1 -f database/20_verify_install.sql
```

The last row must say:

```text
schema_version = 1.0.0
verification_status = passed
```

### Step 5: add initial data and user access

Install the required web application reference data first:

```bash
psql -X -v ON_ERROR_STOP=1 --single-transaction \
  -f database/seed/04_application_reference.sql
```

This installs exactly 49 workflow stages and 80 backend-resolved prompt
variables. It contains no credentials, prompt bodies, connection values, or
business data and is safe to replay unchanged.

Choose one route:

- Development only: run `database/seed/01_metadata_snapshot_demo.sql`, then
  copy and complete `database/seed/02_human_principal_access.template.sql`.
- Real environment: use an independently reviewed operator process to load the
  approved Tenant, metadata, and Entra Principal/access records. This repository
  no longer ships an Excel loader.

Do not run demo seed data in production. A successfully authenticated Entra
user must also have an active matching database Principal and Tenant access.

After the active Super Admin identity exists, install the 36 agentic global
defaults from `database/seed/05_global_prompt_defaults.template.sql` by
following `database/seed/README.md`. Replace its identity placeholders with
that exact Super Admin identity. The script is replay-safe and does not create
Prompts for deterministic stages such as Profiling.

### Step 6: create private snapshot storage

1. Create a **Storage account** in the same region/resource group.
2. Use StorageV2, Standard LRS for development, TLS 1.2 or later.
3. Disable anonymous Blob access.
4. Open **Containers** and create `snapshots` with **Private** access.
5. Under **Lifecycle management**, add deletion rules for `metadata/`,
   `model/`, and `dbml/` after at least 24 hours.

Keep the account network-accessible to the web app. Snapshot download URLs are
short-lived, read-only user-delegation SAS URLs; the container itself stays
private.

### Step 7: create Key Vault

1. Create a **Key vault** in the resource group.
2. Use the Azure RBAC permission model.
3. Add two secrets through the portal:
   - the complete runtime PostgreSQL DSN;
   - a random cursor-signing value of at least 32 bytes.

The DSN must use the runtime login, the `gds_workbench` database, and
`sslmode=verify-full`:

```text
host=<POSTGRES_SERVER>.postgres.database.azure.com port=5432 dbname=gds_workbench user=gds_mcp_runtime password=<RUNTIME_PASSWORD> sslmode=verify-full
```

### Step 8: create the Linux web app

1. Create **Web App**.
2. Choose **Code**, **Linux**, and **Python 3.14**.
3. Create/select the App Service plan. B1 is adequate for a small development
   deployment; size production from actual load.
4. Create the web app.
5. Open **Settings > Configuration > General settings**.
6. Set **Startup Command** to `startup.sh`.
7. Turn on **HTTPS Only** and **Always On**.
8. Open **Identity** and enable the system-assigned managed identity.

### Step 9: grant the web app access

Grant the web app's system-assigned identity:

1. **Key Vault Secrets User** on the Key Vault.
2. **Storage Blob Data Contributor** on only the `snapshots` container.
3. **Storage Blob Delegator** on the storage account.

The first role lets App Service resolve Key Vault references. The storage roles
let the app create/read private snapshot blobs and mint read-only user-delegation
SAS URLs.

### Step 10: configure App Service settings

Open **Web App > Settings > Environment variables** and add:

| Setting | Value |
|---|---|
| `SCM_DO_BUILD_DURING_DEPLOYMENT` | `1` |
| `GDS_ENVIRONMENT` | `production` |
| `GDS_DATABASE_DSN` | Key Vault reference to the runtime DSN |
| `GDS_CURSOR_SIGNING_KEY` | Key Vault reference to the cursor key |
| `GDS_MCP_PUBLIC_URL` | `https://<WEB_APP>.azurewebsites.net/mcp` |
| `GDS_ENTRA_TENANT_ID` | Your Entra Directory/Tenant ID |
| `GDS_ENTRA_API_CLIENT_ID` | Add after Step 11 creates the app registration |
| `GDS_METADATA_SNAPSHOT_STORAGE_ACCOUNT_URL` | `https://<STORAGE_ACCOUNT>.blob.core.windows.net` |
| `GDS_METADATA_SNAPSHOT_STORAGE_CONTAINER` | `snapshots` |

Do not add `GDS_METADATA_SNAPSHOT_MANAGED_IDENTITY_CLIENT_ID` when using the
system-assigned identity. Save the settings and confirm both Key Vault
references show a resolved/healthy status.

### Step 11: configure Microsoft Entra and Easy Auth

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

### Step 12: deploy the MCP ZIP

Azure's Kudu drag-and-drop ZIP page does not support Linux App Service. Use
Azure Cloud Shell in the portal or a local authenticated Azure CLI instead.
Upload/select the ZIP in Cloud Shell, then run:

```bash
az webapp deploy \
  --resource-group "<RESOURCE_GROUP>" \
  --name "<WEB_APP>" \
  --src-path "gds-mcp-appservice-0.2.0.zip" \
  --type zip \
  --restart true \
  --track-status true
```

If running locally from the repository root, use:

```text
mcp_server/dist/gds-mcp-appservice-0.2.0.zip
```

### Step 13: verify the deployment

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

## 4. Path B: create the infrastructure with Azure CLI

Use this path instead of Portal Steps 1-10. Run it from the repository root.
The Microsoft Entra registration is intentionally completed with Portal Step 11
because that one-time screen is clearer and safer than editing nested Microsoft
Graph application objects in a beginner runbook.

### Step 1: sign in and set names

```bash
az login
az account set --subscription "<SUBSCRIPTION_ID>"

GDS_RG="<RESOURCE_GROUP>"
GDS_LOCATION="<REGION>"
GDS_PG_SERVER="<POSTGRES_SERVER>"
GDS_DATABASE="gds_workbench"
GDS_PG_ADMIN="<POSTGRES_ADMIN>"
GDS_PLAN="<APP_SERVICE_PLAN>"
GDS_WEB_APP="<WEB_APP>"
GDS_STORAGE="<STORAGE_ACCOUNT>"
GDS_CONTAINER="snapshots"
GDS_VAULT="<KEY_VAULT>"
GDS_MCP_URL="https://${GDS_WEB_APP}.azurewebsites.net/mcp"
GDS_TENANT_ID="$(az account show --query tenantId -o tsv)"
```

### Step 2: create the resource group and PostgreSQL

Read the administrator password without putting it in shell history:

```bash
read -r -s -p "PostgreSQL administrator password: " GDS_PG_ADMIN_PASSWORD
echo
```

Create the resources:

```bash
az group create \
  --name "$GDS_RG" \
  --location "$GDS_LOCATION" \
  --output none

az postgres flexible-server create \
  --resource-group "$GDS_RG" \
  --name "$GDS_PG_SERVER" \
  --location "$GDS_LOCATION" \
  --admin-user "$GDS_PG_ADMIN" \
  --admin-password "$GDS_PG_ADMIN_PASSWORD" \
  --version 18 \
  --tier Burstable \
  --sku-name Standard_B1ms \
  --storage-size 32 \
  --public-access 0.0.0.0 \
  --yes \
  --output none

unset GDS_PG_ADMIN_PASSWORD

az postgres flexible-server db create \
  --resource-group "$GDS_RG" \
  --server-name "$GDS_PG_SERVER" \
  --database-name "$GDS_DATABASE" \
  --output none
```

`0.0.0.0` allows connections from Azure services. Add a temporary firewall rule
for your own public IP before running local `psql`:

```bash
az postgres flexible-server firewall-rule create \
  --resource-group "$GDS_RG" \
  --name "$GDS_PG_SERVER" \
  --rule-name allow-bootstrap-client \
  --start-ip-address "<YOUR_PUBLIC_IP>" \
  --end-ip-address "<YOUR_PUBLIC_IP>" \
  --output none
```

Now perform Portal Path Steps 4 and 5 to install/verify the schema and load the
initial data.

### Step 3: create storage

```bash
az storage account create \
  --resource-group "$GDS_RG" \
  --name "$GDS_STORAGE" \
  --location "$GDS_LOCATION" \
  --kind StorageV2 \
  --sku Standard_LRS \
  --min-tls-version TLS1_2 \
  --allow-blob-public-access false \
  --output none

GDS_OPERATOR_ID="$(az ad signed-in-user show --query id -o tsv)"
GDS_STORAGE_ID="$(az storage account show \
  --resource-group "$GDS_RG" \
  --name "$GDS_STORAGE" \
  --query id -o tsv)"

az role assignment create \
  --assignee-object-id "$GDS_OPERATOR_ID" \
  --assignee-principal-type User \
  --role "Storage Blob Data Contributor" \
  --scope "$GDS_STORAGE_ID" \
  --output none

az storage container create \
  --account-name "$GDS_STORAGE" \
  --name "$GDS_CONTAINER" \
  --auth-mode login \
  --public-access off \
  --output none

GDS_LIFECYCLE_POLICY='{"rules":[{"enabled":true,"name":"delete-expired-snapshots","type":"Lifecycle","definition":{"actions":{"baseBlob":{"delete":{"daysAfterModificationGreaterThan":1}}},"filters":{"blobTypes":["blockBlob"],"prefixMatch":["snapshots/metadata/","snapshots/model/","snapshots/dbml/"]}}}]}'

az storage account management-policy create \
  --resource-group "$GDS_RG" \
  --account-name "$GDS_STORAGE" \
  --policy "$GDS_LIFECYCLE_POLICY" \
  --output none

unset GDS_LIFECYCLE_POLICY
```

RBAC can take several minutes to propagate. If container creation returns 403,
wait and retry the same non-destructive command.

### Step 4: create Key Vault and the web app

```bash
az keyvault create \
  --resource-group "$GDS_RG" \
  --name "$GDS_VAULT" \
  --location "$GDS_LOCATION" \
  --enable-rbac-authorization true \
  --output none

GDS_VAULT_ID="$(az keyvault show \
  --resource-group "$GDS_RG" \
  --name "$GDS_VAULT" \
  --query id -o tsv)"

az role assignment create \
  --assignee-object-id "$GDS_OPERATOR_ID" \
  --assignee-principal-type User \
  --role "Key Vault Secrets Officer" \
  --scope "$GDS_VAULT_ID" \
  --output none

az appservice plan create \
  --resource-group "$GDS_RG" \
  --name "$GDS_PLAN" \
  --location "$GDS_LOCATION" \
  --is-linux \
  --sku B1 \
  --output none

az webapp create \
  --resource-group "$GDS_RG" \
  --plan "$GDS_PLAN" \
  --name "$GDS_WEB_APP" \
  --runtime "PYTHON:3.14" \
  --startup-file "startup.sh" \
  --assign-identity "[system]" \
  --https-only true \
  --output none
```

### Step 5: grant the web app identity access

```bash
GDS_WEB_IDENTITY="$(az webapp identity show \
  --resource-group "$GDS_RG" \
  --name "$GDS_WEB_APP" \
  --query principalId -o tsv)"

GDS_CONTAINER_ID="${GDS_STORAGE_ID}/blobServices/default/containers/${GDS_CONTAINER}"

az role assignment create \
  --assignee-object-id "$GDS_WEB_IDENTITY" \
  --assignee-principal-type ServicePrincipal \
  --role "Key Vault Secrets User" \
  --scope "$GDS_VAULT_ID" \
  --output none

az role assignment create \
  --assignee-object-id "$GDS_WEB_IDENTITY" \
  --assignee-principal-type ServicePrincipal \
  --role "Storage Blob Data Contributor" \
  --scope "$GDS_CONTAINER_ID" \
  --output none

az role assignment create \
  --assignee-object-id "$GDS_WEB_IDENTITY" \
  --assignee-principal-type ServicePrincipal \
  --role "Storage Blob Delegator" \
  --scope "$GDS_STORAGE_ID" \
  --output none
```

### Step 6: store runtime secrets

Enter the runtime database password created with `\password`:

```bash
read -r -s -p "gds_mcp_runtime password: " GDS_RUNTIME_PASSWORD
echo
GDS_DATABASE_DSN="host=${GDS_PG_SERVER}.postgres.database.azure.com port=5432 dbname=${GDS_DATABASE} user=gds_mcp_runtime password=${GDS_RUNTIME_PASSWORD} sslmode=verify-full"
GDS_CURSOR_KEY="$(openssl rand -base64 48)"
```

Store both values without printing them:

```bash
az keyvault secret set \
  --vault-name "$GDS_VAULT" \
  --name "<DATABASE_DSN_SECRET_NAME>" \
  --value "$GDS_DATABASE_DSN" \
  --output none

az keyvault secret set \
  --vault-name "$GDS_VAULT" \
  --name "<CURSOR_KEY_SECRET_NAME>" \
  --value "$GDS_CURSOR_KEY" \
  --output none

unset GDS_RUNTIME_PASSWORD GDS_DATABASE_DSN GDS_CURSOR_KEY
```

### Step 7: configure non-secret app settings

The two Key Vault references below are placeholders for the names chosen in the
previous step:

```bash
az webapp config appsettings set \
  --resource-group "$GDS_RG" \
  --name "$GDS_WEB_APP" \
  --settings \
    SCM_DO_BUILD_DURING_DEPLOYMENT=1 \
    GDS_ENVIRONMENT=production \
    GDS_DATABASE_DSN="@Microsoft.KeyVault(VaultName=${GDS_VAULT};SecretName=<DATABASE_DSN_SECRET_NAME>)" \
    GDS_CURSOR_SIGNING_KEY="@Microsoft.KeyVault(VaultName=${GDS_VAULT};SecretName=<CURSOR_KEY_SECRET_NAME>)" \
    GDS_MCP_PUBLIC_URL="$GDS_MCP_URL" \
    GDS_ENTRA_TENANT_ID="$GDS_TENANT_ID" \
    GDS_METADATA_SNAPSHOT_STORAGE_ACCOUNT_URL="https://${GDS_STORAGE}.blob.core.windows.net" \
    GDS_METADATA_SNAPSHOT_STORAGE_CONTAINER="$GDS_CONTAINER" \
  --output none

az webapp config set \
  --resource-group "$GDS_RG" \
  --name "$GDS_WEB_APP" \
  --linux-fx-version "PYTHON|3.14" \
  --startup-file "startup.sh" \
  --always-on true \
  --output none
```

### Step 8: configure Entra, deploy, and verify

1. Complete Portal Step 11.
2. Add the resulting API client ID:

   ```bash
   az webapp config appsettings set \
     --resource-group "$GDS_RG" \
     --name "$GDS_WEB_APP" \
     --settings GDS_ENTRA_API_CLIENT_ID="<ENTRA_API_CLIENT_ID>" \
     --output none
   ```

3. Deploy the MCP ZIP:

   ```bash
   az webapp deploy \
     --resource-group "$GDS_RG" \
     --name "$GDS_WEB_APP" \
     --src-path "mcp_server/dist/gds-mcp-appservice-0.2.0.zip" \
     --type zip \
     --restart true \
     --track-status true
   ```

4. Perform Portal Step 13.

## 5. Package and install the Agent Plugins 1.0 package in VS Code

### Step 1: build an endpoint-specific archive

Keep the tracked `plugins/v2/gds/mcp.json` unchanged. Inject the deployed MCP
URL into a new archive:

```bash
python3 plugins/build_gds_v2_plugin_zip.py \
  --output plugins/v2/dist/gds-agent-plugin-local.zip \
  --mcp-url "https://<WEB_APP>.azurewebsites.net/mcp"
```

The builder validates the Agent Plugins manifests and URL, refuses to overwrite
an existing archive, and prints the archive SHA-256 digest. Store that digest
with the release record.

### Step 2: inspect and publish it

Inspect the archive before distribution. Its root must contain one `gds/`
directory with these required paths:

```text
gds/plugin.json
gds/mcp.json
gds/skills/gds/SKILL.md
```

`plugin.json` and `mcp.json` must declare the Agent Plugins 1.0 schemas. The ZIP
is a transport artifact; VS Code does not install this ZIP directly. Distribute
it through an approved internal channel, then unzip it before registration.

### Step 3: register the unzipped plugin in VS Code

Unzip the archive into a reviewed local directory. In VS Code user
`settings.json`, enable Agent Plugins and register the exact `gds` directory
that contains `plugin.json`:

```json
{
  "chat.plugins.enabled": true,
  "chat.pluginLocations": {
    "/absolute/path/to/gds": true
  }
}
```

Use forward slashes or correctly escaped backslashes for a Windows path. Reload
the VS Code window after changing the setting.

For managed distribution, this repository already contains
`.github/plugin/marketplace.json`, whose `gds` entry points to
`./plugins/v2/gds`. Publish the repository, add its `owner/repository` value to
the VS Code `chat.plugins.marketplaces` setting, then install `gds` from the
Agent Plugins view. For a local clone, that setting also accepts a
`file:///absolute/path/to/repository` marketplace.

```json
{
  "chat.plugins.marketplaces": ["owner/repository"]
}
```

**Chat: Install Plugin From Source** requires a dedicated Git repository whose
root is the `gds` directory; this monorepository's root is a marketplace, not an
individual plugin root. Agent Plugins 1.0 standardizes the package;
installation and marketplace policy remain VS Code responsibilities.

### Step 4: verify discovery and authentication

1. Run **Chat: Configure Skills** and confirm the `gds` skill is present.
2. Run **MCP: List Servers** and confirm `gds-workbench` is present and enabled.
3. Open a fresh VS Code Chat in Agent mode and ask:

```text
List the GDS Tenants I can access. Do not make any changes.
```

Expected behavior:

1. VS Code completes its client-managed Microsoft Entra sign-in when required.
2. The server calls `list_tenants`.
3. Only Tenants allowed for the signed-in database Principal appear.
4. No Tenant Lock is acquired for this read-only request.

If the skill appears but the MCP server does not connect, recheck the packaged
URL, the protected-resource metadata paths, and the VS Code client registration
from Portal Step 11. Agent Plugins 1.0 does not embed OAuth credentials;
authentication remains client-managed.

## 6. Production hardening after the first successful deployment

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

## 7. Official references

- [Create Azure Database for PostgreSQL Flexible Server](https://learn.microsoft.com/en-us/azure/postgresql/flexible-server/quickstart-create-server)
- [PostgreSQL firewall rules](https://learn.microsoft.com/en-us/azure/postgresql/security/security-firewall-rules)
- [Configure Python on Linux App Service](https://learn.microsoft.com/en-us/azure/app-service/configure-language-python)
- [Deploy an App Service ZIP](https://learn.microsoft.com/en-us/azure/app-service/deploy-zip)
- [Use Key Vault references in App Service](https://learn.microsoft.com/en-us/azure/app-service/app-service-key-vault-references)
- [Secure an App Service MCP server for VS Code](https://learn.microsoft.com/en-us/azure/app-service/configure-authentication-mcp-server-vscode)
- [Configure Microsoft Entra authentication for App Service](https://learn.microsoft.com/en-us/azure/app-service/configure-authentication-provider-aad)
- [Agent Plugins 1.0 specification](https://agent-plugins.org/specification)
- [Agent Plugins MCP configuration](https://agent-plugins.org/plugin-authors/mcp-servers)
- [Agent plugins in VS Code](https://code.visualstudio.com/docs/agent-customization/agent-plugins)

Repository-specific sources:

- `database/README.md`
- `mcp_server/README.md`
- `plugins/v2/gds/plugin.json`
- `plugins/v2/gds/mcp.json`
- `plugins/v2/gds/docs/USER_GUIDE.md`
- `docs/security.md`
