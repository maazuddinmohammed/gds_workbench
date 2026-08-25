import { render, screen, waitFor, within } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { createMemoryHistory } from "@tanstack/react-router";
import { describe, expect, it, vi } from "vitest";

import { createApiClient } from "../../api";
import { WorkbenchApp, createWorkbenchRouter } from "../../app";

describe("Model Analysis", () => {
  it("filters either relationship endpoint, selects findings, and opens full details", async () => {
    const fetcher = analysisFetchStub();
    const user = userEvent.setup();
    render(<WorkbenchApp router={analysisRouter(fetcher)} />);

    const ledger = await screen.findByRole("table", { name: "Analysis findings" });
    expect(within(ledger).getByText("customer_raw")).toBeVisible();
    expect(within(ledger).getByText("invoice_raw")).toBeVisible();

    await user.selectOptions(screen.getByLabelText("Object endpoint"), "501");
    await user.selectOptions(screen.getByLabelText("Validation state"), "unvalidated");
    await user.click(screen.getByRole("checkbox", { name: "Show inactive" }));
    await user.click(screen.getByRole("button", { name: "Apply finding filters" }));

    expect(fetcher).toHaveBeenCalledWith(
      "/api/v1/tenants/7/models/18/analysis?object_id=501&validation_state=unvalidated&show_inactive=true&page_size=200",
      expect.objectContaining({ credentials: "same-origin" }),
    );

    await screen.findByRole("table", { name: "Analysis findings" });
    await user.click(screen.getByRole("checkbox", { name: "Select finding 81" }));
    expect(screen.getByRole("button", { name: "Lock selected" })).toBeDisabled();
    expect(screen.getByText("Review updates are not available from the web API yet.")).toBeVisible();

    await user.click(screen.getByRole("link", { name: "Open finding 81" }));
    expect(await screen.findByRole("heading", { name: /customer_raw.*invoice_raw/i })).toBeVisible();
    expect(screen.getByText("Matched customer identifier semantics.")).toBeVisible();
    expect(screen.getByText("2 missing targets")).toBeVisible();
  });

  it("shows Analysis run history and creates explicit inference and validation queues", async () => {
    const fetcher = analysisFetchStub();
    const user = userEvent.setup();
    render(<WorkbenchApp router={analysisRouter(fetcher)} />);
    await screen.findByRole("table", { name: "Analysis findings" });

    await user.click(screen.getByRole("button", { name: "Runs" }));
    expect(await screen.findByRole("table", { name: "Analysis runs" })).toBeVisible();
    expect(screen.getByText("Inference")).toBeVisible();
    expect(screen.getByText("Validation")).toBeVisible();

    await user.click(screen.getByRole("button", { name: "Run inference" }));
    const inferenceDialog = await screen.findByRole("dialog", { name: "Configure Analysis inference" });
    await user.selectOptions(within(inferenceDialog).getByLabelText("Execution mode"), "tool_assisted");
    await user.click(within(inferenceDialog).getByRole("button", { name: "Create queued inference run" }));

    await waitFor(() => expect(fetcher).toHaveBeenCalledWith(
      "/api/v1/tenants/7/models/18/runs",
      expect.objectContaining({ method: "POST" }),
    ));
    const inferenceCall = fetcher.mock.calls.find(([, init]) => (
      init?.method === "POST" && String(init.body).includes('"workflow_execution_mode":"tool_assisted"')
    ));
    expect(JSON.parse(String(inferenceCall?.[1]?.body))).toEqual(expect.objectContaining({
      expected_model_revision: 18,
      model_workflow: "analysis",
      workflow_execution_mode: "tool_assisted",
      selected_object_ids: [501, 502],
      requested_batch_id: null,
      agent: expect.objectContaining({ model_code: "databricks-primary" }),
    }));

    await user.click(screen.getByRole("button", { name: "Validate pending" }));
    const validationDialog = await screen.findByRole("dialog", { name: "Configure Analysis validation" });
    await user.click(within(validationDialog).getByRole("button", { name: "Create queued validation run" }));
    const validationCall = fetcher.mock.calls.find(([, init]) => (
      init?.method === "POST" && String(init.body).includes('"workflow_execution_mode":null')
    ));
    expect(JSON.parse(String(validationCall?.[1]?.body))).toEqual(expect.objectContaining({
      model_workflow: "analysis",
      workflow_execution_mode: null,
      agent: null,
    }));
  });

  it("keeps empty, failed, and revision-mismatched results explicit", async () => {
    const emptyFetcher = analysisFetchStub({ empty: true });
    const emptyRouter = analysisRouter(emptyFetcher);
    const { unmount } = render(<WorkbenchApp router={emptyRouter} />);
    expect(await screen.findByText("No Analysis findings match these filters.")).toBeVisible();
    unmount();

    const mismatchFetcher = analysisFetchStub({ modelRevision: 19 });
    const mismatchRender = render(<WorkbenchApp router={analysisRouter(mismatchFetcher)} />);
    expect(await screen.findByRole("alert")).toHaveTextContent(
      "The Model changed while Analysis results were loading.",
    );
    mismatchRender.unmount();

    render(<WorkbenchApp router={analysisRouter(analysisFetchStub({ error: true }))} />);
    expect(await screen.findByRole("alert")).toHaveTextContent(
      "Analysis findings could not be loaded.",
    );
  });
});

