# Conceptual Model

Create a compact business view of what the organization manages and what happens to it. Conceptual is a required Logical Build phase and is business-facing, not a simplified table design. Use PascalCase unless the user or Model policy says otherwise.

Use Kimball's business-process-first discovery as an internal thinking aid:

1. Name the operational activities or state transitions represented, such as placing an order, servicing an account, or assigning a customer to a household.
2. Run a table-by-table pass. For every Object, state what one row means and which process, event, agreement, party, thing, place, or classification it supports. One Object may support several concepts or be context-only.
3. Build a small internal process-to-concept matrix: processes as rows, reusable business concepts as columns. Use it to expose shared concepts, duplicates, and missing context; do not persist the matrix as model records.
4. Consolidate candidates across Objects and Systems only when their business meaning agrees. Names alone never prove identity. Several Objects may support one concept, and one Object never forces one concept.
5. Define each retained concept in plain business language, including what one occurrence represents. Do not add Attributes, keys, normalization, physical tables, or dependency order.
6. Add verb-based business relationships from completed Analysis. Record high-level cardinality only when supported; otherwise use `unknown`. Never infer physical keys.
7. Account for every input as represented, context-only, excluded with reason, or blocked.

Before authoring, challenge the result: remove technical staging concepts, merge synonyms, split concepts that combine different business meanings, and verify that each concept helps explain a process or relationship. Reject one-concept-per-Object, renamed table inventories, and a Conceptual-to-Logical copy. Conceptual supplies shared vocabulary and boundaries; Logical grain and normalization are decided separately.
