---
name: atlas-verify
description: Verify an Atlas artifact or project, or author persisted SQL Validation groups and checks, choosing only the checks the requested result needs. Use for "validate/check/review this model, mapping or code" requests and SQL Validation authoring.
---

# Verify the requested result

Goal: the requested kind of verification, reporting exactly which checks ran, what they found and what remains unverified.

## When to use

| Requested result | Check |
|---|---|
| Record validity | Shared local validators; server validation stays separately authoritative. |
| Modeling quality | The matching quality guide for evidence, grain, identity, relationships and coverage. |
| Mapping or Code correctness | Applied prerequisites, the complete Mapping view and the actual Code being tested. |
| Persisted SQL Validation groups and checks | Applied complete Mapping, plus actual Code when testing its implementation, with [SQL-check authoring](../../references/methods/sql-validation.md). |
| Measured data result | Explicit execution authorization, SQL policy and a governed route under [query scope](../../references/query-scope.md). |

"Validate this logical model" does not need Mapping or SQL check authoring. Review Conceptual only as its own deliverable; never use it to verify other layers.

## What you need

- [Working context](../../references/working-method.md) and its golden rules. Explaining a check needs no workspace.
- The selected scope bound to its Snapshot, revision and pending content. Reuse earlier check results only while their bindings still match.

## Steps

1. Read the selected records with `select --session <dir> --area <area> --dataset <name> --view effective`, never from Snapshot files.
2. If no task is active, run `task-add --session <dir> --outcome <outcome>` first (local bookkeeping, allowed even when nothing may change). Run `validate --session <dir> --area <area>` and read the actual findings. `review_required`, `not_run` and `server_only` are not passes.
3. Review business correctness against requirements and evidence with the one quality guide that fits, listed in [local validation](../../references/local-validation.md).
4. Keep completeness boundaries: partial Mapping can support explicitly incomplete draft Code with typed placeholders, but never SQL Validation authoring or claims of executable correctness.
5. Repair defects through the owning skill only when repair is requested or part of the current task; never invent an expectation to make a check pass.
6. Report scope and bindings, checks run, evidence, unresolved findings and the next action, using the optional format in `templates/validation-summary.md`. Authored SQL Validation records follow the [Change Set lifecycle](../../references/change-set-lifecycle.md) via `next --session <dir> --area project`.

## Done when

- The requested verification ran and its result separates authored, structurally checked, semantically reviewed, executed and applied states.
- Under SQL policy `never`, execution is reported as not run.

## Ask the user when

- Business intent behind an expected result is missing.
- Measuring data needs authorization, a policy change or an unresolved protection decision.
- Approving Stage and, separately, Apply for authored checks.

Saving checks does not run the external comparator, schedule a pipeline or execute generated transformations.

## Next

Route defects by cause to [project change](../atlas-project-change/SKILL.md), [mapping](../atlas-mapping/SKILL.md), [code generation](../atlas-code-generation/SKILL.md) or [metadata](../atlas-metadata/SKILL.md).
