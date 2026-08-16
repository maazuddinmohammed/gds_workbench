# Data-modeling goal template

Replace every bracketed value before starting. Remove branches that do not apply.

```text
/goal Build and verify one governed [Conceptual|Logical|Dimensional|Model Mapping]
model for Tenant [tenant] and existing Model [model], covering [business scope].
Continue across checkpoints until [proposal|validated draft|applied model] satisfies
the stopping condition below, or pause with one precise blocker that requires my
decision, approval, access, or external authority.

Read first:
- every applicable AGENTS.md/project instruction;
- the current Model header/revision and naming templates from get_model;
- current Model Scope plus focused profiling, analysis, Modeling Assertion,
  Conceptual, Logical, Dimensional, mapping, and source records needed;
- the live describe_model_dataset schema for every dataset you may author; and
- existing project decision records and the relevant GDS modeling skill.

Objective and scope:
- Business outcome: [outcome]
- In scope: [domain/process/entities/facts/mappings]
- Out of scope: [explicit exclusions]
- Sources/evidence: [systems, natural-key Objects/Attributes, Assertions]
- Affected Model Change Set sections/datasets: [subset of all eight sections/19 datasets]
- Naming posture: [preserve|adopt|replace after preview and approval]
- Owner/steward: [owner]
- Acceptance checks: [observable business and technical checks]

Work in small checkpoints and keep a compact local progress/decision log:
1. Verify Tenant/Model, current revision, scope, naming, sources, and unresolved
   decisions. Inventory all eight Model Change Set sections and classify each relevant
   dataset current, proposed, not needed, or blocked. Do not invent a missing fact.
2. Draft the model using the matching GDS skill. Include required profiling evidence,
   analysis results, Modeling Assertions, and mappings. State exact grain,
   identifiers or facts/dimensions, history, lineage, and assumptions.
3. Build complete, ID-free records using live dataset schemas. Preview names,
   canonical-key effects, references, record counts, and local validation.
4. If the stopping boundary is proposal, produce the checked records/review and stop
   without acquiring a lock or writing to the server.
5. Otherwise, check the Tenant Lock, pause for approval, and acquire it. Re-read
   `get_model`; if its revision differs from the reviewed baseline, release the lock
   and rebase before creating or staging anything. When it still matches, create or
   resume the Model Change Set, inspect/reconcile every pending dataset, and pause for
   Stage approval.
6. Stage complete approved dataset replacements with the latest draft revision.
   Validate on the server; repair one failed phase at a time and revalidate.
7. If the stopping boundary is validated draft, hand off the authoritative action
   review, release the caller-owned Tenant Lock, and stop without Apply. Report any
   release failure as a blocker.
8. If the boundary is applied model, show the validated action review and pause for a
   fresh explicit Apply approval. Apply only that exact revision, then verify with
   fresh focused reads/DBML or Snapshot and release the lock.

Safety and exclusions:
- Use only advertised MCP names and argument schemas. There is no public Model-create,
  direct graph mutation, naming-template mutation, or mapping-write tool.
- Never expose credentials, temporary Snapshot URLs, connection values, raw prompts,
  raw physical rows, or unredacted tool dumps.
- Do not use arbitrary SQL, direct CRUD, external/Azure/Databricks writes, deployment,
  publishing, or policy changes.
- Preserve server-derived Principal/Tenant/Model authorization, Tenant Lock ownership,
  revision fences, candidate seals, redaction, and idempotency boundaries.
- Never replay an ambiguous non-idempotent call; inspect current state first.
- If this goal acquired the lock, release it before a terminal pause or abandonment
  when safe; report any release failure instead of silently leaving it held.

Stopping condition:
[Proposal: exact records and decisions are complete, locally schema-checked, reviewed,
and all required unknowns are resolved or owned.]
[Validated draft: the exact Model Change Set revision is server-valid and its
authoritative action review is handed off; nothing is Applied.]
[Applied model: that validated revision was explicitly approved, Applied once,
verified by fresh reads/artifact, and the lock was released.]

The goal is not complete with skipped or unknown required work. Pause and name the
smallest required decision when source access, grain/history/naming/ownership,
authorization, another lock owner, external-write approval, or acceptance evidence is
missing.
```

Codex goals are designed around one durable objective, one verifiable stopping
condition, explicit inputs, validation artifacts, checkpoints, and pause rules. The
host goal feature—not this skill—provides persistence.
