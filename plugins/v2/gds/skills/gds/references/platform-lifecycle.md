# Platform lifecycle and orchestration

A Tenant owns Systems for orchestration, not physical-key inference.
Connections locate physical Objects and Attributes in Source/Bronze/Silver/Gold.
Source → Bronze uses `ingestion_object_mapping`, `copy_group` and `copy`; the plugin authors metadata,
not ingestion. After Bronze, create a Model with authorized Model Scope. Profiling, Analysis, and Conceptual
are optional evidence for Logical; never fabricate unavailable data. Dimensional is optional
after applied Logical Mapping.

Logical → Silver Target Registration → scope activation → Logical Mapping → Code and/or QA. The
optional Dimensional branch uses Gold Registration, scope activation, Mapping, Code and/or QA.
Registration produces local DDL plus target Metadata. Mapping is the executable truth source for Code.
QA uses applied Mapping and current relevant Code when present; Code is optional.

Default GDS/Julius orchestration accepts one Tenant and selected Systems, with one active pipeline per
Tenant. Process has one row per System; several rows may reference the same target artifact, and the
runtime executes that artifact once. Distinct safe artifacts at one order run in parallel; lower orders finish first,
and any failure blocks later orders. External triggers control prerequisite Systems.

Databricks SQL may contain semicolon-separated statements and same-session temporary views; its final
statement returns the dataframe. Runtime merge uses the target natural key and Process metadata. An
upstream-target read is dependency evidence; a target self-read may inspect only prior state. Never
infer reruns or order from SQL. This guides generation, not orchestration code. For another runtime,
confirm dialect/artifact, session/final-result, merge/write, dependency/concurrency, and QA rules.
