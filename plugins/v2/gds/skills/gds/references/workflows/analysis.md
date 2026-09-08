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

Judge each candidate's business meaning after inspecting its evidence: matching values can be coincidental, and a join can be technically valid but combine different grains. Reconcile overlapping or contradictory findings before using them downstream.

Use `analysis_result` only for relationships between real physical Attribute endpoints. For inference-only supported, unsupported, or inconclusive findings, put the verdict and reasoning in `relationship_basis`; leave **all** `validation_*` fields null, including `validation_result`. Populate that entire group only from one complete deterministic result. Do not manufacture endpoint pairs for grain or normalization notes: carry those decisions in task notes, model definitions, and source rationales. Unresolved identity, grain, or cardinality that changes the structure requires user evidence or blocks that decision.

Classify every input represented, context-only, excluded with reason, or blocked. Analysis informs Conceptual and Logical work; it never copies source structure into them.

Example: repeated CustomerID values in Orders support a candidate many-to-one reference only if Customer's key is unique in the same Tenant/System boundary and the business roles agree. Equal IDs across two independent CRMs do not establish shared identity. A failed or inconclusive check must change the proposed relationship, confidence, or coverage outcome; never merely attach statistics and continue unchanged.
