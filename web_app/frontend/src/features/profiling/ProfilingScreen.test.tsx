import { render, screen, waitFor, within } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { createMemoryHistory } from "@tanstack/react-router";
import { describe, expect, it, vi } from "vitest";

import { createApiClient } from "../../api";
import { WorkbenchApp, createWorkbenchRouter } from "../../app";

describe("Model Profiling", () => {
  it("shows normalized result filters and opens Object evidence only on request", async () => {
    const fetcher = profilingFetchStub();
    const router = profilingRouter(fetcher);
    const user = userEvent.setup();

    render(<WorkbenchApp router={router} />);

    const table = await screen.findByRole("table", { name: "Profiling results" });
    expect(within(table).getByText("customer_raw")).toBeVisible();
    expect(within(table).getByText("12 profiles")).toBeVisible();
    expect(fetcher.mock.calls.some(([input]) => String(input).endsWith("/profiling/501"))).toBe(false);

    await user.type(screen.getByLabelText("Object ID"), "501");
    await user.type(screen.getByLabelText("Source Tenant code"), " GRDM ");
    await user.type(screen.getByLabelText("System code"), " CRM ");
    await user.type(screen.getByLabelText("Object schema"), " Bronze_CRM ");
    await user.type(screen.getByLabelText("Object name"), " Customer_Raw ");
    await user.click(screen.getByRole("button", { name: "Apply result filters" }));

    expect(await screen.findByRole("table", { name: "Profiling results" })).toBeVisible();
    expect(fetcher).toHaveBeenCalledWith(
      "/api/v1/tenants/7/models/18/profiling?object_id=501&source_tenant_code=grdm&system_code=crm&object_schema=bronze_crm&object_name=customer_raw&page_size=200",
      expect.objectContaining({ credentials: "same-origin" }),
    );

    const showDetails = screen.getByRole("button", { name: "Show profiling details for customer_raw" });
    await user.click(showDetails);

    const drawer = await screen.findByRole("complementary", { name: "Profiling Object details" });
    expect(within(drawer).getByRole("heading", { name: "customer_raw" })).toBeVisible();
    expect(within(drawer).getByText("customer_id")).toBeVisible();
    expect(within(drawer).getByText("80%")).toBeVisible();

    await user.click(within(drawer).getByRole("button", { name: "Close profiling Object details" }));

    expect(screen.queryByRole("complementary", { name: "Profiling Object details" })).not.toBeInTheDocument();
    expect(screen.getByRole("button", { name: "Show profiling details for customer_raw" })).toHaveFocus();
  });

  it("filters run history and shows bounded events in a closable drawer", async () => {
    const fetcher = profilingFetchStub();
    const router = profilingRouter(fetcher);
    const user = userEvent.setup();
    render(<WorkbenchApp router={router} />);
    await screen.findByRole("table", { name: "Profiling results" });

    await user.click(screen.getByRole("button", { name: "Runs" }));

    const runs = await screen.findByRole("table", { name: "Profiling runs" });
    expect(within(runs).getByText("PR-1048")).toBeVisible();
    await user.selectOptions(screen.getByLabelText("Run state"), "completed");

    expect(await screen.findByRole("table", { name: "Profiling runs" })).toBeVisible();
    expect(fetcher).toHaveBeenCalledWith(
      "/api/v1/tenants/7/models/18/runs?workflow=profiling&page_size=200&state=completed",
      expect.objectContaining({ credentials: "same-origin" }),
    );

    const showRun = screen.getByRole("button", { name: "Show details for profiling run PR-1048" });
    await user.click(showRun);

    const drawer = await screen.findByRole("complementary", { name: "Profiling run details" });
    expect(within(drawer).getByRole("heading", { name: "PR-1048" })).toBeVisible();
    expect(within(drawer).getByText("Prepare selected Objects")).toBeVisible();
    expect(within(drawer).getByText("8 of 8")).toBeVisible();

    await user.click(within(drawer).getByRole("button", { name: "Close profiling run details" }));
    expect(screen.queryByRole("complementary", { name: "Profiling run details" })).not.toBeInTheDocument();
    expect(screen.getByRole("button", { name: "Show details for profiling run PR-1048" })).toHaveFocus();
  });

  it("creates a queued run, then requires a separate explicit execute action", async () => {
    const fetcher = profilingFetchStub();
    const router = profilingRouter(fetcher);
    const user = userEvent.setup();
    render(<WorkbenchApp router={router} />);
    await screen.findByRole("table", { name: "Profiling results" });

    await user.click(screen.getByRole("button", { name: "Run profiling" }));

    const dialog = await screen.findByRole("dialog", { name: "Configure profiling run" });
    await user.click(within(dialog).getByRole("radio", { name: /^Selected Objects/ }));
    await user.click(within(dialog).getByRole("checkbox", { name: /customer_raw/ }));
    await user.type(within(dialog).getByLabelText("Batch ID (optional)"), " 10428 ");
    await user.click(within(dialog).getByRole("button", { name: "Create queued run" }));

    const drawer = await screen.findByRole("complementary", { name: "Profiling run details" });
    expect(within(drawer).getByText("Queued")).toBeVisible();
    expect(within(drawer).getByRole("button", { name: "Execute queued run" })).toBeVisible();

    const createCall = fetcher.mock.calls.find(([, init]) => (
      init?.method === "POST" && String(init.body).includes('"model_workflow":"profiling"')
    ));
    expect(createCall?.[0]).toBe("/api/v1/tenants/7/models/18/runs");
    expect(createCall?.[1]?.headers).toEqual(expect.objectContaining({
      "Idempotency-Key": expect.stringMatching(/^[0-9a-f-]{36}$/),
    }));
    expect(JSON.parse(String(createCall?.[1]?.body))).toEqual({
      expected_model_revision: 18,
      model_workflow: "profiling",
      selected_object_ids: [501],
      requested_batch_id: "10428",
    });

    await user.click(within(drawer).getByRole("button", { name: "Execute queued run" }));

    await waitFor(() => {
      expect(fetcher).toHaveBeenCalledWith(
        "/api/v1/tenants/7/models/18/profiling/runs/1049/execute",
        expect.objectContaining({
          body: JSON.stringify({ expected_model_revision: 18 }),
          method: "POST",
        }),
      );
    });
    expect(await within(drawer).findByText("Running")).toBeVisible();
  });

  it("keeps empty server results explicit", async () => {
    const fetcher = profilingFetchStub({ emptyResults: true });
    const router = profilingRouter(fetcher);
    render(<WorkbenchApp router={router} />);

    expect(await screen.findByText("No profiling results match these filters.")).toBeVisible();
  });

  it("shows a safe result loading failure", async () => {
    const fetcher = profilingFetchStub({ resultsError: true });
    const router = profilingRouter(fetcher);
    render(<WorkbenchApp router={router} />);

    expect(await screen.findByRole("alert")).toHaveTextContent(
      "Profiling results could not be loaded.",
    );
  });
});

