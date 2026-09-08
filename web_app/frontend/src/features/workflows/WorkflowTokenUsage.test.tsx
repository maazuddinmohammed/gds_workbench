import { render, screen, within } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { describe, expect, it } from "vitest";

import type { WorkflowCostEstimate, WorkflowTokenUsage as Usage } from "./api";
import { WorkflowTokenUsage } from "./WorkflowTokenUsage";

const complete: Usage = {
  status: "complete", request_count: 3, reported_request_count: 3,
  pending_request_count: 0, missing_usage_request_count: 0,
  input_tokens: 12_000, output_tokens: 800, total_tokens: 12_800,
  cached_input_tokens: 4_000, cache_write_input_tokens: 500, reasoning_output_tokens: 300,
  cost_estimate: { status: "unavailable", currency: "USD", amount: null,
    priced_request_count: 0, unpriced_request_count: 0, pricing_bases: [],
    unpriced_reasons: { pricing_not_configured: 0, outside_pricing_window: 0,
      context_limit_exceeded: 0, missing_usage: 0, unsupported_token_types: 0 } },
  history_incomplete: false,
};

const estimate: WorkflowCostEstimate = {
  ...complete.cost_estimate, status: "estimated", amount: "0.1234567890123400",
  priced_request_count: 3, pricing_bases: ["Configured September rates"],
};

