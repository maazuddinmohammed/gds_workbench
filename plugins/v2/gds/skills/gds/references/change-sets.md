# Local and governed Change Sets

Before writing a dataset, request its compact schema through `describe_metadata_dataset` or `describe_model_dataset`; offline, use local `describe`. Never author fields from memory.

- A missing file means no intent.
- A present array is the complete pending Change Set intent for that dataset, never a patch or a complete copy of the applied dataset.
- Omitted records remain unchanged. Deactivation requires a complete inactive record.
- Preserve nested members when editing a parent.
- Never edit Snapshot files or invent IDs.
- Metadata registration uses only a Metadata Change Set. Model Input Scope, Model Binding, models, Mapping, Code, and Validation use only a Model Change Set.

## Functional review before technical validation

Read the actual completed candidate against the effective graph (Snapshot plus pending records), not just the plan. For each retained result, check business meaning, grain, traceable inputs, and the active workflow's decisions. Distinguish measured evidence, documented/user evidence, supported inference, and unresolved claims. Schema validity does not establish business correctness.

Reconcile in both directions: every scoped input is represented, context-only, excluded with reason, or blocked; every output has a justified purpose and source support. Merge synonyms, split mixed grains, remove unsupported draft additions, and repair affected references. Omission never retires an applied record: explicitly deactivate superseded records only within the requested scope, with complete dependent changes and lock checks. Preserve locked/out-of-scope records; conflicting changes block handoff.

Read descriptions and `attribute_inferred_data_type` from fresh Metadata. Inferred meaning does not change STRING storage or dictate a target type; preserve identifier formatting, decimal precision, and date/time semantics. Reject placeholder prose, invented lineage, guessed precedence, and constant passing checks; never weaken validation to manufacture success.

Keep rationale in schema-supported definitions, basis, and nested support/source fields. Keep only concise sanitized coverage/decision notes in the task; never invent record fields or turn inference into an Assertion. Material uncertainty blocks the affected result; do not call partial coverage complete. After revisions, repeat the affected functional checks, then validate once. Tell the user the main decisions, unresolved limits, and whether evidence was queried; do not claim a business rule was tested from syntax or schema checks.

Local validation overlays pending records on the Snapshot, compiles the complete effective graph, writes the shared report, and computes the exact digest. The agent runs it before notifying the user. `review` is an optional action summary, not another user gate. A positive acknowledgement accepts that digest internally; edits invalidate it.

At Stage, the extension privately reads the draft and reconciles normalized keys: exact resumes, non-overlap combines, differing overlap conflicts. Model revision mismatch requires a fresh Snapshot/reassessment. Metadata uses a non-stale Snapshot, Tenant Lock, and server validation. Read `staging.md`; use `prepare-stage-request` plus `gds_stageApprovedManifest`. Server validation seals the revision; Apply is separately approved.
