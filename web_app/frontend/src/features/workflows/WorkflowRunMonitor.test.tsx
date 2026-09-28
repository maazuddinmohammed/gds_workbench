import { QueryClient, QueryClientProvider, useQuery } from "@tanstack/react-query";
import { render, screen, waitFor, within } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { describe, expect, it, vi } from "vitest";

import { ApiError } from "../../core/http";
import type { ModelsApi } from "../models/api";
import type {
  WorkflowDraftReview,
  WorkflowRunDetail,
  WorkflowRunEvent,
  WorkflowRunMonitorApi,
} from "./api";
import { WorkflowRunMonitor } from "./WorkflowRunMonitor";

describe("Workflow Run monitor", () => {
  it("does not treat frozen Mapping pair selection ordinals as execution progress", async () => {
    const api = monitorApi();
    const run = partialMappingRun();
    api.readWorkflowRun.mockResolvedValue(run);
    api.listWorkflowRuns.mockResolvedValue({ items: [run], next_cursor: null });
    const ordinals = [3, 1, 4, 2];
    api.listWorkflowRunEvents.mockResolvedValue({
      items: ["mapping.pair_completed", "mapping.pair_preserved", "mapping.pair_no_source", "mapping.pair_failed"]
        .map((stage, index) => progressEvent({ stage, sequence: index + 1,
          current: ordinals[index]!, total: 4, message: `Pair outcome ${index + 1}` })),
      next_after_sequence: 4,
    });
    renderMonitor(api, vi.fn(async () => undefined), "mapping");
    expect(await screen.findByText("Pair outcome 4")).toBeVisible();
    expect(screen.queryByRole("progressbar")).not.toBeInTheDocument();
    expect(screen.getByText("3 of 4")).toBeVisible();
    expect(screen.getByText("1 of 4")).toBeVisible();
  });

  it.each(["completed", "completed_with_repair"] as const)(
    "applies only the validated successful Mapping draft when a %s run has failed pairs",
    async (state) => {
      const api = monitorApi();
      const user = userEvent.setup();
      const onApplied = vi.fn(async () => undefined);
      const run = { ...partialMappingRun(), workflow_run_state: state };
      api.readWorkflowRun.mockResolvedValue(run);
      api.listWorkflowRuns.mockResolvedValue({ items: [run], next_cursor: null });
      renderMonitor(api, onApplied, "mapping");

      const outcome = await screen.findByRole("region", { name: "Mapping pair outcomes" });
      expect(outcome).toHaveTextContent("1 generated · 1 failed");
      const failures = within(outcome).getByRole("table", { name: "Failed Mapping pairs" });
      expect(within(failures).getAllByRole("columnheader").map((cell) => cell.textContent))
        .toEqual(["System", "Schema", "Entity", "Issue"]);
      expect(failures).toHaveTextContent("ERP");
      expect(failures).toHaveTextContent("silver");
      expect(failures).toHaveTextContent("Order");
      expect(failures).toHaveTextContent("OrderDate requires a transformation rule.");
      expect(screen.getAllByText("Partial results").every((badge) => badge.classList.contains("is-warning"))).toBe(true);
      expect(api.applyWorkflowDraft).not.toHaveBeenCalled();
      await user.click(await screen.findByRole("button", { name: "Apply successful mappings" }));
      const dialog = await screen.findByRole("dialog", { name: "Apply successful mappings?" });
      expect(dialog).toHaveTextContent("1 failed pair remains unchanged.");
      expect(api.applyWorkflowDraft).not.toHaveBeenCalled();

      api.readWorkflowRun.mockResolvedValue({ ...run, model_change_set_status: "applied" });
      await user.click(within(dialog).getByRole("button", { name: "Apply exact draft" }));
      await waitFor(() => expect(api.applyWorkflowDraft).toHaveBeenCalledWith(
        7, 18, 1048, 5, 2, "d".repeat(64), expect.any(String),
      ));
      await waitFor(() => expect(onApplied).toHaveBeenCalledOnce());
      const compact = await screen.findByLabelText("Latest Mapping run");
      expect(compact).toHaveTextContent("Partial results");
      expect(compact).toHaveTextContent("Draft applied");
      await user.click(screen.getByRole("button", { name: "Show Mapping run activity" }));
      expect(await screen.findByText("Successful mappings applied. Failed pairs remain unchanged.")).toBeVisible();
      expect(screen.queryByRole("button", { name: "Apply successful mappings" })).not.toBeInTheDocument();
    },
  );

  it("shows all-failed Mapping pairs without offering Apply and discloses bounded failures", async () => {
    const api = monitorApi();
    const run: WorkflowRunDetail = { ...partialMappingRun(), workflow_run_state: "failed",
      mapping_outcome: { completed_pair_count: 0, preserved_pair_count: 0, no_source_pair_count: 0, failed_pair_count: 201 },
      mapping_failures_truncated: true, model_change_set_id: null, model_change_set_status: null,
      draft_revision: null, candidate_digest: null, validated_at: null };
    api.readWorkflowRun.mockResolvedValue(run);
    api.listWorkflowRuns.mockResolvedValue({ items: [run], next_cursor: null });
    renderMonitor(api, vi.fn(async () => undefined), "mapping");
    const outcome = await screen.findByRole("region", { name: "Mapping pair outcomes" });
    expect(outcome).toHaveTextContent("0 generated · 201 failed");
    expect(outcome).toHaveTextContent("Showing 1 of 201 failed pairs. The summary includes all failures.");
    expect(outcome).toHaveTextContent("No successful draft is available.");
    expect(screen.queryByText("Partial results")).not.toBeInTheDocument();
    expect(screen.queryByRole("button", { name: /Apply/ })).not.toBeInTheDocument();
    expect(api.readWorkflowDraftReview).not.toHaveBeenCalled();
  });

  it.each(["stale", "expired"])("blocks partial Mapping Apply when its draft review is %s", async (condition) => {
    const api = monitorApi({ staleReview: condition === "stale", expiredReview: condition === "expired" });
    const run = partialMappingRun();
    api.readWorkflowRun.mockResolvedValue(run);
    api.listWorkflowRuns.mockResolvedValue({ items: [run], next_cursor: null });
    renderMonitor(api, vi.fn(async () => undefined), "mapping");
    await screen.findByRole("region", { name: "Mapping pair outcomes" });
    await screen.findByText(condition === "expired"
      ? "This validated draft has expired. Apply is disabled."
      : "The authoritative draft review is unavailable or no longer matches this Run. Apply is disabled.");
    expect(screen.queryByRole("button", { name: "Apply successful mappings" })).not.toBeInTheDocument();
    expect(api.applyWorkflowDraft).not.toHaveBeenCalled();
  });

  it("requires the Tenant Lock before applying successful Mapping pairs", async () => {
    const api = monitorApi();
    const run = partialMappingRun();
    api.readWorkflowRun.mockResolvedValue(run);
    api.listWorkflowRuns.mockResolvedValue({ items: [run], next_cursor: null });
    renderMonitor(api, vi.fn(async () => undefined), "mapping", 1048, undefined, false);
    expect(await screen.findByRole("button", { name: "Apply successful mappings" })).toBeDisabled();
    expect(screen.getByTitle("Owned Tenant Lock required")).toBeVisible();
    expect(api.applyWorkflowDraft).not.toHaveBeenCalled();
  });

  it.each(["queued", "running"] as const)("keeps a %s Mapping run in progress after a pair fails", async (state) => {
    const api = monitorApi();
    const run: WorkflowRunDetail = { ...partialMappingRun(), workflow_run_state: state,
      model_change_set_id: null, model_change_set_status: null, draft_revision: null,
      candidate_digest: null, validated_at: null };
    api.readWorkflowRun.mockResolvedValue(run);
    api.listWorkflowRuns.mockResolvedValue({ items: [run], next_cursor: null });
    renderMonitor(api, vi.fn(async () => undefined), "mapping");
    const outcome = await screen.findByRole("region", { name: "Mapping pair outcomes" });
    expect(outcome).toHaveTextContent("Mapping generation is underway");
    expect(outcome).toHaveTextContent("Generation continues for the remaining pairs.");
    expect(outcome).not.toHaveTextContent("No successful draft is available.");
    expect(screen.queryByText("Partial results")).not.toBeInTheDocument();
    expect(screen.queryByRole("button", { name: "Apply successful mappings" })).not.toBeInTheDocument();
  });

  it("updates recording token usage with the existing manual Refresh", async () => {
    const api = monitorApi();
    const user = userEvent.setup();
    const running: WorkflowRunDetail = { ...workflowRun(false), workflow_run_state: "running",
      model_change_set_id: null, model_change_set_status: null,
      token_usage: { status: "recording", request_count: 2, reported_request_count: 1,
        pending_request_count: 1, missing_usage_request_count: 0,
        input_tokens: 900, output_tokens: 100, total_tokens: 1_000,
        cached_input_tokens: null, cache_write_input_tokens: null, reasoning_output_tokens: null,
        cost_estimate: { status: "unavailable", currency: "USD", amount: null,
          priced_request_count: 0, unpriced_request_count: 0, pricing_bases: [],
          unpriced_reasons: { pricing_not_configured: 0, outside_pricing_window: 0,
            context_limit_exceeded: 0, missing_usage: 0, unsupported_token_types: 0 } },
        history_incomplete: false } };
    api.readWorkflowRun.mockResolvedValue(running);
    renderMonitor(api, vi.fn(async () => undefined));
    const usage = await screen.findByRole("region", { name: "Token usage" });
    expect(usage).toHaveTextContent("Recording so far");
    expect(usage).toHaveTextContent("1 of 2 requests reported token usage. 1 pending.");
    expect(within(usage).getByRole("region", { name: "Estimated model token cost" })).toHaveTextContent("Not available");
    expect(api.readWorkflowRun).toHaveBeenCalledTimes(1);

    api.readWorkflowRun.mockResolvedValue({ ...running, workflow_run_state: "completed",
      token_usage: { ...running.token_usage, status: "complete", reported_request_count: 2,
        pending_request_count: 0, input_tokens: 1_200, output_tokens: 300, total_tokens: 1_500,
        cost_estimate: { ...running.token_usage.cost_estimate, status: "estimated", amount: "0.018",
          priced_request_count: 2, pricing_bases: ["Configured rates"] } } });
    await user.click(screen.getByRole("button", { name: "Refresh runs" }));
    await waitFor(() => expect(usage).toHaveTextContent("Complete"));
    expect(within(usage).getByText((1_500).toLocaleString())).toBeVisible();
    expect(usage).not.toHaveTextContent("1 pending");
    expect(within(usage).getByText("USD 0.018")).toBeVisible();
    expect(api.readWorkflowRun).toHaveBeenCalledTimes(2);
  });

  it("shows recorded zero model usage for deterministic Analysis validation", async () => {
    const api = monitorApi({ deterministic: true });
    const run = workflowRun(true);
    api.readWorkflowRun.mockResolvedValue({ ...run, token_usage: {
      ...run.token_usage, status: "complete", input_tokens: 0, output_tokens: 0, total_tokens: 0,
      cached_input_tokens: 0, cache_write_input_tokens: 0, reasoning_output_tokens: 0,
      cost_estimate: { ...run.token_usage.cost_estimate, status: "estimated", amount: "0" },
    } });
    renderMonitor(api, vi.fn(async () => undefined), "analysis");
    const usage = await screen.findByRole("region", { name: "Token usage" });
    expect(usage).toHaveTextContent("No model requests were made.");
    expect(within(usage).getByText("USD 0")).toBeVisible();
    expect(within(usage).getAllByText("0").filter((item) => item.closest("details") === null)).toHaveLength(3);
    expect(screen.queryByRole("button", { name: "Apply validated draft" })).not.toBeInTheDocument();
  });

  it("retains failed draft diagnostics and loads exact generated records only when requested", async () => {
    const api = monitorApi();
    const user = userEvent.setup();
    const run: WorkflowRunDetail = { ...workflowRun(false), workflow_run_state: "failed",
      model_change_set_status: "active", candidate_digest: null, validated_at: null,
      failure_code: "workflow_change_set_validation_failed", failure_message: "Draft needs corrections." };
    const review = failedDraftReview();
    api.readWorkflowRun.mockResolvedValue(run);
    api.readWorkflowDraftReview.mockImplementation(async (_tenant, _model, _id, dataset) => ({
      ...review, dataset: dataset ?? null,
      records: dataset ? [{ conceptual_object_name: "Customer", conceptual_object_definition: "A customer account." },
        { conceptual_object_name: "Purchase", conceptual_object_definition: "An order placed by a customer." }] : null,
    }));
    renderMonitor(api, vi.fn(async () => undefined));
    expect(await screen.findByRole("table", { name: "Validation error groups" })).toHaveTextContent("active dependency invalid");
    expect(screen.getByText(/2 generated records retained/)).toBeVisible();
    expect(screen.getByText(/Group counts include all validation errors/)).toBeVisible();
    expect(screen.queryByRole("button", { name: "Apply validated draft" })).not.toBeInTheDocument();
    expect(api.readWorkflowDraftReview).toHaveBeenCalledTimes(1);
    await user.click(screen.getByRole("button", { name: "Inspect conceptual object record 2" }));
    const record = await screen.findByRole("article", { name: "Generated conceptual object record 2" });
    expect(record).toHaveTextContent("An order placed by a customer.");
    expect(api.readWorkflowDraftReview).toHaveBeenLastCalledWith(7, 18, run.model_change_set_id, "conceptual_object");
    await user.click(screen.getByRole("button", { name: "Previous record" }));
    expect(screen.getByRole("article", { name: "Generated conceptual object record 1" })).toHaveTextContent("A customer account.");
    expect(api.applyWorkflowDraft).not.toHaveBeenCalled();
    await user.click(screen.getByRole("button", { name: "Refresh runs" }));
    await waitFor(() => expect(api.readWorkflowDraftReview).toHaveBeenCalledTimes(4));
  });

  it.each(["wrong revision", "wrong model", "expired", "unavailable"])(
    "hides retained records when their response is %s", async (reason) => {
      const api = monitorApi();
      const user = userEvent.setup();
      api.readWorkflowRun.mockResolvedValue({ ...workflowRun(false), workflow_run_state: "failed",
        model_change_set_status: "active", candidate_digest: null, validated_at: null });
      const review = failedDraftReview();
      api.readWorkflowDraftReview.mockImplementation(async (_tenant, _model, _id, dataset) => {
        if (!dataset) return review;
        if (reason === "unavailable") throw new Error("Unavailable");
        return { ...review, dataset, records: [{ conceptual_object_definition: "Stale content must be hidden." }],
          ...(reason === "wrong revision" ? { draft_revision: 99 } : {}),
          ...(reason === "wrong model" ? { model_id: 99 } : {}),
          ...(reason === "expired" ? { expires_at: "2020-01-01T00:00:00Z" } : {}),
        };
      });
      renderMonitor(api, vi.fn(async () => undefined));
      await user.selectOptions(await screen.findByLabelText("Inspect generated dataset"), "conceptual_object");
      expect(await screen.findByText(/Generated records could not be loaded or the draft changed/)).toBeVisible();
      expect(screen.queryByText("Stale content must be hidden.")).not.toBeInTheDocument();
      expect(screen.queryByRole("button", { name: "Apply validated draft" })).not.toBeInTheDocument();
    },
  );

  it("keeps failed-draft controls unavailable when summary loading fails", async () => {
    const api = monitorApi();
    api.readWorkflowRun.mockResolvedValue({ ...workflowRun(false), workflow_run_state: "failed",
      model_change_set_status: "active", candidate_digest: null, validated_at: null });
    api.readWorkflowDraftReview.mockRejectedValue(new Error("Unavailable"));
    renderMonitor(api, vi.fn(async () => undefined));
    expect(await screen.findByText(/The retained draft is unavailable or changed/)).toBeVisible();
    expect(screen.queryByLabelText("Inspect generated dataset")).not.toBeInTheDocument();
    expect(screen.queryByRole("button", { name: "Apply validated draft" })).not.toBeInTheDocument();
  });

  it("keeps recent-run status and Refresh available in a compact monitor by default", async () => {
    const api = monitorApi();
    renderMonitor(api, vi.fn(async () => undefined), "conceptual", null);

    const monitor = screen.getByRole("region", { name: "Conceptual recent runs" });
    const toggle = within(monitor).getByRole("button", {
      name: "Show Conceptual run activity",
    });
    expect(toggle).toHaveAttribute("aria-expanded", "false");
    expect(toggle).toHaveAttribute("aria-controls");
    const summary = await within(monitor).findByLabelText("Latest Conceptual run");
    expect(within(summary).getByText("Run 1048")).toBeVisible();
    expect(within(summary).getByText(/completed/i)).toBeVisible();
    expect(within(monitor).getByRole("button", { name: /Refresh/ })).toBeVisible();
    expect(screen.queryByRole("article", { name: "Run 1048 details" })).not.toBeInTheDocument();
  });

  it("expands a focused run and exposes an accessible details toggle", async () => {
    const api = monitorApi();
    const user = userEvent.setup();
    renderMonitor(api, vi.fn(async () => undefined));

    const hide = screen.getByRole("button", { name: "Hide Conceptual run activity" });
    const bodyId = hide.getAttribute("aria-controls");
    expect(hide).toHaveAttribute("aria-expanded", "true");
    expect(bodyId).not.toBeNull();
    expect(document.getElementById(bodyId as string)).not.toHaveAttribute("hidden");
    expect(await screen.findByRole("article", { name: "Run 1048 details" })).toBeVisible();

    await user.click(hide);
    const show = screen.getByRole("button", { name: "Show Conceptual run activity" });
    expect(show).toHaveAttribute("aria-expanded", "false");
    expect(document.getElementById(bodyId as string)).toHaveAttribute("hidden");
    expect(screen.queryByRole("article", { name: "Run 1048 details" })).not.toBeInTheDocument();

    await user.click(show);
    expect(screen.getByRole("button", {
      name: "Hide Conceptual run activity",
    })).toHaveAttribute("aria-expanded", "true");
    expect(await screen.findByRole("article", { name: "Run 1048 details" })).toBeVisible();
  });

  it("expands when a newly started run becomes the focused run", async () => {
    const api = monitorApi();
    const readOverview = vi.fn<ModelsApi["readModelOverview"]>().mockResolvedValue({
      model_id: 18, model_revision: 5, items: [], section_states: [{ section: "conceptual", state: "not_run" }],
    });
    api.listWorkflowRuns.mockResolvedValue({ items: [workflowRun(false), { ...workflowRun(false), workflow_run_id: 1047 }], next_cursor: null });
    api.readWorkflowRun.mockImplementation(async (_tenant, _model, id) => ({ ...workflowRun(false), workflow_run_id: id }));
    const { rerenderMonitor } = renderMonitor(
      api,
      vi.fn(async () => undefined),
      "conceptual",
      null,
      readOverview,
    );

    expect(screen.getByRole("button", {
      name: "Show Conceptual run activity",
    })).toHaveAttribute("aria-expanded", "false");
    const sectionState = screen.getByLabelText("Conceptual section state");
    await waitFor(() => expect(sectionState).toHaveTextContent("not_run"));
    expect(readOverview).toHaveBeenCalledExactlyOnceWith(7, 18);
    readOverview.mockResolvedValue({
      model_id: 18, model_revision: 5, items: [], section_states: [{ section: "conceptual", state: "queued" }],
    });
    rerenderMonitor(1048);

    expect(await screen.findByRole("button", {
      name: "Hide Conceptual run activity",
    })).toHaveAttribute("aria-expanded", "true");
    expect(await screen.findByRole("article", { name: "Run 1048 details" })).toBeVisible();
    await waitFor(() => expect(sectionState).toHaveTextContent("queued"));
    expect(readOverview).toHaveBeenCalledTimes(2);
    rerenderMonitor(1048);
    await userEvent.setup().click(screen.getByRole("button", { name: /Run 1047/ }));
    expect(await screen.findByRole("article", { name: "Run 1047 details" })).toBeVisible();
    expect(readOverview).toHaveBeenCalledTimes(2);
  });

  it("shows the authoritative bounded review and applies the exact validated draft manually", async () => {
    const api = monitorApi();
    const onApplied = vi.fn(async () => undefined);
    const user = userEvent.setup();
    const readOverview = vi.fn<ModelsApi["readModelOverview"]>().mockResolvedValue({
      model_id: 18, model_revision: 5, items: [], section_states: [{ section: "conceptual", state: "completed" }],
    });
    renderMonitor(api, onApplied, "conceptual", 1048, readOverview);

    const review = await screen.findByRole("table", { name: "Validated draft action counts" });
    expect(within(review).getByText("conceptual object")).toBeVisible();
    expect(within(review).getAllByText("3")).toHaveLength(2);
    expect(screen.getByTitle("Candidate digest")).toHaveTextContent("d".repeat(64));
    expect(api.applyWorkflowDraft).not.toHaveBeenCalled();
    const sectionState = screen.getByLabelText("Conceptual section state");
    await waitFor(() => expect(sectionState).toHaveTextContent("completed"));
    const overviewCalls = readOverview.mock.calls.length;

    await user.click(screen.getByRole("button", { name: "Apply validated draft" }));
    const confirmation = await screen.findByRole("dialog", {
      name: "Apply validated Conceptual draft?",
    });
    expect(api.applyWorkflowDraft).not.toHaveBeenCalled();
    readOverview.mockResolvedValue({
      model_id: 18, model_revision: 6, items: [], section_states: [{ section: "conceptual", state: "results_available" }],
    });
    await user.click(within(confirmation).getByRole("button", { name: "Apply exact draft" }));

    await waitFor(() => expect(api.applyWorkflowDraft).toHaveBeenCalledWith(
      7,
      18,
      1048,
      5,
      2,
      "d".repeat(64),
      expect.any(String),
    ));
    await waitFor(() => expect(onApplied).toHaveBeenCalledOnce());
    expect(screen.getByRole("button", {
      name: "Show Conceptual run activity",
    })).toHaveAttribute("aria-expanded", "false");
    const compactSummary = await screen.findByLabelText("Latest Conceptual run");
    expect(compactSummary).toHaveTextContent("Run 1048");
    expect(compactSummary).toHaveTextContent(/completed/i);
    expect(compactSummary).toHaveTextContent("Draft applied");
    await waitFor(() => expect(sectionState).toHaveTextContent("results_available"));
    expect(readOverview).toHaveBeenCalledTimes(overviewCalls + 1);
  });

  it("reviews and applies an exact validated Validation draft", async () => {
    const api = monitorApi();
    const validationRun: WorkflowRunDetail = {
      ...workflowRun(false),
      model_workflow: "validation",
      workflow_execution_mode: null,
    };
    const validationReview: WorkflowDraftReview = {
      ...workflowDraftReview(false),
      validation_outcome: {
        schema_version: "1.0",
        valid: true,
        phase: "complete",
        staged_record_count: 3,
        error_count: 0,
        action_review: [
          {
            dataset: "validation_group",
            insert_count: 1,
            update_count: 0,
            deactivate_count: 0,
            reactivate_count: 0,
            no_change_count: 0,
          },
          {
            dataset: "validation_check",
            insert_count: 2,
            update_count: 0,
            deactivate_count: 0,
            reactivate_count: 0,
            no_change_count: 0,
          },
        ],
      },
      dataset_counts: [
        { dataset: "validation_group", record_count: 1 },
        { dataset: "validation_check", record_count: 2 },
      ],
    };
    api.listWorkflowRuns.mockResolvedValue({ items: [validationRun], next_cursor: null });
    api.readWorkflowRun.mockResolvedValue(validationRun);
    api.readWorkflowDraftReview.mockResolvedValue(validationReview);
    const onApplied = vi.fn(async () => undefined);
    const user = userEvent.setup();
    renderMonitor(api, onApplied, "validation");

    const review = await screen.findByRole("table", { name: "Validated draft action counts" });
    expect(within(review).getByText("validation group")).toBeVisible();
    expect(within(review).getByText("validation check")).toBeVisible();
    await user.click(screen.getByRole("button", { name: "Apply validated draft" }));
    const confirmation = await screen.findByRole("dialog", {
      name: "Apply validated Validation draft?",
    });
    await user.click(within(confirmation).getByRole("button", { name: "Apply exact draft" }));

    await waitFor(() => expect(api.applyWorkflowDraft).toHaveBeenCalledWith(
      7,
      18,
      1048,
      5,
      2,
      "d".repeat(64),
      expect.any(String),
    ));
    await waitFor(() => expect(onApplied).toHaveBeenCalledOnce());
  });

  it("loads the authoritative draft for Code Generation with its fixed execution profile", async () => {
    const api = monitorApi();
    const run: WorkflowRunDetail = { ...workflowRun(false), model_workflow: "code_generation", workflow_execution_mode: null };
    api.listWorkflowRuns.mockResolvedValue({ items: [run], next_cursor: null });
    api.readWorkflowRun.mockResolvedValue(run);
    renderMonitor(api, vi.fn(async () => undefined), "code_generation");
    expect(await screen.findByRole("button", { name: "Apply validated draft" })).toBeEnabled();
    expect(api.readWorkflowDraftReview).toHaveBeenCalledTimes(1);
    expect(screen.getByText("Configured generator")).toBeVisible();
  });

  it("never offers Apply for deterministic Analysis validation or a stale review", async () => {
    const validationApi = monitorApi({ deterministic: true });
    const { unmount } = renderMonitor(validationApi, vi.fn(async () => undefined), "analysis");
    await screen.findByRole("article", { name: "Run 1048 details" });
    expect(screen.queryByRole("button", { name: "Apply validated draft" })).not.toBeInTheDocument();
    unmount();

    const staleApi = monitorApi({ staleReview: true });
    renderMonitor(staleApi, vi.fn(async () => undefined));
    expect(await screen.findByRole("alert")).toHaveTextContent(
      "authoritative draft review is unavailable or no longer matches",
    );
    expect(screen.queryByRole("button", { name: "Apply validated draft" })).not.toBeInTheDocument();
  });

  it("loads older runs and opens an exact run ID outside the visible page", async () => {
    const api = monitorApi();
    const olderRun = { ...workflowRun(false), workflow_run_id: 1047 };
    const directRun = { ...workflowRun(false), workflow_run_id: 1039 };
    api.listWorkflowRuns.mockImplementation(async (_tenant, _model, _workflow, _state, _size, cursor) => (
      cursor
        ? { items: [olderRun], next_cursor: null }
        : { items: [workflowRun(false)], next_cursor: "older" }
    ));
    api.readWorkflowRun.mockImplementation(async (_tenant, _model, runId) => (
      runId === 1039 ? directRun : runId === 1047 ? olderRun : workflowRun(false)
    ));
    const user = userEvent.setup();
    renderMonitor(api, vi.fn(async () => undefined));

    await user.click(await screen.findByRole("button", { name: "Load more runs" }));
    expect(await screen.findByRole("button", { name: /Run 1047/ })).toBeVisible();

    await user.clear(screen.getByLabelText("Run ID"));
    await user.type(screen.getByLabelText("Run ID"), "1039");
    await user.click(screen.getByRole("button", { name: "Open run" }));
    expect(await screen.findByRole("article", { name: "Run 1039 details" })).toBeVisible();
  });

  it("aggregates every event page and refreshes all selected-run resources", async () => {
    const api = monitorApi();
    const firstPage = Array.from({ length: 200 }, (_, index) => workflowEvent(index + 1));
    api.listWorkflowRunEvents.mockImplementation(async (_tenant, _model, _run, after) => (
      after === 0
        ? { items: firstPage, next_after_sequence: 200 }
        : after === 200
          ? { items: [workflowEvent(201)], next_after_sequence: 201 }
          : { items: [], next_after_sequence: after ?? 0 }
    ));
    const user = userEvent.setup();
    renderMonitor(api, vi.fn(async () => undefined));

    expect(await screen.findByText("Run event 201")).toBeVisible();
    expect(api.listWorkflowRunEvents).toHaveBeenCalledWith(7, 18, 1048, 200);
    const listCalls = api.listWorkflowRuns.mock.calls.length;
    const detailCalls = api.readWorkflowRun.mock.calls.length;
    const eventCalls = api.listWorkflowRunEvents.mock.calls.length;
    const reviewCalls = api.readWorkflowDraftReview.mock.calls.length;

    await user.click(screen.getByRole("button", { name: "Refresh runs" }));
    await waitFor(() => {
      expect(api.listWorkflowRuns.mock.calls.length).toBeGreaterThan(listCalls);
      expect(api.readWorkflowRun.mock.calls.length).toBeGreaterThan(detailCalls);
      expect(api.listWorkflowRunEvents.mock.calls.length).toBeGreaterThan(eventCalls);
      expect(api.readWorkflowDraftReview.mock.calls.length).toBeGreaterThan(reviewCalls);
    });
  });

  it("does not poll an active run and refreshes only after the user asks", async () => {
    const api = monitorApi();
    const readOverview = vi.fn<ModelsApi["readModelOverview"]>().mockResolvedValue({
      model_id: 18, model_revision: 5, items: [], section_states: [{ section: "conceptual", state: "running" }],
    });
    const activeRun: WorkflowRunDetail = {
      ...workflowRun(false),
      workflow_run_state: "running",
      completed_at: null,
      model_change_set_id: null,
      model_change_set_status: null,
      draft_revision: null,
      candidate_digest: null,
      validated_at: null,
    };
    api.listWorkflowRuns.mockResolvedValue({ items: [activeRun], next_cursor: null });
    api.readWorkflowRun.mockResolvedValue(activeRun);
    const started = progressEvent({
      sequence: 2,
      message: "Context preparation started for 80 selected Objects.",
      current: 0,
      total: 80,
    });
    const progressing = progressEvent({
      sequence: 3,
      message: "Object contribution coverage processed 10 of 80 selected Objects.",
      current: 10,
      total: 80,
    });
    let eventReads = 0;
    api.listWorkflowRunEvents.mockImplementation(async () => {
      eventReads += 1;
      return {
        items: eventReads === 1 ? [started] : [started, progressing],
        next_after_sequence: eventReads === 1 ? 2 : 3,
      };
    });
    const user = userEvent.setup();
    renderMonitor(api, vi.fn(async () => undefined), "conceptual", 1048, readOverview);

    expect(await screen.findByRole("article", { name: "Run 1048 details" })).toBeVisible();
    expect(screen.getByText(started.message)).toBeVisible();
    expect(screen.queryByText(progressing.message)).not.toBeInTheDocument();
    const listCalls = api.listWorkflowRuns.mock.calls.length;
    const detailCalls = api.readWorkflowRun.mock.calls.length;
    const eventCalls = api.listWorkflowRunEvents.mock.calls.length;
    const sectionState = screen.getByLabelText("Conceptual section state");
    await waitFor(() => expect(sectionState).toHaveTextContent("running"));
    const overviewCalls = readOverview.mock.calls.length;

    await new Promise((resolve) => globalThis.setTimeout(resolve, 2_100));

    expect(api.listWorkflowRuns).toHaveBeenCalledTimes(listCalls);
    expect(api.readWorkflowRun).toHaveBeenCalledTimes(detailCalls);
    expect(api.listWorkflowRunEvents).toHaveBeenCalledTimes(eventCalls);
    expect(readOverview).toHaveBeenCalledTimes(overviewCalls);
    expect(screen.queryByText(progressing.message)).not.toBeInTheDocument();

    readOverview.mockResolvedValue({
      model_id: 18, model_revision: 5, items: [], section_states: [{ section: "conceptual", state: "failed" }],
    });
    await user.click(screen.getByRole("button", { name: "Refresh runs" }));
    await waitFor(() => {
      expect(api.listWorkflowRuns.mock.calls.length).toBeGreaterThan(listCalls);
      expect(api.readWorkflowRun.mock.calls.length).toBeGreaterThan(detailCalls);
      expect(api.listWorkflowRunEvents.mock.calls.length).toBeGreaterThan(eventCalls);
    });
    expect(await screen.findByText(progressing.message)).toBeVisible();
    expect(screen.getByRole("progressbar", {
      name: "Conceptual · object contribution progress: 10 of 80",
    })).toHaveAttribute("value", "10");
    await waitFor(() => expect(sectionState).toHaveTextContent("failed"));
    expect(readOverview).toHaveBeenCalledTimes(overviewCalls + 1);
  });

  it("renders ordered stage milestones with counts and findings", async () => {
    const api = monitorApi();
    api.listWorkflowRunEvents.mockResolvedValue({
      items: [
        progressEvent({
          sequence: 2,
          message: "One-shot started for 30 selected Objects.",
          current: 0,
          total: 30,
        }),
        progressEvent({
          sequence: 3,
          message: "Object contribution coverage processed 10 of 30 selected Objects.",
          current: 10,
          total: 30,
        }),
        progressEvent({
          sequence: 4,
          stage: "conceptual.backend_validation",
          status: "completed",
          message: "Conceptual candidate is ready in a validated draft.",
          current: 1,
          total: 1,
          finding_count: 2,
        }),
      ],
      next_after_sequence: 4,
    });
    renderMonitor(api, vi.fn(async () => undefined));

    const eventsSection = (await screen.findByRole("heading", { name: "Events" })).parentElement;
    expect(eventsSection).not.toBeNull();
    const eventList = within(eventsSection as HTMLElement).getByRole("list");
    const items = within(eventList).getAllByRole("listitem");
    expect(items).toHaveLength(3);
    expect(items[0]).toHaveTextContent("One-shot started");
    expect(items[1]).toHaveTextContent("10 of 30");
    expect(items[2]).toHaveTextContent("2 findings");
    const finalItem = items.at(2);
    expect(finalItem).toBeDefined();
    expect(within(finalItem as HTMLElement).getByText("Event 4 · Attempt 1")).toBeVisible();
  });

  it("shows bounded failure reason, execution context, and event attempt details", async () => {
    const api = monitorApi();
    const failedRun: WorkflowRunDetail = {
      ...workflowRun(false),
      workflow_run_state: "failed",
      failure_code: "agent_context_too_large",
      token_usage: { status: "partial", request_count: 2, reported_request_count: 1,
        pending_request_count: 0, missing_usage_request_count: 1,
        input_tokens: 700, output_tokens: 50, total_tokens: 750,
        cached_input_tokens: null, cache_write_input_tokens: null, reasoning_output_tokens: null,
        cost_estimate: { status: "partial", currency: "USD", amount: "0.001",
          priced_request_count: 1, unpriced_request_count: 1, pricing_bases: ["Configured rates"],
          unpriced_reasons: { pricing_not_configured: 0, outside_pricing_window: 0,
            context_limit_exceeded: 0, missing_usage: 1, unsupported_token_types: 0 } },
        history_incomplete: false },
      failure_message: (
        "The selected execution mode cannot accept this context. Choose another mode explicitly."
      ),
      model_change_set_id: null,
      model_change_set_status: null,
      draft_revision: null,
      candidate_digest: null,
      validated_at: null,
    };
    api.listWorkflowRuns.mockResolvedValue({ items: [failedRun], next_cursor: null });
    api.readWorkflowRun.mockResolvedValue(failedRun);
    api.listWorkflowRunEvents.mockResolvedValue({
      items: [{
        ...workflowEvent(3),
        attempt: 2,
        stage: "conceptual.candidate_authoring",
        status: "failed",
        message: "Candidate authoring stopped safely.",
        current: 1,
        total: 2,
        finding_count: 1,
      }],
      next_after_sequence: 3,
    });
    renderMonitor(api, vi.fn(async () => undefined));

    const failure = await screen.findByRole("alert", { name: "Run failure details" });
    expect(failure).toHaveTextContent("agent context too large");
    expect(failure).toHaveTextContent(
      "The selected execution mode cannot accept this context. Choose another mode explicitly.",
    );
    expect(failure).toHaveTextContent("Conceptual · candidate authoring");
    expect(failure).toHaveTextContent("Attempt 2");
    expect(failure).toHaveTextContent("databricks · databricks-primary");
    const eventMeta = screen.getByText("Event 3 · Attempt 2").closest("small");
    expect(eventMeta).toHaveTextContent("1 of 2");
    expect(eventMeta).toHaveTextContent("1 finding");
    const usage = screen.getByRole("region", { name: "Token usage" });
    expect(usage).toHaveTextContent("Partial");
    expect(usage).toHaveTextContent("1 of 2 requests reported token usage. 1 without usage.");
    expect(within(usage).getByText("750")).toBeVisible();
    expect(within(usage).getByText("USD 0.001")).toBeVisible();
    expect(usage).toHaveTextContent("Partial estimate; includes 1 priced request only.");
  });

  it("keeps one Apply idempotency key across an ambiguous error and confirmation reopen", async () => {
    const api = monitorApi();
    const successfulResult = await api.applyWorkflowDraft(7, 18, 1048, 5, 2, "d".repeat(64), "seed");
    api.applyWorkflowDraft.mockReset();
    api.applyWorkflowDraft
      .mockRejectedValueOnce(new TypeError("Failed to fetch"))
      .mockResolvedValueOnce(successfulResult);
    const user = userEvent.setup();
    renderMonitor(api, vi.fn(async () => undefined));

    await user.click(await screen.findByRole("button", { name: "Apply validated draft" }));
    let confirmation = await screen.findByRole("dialog", { name: "Apply validated Conceptual draft?" });
    await user.click(within(confirmation).getByRole("button", { name: "Apply exact draft" }));
    expect(await within(confirmation).findByRole("alert")).toHaveTextContent("could not be applied");
    await user.click(within(confirmation).getByRole("button", { name: "Close draft confirmation" }));

    await user.click(screen.getByRole("button", { name: "Apply validated draft" }));
    confirmation = await screen.findByRole("dialog", { name: "Apply validated Conceptual draft?" });
    await user.click(within(confirmation).getByRole("button", { name: "Apply exact draft" }));
    await waitFor(() => expect(api.applyWorkflowDraft).toHaveBeenCalledTimes(2));
    expect(api.applyWorkflowDraft.mock.calls[0]?.[6]).toBe(api.applyWorkflowDraft.mock.calls[1]?.[6]);
  });

  it("replaces the Apply idempotency key after a definitive server response", async () => {
    const api = monitorApi();
    const successfulResult = await api.applyWorkflowDraft(7, 18, 1048, 5, 2, "d".repeat(64), "seed");
    api.applyWorkflowDraft.mockReset();
    api.applyWorkflowDraft
      .mockRejectedValueOnce(new ApiError(409, "revision_conflict", null))
      .mockResolvedValueOnce(successfulResult);
    const user = userEvent.setup();
    renderMonitor(api, vi.fn(async () => undefined));

    await user.click(await screen.findByRole("button", { name: "Apply validated draft" }));
    let confirmation = await screen.findByRole("dialog", { name: "Apply validated Conceptual draft?" });
    await user.click(within(confirmation).getByRole("button", { name: "Apply exact draft" }));
    expect(await within(confirmation).findByRole("alert")).toHaveTextContent("Model or draft changed");
    await user.click(within(confirmation).getByRole("button", { name: "Close draft confirmation" }));

    await user.click(screen.getByRole("button", { name: "Apply validated draft" }));
    confirmation = await screen.findByRole("dialog", { name: "Apply validated Conceptual draft?" });
    await user.click(within(confirmation).getByRole("button", { name: "Apply exact draft" }));
    await waitFor(() => expect(api.applyWorkflowDraft).toHaveBeenCalledTimes(2));
    expect(api.applyWorkflowDraft.mock.calls[0]?.[6]).not.toBe(api.applyWorkflowDraft.mock.calls[1]?.[6]);
  });

  it("disables Apply when the authoritative draft review has expired", async () => {
    const api = monitorApi({ expiredReview: true });
    renderMonitor(api, vi.fn(async () => undefined));

    expect(await screen.findByRole("alert")).toHaveTextContent("validated draft has expired");
    expect(screen.queryByRole("button", { name: "Apply validated draft" })).not.toBeInTheDocument();
  });

  it("traps modal focus, closes with Escape, and restores the Apply trigger", async () => {
    const api = monitorApi();
    const user = userEvent.setup();
    renderMonitor(api, vi.fn(async () => undefined));
    const trigger = await screen.findByRole("button", { name: "Apply validated draft" });
    const appRoot = trigger.closest("#root");

    await user.click(trigger);
    const confirmation = await screen.findByRole("dialog", { name: "Apply validated Conceptual draft?" });
    const close = within(confirmation).getByRole("button", { name: "Close draft confirmation" });
    const apply = within(confirmation).getByRole("button", { name: "Apply exact draft" });
    expect(appRoot).toHaveAttribute("inert");
    expect(appRoot).toHaveAttribute("aria-hidden", "true");
    expect(close).toHaveFocus();
    await user.tab({ shift: true });
    expect(apply).toHaveFocus();
    await user.tab();
    expect(close).toHaveFocus();
    await user.keyboard("{Escape}");
    expect(screen.queryByRole("dialog", { name: "Apply validated Conceptual draft?" })).not.toBeInTheDocument();
    expect(appRoot).not.toHaveAttribute("inert");
    expect(appRoot).not.toHaveAttribute("aria-hidden");
    await waitFor(() => expect(trigger).toHaveFocus());
  });
});

