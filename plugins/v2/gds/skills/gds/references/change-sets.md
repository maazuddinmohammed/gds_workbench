# Local and governed Change Sets

Before writing a dataset, request its compact schema through `describe_metadata_dataset` or `describe_model_dataset`; offline, use local `describe`. Never author fields from memory.

- A missing file means no intent.
- A present array is the complete pending Change Set intent for that dataset, never a patch or a complete copy of the applied dataset.
- Omitted records remain unchanged. Deactivation requires a complete inactive record.
- Preserve nested members when editing a parent.
- Never edit Snapshot files or invent IDs.
- Metadata registration uses only a Metadata Change Set. Model Input Scope, Model Binding, models, Mapping, Code, and Validation use only a Model Change Set.

Local validation overlays pending records on the Snapshot, compiles the complete effective graph, writes the shared report, and computes the exact digest. The agent runs it before notifying the user. `review` is an optional action summary, not another user gate. A positive acknowledgement accepts that digest internally; edits invalidate it.

At Stage, fetch any existing draft and reconcile by normalized canonical key. Exact resumes; non-overlap can combine; differing overlap is a conflict. For Model work, a Model revision mismatch stops for a fresh Model Snapshot and reassessment. Metadata has no Tenant-wide revision and relies on a non-stale Snapshot, Tenant Lock, and server validation. Then read `staging.md` and use local `prepare-stage`; never calculate packing or hashes manually. Server Change Set validation seals the final draft revision, and Apply is separately approved.
