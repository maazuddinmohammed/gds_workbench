import { render, screen, waitFor, within } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { createMemoryHistory } from "@tanstack/react-router";
import { describe, expect, it, vi } from "vitest";

import { createApiClient } from "../../api";
import { WorkbenchApp, createWorkbenchRouter } from "../../app";
import { QALedger } from "./QALedger";
import { validateSelectedSystemCodes } from "./QARunDialog";
import type { QAValidationGroup } from "./api";

describe("QA journey", () => {
  it("opens from top-level navigation as a Model-first register", async () => {
    const fetcher = qaFetchStub();
    const user = userEvent.setup();
    render(<WorkbenchApp router={createWorkbenchRouter({
      api: createApiClient(fetcher),
      history: createMemoryHistory({ initialEntries: ["/tenants/7"] }),
    })} />);

    await user.click(await screen.findByRole("link", { name: "QA" }));

    const ledger = await screen.findByRole("table", { name: "Models for QA" });
    expect(within(ledger).getByText("Customer 360")).toBeVisible();
    expect(within(ledger).getByText("QA", { exact: true })).toBeVisible();
    expect(within(ledger).getByRole("link", { name: "Open Customer 360 QA" })).toHaveAttribute(
      "href",
      "/tenants/7/qa/models/18",
    );
  });

  it("groups applied Validation Checks and exposes authoritative digest currentness", async () => {
    const user = userEvent.setup();
    render(<WorkbenchApp router={createWorkbenchRouter({
      api: createApiClient(qaFetchStub()),
      history: createMemoryHistory({ initialEntries: ["/tenants/7/qa/models/18"] }),
    })} />);

    expect(await screen.findByRole("region", { name: "QA recent runs" })).toBeVisible();
    expect(await screen.findByText("Order reconciliation")).toBeVisible();
    expect(screen.getAllByText("Current")).not.toHaveLength(0);
    expect(screen.getByText("Mapping current")).toBeVisible();
    expect(screen.getAllByText("No Code context")).toHaveLength(3);
    expect(screen.getAllByTitle("a".repeat(64))[0]).toHaveTextContent("aaaaaaaaaaaa…");

    await user.click(screen.getByRole("button", { name: /Order reconciliation/ }));
    const checks = await screen.findByRole("table", {
      name: "Order reconciliation Validation Checks",
    });
    expect(within(checks).getByText("Source and target counts match")).toBeVisible();
    expect(within(checks).getByText("Equal Query B")).toBeVisible();
    await user.click(within(checks).getByRole("button", { name: "Show details" }));
    const detail = screen.getByRole("region", { name: "Source and target counts match details" });
    expect(detail).toHaveTextContent("SELECT COUNT(*) FROM bronze.orders");
    expect(detail).toHaveTextContent("SELECT COUNT(*) FROM silver.orders");
  });

  it("distinguishes absent, stale, and current Code from a missing current Mapping", () => {
    const base = validationGroups[0] as QAValidationGroup;
    const groups: QAValidationGroup[] = [
      { ...base, validation_group_id: 91, validation_group_name: "No Code", checks: [] },
      {
        ...base,
        validation_group_id: 92,
        validation_group_name: "Code appeared",
        code_context_digest: null,
        current_code_context_digest: "b".repeat(64),
        code_context_is_current: false,
        validation_group_is_current: false,
        checks: [],
      },
      {
        ...base,
        validation_group_id: 93,
        validation_group_name: "Code disappeared",
        code_context_digest: "c".repeat(64),
        current_code_context_digest: null,
        code_context_is_current: false,
        validation_group_is_current: false,
        checks: [],
      },
      {
        ...base,
        validation_group_id: 94,
        validation_group_name: "Missing current Mapping",
        code_context_digest: "d".repeat(64),
        current_code_context_digest: "d".repeat(64),
        current_mapping_context_digest: null,
        mapping_context_is_current: false,
        code_context_is_current: false,
        validation_group_is_current: false,
        checks: [],
      },
      {
        ...base,
        validation_group_id: 95,
        validation_group_name: "Current Code",
        code_context_digest: "e".repeat(64),
        current_code_context_digest: "e".repeat(64),
        code_context_is_current: true,
        checks: [],
      },
    ];
    render(<QALedger
      groups={groups}
      modelRevision={18}
      loadedModelRevision={18}
      isLoading={false}
      error={null}
    />);

    const noCode = screen.getByLabelText("No Code status");
    expect(within(noCode).getByText("Current")).toBeVisible();
    expect(within(noCode).getByText("No Code context")).toBeVisible();
    expect(within(noCode.closest("article") as HTMLElement).getAllByText("No Code context"))
      .toHaveLength(3);
    expect(within(screen.getByLabelText("Code appeared status")).getByText("Code stale"))
      .toBeVisible();
    expect(within(screen.getByLabelText("Code disappeared status")).getByText("Code stale"))
      .toBeVisible();
    expect(within(screen.getByLabelText("Current Code status")).getByText("Code current"))
      .toBeVisible();
    const missingMapping = screen.getByLabelText("Missing current Mapping status");
    expect(within(missingMapping).getByText("Code stale")).toBeVisible();
    expect(within(missingMapping).getByText("No current Mapping")).toBeVisible();
    expect(within(missingMapping.closest("article") as HTMLElement).getByText(
      "No current Mapping context",
    )).toBeVisible();
  });

  it("selects exact Systems and starts fixed-profile QA through a governed draft run", async () => {
    const fetcher = qaFetchStub();
    const user = userEvent.setup();
    render(<WorkbenchApp router={createWorkbenchRouter({
      api: createApiClient(fetcher),
      history: createMemoryHistory({ initialEntries: ["/tenants/7/qa/models/18"] }),
    })} />);

    const runButton = await screen.findByRole("button", { name: "Run QA" });
    await user.click(runButton);
    const dialog = await screen.findByRole("dialog", { name: "Configure QA run" });
    expect(within(dialog).getByRole("button", { name: "Close Configure QA run" })).toHaveFocus();
    expect(within(dialog).getByText("Detailed coverage · fixed")).toBeVisible();
    const submit = within(dialog).getByRole("button", { name: "Create and start QA" });
    expect(submit).toBeDisabled();

    await user.click(within(dialog).getByRole("checkbox", { name: /Customer CRM/ }));
    expect(within(dialog).getByText("1 of 2 Systems selected")).toBeVisible();
    await user.click(submit);

    expect(await screen.findByText(
      "QA run 2251 started. Refresh runs to review the draft, then Apply the validated draft.",
    )).toBeVisible();
    const create = fetcher.mock.calls.find(([input, init]) => (
      String(input) === "/api/v1/tenants/7/models/18/runs" && init?.method === "POST"
    ));
    expect(JSON.parse(String(create?.[1]?.body))).toEqual({
      expected_model_revision: 18,
      model_workflow: "qa",
      workflow_execution_mode: null,
      selected_object_ids: [],
      selected_system_codes: ["CRM"],
      modeled_entity_type: null,
      requested_batch_id: null,
      agent: {
        sdk_code: "openai_agents",
        provider_code: "databricks",
        model_code: "databricks-primary",
        reasoning_effort_code: "medium",
        max_turns: 8,
        validation_retry_count: 1,
      },
      prompt_overrides: {},
    });
    expect(fetcher).toHaveBeenCalledWith(
      "/api/v1/tenants/7/models/18/qa/runs/2251/execute",
      expect.objectContaining({
        method: "POST",
        body: JSON.stringify({ expected_model_revision: 18 }),
      }),
    );
  });

  it("traps focus, closes with Escape, and restores the QA trigger", async () => {
    const user = userEvent.setup();
    render(<WorkbenchApp router={createWorkbenchRouter({
      api: createApiClient(qaFetchStub()),
      history: createMemoryHistory({ initialEntries: ["/tenants/7/qa/models/18"] }),
    })} />);
    const runButton = await screen.findByRole("button", { name: "Run QA" });
    await user.click(runButton);
    const dialog = await screen.findByRole("dialog", { name: "Configure QA run" });
    const close = within(dialog).getByRole("button", { name: "Close Configure QA run" });
    const cancel = within(dialog).getByRole("button", { name: "Cancel" });
    expect(close).toHaveFocus();
    await user.tab({ shift: true });
    expect(cancel).toHaveFocus();
    await user.tab();
    expect(close).toHaveFocus();
    await user.keyboard("{Escape}");
    expect(screen.queryByRole("dialog", { name: "Configure QA run" })).not.toBeInTheDocument();
    await waitFor(() => expect(runButton).toHaveFocus());
  });

  it("keeps empty, denied, error, and revision-drift states explicit", async () => {
    const empty = renderQA(qaFetchStub({ empty: true }));
    expect(await screen.findByText(
      "No Validation Groups are applied to this Model. Run QA to author the first draft.",
    )).toBeVisible();
    expect(screen.getByRole("button", { name: "Run QA" })).toBeDisabled();
    empty.unmount();

    const denied = renderQA(qaFetchStub({ denied: true }));
    expect(await screen.findByText("You do not have permission to view applied QA validations.")).toBeVisible();
    expect(screen.getByText("You do not have permission to load eligible QA Systems.")).toBeVisible();
    denied.unmount();

    const drift = renderQA(qaFetchStub({ modelRevision: 19 }));
    expect(await screen.findByText(
      "The Model changed while the QA ledger was loading. Refresh before authoring QA.",
    )).toBeVisible();
    expect(screen.getByText(
      "The Model changed while eligible QA Systems were loading. Refresh before starting a run.",
    )).toBeVisible();
    drift.unmount();

    renderQA(qaFetchStub({ error: true }));
    expect(await screen.findByText("Applied QA validations could not be loaded. Refresh to try again.")).toBeVisible();
    expect(screen.queryByText("secret physical row")).not.toBeInTheDocument();
    expect(screen.getByRole("button", { name: "Run QA" })).toHaveAttribute(
      "title",
      "Eligible QA Systems are unavailable; refresh to try again",
    );
  });

  it("rejects empty and case-insensitive duplicate System-code selections", () => {
    expect(validateSelectedSystemCodes([])).toBeNull();
    expect(validateSelectedSystemCodes([" "])).toBeNull();
    expect(validateSelectedSystemCodes(["CRM", " crm "])).toBeNull();
    expect(validateSelectedSystemCodes([" CRM ", "ERP"])).toEqual(["CRM", "ERP"]);
  });
});

