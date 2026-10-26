# Logical design

Use for the guided Logical phase and applicable Grill Me work. Produce a coherent business project with traceable inputs, usable keys and relationships, and explicit generation rules. Load [normalization](normalization.md), [naming](../project/naming.md) and [keys/audit](../project/keys-and-audit.md) as those decisions arise. [Logical records](../project/logical.md) owns exact fields, sources and type codes.

## Build or Optimize

A Project has one Logical model. Work in one of two ways, matching the web workflow:

- **Build** one Subject Area at a time when the user names areas or asks to model Objects that have no Entity yet. The area is a focus window over its Objects, never evidence.
- **Optimize** existing Entities across the model when the user asks to improve, review or repair what is built. Optimize needs no Subject Area.

## Build one Subject Area at a time

1. **Read the focus.** Read the area's active member Objects with `select --session <dir> --area project --dataset subject_area_table --where '{"subject_area_name":"<area>"}'`, then the active Logical Entities already built from them (an Entity belongs to the areas of its active Object sources) and their neighbours: Entities those Entities relate to, and Entities built from Objects this area shares with others.
2. **Reuse before you create.** An Object may sit in several areas. When an earlier area already built an Entity from a shared Object, extend or relate to that Entity; never build a second copy.
3. **Return only changes.** Write new and changed records only; leave unchanged records out of the Change Set. Retire a record by setting its `*_is_active` field to `false`; never delete it or drop it to imply removal. A retired Entity takes its active Attributes and the Relationships that use them with it.
4. **Relate across the boundary.** A foreign key may point at a neighbour outside the area. Keep the whole graph coherent; the area limits what you build, not what you may reference.
5. **Check the area.** Run `coverage --session <dir> --layer logical --subject-area <area>` for the area's own target, then `validate` for the whole Project.
6. **Several areas.** Build them one after another in the web Build dialog's default order, which `validate` reports as `subject_area_summaries`: most shared Objects first, so shared Objects are modeled once and later areas reuse them. Validate after each area.

## Build the project

1. **Inspect the effective context.** Read selected active applied Input Scope, relevant Metadata, profiling/enrichment, Analysis, Context records and existing Logical records. Reuse established policy and phase choices. Protect existing records under [record state](../record-state.md). A Subject Area may choose the Objects; never treat its name or definition as evidence.
2. **Define Entity boundaries and grain.** For each business subject, state one occurrence, its lifecycle/time boundary and candidate business identity. Apply the normalization guide to retain, split, associate or consolidate. Derive the design from eligible source evidence and business Context; avoid mechanically copying the physical table inventory. Choose `logical_entity_type` from the active codes in the read-only `logical_entity_type` list.
3. **Design Attributes and keys.** Account for the subject's useful input Attributes, preserving meaning, units, precision, nullability and time semantics. Use [keys and audit](../project/keys-and-audit.md) for the first generated surrogate, separate natural-key tuple, typed foreign keys and ordered audit block. Source storage types and sample maxima are evidence, not automatic target types or production limits. Do not invent natural-key uniqueness when identity remains unresolved.
4. **Design relationships child -> parent.** Each `logical_relationship` runs from the child's foreign-key Attribute to the parent's key, normally its surrogate; one foreign key has one parent. An Attribute name, definition or Analysis finding alone does not create a relationship. Explain the complete business-key lookup that will obtain the parent key; copying a source identifier is not the same operation. Use `many_to_one`, or `one_to_one` when each parent has at most one child; model many-to-many as an `association` Entity with one Relationship per foreign key. Preserve role distinctions and genuine self-references. Record optionality in the basis because Logical records have no separate optionality field.
5. **Attach usable lineage.** Follow the source rules below for every Entity and Attribute. Distinguish source contribution, lookup input and intentional generation. Preserve all relevant contributors without treating the source list as an executable Mapping. SQL remains optional under [query scope](../query-scope.md); all executed evidence retains its batch scope.
6. **Order dependencies.** Review dependencies across the complete graph. Set Entity dependency order consistently with known dependencies; retain cycles/self-lookups as explicit execution considerations rather than claiming an impossible single-pass order. Process scheduling is designed in its own workflow.
7. **Review business quality and coverage.** Run the relationship and graph review below, then check the design against the requested outcomes and quality checks. Account for every selected Object and Attribute as a contribution, context, justified exclusion or unresolved item. Reassess affected downstream records when revising the project; preserve unrelated work.
8. **Write and validate locally.** Use [Project authoring](../project/change-sets.md) to save complete changed records in the three Logical dataset arrays, then run [local validation](../local-validation.md). Repair structural failures and substantive modeling contradictions before treating affected work as complete. Continue local work where prerequisites permit; use the shared lifecycle only at the actual handoff/dependency boundary.

Logical cardinality has no `unknown` value. If a relationship's multiplicity cannot be supported by metadata, business rules or permitted evidence, retain that candidate in task evidence and resolve it before authoring the relationship. Do not invent a cardinality, fabricate a Context or deactivate a guessed record to make it pass. Physical composite lookup keys remain intact in explanations/evidence; the Relationship payload itself has one Attribute per endpoint.

## Relationship and graph review

