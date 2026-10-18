---
name: atlas-dimensional-model
description: Build or refine Atlas dimensional (Gold) facts, dimensions, bridges, measures, conformance and history from applied logical Entities. Use for star-schema, fact/dimension or SCD requests; supports Guided explanation and requested Grill Me discussion.
---

# Build a dimensional model

Goal: a Gold design with defensible grain, measures, conformance and history, traced to applied Logical Entities.

## When to use

- Design or refine facts, dimensions, bridges, measures, roles or history for analytical questions.
- Not for: Silver normalization ([logical](../atlas-logical-model/SKILL.md)) or applied designs with downstream work ([project change](../atlas-project-change/SKILL.md)).

## What you need

- [Working context](../../references/working-method.md) and its golden rules.
- Active applied Logical Entities and Attributes; Conceptual output is never an input. [Dimensional context](../../references/dimensional-build/context.md) lists what to read, including history rules.
- The business process and questions the design must answer. A department name or report layout is not a fact grain.

## Steps

1. Read applied Logical sources with `select --session <dir> --area project --dataset <name> --view snapshot` and existing Dimensional records with `--view effective`, following `next_cursor` until it is null.
2. State what one row means for each fact, dimension or bridge. A dimension-only request needs member or version grain, not an invented fact.
3. Decide dimensions, roles and conformance, then facts and measures, with [dimensional design](../../references/dimensional-build/design.md). Put additivity, valid aggregation, units and population in Attribute definitions; a valid star can still double-count.
4. Resolve history from requirements and the Project SCD setting; never guess effective time or missing-version behavior.
5. Write complete records with `upsert-batch --session <dir> --area project --changes <JSON> --expected-digest <digest>` per [Dimensional records](../../references/project/dimensional.md), using configured `dimensional_schemas` and naming, with business field names distinct from framework audit names. Never invent SCD, bus-matrix or Logical-source fields.
6. Add framework columns: `policy-apply --session <dir> --layer dimensional --expected-digest <digest> --dry-run true`, show the result, then run it without `--dry-run`. Type 2 Dimensions get the configured history fields.
7. Run `validate --session <dir> --area project`, `coverage --session <dir> --layer dimensional` and the dimensional quality checks, then check coherence across processes.
8. Submit related work together: follow the [Change Set lifecycle](../../references/change-set-lifecycle.md) by repeating `next --session <dir> --area project`.

## Done when

- Each requested structure has stated grain, identity, measures, conformance and history.
- `validate` passes and `coverage` meets the Project target; when `enforced` is false, the user may accept a gap.
- Unchanged, protected and unrelated stars are preserved; scope does not mean rebuilding every star.

## Ask the user when

- The business process, questions or grain are unclear.
- History or missing-version behavior is not evidenced.
- A change to a shared dimension affects other stars.
- Approving Stage and, separately, Apply.

Unresolved grain, identity or history is reported, never filled with a guess or disguised as a Context record. Guided explanation is the default; Grill Me changes questions, not records.

## Next

After Apply, refresh the Project Snapshot before requested [mapping](../atlas-mapping/SKILL.md) or optional [registration](../atlas-registration/SKILL.md).
