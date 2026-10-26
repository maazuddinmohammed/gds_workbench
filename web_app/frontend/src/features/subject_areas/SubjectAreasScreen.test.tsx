import { render, screen, waitFor, within } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { createMemoryHistory } from "@tanstack/react-router";
import { describe, expect, it, vi } from "vitest";

import { createApiClient } from "../../api";
import { WorkbenchApp, createWorkbenchRouter } from "../../app";

describe("Project Subject Areas", () => {
  it("lists areas with plain Object and Attribute counts and an Open button", async () => {
    renderAt("/tenants/7/projects/18/subject-areas", subjectAreaFetchStub());
    const ledger = await screen.findByRole("table", { name: "Subject Areas" });
    expect(within(ledger).getAllByRole("columnheader").map((cell) => cell.textContent)).toEqual([
      "", "Subject Area", "Objects", "Attributes", "Status", "Lock", "Updated", "Actions",
    ]);
    const sales = within(ledger).getByRole("row", { name: /Sales/ });
    expect(within(sales).queryByRole("link", { name: "Sales" })).not.toBeInTheDocument();
    expect(within(sales).getByRole("link", { name: "Open Sales" })).toHaveAttribute(
      "href", "/tenants/7/projects/18/subject-areas/41",
    );
    expect(within(sales).getByText("Orders and customers from capture to invoice.")).toBeVisible();
    expect(within(sales).getByText("120")).toBeVisible();
    expect(within(ledger).getByText("320")).toBeVisible();
    expect(screen.queryByText(/limit|\/ 300/)).not.toBeInTheDocument();
    expect(screen.getByText(/of 4 Bronze Input Scope Objects are in an area/)).toBeVisible();
    expect(screen.getByRole("button", { name: /Unassigned/ })).toHaveTextContent("1");
  });

  it("explains how to start when there are no areas", async () => {
    renderAt("/tenants/7/projects/18/subject-areas", subjectAreaFetchStub({ empty: true }));
    expect(await screen.findByText("No Subject Areas yet.")).toBeVisible();
    expect(screen.getAllByRole("button", { name: "New area" }).length).toBeGreaterThan(0);
  });

  it("creates an area with Objects chosen from the Input Scope", async () => {
    const fetcher = subjectAreaFetchStub();
    const user = userEvent.setup();
    renderAt("/tenants/7/projects/18/subject-areas", fetcher);
    await screen.findByRole("table", { name: "Subject Areas" });
    await user.click(screen.getAllByRole("button", { name: "New area" })[0]!);
    const dialog = await screen.findByRole("dialog", { name: "New Subject Area" });
    await user.type(within(dialog).getByLabelText("Name"), " Billing ");
    await user.type(within(dialog).getByLabelText("Definition"), "Invoices and payments.");
    const picker = await within(dialog).findByRole("table", { name: "Input Scope Objects" });
    expect(within(picker).getAllByRole("columnheader").map((cell) => cell.textContent)).toEqual([
      "", "System", "Object schema", "Object name", "Attributes", "Subject Areas",
    ]);
    expect(within(picker).getAllByRole("row")).toHaveLength(5);
    await user.type(within(dialog).getByLabelText("Search Objects"), "order");
    expect(within(picker).getAllByRole("row")).toHaveLength(2);
    await user.click(within(picker).getByRole("checkbox", { name: "Choose bronze.order_raw" }));
    expect(within(dialog).getByText("1 Object selected")).toBeVisible();
    await user.click(within(dialog).getByRole("button", { name: "Create area" }));
    await waitFor(() => expect(screen.queryByRole("dialog", { name: "New Subject Area" })).not.toBeInTheDocument());
    const save = savedCommands(fetcher);
    expect(save).toEqual([{
      expected_project_revision: 18,
      subject_area_name: "Billing",
      subject_area_definition: "Invoices and payments.",
      add_object_ids: [502],
    }]);
  });

  it("keeps the form and explains a name conflict", async () => {
    const fetcher = subjectAreaFetchStub({ saveError: "subject_area_name_conflict" });
    const user = userEvent.setup();
    renderAt("/tenants/7/projects/18/subject-areas", fetcher);
    await screen.findByRole("table", { name: "Subject Areas" });
    await user.click(screen.getAllByRole("button", { name: "New area" })[0]!);
    const dialog = await screen.findByRole("dialog", { name: "New Subject Area" });
    await user.type(within(dialog).getByLabelText("Name"), "Sales");
    await user.type(within(dialog).getByLabelText("Definition"), "Duplicate.");
    await user.click(within(dialog).getByRole("button", { name: "Create area" }));
    expect(await within(dialog).findByRole("alert")).toHaveTextContent(/already uses this name/);
    expect(within(dialog).getByLabelText("Name")).toHaveValue("Sales");
  });

  it("adds unassigned Objects to an existing area", async () => {
    const fetcher = subjectAreaFetchStub();
    const user = userEvent.setup();
    renderAt("/tenants/7/projects/18/subject-areas", fetcher);
    await screen.findByRole("table", { name: "Subject Areas" });
    await user.click(screen.getByRole("button", { name: /Unassigned/ }));
    const ledger = await screen.findByRole("table", { name: "Unassigned Objects" });
    expect(within(ledger).getAllByRole("columnheader").map((cell) => cell.textContent)).toEqual([
      "", "System", "Object schema", "Object name", "Attributes", "Description", "Subject Areas",
    ]);
    expect(within(ledger).getAllByRole("row")).toHaveLength(2);
    await user.click(within(ledger).getByRole("checkbox", { name: "Select bronze.audit_log" }));
    await user.click(screen.getByRole("button", { name: "Add to area…" }));
    const dialog = await screen.findByRole("dialog", { name: "Add to Subject Area" });
    expect(within(dialog).getByLabelText("Subject Area")).toHaveValue("41");
    expect(within(dialog).getByRole("option", { name: "Sales (2 Objects)" })).toBeInTheDocument();
    await user.click(within(dialog).getByRole("button", { name: "Add Objects" }));
    await waitFor(() => expect(savedCommands(fetcher)).toEqual([{
      expected_project_revision: 18, subject_area_id: 41, add_object_ids: [504],
    }]));
  });

  it("runs Subject Areas over all Bronze Objects, or only the selected ones", async () => {
    const fetcher = subjectAreaFetchStub();
    const user = userEvent.setup();
    renderAt("/tenants/7/projects/18/subject-areas", fetcher);
    await screen.findByRole("table", { name: "Subject Areas" });
    await user.click(screen.getByRole("button", { name: "Run Subject Areas" }));
    const dialog = await screen.findByRole("dialog", { name: "Configure Subject Areas run" });
    expect(within(dialog).getByRole("radio", { name: /All Objects/ })).toBeChecked();
    expect(within(dialog).getByRole("radio", { name: /Selected Objects/ })).not.toBeChecked();
    expect(within(dialog).queryByLabelText("Batch ID (optional)")).not.toBeInTheDocument();
    const submit = within(dialog).getByRole("button", { name: "Create and run Subject Areas" });
    await waitFor(() => expect(submit).toBeEnabled());
    await user.click(submit);
    await waitFor(() => expect(fetcher).toHaveBeenCalledWith(
      "/api/v1/tenants/7/projects/18/subject-areas/runs/1150/execute",
      expect.objectContaining({ method: "POST" }),
    ));
    const create = fetcher.mock.calls.find(([input]) => String(input) === "/api/v1/tenants/7/projects/18/runs");
    expect(JSON.parse(String(create?.[1]?.body))).toMatchObject({
      project_workflow: "subject_area", selected_object_ids: [501, 502, 503, 504], requested_batch_id: null,
    });
  });

  it("runs Subject Areas on the selected unassigned Objects", async () => {
    const fetcher = subjectAreaFetchStub();
    const user = userEvent.setup();
    renderAt("/tenants/7/projects/18/subject-areas", fetcher);
    await screen.findByRole("table", { name: "Subject Areas" });
    await user.click(screen.getByRole("button", { name: /Unassigned/ }));
    const ledger = await screen.findByRole("table", { name: "Unassigned Objects" });
    await user.click(within(ledger).getByRole("checkbox", { name: "Select bronze.audit_log" }));
    await user.click(screen.getByRole("button", { name: "Run on selected…" }));
    const dialog = await screen.findByRole("dialog", { name: "Configure Subject Areas run" });
    expect(within(dialog).getByRole("radio", { name: /Selected Objects/ })).toBeChecked();
    const submit = within(dialog).getByRole("button", { name: "Create and run Subject Areas" });
    await waitFor(() => expect(submit).toBeEnabled());
    await user.click(submit);
    await waitFor(() => expect(fetcher).toHaveBeenCalledWith(
      "/api/v1/tenants/7/projects/18/subject-areas/runs/1150/execute",
      expect.objectContaining({ method: "POST" }),
    ));
    const create = fetcher.mock.calls.find(([input]) => String(input) === "/api/v1/tenants/7/projects/18/runs");
    expect(JSON.parse(String(create?.[1]?.body))).toMatchObject({
      project_workflow: "subject_area", selected_object_ids: [504],
    });
  });

  it("disables changes without the Tenant Lock", async () => {
    renderAt("/tenants/7/projects/18/subject-areas", subjectAreaFetchStub({ hasLock: false }));
    await screen.findByRole("table", { name: "Subject Areas" });
    for (const name of ["New area", "Run Subject Areas"]) {
      const button = screen.getByRole("button", { name });
      expect(button).toBeDisabled();
      expect(button).toHaveAttribute("title", "Tenant Lock required");
    }
  });

  it("shows an area's Objects and removes only unlocked ones", async () => {
    const fetcher = subjectAreaFetchStub();
    const user = userEvent.setup();
    renderAt("/tenants/7/projects/18/subject-areas/41", fetcher);
    const heading = await screen.findByRole("heading", { level: 1, name: "Sales" });
    await waitFor(() => expect(heading).toHaveFocus());
    expect(screen.getByText("120")).toBeVisible();
    const tables = screen.getByRole("table", { name: "Subject Area Objects" });
    expect(within(tables).getAllByRole("columnheader").map((cell) => cell.textContent)).toEqual([
      "", "System", "Object schema", "Object name", "Attributes", "Description", "Also in", "Lock",
    ]);
    const customer = within(tables).getByRole("row", { name: /customer_raw/ });
    expect(within(customer).getByText("Support")).toBeVisible();
    expect(within(customer).getByText("Locked")).toBeVisible();
    await user.click(within(tables).getByRole("checkbox", { name: "Select all Objects in this area" }));
    await user.click(screen.getByRole("button", { name: "Remove from area" }));
    await waitFor(() => expect(savedCommands(fetcher)).toEqual([{
      expected_project_revision: 18, subject_area_id: 41, remove_object_ids: [502],
    }]));
  });

  it("adds Objects to an area with its members shown as already chosen", async () => {
    const fetcher = subjectAreaFetchStub();
    const user = userEvent.setup();
    renderAt("/tenants/7/projects/18/subject-areas/41", fetcher);
    await screen.findByRole("heading", { level: 1, name: "Sales" });
    await user.click(screen.getByRole("button", { name: "Add Objects" }));
    const dialog = await screen.findByRole("dialog", { name: "Add Objects" });
    const picker = await within(dialog).findByRole("table", { name: "Input Scope Objects" });
    const member = within(picker).getByRole("checkbox", { name: "Choose bronze.order_raw" });
    expect(member).toBeChecked();
    expect(member).toBeDisabled();
    await user.click(within(dialog).getByRole("radio", { name: "Unassigned" }));
    expect(within(picker).getAllByRole("row")).toHaveLength(2);
    await user.click(within(picker).getByRole("checkbox", { name: "Choose bronze.audit_log" }));
    await user.click(within(dialog).getByRole("button", { name: "Add Objects" }));
    await waitFor(() => expect(savedCommands(fetcher)).toEqual([{
      expected_project_revision: 18, subject_area_id: 41, add_object_ids: [504],
    }]));
  });
});

