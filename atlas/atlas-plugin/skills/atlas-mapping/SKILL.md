---
name: atlas-mapping
description: Author Atlas source-to-target Mapping for applied logical (Silver) or dimensional (Gold) Entities, one target Entity and source System per branch, complete enough to generate and validate code. Use for mapping, lineage-rule or transformation-design requests.
---

# Map sources to an applied target

Goal: per branch (one schema-qualified target Entity and source System), a transformation complete enough to code and validate.

## When to use

- Map sources to applied Logical (Silver) or Dimensional (Gold) Entities, or update existing Mapping.
- Not for: target design ([logical](../atlas-logical-model/SKILL.md), [dimensional](../atlas-dimensional-model/SKILL.md)) or SQL ([code generation](../atlas-code-generation/SKILL.md)).

## What you need

- [Working context](../../references/working-method.md) and its golden rules. Conceptual output is never a Mapping input.
- Active applied target Entities and Attributes in current Project and Metadata Snapshots; upstream design changes finish first.
- The [Mapping record contract](../../references/project/mapping.md) and the [transformation documents guide](../../references/project/mapping-documents.md), including its exact existing templates.

## Steps

1. Read applied targets with `select --session <dir> --area project --dataset <name> --view snapshot` and existing Mapping with `--view effective`.
2. Resolve [update scope](../../references/methods/change-impact.md): show affected target and System branches with reasons. Regenerate selected branches and keep compatible unchanged rules; a new Project revision alone is no reason to rebuild.
3. Use the selected or configured template; verify installed template codes and show one representative result before writing many.
4. For each branch, decide which inputs really supply it, including needed lookups; never copy every supporting Object or infer origin from the GDS System. Keep the agreed target grain and complete merge key; separate generated own keys from mapped foreign keys.
5. Write ordered Object steps (reads, joins with exact predicates, filter placement, justified deduplication, output grain) and an Attribute rule for every active modeled column per System, including keys, audits, constants and generated fields. Reconcile types, formats, precision and nulls.
6. Set `object_dependency_order` from real prerequisites. Contribution order, Attribute ordinal and Object order are distinct; Process Groups own the runtime schedule.
7. Write `mapping_object` and `mapping_attribute` records with `upsert-batch --session <dir> --area project --changes <JSON> --expected-digest <digest>`. Run `validate --session <dir> --area project` and the document quality checks even when nothing changed, after `task-add` if no task is active.
8. Show sources, steps, rules and dependency order in Atlas Local Workbench, then follow the [Change Set lifecycle](../../references/change-set-lifecycle.md) by repeating `next --session <dir> --area project`.

## Done when

- Every selected branch covers all active modeled Attributes with real lineage and a rule, or is explicitly blocked.
- `validate` and the document quality checks pass, and one Mapping view supplies placement, aliases, types, order, branches, dependencies and population rules.

## Ask the user when

- Cross-System identity, competing-row choice, lookup or conversion failures, or runtime consumer behavior is unresolved.
- A template choice is genuinely ambiguous.
- Approving Stage and, separately, Apply.

Direct mappings need no interview; SQL is optional evidence.

## Next

After Apply, refresh the Project Snapshot and confirm the applied Mapping. Stop before [code generation](../atlas-code-generation/SKILL.md) unless it was requested.