function renderQA(fetcher: ReturnType<typeof vi.fn<typeof fetch>>) {
  return render(<WorkbenchApp router={createWorkbenchRouter({
    api: createApiClient(fetcher),
    history: createMemoryHistory({ initialEntries: ["/tenants/7/qa/models/18"] }),
  })} />);
}

function qaFetchStub(options: {
  empty?: boolean;
  denied?: boolean;
  error?: boolean;
  modelRevision?: number;
} = {}) {
  return vi.fn<typeof fetch>(async (input, init) => {
    const url = String(input);
    if (url === "/api/v1/tenants/7/home") return jsonResponse(tenantHome);
    if (url === "/api/v1/tenants/7/models?status=active&page_size=200") {
      return jsonResponse({ items: [modelLedger], next_cursor: null });
    }
    if (url === "/api/v1/tenants/7/models/18") return jsonResponse(modelDetail);
    if (url === "/api/v1/tenants/7/models/18/qa/systems") {
      if (options.denied) return jsonResponse({ error: { code: "authorization_denied" } }, 403);
      if (options.error) return new Response("secret physical row", { status: 503 });
      return jsonResponse({
        model_id: 18,
        model_revision: options.modelRevision ?? 18,
        items: options.empty ? [] : eligibleSystems,
        is_truncated: false,
      });
    }
    if (url === "/api/v1/tenants/7/models/18/qa/ledger") {
      if (options.denied) return jsonResponse({ error: { code: "authorization_denied" } }, 403);
      if (options.error) return new Response("secret physical row", { status: 503 });
      return jsonResponse({
        model_id: 18,
        model_revision: options.modelRevision ?? 18,
        groups: options.empty ? [] : validationGroups,
      });
    }
    if (url === "/api/v1/config/agent-capabilities") return jsonResponse(agentCapabilities);
    if (url === "/api/v1/tenants/7/models/18/runs?workflow=qa&page_size=5") {
      return jsonResponse({ items: [], next_cursor: null });
    }
    if (url === "/api/v1/tenants/7/models/18/runs" && init?.method === "POST") {
      return jsonResponse({
        created: true,
        workflow_run_id: 2251,
        workflow_run_state: "queued",
        correlation_id: "qa-run-2251",
        prompt_snapshot_count: 4,
        created_at: "2026-08-31T10:00:00Z",
      }, 201);
    }
    if (url === "/api/v1/tenants/7/models/18/qa/runs/2251/execute") {
      return jsonResponse({
        changed: true,
        workflow_run_id: 2251,
        workflow_run_state: "running",
        model_revision: 18,
      }, 202);
    }
    if (url === "/api/v1/tenants/7/models/18/runs/2251") {
      return jsonResponse(runningRun);
    }
    if (url === "/api/v1/tenants/7/models/18/runs/2251/events?after_sequence=0&page_size=200") {
      return jsonResponse({ items: [], next_after_sequence: 0 });
    }
    return new Response(null, { status: 404 });
  });
}

