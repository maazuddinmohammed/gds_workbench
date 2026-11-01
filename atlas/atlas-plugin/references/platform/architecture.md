# How Atlas works

Load for architecture questions or to resolve responsibility; ordinary workflows need only their relevant record and method guides.

## Component names

| Name | Responsibility |
|---|---|
| **Atlas** | The overall product. |
| **Atlas Plugin** | Agent skills, references and local helpers. |
| **Atlas Local Workbench** | Local browser interface for reviewing and editing drafts. |
| **Atlas Bridge** | VS Code extension for Microsoft sign-in, connection checks and approved Stage uploads. |
| **Atlas MCP** | Server exposing governed tools to agents and Atlas Bridge. |
| **Atlas Platform** | Web application for administration, metadata, Projects and workflows. |

Use these names in explanations and handoffs. Stage and Apply remain workflow actions.

Atlas Local Workbench source is bundled in `atlas-local-workbench/`. Its launchers
are `scripts/open-local-workbench.sh` and `scripts/open-local-workbench.ps1`.

## Concepts and ownership

- **Tenant** is an authorization and metadata ownership boundary. Physical storage can belong to a different GDS Tenant; never infer ownership from placement.
- **System** identifies a contributing source/business system. A **Connection** identifies registered access or placement; its secret values are not agent inputs.
- **Object / Attribute** describe physical relations and columns. Project Input Scope selects eligible applied inputs and is configured outside plugin authoring.
- A **Project** owns scoped evidence, Context records, Subject Areas, Logical and Dimensional designs, Mapping, Code and Validation definitions. [Terminology](../terminology.md) and individual record guides distinguish these meanings.
- **Subject Areas** group the Bronze Input Scope into business capabilities; each Logical or Dimensional Build works on one area's Objects at a time while the Project keeps one model per layer. Areas are focus windows, not evidence or authorization boundaries. **Logical** defines normalized grain, identity and relationships from its own eligible evidence; **Dimensional** consumes applied Logical records to define analytical grain, measures and history.
- **Mapping** specifies transformations for target/System branches. **Code** implements saved Mapping. **Validation definitions** describe checks; saving them does not execute them.

## Execution boundaries

```text
Agent: intent, evidence interpretation, modeling decisions
    → local helpers: snapshots, complete draft records, deterministic checks
    → Atlas Local Workbench: review and local editing
    → Atlas Bridge: bounded, digest-verified transport
    → Atlas MCP/shared application/PostgreSQL: authorization, locks, revisions, validation, Apply
```

Atlas Platform and Atlas MCP use shared backend/domain rules. The local browser and CLI share validation/serialization; they cannot replace server authorization. Atlas Plugin, Atlas Bridge and deployed backend are separately versioned. Check actual capabilities before claiming support.

Applied records are authoritative. Snapshots are immutable baselines. The effective local view overlays pending complete records by canonical identity. See [state](state.md), [record protection](../record-state.md) and [governance](governance.md).

## Maintaining the plugin

Skills own task sequences, references own modeling knowledge, machine contracts own syntax, and validators own enforceable checks. Do not copy field schemas or tool arguments into every skill. Read only relevant references; relationship links are not recursive loading instructions.

Keep Tenant/Project-specific facts in governed records or bound task evidence. Only confirmed reusable rules belong in [domain knowledge](../domains/index.md). A rationale inferred from today's project is not recorded historical intent. Templates format existing evidence; they do not create another state store.