function profilingRouter(fetcher: ReturnType<typeof profilingFetchStub>) {
  return createWorkbenchRouter({
    api: createApiClient(fetcher),
    history: createMemoryHistory({
      initialEntries: ["/tenants/7/models/18/profiling"],
    }),
  });
}

function profilingFetchStub(options: {
  emptyResults?: boolean;
  resultsError?: boolean;
} = {}): ReturnType<typeof vi.fn<typeof fetch>> {
  let runCreated = false;
  let runExecuted = false;

  return vi.fn<typeof fetch>(async (input, init) => {
    const url = String(input);
    if (url === "/api/v1/tenants/7/home") return jsonResponse(tenantHomePayload);
    if (url === "/api/v1/tenants/7/models/18") return jsonResponse(modelDetailPayload);
    if (url === "/api/v1/tenants/7/models/18/scope?zone=bronze&page_size=200") {
      return jsonResponse(modelScopePayload);
    }
    if (url.startsWith("/api/v1/tenants/7/models/18/profiling?") && init?.method !== "POST") {
      if (options.resultsError) {
        return jsonResponse({ error: { code: "profiling_unavailable" } }, 503);
      }
      return jsonResponse({
        ...profilingPagePayload,
        items: options.emptyResults ? [] : profilingPagePayload.items,
      });
    }
    if (url === "/api/v1/tenants/7/models/18/profiling/501") {
      return jsonResponse(profilingDetailPayload);
    }
    if (url.startsWith("/api/v1/tenants/7/models/18/runs?workflow=profiling")) {
      return jsonResponse({
        items: runCreated
          ? [profilingRunPayload(1049, runExecuted ? "running" : "queued")]
          : [profilingRunPayload(1048, "completed")],
        next_cursor: null,
      });
    }
    if (url === "/api/v1/tenants/7/models/18/runs" && init?.method === "POST") {
      runCreated = true;
      return jsonResponse({
        created: true,
        workflow_run_id: 1049,
        workflow_run_state: "queued",
        correlation_id: "bbbbbbbb-bbbb-bbbb-bbbb-bbbbbbbbbbbb",
        prompt_snapshot_count: 0,
        created_at: "2026-08-24T15:00:00Z",
      }, 201);
    }
    if (url === "/api/v1/tenants/7/models/18/profiling/runs/1049/execute" && init?.method === "POST") {
      runExecuted = true;
      return jsonResponse({
        changed: true,
        workflow_run_id: 1049,
        workflow_run_state: "running",
        model_revision: 18,
      }, 202);
    }
    const runMatch = url.match(/^\/api\/v1\/tenants\/7\/models\/18\/runs\/(1048|1049)$/);
    if (runMatch) {
      const runId = Number(runMatch[1]);
      const state = runId === 1049 ? (runExecuted ? "running" : "queued") : "completed";
      return jsonResponse({
        ...profilingRunPayload(runId, state),
        correlation_id: runId === 1049
          ? "bbbbbbbb-bbbb-bbbb-bbbb-bbbbbbbbbbbb"
          : "aaaaaaaa-aaaa-aaaa-aaaa-aaaaaaaaaaaa",
        agent_sdk_code: null,
        agent_provider_code: null,
        agent_model_code: null,
        reasoning_effort_code: null,
        max_turns: null,
        validation_retry_count: null,
        failure_code: null,
        failure_message: null,
      });
    }
    if (url.match(/^\/api\/v1\/tenants\/7\/models\/18\/runs\/(1048|1049)\/events\?/)) {
      return jsonResponse({
        items: runExecuted || url.includes("1048") ? [runEventPayload] : [],
        next_after_sequence: runExecuted || url.includes("1048") ? 1 : 0,
      });
    }
    return jsonResponse({ error: { code: "not_found", message: "Not found." } }, 404);
  });
}

