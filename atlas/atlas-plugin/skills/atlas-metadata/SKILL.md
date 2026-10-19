---
name: atlas-metadata
description: Author or correct Atlas physical Metadata for a Tenant, such as Objects, Attributes, descriptions, inferred types, ingestion mappings, copies and processes. Use for physical metadata edits and description/type enrichment, not Project-owned enrichment.
---

# Author physical metadata

Goal: requested Metadata changes as complete, checked records per owning Tenant; a focused correction needs no complete ingestion setup.

## When to use

- Correct or add physical Metadata, or fill descriptions and inferred types.
- Not for: Project-owned enrichment ([source analysis](../atlas-source-analysis/SKILL.md)) or registering derived targets and generated files ([registration](../atlas-registration/SKILL.md)).

## What you need

- [Working context](../../references/working-method.md) and its golden rules: authorized Tenant and absolute working folder. A Project only when the selection comes from it.
- A fresh Metadata Snapshot when new authoring starts; reuse that baseline for related work.
- The [Metadata table index](../../references/metadata/index.md) to choose datasets and read their installed schemas; call `describe_metadata_dataset` only for a missing or mismatched schema. Don't load table guides recursively.

## Steps

1. Read complete effective records with `select --session <dir> --area metadata --dataset <name> --view effective`, or import baseline rows with `copy --session <dir> --area metadata --dataset <name> --where <JSON> --expected-digest <digest>`. Add `--owner <tenant-id>` for another registered owner.
2. Apply [editing rules](../../references/metadata/editing.md): complete normalized natural keys, true owner versus physical placement, registered references and framework conventions. Tenant, System, Connection and lookup records are read-only; never invent lookup values or database IDs.
3. For descriptions and inferred types, follow [enrichment quality](../../references/metadata/enrichment-quality.md): change only `object_description`, `attribute_description` and `attribute_inferred_data_type`, include active unlocked Attributes of selected Objects unless narrowed, fill missing values by default and replace nonempty ones only when asked.
4. Write complete records for what the inputs confirm with `upsert-batch --session <dir> --area metadata --changes <JSON> --expected-digest <digest>`, preserving pending edits and unrelated fields; ask about genuine unknowns.
5. Run `validate --session <dir> --area metadata` and the relevant table checklists after each coherent batch; report semantic review and server-only checks separately.
6. Show the batch in Atlas Local Workbench, then follow the [Change Set lifecycle](../../references/change-set-lifecycle.md) by repeating `next --session <dir> --area metadata`. Each owner has its own Change Set, lock and approvals.

## Done when

- Requested records are complete, validated and reviewed; unresolved evidence is reported.
- Natural-key changes went through the manual-correction rule; nothing was renamed by replacement and deactivation.
- Report drafted, validated and applied states; authoring never executes DDL, ingestion, scheduling or deployment.

## Ask the user when

- Which Zones to cover is unclear: use the exact Objects or applied Project scope, otherwise ask; never default to Bronze or every Zone. The index links the intake questions.
- Replacing nonempty descriptions or types, or custom framework behavior, affects the result.
- Approving Stage and, separately, Apply.

A locked Object protects its Attributes and additions; inactive history stays intact. Project-based selections use applied Input Scope and exact owner keys without changing membership.

## Next

Source interpretation: [source analysis](../atlas-source-analysis/SKILL.md); target or Process registration: [registration](../atlas-registration/SKILL.md).
