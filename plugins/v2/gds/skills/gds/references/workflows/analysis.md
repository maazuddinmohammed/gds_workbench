# Analysis

Use physical metadata, Profiles, existing Analysis, and Assertions to investigate grain, keys, overlaps, relationships, and data-quality signals.

First enumerate plausible relationship candidates from names, descriptions, keys, value domains, Profiles, and Assertions across every scoped Object, including cross-System alignments. Then support, reject, or retain each candidate as inference. When SQL policy permits, use bounded join coverage, uniqueness, cardinality, and orphan checks; do not query unrelated pairs without a relationship signal.

Record evidence-backed findings, confidence, and supporting endpoints. A finding may be inference-only. Populate measured validation fields only from actual deterministic results; never partially populate a measured group or fabricate numbers.

Classify each selected input represented, context-only, excluded with reason, or blocked. Analysis advises later models; it does not silently create model structure.
