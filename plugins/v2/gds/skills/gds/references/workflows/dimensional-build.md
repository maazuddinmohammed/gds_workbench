# Dimensional Build

Require applied Logical Mapping and eligible Silver contributions. Dimensional is optional.

Show existing dimensional work and resolve add/refine/rebuild intent only if unknown. Ask which business processes and analytical questions to support; reuse prior outcomes or propose evidenced possibilities for confirmation.

Invoke Metadata Enrichment for missing underlying Source/Bronze descriptions/types through registered upstream lineage; use its separate owning-Tenant Metadata task, Apply, and refresh. Reuse complete enrichment and object-analysis notes. Silver modeled types/definitions come from applied Logical; fix upstream ambiguity rather than treating Silver as Source/Bronze input.

Read `../model-conventions.md`; reuse or confirm missing naming/audit choices. Use PascalCase by default. Dimensional key Attributes end in `Key`, such as `CustomerKey`; user instructions or Model policy override this.

Follow Kimball's four decisions in order for each selected business process:

1. Select one operational business process, not a department or report.
2. Declare exactly what one atomic fact row represents before choosing Dimensions or measures.
3. Identify descriptive Dimensions that are true to that grain, including role-playing use. Compare processes through an internal process-to-dimension bus matrix and conform a Dimension only when meaning, keys, and values are compatible.
4. Identify numeric, factless, or event facts true to the declared grain. Define additivity and default aggregation; never store a measure from another grain.

Then choose transaction, periodic-snapshot, accumulating-snapshot, or factless Fact behavior; identify Bridges only for genuine many-to-many grain; define history behavior, keys, and relationships; and trace every structure to applied Logical Mapping and evidence. Record optionality explicitly rather than inferring it from cardinality. Mark each eligible Silver contribution represented, context-only, excluded with reason, or blocked.

Assign `dimensional_submodel` by business process and reuse conformed Dimensions through Entity `submodels` memberships. Keep role-playing meanings distinct without copying the same Dimension definition.

After drafting, inspect the actual graph: can each Fact join its Dimensions at the declared grain without duplication or loss? Specify current versus event-time history lookup, unknown/late-member handling, snapshot completeness, and any Bridge allocation in existing definitions/source rationale and relationship basis. Mark semi-additive measures and the dimensions across which summation is valid; a balance is not additive over time. Do not invent extra policy fields. Missing executable policy must be resolved before downstream Mapping.

Read `../examples/modeling-decisions.md` for a worked grain check. Do not guess grain, conformance, history, measures, or optionality. Apply Dimensional records through one Model Change Set and stop before Gold registration.
