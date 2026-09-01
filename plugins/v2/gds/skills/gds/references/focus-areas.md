# Focus areas

Allow multiple selections, but execute one current task at a time.

## Metadata

Inspect or author only Change Set-eligible Metadata datasets from a fresh Metadata Snapshot. Use canonical keys and complete records. Preserve fields without evidence. Deactivation is explicit; omission never means deletion. Target Registration uses its own workflow target.

## Model

Use one Model per session and route through `workflow-targets.md`. Prefer Snapshot evidence. Under
`essential` or `as_needed`, the existing governed SQL tool may collect combined bounded
evidence/profile results; `never` proceeds without them. Assertion preparation is optional.
Never expose Model Scope mutation.

## Code

Generate target-registration DDL locally or author applied-Mapping artifacts as complete
`generated_code` Model records. Default SQL is Databricks. Never execute, upload, or deploy
generated transformation code. General application code is outside GDS.

## QA

Author `validation_group` and `validation_check` Model records from applied Mapping, any current
relevant Code when present, and user rules. Scope is exact source System codes. QA Apply stores definitions;
later orchestration executes them.

## Validation

Run local Metadata, Model, generated DDL/code, or session-readiness checks. Read the effective Snapshot-plus-pending graph. Return bounded issues in memory; do not create report files or mutate records. This cannot prove runtime/data correctness and cannot replace governed server Validate. A validation-only task ends as `done`.

## Ad Hoc

Use the read-only fast path for bounded inspection or explanation. If the request grows into mutation, stop, create a normal area task and plan, then enter the required gates.
