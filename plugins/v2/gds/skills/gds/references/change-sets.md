# Local and governed Change Sets

Before writing a dataset, request its compact schema through `describe_metadata_dataset` or `describe_model_dataset`; offline, use local `describe`. Never author fields from memory.

- A missing file means no intent.
- A present array is the complete pending Change Set intent for that dataset, never a patch or a complete copy of the applied dataset.
- Omitted records remain unchanged. Deactivation requires a complete inactive record.
- Preserve nested members when editing a parent.
- Never edit Snapshot files or invent IDs.
- Metadata registration uses only a Metadata Change Set. Model Input Scope, Model Binding, models, Mapping, Code, and Validation use only a Model Change Set.

## Functional review before technical validation

Review actual records against the effective graph (Snapshot plus pending records): business meaning, grain, lineage and workflow decisions. Distinguish measured, documented, inferred and unresolved evidence. Schema validity does not establish business correctness.

Reconcile in both directions: every scoped input is represented, context-only, excluded with reason, or blocked; every output has a justified purpose and source support. Merge synonyms, split mixed grains, remove unsupported draft additions, and repair affected references. Omission never retires an applied record: explicitly deactivate superseded records only within the requested scope, with complete dependent changes and lock checks. Preserve locked/out-of-scope records; conflicting changes block handoff.

Read descriptions/types from fresh Metadata. Inferred meaning does not dictate target capacity. Preserve identifier formatting and decimal/time semantics. Reject placeholder definitions, invented lineage/defaults and constant passing checks.

Keep rationale in existing definition/basis/support fields and sanitized task notes. Never invent fields or turn inference into an Assertion. Material uncertainty blocks the affected result. Repeat affected checks after edits; present actual decisions, coverage, limits and whether evidence was queried.

Local validation overlays pending records on the Snapshot, compiles the complete effective graph, writes the shared report, and computes the exact digest. The agent runs it before notifying the user. For affected Conceptual/Logical work it also generates a separate evidence report and decision scaffold; follow `modeling-quality.md`. `valid=true` is structural, and `evidence_present` confirms citations/completeness only; neither proves a good model. `review` is an optional action summary, not another user gate. A positive acknowledgement accepts that digest internally; edits invalidate it.

For handoff/reconciliation follow `server-handoff.md` and `staging.md`: `prepare-stage-request` plus `gds_stageApprovedManifest`. Server validation seals the revision; Apply is separately approved.
