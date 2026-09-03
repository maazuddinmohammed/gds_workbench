# Dimensional Build

Require applied Logical Mapping and eligible Silver contributions. Dimensional is optional.

Use PascalCase by default. Dimensional key Attributes end in `Key`, such as `CustomerKey`; user instructions or Model policy override this.

Follow Kimball's four decisions in order for each selected business process:

1. Select one operational business process, not a department or report.
2. Declare exactly what one atomic fact row represents before choosing Dimensions or measures.
3. Identify descriptive Dimensions that are true to that grain, including role-playing use. Compare processes through an internal process-to-dimension bus matrix and conform a Dimension only when meaning, keys, and values are compatible.
4. Identify numeric, factless, or event facts true to the declared grain. Define additivity and default aggregation; never store a measure from another grain.

Then choose transaction, periodic-snapshot, accumulating-snapshot, or factless Fact behavior; identify Bridges only for genuine many-to-many grain; define history behavior, keys, and relationships; and trace every structure to applied Logical Mapping and evidence. Record optionality explicitly rather than inferring it from cardinality. Mark each eligible Silver contribution represented, context-only, excluded with reason, or blocked.

Do not guess grain, conformance, history, measures, or optionality. Apply Dimensional records through one Model Change Set and stop before Gold registration.
