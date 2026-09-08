import { withRecordReview } from "../../test/modelRecordReview";
import { render, screen, waitFor, within } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { createMemoryHistory } from "@tanstack/react-router";
import { describe, expect, it, vi } from "vitest";

import { createApiClient } from "../../api";
import { WorkbenchApp, createWorkbenchRouter } from "../../app";
import { validateSelectedSystemCodes } from "./ValidationRunDialog";
import type { ValidationValidationGroup } from "./api";

describe("Validation journey", () => {
  it("opens from top-level navigation as a Model-first register", async () => {
    const fetcher = validationFetchStub();
    const user = userEvent.setup();
    render(<WorkbenchApp router={createWorkbenchRouter({
      api: createApiClient(fetcher),
      history: createMemoryHistory({ initialEntries: ["/tenants/7"] }),
    })} />);

    await user.click(await screen.findByRole("link", { name: "Validation" }));

    const ledger = await screen.findByRole("table", { name: "Models for Validation" });
    expect(within(ledger).getByText("Customer 360")).toBeVisible();
    expect(within(ledger).getByText("Validation", { exact: true })).toBeVisible();
    expect(within(ledger).getByRole("link", { name: "Open Customer 360 Validation" })).toHaveAttribute(
      "href",
      "/tenants/7/validation/models/18",
    );
  });

  it("navigates Groups → Checks → SQL with page URLs and keyboard access", async () => {
    const user = userEvent.setup();
    const history = createMemoryHistory({ initialEntries: ["/tenants/7/validation/models/18"] });
    render(<WorkbenchApp router={createWorkbenchRouter({ api: createApiClient(validationFetchStub()), history })} />);

    const groups = await screen.findByRole("table", { name: "Validation Groups" });
    expect(within(groups).getByText("Mapping current")).toBeVisible();
    expect(within(groups).getByText("Code current")).toBeVisible();
    expect(screen.queryByText("Source and target counts match")).not.toBeInTheDocument();
    const groupLink = within(groups).getByRole("link", { name: "Show details for Order reconciliation" });
    groupLink.focus();
    await user.keyboard("{Enter}");
    const checks = await screen.findByRole("table", { name: "Order reconciliation Validation Checks" });
    expect(history.location.pathname).toBe("/tenants/7/validation/models/18/groups/91");
    expect(screen.queryByRole("table", { name: "Validation Groups" })).not.toBeInTheDocument();
    expect(within(checks).getByText("Equal Query B")).toBeVisible();
    expect(screen.queryByText("SELECT COUNT(*) FROM bronze.orders")).not.toBeInTheDocument();
    await user.click(within(checks).getByRole("link", { name: "Show details for Source and target counts match" }));
    const detail = await screen.findByRole("region", { name: "Source and target counts match details" });
    expect(history.location.pathname).toBe("/tenants/7/validation/models/18/groups/91/checks/301");
    expect(detail).toHaveTextContent("SELECT COUNT(*) FROM bronze.orders");
    expect(detail).toHaveTextContent("SELECT COUNT(*) FROM silver.orders");
    expect(screen.getByRole("heading", { name: "Source and target counts match" })).toHaveFocus();
    expect(screen.queryByRole("table")).not.toBeInTheDocument();
    expect(screen.getByText(/execution results are not recorded here/)).toBeVisible();
    await user.click(screen.getByRole("link", { name: "Back to Checks" }));
    expect(await screen.findByRole("table", { name: "Order reconciliation Validation Checks" })).toBeVisible();
    await user.click(screen.getByRole("link", { name: "Back to Groups" }));
    expect(await screen.findByRole("table", { name: "Validation Groups" })).toBeVisible();
    history.back();
    expect(await screen.findByRole("table", { name: "Order reconciliation Validation Checks" })).toBeVisible();
  });

  it.each([
    ["/groups/999", "This Validation Group is not available in this Model."],
    ["/groups/91/checks/999", "This Validation Check is not available in this Group."],
    ["/groups/92/checks/301", "This Validation Check is not available in this Group."],
  ])("keeps missing or unrelated detail routes inside their scope (%s)", async (path, message) => {
    renderValidation(validationFetchStub({ groups: [...validationGroups, { ...validationGroups[0]!, validation_group_id: 92, checks: [] }] }), path);
    expect(await screen.findByText(message)).toBeVisible();
    expect(screen.queryByText("SELECT COUNT(*) FROM bronze.orders")).not.toBeInTheDocument();
    expect(screen.getByRole("link", { name: /Back to (Checks|Groups)/ })).toBeVisible();
  });

  it("distinguishes stale and current Code and Mapping", async () => {
    const base = validationGroups[0] as ValidationValidationGroup;
    const groups: ValidationValidationGroup[] = [
      {
        ...base,
        validation_group_id: 93,
        validation_group_name: "Stale Code",
        code_context_is_current: false,
        validation_group_is_current: false,
        checks: [],
      },
      {
        ...base,
        validation_group_id: 94,
        validation_group_name: "Stale Mapping",
        mapping_context_is_current: false,
        code_context_is_current: false,
        validation_group_is_current: false,
        checks: [],
      },
      {
        ...base,
        validation_group_id: 95,
        validation_group_name: "Current Code",
        code_context_is_current: true,
        checks: [],
      },
    ];
    renderValidation(validationFetchStub({ groups }));
    await screen.findByRole("table", { name: "Validation Groups" });

    expect(within(screen.getByLabelText("Stale Code status")).getByText("Code stale"))
      .toBeVisible();
    expect(within(screen.getByLabelText("Current Code status")).getByText("Code current"))
      .toBeVisible();
    const missingMapping = screen.getByLabelText("Stale Mapping status");
    expect(within(missingMapping).getByText("Code stale")).toBeVisible();
    expect(within(missingMapping).getByText("Mapping stale")).toBeVisible();
  });

  it.each([0, false, "", [0, false, ""]])("preserves literal operands (%j) before SQL", async (value) => {
    const base = validationGroups[0]!;
    const group = { ...base, checks: [{ ...base.checks[0]!, validation_comparison_value_type: Array.isArray(value) ? "literal_list" : "literal", validation_comparison_value: value, validation_comparison_query_sql: null }] } as ValidationValidationGroup;
    renderValidation(validationFetchStub({ groups: [group] }), "/groups/91/checks/301");
    const detail = await screen.findByRole("region", { name: "Source and target counts match details" });
    expect(within(detail).getByText("Comparison value").nextElementSibling?.textContent).toBe(JSON.stringify(value));
    expect(within(detail).queryByText("Query B")).not.toBeInTheDocument();
  });

  it("selects exact Systems and starts fixed-profile Validation through a governed draft run", async () => {
    const fetcher = validationFetchStub();
    const user = userEvent.setup();
    render(<WorkbenchApp router={createWorkbenchRouter({
      api: createApiClient(fetcher),
      history: createMemoryHistory({ initialEntries: ["/tenants/7/validation/models/18"] }),
    })} />);

    const runButton = await screen.findByRole("button", { name: "Run Validation" });
    await user.click(runButton);
    const dialog = await screen.findByRole("dialog", { name: "Configure Validation run" });
    expect(within(dialog).getByRole("button", { name: "Close Configure Validation run" })).toHaveFocus();
    expect(within(dialog).getByText("The prompt template configures the available context tools.")).toBeVisible();
    const submit = within(dialog).getByRole("button", { name: "Create and start Validation" });
    expect(submit).toBeDisabled();

    await user.click(within(dialog).getByRole("checkbox", { name: /Customer CRM/ }));
    expect(within(dialog).getByText("1 of 2 Systems selected")).toBeVisible();
    await user.click(submit);

    expect(await screen.findByText(
      "Validation run 2251 started. Refresh runs to review the draft, then Apply the validated draft.",
    )).toBeVisible();
    const create = fetcher.mock.calls.find(([input, init]) => (
      String(input) === "/api/v1/tenants/7/models/18/runs" && init?.method === "POST"
    ));
    expect(JSON.parse(String(create?.[1]?.body))).toEqual({
      expected_model_revision: 18,
      model_workflow: "validation",
      workflow_execution_mode: null,
      selected_object_ids: [],
      selected_system_codes: ["CRM"],
      modeled_entity_type: null,
      requested_batch_id: null,
      agent: {
        sdk_code: "openai_agents_sdk",
        provider_code: "microsoft_foundry",
        model_code: "foundry-primary",
        reasoning_effort_code: "medium",
        max_turns: 8,
        validation_retry_count: 1,
      },
      prompt_overrides: {},
    });
    expect(fetcher).toHaveBeenCalledWith(
      "/api/v1/tenants/7/models/18/validation/runs/2251/execute",
      expect.objectContaining({
        method: "POST",
        body: JSON.stringify({ expected_model_revision: 18 }),
      }),
    );
  });

  it.each(["network", "server"] as const)("retries an ambiguous Validation %s create with the original command and key", async (failure) => {
    const success = validationFetchStub();
    let attempts = 0;
    const fetcher = vi.fn<typeof fetch>(async (input, init) => {
      if (String(input) === "/api/v1/tenants/7/models/18/runs" && init?.method === "POST" && ++attempts === 1) {
        if (failure === "network") throw new TypeError("Synthetic network failure");
        return jsonResponse({ error: { code: "unavailable" } }, 503);
      }
      return success(input, init);
    });
    const user = userEvent.setup();
    render(<WorkbenchApp router={createWorkbenchRouter({
      api: createApiClient(fetcher),
      history: createMemoryHistory({ initialEntries: ["/tenants/7/validation/models/18"] }),
    })} />);
    await screen.findByRole("button", { name: "Run Validation" });
    await waitFor(() => expect(screen.getByRole("button", { name: "Run Validation" })).toBeEnabled());
    await user.click(screen.getByRole("button", { name: "Run Validation" }));
    await screen.findByRole("dialog", { name: "Configure Validation run" });
    await user.click(screen.getByRole("checkbox", { name: /Customer CRM/ }));
    const submit = await screen.findByRole("button", { name: "Create and start Validation" });
    await waitFor(() => expect(submit).toBeEnabled());
    for (const label of ["Agent SDK", "Provider", "Maximum turns", "Validation retries"]) {
      expect(screen.queryByLabelText(label)).not.toBeInTheDocument();
    }
    await user.click(submit);
    await screen.findByRole("alert");
    expect(screen.getByLabelText("Model")).toBeEnabled();
    await user.click(submit);
    await waitFor(() => expect(screen.queryByRole("dialog")).not.toBeInTheDocument());
    const creates = fetcher.mock.calls.filter(([input, init]) =>
      String(input) === "/api/v1/tenants/7/models/18/runs" && init?.method === "POST");
    expect(creates).toHaveLength(2);
    expect(creates[1]?.[1]?.body).toBe(creates[0]?.[1]?.body);
    const firstKey = new Headers(creates[0]?.[1]?.headers).get("Idempotency-Key");
    expect(firstKey).toMatch(/^[a-f0-9-]{36}$/);
    expect(new Headers(creates[1]?.[1]?.headers).get("Idempotency-Key")).toBe(firstKey);
  });

  it("uses tool-supported model and reasoning profiles while keeping the public mode unset", async () => {
    const success = validationFetchStub();
    const fetcher = vi.fn<typeof fetch>(async (input, init) => {
      if (String(input) === "/api/v1/config/agent-capabilities") return jsonResponse({
        ...agentCapabilities,
        models: [...agentCapabilities.models, { ...agentCapabilities.models[0],
          code: "foundry-alternate", name: "Alternate Foundry model",
          execution_profiles: [
            { sdk_code: "openai_agents_sdk", execution_mode: "one_shot", reasoning_effort_codes: ["medium"] },
            { sdk_code: "openai_agents_sdk", execution_mode: "tool_assisted", reasoning_effort_codes: ["high"] },
          ],
        }],
        reasoning_efforts: [...agentCapabilities.reasoning_efforts, { code: "high", name: "High" }],
      });
      return success(input, init);
    });
    const user = userEvent.setup();
    renderValidation(fetcher);
    await waitFor(() => expect(screen.getByRole("button", { name: "Run Validation" })).toBeEnabled());
    await user.click(screen.getByRole("button", { name: "Run Validation" }));
    const dialog = await screen.findByRole("dialog", { name: "Configure Validation run" });
    await waitFor(() => expect(within(dialog).getByLabelText("Model")).toHaveValue("foundry-primary"));
    await user.selectOptions(within(dialog).getByLabelText("Model"), "foundry-alternate");
    expect(within(within(dialog).getByLabelText("Reasoning effort")).queryByRole("option", { name: "Medium" })).not.toBeInTheDocument();
    await user.selectOptions(within(dialog).getByLabelText("Reasoning effort"), "high");
    expect(within(dialog).queryByLabelText("Execution mode")).not.toBeInTheDocument();
    await user.click(within(dialog).getByRole("checkbox", { name: /Customer CRM/ }));
    await user.click(within(dialog).getByRole("button", { name: "Create and start Validation" }));
    await waitFor(() => expect(screen.queryByRole("dialog")).not.toBeInTheDocument());
    const create = fetcher.mock.calls.find(([input, init]) =>
      String(input) === "/api/v1/tenants/7/models/18/runs" && init?.method === "POST");
    expect(JSON.parse(String(create?.[1]?.body))).toMatchObject({
      workflow_execution_mode: null, selected_system_codes: ["CRM"], agent: {
        sdk_code: "openai_agents_sdk", provider_code: "microsoft_foundry",
        model_code: "foundry-alternate", reasoning_effort_code: "high",
      },
    });
  });

  it("traps focus, closes with Escape, and restores the Validation trigger", async () => {
    const user = userEvent.setup();
    render(<WorkbenchApp router={createWorkbenchRouter({
      api: createApiClient(validationFetchStub()),
      history: createMemoryHistory({ initialEntries: ["/tenants/7/validation/models/18"] }),
    })} />);
    const runButton = await screen.findByRole("button", { name: "Run Validation" });
    await user.click(runButton);
    const dialog = await screen.findByRole("dialog", { name: "Configure Validation run" });
    const close = within(dialog).getByRole("button", { name: "Close Configure Validation run" });
    const cancel = within(dialog).getByRole("button", { name: "Cancel" });
    expect(close).toHaveFocus();
    await user.tab({ shift: true });
    expect(cancel).toHaveFocus();
    await user.tab();
    expect(close).toHaveFocus();
    await user.keyboard("{Escape}");
    expect(screen.queryByRole("dialog", { name: "Configure Validation run" })).not.toBeInTheDocument();
    await waitFor(() => expect(runButton).toHaveFocus());
  });

  it("keeps empty, denied, error, and revision-drift states explicit", async () => {
    const empty = renderValidation(validationFetchStub({ empty: true }));
    expect(await screen.findByText(
      "No Validation Groups are applied to this Model. Run Validation to author the first draft.",
    )).toBeVisible();
    expect(screen.getByRole("button", { name: "Run Validation" })).toBeDisabled();
    empty.unmount();

    const denied = renderValidation(validationFetchStub({ denied: true }));
    expect(await screen.findByText("You do not have permission to view applied Validation definitions.")).toBeVisible();
    expect(screen.getByText("You do not have permission to load eligible Validation Systems.")).toBeVisible();
    denied.unmount();

    const drift = renderValidation(validationFetchStub({ modelRevision: 19 }));
    expect(await screen.findByText(
      "The Model changed while the Validation ledger was loading. Refresh before authoring Validation.",
    )).toBeVisible();
    expect(screen.getByText(
      "The Model changed while eligible Validation Systems were loading. Refresh before starting a run.",
    )).toBeVisible();
    drift.unmount();

    renderValidation(validationFetchStub({ error: true }));
    expect(await screen.findByText("Applied Validation definitions could not be loaded. Refresh to try again.")).toBeVisible();
    expect(screen.queryByText("secret physical row")).not.toBeInTheDocument();
    expect(screen.getByRole("button", { name: "Run Validation" })).toHaveAttribute(
      "title",
      "Eligible Validation Systems are unavailable; refresh to try again",
    );
  });

  it("rejects empty and case-insensitive duplicate System-code selections", () => {
    expect(validateSelectedSystemCodes([])).toBeNull();
    expect(validateSelectedSystemCodes([" "])).toBeNull();
    expect(validateSelectedSystemCodes(["CRM", " crm "])).toBeNull();
    expect(validateSelectedSystemCodes([" CRM ", "ERP"])).toEqual(["CRM", "ERP"]);
  });
});

