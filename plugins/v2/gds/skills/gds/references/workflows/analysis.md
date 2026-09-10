# Analysis

Turn physical metadata, Profiles, Assertions, and permitted queries into explicit modeling decisions. Do not treat a source table as an implied target Entity.

Reuse existing findings and `../session.md` object-analysis notes; revisit affected evidence only. Ask for additional business rules or documents only when not already supplied. For every scoped Object, determine or state the uncertainty around:

- the business process or state represented and what one row means;
- candidate business identifiers and whether their meaning is stable across Systems;
- repeating or multi-valued groups, header/detail mixtures, and columns at different grains;
- functional dependencies: which identifier determines each descriptor;
- coded domains, reference data, lifecycle/status, effective dates, and history behavior; and
- plausible within- and cross-Tenant/System relationships or identity overlaps.

Start relationship candidates from names, descriptions, keys, value domains, and existing evidence. Agent-generated descriptions are hypotheses, not independent relationship evidence. Use `../analysis-probes.md` and `analysis-plan` for registered composite-key, dependency and join aggregate probes. A plan is not a measurement; run only under the SQL policy. Test only signaled candidates with bounded uniqueness, determinant consistency, join coverage, cardinality, orphan, and cross-System overlap checks. A query result is evidence, not an automatic relationship or merge decision.

Judge each candidate's business meaning after inspecting its evidence: matching values can be coincidental, and a join can be technically valid but combine different grains. Reconcile overlapping or contradictory findings before using them downstream.

Zero orphans among non-null keys does not prove mandatory participation. Inspect source-key nulls and documented rules before declaring a required relationship.

Use `analysis_result` only for relationships between real physical Attribute endpoints. For inference-only supported, unsupported, or inconclusive findings, put the verdict and reasoning in `relationship_basis`; leave **all** `validation_*` fields null, including `validation_result`. Populate that entire group only from one complete deterministic result. Do not manufacture endpoint pairs for grain or normalization notes: carry those decisions in task notes, model definitions, and source rationales. Unresolved identity, grain, or cardinality that changes the structure requires user evidence or blocks that decision.

Consider composite candidates explicitly; the current `analysis_result` endpoints are individual Attributes. Keep composite determinants and joint measurements in scratchpad notes and supported rationale; never claim a tuple relationship was independently proven by its component pairs.

Review the full graph for competing relationships, contradictions, and unexplained isolated Objects. Choose measurement scope deliberately: batch Orders may reference historical Customers. Classify every input represented, context-only, excluded with reason, or blocked. Analysis informs Conceptual and Logical work; it never copies source structure into them.

Example: repeated CustomerID values in Orders support a candidate many-to-one reference only if Customer's key is unique within the evidenced identifier domain and the business roles agree. Equal IDs across two independent CRMs do not establish shared identity. Preserve each candidate as supported, rejected with evidence, or unresolved with the next discriminating check; silence is not a disposition. A failed or inconclusive check must change the proposed relationship, confidence, or coverage outcome; never merely attach statistics and continue unchanged.
