# GDS Agent Plugin

Portable Agent Plugins 1.0 package. It connects compatible agent clients to the
GDS Workbench MCP server and teaches GDS concepts and governed workflows. The
package also includes a local browser Data Workbench for Metadata and Model
Snapshots; that utility is not a VS Code webview and does not depend on an editor.
Model workflows cover Model Details/Scope, Profiling, Analysis, Assertions,
Conceptual, Logical, Dimensional, and Mapping records as one governed graph.
The profiling skill can run aggregate-only, batch-aware Databricks SQL and prepare
Change Set-ready Profile records without exposing source rows or credentials.

## Install in VS Code

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
6. Run `Chat: Configure Skills` and confirm these skills appear:

   ```text
   understand-gds                 manage-gds-metadata
   manage-gds-model
   open-gds-metadata-workbench    author-model-metadata
   build-conceptual-model         build-logical-model
   build-dimensional-model        build-data-mapping
   profile-gds-data
   grill-data-model               run-data-modeling-goal
   ```

7. In Agent chat, invoke a skill such as `/gds:build-logical-model` or describe
   the matching task naturally.

If this workspace already registers the remote server in `.vscode/mcp.json`,
disable that registration while using the plugin connection. Multiple
registrations expose duplicate tool names.

## What is packaged

```text
gds/
├── plugin.json
├── mcp.json
├── tool-contract.json
├── README.md
├── references/
│   ├── model-tools.md
│   ├── model-datasets.md
│   ├── governed-model-workflow.md
│   ├── modeling-method.md
│   └── decision-record.md
└── skills/
    ├── build-conceptual-model/{SKILL.md,agents/openai.yaml}
    ├── build-logical-model/{SKILL.md,agents/openai.yaml}
    ├── build-dimensional-model/{SKILL.md,agents/openai.yaml}
    ├── build-data-mapping/{SKILL.md,agents/openai.yaml}
    ├── profile-gds-data/{SKILL.md,agents/openai.yaml,references/,scripts/}
    ├── author-model-metadata/{SKILL.md,agents/openai.yaml}
    ├── manage-gds-model/{SKILL.md,agents/openai.yaml}
    ├── grill-data-model/{SKILL.md,agents/openai.yaml,references/}
    ├── run-data-modeling-goal/{SKILL.md,agents/openai.yaml,references/}
    ├── understand-gds/
    │   ├── SKILL.md
    │   ├── agents/openai.yaml
    │   └── references/gds-overview.md
    ├── manage-gds-metadata/
    │   ├── SKILL.md
    │   ├── agents/openai.yaml
    │   ├── references/
    │   └── scripts/
    │       ├── inspect-metadata-catalog.ps1
    │       ├── inspect-metadata-catalog.sh
    │       ├── initialize-metadata-change-set.ps1
    │       ├── initialize-metadata-change-set.sh
    │       ├── initialize-gds-workspace.ps1
    │       ├── initialize-gds-workspace.sh
    │       ├── build-stage-review.js
    │       ├── metadata-schema.ps1
    │       ├── prepare-metadata-stage-review.ps1
    │       ├── prepare-metadata-stage-review.sh
    │       ├── remove-local-metadata-record.ps1
    │       ├── remove-local-metadata-record.sh
    │       ├── upsert-local-metadata-record.ps1
    │       ├── upsert-local-metadata-record.sh
    │       ├── validate-local-change-set.ps1
    │       ├── validate-local-change-set.sh
    │       ├── validate-metadata-dataset.js
    │       ├── validate-metadata-snapshot.ps1
    │       ├── validate-metadata-snapshot.sh
    │       ├── update-local-change-set-state.ps1
    │       └── update-local-change-set-state.sh
    └── open-gds-metadata-workbench/
        ├── SKILL.md
        ├── scripts/{open-gds-metadata-workbench.ps1,open-gds-metadata-workbench.sh}
        └── assets/workbench/{index.html,styles.css,logic.js,app.js}
```

`mcp.json` contains only the HTTPS endpoint. It contains no token, client
secret, password, or authorization header. VS Code owns client authentication;
the MCP server derives the Principal and Tenant authorization server-side.
`tool-contract.json` records the exact 51-tool schema fingerprint expected by
this release; `/health/ready` exposes the deployed fingerprint for parity checks.

## Quick smoke test

There is no `build_metadata_change_set` MCP tool. Use
`/gds:manage-gds-metadata` to build a local draft; the governed server lifecycle is
`create_metadata_change_set` → `stage_metadata_change_set` →
`validate_metadata_change_set` → `apply_metadata_change_set`. Use
`/gds:manage-gds-model` for the corresponding Model lifecycle.

Ask the agent:

```text
List the GDS Tenants I can access. Do not make any changes.
```

Then confirm it uses `list_tenants` without acquiring a lock. For a change
request, confirm it checks/acquires the Tenant Lock and stops before Apply for
explicit approval.

To prepare a bounded modeling goal without starting it, ask:

```text
Use run-data-modeling-goal to give me a paste-ready goal prompt for a validated
Logical model. Do not start the goal.
```

To prepare aggregate profiling evidence for a Model Change Set, ask:

```text
Use profile-gds-data to profile this registered table in TEST. Use its configured
batch Attribute and ask me for the batch ID if it is missing.
```

To open the local utility, ask:

```text
Open the GDS Data Workbench.
```

The utility opens in the default browser. Direct local folder editing requires
current Chrome or Edge. It reads `GDS/metadata-snapshot` or
`GDS/model-snapshot` and writes only the matching local Change Set folder; it
never calls MCP or PostgreSQL.