function renderAt(path: string, fetcher: ReturnType<typeof subjectAreaFetchStub>) {
  render(<WorkbenchApp router={createWorkbenchRouter({
    api: createApiClient(fetcher),
    history: createMemoryHistory({ initialEntries: [path] }),
  })} />);
}

function savedCommands(fetcher: ReturnType<typeof subjectAreaFetchStub>) {
  return fetcher.mock.calls
    .filter(([input]) => String(input) === "/api/v1/tenants/7/projects/18/change-sets/review/subject-area")
    .map(([, init]) => JSON.parse(String(init?.body)) as unknown);
}

function subjectAreaFetchStub(options: { empty?: boolean; hasLock?: boolean; saveError?: string } = {}) {
  return vi.fn<typeof fetch>(async (input) => {
    const url = String(input);
    if (url === "/api/v1/tenants/7/home") {
      const owned = options.hasLock ?? true;
      return jsonResponse({ ...tenantHomePayload, lock: { ...tenantHomePayload.lock, is_locked: owned, owned_by_current_principal: owned } });
    }
    if (url === "/api/v1/tenants/7/projects/18") return jsonResponse(projectPayload);
    if (url === "/api/v1/tenants/7/projects/18/subject-areas") {
      return jsonResponse({ ...areaPage, ...(options.empty ? { items: [], unassigned_table_count: 4 } : {}) });
    }
    if (url === "/api/v1/tenants/7/projects/18/subject-areas/tables") {
      return jsonResponse({ project_id: 18, project_revision: 18, items: scopeTables });
    }
    if (url === "/api/v1/tenants/7/projects/18/subject-areas/41") {
      return jsonResponse({
        ...areaPage.items[0], project_id: 18, project_revision: 18,
        tables: scopeTables.filter((table) => table.areas.some((area) => area.subject_area_id === 41)),
      });
    }
    if (url === "/api/v1/tenants/7/projects/18/change-sets/review/subject-area") {
      if (options.saveError) return jsonResponse({ error: { code: options.saveError } }, 409);
      return jsonResponse({ project_id: 18, project_change_set_id: "receipt", project_revision: 19, action_count: 1 });
    }
    if (url === "/api/v1/tenants/7/projects/18/input-scope?zone=bronze&page_size=200") {
      return jsonResponse({ project_id: 18, project_revision: 18, items: scopeTables.map(scopeObject), next_cursor: null });
    }
    if (url === "/api/v1/config/agent-capabilities") return jsonResponse(agentCapabilitiesPayload);
    if (url.startsWith("/api/v1/tenants/7/projects/18/runs?")) return jsonResponse({ items: [], next_cursor: null });
    if (url === "/api/v1/tenants/7/projects/18/runs") {
      return jsonResponse({
        created: true, workflow_run_id: 1150, workflow_run_state: "queued", correlation_id: "subject-area-run-1150",
        prompt_snapshot_count: 1, created_at: "2026-08-24T16:00:00Z",
      }, 201);
    }
    if (url === "/api/v1/tenants/7/projects/18/subject-areas/runs/1150/execute") {
      return jsonResponse({ changed: true, workflow_run_id: 1150, workflow_run_state: "running", project_revision: 18 }, 202);
    }
    return jsonResponse({ error: { code: "not_found" } }, 404);
  });
}