function renderMonitor(
  api: WorkflowRunMonitorApi,
  onApplied: () => Promise<void>,
  workflow: "analysis" | "conceptual" | "validation" | "code_generation" | "mapping" = "conceptual",
  focusRunId: number | null = 1048,
  readOverview?: ModelsApi["readModelOverview"],
  hasTenantLock = true,
) {
  const queryClient = new QueryClient({
    defaultOptions: { queries: { retry: false }, mutations: { retry: false } },
  });
  const appRoot = document.createElement("div");
  appRoot.id = "root";
  document.body.append(appRoot);
  const monitor = (nextFocusRunId: number | null) => (
    <QueryClientProvider client={queryClient}>
      {readOverview ? <SectionStatus readOverview={readOverview} /> : null}
      <WorkflowRunMonitor
        api={api}
        tenantId={7}
        modelId={18}
        modelRevision={5}
        workflow={workflow}
        hasTenantLock={hasTenantLock}
        focusRunId={nextFocusRunId}
        onApplied={onApplied}
      />
    </QueryClientProvider>
  );
  const rendered = render(
    monitor(focusRunId),
    { container: appRoot },
  );
  return {
    ...rendered,
    rerenderMonitor: (nextFocusRunId: number | null) => rendered.rerender(
      monitor(nextFocusRunId),
    ),
  };
}