function analysisRouter(fetcher: ReturnType<typeof analysisFetchStub>) {
  return createWorkbenchRouter({
    api: createApiClient(fetcher),
    history: createMemoryHistory({
      initialEntries: ["/tenants/7/models/18/analysis"],
    }),
  });
}

function analysisFetchStub(options: {
  empty?: boolean;
  error?: boolean;
  modelRevision?: number;
} = {}) {
  return vi.fn<typeof fetch>(async (input, init) => {
    const url = String(input);
    if (url === "/api/v1/tenants/7/home") return jsonResponse(tenantHomePayload);
    if (url === "/api/v1/tenants/7/models/18") return jsonResponse(modelPayload);
    if (url === "/api/v1/tenants/7/models/18/scope?zone=bronze&page_size=200") {
      return jsonResponse(scopePayload);
    }
    if (url.startsWith("/api/v1/tenants/7/models/18/analysis?") && init?.method !== "POST") {
      if (options.error) return jsonResponse({ error: { code: "unavailable" } }, 503);
      return jsonResponse({
        model_id: 18,
        model_revision: options.modelRevision ?? 18,
        items: options.empty ? [] : [analysisFindingPayload],
        next_cursor: null,
      });
    }
    if (url === "/api/v1/tenants/7/models/18/analysis/81") {
      return jsonResponse(analysisDetailPayload);
    }
    if (url.startsWith("/api/v1/tenants/7/models/18/runs?workflow=analysis")) {
      return jsonResponse({ items: analysisRunsPayload, next_cursor: null });
    }
    if (url === "/api/v1/config/agent-capabilities") return jsonResponse(capabilitiesPayload);
    if (url === "/api/v1/tenants/7/models/18/runs" && init?.method === "POST") {
      return jsonResponse({
        created: true,
        workflow_run_id: 1051,
        workflow_run_state: "queued",
        correlation_id: "bbbbbbbb-bbbb-bbbb-bbbb-bbbbbbbbbbbb",
        prompt_snapshot_count: 2,
        created_at: "2026-08-24T15:00:00Z",
      }, 201);
    }
    return jsonResponse({ error: { code: "not_found" } }, 404);
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
  lock_actions: { can_acquire: false, can_renew: true, can_release: true, can_override: false },
  systems: [],
};

const modelPayload = {
  model_id: 18,
  tenant_id: 7,
  model_name: "Customer 360",
  model_description: "Cross-system customer domain",
  model_revision: 18,
  model_scope_object_count: 2,
  silver_model_naming_instructions: null,
  silver_model_audit_columns_template: null,
  gold_model_naming_instructions: null,
  gold_model_technical_columns_template: null,
  gold_model_audit_columns_template: null,
  default_agent_sdk_code: "openai_agents",
  default_agent_provider_code: "databricks",
  default_agent_model_code: "databricks-primary",
  default_reasoning_effort_code: "medium",
  default_max_turns: 8,
  default_validation_retry_count: 1,
  is_active: true,
  updated_at: "2026-08-24T14:00:00Z",
};

const scopePayload = {
  model_id: 18,
  model_revision: 18,
  items: [
    scopeObject(501, "customer_raw", "CRM"),
    scopeObject(502, "invoice_raw", "ERP"),
  ],
  next_cursor: null,
};

function scopeObject(objectId: number, objectName: string, systemCode: string) {
  return {
    model_scope_id: objectId + 1000,
    object_id: objectId,
    connection_id: objectId + 2000,
    system_id: objectId + 3000,
    system_code: systemCode,
    system_name: `${systemCode} system`,
    source_tenant_id: 3,
    source_tenant_code: "GRDM",
    source_tenant_name: "Global Reference Data",
    object_schema: "bronze",
    object_name: objectName,
    zone_code: "bronze",
    attribute_count: 12,
    batch_attribute_name: "batch_id",
    is_bronze_source_eligible: true,
    is_dimensional_source_eligible: false,
    is_logical_mapping_target_eligible: false,
    is_dimensional_mapping_target_eligible: false,
    created_at: "2026-08-24T12:00:00Z",
    updated_at: "2026-08-24T12:00:00Z",
  };
}

const fromEndpoint = {
  object_id: 501,
  attribute_id: 601,
  source_tenant_id: 3,
  source_tenant_code: "GRDM",
  source_tenant_name: "Global Reference Data",
  system_id: 11,
  system_code: "CRM",
  system_name: "Customer Relationship Management",
  connection_id: 21,
  connection_code: "crm-prod",
  object_schema: "bronze",
  object_name: "customer_raw",
  attribute_name: "customer_id",
  attribute_data_type: "bigint",
};

const toEndpoint = {
  ...fromEndpoint,
  object_id: 502,
  attribute_id: 602,
  system_id: 12,
  system_code: "ERP",
  system_name: "Enterprise Resource Planning",
  connection_id: 22,
  connection_code: "erp-prod",
  object_name: "invoice_raw",
};

const analysisFindingPayload = {
  analysis_result_id: 81,
  from_endpoint: fromEndpoint,
  to_endpoint: toEndpoint,
  relationship_kind: "reference",
  relationship_confidence: "high",
  validation_state: "unvalidated",
  validation_result: null,
  status: "needs_review",
  is_locked: false,
  updated_at: "2026-08-24T14:20:00Z",
};

const analysisDetailPayload = {
  ...analysisFindingPayload,
  validation_state: "validated",
  validation_result: "supported",
  relationship_basis: "Matched customer identifier semantics.",
  relationship_basis_truncated: false,
  evidence: {
    validation_policy_version: "1.0.0",
    validation_policy_digest: "a".repeat(64),
    result: "supported",
    source_non_null_count: 100,
    source_distinct_count: 98,
    target_non_null_count: 100,
    target_distinct_count: 98,
    source_missing_target_count: 2,
    unused_target_count: 4,
    duplicate_target_key_count: 0,
  },
  provenance: {
    agent_run_id: null,
    inference_workflow_run_id: 1048,
    validation_workflow_run_id: 1049,
  },
  created_at: "2026-08-24T14:00:00Z",
};

const analysisRunsPayload = [
  {
    workflow_run_id: 1048,
    model_workflow: "analysis",
    workflow_execution_mode: "tool_assisted",
    modeled_entity_type: null,
    selected_scope_count: 2,
    requested_batch_id: null,
    workflow_run_state: "completed",
    actor_display_name: "Maaz",
    created_at: "2026-08-24T14:00:00Z",
    started_at: "2026-08-24T14:01:00Z",
    completed_at: "2026-08-24T14:02:00Z",
  },
  {
    workflow_run_id: 1049,
    model_workflow: "analysis",
    workflow_execution_mode: null,
    modeled_entity_type: null,
    selected_scope_count: 2,
    requested_batch_id: null,
    workflow_run_state: "completed",
    actor_display_name: "Maaz",
    created_at: "2026-08-24T14:10:00Z",
    started_at: "2026-08-24T14:11:00Z",
    completed_at: "2026-08-24T14:12:00Z",
  },
];

const capabilitiesPayload = {
  schema_version: "1.0",
  sdks: [{ code: "openai_agents", name: "OpenAI Agents SDK", provider_codes: ["databricks"] }],
  providers: [{ code: "databricks", name: "Databricks Model Serving" }],
  models: [{
    code: "databricks-primary",
    name: "GPT-5.6",
    provider_code: "databricks",
    sdk_codes: ["openai_agents"],
    reasoning_effort_codes: ["medium"],
  }],
  reasoning_efforts: [{ code: "medium", name: "Medium" }],
  max_turns: { minimum: 1, default: 8, maximum: 50 },
  validation_retries: { minimum: 0, default: 1, maximum: 5 },
};
