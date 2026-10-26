---
name: atlas
description: Start or resume Atlas and route a data-modeling request to the needed workflow using current scope, evidence and artifact readiness. Use for unclear intent or work spanning stages; clear tasks can enter their skill directly.
---

# Atlas modeling playbook

Goal: route each request to the one workflow that produces it, reusing current state, without making the user explain the SDLC or answer setup questionnaires.

## When to use

- Unclear intent, a new or resumed session, or work spanning several stages. Clear tasks can enter their skill directly.

## What you need

- [Working context](../../references/working-method.md) and its golden rules. General explanations need no Tenant, Project, workspace or Workbench.
- In an existing workspace, `status --session <dir>` and `next --session <dir>` show the active task, unfinished work and the most urgent area.

## Steps

1. Identify the requested outcome.
2. Check [artifact readiness](../../references/platform/readiness.md) for the selected artifacts, not the last skill used: applied records, pending drafts, coverage and evidence freshness can differ per artifact. A task note is not approval; a pending prerequisite is not applied.
3. Load the one skill that owns the outcome:

| Requested outcome | Skill |
|---|---|
| Explain Atlas, a project, lineage or why an entity exists | [Investigate](../atlas-investigate/SKILL.md) |
| Profile, enrich or analyze sources, grain, keys or relationships | [Source analysis](../atlas-source-analysis/SKILL.md) |
| Group scope Objects by business capability | [Subject Areas](../atlas-subject-areas/SKILL.md) |
| Build normalized Entities, Attributes and relationships | [Logical model](../atlas-logical-model/SKILL.md) |
| Design dimensions, facts, measures or history | [Dimensional model](../atlas-dimensional-model/SKILL.md) |
| Map sources to an applied target | [Mapping](../atlas-mapping/SKILL.md) |
| Generate transformation SQL from applied Mapping | [Code generation](../atlas-code-generation/SKILL.md) |
| Check a project or artifact, or author SQL Validation | [Verify](../atlas-verify/SKILL.md) |
| Change an existing project and assess dependency effects | [Project change](../atlas-project-change/SKILL.md) |
| Correct physical Metadata, descriptions or ingestion settings | [Metadata](../atlas-metadata/SKILL.md) |
| Register targets or generated files for runtime handoff | [Registration](../atlas-registration/SKILL.md) |

4. Follow real dependencies without needless stages. Source-to-logical work prefers profiling, Project enrichment, analysis, then logical; these local phases may use pending earlier results, and backend Profiling needs a Snapshot refresh. Dimensional needs applied Logical; Mapping, Code and SQL Validation need applied inputs, refreshed after Apply. Existing-project Mapping can start at Mapping; why-and-update investigates first. Never skip an actual prerequisite.
5. For an unsupported request, explain the [capability gap](../../references/platform/capabilities.md) and continue independent supported work. No fallback expands permissions.

## Done when

- The owning skill delivered the requested outcome, and you stopped there.

## Ask the user when

- The outcome or its target Tenant, Project or Entities is genuinely ambiguous.
- Resuming unfinished work versus starting new work is unclear.

Guided explanation is the default; requested Grill Me runs inside the same skill. Choosing a workflow never approves Stage, Apply, SQL execution or deployment.

## Next

Saving work always follows the [Change Set lifecycle](../../references/change-set-lifecycle.md). Read [architecture](../../references/platform/architecture.md) only when platform understanding is needed.