function SectionStatus({ readOverview }: { readOverview: ModelsApi["readModelOverview"] }) {
  const query = useQuery({ queryKey: ["model-overview", 7, 18], queryFn: () => readOverview(7, 18),
    staleTime: 30_000, refetchOnWindowFocus: false });
  return <output aria-label="Conceptual section state">
    {query.data?.section_states?.find((entry) => entry.section === "conceptual")?.state ?? "Loading"}
  </output>;
}

function monitorApi(options: {
  deterministic?: boolean;
  expiredReview?: boolean;
  staleReview?: boolean;
} = {}) {
  const run = workflowRun(options.deterministic ?? false);
  const review = workflowDraftReview(
    options.staleReview ?? false,
    options.expiredReview ?? false,
  );
  return {
    listWorkflowRuns: vi.fn<WorkflowRunMonitorApi["listWorkflowRuns"]>(
      async () => ({ items: [run], next_cursor: null }),
    ),
    readWorkflowRun: vi.fn<WorkflowRunMonitorApi["readWorkflowRun"]>(async () => run),
    listWorkflowRunEvents: vi.fn<WorkflowRunMonitorApi["listWorkflowRunEvents"]>(async () => ({
      items: [{
        sequence: 1,
        attempt: 1,
        stage: "conceptual.backend_validation",
        status: "completed" as const,
        message: "Validated one bounded candidate.",
        current: 1,
        total: 1,
        percent: "100",
        finding_count: 1,
        created_at: "2026-08-25T12:01:00Z",
      }],
      next_after_sequence: 1,
    })),
    readWorkflowDraftReview: vi.fn<WorkflowRunMonitorApi["readWorkflowDraftReview"]>(
      async () => review,
    ),
    applyWorkflowDraft: vi.fn<WorkflowRunMonitorApi["applyWorkflowDraft"]>(async () => ({
      schema_version: "1.0" as const,
      model_id: 18,
      workflow_run_id: 1048,
      model_change_set_id: "aaaaaaaa-aaaa-aaaa-aaaa-aaaaaaaaaaaa",
      replayed: false,
      draft_revision: 2,
      candidate_digest: "d".repeat(64),
      action_count: 3,
      model_revision: 6,
      applied_at: "2026-08-25T12:02:00Z",
    })),
  } satisfies WorkflowRunMonitorApi;
}

