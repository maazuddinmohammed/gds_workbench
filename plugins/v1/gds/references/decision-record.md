# Data-modeling decision record

Prefer the project's existing ADR or decision-log format. If none exists, ask before
creating a local record and suggest `.scratch/data-modeling/decisions.md`. Keep the
record concise and free of raw prompts, credentials, temporary URLs, physical row
samples, and unredacted tool output.

```markdown
## DM-YYYYMMDD-NN — <decision title>

- Status: proposed | accepted | superseded | blocked
- Scope: <Tenant code, Model name, layer, business process/domain>
- Owner: <business/technical decision owner or unknown>
- Decision: <one precise sentence>
- Why now: <question this resolves>
- Evidence: <named requirement, source Object/Attribute natural key, profiling result,
  Modeling Assertion key, or current Model record>
- Options considered: <short alternatives and tradeoffs>
- Consequences: <model, mapping, history, naming, or delivery effects>
- Assumptions/open issues: <explicit unknowns>
- Acceptance check: <observable proof>
- Revisit when: <trigger that invalidates the decision>
```

During a bounded interview, update the record after each answered branch instead of
asking the same question again. Distinguish accepted user decisions from agent
recommendations and inferred evidence. At the stopping point, summarize accepted
decisions, assumptions, open issues, and the next safe action.
