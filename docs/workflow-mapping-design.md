# Mapping — inputs, prompts and validation

**Current contract — 28 September 2026.** Mapping belongs to schema-qualified
Logical or Dimensional Entities and their modeled Attributes. Physical target
registration and Model Bindings are not prerequisites. See
[ADR 012](adr/012-entity-owned-mapping-and-code.md) and
[current domain contracts](../CONTEXT.md).

Stage: `mapping_authoring`. Modes: One-shot and Tool-assisted. Variables and readers
are explicit workflow-local author choices; no hidden context is appended.

## Partial output and Apply

Each frozen Entity/System pair is authored independently. Any valid Object
transformation **or** Attribute transformation keeps the pair. Complete Attribute
coverage is not required to save Mapping. Return supported transformations and
leave missing ones blank; never invent joins, defaults or rules to fill coverage.
Object-only and Attribute-only mappings are valid authoring progress.

Regeneration clears omitted or null selected, unlocked documents, including saved
values. Locked and unselected mappings stay unchanged. Existing Object logic is
also preserved when any Attribute is locked or unselected, because changing joins
or grain could change that protected Attribute's behavior. Empty JSON documents
normalize to missing output. A new pair with no Object or Attribute output creates
no empty Mapping records. An existing pair cleared of all output keeps its record
history and detail URLs but is hidden from the Entity Mapping ledger.

The detail spreadsheet lists every active modeled Attribute. Missing Attribute
records are derived by the backend and have null Mapping IDs; they cannot be
selected for record review. Their transformations are blank. Persisted records
whose transformations were cleared keep their real IDs and review actions. For
example, ten active Attributes with five authored mappings display ten rows and
five blank transformations. Attribute-only output leaves the Object section blank.

Valid partial and complete pairs form one draft, validated against the full future
Model graph before explicit review and Apply. Recoverable provider, evidence-access
or candidate-integrity failures are isolated to their pair; failed pairs remain
unchanged. A true failure with no successful changes fails the Run. Authorization,
Tenant Lock, worker claim, revision and finalization failures remain fatal.

Typed outcomes distinguish completed, partial, preserved, no-source, empty and
failed pairs. The web app shows **Partial results** for completed Runs containing
incomplete or failed pairs, including after Apply. Incomplete counts are separate
from the failed-pair issue list. Frozen pair ordinals identify targets, not progress.
No applicable source is distinct from no supported transformation output; missing
business evidence must not be relabeled as no source.

Code and Validation retain their complete Mapping eligibility and coverage gates.
Saving partial Mapping does not make it ready for downstream generation. Apply
stores authored state; it does not execute SQL or load data.

The optional Model default Mapping System covers Entities supported only by
active applicable Assertions without physical or Logical source provenance.
`source_system.is_default=true` identifies this assignment; source candidates are
empty. Every returned transformation needs explicit supporting rules. Unsupported
transformations remain blank. The default cannot replace known source provenance
or unavailable upstream Mapping; see ADR 012 for ownership and eligibility.

## Default transformation templates

[The governed seed](../database/seed/07_global_mapping_output_templates.template.sql)
defines `mapping_object_default` and `mapping_attribute_default`.

- Object documents contain physical `source_objects` where appropriate, optional
  `source_logical_entities` and `source_dimensional_entities`, and ordered `steps`.
  Logical physical sources carry Tenant/System/Connection/schema/Object keys and
  aliases. Modeled sources carry their schema-qualified Entity keys and aliases.
  Steps describe joins and exact predicates, filters, grain changes and evidenced
  processing; they do not repeat Attribute expressions or entire SQL pipelines.
- Attribute documents contain optional physical `source_attributes`,
  `source_logical_attributes` or `source_dimensional_attributes`, plus a
  `transformation` expression or precise implementable rule. Preserve actual source
  keys, types, casts and null behavior. Physical sources belong to Logical Mapping;
  Dimensional inputs use Logical keys, with eligible Dimensional peer lookups.

[Template definitions and examples](workflow-prompts/mapping.output-templates.proposal.json)
provide the field shapes. Templates guide flexible document content; they do not
replace the fixed outer candidate contract or prove arbitrary SQL semantics.
Missing documents remain blank rather than storing a fabricated expression.

New Logical and Dimensional Runs resolve omitted/null template choices to the
defaults. Either template can be overridden independently. Resolved IDs and schema
digests are frozen with the Run. Correlation replay retains existing choices;
unavailable defaults fail new creation explicitly. Existing documents and frozen
Runs are not rewritten by template installation.

## Inputs and readers

[Context schemas and examples](workflow-prompts/mapping.context.json) define the
exact variables; [reader contracts](workflow-prompts/mapping.tools.json) define
selectors and paging. The main inputs are:

- `mapping_route`, `operation` and `readiness`: frozen layer and per-record actions;
  only selected, unlocked records can change.
- `target_metadata`: the modeled Entity's schema-qualified identity, definition,
  grain and ordered modeled Attributes. These are not registered physical targets.
- `source_evidence` and `mapping_support`: eligible physical or modeled sources,
  source support and applicable Assertions for this Entity/System pair.
- `existing_mapping`: existing Object and Attribute documents, order, status and
  locks. Null documents mean unauthored or cleared transformations.
- `authoring_policy`: effective Model naming, SCD guidance and configured columns.
- `source_system`: exact selected System and eligible default-System marker.
- `object_output_template` and `attribute_output_template`: selected document guidance.

`get_mapping_target`, `get_mapping_sources` and `get_existing_mapping` read frozen
prepared context only. Omitted/empty selectors return all eligible records, paged;
continue using the returned cursor. Records stay whole, oversized records fail
explicitly, and unavailable evidence is not an empty result. Readers do not query
physical data or execute generated SQL. Reader availability follows saved Prompt
configuration.

## Backend validation

1. Resolve the frozen Model, schema-qualified Entity/System pair, route, selected
   Attributes and authorized source evidence.
2. Accept a subset of selected, unlocked Attribute names; reject duplicates,
   unknown names and output that replaces preserved content. Derive identities,
   status, locks, template codes and provenance server-side.
3. Validate schema version, outer fields, nonnegative dependency order and document
   limits: 524,288 bytes for Object content, 65,536 for each Attribute document,
   and at most 5,000 Attribute entries. Normalize empty documents to null.
4. Check declared source references and aliases against eligible frozen evidence,
   along with preserved Object logic. Custom document prose is not proof that
   arbitrary expressions execute correctly.
5. Reconcile missing selected output to explicit saved blanks; omit new empty
   records. Validate staged records and the complete future Model graph, including
   typed ownership, references, dependencies, locks and revision fences.
6. Use bounded repair for invalid candidates. Missing-rule diagnostics accompany
   partial output; true integrity or provider failures remain pair-isolated.
   Schema validation does not execute SQL or prove business results.

## Prompt sources

Use the maintained prompt artifacts directly; this document does not duplicate
full prompt bodies:

- [One-shot defaults and candidate schema](workflow-prompts/mapping.one_shot.json)
- [Tool-assisted defaults and candidate schema](workflow-prompts/mapping.tool_assisted.json)
- [Synthetic review example](workflow-prompts/mapping.review.example.json)
- [Runtime candidate contract](../web_app/backend/gds_workbench_api/features/mapping/contracts.py)
- [Runtime output guidance](../web_app/backend/gds_workbench_api/features/mapping/output_schema.py)
- [Reconciliation](../web_app/backend/gds_workbench_api/features/mapping/reconciliation.py)

The runtime contracts remain authoritative for bounds and accepted fields.