1. Read the complete effective **active** Logical Entity, Attribute and Relationship records, including pending changes. Reuse applicable Analysis, source context and recorded user decisions; respect locks and the requested edit scope.
2. Inspect candidate references by name/role **and** business domain, type, Entity grain, parent identity and complete key context. Include differently named references, classifications and hierarchies. An `ID` suffix or matching names alone never establishes a FK. Keep composite lookup tuples intact; do not represent their components as independently valid joins.
3. Compare supported references with actual `logical_relationship` records. Add missing justified relationships through the [Logical contract](../project/logical.md), from the child's real active foreign key to the parent's key, with compatible types, supported cardinality and concise basis. Do not invent an edge or change a protected record to improve connectivity. Metadata/business evidence can suffice; SQL is optional under policy.
4. Identify isolated Entities (no relationship to another active Entity) and disconnected components (groups with no connecting active relationship). Inspect the whole graph, including links that cross Subject Areas; a self-reference alone does not connect an Entity to another. Present the Entity names in each relevant component and any justified proposed links, with one-line reasons or uncertainty.
5. Before completing the requested project work, resolve unexplained separations with the user: **"Keep [Entity/group] intentionally separate, or connect it through [justified relationship]?"** Offer a link only when supported; otherwise ask whether to keep it separate or supply missing business context. Reuse an existing decision while its basis remains applicable. The user may keep standalone Entities or separate groups; record that choice in the current task, without a compulsory Context.
6. After agreed edits, validate and review the effective graph again. Preserve unrelated/protected work and expose blocked relationships. Intentional separation is valid, not a structural error; never manufacture joins to make the graph fully connected. Discussion-only work can report proposals without writing records.

## Sources and justified standalone structures

- An Entity's physical sources reference real scoped **Objects**; an Attribute's physical sources reference real scoped **Attributes**. Copy exact registered keys, including physical placement Tenant. Each Attribute's physical source must also have its matching Object source on that Entity; the current Apply path requires this even though earlier validation does not fully check it.
- Use several sources when several inputs contribute. If two sources disagree, explain reconciliation/precedence when known or record the gap; the order of sources is not an executable rule. Referencing several tables does not prove row identity or valid joins.
- Subject Areas do not guide Logical design and cannot be a typed source. Use attributable business Context directly; do not substitute area names or Analysis record IDs for physical lineage.
- Generated surrogates, framework audit fields, calendar structures and justified constant/reference sets may have `sources: []`. Explain their meaning and population ownership. Do not fabricate an Object, Attribute, Connection or source System to avoid an empty array.
- Reuse or create an [Context](../project/context.md) only when an applicable user/documented rule needs durable representation, such as an agreed fiscal calendar or a fixed business code set. A straightforward generated field or ordinary design decision does not require one. Existing user instructions are evidence; an agent's unsupported inference is not.
- A calendar needs a declared grain, range and relevant calendar rules. A constant set needs intended values/meanings and ownership of changes. Missing business-specific details stay visible. Designing a later `DimDate` does not require inventing a physical source or moving Gold work into the Logical phase.
- For source-derived outputs, maximize useful lineage. Empty sources must not hide available input contributions. For independent outputs, record how generation will be supplied; downstream Mapping/Code must still support that path. No fabricated `SourceSystemID` or source expression is permitted to make a standalone design look executable.

## Quality checks

| Check | Required review |
|---|---|
| logical.grain | One coherent occurrence per Entity; mixed header/detail, event/current state and repeating membership are resolved. |
| logical.identity | Natural-key tuple and source namespace are justified; generated IDs do not hide duplicate business occurrences. |
| logical.boundaries | No unexplained source-shaped copies, duplicate meanings, excessive lookups or missing independent subjects; Entities built from shared Objects are reused across areas, not copied. |
| logical.attributes | Useful source-specific fields retained; consolidated meanings, units, types, precision and time semantics agree. |
| logical.relationships | Child -> parent from a real foreign key to the parent's key; compatible types, coherent cardinality and optionality; full lookup identity and possible fan-out considered. |
| logical.connectivity | Supported FKs have explicit records; isolated Entities and disconnected components are reviewed, with applicable user decisions for intentional separation. |
| logical.lineage | Source-derived outputs trace to actual inputs; Attribute sources have parent Object sources; intentional generation is explained. |
| logical.population | Confirmed names, own surrogate first, complete audit block and database/framework/source ownership agree. Missing template definitions remain unresolved. |
| logical.coverage | Selected Objects and Attributes accounted for, per Subject Area when building an area; unsupported assumptions and blocked work remain visible. |

For consequential consolidation or complex projects, use a focused independent review when available, or explicitly review the alternatives in the same task. Review actual records and requirements; an extra agent, a low Entity count or a clean validator result does not prove a good project. Ask for business clarification where it would change the design.

## Compatibility notes

These rules combine automated structural/policy checks with agent review of business meaning. Atlas quality checks permit supported metadata-derived inference and optional Context records; they reject contradictory claimed measurements. Never invent evidence to clear a finding. See the [local validation](../local-validation.md) for enforcement boundaries.

Generated calendars have precedent in [Microsoft date-table guidance](https://learn.microsoft.com/en-us/power-bi/guidance/project-date-tables); Power BI-specific time-intelligence requirements are not automatically Logical Model rules.
