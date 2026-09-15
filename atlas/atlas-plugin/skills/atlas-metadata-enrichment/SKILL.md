---
name: atlas-metadata-enrichment
description: Improve existing Object descriptions, Attribute descriptions and inferred data types using business context and evidence. Use for a Tenant/System selection or Objects selected through Model Input Scope. Produces Metadata changes for downstream modeling, mapping, code and analysis.
---

# Metadata enrichment



Improve the meaning and inferred types of selected metadata. A Model may supply selection and evidence; enrichment itself writes Metadata records only.

| Record | Fields this workflow may change |
|---|---|
| Object | object_description |
| Attribute | attribute_description, attribute_inferred_data_type |

Compare against the incoming effective records so earlier pending authoring edits are preserved. Keep physical types, keys, flags, custom expressions and all other fields unchanged. No Model changes or source-table ALTER/COMMENT operations are implied.

## Resolve inputs

1. Follow the [working method](../../references/working-method.md). Resolve Tenant, absolute working directory and SQL policy; reuse supplied choices. Resolve an environment only when permitted evidence queries need it.
2. Resolve the requested Objects and Attributes using complete physical keys:
   - Tenant/System selection: establish the Zone and exact scope before writing. Distinguish an originating System from the physical GDS System holding Bronze Objects; use verified Object Mapping provenance where applicable.
   - Model selection: read active applied Model Input Scope, then resolve its exact Object keys in Metadata. Use the returned Zones; a Model is not required for the Tenant/System route. Scope visibility alone does not authorize metadata writes.
3. Prepare a fresh [Metadata Snapshot](../../references/snapshots/metadata.md) at entry for fresh work; preserve/reconcile an existing baseline and draft. Also use a [Model Snapshot](../../references/snapshots/model.md) when Model Input Scope is the selector. Accumulate related local work against these bound inputs.
4. Read the selected Object/Attribute schemas and actual records. Follow [record state](../../references/record-state.md), including Object protection of its Attributes; record what cannot be changed. Start/reuse Workbench through its verified available launcher.

## Enrich each Object and its selected Attributes

Use the shared [quality procedure and examples](../../references/metadata/enrichment-quality.md) for these steps. Reuse common Tenant/System/Connection context across Objects; do not reread it for every column.

1. **Collect context.** Read Tenant and System descriptions, System Type, actual Connection description/type, existing Object/Attribute descriptions, column names/types and relevant supplied documentation or glossary definitions.
2. **Understand the Object.** Establish its business subject, purpose and what one row represents. Examine keys, dates, status fields, measures, relationships and relevant expressions. Treat names as clues; retain unresolved meanings explicitly.
3. **Resolve material gaps.** Name the uncertainty first, then use existing evidence or permitted targeted SQL/profile checks. Respect masking and actual query coordinates. SQL Never uses existing metadata/docs; missing evidence must not become a fabricated fact.
4. **Draft the Object description.** Explain its subject and row meaning, adding supported lifecycle or usage distinctions. Omit generic Zone/storage wording and lists that merely repeat the schema. Unknown grain is not an invitation to guess it.
5. **Draft Attribute descriptions.** Describe each field within that Object's meaning: its role and, when supported, units, code meanings, time semantics or relationship. Distinguish similarly named concepts such as billed customer and recipient.
6. **Infer Attribute types.** Follow the shared [type procedure](../../references/metadata/enrichment-quality.md#infer-types-with-evidence): use meaning, applicable declarations, expressions and optional data evidence. Keep physical attribute_data_type unchanged.
7. **Review and repair.** Compare every claim with its evidence, then check Object/Attribute consistency and meaningful information beyond the names. Check candidate types for ambiguity and information loss. Revise unsupported wording; do not require another model or a fixed number of review passes.
8. **Save useful results locally.** Upsert complete records with only the three allowed fields changed. Store concise supporting findings, unresolved questions and type limitations in existing task evidence, keyed to the relevant records. Do not create invented metadata fields or save physical samples/raw tool output.
9. **Validate the batch and hand off.** Follow [local validation](../../references/local-validation.md) with the [enrichment checks](../../references/metadata/enrichment-quality.md#enrichment-checks). Report changed, unchanged and unresolved/protected records accurately. Follow the shared [Change Set lifecycle](../../references/change-set-lifecycle.md) for Workbench review, extension staging, server validation and separate Apply approval. Recheck the scope Model revision when it determined selection.

## Scope and replacement defaults

- Use the request or Model Input Scope to determine Zones. Otherwise ask which Zone to use; never silently choose Bronze or every Zone. Any registered eligible Source/Bronze/Silver/Gold Object can be selected through the direct route.
- Include all active, unlocked Attributes of the selected Objects unless the request narrows them. Parent Object protection still applies; a default selection never bypasses a lock.
- Fill missing Object/Attribute descriptions and inferred types by default. Nonempty existing values remain unchanged unless the request explicitly authorizes improving/replacing them; better evidence alone does not authorize replacement.
- For Model-derived cross-owner selection, use [separate owner roots in the same workspace](../../references/workspace-contract.md#model-derived-metadata-owners). Review and submit each owner's Metadata Change Set under its own identity; retain the original Model scope/version as input evidence.

## Gotchas

- Zone determines which record and evidence to use; it is not the subject of the description. Describe an actual ingestion timestamp operationally when that is its meaning, without generic Bronze boilerplate.
- Attribute Mappings may be empty. Interpret actual Source/Bronze custom expressions and their inputs; do not require a mapping row or inherit Source types blindly.
- Bronze physical STRING can still have a useful inferred numeric/date type. A string of digits can also be an identifier that must remain textual.
- Model input access can span Source Tenants. Partition Metadata changes by Object.source_tenant_code ownership; physical GDS placement is not ownership.
- Existing generated descriptions are context, not independent proof of grain, relationships or types.

For a descriptions-only request, include missing Object and Attribute descriptions within the selected Object scope unless the request narrows one level. Preserve inferred data types in that case; they are not implicitly part of every enrichment request.
