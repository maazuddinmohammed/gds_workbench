# Retained agent verification limits

Completed September 5/21 implementation plans and superseded architecture
artifacts were removed on 2026-09-28. Current contracts belong in `CONTEXT.md`,
`docs/adr/`, workflow design documents, and executable tests. Historical passing
counts do not verify today's source.

- Synthetic provider responses, in-memory SDK transport, and disposable-database
  pipelines verify request delivery, protection, persistence, and replay. They do
  not establish live-model quality, provider context capacity, latency, or actual
  Databricks transformation results.
- Unsupported workflow modes remain unsupported; test coverage of supported
  modes is not evidence that every workflow supports both modes.
- No populated database or stored custom/published Prompt was migrated. Fresh
  install seeds and edited source do not update existing installations.
- Large unbounded input can increase memory/serialization work. Paging is not
  proof of streaming or a provider capacity guarantee. Explicit turn/retry,
  persisted-record, export, and SQL execution contracts remain separate limits.
- Windows PowerShell and native browser directory-picker checks require their
  actual environments. Automated JavaScript/DOM checks do not substitute for them.
- The September 21 enrichment audit recorded a source-description limitation:
  exact renamed Source Attribute lineage was not exposed through the default
  enrichment variables. Direct description propagation would require an explicit
  lineage contract, not guessed matching or stronger wording. This capability
  note has not been revalidated after later changes and is not an implementation
  request.

Latest results: [workflow verification](../workflow-verification-2026-09-28.md).
Open defect: [failure-stage attribution](issues/01-report-actual-failed-stage.md).
