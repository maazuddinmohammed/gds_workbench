# Server handoff

Load only after a positive acknowledgement of the exact local digest.

1. Check the Tenant Lock. The acknowledgement authorizes acquisition when the Tenant is unlocked. Another owner stops; override requires separate explicit authorization and a reason.
2. For Model work, re-read the authoritative Model revision. On mismatch, automatically create and install a fresh Model Snapshot, then reassess; never merge automatically. Metadata has no tenant-wide revision: require its local Snapshot to be non-stale and rely on this lock plus server validation.
3. Get or create the correct Metadata or Model Change Set. Never create a draft merely to inspect.
4. Reconcile its current pending datasets against the accepted local digest. Content/action changes require another notification and acknowledgement; byte-identical reassessment retains approval.
5. Read `staging.md`. Run local `prepare-stage` once with the exact server pending datasets, then execute its ordered `operations` exactly. Carry a returned revision only where the manifest directs it.
6. Validate the exact staged revision on the server. On `valid=false`, cache that active revision as failed before editing. Repair returned paths locally, revalidate, notify, and obtain acknowledgement for changed content. Then replace only this task's failed draft as described in `staging.md`; ordinary conflicts still stop.
7. Show authoritative `action_review` and ask separately for Apply approval.
8. Apply once, mark the area stale, release a lock acquired here, and stop.

Use the Metadata Change Set tools only for Metadata and the Model Change Set tools only for Model records. Archive only on an explicit request.
