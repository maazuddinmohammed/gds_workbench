---
name: atlas-source-analysis
description: Profile, enrich and analyze Atlas source tables for meaning, grain, keys and relationships with explicit coverage. Use for source discovery, profiling, Project enrichment or relationship analysis before modeling.
---

# Analyze source evidence

Goal: scoped findings with explicit coverage. Profiling measures data, Project enrichment records meaning, Analysis interprets relationships.

## When to use

- Understand selected source Objects: meaning, row grain, candidate keys, relationships, data quality.
- Not for: correcting physical descriptions or types ([metadata](../atlas-metadata/SKILL.md)) or explaining an existing design ([investigate](../atlas-investigate/SKILL.md)).

## What you need

- [Working context](../../references/working-method.md) and its golden rules. A supplied-schema explanation can stay read-only.
- For saved Analysis or profiling: verified Project, installed Snapshots and active applied Input Scope, which you never change.
- The saved SQL policy. Metadata-based inference is useful even when execution is unavailable.

## Steps

1. Read the selected scope and existing evidence with `select --session <dir> --area project --dataset <name> --view effective`. Classify each input as covered, missing, stale or blocked; reuse valid evidence.
2. Measure only when requested or needed: start backend [profiling](../../references/logical-build/profiling.md) with `start_profiling_run`, poll `get_profiling_run_status`, then install a fresh Project Snapshot (`create_project_snapshot`, download, `snapshot-install`) while preserving local drafts. Never write profiling SQL, import aggregates or stage profiles. Under SQL policy `never`, start no run: mark measurements unmeasured; missing counts are not zero.
3. For enrichment work or a full source-to-model request, record meaning as `object_enrichment` and `attribute_enrichment` with [Project enrichment](../../references/project/enrichment.md) before dependent analysis.
4. For each Object, state what a row represents, candidate natural keys and namespace, lifecycle, units and category meanings. Test composite identities; an ID-looking column is not proof of uniqueness. Label each finding declared, inferred or measured; use domain rules only when verified as applicable.
5. Find relationships with [relationship discovery](../../references/logical-build/find-relationships.md); names suggest candidates, not proof. `analysis-plan --session <dir> --plan-file <file>` prepares deterministic probes; running them is separate, governed SQL.
6. Write supported relationships as `analysis_result` records with `upsert-batch --session <dir> --area project --changes <JSON> --expected-digest <digest>`, keeping inferred cardinality and its basis apart from measured validation. Unsupported candidates stay in task evidence.
7. Run `validate --session <dir> --area project` and account for every requested input: addressed, excluded, unresolved or blocked. The optional findings format is `templates/source-findings.md`.
8. Submit authored records with the [Change Set lifecycle](../../references/change-set-lifecycle.md) by repeating `next --session <dir> --area project`. Read-only analysis needs no Change Set.

## Done when

- Every requested input has a coverage status and measured versus inferred findings.
- Authored records pass `validate`; unresolved candidates and blocked inputs are reported.

## Ask the user when

- Running SQL would help but the policy, environment or data protection is unresolved; unresolved protection blocks the probe.
- Evidence conflicts on a key or relationship that downstream design depends on.
- Approving Stage and, separately, Apply.

## Next

Continue to [logical modeling](../atlas-logical-model/SKILL.md), [mapping](../atlas-mapping/SKILL.md) or [subject areas](../atlas-subject-areas/SKILL.md) only when the outcome needs it.
