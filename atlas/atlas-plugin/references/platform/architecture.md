# How Atlas works

Load for architecture questions or to resolve responsibility; ordinary workflows need only their relevant record and method guides.

## Concepts and ownership

- **Tenant** is an authorization and metadata ownership boundary. Physical storage can belong to a different GDS Tenant; never infer ownership from placement.
- **System** identifies a contributing source/business system. A **Connection** identifies registered access or placement; its secret values are not agent inputs.
- **Object / Attribute** describe physical relations and columns. Model Input Scope selects eligible applied inputs and is configured outside plugin authoring.
- A **Model** owns scoped evidence, Assertions, Conceptual, Logical and Dimensional designs, Mapping, Code and Validation definitions. [Terminology](../terminology.md) and individual record guides distinguish these meanings.
- **Conceptual** describes business meaning; **Logical** defines normalized grain, identity and relationships; **Dimensional** defines analytical grain, measures and history. A Submodel organizes a useful part of a design; it is not a separate authorization boundary.
- **Mapping** specifies transformations for target/System branches. **Code** implements saved Mapping. **Validation definitions** describe checks; saving them does not execute them.

## Execution boundaries

```text
Agent: intent, evidence interpretation, modeling decisions
    → local helpers: snapshots, complete draft records, deterministic checks
    → Workbench: review and local editing
    → approved host Stage runner: bounded, digest-verified transport
    → MCP/application/PostgreSQL: authorization, locks, revisions, validation, Apply
```

The web application and MCP use shared backend/domain rules. The local browser and CLI share validation/serialization; they cannot replace server authorization. Plugin, Stage Runner/connector and deployed backend are separately versioned. Check actual capabilities before claiming support.

Applied records are authoritative. Snapshots are immutable baselines. The effective local view overlays pending complete records by canonical identity. See [state](state.md), [record protection](../record-state.md) and [governance](governance.md).

## Maintaining the plugin

Skills own task sequences, references own modeling knowledge, machine contracts own syntax, and validators own enforceable checks. Do not copy field schemas or tool arguments into every skill. Read only relevant references; relationship links are not recursive loading instructions.

Keep Tenant/Model-specific facts in governed records or bound task evidence. Only confirmed reusable rules belong in [domain knowledge](../domains/index.md). A rationale inferred from today's model is not recorded historical intent. Templates format existing evidence; they do not create another state store.
