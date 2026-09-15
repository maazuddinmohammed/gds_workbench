# Business concepts

Use for the Conceptual phase and applicable Grill Me work. Define business concepts and their associations from the selected Model inputs. Keep field definitions in [Conceptual records](../model/conceptual.md), local writes in [Model Change Sets](../model/change-sets.md), and protection in [record state](../record-state.md).

## Identify and consolidate concepts

1. **Read the business context.** Use the selected active applied Input Scope, Object/Attribute meanings, Tenant/System context, relevant Assertions and existing Analysis. Read existing and pending concepts, aliases and relationships, including inactive history for identity matching. Reuse Profile evidence when useful; neither profiling nor SQL is mandatory to identify a clear business meaning.
2. **Identify what the business records.** Look for parties, things, places, events, agreements and meaningful classifications. For each candidate, state what one occurrence represents and what distinguishes it from nearby concepts. An Order and an Order Line have different meanings and grains. A technical ingestion batch or a history copy does not automatically introduce a business concept.
3. **Check for an existing meaning before adding.** Compare names, aliases, definitions, grain and business context across the effective Model. Reuse a concept when those meanings agree, even across Systems or differently named Objects. Preserve separate concepts when identity, purpose or business lifecycle differs. Shared spelling, matching IDs or similar columns alone do not establish equivalence.
4. **Consolidate equivalent candidates.** Select one established business name and retain genuine synonyms as aliases. Several Objects can support that concept; one Object can support several concepts when its contents justify each. Do not create a concept per table, Zone, batch or System. Consolidating meanings does not merge physical rows or prove that identifiers match across Systems.
5. **Write the definition and grain.** Define the subject in plain business language, with its relevant boundary. Describe one business occurrence; omit physical keys, types, audit columns and normalization decisions. Follow [Model naming](../model/naming.md): Conceptual Objects and Relationships use PascalCase by default, with explicit user overrides. Type examples are categories, not a new enum. Do not force a broad Party concept or split every repeated string into a separate classification.
6. **Attach specific support.** Select the actual scoped Objects or applicable Assertion Records that establish this meaning. Explain each source's contribution. Attribute names may clarify the reason but cannot become Attribute-typed supports. Merge supports by source identity using the exact shared schema. A locked concept may remain an endpoint, but adding support or an alias changes it: preserve it and record the blocked improvement instead of creating a duplicate.

For classifications, ask whether the business recognizes a distinct category with its own meaning, membership or rules. A status field can support an Order Status concept without a separate physical lookup table; use its real owning Object as support. A few repeated values alone are insufficient. An intentionally independent concept, such as a user-requested calendar or constant set, may have empty supports with its purpose explained. Use a real applicable [Assertion](../model/assertions.md) when a supplied business rule needs durable representation; do not require one for every concept or fabricate support. Unsupported business claims still remain unresolved.

## Identify concept relationships

7. **Write business sentences.** Review relevant Analysis and Object meanings, then express meaningful associations: Customer places Order; Order contains Order Line; Product belongs to Product Category. A physical foreign key is evidence, not a requirement for a conceptual association. Metadata and explicit business rules may establish a relationship without SQL. Conversely, a physical join does not automatically deserve a conceptual edge.
8. **Consolidate repeated evidence, preserve roles.** Several physical links may support one business relationship. Merge their evidence under that relationship. Keep different business roles, such as Order billed to Customer and Order shipped to Customer, when their meanings differ. Do not add a second inverse edge just to restate the same association, infer every transitive connection, or force every concept to connect.
9. **Determine direction and cardinality.** Read multiplicity from the proposed from concept to the to concept. Customer → Order may be one-to-many while Order → Customer is many-to-one. Explain the business rule separately from any observed data. Do not infer one-to-one from one supporting Object per side or one row per key in a sample. Use `unknown` when the association is supported but multiplicity remains unclear. Many-to-many is valid at this stage; bridge design belongs to logical modeling.
10. **Explain the relationship's own evidence.** Record why the association exists and why its cardinality is inferred or measured. Attach applicable supports that establish the association, rather than blindly copying both concepts' support arrays. Preserve contradictions and material limitations. Confidence describes the supported conclusion; no SQL does not automatically mean low confidence.

