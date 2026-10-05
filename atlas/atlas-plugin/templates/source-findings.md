# Source findings format

Use these fields in the existing task/report only when useful; do not create another status store.

- Scope: exact owner/Object identities and selected population/batches.
- Inputs: Snapshot/revision and profile time/scope bindings; applicable documents.
- Findings per Object: row meaning; candidate key tuple/namespace; relationship candidates; important business semantics.
- Evidence class: declared, inferred, measured or unknown; source and limitations.
- Coverage: addressed, explicitly excluded, unresolved and blocked inputs, with reasons.
- Next decision: what missing fact could change the model and which authorized action could resolve it.

Keep aggregate conclusions and references. Do not persist physical samples, raw tool envelopes, prompts, credentials or signed URLs. An empty result is not proof of absence when coverage was truncated.
