# Platform lifecycle and orchestration intent

A Tenant owns Systems. Connections locate physical Objects and Attributes across Source, Bronze,
Silver, and Gold. Source → Bronze uses `ingestion_object_mapping`, `copy_group` and `copy`.
The plugin may author this metadata but never runs ingestion.

After Bronze registration, create one Model and obtain authorized Model Scope. Profiling, Analysis, and Conceptual are optional evidence enrichment before Logical; they improve rationale but never
replace physical coverage. Without live-data permission, use Snapshots and user evidence, report
gaps, and never fabricate results. Dimensional is optional after applied Logical Mapping.

The delivery chain is:

```text
Logical → Silver Target Registration → scope activation → Logical Mapping → Code and/or QA
Logical Mapping → optional Dimensional → Gold Registration → scope activation → Mapping → Code and/or QA
```

Target Registration produces local DDL and target Metadata. Mapping is the executable truth source for Code. QA uses applied Mapping and current relevant Code when present; Code is optional.
Preserve support, rationale, dependencies, and coverage so downstream artifacts explain why.

Default GDS/Julius orchestration takes one Tenant and selected Systems, with one active pipeline per
Tenant. Process has one row per System. Rows may reference the same target artifact; runtime executes
that artifact once. Distinct safe artifacts at one order parallelize, any failure blocks later orders,
and lower orders finish first. External triggers control prerequisite Systems. Do not invent triggers.

Databricks SQL may chain semicolon-separated statements and same-session temporary views; the final
statement returns the dataframe. Runtime merge uses the target natural key and Process metadata.
An upstream-target read is dependency evidence; a target self-read may only consult prior state.
Never infer a rerun or order from SQL alone. Generation context—not orchestration code. For another runtime, confirm dialect/artifact,
session/final-result, merge/write, dependency/concurrency, and QA-engine rules in each affected task plan.
