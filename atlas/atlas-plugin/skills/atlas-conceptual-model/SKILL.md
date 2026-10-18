---
name: atlas-conceptual-model
description: Define or refine an Atlas Conceptual model of business concepts and relationships as a standalone deliverable. Use for business-concept, subject-area or glossary-style modeling requests; never as input to logical or later work.
---

# Model business concepts

Goal: a standalone Conceptual model with clear business meanings and supported relationships.

## When to use

- Define business concepts, what one instance represents, lifecycles and business relationships.
- Not a step toward Logical, Dimensional, Mapping, Code or SQL Validation work: those never read Conceptual output. A later Logical request starts from its own evidence in [logical modeling](../atlas-logical-model/SKILL.md).

## What you need

- [Working context](../../references/working-method.md) and its golden rules. A discussion-only answer needs no workspace or records.
- For saved concepts: the Project, applied Input Scope, installed Snapshots and effective existing Conceptual records.
- Source meaning from profiles, Project enrichment, Analysis and attributable Context records; pending results count. Profiling is not required ceremony; material gaps go to [source analysis](../atlas-source-analysis/SKILL.md).

## Steps

1. Read existing concepts and evidence with `select --session <dir> --area project --dataset <name> --view effective`, following `next_cursor` until it is null.
2. With [business concepts](../../references/conceptual-build/business-concepts.md), name each concept, what one instance represents, its lifecycle and distinctions. Consolidate equivalent concepts; keep genuinely different roles separate.
3. Attach real physical or Context supports. A requirement does not prove a physical source exists; explain justified standalone concepts instead of fabricating supports.
4. Define relationships and their basis. Cardinality may stay unknown; never infer it from column names or copy physical foreign keys without their business meaning.
5. Write complete `conceptual_object` and `conceptual_relationship` records with `upsert-batch --session <dir> --area project --changes <JSON> --expected-digest <digest>` per the [Conceptual records](../../references/project/conceptual.md) contract.
6. Run `validate --session <dir> --area project` and the conceptual quality review: real endpoints, eligible supports, coherent definitions, coverage of selected inputs.
7. To save, follow the [Change Set lifecycle](../../references/change-set-lifecycle.md) by repeating `next --session <dir> --area project`. Finishing the model does not require Apply.

## Done when

- Requested concepts and relationships are explained, recorded where authoring was requested, and checked against evidence.
- Exclusions, uncertainty and affected Conceptual records are reported.
- No downstream work was created from these changes.

## Ask the user when

- A concept's meaning, boundary or lifecycle is ambiguous, or two concepts might be the same.
- Evidence conflicts about a relationship's meaning.
- Approving Stage and, separately, Apply.

Use the interview method from working context for consequential ambiguity, reusing confirmed answers, and record consequential decisions in task evidence; the optional [decision format](../../templates/modeling-decision.md) adds no new ledger. Use domain rules only when verified as applicable. Unknown facts stay unknown; never create a Context record only to pass validation.

## Next

Stop here unless the user asks for more. Explaining an existing design uses [investigate](../atlas-investigate/SKILL.md).