function jsonResponse(value: unknown, status = 200): Response {
  return new Response(JSON.stringify(value), {
    status,
    headers: { "content-type": "application/json" },
  });
}

const tenantHome = {
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
    purpose: "QA review",
    acquired_at: "2026-08-31T09:00:00Z",
    expires_at: "2026-08-31T12:00:00Z",
  },
  lock_actions: { can_acquire: false, can_renew: true, can_release: true, can_override: false },
  systems: [],
};

const modelLedger = {
  model_id: 18,
  model_name: "Customer 360",
  model_description: "Cross-system customer domain",
  model_revision: 18,
  model_scope_object_count: 25,
  latest_workflow: "qa",
  latest_run_status: "completed",
  updated_at: "2026-08-31T09:00:00Z",
};

const modelDetail = {
  ...modelLedger,
  tenant_id: 7,
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
};

const eligibleSystems = [
  {
    system_id: 2,
    system_code: "CRM",
    system_name: "Customer CRM",
    mapping_target_count: 3,
    current_code_target_count: 2,
    has_applied_qa: true,
  },
  {
    system_id: 3,
    system_code: "ERP",
    system_name: "Order ERP",
    mapping_target_count: 4,
    current_code_target_count: 0,
    has_applied_qa: false,
  },
];

const validationGroups = [{
  validation_group_id: 91,
  system_id: 2,
  system_code: "CRM",
  validation_group_name: "Order reconciliation",
  validation_group_description: "Source and target counts reconcile.",
  mapping_context_digest: "a".repeat(64),
  code_context_digest: null,
  current_mapping_context_digest: "a".repeat(64),
  current_code_context_digest: null,
  mapping_context_is_current: true,
  code_context_is_current: true,
  validation_group_is_current: true,
  is_active: true,
  checks: [{
    validation_check_id: 301,
    validation_check_name: "Source and target counts match",
    validation_check_description: "Counts must match after processing.",
    validation_category_code: "reconciliation.counts",
    validation_severity: "blocking",
    validation_query_sql: "SELECT COUNT(*) FROM bronze.orders",
    validation_comparison_query_sql: "SELECT COUNT(*) FROM silver.orders",
    validation_result_data_type: "integer",
    validation_comparison_operator: "equal",
    validation_comparison_value_type: "query",
    validation_comparison_value: null,
    is_active: true,
  }],
}];

