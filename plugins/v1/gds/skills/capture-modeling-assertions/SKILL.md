---
name: capture-modeling-assertions
description: "Extract durable, source-located modeling facts from accessible documents or supplied text and prepare GDS modeling_assertion_document and modeling_assertion_record evidence. Use when requirements, glossaries, policies, specifications, spreadsheets, or notes should support data-model decisions; not for unsourced inference or general document summaries."
---

# Capture Modeling Assertions

Turn source material into small, retrievable modeling facts with durable provenance.
This is a governed evidence layer, not a vector search index or a substitute for the
source. Never store secrets, credentials, raw prompts, raw physical rows, temporary
download URLs, or sensitive local paths.

Follow the shared [Model authoring workflow](../../references/model-authoring-workflow.md).
Read [assertion contract](references/assertion-contract.md) before extraction. Use
[example records](references/assertion-example.json) only when exact JSON shape helps.
Ask only for missing Model/source identity, an inaccessible source, or ambiguity that
materially changes a fact.

## Extract evidence

Resolve the Model and read existing Assertion Documents/Records for the same source
before authoring. Process large sources section-by-section. Preserve a safe stable
source title/version and precise page, section, table, sheet/range, or paragraph
location; do not use a temporary URL as identity.

Extract only atomic statements that affect analysis, conceptual, logical,
dimensional, or mapping decisions. Keep conditions, exceptions, effective dates, and
scope with the fact. Separate independent claims. Paraphrase faithfully; use a short
quote only when wording itself controls interpretation.

Do not convert examples, headings, observed data patterns, or the agent's design choice
into source assertions. Mark conflict or ambiguity as `needs_review`; never silently
pick one source. Confidence measures source clarity, not agreement with a proposed
model.

## Author exact records

Call `describe_model_dataset` for both `modeling_assertion_document` and
`modeling_assertion_record`; live schemas are authoritative. Create one complete
Document record per stable source/version and one complete Record per atomic fact.
Use stable semantic keys and only applicable layer enum values. New records are
unlocked.

When replacing a canonical key, retain the complete intended dataset context required
by the selected draft workflow. Never overwrite an unseen resumed server draft. A
downstream model record may cite an Assertion only when its applicable layers include
that model layer.

## Retrieve as modeling context

For a RAG-like review, first select relevant Assertion Documents, then call
`get_modeling_assertion_records` with their IDs. Filter by applicable layer, status,
source location, and semantic subject; follow cursors until the requested evidence is
complete. Cite assertion keys in conclusions and in modeled-layer supports/sources.
State when focused retrieval may have missed relevant evidence.

Report source coverage, created/updated/needs-review counts, conflicts, and next
boundary. Do not echo an entire source or unchanged records unless asked.