describe("Workflow token usage", () => {
  it("preserves the backend decimal estimate and keeps pricing evidence collapsed", async () => {
    const user = userEvent.setup();
    render(<WorkflowTokenUsage usage={{ ...complete, cost_estimate: estimate }} />);
    const cost = screen.getByRole("region", { name: "Estimated model token cost" });
    expect(within(cost).getByText("USD 0.1234567890123400")).toBeVisible();
    expect(within(cost).getByText(/Configured September rates/)).not.toBeVisible();
    await user.click(within(cost).getByText("Pricing details"));
    expect(cost).toHaveTextContent("Recorded requests: 3 priced, 0 unpriced.");
    expect(within(cost).getByText("Pricing basis: Configured September rates.")).toBeVisible();
    expect(within(cost).getByText(/not an invoice/)).toBeVisible();
    expect(cost).toHaveTextContent("Excludes provisioned capacity, Databricks compute and other services.");
  });

  it("shows a backend-confirmed zero estimate for a no-call run", () => {
    render(<WorkflowTokenUsage usage={{ ...complete, request_count: 0, reported_request_count: 0,
      input_tokens: 0, output_tokens: 0, total_tokens: 0,
      cost_estimate: { ...estimate, amount: "0", priced_request_count: 0, pricing_bases: [] } }} />);
    expect(screen.getByText("USD 0")).toBeVisible();
    expect(screen.getByText("No model requests were made.")).toBeVisible();
  });

  it.each([
    ["pricing_not_configured", "Rates are not configured"],
    ["outside_pricing_window", "Requests fall outside the pricing period"],
    ["context_limit_exceeded", "Requests exceed the pricing context limit"],
    ["missing_usage", "Required usage was not reported"],
    ["unsupported_token_types", "Usage includes unsupported token categories"],
  ] as const)("explains unpriced requests for %s without inventing an amount", async (reason, label) => {
    const user = userEvent.setup();
    render(<WorkflowTokenUsage usage={{ ...complete, cost_estimate: {
      ...complete.cost_estimate, status: "unpriced", unpriced_request_count: 3,
      unpriced_reasons: { ...complete.cost_estimate.unpriced_reasons, [reason]: 3 },
    } }} />);
    const cost = screen.getByRole("region", { name: "Estimated model token cost" });
    expect(within(cost).getByText("Unpriced")).toBeVisible();
    expect(within(cost).getByText(`${label}.`)).toBeVisible();
    expect(within(cost).queryByText(/^USD /)).not.toBeInTheDocument();
    await user.click(within(cost).getByText("Pricing details"));
    expect(within(cost).getByText(`${label}: 3 requests.`)).toBeVisible();
  });

  it("qualifies partial observed cost during recording and incomplete history", async () => {
    const user = userEvent.setup();
    render(<WorkflowTokenUsage usage={{ ...complete, status: "recording", request_count: 4,
      history_incomplete: true, cost_estimate: { ...estimate, status: "partial",
        unpriced_request_count: 1, unpriced_reasons: { ...estimate.unpriced_reasons, missing_usage: 1 },
        pricing_bases: ["Earlier configured rates", "Updated configured rates"],
      } }} />);
    const cost = screen.getByRole("region", { name: "Estimated model token cost" });
    expect(cost).toHaveTextContent("Partial estimate; includes 3 priced requests only. Earlier costs may be missing.");
    expect(within(cost).getByText("Estimate so far; this run is still recording usage.")).toBeVisible();
    await user.click(within(cost).getByText("Pricing details"));
    expect(cost).toHaveTextContent("Recorded requests: 3 priced, 1 unpriced.");
    expect(cost).toHaveTextContent("Earlier configured rates; Updated configured rates");
  });

  it("keeps absent pricing unavailable for older usage responses", () => {
    const { cost_estimate: _cost, ...olderUsage } = complete;
    render(<WorkflowTokenUsage usage={olderUsage as Usage} />);
    const cost = screen.getByRole("region", { name: "Estimated model token cost" });
    expect(within(cost).getByText("Not available")).toBeVisible();
    expect(within(cost).queryByText(/^USD /)).not.toBeInTheDocument();
  });

  it("shows exact reported totals and keeps the included token breakdown collapsed", async () => {
    const user = userEvent.setup();
    render(<WorkflowTokenUsage usage={complete} />);
    const summary = screen.getByRole("region", { name: "Token usage" });
    expect(summary).toHaveTextContent("Complete");
    expect(within(summary).getByText((12_000).toLocaleString())).toBeVisible();
    expect(within(summary).getByText("800")).toBeVisible();
    expect(within(summary).getByText((12_800).toLocaleString())).toBeVisible();
    expect(summary).toHaveTextContent("3 recorded model requests across stages, tool turns and repairs.");
    expect(within(summary).getByText("Cached input")).not.toBeVisible();
    await user.click(within(summary).getByText("Token breakdown"));
    expect(within(summary).getByText((4_000).toLocaleString())).toBeVisible();
    expect(within(summary).getByText("500")).toBeVisible();
    expect(within(summary).getByText("300")).toBeVisible();
    expect(summary).toHaveTextContent("Cache counts are included in input tokens; reasoning is included in output tokens.");
  });

  it("distinguishes known zero requests from missing reporting", () => {
    render(<WorkflowTokenUsage usage={{ ...complete, request_count: 0, reported_request_count: 0,
      input_tokens: 0, output_tokens: 0, total_tokens: 0,
      cached_input_tokens: 0, cache_write_input_tokens: 0, reasoning_output_tokens: 0 }} />);
    expect(screen.getByText("No model requests were made.")).toBeVisible();
    expect(screen.getByText("Complete")).toBeVisible();
    expect(screen.getAllByText("0").filter((item) => item.closest("details") === null)).toHaveLength(3);
    expect(screen.queryByText("Not reported")).not.toBeInTheDocument();
  });

  it.each(["legacy", "older response"])("does not invent zero usage for %s", (kind) => {
    render(<WorkflowTokenUsage usage={kind === "older response" ? undefined : {
      ...complete, status: "unavailable", request_count: 0, reported_request_count: 0,
      input_tokens: null, output_tokens: null, total_tokens: null,
      cached_input_tokens: null, cache_write_input_tokens: null, reasoning_output_tokens: null,
    }} />);
    expect(screen.getByText("Unavailable")).toBeVisible();
    expect(screen.getByText("Token usage was not recorded for this run.")).toBeVisible();
    expect(screen.queryByText("0")).not.toBeInTheDocument();
    expect(screen.queryByText("Token breakdown")).not.toBeInTheDocument();
  });

  it("qualifies recording totals and describes pending requests without polling", () => {
    render(<WorkflowTokenUsage usage={{ ...complete, status: "recording",
      request_count: 4, pending_request_count: 1,
      cached_input_tokens: null, cache_write_input_tokens: null, reasoning_output_tokens: null }} />);
    expect(screen.getByText("Recording so far")).toBeVisible();
    expect(screen.getByText(/Use Refresh to update/)).toBeVisible();
    expect(screen.getByText(/3 of 4 requests reported token usage. 1 pending. Totals include reported usage only/)).toBeVisible();
  });

  it("explains partial totals, missing reports and incomplete earlier history", () => {
    render(<WorkflowTokenUsage usage={{ ...complete, status: "partial",
      request_count: 5, pending_request_count: 1, missing_usage_request_count: 1,
      cached_input_tokens: null, cache_write_input_tokens: null, reasoning_output_tokens: null,
      history_incomplete: true }} />);
    expect(screen.getByText("Partial")).toBeVisible();
    expect(screen.getByText(/3 of 5 requests reported token usage. 1 pending. 1 without usage/)).toBeVisible();
    expect(screen.getByText("Earlier requests may not be included.")).toBeVisible();
    expect(screen.getByText((12_800).toLocaleString())).toBeVisible();
  });

  it("keeps absent optional breakdowns unknown even with complete main totals", async () => {
    const user = userEvent.setup();
    render(<WorkflowTokenUsage usage={{ ...complete,
      cached_input_tokens: null, cache_write_input_tokens: null, reasoning_output_tokens: null }} />);
    expect(screen.getByText("Complete")).toBeVisible();
    await user.click(screen.getByText("Token breakdown"));
    expect(screen.getAllByText("Not reported")).toHaveLength(3);
    for (const unknown of screen.getAllByText("Not reported")) expect(unknown).toBeVisible();
    expect(screen.queryByText("0")).not.toBeInTheDocument();
  });

  it("does not substitute zero when no pending request has reported core counts", () => {
    render(<WorkflowTokenUsage usage={{ ...complete, status: "recording",
      request_count: 1, reported_request_count: 0, pending_request_count: 1,
      input_tokens: null, output_tokens: null, total_tokens: null,
      cached_input_tokens: null, cache_write_input_tokens: null, reasoning_output_tokens: null }} />);
    expect(screen.getAllByText("Not reported").filter((item) => item.closest("details") === null)).toHaveLength(3);
    expect(screen.queryByText("0")).not.toBeInTheDocument();
  });

  it("does not claim zero model usage when earlier history is incomplete", () => {
    render(<WorkflowTokenUsage usage={{ ...complete, status: "partial", history_incomplete: true,
      request_count: 0, reported_request_count: 0,
      input_tokens: null, output_tokens: null, total_tokens: null,
      cached_input_tokens: null, cache_write_input_tokens: null, reasoning_output_tokens: null }} />);
    expect(screen.getByText("Earlier requests may not be included.")).toBeVisible();
    expect(screen.getByText("0 recorded model requests across stages, tool turns and repairs.")).toBeVisible();
    expect(screen.getAllByText("Not reported").filter((item) => item.closest("details") === null)).toHaveLength(3);
    expect(screen.queryByText("No model requests were made.")).not.toBeInTheDocument();
  });
});
