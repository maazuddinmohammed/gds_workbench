# Logical design

Use for the guided Logical phase and applicable Grill Me work. Produce a coherent business model with traceable inputs, usable keys and relationships, and explicit generation rules. Load [normalization](normalization.md), [naming](../model/naming.md) and [keys/audit](../model/keys-and-audit.md) as those decisions arise. [Logical records](../model/logical.md) owns exact fields, sources and memberships.

## Build the model

1. **Inspect the effective context.** Read selected active applied Input Scope, relevant Metadata, Analysis, Concepts, Assertions and existing Logical records. Reuse established policy and phase choices. Protect existing records under [record state](../record-state.md). A Conceptual phase boundary alone does not require Apply; the current catalog has no applied Conceptual prerequisite for Logical authoring.
2. **Define Entity boundaries and grain.** For each business subject, state one occurrence, its lifecycle/time boundary and candidate business identity. Apply the normalization guide to retain, split, associate or consolidate. A Concept can inform several Entities; avoid mechanically copying either the physical table inventory or Concept inventory.
3. **Design Attributes and keys.** Account for the subject's useful input Attributes, preserving meaning, units, precision, nullability and time semantics. Use [keys and audit](../model/keys-and-audit.md) for the first generated surrogate, separate natural-key tuple, typed foreign keys and ordered audit block. Source storage types and sample maxima are evidence, not automatic target types or production limits. Do not invent natural-key uniqueness when identity remains unresolved.
4. **Design relationships.** Select actual modeled Attribute endpoints and author explicit `logical_relationship` records for supported FKs; an Attribute name, definition or Analysis finding alone does not create a relationship. By default, modeled FKs reference the parent's surrogate. Explain the complete business-key lookup that will obtain it; copying a source identifier is not the same operation. Preserve role distinctions and genuine self-references. Record optionality in the supported basis/definitions because Logical records have no separate optionality field.
5. **Attach usable lineage.** Follow the source rules below for every Entity and Attribute. Distinguish source contribution, lookup input and intentional generation. Preserve all relevant contributors without treating the source list as an executable Mapping. SQL remains optional under [query scope](../query-scope.md); all executed evidence retains its batch scope.
6. **Organize Submodels where useful.** Use the business grouping procedure below; memberships share Entity definitions. Review dependencies across the complete graph. Set Entity dependency order consistently with known dependencies; retain cycles/self-lookups as explicit execution considerations rather than claiming an impossible single-pass order. Process scheduling is designed in its own workflow.
7. **Review business quality and coverage.** Run the relationship and graph review below, then check the design against the requested outcomes and quality checks. Account for every selected Object and Attribute as a contribution, context, justified exclusion or unresolved item. Reassess affected downstream records when revising the model; preserve unrelated work.
8. **Write and validate locally.** Use [Model authoring](../model/change-sets.md) to save complete records in the four Logical dataset arrays, then run [local validation](../local-validation.md). Repair structural failures and substantive modeling contradictions before treating affected work as complete. Continue local work where prerequisites permit; use the shared lifecycle only at the actual handoff/dependency boundary.

Logical cardinality has no `unknown` value. If a relationship's multiplicity cannot be supported by metadata, business rules or permitted evidence, retain that candidate in task evidence and resolve it before authoring the relationship. Do not invent a cardinality, fabricate an Assertion or deactivate a guessed record to make it pass. Physical composite lookup keys remain intact in explanations/evidence; the Relationship payload itself has one Attribute per endpoint.

## Relationship and graph review

1. Read the complete effective **active** Logical Entity, Attribute and Relationship records, including pending changes. Reuse applicable Analysis, source context and recorded user decisions; respect locks and the requested edit scope.
2. Inspect candidate references by name/role **and** business domain, type, Entity grain, parent identity and complete key context. Include differently named references, classifications and hierarchies. An `ID` suffix or matching names alone never establishes a FK. Keep composite lookup tuples intact; do not represent their components as independently valid joins.
3. Compare supported references with actual `logical_relationship` records. Add missing justified relationships through the [Logical contract](../model/logical.md), using real active endpoints, compatible types, supported direction/cardinality and concise basis. Do not invent an edge or change a protected record to improve connectivity. Metadata/business evidence can suffice; SQL is optional under policy.
4. Identify isolated Entities (no relationship to another active Entity) and disconnected components (groups with no connecting active relationship). Inspect the whole graph, including cross-Submodel links; a self-reference alone does not connect an Entity to another. Present the Entity names in each relevant component and any justified proposed links, with one-line reasons or uncertainty.
5. Before completing the requested model work, resolve unexplained separations with the user: **"Keep [Entity/group] intentionally separate, or connect it through [justified relationship]?"** Offer a link only when supported; otherwise ask whether to keep it separate or supply missing business context. Reuse an existing decision while its basis remains applicable. The user may keep standalone Entities or separate groups; record that choice in the current task, without a compulsory Assertion.
6. After agreed edits, validate and review the effective graph again. Preserve unrelated/protected work and expose blocked relationships. Intentional separation is valid, not a structural error; never manufacture joins to make the graph fully connected. Discussion-only work can report proposals without writing records.

