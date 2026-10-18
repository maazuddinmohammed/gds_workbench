---
name: atlas-project-change
description: Change an existing Atlas project safely, tracing dependency effects across models, Mapping, Code, Validation and registrations before editing. Use for updates to applied designs, Project settings or rules where downstream impact matters.
---

# Change an existing project safely

Goal: make the requested difference and account for its real downstream effects, without regenerating unaffected work.

## When to use

- Change grain, identity, type, nullability, relationships, history or a business rule in applied work, or update Project settings.
- Design itself happens in the owning skill: [conceptual](../atlas-conceptual-model/SKILL.md), [logical](../atlas-logical-model/SKILL.md), [dimensional](../atlas-dimensional-model/SKILL.md), [mapping](../atlas-mapping/SKILL.md), [code](../atlas-code-generation/SKILL.md), [metadata](../atlas-metadata/SKILL.md), or [source analysis](../atlas-source-analysis/SKILL.md) for Project enrichment. A "why" question goes to [investigate](../atlas-investigate/SKILL.md) first.

## What you need

- [Working context](../../references/working-method.md) and its golden rules.
- Installed Snapshots, current applied records and pending edits. Authoritative freshness comes from server reads of the current Project revision; `status` and `next` show local state only.
- The requested behavior and the exact affected Project and Entities.

## Steps

1. Read the affected records and neighbors with `select --session <dir> --area project --dataset <name> --view effective`.
2. State the before and after: grain, identity, type, nullability, relationship, history or rule.
3. Trace real dependencies with [impact and update scope](../../references/methods/change-impact.md): source supports, relationships, Mapping branches, Code assignments, Validation definitions and registrations. Names or a new Project revision prove nothing.
4. Classify definite and possible effects, reusable work and blocked or unknown dependencies; the account may be incomplete. The optional format is `templates/change-impact.md`.
5. Make one coherent change at a time in the owning skill. Project policies use [settings](../../references/project/settings.md) through `project_details`; never rename the Project or change web-agent defaults. Metadata natural-key changes are [manual corrections](../../references/metadata/editing.md#manual-natural-key-changes).
6. Verify the changed records and relevant neighbors with [verify](../atlas-verify/SKILL.md); repair affected downstream work only within the authorized scope.
7. Submit each area's complete related batch with the [Change Set lifecycle](../../references/change-set-lifecycle.md) by repeating `next --session <dir> --area <area>`; Metadata and Project apply separately, in dependency order.

## Done when

- The requested change is made, checked and explained with its evidence.
- Affected, preserved and blocked downstream work is listed; nothing protected is marked current.
- Drafted, validated and applied states are reported accurately.

## Ask the user when

- A necessary dependency would add material scope, or intents conflict.
- A protected record blocks the change; never bypass a lock by renaming or recreating records.
- Approving Stage and, separately, Apply.

Pending upstream changes are not applied inputs. Task text or intent never authorizes retrying an uncertain Stage.

## Next

After Apply, refresh Snapshots and confirm the saved result before dependent work.
