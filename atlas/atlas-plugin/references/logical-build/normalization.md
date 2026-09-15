# Normalization decisions

Use while choosing Logical Entity boundaries. Start from business meaning, grain and dependencies, using the user's twelve factors below as decision prompts. They are not a score, required questionnaire or automatic split rule. Explain consequential decisions in the existing task; simple cases need only a short reason.

## Decide what belongs together

1. State what one Entity occurrence represents, including its time boundary, and identify its candidate business key or unresolved identity. Inspect real Attributes and context; a surrogate does not remove dependencies on business facts.
2. Ask what determines each Attribute: the complete occurrence, part of its business key, or another subject. Separate mixed grains and independently repeating occurrences; consider independent subjects when their own facts/lifecycle need consistent management.
3. Compare retain, split and association designs using the relevant factors. Prefer the simplest design that preserves meaning, identity and required integrity. Neither a table-count target nor blanket 3NF compliance decides the result.
4. Check required relationships and business questions after the proposed split/consolidation. Confirm that full keys preserve occurrences and that joins do not introduce unintended fan-out or loss. Use metadata and domain evidence; SQL is optional under [query scope](../query-scope.md).
5. Record a material decision as **retain/split/link → business reason → grain/key implications → unresolved issue**, if any. Preserve the affected input lineage through [Logical sources](../model/logical.md). Revisit the decision when conflicting evidence changes its basis.

## Twelve decision factors

| Factor | Favors separating | Favors retaining together / qualification |
|---|---|---|
| 1. Independent business meaning | A distinct subject with a definable boundary. | Information only describes its parent; a label alone need not become an Entity. |
| 2. Repetition | Repeated facts belong to a separately managed subject. | Small controlled repetition; repetition or low distinct count alone is insufficient. |
| 3. Update consistency | One fact must change consistently wherever referenced. | Immutable or deliberately recorded historical facts may belong to each occurrence. |
| 4. Cardinality | Independent children, repeating groups or genuine many-to-many occurrences. | True one-to-one may stay together; it can also connect distinct subjects or an optional extension. |
| 5. Independent lifecycle | Creation, changes or deactivation happen independently. | No lifecycle outside the parent. Storage history alone is not a new business subject. |
| 6. Independent identifier | The business identifies the subject separately. | No distinct identification need; absence of a source ID does not rule out a valid Entity. |
| 7. Additional attributes | The subject has its own descriptions, rules, hierarchy or validity. | One or two simple descriptive fields may stay with the parent; count alone is not decisive. |
| 8. Relationships | Other Entities meaningfully refer to the subject. | No other references and no independent meaning; avoid hypothetical reuse as the only justification. |
| 9. Data integrity | Separate identity, uniqueness and referential rules protect real business facts. | Extra relational constraints provide little benefit. A surrogate alone does not enforce business uniqueness. |
| 10. Query pattern | Independent updates and consistent shared facts matter. | Repeated joint analysis may justify a later read-oriented shape; preserve distinct subjects in the Logical design unless a concrete reason supports combining them. |
| 11. Performance | Duplicated mutable facts would impose material write cost. | Evidence shows a read benefit worth controlled duplication; do not guess physical performance from table count. |
| 12. Historical requirements | Changes to the subject need their own validity/lifecycle. | The event deliberately records the value at that time. Current and event-time values may be different facts. |

These factors come from the user's proposed framework, refined for Atlas. They do not require physical SQL tests or a twelve-row decision log for each Entity.

## Cases that change the decision

- **Repeating occurrences:** represent Order and Order Line separately when one order contains several lines. If a product can appear twice, `Order + Product` is not the line's unique business key; consider evidenced `Order + LineNumber`.
- **Many-to-many:** use an association Entity when the model must represent each membership/event. Give it the required own surrogate and identify its actual business occurrence. Endpoint pairs need not be unique when memberships repeat over time. Association Attributes describe that occurrence.
- **Reference values:** repeated `Status` or `Color` does not automatically require a lookup Entity. A managed classification with meanings, hierarchy, validity or shared references may justify one. Strings are legitimate identifiers; numeric keys do not determine business importance.
- **Historical facts:** Product's current price and Order Line's agreed price have different meanings. Retain the transaction price; do not replace it with a join to today's Product price. Apply the same reasoning to shipment-time addresses and versioned agreements.
- **Equivalent sources:** consolidate only when meanings, grain and Attribute semantics agree. Retain source-qualified business keys or verified crosswalks when identifiers overlap. Matching values across Systems do not establish a shared identity.
- **Simple one-to-one:** retain descriptive fields when they belong to the same occurrence. Separate an independently governed extension when justified; cardinality alone does not force a merge.

Preserve identifier formatting, units, decimal precision and time semantics when consolidating Attributes. Do not drop useful source-specific fields just because only one System supplies them. Unsupported identity or lifecycle assumptions remain unresolved rather than becoming fabricated keys or structures.

## Design checks

Review one coherent grain per Entity, Attribute dependencies, full business-key tuples, unnecessary splits, missed independent subjects, historical meaning and relationship joinability. Compare plausible alternatives only where they could change quality. Use [local validation](../local-validation.md) for structural checks; use the actual business requirements to judge the model.

The distinction between subject boundaries and implementation choices is supported by [Oracle's logical-model guidance](https://docs.oracle.com/en/database/oracle/sql-developer-data-modeler/19.2/dmdug/data-modeler-concepts-usage.html). [Microsoft's design examples](https://support.microsoft.com/en-us/access/database-design-basics) illustrate separate subjects, classifications with their own descriptions and association records. These inform the procedure; Atlas's twelve-factor framework and conventions are not an industry-mandated algorithm.
