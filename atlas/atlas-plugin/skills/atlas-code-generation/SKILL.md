---
name: atlas-code-generation
description: Generate Atlas SQL transformation code from applied Mapping for Silver or Gold targets, with explicit file grouping and source-System assignments. Use for code generation or regeneration requests; registration DDL, Process setup and SQL Validation are separate.
---

# Generate transformation code

Goal: reviewable SQL artifacts and source-System assignments that faithfully implement applied Mapping.

## When to use

- Generate or regenerate SQL for selected Silver or Gold targets.
- Not for: transformation design ([mapping](../atlas-mapping/SKILL.md)), target DDL or Process setup ([registration](../atlas-registration/SKILL.md)) or SQL Validation ([verify](../atlas-verify/SKILL.md)).

## What you need

- [Working context](../../references/working-method.md) and its golden rules. Writing SQL never executes it.
- Active applied Mapping and modeled Entities. A target/System pair is eligible when at least one Object or Attribute transformation is saved. Conceptual output is never Code input.
- Python generation is deferred: keep existing Python artifacts and never silently substitute SQL for a Python request.

## Steps

1. Read each target's complete Mapping view with `read_mapping_context` (all five components at the applied revision). If it fails, run `next --session <dir> --area project --error <code>`; never substitute Snapshot rows. Then read current Code and assignments with `select --dataset <name> --view effective` and any local files you will change.
2. Resolve [update scope](../../references/methods/change-impact.md): show new, missing and affected artifacts and Systems; preserve locked and unchanged work.
3. Agree file grouping; show filenames, contributing Systems and a representative structure.
4. Generate each artifact with [SQL generation](../../references/code-generation/sql.md): temporary-view stages, Attribute expressions at their stage, one explicit target projection. A missing Attribute rule becomes a typed `CAST(NULL AS <type>)` placeholder with a review finding; an unproven row source becomes a typed zero-row projection. Never invent rows, joins or rules.
5. Save files under the workspace `code/` area and write matching `generated_code` and `generated_code_source_system` records per [Code records](../../references/project/generated-code.md) with `upsert-batch --session <dir> --area project --changes <JSON> --expected-digest <digest>`. `artifact_name` is a filename only; record content must equal the file text.
6. Check every active System with nonempty Mapping has exactly one active assignment, then run `validate --session <dir> --area project` and the SQL content checks. Unsupported checks stay unverified.
7. Review the complete batch in Atlas Local Workbench and follow the [Change Set lifecycle](../../references/change-set-lifecycle.md) by repeating `next --session <dir> --area project`; never per file.

## Done when

- Each target's artifacts cover every mapped System once and pass local checks; placeholders are listed.
- Authored, validated and applied states are reported separately. Apply stores code; it never deploys or runs it.

## Ask the user when

- File grouping is not already decided: "One file per target containing its Systems, or separate files per System and target? Any target-specific exceptions?" Never assume a default or one file per source table.
- A layout cannot preserve Mapping's collision and dependency rules.
- Manual edits conflict with the applied Mapping, or a lock blocks the change.
- Approving Stage and, separately, Apply.

## Next

Continue to SQL Validation or Process registration only when requested.
