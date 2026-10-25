---
name: atlas-code-generation
description: Generate Atlas SQL transformation code from applied Mapping for Silver or Gold targets, with explicit file grouping and source-System assignments. Use for code generation or regeneration requests; registration DDL, Process setup and SQL Validation are separate.
---

# Generate transformation code

Goal: reviewable SQL artifacts and source-System assignments implementing applied Mapping.

## When to use

- Generate or regenerate SQL for selected Silver or Gold targets.
- Fix a reported runtime error: compare the file with its applied `generated_code` record, fix every Mapping or metadata mismatch and ask them to rerun it.
- Not for: transformation design ([mapping](../atlas-mapping/SKILL.md)), target DDL or Process setup ([registration](../atlas-registration/SKILL.md)) or SQL Validation ([verify](../atlas-verify/SKILL.md)).

## What you need

- [Working context](../../references/working-method.md) and its golden rules. Writing SQL never executes it.
- Active applied Mapping and modeled Entities; a target/System pair is eligible once any Object or Attribute transformation is saved.
- Python generation is deferred: keep Python artifacts; never substitute SQL for a Python request.

## Steps

1. Read each target's complete Mapping view with `read_mapping_context` (all five components, applied revision). If it fails, run `next --session <dir> --area project --error <code>`; never substitute Snapshot rows. Then read current Code, assignments (`select --dataset <name> --view effective`) and local files you will change.
2. Resolve [update scope](../../references/methods/change-impact.md): show new, missing and affected artifacts and Systems; preserve locked and unchanged work.
3. Agree file grouping; show filenames, contributing Systems and a representative structure.
4. Generate each artifact with [SQL generation](../../references/code-generation/sql.md): temporary-view stages, staged Attribute expressions, one explicit target projection. A missing Attribute rule becomes a typed `CAST(NULL AS <type>)` placeholder and finding; an unproven row source becomes a typed zero-row projection. Never invent rows, joins or rules.
5. Save files under the workspace `code/` and write matching `generated_code` and `generated_code_source_system` records per [Code records](../../references/project/generated-code.md) with `upsert-batch --session <dir> --area project --changes <JSON> --expected-digest <digest>`. `artifact_name` is a filename only; record content must equal the file text.
6. Check every active System with nonempty Mapping has exactly one active assignment, then run `validate --session <dir> --area project` and SQL content checks; unsupported checks stay unverified.
7. Review the complete batch in Atlas Local Workbench and follow the [Change Set lifecycle](../../references/change-set-lifecycle.md) by repeating `next --session <dir> --area project`; never per file.

## Done when

- Each target's artifacts cover every mapped System once, pass local checks and list placeholders.
- Report authored, validated and applied states separately; Apply stores code and never deploys or runs it.

## Ask the user when

- File grouping is not already decided: "One file per target containing its Systems, or separate files per System and target?" Never assume a default or one file per source table.
- A layout cannot preserve Mapping's collision and dependency rules.
- Manual edits conflict with applied Mapping, or a lock blocks the change.
- Approving Stage and, separately, Apply.

## Next

SQL Validation or Process registration, only when requested.
