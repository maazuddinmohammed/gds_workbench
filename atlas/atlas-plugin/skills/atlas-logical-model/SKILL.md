---
name: atlas-logical-model
description: Build or refine Atlas logical (Silver) Entities, Attributes and child-to-parent relationships with explicit grain, identity and normalization, one Subject Area at a time. Use for logical modeling or normalization requests; supports Guided explanation and requested Grill Me discussion in the same workflow.
---

# Build a logical model

Goal: one normalized Silver model with explicit grain, identity and traceable sources.

## When to use

- Build Silver Entities, Attributes, keys and relationships per Subject Area, or optimize existing ones.
- Not for: evidence gaps ([source analysis](../atlas-source-analysis/SKILL.md)), facts and dimensions ([dimensional](../atlas-dimensional-model/SKILL.md)) or applied designs with downstream work ([project change](../atlas-project-change/SKILL.md)).

## What you need

- [Working context](../../references/working-method.md) and its golden rules.
- Installed Metadata and Project Snapshots and active applied Input Scope; [Logical context](../../references/logical-build/context.md) lists what to read.
- Profiles, Project enrichment and Analysis from the effective local view; pending results count without Apply.

## Steps

1. With [logical design](../../references/logical-build/logical-design.md), **Build** one Subject Area at a time for named areas or unmodeled Objects; otherwise **Optimize** existing Entities.
2. Read with `select --session <dir> --area project --dataset <name> --view effective` until `next_cursor` is null: for a Build, the area's Objects, the Entities built from them and their neighbours. Reuse, never copy, an Entity built from a shared Object.
3. Record each Entity's row meaning, complete natural key and active `logical_entity_type` code. Normalize by real dependencies; matching names never prove a relationship. Under SQL policy `never`, label metadata findings unmeasured.
4. Write only new and changed records with `upsert-batch --session <dir> --area project --changes <JSON> --expected-digest <digest>` per [Logical records](../../references/project/logical.md): Relationships child -> parent; retirement through `*_is_active: false`, never deletion; configured schemas and naming; each physical Attribute source paired with its parent's Object source.
5. Add framework columns: run `policy-apply --session <dir> --layer logical --expected-digest <digest> --dry-run true`, show the result, then run it without `--dry-run`.
6. After each coherent batch, run `validate --session <dir> --area project` and `coverage --session <dir> --layer logical --subject-area <area>` (no area when optimizing). Persist supported foreign keys, keep unresolved candidates in task evidence and explain isolated Entities.
7. Submit related work together, not per Entity: follow the [Change Set lifecycle](../../references/change-set-lifecycle.md) by repeating `next --session <dir> --area project`.

## Done when

- Every Object in scope is modeled, excluded with a reason, or reported as blocked.
- `validate` passes and `coverage` meets the Project target; when `enforced` is false, the user may accept a gap.
- You showed grain, identity, relationships, each validation warning and its resolution, coverage against the target, and open questions.

## Ask the user when

- Grain or business identity is ambiguous, or evidence conflicts.
- Two sources may be the same business entity, or a split or merge changes meaning.
- Approving Stage and, separately, Apply.

Guided explanation is the default; requested Grill Me uses the working-context interview method and changes questions, not records.

## Next

After Apply, continue to [dimensional modeling](../atlas-dimensional-model/SKILL.md) or [mapping](../atlas-mapping/SKILL.md) when requested. [Registration](../atlas-registration/SKILL.md) is optional and never a Mapping prerequisite.