Resolve only consequential uncertainty. Ask a focused business question, inspect existing evidence, or use permitted SQL under [query scope](../query-scope.md). Queries retain each Object's approved batch selection; a shared batch number does not prove aligned populations. Never turn missing SQL into fabricated measurements or require SQL to confirm an already clear association.

## Save and validate locally

11. **Write complete records.** Read the [Conceptual field guide and examples](../model/conceptual.md) and use the shared Model authoring procedure. Resolve exact schema questions with its read-only `describe_model_dataset` contract using `conceptual_object` or `conceptual_relationship`. Write the two local dataset arrays; preserve previous changes and protected nested members. Conceptual supports are nested records, not another dataset.
12. **Validate, repair, then review coverage.** Run [local validation](../local-validation.md) on the effective result after the phase's local batch. Apply the semantic checks below; repair failures and rerun affected checks. Each selected Object should support a concept/relationship, provide context only, be intentionally excluded, or remain explicitly unresolved. Reuse the existing task's evidence/progress for this compact coverage record; no separate handoff kit. Structural validity does not prove business completeness.

| Quality check | What to check / why |
|---|---|
| conceptual.meaning | Definition and grain express a business meaning, not a table/Zone description. |
| conceptual.identity | Equivalent meanings reuse concepts; different meanings and relationship roles remain distinct. |
| conceptual.support | Source-derived claims have relevant eligible supports; each support explains its contribution. Intentional independent concepts explain their basis without invented sources or mandatory Assertions. |
| conceptual.relationship | Association, direction and cardinality agree; uncertain multiplicity is explicit, inferred evidence is not labeled measured. |
| conceptual.coverage | Selected Objects and meaningful relationships were considered; exclusions, protected changes and unresolved items stay visible. |

These are workflow quality checks, not claims that the current backend proves semantics. The shared local guide owns structural checks and reporting. Keep related Analysis and Conceptual changes together locally when prerequisites permit; completing this phase alone does not trigger Stage or Apply. Reassess affected downstream work after revising concepts.

## Compact decisions

| Evidence | Decision |
|---|---|
| CRM customer and ERP customer master describe the same purchasing-party meaning | One Customer concept, two Object supports. Cross-system record matching remains unproven. |
| Current and history Objects describe that same Customer | Reuse Customer; storage history alone is not another concept. |
| Sales account describes a purchasing relationship; finance account describes a ledger classification | Distinct Customer Account and Ledger Account; same word, different meaning. |
| Orders contains separate billing and shipping customer references | Preserve the two role relationships to Customer when the business meaning is shared. |
| Products contains a business-defined category but no scoped category Object | Category may be a concept supported by Products; no invented physical lookup or Analysis endpoint. |

## Representation limits

- Current Conceptual schema rejects self-relationships. If consolidating concepts produces one, retain the intended hierarchy/association in task evidence and report the limit. Do not invent another concept to bypass it.
- Conceptual records contain no Attributes, physical keys for the concept itself, minimum-participation fields or Analysis-reference fields. Use only the supported fields; Object supports retain their exact physical identities.
- A locked or inactive existing concept is not missing. Follow shared state rules when matching and revising it; do not bypass protection with synonyms or automatic reactivation.

## Design basis

This Atlas procedure applies general guidance to the existing schema and the user's metadata-first policy. Business entities and associations are the conceptual focus in [IBM's data-modeling guidance](https://www.ibm.com/think/topics/data-modeling). Meaning depends on business context, as described in [Microsoft's domain-analysis guidance](https://learn.microsoft.com/en-us/azure/architecture/microservices/model/domain-analysis). Preferred names, aliases and equivalence are distinct from mere relatedness in the [W3C SKOS primer](https://www.w3.org/TR/skos-primer/); Atlas does not require RDF or ontology tooling. These sources do not establish automatic correctness or require this exact sequence.
