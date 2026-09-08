# Token usage UI checkpoint

2026-09-05. Frontend only; exact shared Run detail token_usage contract.

- Reused WorkflowTokenUsage in shared WorkflowRunMonitor and ProfilingRunDrawer.
- Three main totals; collapsed native details for included cached, cache-write and reasoning counts.
- Explicit unavailable, recording, partial and complete states; known zero requests distinct from unknown; incomplete history and report coverage visible.
- Existing selected Run read/Refresh only. No new query, polling, frontend aggregation or pricing.
- Tests cover complete totals, missing optional breakdowns, zero, legacy response, recording/pending, partial/history, failed Run usage, deterministic Analysis validation, selected Profiling Run and manual Refresh.
- Full frontend check: 244 tests, TypeScript and production build passed. Existing bundle-size advisory remains.
- Incomplete prior history with zero tracked receipts remains partial/unknown; request counts explicitly say recorded requests.
- Browser QA: synthetic production components, desktop and 390px iframe; collapsed/expanded token details, partial failure context and narrow numeric totals fit; Enter/Space toggles native details with visible focus.
- Temporary preview server stopped and browser tab closed. No external data or Databricks used.

Files: features/workflows/api.ts, WorkflowTokenUsage.tsx/.test.tsx, WorkflowRunMonitor.tsx/.test.tsx; features/profiling/ProfilingRuns.tsx, ProfilingScreen.test.tsx; features/metadata_enrichment/MetadataEnrichment.test.tsx (required field fixture only); styles/workflow-runs.css.

## Cost estimate UI checkpoint

Shared usage component now consumes required nested cost_estimate. Frontend
preserves the exact fixed-point amount string, displays USD and estimated scope,
and never calculates rates or substitutes zero for missing evidence. Missing
pricing/usage/window/context/category coverage has bounded named explanations.
Partial and recording estimates are qualified; history gaps remain explicit.
Pricing details are a native collapsed disclosure with bases and request counts.
No new Run options, billing queries, configuration UI or periodic Refresh.

Verification: 253 frontend tests, TypeScript and production build pass; diff check
clean. Unit cases cover exact precision, true zero, all five unpriced reasons,
partial/history/recording, and older unavailable responses. Integration verifies
manual Refresh updates cost in shared Run monitor and Profiling drawer, failed
Run retains partial cost, deterministic Analysis validation shows known zero.
Desktop + 390px browser checks: amount and expanded pricing fit, missing rates
remain unpriced, Enter/Space operate native details. Synthetic preview stopped
and browser closed. No external data or model call.
