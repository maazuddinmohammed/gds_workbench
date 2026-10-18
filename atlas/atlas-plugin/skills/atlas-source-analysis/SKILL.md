---
name: atlas-source-analysis
description: Profile, enrich or analyze Atlas source tables to establish row meaning, candidate keys, relationships and evidence for modeling. Use for source investigation or missing modeling evidence; physical metadata corrections and project construction have separate skills.
---

# Analyze source evidence

Produce scoped findings, supported relationship candidates and explicit coverage. Profiling measures data; Project-owned enrichment records its meaning; analysis interprets relationships. Metadata-based inference is useful even when execution is unavailable.

## Resolve inputs

1. Follow [working context](../../references/working-method.md). A supplied-schema explanation can stay read-only; saved Project Analysis and backend profiling require verified Project context. For Project work, resolve selected active applied Input Scope without changing membership. Inspect exact owner-qualified Objects/Attributes, relevant Context records, existing profiles, Project-owned enrichment and Analysis through [focused reads](../../references/tools/reads.md).
2. Bind required [Metadata](../../references/snapshots/metadata.md) and [Project](../../references/snapshots/project.md) inputs. Preserve pending work; reconcile required refreshes. Classify selected inputs as covered with applicable evidence, missing, stale or blocked. Reuse explicit selections and valid evidence instead of asking to redo every phase.
3. Read [record state](../../references/record-state.md). Protected inputs may be readable while their records cannot be changed. Resolve missing physical identity, access, masking or batch facts before affected execution.

## Measure only when needed and authorized

Use [backend profiling](../../references/logical-build/profiling.md) for requested or necessary measurements: resolve Object IDs/batches, start the governed run, inspect status/cancellation and refresh Project evidence after verified completion. Preserve/reconcile any local draft before installing a new Snapshot. Never generate fallback profiling SQL, import aggregates or stage Profile records.

SQL Never means no execution: reuse available evidence and mark missing measurements as unmeasured, then continue independent interpretation. Missing counts are not zero. Other permitted probes follow [query scope](../../references/query-scope.md), including aggregate evidence, protection and provenance. The SQL tool does not independently enforce every metadata masking rule; unresolved protection blocks a probe.

## Enrich before dependent analysis

For enrichment work or a full source-to-data-model request, follow [Project enrichment](../../references/project/enrichment.md). Use applicable profiles and source context to author Project-owned Object/Attribute findings locally. Prefer profiling → enrichment → analysis; reuse valid existing results. Read the effective local view so pending findings feed analysis immediately. Keep them in the same related draft until submission is needed.

## Interpret and capture

1. Establish what each selected row represents, candidate natural-key tuples and their namespace, lifecycle, units and important category meanings. Inspect [approved domain knowledge](../../references/domains/index.md) only when relevant. Distinguish declared, inferred and measured facts; test composite identities rather than assuming an ID-looking column is unique.
2. Follow [relationship discovery](../../references/logical-build/find-relationships.md). Examine identity/role and category/reference candidates, their endpoints, join meaning and cardinality. Names suggest candidates, not proof. Use `analysis-plan` for supported deterministic probe preparation; execution remains separately governed.
3. For persisted relationships, use [Analysis records](../../references/project/analysis-result.md) and [Project authoring](../../references/project/change-sets.md). Populate inferred cardinality and its basis separately from measured validation. Keep unsupported candidates in task evidence, not invented records or Context records.
4. Reuse effective Project enrichment and profiling findings; keep physical Metadata separate. Explicit physical-description correction uses [metadata](../atlas-metadata/SKILL.md).
5. Account for every requested input: addressed, explicitly excluded, unresolved or blocked. Preserve concise evidence bindings and uncertainty using the optional [findings format](../../templates/source-findings.md); omit raw samples and tool dumps.

## Finish or continue

Run [local validation](../../references/local-validation.md) for authored records and review evidence quality. Persisted changes follow the shared [Change Set lifecycle](../../references/change-set-lifecycle.md); read-only analysis needs no Change Set. Report measured versus inferred findings and unresolved coverage. Continue to [conceptual](../atlas-conceptual-model/SKILL.md), [logical](../atlas-logical-model/SKILL.md) or [mapping](../atlas-mapping/SKILL.md) only when the requested outcome needs it.
