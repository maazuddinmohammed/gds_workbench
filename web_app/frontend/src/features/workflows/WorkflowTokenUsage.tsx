import type { WorkflowCostEstimate, WorkflowTokenUsage as TokenUsage } from "./api";

const COST_REASON_LABELS: Record<keyof WorkflowCostEstimate["unpriced_reasons"], string> = {
  pricing_not_configured: "Rates are not configured",
  outside_pricing_window: "Requests fall outside the pricing period",
  context_limit_exceeded: "Requests exceed the pricing context limit",
  missing_usage: "Required usage was not reported",
  unsupported_token_types: "Usage includes unsupported token categories",
};

export function WorkflowTokenUsage({ usage }: { usage: TokenUsage | undefined }) {
  const available = usage !== undefined && usage.status !== "unavailable";
  const status = usage?.status === "complete" ? "Complete"
    : usage?.status === "recording" ? "Recording so far"
      : usage?.status === "partial" ? "Partial" : "Unavailable";
  const cost = usage?.cost_estimate;
  const hasEstimate = (cost?.status === "estimated" || cost?.status === "partial")
    && cost.amount !== null;
  const reasons = cost ? (Object.keys(COST_REASON_LABELS) as Array<keyof typeof COST_REASON_LABELS>)
    .map((key) => ({ key, label: COST_REASON_LABELS[key], count: cost.unpriced_reasons[key] }))
    .filter(({ count }) => count > 0) : [];
  return (
    <section className="workflow-token-usage" aria-label="Token usage">
      <header><h3>Token usage</h3><span className={`status-badge ${usage?.status === "complete" ? "is-success" : usage?.status === "partial" ? "is-warning" : "is-neutral"}`}>{status}</span></header>
      {!available ? <p>Token usage was not recorded for this run.</p> : <>
        <dl className="workflow-token-totals">
          <div><dt>Input tokens</dt><dd>{tokenCount(usage.input_tokens)}</dd></div>
          <div><dt>Output tokens</dt><dd>{tokenCount(usage.output_tokens)}</dd></div>
          <div><dt>Total tokens</dt><dd>{tokenCount(usage.total_tokens)}</dd></div>
        </dl>
        <p>
          {usage.status === "complete" && usage.request_count === 0
            ? "No model requests were made."
            : `${usage.request_count.toLocaleString()} recorded model ${usage.request_count === 1 ? "request" : "requests"} across stages, tool turns and repairs.`}
          {usage.status === "recording" ? " Use Refresh to update." : ""}
        </p>
        {usage.status === "partial" || usage.status === "recording" ? <p>
          {usage.reported_request_count.toLocaleString()} of {usage.request_count.toLocaleString()} requests reported token usage.
          {usage.pending_request_count > 0 ? ` ${usage.pending_request_count.toLocaleString()} pending.` : ""}
          {usage.missing_usage_request_count > 0 ? ` ${usage.missing_usage_request_count.toLocaleString()} without usage.` : ""}
          {" Totals include reported usage only."}
        </p> : null}
        {usage.history_incomplete ? <p>Earlier requests may not be included.</p> : null}
        <details>
          <summary>Token breakdown</summary>
          <dl className="workflow-token-totals">
            <div><dt>Cached input</dt><dd>{tokenCount(usage.cached_input_tokens)}</dd></div>
            <div><dt>Cache-write input</dt><dd>{tokenCount(usage.cache_write_input_tokens)}</dd></div>
            <div><dt>Reasoning output</dt><dd>{tokenCount(usage.reasoning_output_tokens)}</dd></div>
          </dl>
          <p>Cache counts are included in input tokens; reasoning is included in output tokens. Unreported details remain unknown.</p>
        </details>
      </>}
      <section className="workflow-cost-estimate" aria-label="Estimated model token cost">
        <dl>
          <dt>Estimated model token cost</dt>
          <dd>{hasEstimate ? `USD ${cost.amount}` : cost?.status === "unpriced" ? "Unpriced" : "Not available"}</dd>
        </dl>
        {cost?.status === "partial" ? <p>
          Partial estimate; includes {cost.priced_request_count.toLocaleString()} priced {cost.priced_request_count === 1 ? "request" : "requests"} only.
          {usage?.history_incomplete ? " Earlier costs may be missing." : ""}
        </p> : null}
        {hasEstimate && usage?.status === "recording" ? <p>Estimate so far; this run is still recording usage.</p> : null}
        {cost?.status === "unpriced" ? <p>{reasons.length
          ? `${reasons.map(({ label }) => label).join("; ")}.`
          : "No matching pricing estimate is available."}</p> : null}
        <details>
          <summary>Pricing details</summary>
          {cost && cost.status !== "unavailable" ? <p>
            Recorded requests: {cost.priced_request_count.toLocaleString()} priced, {cost.unpriced_request_count.toLocaleString()} unpriced.
          </p> : <p>Pricing and usage evidence are unavailable.</p>}
          {cost?.pricing_bases.length ? <p>Pricing basis: {cost.pricing_bases.join("; ")}.</p> : null}
          {cost && reasons.length ? <ul>
            {reasons.map(({ key, label, count }) => <li key={key}>{label}: {count.toLocaleString()} {count === 1 ? "request" : "requests"}.</li>)}
          </ul> : null}
          <p>Estimate from configured rates, not an invoice. Excludes provisioned capacity, Databricks compute and other services.</p>
        </details>
      </section>
    </section>
  );
}

function tokenCount(value: number | null): string {
  return value === null ? "Not reported" : value.toLocaleString();
}