function jsonResponse(value: unknown, status = 200): Response {
  return new Response(JSON.stringify(value), { status, headers: { "content-type": "application/json" } });
}

function membership(subjectAreaId: number, name: string, id: number, locked = false) {
  return { subject_area_id: subjectAreaId, subject_area_name: name, subject_area_table_id: id, subject_area_table_is_locked: locked };
}

function table(objectId: number, name: string, columns: number, areas: ReturnType<typeof membership>[]) {
  return {
    object_id: objectId, tenant_code: "GRDM", system_code: "CRM", connection_code: "crm-prod",
    object_schema: "bronze", object_name: name, object_description: `${name} rows.`, zone_code: "bronze",
    column_count: columns, areas,
  };
}

const scopeTables = [
  table(501, "customer_raw", 40, [membership(41, "Sales", 61, true), membership(42, "Support", 63)]),
  table(502, "order_raw", 80, [membership(41, "Sales", 62)]),
  table(503, "ticket_raw", 280, [membership(42, "Support", 64)]),
  table(504, "audit_log", 12, []),
];

function scopeObject(item: (typeof scopeTables)[number]) {
  return {
    project_input_scope_id: item.object_id + 100, object_id: item.object_id, connection_id: 301, system_id: 401,
    system_code: "CRM", system_name: "Customer Relationship Management", source_tenant_id: 9, source_tenant_code: "GRDM",
    source_tenant_name: "Global Reference Data", object_schema: "bronze", object_name: item.object_name, zone_code: "bronze",
    batch_attribute_name: null, attribute_count: item.column_count, is_project_input_eligible: true,
    created_at: "2026-08-24T14:00:00Z", updated_at: "2026-08-24T14:00:00Z",
  };
}