function workflowRun(deterministic: boolean): WorkflowRunDetail {
  return {
    token_usage: {
      status: "unavailable", request_count: 0, reported_request_count: 0,
      pending_request_count: 0, missing_usage_request_count: 0,
      input_tokens: null, output_tokens: null, total_tokens: null,
      cached_input_tokens: null, cache_write_input_tokens: null, reasoning_output_tokens: null,
      cost_estimate: { status: "unavailable", currency: "USD", amount: null,
        priced_request_count: 0, unpriced_request_count: 0, pricing_bases: [],
        unpriced_reasons: { pricing_not_configured: 0, outside_pricing_window: 0,
          context_limit_exceeded: 0, missing_usage: 0, unsupported_token_types: 0 } },
      history_incomplete: false,
    },
    workflow_run_id: 1048,
    model_workflow: deterministic ? "analysis" : "conceptual",
    workflow_execution_mode: deterministic ? null : "one_shot",
    modeled_entity_type: null,
    selected_scope_count: 2,
    requested_batch_id: null,
    workflow_run_state: "completed",
    actor_display_name: "Maaz",
    created_at: "2026-08-25T12:00:00Z",
    started_at: "2026-08-25T12:00:10Z",
    completed_at: "2026-08-25T12:01:00Z",
    correlation_id: "bbbbbbbb-bbbb-bbbb-bbbb-bbbbbbbbbbbb",
    agent_sdk_code: deterministic ? null : "openai_agents",
    agent_provider_code: deterministic ? null : "databricks",
    agent_model_code: deterministic ? null : "databricks-primary",
    reasoning_effort_code: deterministic ? null : "medium",
    max_turns: deterministic ? null : 8,
    validation_retry_count: deterministic ? null : 1,
    failure_code: null,
    failure_message: null,
    model_change_set_id: deterministic ? null : "aaaaaaaa-aaaa-aaaa-aaaa-aaaaaaaaaaaa",
    model_change_set_status: deterministic ? null : "validated",
    draft_revision: deterministic ? null : 2,
    candidate_digest: deterministic ? null : "d".repeat(64),
    validated_at: deterministic ? null : "2026-08-25T12:00:55Z",
  };
}

