# Dimensional Build

Require applied Logical Mapping and eligible Silver contributions. Dimensional is optional.

Use PascalCase by default. Dimensional key Attributes end in `Key`, such as `CustomerKey`; user instructions or Model policy override this.

For each selected business process:

1. Declare fact grain before measures.
2. Identify Facts, Dimensions, Bridges, conformed Dimensions, and role-playing use.
3. Define measures and aggregation behavior, history behavior, keys, and relationships.
4. Trace every structure to applied Logical Mapping and supporting evidence.
5. Record relationship optionality explicitly from evidence; never infer it only from cardinality.
6. Mark each eligible Silver contribution represented, context-only, excluded with reason, or blocked.

Do not guess grain, conformance, history, measures, or optionality. Apply Dimensional records through one Model Change Set and stop before Gold registration.
