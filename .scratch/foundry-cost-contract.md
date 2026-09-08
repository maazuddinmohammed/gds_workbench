# Cost estimate checkpoint plan

One production slice after durable token usage gates. No external model calls or
billing queries. User does not know deployment pricing; default is unpriced.

- Configure optional `GDS_WEB_FOUNDRY_PRICING_JSON`, keyed by registered model
  code; notebooks accept `GDS_NOTEBOOK_FOUNDRY_PRICING_JSON` through the existing
  shared configuration adapter. No new user Run controls.
- Per model: `basis` (1–80 plain label chars), required Decimal
  `input_usd_per_million`, `cached_input_usd_per_million`,
  `cache_write_input_usd_per_million`, `output_usd_per_million` (0–1,000,000,
  at most 8 decimal places), nullable timezone-aware `valid_from`, `valid_until`,
  nullable `max_input_tokens` (1–1e12). Null applicability means the administrator
  explicitly applies the configured rates without that restriction.
- Bound total configuration to 64 KiB, reject unknown model codes, extra fields,
  invalid decimals, inverted windows, and unsafe labels. Errors never echo input.
- Begin Run usage returns its frozen model code. Recorder chooses matching
  pricing from runtime connections using this server-derived code, then freezes
  the snapshot in each receipt before sending the HTTP request. Recovery can
  capture a new schedule without rewriting old receipts.
- SQL accepts a final optional pricing JSON argument on begin-request and
  normalizes/validates it into columns. Receipt guard freezes all pricing fields.
- Read aggregation calculates Decimal USD using immutable rates and usage:
  `(input*input_rate + cached*(cached_rate-input_rate)
    + cache_write*(cache_write_rate-input_rate) + output*output_rate) / 1e6`.
  Reasoning is already part of output. A missing cache count is immaterial only
  when its differential rate is zero (or input count is confirmed zero).
- Do not price missing core counts, pending receipts, unsupported token
  categories, expired/not-yet-valid schedules, excess context, or unconfigured
  requests. Return fixed reason counts, not raw provider details.
- `WorkflowTokenUsageSummary.cost_estimate`: status
  `unavailable|unpriced|partial|estimated`, currency `USD`,
  `amount` nullable decimal string, `priced_request_count`,
  `unpriced_request_count`, `pricing_bases` sorted distinct labels,
  `unpriced_reasons` fixed-key count dictionary. Reasons:
  `pricing_not_configured`, `outside_pricing_window`, `context_limit_exceeded`,
  `missing_usage`, `unsupported_token_types`.
- Legacy/history gaps remain explicit. Known tracked no-call totals produce
  estimated zero; history-gap no-call ledger gives unavailable amount. Partial
  sum includes priced requests only. Active state stays on token summary.
- Web existing shared usage component displays estimate and concise unknown
  reason; optional details explain basis and partial requests. Notebook returns
  the same nested summary on completion and replay. This estimates model tokens,
  not invoices, provisioned capacity, SQL/Databricks compute, or other services.

Owners: root config/contracts + numeric/read integration review; writer agent
SQL/recorder/assembly + DB write gates; reader agent read aggregation/notebook;
frontend agent existing usage presentation + tests. Finish as one checkpoint.
