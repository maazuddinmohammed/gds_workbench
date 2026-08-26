import { render, screen } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { createMemoryHistory } from "@tanstack/react-router";
import { describe, expect, it, vi } from "vitest";

import { createApiClient } from "../../api";
import { WorkbenchApp, createWorkbenchRouter } from "../../app";

describe("Model Dimensional", () => {
  it("opens a Dimensional Object detail page with complete normalized context", async () => {
    const user = userEvent.setup();
    render(<WorkbenchApp router={dimensionalRouter(dimensionalFetchStub())} />);

    expect(await screen.findByRole("table", { name: "Dimensional Objects" })).toBeVisible();
    expect(screen.getByText("sales_fact")).toBeVisible();
    await user.click(screen.getByRole("link", { name: "Open Dimensional Object 301" }));

    expect(await screen.findByRole("heading", { name: "sales_fact" })).toBeVisible();
    expect(screen.getByRole("heading", { name: "Submodel membership" })).toBeVisible();
    expect(screen.getByText("Sales Analytics")).toBeVisible();
    expect(screen.getByRole("heading", { name: "Source mappings" })).toBeVisible();
    expect(screen.getAllByText("silver.sales_order")).toHaveLength(2);
    expect(screen.getByText("assertion:sales-grain")).toBeVisible();
    expect(screen.getByRole("heading", { name: "Provenance" })).toBeVisible();

    await user.click(screen.getByRole("link", { name: "Back to Dimensional" }));
    expect(await screen.findByRole("table", { name: "Dimensional Objects" })).toBeVisible();
  });

  it("reviews Dimensional Attributes and Relationships on dedicated detail pages", async () => {
    const user = userEvent.setup();
    render(<WorkbenchApp router={dimensionalRouter(dimensionalFetchStub())} />);
    await screen.findByRole("table", { name: "Dimensional Objects" });

    await user.click(screen.getByRole("button", { name: "Attributes" }));
    expect(await screen.findByRole("table", { name: "Dimensional Attributes" })).toBeVisible();
    await user.click(screen.getByRole("link", { name: "Open Dimensional Attribute 401" }));
    expect(await screen.findByRole("heading", { name: "sales_amount" })).toBeVisible();
    expect(screen.getByRole("heading", { name: "Source mappings" })).toBeVisible();
    expect(screen.getAllByText("silver.sales_order.sales_amount")).toHaveLength(2);
    expect(screen.getByText("assertion:additive-sales")).toBeVisible();

    await user.click(screen.getByRole("link", { name: "Back to Dimensional" }));
    await screen.findByRole("table", { name: "Dimensional Objects" });
    await user.click(screen.getByRole("button", { name: "Relationships" }));
    expect(await screen.findByRole("table", { name: "Dimensional Relationships" })).toBeVisible();
    await user.click(screen.getByRole("link", { name: "Open Dimensional Relationship 501" }));
    expect(await screen.findByRole("heading", { name: "customer to sales" })).toBeVisible();
    expect(screen.getByText("customer_dimension.customer_key")).toBeVisible();
    expect(screen.getByText("sales_fact.customer_key")).toBeVisible();
    expect(screen.getByText("The customer key establishes the conformed join.")).toBeVisible();
    expect(screen.getByText("Each sale has one customer; a customer has many sales.")).toBeVisible();
  });

  it("sends only supported bounded filters and follows opaque pagination cursors", async () => {
    const fetcher = dimensionalFetchStub({ hasNextPage: true });
    const user = userEvent.setup();
    render(<WorkbenchApp router={dimensionalRouter(fetcher)} />);
    await screen.findByRole("table", { name: "Dimensional Objects" });

    await user.type(screen.getByLabelText("Object name prefix"), " Sales ");
    await user.selectOptions(screen.getByLabelText("Object status"), "needs_review");
    await user.selectOptions(screen.getByLabelText("Object lock"), "false");
    await user.click(screen.getByRole("button", { name: "Apply Object filters" }));
    expect(fetcher).toHaveBeenCalledWith(
      "/api/v1/tenants/7/models/18/dimensional/objects?status=needs_review&locked=false&name_prefix=sales&page_size=200",
      expect.objectContaining({ credentials: "same-origin" }),
    );
    await user.click(await screen.findByRole("button", { name: "Load more Dimensional Objects" }));
    expect(fetcher).toHaveBeenCalledWith(
      "/api/v1/tenants/7/models/18/dimensional/objects?status=needs_review&locked=false&name_prefix=sales&page_size=200&cursor=objects-next",
      expect.objectContaining({ credentials: "same-origin" }),
    );

    await user.click(screen.getByRole("button", { name: "Attributes" }));
    await screen.findByRole("table", { name: "Dimensional Attributes" });
    await user.type(screen.getByLabelText("Attribute name prefix"), " Amount ");
    await user.type(screen.getByLabelText("Attribute Object ID"), "301");
    await user.click(screen.getByRole("button", { name: "Apply Attribute filters" }));
    expect(fetcher).toHaveBeenCalledWith(
      "/api/v1/tenants/7/models/18/dimensional/attributes?name_prefix=amount&dimensional_entity_id=301&page_size=200",
      expect.objectContaining({ credentials: "same-origin" }),
    );

    await user.click(screen.getByRole("button", { name: "Relationships" }));
    await screen.findByRole("table", { name: "Dimensional Relationships" });
    await user.type(screen.getByLabelText("Relationship name prefix"), " Customer ");
    await user.type(screen.getByLabelText("Relationship Object ID"), "302");
    await user.click(screen.getByRole("button", { name: "Apply Relationship filters" }));
    expect(fetcher).toHaveBeenCalledWith(
      "/api/v1/tenants/7/models/18/dimensional/relationships?name_prefix=customer&dimensional_entity_id=302&page_size=200",
      expect.objectContaining({ credentials: "same-origin" }),
    );
  });

  it("keeps empty, safe-error, denied, and revision mismatch states explicit", async () => {
    const empty = render(
      <WorkbenchApp router={dimensionalRouter(dimensionalFetchStub({ empty: true }))} />,
    );
    expect(await screen.findByText("No Dimensional Objects match these filters.")).toBeVisible();
    empty.unmount();

    const mismatch = render(
      <WorkbenchApp router={dimensionalRouter(dimensionalFetchStub({ modelRevision: 19 }))} />,
    );
    expect(await screen.findByRole("alert")).toHaveTextContent(
      "The Model changed while Dimensional Objects were loading.",
    );
    mismatch.unmount();

    const denied = render(
      <WorkbenchApp router={dimensionalRouter(dimensionalFetchStub({ denied: true }))} />,
    );
    expect(await screen.findByRole("alert")).toHaveTextContent(
      "You do not have permission to view Dimensional Objects.",
    );
    denied.unmount();

    render(<WorkbenchApp router={dimensionalRouter(dimensionalFetchStub({ error: true }))} />);
    expect(await screen.findByRole("alert")).toHaveTextContent(
      "Dimensional Objects could not be loaded.",
    );
  });

  it("keeps Dimensional execution lock-gated and explicitly creates then starts a run", async () => {
    const unlocked = render(
      <WorkbenchApp router={dimensionalRouter(dimensionalFetchStub({ hasLock: false }))} />,
    );
    await screen.findByRole("table", { name: "Dimensional Objects" });
    expect(screen.getByRole("button", { name: "Run Dimensional" })).toBeDisabled();
    expect(screen.getByText("Tenant Lock required to run")).toBeVisible();
    unlocked.unmount();

    const fetcher = dimensionalFetchStub();
    const user = userEvent.setup();
    render(<WorkbenchApp router={dimensionalRouter(fetcher)} />);
    await screen.findByRole("table", { name: "Dimensional Objects" });
    expect(screen.getByText("Tenant Lock held")).toBeVisible();
    await user.click(screen.getByRole("button", { name: "Run Dimensional" }));
    expect(await screen.findByRole("heading", { name: "Configure Dimensional run" })).toBeVisible();
    await user.click(screen.getByRole("button", { name: "Create and run Dimensional" }));

    expect(fetcher).toHaveBeenCalledWith(
      "/api/v1/tenants/7/models/18/runs",
      expect.objectContaining({
        method: "POST",
        body: expect.stringContaining('"model_workflow":"dimensional"'),
      }),
    );
    expect(fetcher).toHaveBeenCalledWith(
      "/api/v1/tenants/7/models/18/dimensional/runs/1250/execute",
      expect.objectContaining({
        method: "POST",
        body: JSON.stringify({ execution_mode: "one_shot", expected_model_revision: 18 }),
      }),
    );
  });
});