function partialMappingRun(): WorkflowRunDetail {
  return { ...workflowRun(false), model_workflow: "mapping", workflow_run_state: "completed_with_repair",
    mapping_outcome: { completed_pair_count: 1, preserved_pair_count: 0, no_source_pair_count: 0, failed_pair_count: 1 },
    mapping_failures: [{ source_system_id: 22, system_code: "ERP", modeled_entity_id: 42,
      entity_schema_name: "silver", entity_name: "Order", message: "OrderDate requires a transformation rule." }],
    mapping_failures_truncated: false };
}

function workflowDraftReview(stale: boolean, expired = false): WorkflowDraftReview {
  return {
    schema_version: "1.0",
    model_id: 18,
    model_change_set_id: "aaaaaaaa-aaaa-aaaa-aaaa-aaaaaaaaaaaa",
    status: "validated",
    draft_revision: 2,
    candidate_digest: (stale ? "e" : "d").repeat(64),
    validation_outcome: {
      schema_version: "1.0",
      valid: true,
      phase: "complete",
      staged_record_count: 3,
      error_count: 0,
      action_review: [{
        dataset: "conceptual_object",
        insert_count: 3,
        update_count: 0,
        deactivate_count: 0,
        reactivate_count: 0,
        no_change_count: 0,
      }],
    },
    dataset_counts: [{ dataset: "conceptual_object", record_count: 3 }],
    dataset: null,
    records: null,
    created_at: "2026-08-25T12:00:00Z",
    last_activity_at: "2026-08-25T12:01:00Z",
    expires_at: expired ? "2020-01-01T00:00:00Z" : "2099-08-25T13:00:00Z",
    validated_at: "2026-08-25T12:00:55Z",
    applied_at: null,
    terminal_at: null,
  };
}

