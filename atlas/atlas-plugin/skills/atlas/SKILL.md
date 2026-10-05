---
name: atlas
description: Start or resume Atlas and route a data-modeling request to the needed workflow using current scope, evidence and artifact readiness. Use for unclear intent or work spanning stages; clear tasks can enter their skill directly.
---

# Atlas modeling playbook

Identify the requested outcome, inspect relevant state and load only the needed workflow. Do not make the user explain the SDLC or complete a setup questionnaire before a simple answer.

## Resolve the next useful step

Follow [working context](../../references/working-method.md) once: reuse verified selections, preserve drafts, resolve only missing identity and inspect relevant unfinished work. A general explanation needs no Tenant/Model/workspace or Workbench. Open Workbench when local authoring/review needs it.

Use [artifact readiness](../../references/platform/readiness.md), not the last skill name or one global Model stage. Applied records, pending drafts, coverage and evidence freshness may differ for each selected artifact. Do not treat a task note as approval or a pending prerequisite as applied.

| Requested outcome | Load |
|---|---|
| Explain Atlas, a model, lineage or why an entity exists | [Investigate](../atlas-investigate/SKILL.md) |
| Profile/analyze source tables, grain, keys or relationships | [Source analysis](../atlas-source-analysis/SKILL.md) |
| Define business concepts and relationships | [Conceptual model](../atlas-conceptual-model/SKILL.md) |
| Build normalized Entities, Attributes and Submodels | [Logical model](../atlas-logical-model/SKILL.md) |
| Design dimensions, facts, measures or history | [Dimensional model](../atlas-dimensional-model/SKILL.md) |
| Map sources to an applied target model | [Mapping](../atlas-mapping/SKILL.md) |
| Generate transformation SQL from applied Mapping | [Code generation](../atlas-code-generation/SKILL.md) |
| Check a model/artifact or author SQL Validation definitions | [Verify](../atlas-verify/SKILL.md) |
| Modify an existing model and assess dependency effects | [Model change](../atlas-model-change/SKILL.md) |
| Correct physical Metadata, descriptions or ingestion settings | [Metadata](../atlas-metadata/SKILL.md) |
| Register model targets or generated files for runtime handoff | [Registration](../atlas-registration/SKILL.md) |

A source-to-logical request can use analysis → conceptual work when useful → logical design. An existing-model Mapping request can start at Mapping. A why-and-update request investigates rationale before impact/change. Reuse valid evidence and skip unnecessary stages; never skip an actual prerequisite. Stop at the requested outcome.

Guided explanation is the default; requested Grill Me uses the same skill with [interview guidance](../../references/modeling-interview.md#interaction-mode). Resolve consequential unknowns without forcing a mode menu. Delegation guidance loads only before authorized delegation.

Direct entry uses the same context rules without looping back through startup. Narrow questions may need only one reference. For an unsupported request, explain the specific [capability gap](../../references/platform/capabilities.md) and continue independent supported work. No generic fallback expands permissions.

Verify each coherent authoring part. Related changes use the [Change Set lifecycle](../../references/change-set-lifecycle.md); choosing a workflow never approves Stage, Apply, SQL execution or deployment. Consult [architecture](../../references/platform/architecture.md) only when platform understanding is needed.
