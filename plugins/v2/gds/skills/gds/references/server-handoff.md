# Server handoff

Load only after a positive acknowledgement of the exact local digest.

1. Re-read authoritative Model revision or Metadata state. A mismatch stops: request a fresh Snapshot and reassess; never merge automatically.
2. Check the Tenant Lock. The acknowledgement authorizes acquisition when the Tenant is unlocked. Another owner stops; override requires separate explicit authorization and a reason.
3. Get or create the correct Metadata or Model Change Set. Never create a draft merely to inspect.
4. Reconcile its current pending datasets against the accepted local digest. Content/action changes require another user review; byte-identical reassessment retains approval.
5. Use one direct Stage for all affected complete datasets when within limits. Otherwise commit one batch per oversized dataset and pass each returned draft revision into the next batch.
6. Validate the exact staged revision on the server. Repair returned paths locally and repeat from review if content changes.
7. Show authoritative `action_review` and ask separately for Apply approval.
8. Apply once, mark the area stale, release a lock acquired here, and stop.

Use the Metadata Change Set tools only for Metadata and the Model Change Set tools only for Model records. Archive only on an explicit request.
