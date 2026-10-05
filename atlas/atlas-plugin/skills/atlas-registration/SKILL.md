---
name: atlas-registration
description: Register applied model targets or generated transformation artifacts in Atlas physical/runtime Metadata, with optional local creation DDL. Use for target or Process registration; does not deploy, upload files or execute pipelines.
---

# Register approved outputs

Select the requested registration procedure; these are independent operations with different prerequisites, not a compulsory sequence.

| Outcome | Load only this procedure | Required applied inputs |
|---|---|---|
| Register Silver/Gold targets or prepare creation DDL | [Target registration](../../references/methods/registration/targets.md), then its [target-definition guide](../../references/methods/registration/target-definition.md) | Selected Logical/Dimensional Entities and Attributes, resolved owner/placement and current Metadata. DDL-only requests need no Metadata Change Set. |
| Register generated files with runtime Process metadata | [Process registration](../../references/methods/registration/processes.md) | Code, source-System assignments, Mapping, separately registered compatible targets and confirmed runtime/group/type details. |

Follow [working context](../../references/working-method.md), [record state](../../references/record-state.md) and [impact/update scope](../../references/methods/change-impact.md). Reuse verified choices and valid existing registrations. Scope a change from actual dependencies; changed code text alone does not require a new Process identity.

Resolve physical owner separately from Model Tenant and GDS placement. Multiple owners use separate Metadata roots and Change Sets. Show unresolved ownership, schema assignments or runtime locations before completing dependent records. A local output folder is not automatically a deployed runtime path.

Creation DDL remains an optional, separately selected local artifact. It cannot be executed by `execute_databricks_sql`; registration Apply does not create/alter tables. Registration is not a prerequisite for Mapping or Code generation. Process order is a positive runtime stage, not a mechanical offset of Mapping order.

Use [local validation](../../references/local-validation.md) and the selected procedure's semantic checks. Review the complete related batch and follow the [Change Set lifecycle](../../references/change-set-lifecycle.md) for Metadata changes. Verify saved registrations after confirmed Apply; report DDL as generated, not executed. Runtime file existence, scheduling and deployment remain unverified unless independently established through an authorized supported route.

Focused corrections to existing Process/Copy configuration use [metadata](../atlas-metadata/SKILL.md). Missing transformation logic returns to [mapping](../atlas-mapping/SKILL.md) or [code generation](../atlas-code-generation/SKILL.md); registration does not invent that logic or regroup artifacts.
