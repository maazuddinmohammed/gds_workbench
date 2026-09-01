# Dimensional Build

Require applied active Logical Mapping and fresh Snapshots. Eligible sources are active scoped Silver
with `is_dimensional_source_eligible=true`; that flag requires an active applied Logical Mapping contribution.
Never treat every Silver Object as eligible. Dimensional is optional. Ask for Build
mode and Full/Selected process scope.

Before writing, load each selected Model output dataset contract.

For each selected process:

1. Declare the fact grain before measures.
2. Identify facts, dimensions, bridges, and conformed dimensions from Silver contributions and supporting evidence.
3. Define measure aggregation behavior, dimension keys, history behavior, and role-playing use explicitly.
4. Use profiles, Analysis, Conceptual results, and Assertions as context.
5. Require active applied Logical Mapping lineage back to Silver; never source Gold directly from unmodeled physical inputs.
6. Relationships require `dimensional_relationship_is_optional`. For Fact/Bridge-to-Dimension, `true`: projected foreign key may be null; `false` requires non-null. Never infer optionality from cardinality; explain evidence in relationship basis.
7. Mark covered, excluded with reason, or blocked. Do not guess unresolved grain, conformance, history, optionality, or measures.

Build one local Model Change Set, review, accept, Stage, server Validate, Apply once, mark Model stale, and stop.