const agentCapabilities = {
  schema_version: "3.0",
  sdks: [{ code: "openai_agents", name: "OpenAI Agents", provider_codes: ["databricks"] }],
  providers: [{ code: "databricks", name: "Databricks Model Serving" }],
  models: [{
    code: "databricks-primary",
    name: "GPT-5.6",
    provider_code: "databricks",
    deployment_name: "databricks-primary",
    execution_profiles: [{
      sdk_code: "openai_agents",
      execution_mode: "detailed_coverage",
      reasoning_effort_codes: ["medium"],
    }],
  }],
  reasoning_efforts: [{ code: "medium", name: "Medium" }],
  max_turns: { minimum: 1, default: 8, maximum: 50 },
  validation_retries: { minimum: 0, default: 1, maximum: 5 },
};

const runningRun = {
  workflow_run_id: 2251,
  model_workflow: "qa",
  workflow_execution_mode: "detailed_coverage",
  modeled_entity_type: null,
  selected_scope_count: 1,
  requested_batch_id: null,
  workflow_run_state: "running",
  actor_display_name: "Maaz",
  created_at: "2026-08-31T10:00:00Z",
  started_at: "2026-08-31T10:00:01Z",
  completed_at: null,
  correlation_id: "qa-run-2251",
  agent_sdk_code: "openai_agents",
  agent_provider_code: "databricks",
  agent_model_code: "databricks-primary",
  reasoning_effort_code: "medium",
  max_turns: 8,
  validation_retry_count: 1,
  failure_code: null,
  failure_message: null,
  model_change_set_id: null,
  model_change_set_status: null,
  draft_revision: null,
  candidate_digest: null,
  validated_at: null,
};
