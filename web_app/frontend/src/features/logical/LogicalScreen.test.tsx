import { withRecordReview } from "../../test/projectRecordReview";
import { act, render, screen, waitFor, within } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { createMemoryHistory } from "@tanstack/react-router";
import { describe, expect, it, vi } from "vitest";

import { createApiClient } from "../../api";
import { WorkbenchApp, createWorkbenchRouter } from "../../app";

describe("Project Logical", () => {
  it.each([
    ["entities/71", "silver.customer_account"],
    ["attributes/81", "customer_id"],
    ["relationships/101", "silver.sales_order.customer_id → silver.customer_account.customer_id"],
  ])("keeps %s record actions beside its heading with lifecycle commands under More", async (detail, title) => {
    const user = userEvent.setup();
    render(<WorkbenchApp router={createWorkbenchRouter({
      api: createApiClient(logicalFetchStub()),
      history: createMemoryHistory({ initialEntries: [`/tenants/7/projects/18/logical/${detail}`] }),
    })} />);
    const heading = await screen.findByRole("heading", { level: 1, name: title });
    const header = heading.closest("header")!;
    expect(within(header).queryByText(/^Logical (Entity|Attribute|Relationship) \d+$/)).not.toBeInTheDocument();
    expect(within(header).getByText("Active")).toBeVisible();
    expect(within(header).getByRole("button", { name: "Edit definition" })).toBeVisible();
    expect(within(header).getByRole("button", { name: "Lock" })).not.toBeVisible();
    const more = within(header).getByText("More", { selector: "summary" });
    await user.click(more);
    expect(within(header).getByRole("button", { name: "Lock" })).toBeVisible();
    expect(within(header).getByRole("button", { name: "Deactivate" })).toBeVisible();
    within(header).getByRole("button", { name: "Lock" }).focus();
    await user.keyboard("{Escape}");
    expect(more).toHaveFocus();
    expect(within(header).getByRole("button", { name: "Lock" })).not.toBeVisible();
  });

  it("lists Subject Areas with their Logical Entities, each opening the usual Entity page", async () => {
    const user = userEvent.setup();
    const fetcher = logicalFetchStub();
    const router = logicalRouter(fetcher);
    render(<WorkbenchApp router={router} />);
    await screen.findByRole("table", { name: "Logical Entities" });
    await user.click(within(screen.getByRole("navigation", { name: "Logical views" })).getByRole("button", { name: /Subject Areas/ }));

    const areas = await screen.findByRole("table", { name: "Logical Subject Areas" });
    expect(within(areas).getAllByRole("columnheader").map((cell) => cell.textContent)).toEqual([
      "Subject Area", "Objects", "Logical Entities", "",
    ]);
    const row = within(areas).getByRole("row", { name: /Sales/ });
    expect(within(row).getAllByRole("cell").map((cell) => cell.textContent)).toEqual([
      "SalesCustomer orders.", "2", "1", "Show Entities",
    ]);
    await user.click(within(row).getByRole("link", { name: "Show Sales Entities" }));

    expect(await screen.findByRole("heading", { name: "Sales", level: 1 })).toBeVisible();
    const entities = await screen.findByRole("table", { name: "Sales Logical Entities" });
    expect(within(entities).getByText("customer_account")).toBeVisible();
    expect(fetcher.mock.calls.some(([input]) => String(input).includes("subject_area_id=41"))).toBe(true);
    expect(screen.getByRole("link", { name: "Edit Subject Area" })).toHaveAttribute(
      "href", "/tenants/7/projects/18/subject-areas/41",
    );
    await user.click(within(entities).getByRole("link", { name: "Open Logical Entity 71" }));
    expect(await screen.findByRole("heading", { name: "silver.customer_account" })).toBeVisible();

    // Back from the area returns to the Subject Areas tab.
    act(() => router.history.back());
    await user.click(await screen.findByRole("link", { name: "← Back to Subject Areas" }));
    expect(await screen.findByRole("table", { name: "Logical Subject Areas" })).toBeVisible();
    expect(within(screen.getByRole("navigation", { name: "Logical views" })).getByRole("button", { name: /Subject Areas/ }))
      .toHaveAttribute("aria-pressed", "true");
  });

  it("reviews a Logical Entity with its derived Subject Areas and sources on a detail page", async () => {
    const fetcher = logicalFetchStub();
    const user = userEvent.setup();
    render(<WorkbenchApp router={logicalRouter(fetcher)} />);

    const ledger = await screen.findByRole("table", { name: "Logical Entities" });
    expect(within(ledger).getAllByRole("columnheader").slice(1, 3).map((cell) => cell.textContent)).toEqual(["Schema", "Entity name"]);
    expect(within(ledger).getByRole("cell", { name: "silver" })).toBeVisible();
    expect(within(ledger).getByText("customer_account")).toBeVisible();
    expect(within(ledger).getByText("Core")).toBeVisible();
    expect(within(ledger).getByRole("cell", { name: "Active" })).toBeVisible();

    await user.click(screen.getByRole("link", { name: "Open Logical Entity 71" }));

    expect(await screen.findByRole("heading", { name: "silver.customer_account" })).toHaveFocus();
    const definition = within(screen.getByRole("region", { name: "Entity definition" }));
    expect(definition.getByText("Type", { selector: "dt" }).nextElementSibling).toHaveTextContent("Core");
    expect(screen.queryByText("Type detail")).not.toBeInTheDocument();
    const areas = definition.getByRole("list", { name: "Entity Subject Areas" });
    expect(within(areas).getAllByRole("link").map((link) => link.textContent)).toEqual(["Sales", "Support"]);
    expect(within(areas).getByRole("link", { name: "Sales" })).toHaveAttribute("href", "/tenants/7/projects/18/subject-areas/41");
    expect(await screen.findByRole("table", { name: "Entity Attributes" })).toBeVisible();
    const sources = screen.getByRole("table", { name: "Source mappings" });
    expect(within(sources).getAllByRole("columnheader").map((cell) => cell.textContent)).toEqual([
      "Schema", "Object / entity", "Rationale", "Status", "Details",
    ]);
    expect(within(sources).getByRole("cell", { name: "bronze" })).toBeVisible();
    expect(within(sources).getByRole("cell", { name: "customer_raw" })).toBeVisible();
    // The Object source has no rationale.
    expect(within(sources).getAllByRole("row")[1]!.querySelectorAll("td")[2]).toHaveTextContent("—");
    expect(within(sources).getAllByRole("cell", { name: /^Active/ })).toHaveLength(2);
    await user.click(within(sources).getAllByText("Show details")[0]!);
    expect(screen.getByText("crm-prod")).toBeVisible();
    await user.click(within(sources).getAllByText("Show details")[1]!);
    expect(screen.getByText("Customer identity is governed across systems.")).toBeVisible();
    expect(screen.queryByText("Source mapping id")).not.toBeInTheDocument();
    expect(screen.queryByText("Workflow run 1048")).not.toBeInTheDocument();
    expect(screen.queryByRole("heading", { name: "Provenance" })).not.toBeInTheDocument();
    expect(screen.queryByText(/Submodel/)).not.toBeInTheDocument();
  });

  it("shows no Submodels and reviews Attributes and child-to-parent Relationships", async () => {
    const user = userEvent.setup();
    const fetcher = logicalFetchStub();
    render(<WorkbenchApp router={logicalRouter(fetcher)} />);
    await screen.findByRole("table", { name: "Logical Entities" });
    const views = within(screen.getByRole("navigation", { name: "Logical views" }));
    expect(views.getAllByRole("button").map((button) => button.textContent?.replace(/\d/g, ""))).toEqual(["Subject Areas", "Entities", "Relationships"]);
    expect(screen.queryByText(/Submodel/)).not.toBeInTheDocument();
    expect(fetcher.mock.calls.some(([input]) => String(input).includes("submodel"))).toBe(false);

    expect(screen.queryByRole("button", { name: "Attributes" })).not.toBeInTheDocument();
    await user.click(screen.getByRole("link", { name: "Open Logical Entity 71" }));
    expect(await screen.findByRole("table", { name: "Entity Attributes" })).toBeVisible();
    expect(fetcher).toHaveBeenCalledWith(
      "/api/v1/tenants/7/projects/18/logical/attributes?active=true&logical_entity_id=71&page_size=200",
      expect.objectContaining({ credentials: "same-origin" }),
    );
    expect(within(screen.getByRole("table", { name: "Entity Attributes" })).getByRole("cell", { name: "Active" })).toBeVisible();
    await user.click(screen.getByRole("link", { name: "Open Logical Attribute 81" }));
    expect(await screen.findByRole("heading", { name: "customer_id" })).toHaveFocus();
    expect(screen.getByRole("heading", { name: "Type and nullability" })).toBeVisible();
    expect(screen.getByRole("heading", { name: "Keys" })).toBeVisible();
    expect(screen.getByText("Nullable").nextElementSibling).toHaveTextContent("No");
    expect(screen.getByText("Surrogate key").nextElementSibling).toHaveTextContent("Yes");
    expect(screen.queryByText("Primary key")).not.toBeInTheDocument();
    const sourceTable = screen.getByRole("table", { name: "Source mappings" });
    for (const name of ["bronze", "customer_raw", "customer_id"]) expect(within(sourceTable).getByRole("cell", { name })).toBeVisible();
    expect(within(sourceTable).getByRole("columnheader", { name: "Attribute" })).toBeVisible();

    await user.click(screen.getByRole("link", { name: "Back to Entity" }));
    expect(await screen.findByRole("table", { name: "Entity Attributes" })).toBeVisible();
    await user.click(screen.getByRole("link", { name: "Back to Logical" }));
    await user.click(await screen.findByRole("button", { name: "Relationships" }));
    const relationships = await screen.findByRole("table", { name: "Logical Relationships" });
    expect(within(relationships).getAllByRole("columnheader").map((cell) => cell.textContent)).toEqual([
      "", "From", "To", "Cardinality", "Status", "Lock", "Updated", "",
    ]);
    const [from, to, cardinality, status, lock] = within(relationships).getAllByRole("row")[1]!
      .querySelectorAll("td:not(:first-child)");
    expect(from).toHaveTextContent("silver.sales_ordercustomer_id");
    expect(to).toHaveTextContent("silver.customer_accountcustomer_id");
    expect(cardinality).toHaveTextContent("Many to one");
    expect(status).toHaveTextContent("Active");
    expect(lock).toHaveTextContent("Open");
    expect(within(relationships).queryByText("customer places order")).not.toBeInTheDocument();

    await user.click(screen.getByRole("link", { name: "Open Logical Relationship 101" }));
    expect(await screen.findByRole("heading", {
      name: "silver.sales_order.customer_id → silver.customer_account.customer_id",
    })).toHaveFocus();
    const fact = (label: string) => screen.getByText(label, { selector: "dt" }).nextElementSibling;
    expect(within(fact("From Entity") as HTMLElement).getByRole("link", { name: "silver.sales_order" }))
      .toHaveAttribute("href", "/tenants/7/projects/18/logical/entities/72");
    expect(fact("Foreign key Attribute")).toHaveTextContent("customer_id");
    expect(within(fact("To Entity") as HTMLElement).getByRole("link", { name: "silver.customer_account" }))
      .toHaveAttribute("href", "/tenants/7/projects/18/logical/entities/71");
    expect(fact("Key Attribute")).toHaveTextContent("customer_id");
    expect(fact("Cardinality")).toHaveTextContent("Many to one");
    expect(fact("Basis")).toHaveTextContent("Each order belongs to the customer who placed it.");
    expect(screen.queryByText("Cardinality basis")).not.toBeInTheDocument();
    expect(screen.queryByText("Definition", { selector: "dt" })).not.toBeInTheDocument();
  });

  it("filters Entities by Subject Area and status, and keeps empty, error, and revision states explicit", async () => {
    const user = userEvent.setup();
    const fetcher = logicalFetchStub();
    const filtered = render(<WorkbenchApp router={logicalRouter(fetcher)} />);
    await screen.findByRole("table", { name: "Logical Entities" });

    if (screen.getByRole("button", { name: /^Filters/ }).getAttribute("aria-expanded") === "false") await user.click(screen.getByRole("button", { name: /^Filters/ }));
    const areaFilter = screen.getByLabelText("Subject Area");
    await waitFor(() => expect(areaFilter).toBeEnabled());
    expect(within(areaFilter).getAllByRole("option").map((option) => option.textContent)).toEqual([
      "All Subject Areas", "Empty", "Finance", "Marketing", "Sales", "Support",
    ]);
    expect(screen.queryByLabelText("Entity Submodel")).not.toBeInTheDocument();
    await user.type(screen.getByLabelText("Entity name prefix"), " Customer ");
    await user.selectOptions(areaFilter, "Sales");
    await user.selectOptions(screen.getByLabelText("Entity status"), "Inactive");
    await user.selectOptions(screen.getByLabelText("Entity lock"), "true");
    await user.click(screen.getByRole("button", { name: "Apply Entity filters" }));
    expect(fetcher).toHaveBeenCalledWith(
      "/api/v1/tenants/7/projects/18/logical/entities?active=false&locked=true&name_prefix=customer&subject_area_id=41&page_size=200",
      expect.objectContaining({ credentials: "same-origin" }),
    );
    await user.click(screen.getByRole("button", { name: "Clear" }));
    expect(screen.getByLabelText("Entity status")).toHaveValue("true");
    expect(screen.getByLabelText("Entity name prefix")).toHaveValue("");
    expect(screen.getByLabelText("Subject Area")).toHaveValue("");
    expect(screen.getByLabelText("Entity lock")).toHaveValue("");
    expect(screen.queryByRole("button", { name: "Activate selected" })).not.toBeInTheDocument();
    expect(fetcher).toHaveBeenCalledWith(
      "/api/v1/tenants/7/projects/18/logical/entities?active=true&page_size=200",
      expect.objectContaining({ credentials: "same-origin" }),
    );
    filtered.unmount();

    const empty = render(
      <WorkbenchApp router={logicalRouter(logicalFetchStub({ empty: true }))} />,
    );
    expect(await screen.findByText("No Logical Entities match these filters.")).toBeVisible();
    empty.unmount();

    const mismatch = render(
      <WorkbenchApp router={logicalRouter(logicalFetchStub({ projectRevision: 19 }))} />,
    );
    expect(await screen.findByRole("alert")).toHaveTextContent(
      "The Project changed while Logical Entities were loading.",
    );
    mismatch.unmount();

    render(<WorkbenchApp router={logicalRouter(logicalFetchStub({ error: true }))} />);
    expect(await screen.findByRole("alert")).toHaveTextContent(
      "Logical Entities could not be loaded.",
    );
  });

  it("keeps Build and Optimize lock-gated", async () => {
    render(<WorkbenchApp router={logicalRouter(logicalFetchStub({ hasLock: false }))} />);
    await screen.findByRole("table", { name: "Logical Entities" });
    for (const name of ["Build", "Optimize"]) {
      expect(screen.getByRole("button", { name })).toBeDisabled();
      expect(screen.getByRole("button", { name })).toHaveAttribute("title", "Tenant Lock required");
    }
    // Build and Optimize sit in one Run menu, like the other Run menus.
    expect(screen.getByText("Run Logical", { selector: "summary" })).toBeVisible();
  });

  it("builds checked Subject Areas in the default most-shared-first order, as reordered", async () => {
    const fetcher = logicalFetchStub();
    const user = userEvent.setup();
    render(<WorkbenchApp router={logicalRouter(fetcher)} />);
    await screen.findByRole("table", { name: "Logical Entities" });
    expect(screen.getByText("Tenant Lock held by you")).toBeVisible();
    await user.click(screen.getByText("Run Logical", { selector: "summary" }));
    await user.click(screen.getByRole("button", { name: "Build" }));

    const dialog = await screen.findByRole("dialog", { name: "Configure Logical Build" });
    expect(within(dialog).getByText(/one after another into one draft/)).toBeVisible();
    expect(within(dialog).queryByRole("checkbox", { name: "Select all Objects" })).not.toBeInTheDocument();
    const areas = await within(dialog).findByRole("table", { name: "Subject Areas to build" });
    const rowNames = () => within(areas).getAllByRole("rowheader").map((cell) => cell.textContent);
    // Active areas with Objects: most shared Objects first, then most Objects, then name.
    expect(rowNames()).toEqual(["Support", "Marketing", "Sales", "Finance"]);
    expect(within(areas).getAllByRole("columnheader").map((cell) => cell.textContent)).toEqual([
      "", "Order", "Subject Area", "Objects", "Shared Objects", "Move",
    ]);
    const support = within(areas).getByRole("row", { name: /Support/ });
    expect([...support.querySelectorAll("td")].slice(1, 4).map((cell) => cell.textContent)).toEqual(["1", "3", "1"]);
    expect(within(dialog).getByText("4 of 4 selected")).toBeVisible();
    expect(within(areas).getByRole("button", { name: "Move Support up" })).toBeDisabled();
    expect(within(areas).getByRole("button", { name: "Move Finance down" })).toBeDisabled();

    await user.click(within(areas).getByRole("button", { name: "Move Finance up" }));
    expect(rowNames()).toEqual(["Support", "Marketing", "Finance", "Sales"]);
    expect(within(areas).getByRole("button", { name: "Move Finance up" })).toHaveFocus();
    await user.click(within(areas).getByRole("button", { name: "Move Marketing up" }));
    expect(rowNames()).toEqual(["Marketing", "Support", "Finance", "Sales"]);
    // The top row cannot move up, so focus stays on the same row's other move button.
    expect(within(areas).getByRole("button", { name: "Move Marketing down" })).toHaveFocus();
    expect(within(dialog).getByRole("status")).toHaveTextContent("Marketing moved to position 1 of 4.");

    await user.click(within(areas).getByRole("checkbox", { name: "Select Support" }));
    expect(within(areas).getByRole("row", { name: /Support/ })).toHaveTextContent("Skipped");
    expect(within(areas).getByRole("row", { name: /Finance/ }).querySelectorAll("td")[1]).toHaveTextContent("2");
    expect(within(dialog).getByText("3 of 4 selected")).toBeVisible();
    const selectAll = within(areas).getByRole("checkbox", { name: "Select all Subject Areas" });
    expect(selectAll).toBePartiallyChecked();
    await user.click(selectAll);
    expect(within(dialog).getByText("4 of 4 selected")).toBeVisible();
    await user.click(selectAll);
    expect(within(dialog).getByText("0 of 4 selected")).toBeVisible();
    expect(within(dialog).getByRole("button", { name: "Create and run Logical Build" })).toBeDisabled();
    for (const name of ["Marketing", "Finance", "Sales"]) {
      await user.click(within(areas).getByRole("checkbox", { name: `Select ${name}` }));
    }

    await user.click(within(dialog).getByRole("button", { name: "Create and run Logical Build" }));
    await waitFor(() => expect(createRunBody(fetcher)).toBeDefined());
    const body = createRunBody(fetcher)!;
    expect(body).toMatchObject({
      expected_project_revision: 18,
      project_workflow: "logical",
      workflow_execution_mode: "tool_assisted",
      workflow_operation: "build",
      subject_area_ids: [46, 43, 41],
      selected_object_ids: [],
      requested_batch_id: null,
      prompt_overrides: {},
    });
    expect(body).not.toHaveProperty("selected_entity_ids");
    expect(body).not.toHaveProperty("modeled_entity_type");
    expect(fetcher.mock.calls.some(([input]) => String(input).includes("input-scope"))).toBe(false);
    await waitFor(() => expect(fetcher).toHaveBeenCalledWith(
      "/api/v1/tenants/7/projects/18/logical/runs/1050/execute",
      expect.objectContaining({
        method: "POST",
        body: JSON.stringify({ execution_mode: "tool_assisted", expected_project_revision: 18 }),
      }),
    ));
  });

  it("optimizes the whole Logical model without a Subject Area or Object selection", async () => {
    const fetcher = logicalFetchStub();
    const user = userEvent.setup();
    render(<WorkbenchApp router={logicalRouter(fetcher)} />);
    await screen.findByRole("table", { name: "Logical Entities" });
    await user.click(screen.getByText("Run Logical", { selector: "summary" }));
    await user.click(screen.getByRole("button", { name: "Optimize" }));

    const dialog = await screen.findByRole("dialog", { name: "Configure Logical Optimize" });
    expect(within(dialog).getByText(/reviews the whole Logical model/)).toBeVisible();
    expect(within(dialog).getByText(/merging duplicate Entities by retiring/)).toBeVisible();
    expect(within(dialog).queryByRole("table")).not.toBeInTheDocument();
    expect(within(dialog).queryByRole("checkbox")).not.toBeInTheDocument();
    expect(within(dialog).queryByLabelText("Batch ID (optional)")).not.toBeInTheDocument();
    expect(within(dialog).getByLabelText("Execution mode")).toBeVisible();
    await user.click(within(dialog).getByRole("button", { name: "Create and run Logical Optimize" }));

    await waitFor(() => expect(createRunBody(fetcher)).toBeDefined());
    const body = createRunBody(fetcher)!;
    expect(body).toMatchObject({
      project_workflow: "logical",
      workflow_operation: "optimize",
      selected_object_ids: [],
      requested_batch_id: null,
    });
    expect(body).not.toHaveProperty("subject_area_ids");
    expect(body).not.toHaveProperty("selected_entity_ids");
    expect(fetcher.mock.calls.some(([input]) => String(input).includes("input-scope"))).toBe(false);
  });
});

