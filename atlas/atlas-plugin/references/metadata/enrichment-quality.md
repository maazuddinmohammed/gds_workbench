# Enrichment quality

Reusable description and inferred-type guidance for enrichment and downstream workflows. Procedures are Atlas recommendations synthesized from the user's framework, inspected contracts and the primary sources cited below. They are not claims that those sources prescribe this exact workflow.

## Describe the Object's meaning

1. **Collect relevant context once.** Read the owning Tenant, originating System, actual Connection, their types/descriptions, the Object's columns and any supplied definitions. For Bronze, storage System/Connection may differ from business origin. Follow confirmed lineage and expressions when they affect meaning.
2. **State what is known.** Identify the business subject, purpose and row grain. Separate declared, observed and inferred evidence in task notes. Existing descriptions and schema patterns suggest interpretations; names or generated prose alone do not prove them.
3. **Investigate only useful gaps.** For uncertainty that changes the description, inspect source comments, approved terminology, related definitions or permitted aggregate evidence. Uniqueness checks may support grain; value patterns alone cannot establish tax treatment, currency, business intent or a join relationship.
4. **Write a direct description.** Start with the represented business entity/event or operational fact. Add what one row represents when supported, then any important lifecycle, scope or usage distinction. Use concise sentences; no fixed sentence count or new byte cap.
5. **Check every claim.** Remove unsupported assertions and text that merely restates a name. Do not prepend Zone, storage format, connection technology, 'this table contains data' or similar boilerplate. Include operational details only when they explain the Object's actual meaning.