const areaPage = {
  project_id: 18,
  project_revision: 18,
  scope_table_count: 4,
  unassigned_table_count: 1,
  items: [
    {
      subject_area_id: 41, workflow_run_id: 1048, subject_area_name: "Sales",
      subject_area_definition: "Orders and customers from capture to invoice.", subject_area_is_active: true,
      subject_area_is_locked: false, table_count: 2, shared_table_count: 1, column_count: 120, updated_at: "2026-08-24T14:30:00Z",
    },
    {
      subject_area_id: 42, workflow_run_id: null, subject_area_name: "Support",
      subject_area_definition: "Customer tickets and resolutions.", subject_area_is_active: true,
      subject_area_is_locked: false, table_count: 2, shared_table_count: 1, column_count: 320, updated_at: "2026-08-24T14:40:00Z",
    },
  ],
};

const tenantHomePayload = {
  tenant: {
    tenant_id: 7, tenant_code: "NWA", tenant_name: "Northwind Analytics", tenant_description: null,
    tenant_visibility: "private", effective_role: "tenant_admin",
  },
  lock: {
    is_locked: true, owner_display_name: "Maaz", owned_by_current_principal: true, purpose: "Project authoring",
    acquired_at: "2026-08-24T14:12:00Z", expires_at: "2026-08-24T16:12:00Z",
  },
  lock_actions: { can_acquire: false, can_renew: true, can_release: true, can_override: false },
  systems: [],
};