function dimensionalRouter(fetcher: ReturnType<typeof dimensionalFetchStub>) {
  return createWorkbenchRouter({
    api: createApiClient(fetcher),
    history: createMemoryHistory({
      initialEntries: ["/tenants/7/models/18/dimensional"],
    }),
  });
}

function dimensionalFetchStub(options: {
  empty?: boolean;
  error?: boolean;
  denied?: boolean;
  modelRevision?: number;
  hasNextPage?: boolean;
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
    if (url === "/api/v1/tenants/7/models/18") return jsonResponse(modelPayload);
    if (url.startsWith("/api/v1/tenants/7/models/18/dimensional/objects?")) {
      if (options.denied) return jsonResponse({ error: { code: "forbidden" } }, 403);
      if (options.error) return jsonResponse({ error: { code: "unavailable" } }, 503);
      const isNextPage = url.includes("cursor=objects-next");
      return jsonResponse({
        model_id: 18,
        model_revision: options.modelRevision ?? 18,
        items: options.empty
          ? []
          : [{
            ...dimensionalObjectPayload,
            ...(isNextPage
              ? { dimensional_entity_id: 302, dimensional_entity_name: "customer_dimension" }
              : {}),
          }],
        next_cursor: options.hasNextPage && !isNextPage ? "objects-next" : null,
      });
    }
    if (url === "/api/v1/tenants/7/models/18/dimensional/objects/301") {
      return jsonResponse(dimensionalObjectDetailPayload);
    }
    if (url.startsWith("/api/v1/tenants/7/models/18/dimensional/attributes?")) {
      return jsonResponse({
        model_id: 18,
        model_revision: 18,
        items: [dimensionalAttributePayload],
        next_cursor: null,
      });
    }
    if (url === "/api/v1/tenants/7/models/18/dimensional/attributes/401") {
      return jsonResponse(dimensionalAttributeDetailPayload);
    }
    if (url.startsWith("/api/v1/tenants/7/models/18/dimensional/relationships?")) {
      return jsonResponse({
        model_id: 18,
        model_revision: 18,
        items: [dimensionalRelationshipPayload],
        next_cursor: null,
      });
    }
    if (url === "/api/v1/tenants/7/models/18/dimensional/relationships/501") {
      return jsonResponse(dimensionalRelationshipDetailPayload);
    }
    if (url === "/api/v1/tenants/7/models/18/scope?zone=silver&page_size=200") {
      return jsonResponse({
        model_id: 18,
        model_revision: 18,
        items: [dimensionalScopeObjectPayload],
        next_cursor: null,
      });
    }
    if (url === "/api/v1/config/agent-capabilities") {
      return jsonResponse(agentCapabilitiesPayload);
    }
    if (url === "/api/v1/tenants/7/models/18/runs?workflow=dimensional&page_size=5") {
      return jsonResponse({ items: [], next_cursor: null });
    }
    if (url === "/api/v1/tenants/7/models/18/runs") {
      return jsonResponse({
        created: true,
        workflow_run_id: 1250,
        workflow_run_state: "queued",
        correlation_id: "dimensional-run-1250",
        prompt_snapshot_count: 5,
        created_at: "2026-08-24T16:00:00Z",
      }, 201);
    }
    if (url === "/api/v1/tenants/7/models/18/dimensional/runs/1250/execute") {
      return jsonResponse({
        changed: true,
        workflow_run_id: 1250,
        workflow_run_state: "running",
        started_at: "2026-08-24T16:00:01Z",
        model_revision: 18,
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
  model_scope_object_count: 25,
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

const dimensionalObjectPayload = {
  dimensional_entity_id: 301,
  workflow_run_id: 1200,
  dimensional_entity_name: "sales_fact",
  dimensional_entity_type: "fact",
  dimensional_fact_type: "transaction",
  dimensional_entity_dependency_order: 1,
  dimensional_entity_confidence: "high",
  dimensional_entity_status: "needs_review",
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
      support_source_type: "object",
      source_role: "primary",
      source_order: 1,
      rationale: "The Silver order table establishes the transaction grain.",
      status: "active",
      is_locked: false,
      created_at: "2026-08-24T14:42:00Z",
      updated_at: "2026-08-24T15:00:00Z",
      source_object: {
        object_id: 501,
        tenant_code: "DDS",
        system_code: "ERP",
        connection_code: "erp-prod",
        object_schema: "silver",
        object_name: "sales_order",
      },
    },
    {
      dimensional_entity_source_mapping_id: 902,
      workflow_run_id: null,
      support_source_type: "assertion",
      source_role: "supporting",
      source_order: 2,
      rationale: "The approved assertion confirms analytical grain.",
      status: "active",
      is_locked: true,
      created_at: "2026-08-24T14:43:00Z",
      updated_at: "2026-08-24T15:00:00Z",
      assertion_record: {
        modeling_assertion_record_id: 601,
        modeling_assertion_record_key: "assertion:sales-grain",
        modeling_assertion_document_name: "Sales model guide",
        modeling_assertion_record_type: "grain",
        modeling_assertion_text: "Sales facts are recorded at completed order-line grain.",
        modeling_assertion_confidence: "high",
        modeling_assertion_record_status: "active",
      },
    },
  ],
};

const dimensionalAttributePayload = {
  dimensional_attribute_id: 401,
  workflow_run_id: 1200,
  dimensional_entity_id: 301,
  dimensional_entity_name: "sales_fact",
  dimensional_attribute_name: "sales_amount",
  dimensional_attribute_data_type: "decimal(18,2)",
  dimensional_attribute_is_nullable: false,
  dimensional_attribute_ordinal_position: 5,
  dimensional_attribute_role: "measure",
  dimensional_attribute_key_role: "none",
  dimensional_attribute_is_grain_component: false,
  dimensional_attribute_additivity: "additive",
  dimensional_attribute_default_aggregation: "sum",
  dimensional_attribute_change_behavior: null,
  dimensional_attribute_is_audit_column: false,
  dimensional_attribute_confidence: "high",
  dimensional_attribute_status: "needs_review",
  dimensional_attribute_is_locked: false,
  updated_at: "2026-08-24T15:00:00Z",
};

const dimensionalAttributeDetailPayload = {
  ...dimensionalAttributePayload,
  dimensional_attribute_definition: "Extended monetary value of the completed order line.",
  dimensional_attribute_aggregation_basis: "Additive across all dimensional axes.",
  created_at: "2026-08-24T14:40:00Z",
  sources: [
    {
      dimensional_attribute_source_mapping_id: 1001,
      workflow_run_id: 1200,
      dimensional_entity_source_mapping_id: 901,
      support_source_type: "attribute",
      source_order: 1,
      rationale: "The Silver amount is the governed monetary source.",
      status: "active",
      is_locked: false,
      created_at: "2026-08-24T14:42:00Z",
      updated_at: "2026-08-24T15:00:00Z",
      source_attribute: {
        object_id: 501,
        attribute_id: 502,
        tenant_code: "DDS",
        system_code: "ERP",
        connection_code: "erp-prod",
        object_schema: "silver",
        object_name: "sales_order",
        attribute_name: "sales_amount",
      },
    },
    {
      dimensional_attribute_source_mapping_id: 1002,
      workflow_run_id: null,
      support_source_type: "assertion",
      source_order: 2,
      rationale: "The assertion establishes aggregation behavior.",
      status: "active",
      is_locked: true,
      created_at: "2026-08-24T14:43:00Z",
      updated_at: "2026-08-24T15:00:00Z",
      assertion_record: {
        modeling_assertion_record_id: 602,
        modeling_assertion_record_key: "assertion:additive-sales",
        modeling_assertion_document_name: "Sales model guide",
        modeling_assertion_record_type: "aggregation",
        modeling_assertion_text: "Sales amount is additive across all dimensions.",
        modeling_assertion_confidence: "high",
        modeling_assertion_record_status: "active",
      },
    },
  ],
};

const dimensionalRelationshipPayload = {
  dimensional_relationship_id: 501,
  workflow_run_id: 1200,
  from_dimensional_entity_id: 302,
  from_dimensional_entity_name: "customer_dimension",
  from_dimensional_attribute_id: 402,
  from_dimensional_attribute_name: "customer_key",
  to_dimensional_entity_id: 301,
  to_dimensional_entity_name: "sales_fact",
  to_dimensional_attribute_id: 403,
  to_dimensional_attribute_name: "customer_key",
  dimensional_relationship_name: "customer to sales",
  dimensional_relationship_kind: "foreign_key",
  dimensional_relationship_cardinality: "one_to_many",
  dimensional_relationship_is_optional: false,
  dimensional_relationship_role_name: "customer",
  dimensional_relationship_confidence: "high",
  dimensional_relationship_status: "needs_review",
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

const dimensionalScopeObjectPayload = {
  model_scope_id: 211,
  object_id: 511,
  connection_id: 311,
  system_id: 411,
  system_code: "GDS",
  system_name: "Governed Data Store",
  source_tenant_id: 7,
  source_tenant_code: "NWA",
  source_tenant_name: "Northwind Analytics",
  object_schema: "silver",
  object_name: "sales_order",
  zone_code: "silver",
  batch_attribute_name: "batch_id",
  attribute_count: 14,
  is_bronze_source_eligible: false,
  is_dimensional_source_eligible: true,
  is_logical_mapping_target_eligible: true,
  is_dimensional_mapping_target_eligible: false,
  created_at: "2026-08-24T14:00:00Z",
  updated_at: "2026-08-24T14:00:00Z",
};

const agentCapabilitiesPayload = {
  schema_version: "1.0",
  sdks: [{ code: "openai_agents", name: "OpenAI Agents", provider_codes: ["databricks"] }],
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
