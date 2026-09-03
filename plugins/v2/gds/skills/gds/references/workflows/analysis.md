# Analysis

Turn physical metadata, Profiles, Assertions, and permitted queries into explicit modeling decisions. Do not treat a source table as an implied target Entity.

For every scoped Object, determine or state the uncertainty around:

- the business process or state represented and what one row means;
- candidate business identifiers and whether their meaning is stable across Systems;
- repeating or multi-valued groups, header/detail mixtures, and columns at different grains;
- functional dependencies: which identifier determines each descriptor;
- coded domains, reference data, lifecycle/status, effective dates, and history behavior; and
- plausible within- and cross-System relationships or identity overlaps.

Start relationship candidates from names, descriptions, keys, value domains, and existing evidence. Under the SQL policy, test only signaled candidates with bounded uniqueness, determinant consistency, join coverage, cardinality, orphan, and cross-System overlap checks. A query result is evidence, not an automatic relationship or merge decision.

Record supported, unsupported, or inconclusive findings with confidence and basis. A finding may remain inference-only. Populate measured fields only from one complete deterministic result; never fabricate or partially populate them. Unresolved identity, grain, or cardinality that changes the structure requires user evidence or blocks that decision.

Classify every input represented, context-only, excluded with reason, or blocked. Analysis informs Conceptual and Logical work; it never copies source structure into them.