function renderValidation(fetcher: ReturnType<typeof vi.fn<typeof fetch>>, path = "") {
  return render(<WorkbenchApp router={createWorkbenchRouter({
    api: createApiClient(fetcher),
    history: createMemoryHistory({ initialEntries: [`/tenants/7/validation/models/18${path}`] }),
  })} />);
}

function validationFetchStub(options: {
  groups?: ValidationValidationGroup[];
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
    if (url === "/api/v1/tenants/7/models/18/validation/systems") {
      if (options.denied) return jsonResponse({ error: { code: "authorization_denied" } }, 403);
      if (options.error) return new Response("secret physical row", { status: 503 });
      return jsonResponse({
        model_id: 18,
        model_revision: options.modelRevision ?? 18,
        items: options.empty ? [] : eligibleSystems,
        is_truncated: false,
      });
    }
    if (url === "/api/v1/tenants/7/models/18/validation/ledger") {
      if (options.denied) return jsonResponse({ error: { code: "authorization_denied" } }, 403);
      if (options.error) return new Response("secret physical row", { status: 503 });
      return jsonResponse({
        model_id: 18,
        model_revision: options.modelRevision ?? 18,
        groups: options.empty ? [] : options.groups ?? validationGroups,
      });
    }
    if (url === "/api/v1/config/agent-capabilities") return jsonResponse(agentCapabilities);
    if (url === "/api/v1/tenants/7/models/18/runs?workflow=validation&page_size=5") {
      return jsonResponse({ items: [], next_cursor: null });
    }
    if (url === "/api/v1/tenants/7/models/18/runs" && init?.method === "POST") {
      return jsonResponse({
        created: true,
        workflow_run_id: 2251,
        workflow_run_state: "queued",
        correlation_id: "validation-run-2251",
        prompt_snapshot_count: 4,
        created_at: "2026-08-31T10:00:00Z",
      }, 201);
    }
    if (url === "/api/v1/tenants/7/models/18/validation/runs/2251/execute") {
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
    purpose: "Validation review",
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
  model_input_scope_object_count: 25,
  latest_workflow: "validation",
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
    has_applied_validation: true,
  },
  {
    system_id: 3,
    system_code: "ERP",
    system_name: "Order ERP",
    mapping_target_count: 4,
    current_code_target_count: 0,
    has_applied_validation: false,
  },
];

const validationGroups: ValidationValidationGroup[] = [{
  is_locked: false,
  validation_group_id: 91,
  system_id: 2,
  system_code: "CRM",
  validation_group_name: "Order reconciliation",
  validation_group_description: "Source and target counts reconcile.",
  mapping_context_is_current: true,
  code_context_is_current: true,
  validation_group_is_current: true,
  is_active: true,
  checks: [{
    is_locked: false,
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
  sdks: [{ code: "openai_agents_sdk", name: "OpenAI Agents", provider_codes: ["microsoft_foundry"] }],
  providers: [{ code: "microsoft_foundry", name: "Microsoft Foundry" }],
  models: [{
    code: "foundry-primary",
    name: "GPT-5.6",
    provider_code: "microsoft_foundry",
    deployment_name: "foundry-primary",
    execution_profiles: [{
      sdk_code: "openai_agents_sdk",
      execution_mode: "tool_assisted",
      reasoning_effort_codes: ["medium"],
    }],
  }],
  reasoning_efforts: [{ code: "medium", name: "Medium" }],
  max_turns: { minimum: 1, default: 8, maximum: 50 },
  validation_retries: { minimum: 0, default: 1, maximum: 5 },
};

const runningRun = {
  workflow_run_id: 2251,
  model_workflow: "validation",
  workflow_execution_mode: "one_shot",
  modeled_entity_type: null,
  selected_scope_count: 1,
  requested_batch_id: null,
  workflow_run_state: "running",
  actor_display_name: "Maaz",
  created_at: "2026-08-31T10:00:00Z",
  started_at: "2026-08-31T10:00:01Z",
  completed_at: null,
  correlation_id: "validation-run-2251",
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


it.each([["Groups", "validation_group", 91], ["Checks", "validation_check", 301]] as const)(
  "reviews selected Validation %s", async (kind, dataset, id) => {
    const { fetcher, commands } = withRecordReview(validationFetchStub());
    render(<WorkbenchApp router={createWorkbenchRouter({ api: createApiClient(fetcher),
      history: createMemoryHistory({ initialEntries: ["/tenants/7/validation/models/18"] }),
    })} />);
    const user = userEvent.setup();
    if (kind === "Checks") await user.click(await screen.findByRole("link", { name: "Show details for Order reconciliation" }));
    await user.click(await screen.findByRole("checkbox", { name: `Select Validation ${kind === "Groups" ? "Group" : "Check"} ${id}` }));
    await user.click(screen.getByRole("button", { name: "Lock selected" }));
    await user.click(await screen.findByRole("button", { name: "Apply this change" }));
    expect(commands[0]).toEqual({ dataset, record_ids: [id], action: "lock", expected_model_revision: 18 });
    expect(commands[1]?.expected_plan_digest).toBe("c".repeat(64));
  },
);
