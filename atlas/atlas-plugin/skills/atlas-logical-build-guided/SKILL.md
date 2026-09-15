---
name: atlas-logical-build-guided
description: Build or refine a logical model through the guided Profiling, Analysis, Conceptual and Logical phases. Use when Atlas selects Guided logical build or the user requests that sequence; collaborative Grill Me modeling has its own skill.
---

# Logical build — Guided

This skill owns the guided sequence. Load shared topic methods as each phase needs them; interview behavior belongs to the separate Grill Me skill.

## Establish context

Follow [Logical build context](../../references/logical-build/context.md). Reuse the workflow selected through Atlas or a direct request. This skill follows the guided sequence; it does not run the Grill Me interview.

## Guided workflow

Proceed in order: **Profiling → Analysis → Conceptual → Logical**. Topic references supply the methods.

At each phase, inspect effective records (Snapshot plus pending work), show applicable results and coverage, and reuse answers already supplied.

| Phase | No applicable results | Applicable results exist |
|---|---|---|
| Profiling | Ask "Start profiling for [selected Objects]?" | Ask "Reuse existing profiles, redo all selected Objects, or redo specific Objects?" |
| Analysis | Start automatically using [finding relationships](../../references/logical-build/find-relationships.md). | Ask "Reuse the existing analysis or redo it?" Clarify affected scope when needed. |
| Conceptual | Start automatically using [business concepts](../../references/logical-build/business-concepts.md). | Ask "Keep the existing conceptual model or revise it?" Clarify affected scope when needed. |
| Logical | Start automatically using [logical design](../../references/logical-build/logical-design.md). | Ask "Keep the existing logical model or revise it?" Clarify affected scope when needed. |

With SQL `never`, reuse applicable existing profiles or record Profiling as **not executed under policy**, then continue metadata-based Analysis/Conceptual/Logical work. Do not ask to execute SQL that the policy already forbids. Prepare SQL only when requested; missing measurements remain explicit and do not require fabricated counts or Assertions.

For profiling, load the [profiling reference](../../references/logical-build/profiling.md). Resolve inputs and batch choices, invoke the available generator using its verified contract, execute permitted query groups, and save validated results as the reference directs. If generation fails, use its [agent-written SQL fallback](../../references/logical-build/profiling.md#agent-written-sql-fallback). Keep SQL templates, files, tool arguments and result handling in that reference.

For analysis, load [finding relationships](../../references/logical-build/find-relationships.md): inspect scoped Objects, infer clear identity/role and category/reference relationships from metadata, and use SQL only when useful under the saved policy. Keep inferred and measured conclusions explicit. Shared [Model authoring](../../references/model/change-sets.md) owns the unchanged payload structure.

For conceptual modeling, load [business concepts](../../references/logical-build/business-concepts.md): identify business meanings and grain, reuse/consolidate equivalent concepts, attach real supports, then define relationships and cardinality. Use the exact [Conceptual record contract](../../references/model/conceptual.md) for the two local datasets and nested supports.

For logical modeling, load [logical design](../../references/logical-build/logical-design.md): establish Entity grain and identity, apply [normalization decisions](../../references/logical-build/normalization.md), design Attributes/keys/relationships, preserve source lineage and organize useful Submodels. Use [Logical records](../../references/model/logical.md) for exact payloads and [Assertions](../../references/model/assertions.md) only when applicable. Justified generated/standalone structures need no fabricated physical source.

After each authored phase's local batch, run the shared [local validation sequence](../../references/local-validation.md), repair failures and rerun affected checks before treating that work as complete. Validate actual endpoints and eligible scope as well as schema. This is local validation; SQL relationship testing is optional under policy.

## Gotchas

- Partial coverage needs both branches: reuse/redo covered inputs and follow missing-result behavior for uncovered inputs. Preserve the selected scope.
- Redoing upstream work requires reassessing affected downstream findings. Preserve unrelated results; do not restart everything automatically.
- Automatic phase entry does not override SQL policy, prerequisites or Apply approval. Declined/unavailable profiling remains explicit; generated SQL is not measured evidence.
- A SQL fallback changes how queries are prepared. Missing batch choices or unresolved scope/protection still need resolution under the profiling reference.
- Conceptual cardinality can be unknown; Logical cardinality cannot. Keep unresolved Logical candidates in task evidence until their multiplicity is supported.
- An Attribute's physical source needs a matching Object source on its Entity. Empty sources are valid for intentional generation; they must not hide available lineage.

Accumulate related local work across phases where contracts permit. Follow the shared [Change Set lifecycle](../../references/change-set-lifecycle.md) when ready or when an applied dependency requires it; phase boundaries alone do not trigger Stage or Apply.

## Topic references

Organize supporting guidance by reusable subject:

- **[Profiling](../../references/logical-build/profiling.md):** preparation, generator/fallback, execution, measurements and evidence reuse.
- **[Finding relationships](../../references/logical-build/find-relationships.md):** candidate discovery, supporting checks, cardinality, contradictions and unresolved relationships.
- **[Business concepts](../../references/logical-build/business-concepts.md):** meaning, grain, consolidation, supports, business relationships and coverage.
- **[Logical design](../../references/logical-build/logical-design.md):** Entity/Attribute design, relationships, sources, standalone structures, Submodels and business-quality review.
- **[Normalization](../../references/logical-build/normalization.md):** twelve decision factors, dependencies and concrete retain/split/association examples.
- **[Naming](../../references/model/naming.md):** shared PascalCase, uppercase ID and dimensional Key conventions.
- **[Keys and audit columns](../../references/model/keys-and-audit.md):** surrogate/natural/foreign keys, confirmed columns, ordering and population ownership.

Load only relevant topics. Both Logical Build skills use the same logical-build references; names, keys/audit and record contracts also serve other workflows. Interview changes belong in Grill Me, not these domain methods. Check legacy consumer behavior against confirmed Atlas rules.

## Continue when requested

Continue with [target registration](../atlas-target-registration/SKILL.md), [Entity Binding](../atlas-entity-binding/SKILL.md) and [Mapping](../atlas-mapping/SKILL.md) when requested. Those workflows and Code Generation must preserve the design and identify actual support for generated inputs.