## Sources and justified standalone structures

- An Entity's physical sources reference real scoped **Objects**; an Attribute's physical sources reference real scoped **Attributes**. Copy exact registered keys, including physical placement Tenant. Each Attribute's physical source must also have its matching Object source on that Entity; the current Apply path requires this even though earlier validation does not fully check it.
- Use several sources when several inputs contribute. If two sources disagree, explain reconciliation/precedence when known or record the gap; source order alone is not an executable rule. Referencing several tables does not prove row identity or valid joins.
- Concepts guide design but are not a supported typed source in Logical payloads. Do not substitute Concept names or Analysis record IDs for physical lineage.
- Generated surrogates, framework audit fields, calendar structures and justified constant/reference sets may have `sources: []`. Explain their meaning and population ownership. Do not fabricate an Object, Attribute, Connection or source System to avoid an empty array.
- Reuse or create an [Assertion](../model/assertions.md) only when an applicable user/documented rule needs durable representation, such as an agreed fiscal calendar or a fixed business code set. A straightforward generated field or ordinary design decision does not require one. Existing user instructions are evidence; an agent's unsupported inference is not.
- A calendar needs a declared grain, range and relevant calendar rules. A constant set needs intended values/meanings and ownership of changes. Missing business-specific details stay visible. Designing a later `DimDate` does not require inventing a physical source or moving Gold work into the Logical phase.
- For source-derived outputs, maximize useful lineage. Empty sources must not hide available input contributions. For independent outputs, record how generation will be supplied; downstream Mapping/Code must still support that path. No fabricated `SourceSystemID` or source expression is permitted to make a standalone design look executable.

## Choose Submodels

1. Start with existing effective groups. Identify recognizable business subjects/capabilities such as Sales, Product Management or Finance, using the model's actual content and users' terminology.
2. Create a group when it gives a useful coherent view: related Entities share business purpose, rules or ownership, and grouping makes the Model easier to understand. A small cohesive Model may need no Submodel or one useful group. There is no required table count, group count or group-size ratio.
3. Avoid a group for each table, physical System, Zone or pipeline. Split a broad group when it conceals meaningful subjects; consolidate groups that have the same purpose. Do not create empty speculative groups or a catch-all that obscures real boundaries.
4. Create each Entity once, then add the applicable memberships. Customer may belong to both Sales and Service without two Customer Entities. Cross-submodel relationships remain part of the complete Model; memberships do not isolate keys, lifecycle or data copies.
5. Resolve each membership to the exact Submodel name and preserve its status/lock. New active memberships should connect active Entities and Submodels. Empty memberships are schema-valid; an ungrouped Entity is not automatically an error. Check whether that choice improves clarity.

Submodel names and membership fields come from the [Logical record contract](../model/logical.md). Naming, lifecycle and source rules remain shared; do not duplicate them in group-specific instructions.

## Quality checks

| Check | Required review |
|---|---|
| logical.grain | One coherent occurrence per Entity; mixed header/detail, event/current state and repeating membership are resolved. |
| logical.identity | Natural-key tuple and source namespace are justified; generated IDs do not hide duplicate business occurrences. |
| logical.boundaries | No unexplained source-shaped copies, duplicate meanings, excessive lookups or missing independent subjects. |
| logical.attributes | Useful source-specific fields retained; consolidated meanings, units, types, precision and time semantics agree. |
| logical.relationships | Real compatible endpoints; direction, cardinality and optionality coherent; full lookup identity and possible fan-out considered. |
| logical.connectivity | Supported FKs have explicit records; isolated Entities and disconnected components are reviewed, with applicable user decisions for intentional separation. |
| logical.lineage | Source-derived outputs trace to actual inputs; Attribute sources have parent Object sources; intentional generation is explained. |
| logical.grouping | Submodels clarify business subjects, share Entities and preserve cross-group relationships. |
| logical.population | Confirmed names, own surrogate first, complete audit block and database/framework/source ownership agree. Missing template definitions remain unresolved. |
| logical.coverage | Selected Objects and Attributes accounted for; unsupported assumptions and blocked work remain visible. |

For consequential consolidation or complex models, use a focused independent review when available, or explicitly review the alternatives in the same task. Review actual records and requirements; an extra agent, a low Entity count or a clean validator result does not prove a good model. Ask for business clarification where it would change the design.

## Compatibility notes

These rules combine automated structural/policy checks with agent review of business meaning. Atlas quality checks permit supported metadata-derived inference and optional Assertions; they reject contradictory claimed measurements. Never invent evidence to clear a finding. See the [local validation](../local-validation.md) for enforcement boundaries.

Business grouping follows the subject-view approach described in [Oracle Data Modeler](https://docs.oracle.com/en/database/oracle/sql-developer-data-modeler/19.2/dmdug/data-modeler-concepts-usage.html). Generated calendars have precedent in [Microsoft date-table guidance](https://learn.microsoft.com/en-us/power-bi/guidance/model-date-tables); Power BI-specific time-intelligence requirements are not automatically Logical Model rules.
