# Retrieve the next needed evidence

1. Resolve authorized identity and scope through [initialization](initialization.md). Retrieve current Model policies/templates when relevant, rather than treating examples as configured defaults.
2. For a focused server read, use the actual advertised schema. `inspect_metadata` and `read_model_section` cover selected datasets; respect returned bounds, cursor and revision semantics. A missing or truncated response is not proof of absence.
3. For local authoring, use [Metadata](../snapshots/metadata.md) / [Model](../snapshots/model.md) snapshots. Read manifest/catalog, relevant schema, then bounded selected records. Read the effective view when preserving pending edits, and the snapshot view when an applied prerequisite matters.
4. Retrieve the dependency neighborhood needed to explain or change those records. Resolve cross-owner physical keys completely. Keep a coverage account of selected, addressed, excluded and unresolved inputs; a sample cannot establish complete coverage.
5. For Mapping consumers, use the [complete Mapping view](../model/mapping-documents.md#complete-context-for-coding-and-validation). Code/Validation content comes from relevant Snapshot records. Load full code only for artifacts being examined or modified.
6. Retain concise findings and exact input bindings, not raw physical samples, raw tool envelopes, prompts, credentials, secret references or signed URLs. References should allow evidence to be retrieved again.

Use [local runtime](../local-runtime.md) for supported traversal commands. Refresh conflicts require reconciling base/current/proposed content. Known backend gaps are in [capabilities](../platform/capabilities.md).