function jsonResponse(value: unknown, status = 200): Response {
  return new Response(JSON.stringify(value), {
    status,
    headers: { "content-type": "application/json" },
  });
}

const tenantHomePayload = {
  tenant: {
    tenant_id: 7,
    tenant_code: "NWA",
    tenant_name: "Northwind Analytics",
    tenant_description: null,
    tenant_visibility: "private",
    effective_role: "tenant_admin",
  },
  lock: {
    is_locked: true,
    owner_display_name: "Maaz",
    owned_by_current_principal: true,
    purpose: "Model authoring",
    acquired_at: "2026-08-24T14:12:00Z",
    expires_at: "2026-08-24T16:12:00Z",
  },
  lock_actions: {
    can_acquire: false,
    can_renew: true,
    can_release: true,
    can_override: false,
  },
  systems: [],
};

const modelDetailPayload = {
  model_id: 18,
  tenant_id: 7,
  model_name: "Customer 360",
  model_description: "Cross-system customer domain",
  model_revision: 18,
  model_scope_object_count: 25,
  silver_model_naming_instructions: null,
  silver_model_audit_columns_template: null,
  gold_model_naming_instructions: null,
  gold_model_technical_columns_template: null,
  gold_model_audit_columns_template: null,
  default_agent_sdk_code: null,
  default_agent_provider_code: null,
  default_agent_model_code: null,
  default_reasoning_effort_code: null,
  default_max_turns: null,
  default_validation_retry_count: null,
  is_active: true,
  updated_at: "2026-08-24T14:00:00Z",
};