function createRunBody(fetcher: ReturnType<typeof logicalFetchStub>): Record<string, unknown> | undefined {
  const call = fetcher.mock.calls.find(([input, init]) => String(input) === "/api/v1/tenants/7/projects/18/runs" && init?.method === "POST");
  return call ? JSON.parse(String(call[1]?.body)) as Record<string, unknown> : undefined;
}

function logicalRouter(fetcher: ReturnType<typeof logicalFetchStub>) {
  return createWorkbenchRouter({
    api: createApiClient(fetcher),
    history: createMemoryHistory({
      initialEntries: ["/tenants/7/projects/18/logical"],
    }),
  });
}

function logicalFetchStub(options: {
  empty?: boolean;
  error?: boolean;
  projectRevision?: number;
  hasLock?: boolean;
} = {}) {
  return vi.fn<typeof fetch>(async (input, init) => {
    const url = String(input);
    if (url === "/api/v1/tenants/7/home") {
      return jsonResponse({
        ...tenantHomePayload,
        lock: {
          ...tenantHomePayload.lock,
          is_locked: options.hasLock ?? true,
          owned_by_current_principal: options.hasLock ?? true,
        },
      });
    }
    if (url === "/api/v1/tenants/7/projects/18") return jsonResponse(projectPayload);
    if (url.startsWith("/api/v1/tenants/7/projects/18/logical/entities?")) {
      if (options.error) return jsonResponse({ error: { code: "unavailable" } }, 503);
      return jsonResponse({
        project_id: 18,
        project_revision: options.projectRevision ?? 18,
        items: options.empty ? [] : [logicalEntityPayload],
        next_cursor: null,
      });
    }
    if (url === "/api/v1/tenants/7/projects/18/logical/entities/71") {
      return jsonResponse(logicalEntityDetailPayload);
    }
    if (url === "/api/v1/tenants/7/projects/18/subject-areas") return jsonResponse(subjectAreaPagePayload);
    if (url === "/api/v1/tenants/7/projects/18/logical/subject-areas") {
      return jsonResponse({
        project_id: 18,
        project_revision: 18,
        items: [{
          subject_area_id: 41, subject_area_name: "Sales", subject_area_definition: "Customer orders.",
          table_count: 2, entity_count: 1,
        }],
      });
    }
    if (url.startsWith("/api/v1/tenants/7/projects/18/logical/attributes?")) {
      return jsonResponse({
        project_id: 18,
        project_revision: 18,
        items: [logicalAttributePayload],
        next_cursor: null,
      });
    }
    if (url === "/api/v1/tenants/7/projects/18/logical/attributes/81") {
      return jsonResponse(logicalAttributeDetailPayload);
    }
    if (url.startsWith("/api/v1/tenants/7/projects/18/logical/relationships?")) {
      return jsonResponse({
        project_id: 18,
        project_revision: 18,
        items: [logicalRelationshipPayload],
        next_cursor: null,
      });
    }
    if (url === "/api/v1/tenants/7/projects/18/logical/relationships/101") {
      return jsonResponse(logicalRelationshipDetailPayload);
    }
    if (url === "/api/v1/config/agent-capabilities") {
      return jsonResponse(agentCapabilitiesPayload);
    }
    if (url === "/api/v1/tenants/7/projects/18/runs?workflow=logical&page_size=5") {
      return jsonResponse({ items: [], next_cursor: null });
    }
    if (url === "/api/v1/tenants/7/projects/18/runs" && init?.method === "POST") {
      return jsonResponse({
        created: true,
        workflow_run_id: 1050,
        workflow_run_state: "queued",
        correlation_id: "logical-run-1050",
        prompt_snapshot_count: 5,
        created_at: "2026-08-24T16:00:00Z",
      }, 201);
    }
    if (
      url === "/api/v1/tenants/7/projects/18/logical/runs/1050/execute"
      && init?.method === "POST"
    ) {
      return jsonResponse({
        changed: true,
        workflow_run_id: 1050,
        workflow_run_state: "running",
        project_revision: 18,
      }, 202);
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
    purpose: "Project authoring",
    acquired_at: "2026-08-24T14:12:00Z",
    expires_at: "2026-08-24T16:12:00Z",
  },
  lock_actions: { can_acquire: false, can_renew: true, can_release: true, can_override: false },
  systems: [],
};

const projectPayload = {
  project_id: 18,
  tenant_id: 7,
  project_name: "Customer 360",
  project_description: "Cross-system customer domain",
  project_revision: 18,
  project_input_scope_object_count: 25,
  logical_schemas: [], dimensional_schemas: [], silver_model_naming_instructions: null,
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

function subjectArea(id: number, name: string, tables: number, shared: number, active = true) {
  return {
    subject_area_id: id, workflow_run_id: null, subject_area_name: name,
    subject_area_definition: `${name} capability.`, subject_area_is_active: active,
    subject_area_is_locked: false, table_count: tables, shared_table_count: shared,
    column_count: tables * 10, updated_at: "2026-08-24T14:30:00Z",
  };
}

// Inactive areas and areas without Objects are not offered for Build.
const subjectAreaPagePayload = {
  project_id: 18,
  project_revision: 18,
  scope_table_count: 12,
  unassigned_table_count: 0,
  items: [
    subjectArea(41, "Sales", 2, 1),
    subjectArea(42, "Support", 3, 1),
    subjectArea(43, "Finance", 4, 0),
    subjectArea(44, "Archive", 2, 2, false),
    subjectArea(45, "Empty", 0, 0),
    subjectArea(46, "Marketing", 2, 1),
  ],
};

const logicalEntityPayload = {
  logical_entity_id: 71,
  workflow_run_id: 1048,
  logical_entity_schema_name: "silver", logical_entity_name: "customer_account",
  logical_entity_type: "core",
  logical_entity_dependency_order: 1,
  logical_entity_is_active: true,
  logical_entity_is_locked: false,
  updated_at: "2026-08-24T15:00:00Z",
};

const logicalEntityDetailPayload = {
  ...logicalEntityPayload,
  logical_entity_definition: "A governed customer identity used by downstream projects.",
  logical_entity_grain: "One row per recognized customer.",
  created_at: "2026-08-24T14:40:00Z",
  subject_areas: [
    { subject_area_id: 41, subject_area_name: "Sales" },
    { subject_area_id: 42, subject_area_name: "Support" },
  ],
  sources: [
    {
      logical_entity_source_mapping_id: 901,
      workflow_run_id: 1048,
      support_source_type: "object",
      rationale: null,
      is_active: true,
      is_locked: false,
      created_at: "2026-08-24T14:45:00Z",
      updated_at: "2026-08-24T15:00:00Z",
      source_object: {
        object_id: 501,
        tenant_code: "GRDM",
        system_code: "CRM",
        connection_code: "crm-prod",
        object_schema: "bronze",
        object_name: "customer_raw",
      },
    },
    {
      logical_entity_source_mapping_id: 902,
      workflow_run_id: null,
      support_source_type: "context_record",
      rationale: "The context confirms cross-system semantics.",
      is_active: true,
      is_locked: true,
      created_at: "2026-08-24T14:46:00Z",
      updated_at: "2026-08-24T15:00:00Z",
      context_record: {
        context_record_id: "00000000-0000-4000-8000-000000000091",
        context_group_name: "Customer governance rules",
        context_type_name: "Business Requirements",
        source_reference: null,
        context_text: "Customer identity is governed across systems.",
        status: "active",
      },
    },
  ],
};

const logicalAttributePayload = {
  logical_attribute_id: 81,
  workflow_run_id: 1048,
  logical_entity_id: 71,
  logical_entity_schema_name: "silver", logical_entity_name: "customer_account",
  logical_attribute_name: "customer_id",
  logical_attribute_data_type: "bigint",
  logical_attribute_is_nullable: false,
  logical_attribute_is_natural_key: false,
  logical_attribute_is_surrogate_key: true,
  logical_attribute_ordinal_position: 1,
  logical_attribute_is_audit_column: false,
  logical_attribute_is_active: true,
  logical_attribute_is_locked: false,
  updated_at: "2026-08-24T15:00:00Z",
};

const logicalAttributeDetailPayload = {
  ...logicalAttributePayload,
  logical_attribute_definition: "Stable surrogate key for the governed customer.",
  created_at: "2026-08-24T14:42:00Z",
  sources: [
    {
      logical_attribute_source_mapping_id: 1001,
      workflow_run_id: 1048,
      logical_entity_source_mapping_id: 901,
      support_source_type: "attribute",
      rationale: "Source customer identifier seeds the surrogate key.",
      is_active: true,
      is_locked: false,
      created_at: "2026-08-24T14:45:00Z",
      updated_at: "2026-08-24T15:00:00Z",
      source_attribute: {
        object_id: 501,
        attribute_id: 601,
        tenant_code: "GRDM",
        system_code: "CRM",
        connection_code: "crm-prod",
        object_schema: "bronze",
        object_name: "customer_raw",
        attribute_name: "customer_id",
      },
    },
  ],
};

// Child to parent: each sales order points at the customer who placed it.
const logicalRelationshipPayload = {
  logical_relationship_id: 101,
  workflow_run_id: 1048,
  from_logical_entity_id: 72,
  from_logical_entity_schema_name: "silver", from_logical_entity_name: "sales_order",
  from_logical_attribute_id: 82,
  from_logical_attribute_name: "customer_id",
  to_logical_entity_id: 71,
  to_logical_entity_schema_name: "silver", to_logical_entity_name: "customer_account",
  to_logical_attribute_id: 81,
  to_logical_attribute_name: "customer_id",
  logical_relationship_cardinality: "many_to_one",
  logical_relationship_is_active: true,
  logical_relationship_is_locked: false,
  updated_at: "2026-08-24T15:00:00Z",
};

const logicalRelationshipDetailPayload = {
  ...logicalRelationshipPayload,
  logical_relationship_basis: "Each order belongs to the customer who placed it.",
  created_at: "2026-08-24T14:42:00Z",
};

const agentCapabilitiesPayload = {
  schema_version: "3.0",
  sdks: [{ code: "openai_agents_sdk", name: "OpenAI Agents", provider_codes: ["microsoft_foundry"] }],
  providers: [{ code: "microsoft_foundry", name: "Microsoft Foundry" }],
  models: [{
    code: "foundry-primary",
    name: "GPT-5.6",
    provider_code: "microsoft_foundry",
    deployment_name: "foundry-primary",
    execution_profiles: ["one_shot", "tool_assisted"].map((execution_mode) => ({
      sdk_code: "openai_agents_sdk",
      execution_mode,
      reasoning_effort_codes: ["medium"],
    })),
  }],
  reasoning_efforts: [{ code: "medium", name: "Medium" }],
  max_turns: { minimum: 1, default: 8, maximum: 50 },
  validation_retries: { minimum: 0, default: 1, maximum: 5 },
};


it.each([["Entities", "logical_entity", 71], ["Attributes", "logical_attribute", 81], ["Relationships", "logical_relationship", 101]] as const)("reviews selected %s through the governed endpoint", async (view, dataset, recordId) => {
  const { fetcher, commands } = withRecordReview(logicalFetchStub());
  render(<WorkbenchApp router={createWorkbenchRouter({ api: createApiClient(fetcher),
    history: createMemoryHistory({ initialEntries: ["/tenants/7/projects/18/logical"] }),
  })} />);
  const user = userEvent.setup();
  if (view === "Attributes") await user.click(await screen.findByRole("link", { name: "Open Logical Entity 71" }));
  else await user.click(await screen.findByRole("button", { name: view }));
  const selection = await screen.findByRole("checkbox", { name: new RegExp(`^Select Logical .* ${recordId}$`) });
  await user.click(selection);
  await user.click(screen.getByRole("button", { name: "Lock selected" }));
  const apply = await screen.findByRole("button", { name: "Apply this change" });
  expect(commands[0]).toEqual({ dataset, record_ids: [recordId], action: "lock", expected_project_revision: 18 });
  await user.click(apply);
  expect(commands[1]).toEqual({ ...commands[0], expected_plan_digest: "c".repeat(64) });
});
