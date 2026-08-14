# GDS Agent Plugin

Portable Agent Plugin 1.0 for VS Code. It connects to the GDS Workbench MCP
server and teaches an agent GDS concepts and governed workflows. The current
package includes general GDS guidance and metadata read/change guidance.

## Install from this folder

1. Open VS Code Settings (JSON).
2. Enable Agent Plugins and register the extracted plugin directory:

   ```json
   {
     "chat.plugins.enabled": true,
     "chat.pluginLocations": {
       "/absolute/path/to/gds": true
     }
   }
   ```

3. Run `Developer: Reload Window`.
4. Run `Chat: Open Customizations` and confirm `gds` appears.
5. Run `MCP: List Servers`, start `gds-workbench`, and complete the Entra
   browser sign-in if VS Code requests it.
6. Run `Chat: Configure Skills` and confirm `understand-gds` and
   `manage-gds-metadata` appear.
7. In Agent chat, invoke `/gds:understand-gds` or
   `/gds:manage-gds-metadata`. The agent can also select either skill from the
   request.

If this workspace already registers the remote server directly or through a
bridge in `.vscode/mcp.json`, disable those registrations while using the
plugin connection. Multiple registrations expose duplicate tool names.

## What is packaged

```text
gds/
├── plugin.json
├── mcp.json
├── README.md
└── skills/
    ├── understand-gds/
    │   ├── SKILL.md
    │   └── references/gds-overview.md
    └── manage-gds-metadata/
        ├── SKILL.md
        ├── references/
        └── scripts/
            ├── inspect-metadata-catalog.ps1
            ├── inspect-metadata-catalog.sh
            ├── initialize-metadata-change-set.ps1
            ├── initialize-metadata-change-set.sh
            ├── initialize-gds-workspace.ps1
            ├── initialize-gds-workspace.sh
            ├── build-stage-review.js
            ├── metadata-schema.ps1
            ├── prepare-metadata-stage-review.ps1
            ├── prepare-metadata-stage-review.sh
            ├── remove-local-metadata-record.ps1
            ├── remove-local-metadata-record.sh
            ├── upsert-local-metadata-record.ps1
            ├── upsert-local-metadata-record.sh
            ├── validate-local-change-set.ps1
            ├── validate-local-change-set.sh
            ├── validate-metadata-dataset.js
            ├── validate-metadata-snapshot.ps1
            ├── validate-metadata-snapshot.sh
            ├── update-local-change-set-state.ps1
            └── update-local-change-set-state.sh
```

`mcp.json` contains only the HTTPS endpoint. It contains no token, client
secret, password, or authorization header. VS Code owns client authentication;
the MCP server derives the Principal and Tenant authorization server-side.

## Quick smoke test

Ask the agent:

```text
List the GDS Tenants I can access. Do not make any changes.
```

Then confirm it uses `list_tenants` without acquiring a lock. For a change
request, confirm it checks/acquires the Tenant Lock and stops before Apply for
explicit approval.