const projectPayload = {
  project_id: 18, tenant_id: 7, project_name: "Customer 360", project_description: "Cross-system customer domain",
  project_revision: 18, project_input_scope_object_count: 4, logical_schemas: [], dimensional_schemas: [],
  silver_model_naming_instructions: null, silver_model_audit_columns_template: null,
  gold_model_naming_instructions: null, gold_model_technical_columns_template: null,
  gold_model_audit_columns_template: null, default_agent_sdk_code: "openai_agents_sdk",
  default_agent_provider_code: "microsoft_foundry", default_agent_model_code: "foundry-primary",
  default_reasoning_effort_code: "medium", default_max_turns: 8, default_validation_retry_count: 1,
  is_active: true, updated_at: "2026-08-24T14:00:00Z",
};

const agentCapabilitiesPayload = {
  schema_version: "3.0",
  sdks: [{ code: "openai_agents_sdk", name: "OpenAI Agents", provider_codes: ["microsoft_foundry"] }],
  providers: [{ code: "microsoft_foundry", name: "Microsoft Foundry" }],
  models: [{
    code: "foundry-primary", name: "GPT-5.6", provider_code: "microsoft_foundry", deployment_name: "foundry-primary",
    execution_profiles: ["one_shot", "tool_assisted"].map((execution_mode) => ({
      sdk_code: "openai_agents_sdk", execution_mode, reasoning_effort_codes: ["medium"],
    })),
  }],
  reasoning_efforts: [{ code: "medium", name: "Medium" }],
  max_turns: { minimum: 1, default: 8, maximum: 50 },
  validation_retries: { minimum: 0, default: 1, maximum: 5 },
};
