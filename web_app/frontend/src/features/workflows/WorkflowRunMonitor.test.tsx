import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { render, screen, waitFor, within } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { describe, expect, it, vi } from "vitest";

import { ApiError } from "../../core/http";
import type {
  WorkflowDraftReview,
  WorkflowRunDetail,
  WorkflowRunEvent,
  WorkflowRunMonitorApi,
} from "./api";
import { WorkflowRunMonitor } from "./WorkflowRunMonitor";

describe("Workflow Run monitor", () => {
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
    const { rerenderMonitor } = renderMonitor(
      api,
      vi.fn(async () => undefined),
      "conceptual",
      null,
    );

    expect(screen.getByRole("button", {
      name: "Show Conceptual run activity",
    })).toHaveAttribute("aria-expanded", "false");
    rerenderMonitor(1048);

    expect(await screen.findByRole("button", {
      name: "Hide Conceptual run activity",
    })).toHaveAttribute("aria-expanded", "true");
    expect(await screen.findByRole("article", { name: "Run 1048 details" })).toBeVisible();
  });

  it("shows the authoritative bounded review and applies the exact validated draft manually", async () => {
    const api = monitorApi();
    const onApplied = vi.fn(async () => undefined);
    const user = userEvent.setup();
    renderMonitor(api, onApplied);

    const review = await screen.findByRole("table", { name: "Validated draft action counts" });
    expect(within(review).getByText("conceptual object")).toBeVisible();
    expect(within(review).getAllByText("3")).toHaveLength(2);
    expect(screen.getByTitle("Candidate digest")).toHaveTextContent("d".repeat(64));
    expect(api.applyWorkflowDraft).not.toHaveBeenCalled();

    await user.click(screen.getByRole("button", { name: "Apply validated draft" }));
    const confirmation = await screen.findByRole("dialog", {
      name: "Apply validated Conceptual draft?",
    });
    expect(api.applyWorkflowDraft).not.toHaveBeenCalled();
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
  });

  it("reviews and applies an exact validated QA draft", async () => {
    const api = monitorApi();
    const qaRun: WorkflowRunDetail = {
      ...workflowRun(false),
      model_workflow: "qa",
      workflow_execution_mode: "detailed_coverage",
    };
    const qaReview: WorkflowDraftReview = {
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
    api.listWorkflowRuns.mockResolvedValue({ items: [qaRun], next_cursor: null });
    api.readWorkflowRun.mockResolvedValue(qaRun);
    api.readWorkflowDraftReview.mockResolvedValue(qaReview);
    const onApplied = vi.fn(async () => undefined);
    const user = userEvent.setup();
    renderMonitor(api, onApplied, "qa");

    const review = await screen.findByRole("table", { name: "Validated draft action counts" });
    expect(within(review).getByText("validation group")).toBeVisible();
    expect(within(review).getByText("validation check")).toBeVisible();
    await user.click(screen.getByRole("button", { name: "Apply validated draft" }));
    const confirmation = await screen.findByRole("dialog", {
      name: "Apply validated QA draft?",
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
    renderMonitor(api, vi.fn(async () => undefined));

    expect(await screen.findByRole("article", { name: "Run 1048 details" })).toBeVisible();
    expect(screen.getByText(started.message)).toBeVisible();
    expect(screen.queryByText(progressing.message)).not.toBeInTheDocument();
    const listCalls = api.listWorkflowRuns.mock.calls.length;
    const detailCalls = api.readWorkflowRun.mock.calls.length;
    const eventCalls = api.listWorkflowRunEvents.mock.calls.length;

    await new Promise((resolve) => globalThis.setTimeout(resolve, 2_100));

    expect(api.listWorkflowRuns).toHaveBeenCalledTimes(listCalls);
    expect(api.readWorkflowRun).toHaveBeenCalledTimes(detailCalls);
    expect(api.listWorkflowRunEvents).toHaveBeenCalledTimes(eventCalls);
    expect(screen.queryByText(progressing.message)).not.toBeInTheDocument();

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
  });

  it("renders ordered stage milestones with counts and findings", async () => {
    const api = monitorApi();
    api.listWorkflowRunEvents.mockResolvedValue({
      items: [
        progressEvent({
          sequence: 2,
          message: "Detailed coverage started for 30 selected Objects.",
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
    expect(items[0]).toHaveTextContent("Detailed coverage started");
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
  workflow: "analysis" | "conceptual" | "qa" = "conceptual",
  focusRunId: number | null = 1048,
) {
  const queryClient = new QueryClient({
    defaultOptions: { queries: { retry: false }, mutations: { retry: false } },
  });
  const appRoot = document.createElement("div");
  appRoot.id = "root";
  document.body.append(appRoot);
  const monitor = (nextFocusRunId: number | null) => (
    <QueryClientProvider client={queryClient}>
      <WorkflowRunMonitor
        api={api}
        tenantId={7}
        modelId={18}
        modelRevision={5}
        workflow={workflow}
        hasTenantLock
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
    message: "Detailed coverage is running.",
    current: 0,
    total: 1,
    percent: "0",
    finding_count: 0,
    created_at: "2026-08-25T12:01:00Z",
    ...overrides,
  };
}
