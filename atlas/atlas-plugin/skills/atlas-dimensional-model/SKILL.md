---
name: atlas-dimensional-model
description: Build or refine Atlas dimensional (Gold) facts, dimensions, bridges, measures, conformance and history from applied logical Entities, one Subject Area at a time. Use for star-schema, fact/dimension or SCD requests; supports Guided explanation and requested Grill Me discussion.
---

# Build a dimensional model

Goal: one Gold model with defensible grain, measures, conformance and history from applied Logical Entities.

## When to use

- Design or refine facts, dimensions, bridges, measures, roles or history for analytical questions.
- Not for: Silver normalization ([logical](../atlas-logical-model/SKILL.md)) or applied designs with downstream work ([project change](../atlas-project-change/SKILL.md)).

## What you need

- [Working context](../../references/working-method.md) and its golden rules.
- Active applied Logical Entities and Attributes; [Dimensional context](../../references/dimensional-build/context.md) lists what to read, including history rules.
- The business process and questions to answer; a department name or report layout is not a fact grain.

## Steps

1. With [dimensional design](../../references/dimensional-build/design.md), **Build** one Subject Area at a time for named areas; otherwise **Optimize** existing facts and dimensions.
2. Read applied Logical sources with `select --session <dir> --area project --dataset <name> --view snapshot` and Dimensional records with `--view effective` until `next_cursor` is null; for a Build, the area's Logical Entities, what was built from them and shared dimensions.
3. State what one row means for each fact, dimension or bridge; a dimension-only request needs member or version grain, not an invented fact.
4. Decide dimensions, roles and conformance, reusing shared dimensions, then facts and measures with additivity, units and population in their definitions. Resolve history from requirements and the Project SCD setting; never guess effective time.
5. Write only new and changed records with `upsert-batch --session <dir> --area project --changes <JSON> --expected-digest <digest>` per [Dimensional records](../../references/project/dimensional.md): configured schemas and naming, active fact type codes, Relationships child -> parent with roles only for role-playing dimensions, retirement through `*_is_active: false`.
6. Add framework columns: `policy-apply --session <dir> --layer dimensional --expected-digest <digest> --dry-run true`, show the result, then run it without `--dry-run`.
7. Run `validate --session <dir> --area project`, `coverage --session <dir> --layer dimensional --subject-area <area>` (no area when optimizing) and the quality checks; check coherence across processes.
8. Submit related work together: follow the [Change Set lifecycle](../../references/change-set-lifecycle.md) by repeating `next --session <dir> --area project`.

## Done when

- Each requested structure has stated grain, identity, measures, conformance and history.
- `validate` passes and `coverage` meets the Project target; when `enforced` is false, the user may accept a gap.
- Unchanged, protected and unrelated stars are preserved; scope never means rebuilding everything.

## Ask the user when

- The business process, questions or grain are unclear.
- History or missing-version behavior is not evidenced.
- A change to a shared dimension affects other stars.
- Approving Stage and, separately, Apply.

Report unresolved grain, identity or history; never guess it or disguise it as Context. Guided explanation is the default; Grill Me changes questions, not records.

## Next

After Apply, refresh the Project Snapshot before requested [mapping](../atlas-mapping/SKILL.md) or optional [registration](../atlas-registration/SKILL.md).
