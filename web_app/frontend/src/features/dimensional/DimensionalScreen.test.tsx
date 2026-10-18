import { withRecordReview } from "../../test/projectRecordReview";
import { render, screen, within } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { createMemoryHistory } from "@tanstack/react-router";
import { describe, expect, it, vi } from "vitest";

import { createApiClient } from "../../api";
import { WorkbenchApp, createWorkbenchRouter } from "../../app";

describe("Project Dimensional", () => {
  it.each([
    ["objects/301", "gold.sales_fact"],
    ["attributes/401", "sales_amount"],
    ["relationships/501", "customer to sales"],
  ])("keeps %s record actions beside its heading with lifecycle commands under More", async (detail, title) => {
    const user = userEvent.setup();
    render(<WorkbenchApp router={createWorkbenchRouter({
      api: createApiClient(dimensionalFetchStub()),
      history: createMemoryHistory({ initialEntries: [`/tenants/7/projects/18/dimensional/${detail}`] }),
    })} />);
    const heading = await screen.findByRole("heading", { level: 1, name: title });
    const header = heading.closest("header")!;
    const detailPage = heading.closest("article")!;
    expect(detailPage).toHaveClass("modeled-detail-page");
    const definition = within(detailPage).getByText("Definition", { selector: "dt" });
    expect(definition.closest("dl")).toHaveClass("modeled-detail-fields");
    expect(definition.nextElementSibling).not.toBeEmptyDOMElement();
    expect(within(header).queryByText(/^Dimensional (Entity|Attribute|Relationship|Submodel) \d+$/)).not.toBeInTheDocument();
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

  it("opens a Dimensional Entity detail page with complete normalized context", async () => {
    const user = userEvent.setup();
    const fetcher = dimensionalFetchStub();
    render(<WorkbenchApp router={dimensionalRouter(fetcher)} />);

    const ledger = await screen.findByRole("table", { name: "Dimensional Entities" });
    const views = within(screen.getByRole("navigation", { name: "Dimensional views" }));
    expect(views.getAllByRole("button").map((button) => button.textContent?.replace(/\d/g, ""))).toEqual(["Entities", "Relationships", "Submodels"]);
    expect(fetcher.mock.calls.some(([input]) => String(input).includes("/dimensional/attributes"))).toBe(false);
    expect(within(ledger).getAllByRole("columnheader").slice(1, 3).map((cell) => cell.textContent)).toEqual(["Schema", "Entity name"]);
    expect(within(ledger).getByRole("cell", { name: "gold" })).toBeVisible();
    expect(within(ledger).getByText("sales_fact")).toBeVisible();
    await user.click(screen.getByRole("link", { name: "Open Dimensional Entity 301" }));

    expect(await screen.findByRole("heading", { name: "gold.sales_fact" })).toBeVisible();
    expect(screen.getByRole("heading", { name: "Submodel membership" })).toBeVisible();
    expect(screen.getByText("Sales Analytics")).not.toBeVisible();
    expect(await screen.findByRole("table", { name: "Entity Attributes" })).toBeVisible();
    await user.click(screen.getByRole("heading", { name: "Submodel membership" }));
    await user.click(screen.getByRole("heading", { name: "Source mappings" }));
    expect(screen.getByText("Sales Analytics")).toBeVisible();
    const memberships = screen.getByRole("region", { name: "Scrollable Submodel memberships" });
    expect(memberships).toHaveAttribute("tabindex", "0");
    memberships.focus();
    expect(memberships).toHaveFocus();
    expect(screen.getByRole("heading", { name: "Source mappings" })).toBeVisible();
    expect(within(screen.getByRole("table", { name: "Source mappings" })).getByRole("cell", { name: "silver" })).toBeVisible();
    expect(within(screen.getByRole("table", { name: "Source mappings" })).getByRole("cell", { name: "sales_order" })).toBeVisible();
    expect(screen.getAllByText("Sales project guide")[0]!).toBeVisible();
    expect(screen.queryByRole("heading", { name: "Provenance" })).not.toBeInTheDocument();

    await user.click(screen.getByRole("link", { name: "Back to Dimensional" }));
    expect(await screen.findByRole("table", { name: "Dimensional Entities" })).toBeVisible();
  });

  it("reviews Dimensional Attributes and Relationships on dedicated detail pages", async () => {
    const user = userEvent.setup();
    render(<WorkbenchApp router={dimensionalRouter(dimensionalFetchStub())} />);
    await screen.findByRole("table", { name: "Dimensional Entities" });

    await user.click(screen.getByRole("link", { name: "Open Dimensional Entity 301" }));
    expect(await screen.findByRole("table", { name: "Entity Attributes" })).toBeVisible();
    await user.click(screen.getByRole("link", { name: "Open Dimensional Attribute 401" }));
    expect(await screen.findByRole("heading", { name: "sales_amount" })).toHaveFocus();
    expect(screen.getByText("Natural key").nextElementSibling).toHaveTextContent("No");
    expect(screen.getByText("Surrogate key").nextElementSibling).toHaveTextContent("No");
    expect(screen.getByText("Audit column").nextElementSibling).toHaveTextContent("No");
    await user.click(screen.getByRole("heading", { name: "Source mappings" }));
    await user.click(within(screen.getByRole("table", { name: "Source mappings" })).getAllByText("Show details")[0]!);
    expect(screen.queryByText("Entity mapping id")).not.toBeInTheDocument();
    expect(screen.getByRole("heading", { name: "Source mappings" })).toBeVisible();
    const sourceTable = screen.getByRole("table", { name: "Source mappings" });
    for (const name of ["silver", "sales_order", "sales_amount"]) expect(within(sourceTable).getByRole("cell", { name })).toBeVisible();
    expect(screen.getAllByText("Sales project guide")[0]!).toBeVisible();

    await user.click(screen.getByRole("link", { name: "Back to Entity" }));
    expect(await screen.findByRole("heading", { name: "gold.sales_fact" })).toBeVisible();
    await user.click(screen.getByRole("link", { name: "Back to Dimensional" }));
    await screen.findByRole("table", { name: "Dimensional Entities" });
    await user.click(screen.getByRole("button", { name: "Relationships" }));
    expect(await screen.findByRole("table", { name: "Dimensional Relationships" })).toBeVisible();
    await user.click(screen.getByRole("link", { name: "Open Dimensional Relationship 501" }));
    expect(await screen.findByRole("heading", { name: "customer to sales" })).toBeVisible();
    expect(screen.getByText("From", { selector: "dt" }).nextElementSibling).toHaveTextContent("gold.customer_dimension.customer_key");
    expect(screen.getByText("To", { selector: "dt" }).nextElementSibling).toHaveTextContent("gold.sales_fact.customer_key");
    expect(screen.getByText("The customer key establishes the conformed join.")).toBeVisible();
    expect(screen.getByText("Each sale has one customer; a customer has many sales.")).toBeVisible();
  });

  it.each(["natural", "surrogate"] as const)("shows %s key flags on Dimensional Attributes", async (keyAttribute) => {
    render(<WorkbenchApp router={createWorkbenchRouter({
      api: createApiClient(dimensionalFetchStub({ keyAttribute })),
      history: createMemoryHistory({ initialEntries: ["/tenants/7/projects/18/dimensional/attributes/401"] }),
    })} />);
    await screen.findByRole("heading", { name: "sales_amount" });
    expect(screen.queryByRole("heading", { name: "Aggregation" })).not.toBeInTheDocument();
    expect(screen.queryByText("Change behavior")).not.toBeInTheDocument();
    expect(screen.getByText("Natural key").nextElementSibling).toHaveTextContent(keyAttribute === "natural" ? "Yes" : "No");
    expect(screen.getByText("Surrogate key").nextElementSibling).toHaveTextContent(keyAttribute === "surrogate" ? "Yes" : "No");
  });

  it("sends only supported bounded filters and follows opaque pagination cursors", async () => {
    const fetcher = dimensionalFetchStub({ hasNextPage: true });
    const user = userEvent.setup();
    render(<WorkbenchApp router={dimensionalRouter(fetcher)} />);
    await screen.findByRole("table", { name: "Dimensional Entities" });

    if (screen.getByRole("button", { name: /^Filters/ }).getAttribute("aria-expanded") === "false") await user.click(screen.getByRole("button", { name: /^Filters/ }));
    await user.type(screen.getByLabelText("Entity name prefix"), " Sales ");
    await user.selectOptions(screen.getByLabelText("Entity status"), "inactive");
    await user.selectOptions(screen.getByLabelText("Entity lock"), "false");
    await user.click(screen.getByRole("button", { name: "Apply Entity filters" }));
    expect(fetcher).toHaveBeenCalledWith(
      "/api/v1/tenants/7/projects/18/dimensional/objects?status=inactive&locked=false&name_prefix=sales&page_size=200",
      expect.objectContaining({ credentials: "same-origin" }),
    );
    await user.click(await screen.findByRole("button", { name: "Load more Dimensional Entities" }));
    expect(fetcher).toHaveBeenCalledWith(
      "/api/v1/tenants/7/projects/18/dimensional/objects?status=inactive&locked=false&name_prefix=sales&page_size=200&cursor=objects-next",
      expect.objectContaining({ credentials: "same-origin" }),
    );

    await user.click(screen.getByRole("button", { name: "Relationships" }));
    await screen.findByRole("table", { name: "Dimensional Relationships" });
    await user.type(screen.getByLabelText("Relationship name prefix"), " Customer ");
    await user.type(screen.getByLabelText("Relationship Entity ID"), "302");
    await user.click(screen.getByRole("button", { name: "Apply Relationship filters" }));
    expect(fetcher).toHaveBeenCalledWith(
      "/api/v1/tenants/7/projects/18/dimensional/relationships?status=active&name_prefix=customer&dimensional_entity_id=302&page_size=200",
      expect.objectContaining({ credentials: "same-origin" }),
    );
  });

  it("keeps empty, safe-error, denied, and revision mismatch states explicit", async () => {
    const empty = render(
      <WorkbenchApp router={dimensionalRouter(dimensionalFetchStub({ empty: true }))} />,
    );
    expect(await screen.findByText("No Dimensional Entities match these filters.")).toBeVisible();
    empty.unmount();

    const mismatch = render(
      <WorkbenchApp router={dimensionalRouter(dimensionalFetchStub({ projectRevision: 19 }))} />,
    );
    expect(await screen.findByRole("alert")).toHaveTextContent(
      "The Project changed while Dimensional Entities were loading.",
    );
    mismatch.unmount();

    const denied = render(
      <WorkbenchApp router={dimensionalRouter(dimensionalFetchStub({ denied: true }))} />,
    );
    expect(await screen.findByRole("alert")).toHaveTextContent(
      "You do not have permission to view Dimensional Entities.",
    );
    denied.unmount();

    render(<WorkbenchApp router={dimensionalRouter(dimensionalFetchStub({ error: true }))} />);
    expect(await screen.findByRole("alert")).toHaveTextContent(
      "Dimensional Entities could not be loaded.",
    );
  });

  it("keeps Dimensional execution lock-gated and explicitly creates then starts a run", async () => {
    const unlocked = render(
      <WorkbenchApp router={dimensionalRouter(dimensionalFetchStub({ hasLock: false }))} />,
    );
    await screen.findByRole("table", { name: "Dimensional Entities" });
    expect(screen.getByRole("button", { name: "Run Dimensional" })).toBeDisabled();
    expect(screen.getByRole("button", { name: "Run Dimensional" })).toHaveAttribute("title", "Tenant Lock required");
    unlocked.unmount();

    const fetcher = dimensionalFetchStub();
    const user = userEvent.setup();
    render(<WorkbenchApp router={dimensionalRouter(fetcher)} />);
    await screen.findByRole("table", { name: "Dimensional Entities" });
    expect(screen.getByText("Tenant Lock held by you")).toBeVisible();
    await user.click(screen.getByRole("button", { name: "Run Dimensional" }));
    expect(await screen.findByRole("heading", { name: "Configure Dimensional run" })).toBeVisible();
    await user.click(screen.getByRole("button", { name: "Create and run Dimensional" }));

    expect(fetcher).toHaveBeenCalledWith(
      "/api/v1/tenants/7/projects/18/runs",
      expect.objectContaining({
        method: "POST",
        body: expect.stringContaining('"project_workflow":"dimensional"'),
      }),
    );
    const createCall = fetcher.mock.calls.find(([input, init]) => String(input).endsWith("/projects/18/runs") && init?.method === "POST");
    expect(JSON.parse(String(createCall?.[1]?.body))).toMatchObject({ selected_object_ids: [], selected_entity_ids: [501], modeled_entity_type: "logical_entity" });
    expect(fetcher.mock.calls.some(([input]) => String(input).includes("input-scope?zone=silver"))).toBe(false);
    expect(fetcher).toHaveBeenCalledWith(
      "/api/v1/tenants/7/projects/18/dimensional/runs/1250/execute",
      expect.objectContaining({
        method: "POST",
        body: JSON.stringify({ execution_mode: "tool_assisted", expected_project_revision: 18 }),
      }),
    );
  });
});

function dimensionalRouter(fetcher: ReturnType<typeof dimensionalFetchStub>) {
  return createWorkbenchRouter({
    api: createApiClient(fetcher),
    history: createMemoryHistory({
      initialEntries: ["/tenants/7/projects/18/dimensional"],
    }),
  });
}

function dimensionalFetchStub(options: {
  empty?: boolean;
  error?: boolean;
  denied?: boolean;
  projectRevision?: number;
  hasNextPage?: boolean;
  keyAttribute?: "natural" | "surrogate";
  hasLock?: boolean;
} = {}) {
  return vi.fn<typeof fetch>(async (input) => {
    const url = String(input);
    if (url === "/api/v1/tenants/7/home") return jsonResponse({
      ...tenantHomePayload,
      lock: {
        ...tenantHomePayload.lock,
        is_locked: options.hasLock ?? true,
        owned_by_current_principal: options.hasLock ?? true,
      },
    });
    if (url === "/api/v1/tenants/7/projects/18") return jsonResponse(projectPayload);
    if (url.startsWith("/api/v1/tenants/7/projects/18/dimensional/objects?")) {
      if (options.denied) return jsonResponse({ error: { code: "forbidden" } }, 403);
      if (options.error) return jsonResponse({ error: { code: "unavailable" } }, 503);
      const isNextPage = url.includes("cursor=objects-next");
      return jsonResponse({
        project_id: 18,
        project_revision: options.projectRevision ?? 18,
        items: options.empty
          ? []
          : [{
            ...dimensionalObjectPayload,
            ...(isNextPage
              ? { dimensional_entity_id: 302, dimensional_entity_schema_name: "gold", dimensional_entity_name: "customer_dimension" }
              : {}),
          }],
        next_cursor: options.hasNextPage && !isNextPage ? "objects-next" : null,
      });
    }
    if (url === "/api/v1/tenants/7/projects/18/dimensional/objects/301") {
      return jsonResponse(dimensionalObjectDetailPayload);
    }
    if (url.startsWith("/api/v1/tenants/7/projects/18/dimensional/attributes?")) {
      return jsonResponse({
        project_id: 18,
        project_revision: 18,
        items: [dimensionalAttributePayload],
        next_cursor: null,
      });
    }
    if (url === "/api/v1/tenants/7/projects/18/dimensional/attributes/401") {
      return jsonResponse({
        ...dimensionalAttributeDetailPayload,
        dimensional_attribute_is_natural_key: options.keyAttribute === "natural",
        dimensional_attribute_is_surrogate_key: options.keyAttribute === "surrogate",
      });
    }
    if (url.startsWith("/api/v1/tenants/7/projects/18/dimensional/relationships?")) {
      return jsonResponse({
        project_id: 18,
        project_revision: 18,
        items: [dimensionalRelationshipPayload],
        next_cursor: null,
      });
    }
    if (url === "/api/v1/tenants/7/projects/18/dimensional/relationships/501") {
      return jsonResponse(dimensionalRelationshipDetailPayload);
    }
    if (url === "/api/v1/tenants/7/projects/18/logical/entities?status=active&page_size=200") {
      return jsonResponse({
        project_id: 18,
        project_revision: 18,
        items: [{ logical_entity_id: 501, logical_entity_schema_name: "silver", logical_entity_name: "sales_order", logical_entity_status: "active", logical_entity_is_locked: false }],
        next_cursor: null,
      });
    }
    if (url === "/api/v1/config/agent-capabilities") {
      return jsonResponse(agentCapabilitiesPayload);
    }
    if (url === "/api/v1/tenants/7/projects/18/runs?workflow=dimensional&page_size=5") {
      return jsonResponse({ items: [], next_cursor: null });
    }
    if (url === "/api/v1/tenants/7/projects/18/runs") {
      return jsonResponse({
        created: true,
        workflow_run_id: 1250,
        workflow_run_state: "queued",
        correlation_id: "dimensional-run-1250",
        prompt_snapshot_count: 5,
        created_at: "2026-08-24T16:00:00Z",
      }, 201);
    }
    if (url === "/api/v1/tenants/7/projects/18/dimensional/runs/1250/execute") {
      return jsonResponse({
        changed: true,
        workflow_run_id: 1250,
        workflow_run_state: "running",
        started_at: "2026-08-24T16:00:01Z",
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

const dimensionalObjectPayload = {
  dimensional_entity_id: 301,
  workflow_run_id: 1200,
  dimensional_entity_schema_name: "gold", dimensional_entity_name: "sales_fact",
  dimensional_entity_type: "fact",
  dimensional_fact_type: "transaction",
  dimensional_entity_dependency_order: 1,
  dimensional_entity_status: "active",
  dimensional_entity_is_locked: false,
  updated_at: "2026-08-24T15:00:00Z",
};

const dimensionalObjectDetailPayload = {
  ...dimensionalObjectPayload,
  dimensional_entity_definition: "Transaction-grain sales activity for analytical reporting.",
  dimensional_entity_grain_definition: "One row per completed order line.",
  created_at: "2026-08-24T14:40:00Z",
  submodels: [{
    dimensional_entity_submodel_id: 801,
    workflow_run_id: 1200,
    dimensional_submodel_id: 91,
    dimensional_submodel_name: "Sales Analytics",
    membership_status: "active",
    membership_is_locked: false,
    created_at: "2026-08-24T14:42:00Z",
    updated_at: "2026-08-24T15:00:00Z",
  }],
  sources: [
    {
      dimensional_entity_source_mapping_id: 901,
      workflow_run_id: 1200,
      support_source_type: "logical_entity",
      source_order: 1,
      rationale: "The Silver order table establishes the transaction grain.",
      status: "active",
      is_locked: false,
      created_at: "2026-08-24T14:42:00Z",
      updated_at: "2026-08-24T15:00:00Z",
      source_logical_entity: { logical_entity_id: 501, logical_entity_schema_name: "silver", logical_entity_name: "sales_order" },
    },
    {
      dimensional_entity_source_mapping_id: 902,
      workflow_run_id: null,
      support_source_type: "context_record",
      source_order: 2,
      rationale: "The approved context confirms analytical grain.",
      status: "active",
      is_locked: true,
      created_at: "2026-08-24T14:43:00Z",
      updated_at: "2026-08-24T15:00:00Z",
      context_record: {
        context_record_id: "00000000-0000-4000-8000-000000000601",
        context_group_name: "Sales project guide",
        context_type_name: "Business Requirements",
        source_reference: null,
        context_text: "Sales facts are recorded at completed order-line grain.",
        status: "active",
      },
    },
  ],
};

const dimensionalAttributePayload = {
  dimensional_attribute_id: 401,
  workflow_run_id: 1200,
  dimensional_entity_id: 301,
  dimensional_entity_schema_name: "gold", dimensional_entity_name: "sales_fact",
  dimensional_attribute_name: "sales_amount",
  dimensional_attribute_data_type: "decimal(18,2)",
  dimensional_attribute_is_nullable: false,
  dimensional_attribute_ordinal_position: 5,
  dimensional_attribute_is_natural_key: false,
  dimensional_attribute_is_surrogate_key: false,
  dimensional_attribute_is_audit_column: false,
  dimensional_attribute_status: "active",
  dimensional_attribute_is_locked: false,
  updated_at: "2026-08-24T15:00:00Z",
};

const dimensionalAttributeDetailPayload = {
  ...dimensionalAttributePayload,
  dimensional_attribute_definition: "Extended monetary value of the completed order line.",
  created_at: "2026-08-24T14:40:00Z",
  sources: [
    {
      dimensional_attribute_source_mapping_id: 1001,
      workflow_run_id: 1200,
      dimensional_entity_source_mapping_id: 901,
      support_source_type: "logical_attribute",
      source_order: 1,
      rationale: "The Silver amount is the governed monetary source.",
      status: "active",
      is_locked: false,
      created_at: "2026-08-24T14:42:00Z",
      updated_at: "2026-08-24T15:00:00Z",
      source_logical_attribute: { logical_entity_id: 501, logical_entity_schema_name: "silver", logical_entity_name: "sales_order", logical_attribute_id: 502, logical_attribute_name: "sales_amount" },
    },
    {
      dimensional_attribute_source_mapping_id: 1002,
      workflow_run_id: null,
      support_source_type: "context_record",
      source_order: 2,
      rationale: "The context establishes aggregation behavior.",
      status: "active",
      is_locked: true,
      created_at: "2026-08-24T14:43:00Z",
      updated_at: "2026-08-24T15:00:00Z",
      context_record: {
        context_record_id: "00000000-0000-4000-8000-000000000602",
        context_group_name: "Sales project guide",
        context_type_name: "Business Requirements",
        source_reference: null,
        context_text: "Sales amount is additive across all dimensions.",
        status: "active",
      },
    },
  ],
};

const dimensionalRelationshipPayload = {
  dimensional_relationship_id: 501,
  workflow_run_id: 1200,
  from_dimensional_entity_id: 302,
  from_dimensional_entity_schema_name: "gold", from_dimensional_entity_name: "customer_dimension",
  from_dimensional_attribute_id: 402,
  from_dimensional_attribute_name: "customer_key",
  to_dimensional_entity_id: 301,
  to_dimensional_entity_schema_name: "gold", to_dimensional_entity_name: "sales_fact",
  to_dimensional_attribute_id: 403,
  to_dimensional_attribute_name: "customer_key",
  dimensional_relationship_name: "customer to sales",
  dimensional_relationship_kind: "foreign_key",
  dimensional_relationship_cardinality: "one_to_many",
  dimensional_relationship_is_optional: false,
  dimensional_relationship_role_name: "customer",
  dimensional_relationship_status: "active",
  dimensional_relationship_is_locked: false,
  updated_at: "2026-08-24T15:00:00Z",
};

const dimensionalRelationshipDetailPayload = {
  ...dimensionalRelationshipPayload,
  dimensional_relationship_definition: "Conformed Customer Dimension joined to the Sales Fact.",
  dimensional_relationship_basis: "The customer key establishes the conformed join.",
  dimensional_relationship_cardinality_basis: "Each sale has one customer; a customer has many sales.",
  created_at: "2026-08-24T14:44:00Z",
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


it.each([["Entities", "dimensional_entity", 301], ["Attributes", "dimensional_attribute", 401], ["Relationships", "dimensional_relationship", 501]] as const)("reviews selected %s through the governed endpoint", async (view, dataset, recordId) => {
  const { fetcher, commands } = withRecordReview(dimensionalFetchStub());
  render(<WorkbenchApp router={createWorkbenchRouter({ api: createApiClient(fetcher),
    history: createMemoryHistory({ initialEntries: ["/tenants/7/projects/18/dimensional"] }),
  })} />);
  const user = userEvent.setup();
  if (view === "Attributes") {
    await user.click(await screen.findByRole("link", { name: "Open Dimensional Entity 301" }));
    await screen.findByRole("table", { name: "Entity Attributes" });
    expect(fetcher).toHaveBeenCalledWith(
      "/api/v1/tenants/7/projects/18/dimensional/attributes?status=active&dimensional_entity_id=301&page_size=200",
      expect.objectContaining({ credentials: "same-origin" }),
    );
  } else await user.click(await screen.findByRole("button", { name: view }));
  const selection = await screen.findByRole("checkbox", { name: new RegExp(`^Select Dimensional .* ${recordId}$`) });
  await user.click(selection);
  await user.click(screen.getByRole("button", { name: "Lock selected" }));
  const apply = await screen.findByRole("button", { name: "Apply this change" });
  expect(commands[0]).toEqual({ dataset, record_ids: [recordId], action: "lock", expected_project_revision: 18 });
  await user.click(apply);
  expect(commands[1]).toEqual({ ...commands[0], expected_plan_digest: "c".repeat(64) });
});