Business context combined with schema, lineage and profile evidence is supported by [DataHub's documentation guidance](https://support.datahub.com/hc/en-us/articles/52985040530715-Best-Practices-for-AI-Ready-Documentation-in-DataHub-AI-Doc-Generation-and-Context-Documents) and [Google's metadata-generation guidance](https://cloud.google.com/blog/products/data-analytics/generate-metadata-automatically-in-google-data-cloud). Explicit row grain helps downstream interpretation; see [dbt's grain guide](https://www.getdbt.com/blog/guide-to-data-grain). Atlas retains unknowns rather than treating these sources as permission to invent details.

## Describe Attributes in context

1. Use the Object's established row meaning. Identify whether the Attribute is an identifier, measure, category, date/time, narrative value or operational field.
2. Explain its business role directly. Include units/currency, reference/code meanings, time basis or null meaning only when known and material. Preserve distinctions between similar fields.
3. Reuse supported terminology where the meaning is the same. Do not expand unfamiliar abbreviations, equate similarly named fields or copy a Source description when transformation changes its meaning.
4. Check that the description helps someone choose a field, interpret a value or write the correct calculation. Avoid 'identifier for ID' or 'amount value'; if meaning remains unknown, preserve the existing value/null and record the gap.

The [USGS data dictionary guide](https://www.usgs.gov/data-management/data-dictionaries) emphasizes useful definitions, reference domains, missing-value conventions and shared vocabulary. Broad architecture and evidence notes belong in shared context/task evidence; keep stored field descriptions focused.

## Small examples

Synthetic facts supplied for illustration; these are not defaults for actual tenant data.

| Established evidence | Suitable description |
|---|---|
| Sales system; one row per order line; item, quantity and selling unit price. | Individual items on customer orders. Each row represents one order line and records the item, ordered quantity and selling unit price. |
| line_amount excludes tax; currency is supplied by currency_code. | Order-line amount before tax, expressed in the currency identified by currency_code. |
| order_number is assigned by the ordering system; leading zeros distinguish valid identifiers. | Order number assigned by the ordering system, retaining leading zeros. |
| loaded_at records the time this record was ingested. | Time this record was ingested into the data platform. |
| amt has no reliable definition or corroborating context. | Leave the value unchanged; record that the amount's business meaning is unresolved. |

The same business meaning may justify the same description across Zones. A transformation that changes meaning requires a different description; a Zone label alone does not.

## Infer types with evidence

1. **Resolve the actual value.** Read physical type, inferred type, documented role, relevant Source/Bronze expressions and actual inputs. Constants and combined expressions are valid; Source type inheritance requires confirmed meaning-preserving lineage, not matching names or mandatory Attribute Mappings.
2. **Collect applicable declarations.** Prefer a current schema or documented format when it describes these values. Preserve known decimal precision/scale and timestamp semantics. A physical STRING declaration does not settle the logical interpretation of its contents.
3. **Choose a candidate by meaning.** Distinguish quantities from identifiers/codes. Use verified downstream-compatible type names and known native aliases. Retain meaningful leading zeros, formatting and code distinctions; do not infer a number merely because digits parse.
4. **Check uncertainty with permitted evidence.** Reuse existing profiles first. If needed under SQL policy, obtain aggregate counts of missing/nonmissing values, compatible/incompatible parses and relevant formats/ranges. State whether coverage is sampled or complete. Use declared missing-value conventions; do not silently treat zero, N/A or empty text as null.
5. **Check information loss and contradictions.** Consider rounding, overflow, meaningful formatting, date ambiguity, timezone behavior and mixed inputs. A successful cast can still change a value. Do not discard incompatible observations to force a preferred type or automatically relabel a declared numeric field as text because it contains a data-quality exception.
6. **Record the best supported conclusion.** Update only attribute_inferred_data_type under the selected replacement policy. Keep evidence method, scope and limitations in task notes; sample-derived sizes remain provisional and downstream target sizing needs its own decision. If evidence remains insufficient, preserve the existing value/null and record the gap. All-null observations are inconclusive on their own; an applicable declaration, expression or documented meaning may still establish the type.

Physical representation and logical types are separate concepts in [Frictionless Table Schema](https://specs.frictionlessdata.io/table-schema/). [DuckDB's detection documentation](https://duckdb.org/docs/current/data/csv/auto_detection) demonstrates candidate testing, sampling limits and ambiguous date formats. [Databricks DECIMAL documentation](https://docs.databricks.com/aws/en/sql/language-manual/data-types/decimal-type) demonstrates that casts can round while succeeding. These inform the checks above; Atlas does not adopt their inference defaults automatically.

| Evidence | Type conclusion |
|---|---|
| A textual order identifier has meaningful leading zeros. | Keep a textual inferred type; numeric parsing would lose meaning. |
| Current Source declaration is DECIMAL(12,2); verified Bronze lineage preserves the value as text. | DECIMAL(12,2) is supported as an inferred type while physical storage remains STRING. |
| A small sample contains decimal-looking values. | Investigate a decimal candidate; observed precision/scale are not a production-capacity guarantee. |
| Values such as 03/04/2025 have no known date convention. | Date interpretation remains unresolved; do not choose a locale by guesswork. |

Evidence queries use supported registered coordinates and SQL policy, with masking respected through known mappings and expression inputs. Do not inspect protected values or treat missing lineage as evidence of no masking. Keep findings and aggregates; do not retain physical samples or raw tool envelopes. The exact reusable SQL helpers will be finalized separately.

## Enrichment checks

These are modular workflow checks for later implementation/review, separate from the [existing table checks](validation.md). No new validators are implemented by this document.

| Rule | Check / purpose | Enforcement status |
|---|---|---|
| enrichment.scope | Exact selected Object/Attribute keys, Zone and owner; Model scope revision when used. Prevent accidental expansion or wrong-Tenant writes. | Existing ownership/reference checks plus proposed workflow scope comparison. |
| enrichment.fields | Compare with incoming effective records; enrichment changes only the three allowed fields. Preserve earlier pending authoring edits. | Proposed local/backend operation-boundary check; not a restriction on general Metadata authoring. |
| enrichment.descriptions | Meaningful Object/Attribute definitions, consistent terminology and supported claims; no Zone boilerplate or tautology. | Agent review rubric; a text/schema validator cannot prove business truth. |
| enrichment.types | Evidence supports interpretation; physical type unchanged; identify loss, ambiguity and limited coverage. | Existing null/nonblank/100-character field shape; semantic checks proposed. No current inferred-type grammar validator. |
| enrichment.protection | Preserve locks and masking protections; no inferred-meaning changes to activity/key flags. | Existing lock checks; evidence helper lineage/masking parity needs review when ported. |
| enrichment.coverage | Account for selected records as updated, unchanged, protected or unresolved; complete local batch and retain evidence for downstream use. | Proposed workflow result summary; coverage does not require inventing a value. |

Shared description fields are nullable text with no 2,000-byte limit found in their record schemas. The inferred-type field is nullable or a nonblank string of at most 100 characters. Do not carry legacy workflow caps or fill-only policies into Atlas as database requirements.

## Skill and helper design

The skill contains the sequence; this reference holds reusable quality rules and examples. Existing Snapshot readers and validators should be reused. Add deterministic helpers for repeated evidence/type checks only when their contracts are agreed. This follows [Agent Skills guidance](https://agentskills.io/skill-creation/best-practices) on concrete procedures, examples, progressive disclosure and validation loops. Outcome quality still needs evaluation with representative cases and the models the plugin will support; structural validation is not an evaluation of writing quality.

Local provenance: metadata_records.py; current GDS metadata-enrichment.md; profiling.js; metadata-enrichment-type-evidence.sql. Legacy Attribute-Mapping-only Bronze inference, Model-required selection, scope caps and inferred-type fill-only policy are not adopted by this draft.
