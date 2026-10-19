---
name: atlas-logical-model
description: Build or refine Atlas logical (Silver) Entities, Attributes, relationships and Submodels with explicit grain, identity and normalization. Use for logical modeling or normalization requests; supports Guided explanation and requested Grill Me discussion in the same workflow.
---

# Build a logical model

Goal: a normalized Silver design with explicit grain, complete identity and traceable sources.

## When to use

- Design or refine Silver Entities, Attributes, keys, relationships or Submodels from applied Project Input Scope.
- Not for: evidence gaps ([source analysis](../atlas-source-analysis/SKILL.md)), facts and dimensions ([dimensional](../atlas-dimensional-model/SKILL.md)) or applied designs with downstream work ([project change](../atlas-project-change/SKILL.md)).

## What you need

- [Working context](../../references/working-method.md) and its golden rules.
- Installed Metadata and Project Snapshots and active applied Input Scope; [Logical context](../../references/logical-build/context.md) lists what to read.
- Profiles, Project enrichment and Analysis from the effective local view; pending results count without Apply. Never Conceptual records.

## Steps

1. Read selected sources and existing design with `select --session <dir> --area project --dataset <name> --view effective`, following `next_cursor` until it is null.
2. For each business area, state what one row means and its complete natural key, including source namespace when needed. Normalize by real dependencies and lifecycle with [logical design](../../references/logical-build/logical-design.md); matching names never prove a relationship. Under SQL policy `never`, model from metadata and label findings unmeasured.
3. Write complete Entity, Attribute, Relationship and Submodel records with `upsert-batch --session <dir> --area project --changes <JSON> --expected-digest <digest>` per [Logical records](../../references/project/logical.md). Use configured schemas and naming, give business fields distinct names such as `SourceCreatedDate`, and pair each physical Attribute source with its Object source on the Entity.
4. Add framework columns: run `policy-apply --session <dir> --layer logical --expected-digest <digest> --dry-run true`, show the result, then run it without `--dry-run`.
5. Run `validate --session <dir> --area project`, `coverage --session <dir> --layer logical` and the logical design quality checks. Repair and rerun after each coherent batch.
6. Review the relationship graph: persist supported foreign keys, keep unresolved candidates in task evidence and explain isolated Entities.
7. Submit related work together, not per Entity: follow the [Change Set lifecycle](../../references/change-set-lifecycle.md) by repeating `next --session <dir> --area project`.

## Done when

- Every selected input is modeled, excluded with a reason, or reported as blocked.
- `validate` passes and `coverage` meets the Project target; when `enforced` is false, the user may accept a gap.
- You showed grain, identity, relationships, validation findings with how each warning was resolved, coverage against the target, and open questions.

## Ask the user when

- Grain or business identity is ambiguous, or evidence conflicts.
- Two sources may be the same business entity, or a split or merge changes meaning.
- Approving Stage and, separately, Apply.

Guided explanation is the default. For requested Grill Me, use the interview method linked from working context; it changes questions, not records.

## Next

After Apply, continue to [dimensional modeling](../atlas-dimensional-model/SKILL.md) or [mapping](../atlas-mapping/SKILL.md) when requested. [Registration](../atlas-registration/SKILL.md) is optional and never a Mapping prerequisite.
