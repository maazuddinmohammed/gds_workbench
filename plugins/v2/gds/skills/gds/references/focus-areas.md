# Focus areas

Allow multiple selections, but execute one current task at a time.

## Metadata

Inspect or author only Change Set-eligible Metadata datasets from a fresh Metadata Snapshot. Use canonical keys and complete records. Preserve fields without evidence. Deactivation is explicit; omission never means deletion. Target Registration uses its own workflow target.

## Model

Use one Model per session. Route main development through `workflow-targets.md`. Profiles and Analysis are existing evidence; do not execute SQL. Assertion preparation is optional custom Model work. Never expose Model Scope mutation.

## Code

Only generate/regenerate target DDL or post-Apply Mapping artifacts, inspect/diff local output, and report staleness from embedded revision/digest. Default SQL is Databricks. Never execute, upload, or deploy generated code. General application code is outside GDS.

## Validation

Run local Metadata, Model, generated DDL/code, or session-readiness checks. Read the effective Snapshot-plus-pending graph. Return bounded issues in memory; do not create report files or mutate records. This cannot prove runtime/data correctness and cannot replace governed server Validate. A validation-only task ends as `done`.

## Ad Hoc

Use the read-only fast path for bounded inspection or explanation. If the request grows into mutation, stop, create a normal area task and plan, then enter the required gates.
