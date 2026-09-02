# Local and governed Change Sets

Before writing a dataset, request its compact schema through `describe_metadata_dataset` or `describe_model_dataset`; offline, use local `describe`. Never author fields from memory.

- A missing file means no intent.
- A present array is the complete pending Change Set intent for that dataset, never a patch or a complete copy of the applied dataset.
- Omitted records remain unchanged. Deactivation requires a complete inactive record.
- Preserve nested members when editing a parent.
- Never edit Snapshot files or invent IDs.
- Metadata registration uses only a Metadata Change Set. Model Input Scope, Model Binding, models, Mapping, Code, and Validation use only a Model Change Set.

Local review overlays pending records on the Snapshot and computes the exact digest. The agent runs review and validation before notifying the user. A positive acknowledgement accepts that digest internally; edits invalidate it.

At Stage, fetch any existing draft and reconcile by normalized canonical key. Exact resumes; non-overlap can combine; differing overlap is a conflict. A revision mismatch stops for a fresh Snapshot and reassessment. Then read `staging.md` and use local `prepare-stage`; never calculate packing or hashes manually. Server Change Set validation seals the final revision, and Apply is separately approved.
