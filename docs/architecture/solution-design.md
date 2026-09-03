# GDS Workbench solution overview

Separate entry points. One governed PostgreSQL source of truth.

```mermaid
flowchart LR
    subgraph developerAccess["DEVELOPER ACCESS"]
        direction TB
        developer(["Developer"])
        vscode["VS Code<br/>GDS Plugin"]
        localHtml["Local HTML<br/>Workbench"]
        developer --> vscode
        vscode --- localHtml
    end

    subgraph mcpPlatform["MCP PLATFORM"]
        direction TB
        mcp["MCP Server<br/>Azure App Service"]
        keyVault["Key Vault"]
        storage["Storage Account<br/>Snapshots"]
        mcp ~~~ keyVault
        keyVault ~~~ storage
    end

    subgraph central[" "]
        direction TB
        postgres[("PostgreSQL<br/>SOURCE OF TRUTH<br/>Data · Authorization · Locks · Audit")]
        entra["Microsoft Entra ID<br/>MCP + Web Authentication"]
        postgres ~~~ entra
    end

    subgraph workflowPlatform["WORKFLOW PLATFORM"]
        direction TB
        workflows["GDS Workflows<br/>Shared Logic"]
        ai["Foundry + Databricks<br/>AI and Data"]
        workflows --> ai
    end

    subgraph webApp["DATABRICKS WEB APP"]
        direction TB
        react["React Front End"]
        fastapi["FastAPI"]
        react --> fastapi
    end

    subgraph webAccess["WEB & NOTEBOOK ACCESS"]
        direction TB
        browser["Web Browser"]
        notebooks["Databricks Notebooks"]
    end

    vscode -->|"MCP"| mcp
    mcp <-->|"Governed access"| postgres
    postgres <-->|"Governed state"| workflows
    workflows <-->|"API"| fastapi
    workflows <-->|"Run"| notebooks
    react <-->|"HTTPS"| browser

    classDef access fill:#EFF6FF,stroke:#2563EB,color:#0F172A,stroke-width:1px;
    classDef app fill:#EEF2FF,stroke:#4F46E5,color:#0F172A,stroke-width:1px;
    classDef source fill:#ECFDF5,stroke:#059669,color:#052E16,stroke-width:3px;
    classDef service fill:#F8FAFC,stroke:#64748B,color:#0F172A,stroke-width:1px;

    class developer,vscode,localHtml,browser,notebooks access;
    class mcp,workflows,react,fastapi app;
    class postgres source;
    class keyVault,storage,ai,entra service;

    style developerAccess fill:#F8FAFC,stroke:#93C5FD,stroke-width:1px;
    style webAccess fill:#F8FAFC,stroke:#93C5FD,stroke-width:1px;
    style central fill:transparent,stroke:transparent;
    style mcpPlatform fill:#FFFFFF,stroke:#C7D2FE,stroke-width:1px;
    style workflowPlatform fill:#FFFFFF,stroke:#C7D2FE,stroke-width:1px;
    style webApp fill:#FFFFFF,stroke:#C7D2FE,stroke-width:1px;
```

## Reading the diagram

- **Left:** developer access flows from VS Code to MCP.
- **Center:** PostgreSQL owns shared data and authorization.
- **Right:** the Web App and notebooks use the same GDS workflow logic.
- **Supporting services:** Entra ID, Key Vault, Storage, Foundry, and
  Databricks.

The workflow box is a logical view. Its code is packaged independently with the
Databricks Web App and notebooks; it is not a separate deployed service.

## References

- [Architecture overview](overview.md)
- [Security](../security.md)
- [MCP deployment](../AZURE_FRESH_DEPLOYMENT.md)
- [Web App deployment](../../web_app/DEPLOYMENT_GUIDE.md)
- [Notebook deployment](../../databricks_notebooks/README.md)