const modelScopePayload = {
  model_id: 18,
  model_revision: 18,
  items: [{
    model_scope_id: 101,
    object_id: 501,
    connection_id: 21,
    system_id: 31,
    system_code: "CRM",
    system_name: "Customer Relationship Management",
    source_tenant_id: 8,
    source_tenant_code: "GRDM",
    source_tenant_name: "Global Reference Data",
    object_schema: "bronze_crm",
    object_name: "customer_raw",
    zone_code: "bronze",
    batch_attribute_name: "batch_id",
    attribute_count: 12,
    is_bronze_source_eligible: true,
    is_dimensional_source_eligible: false,
    is_logical_mapping_target_eligible: false,
    is_dimensional_mapping_target_eligible: false,
    created_at: "2026-08-24T14:00:00Z",
    updated_at: "2026-08-24T14:00:00Z",
  }],
  next_cursor: null,
};

const profilingPagePayload = {
  model_id: 18,
  model_revision: 18,
  items: [{
    object_id: 501,
    source_tenant_id: 8,
    source_tenant_code: "GRDM",
    source_tenant_name: "Global Reference Data",
    system_id: 31,
    system_code: "CRM",
    system_name: "Customer Relationship Management",
    connection_id: 21,
    connection_code: "CRM_DBR",
    object_schema: "bronze_crm",
    object_name: "customer_raw",
    profiled_attribute_count: 12,
    last_profiled_at: "2026-08-24T14:00:00Z",
  }],
  next_cursor: null,
};

const profilingDetailPayload = {
  ...profilingPagePayload.items[0],
  model_id: 18,
  model_revision: 18,
  attribute_profiles: [{
    attribute_id: 601,
    attribute_name: "customer_id",
    attribute_ordinal_position: 1,
    attribute_data_type: "bigint",
    source_context_digest: "a".repeat(64),
    row_count: 10,
    non_null_count: 8,
    null_count: 2,
    blank_count: 0,
    distinct_count: 8,
    min_data_length: 1,
    max_data_length: 8,
    avg_data_length: "4.2",
    percent_populated: "80",
    percent_duplicates: "0",
    percent_null: "20",
    percent_blank: "0",
    percent_distinct: "100",
    provenance: { agent_run_id: null, workflow_run_id: 1048 },
    created_at: "2026-08-24T14:00:00Z",
    updated_at: "2026-08-24T14:00:00Z",
  }],
  profiles_truncated: false,
};

function profilingRunPayload(
  workflowRunId: number,
  workflowRunState: "queued" | "running" | "completed",
) {
  return {
    workflow_run_id: workflowRunId,
    model_workflow: "profiling",
    workflow_execution_mode: null,
    modeled_entity_type: null,
    selected_scope_count: 8,
    requested_batch_id: workflowRunId === 1048 ? "10428" : "10429",
    workflow_run_state: workflowRunState,
    actor_display_name: "Maaz",
    created_at: "2026-08-24T14:00:00Z",
    started_at: workflowRunState === "queued" ? null : "2026-08-24T14:00:01Z",
    completed_at: workflowRunState === "completed" ? "2026-08-24T14:01:12Z" : null,
  };
}

const runEventPayload = {
  sequence: 1,
  attempt: 1,
  stage: "prepare",
  status: "completed",
  message: "Prepare selected Objects",
  current: 8,
  total: 8,
  percent: "100",
  finding_count: 0,
  created_at: "2026-08-24T14:00:02Z",
};