function failedDraftReview(): WorkflowDraftReview {
  return { ...workflowDraftReview(false), status: "active", candidate_digest: null, validated_at: null,
    dataset_counts: [{ dataset: "conceptual_object", record_count: 2 }],
    validation_outcome: {
      schema_version: "1.0", valid: false, phase: "complete", staged_record_count: 2,
      error_count: 26, action_review: [], errors_truncated: true,
      error_groups: [{ dataset: "conceptual_object", code: "active_dependency_invalid", count: 26 }],
      errors: [{ code: "active_dependency_invalid", dataset: "conceptual_object", record_number: 2,
        fields: ["is_active"], message: "An active relationship requires this object." }],
    },
  };
}

function workflowEvent(sequence: number) {
  return {
    sequence,
    attempt: 1,
    stage: `run.event.${sequence}`,
    status: "running" as const,
    message: `Run event ${sequence}`,
    current: sequence,
    total: 201,
    percent: String((sequence / 201) * 100),
    finding_count: 0,
    created_at: "2026-08-25T12:01:00Z",
  };
}

function progressEvent(overrides: Partial<WorkflowRunEvent>): WorkflowRunEvent {
  return {
    sequence: 2,
    attempt: 1,
    stage: "conceptual.object_contribution",
    status: "running",
    message: "One-shot is running.",
    current: 0,
    total: 1,
    percent: "0",
    finding_count: 0,
    created_at: "2026-08-25T12:01:00Z",
    ...overrides,
  };
}
