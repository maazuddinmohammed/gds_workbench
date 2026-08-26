import { render, screen, within } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { createMemoryHistory } from "@tanstack/react-router";
import { describe, expect, it, vi } from "vitest";

import { createApiClient } from "../../api";
import { WorkbenchApp, createWorkbenchRouter } from "../../app";

describe("Model Logical", () => {
  it("reviews a Logical Entity and its complete normalized context on a detail page", async () => {
    const fetcher = logicalFetchStub();
    const user = userEvent.setup();
    render(<WorkbenchApp router={logicalRouter(fetcher)} />);

    const ledger = await screen.findByRole("table", { name: "Logical Entities" });
    expect(within(ledger).getByText("customer_account")).toBeVisible();

    await user.click(screen.getByRole("link", { name: "Open Logical Entity 71" }));

    expect(await screen.findByRole("heading", { name: "customer_account" })).toBeVisible();
    expect(screen.getByRole("heading", { name: "Submodel membership" })).toBeVisible();
    expect(screen.getByText("Customer domain")).toBeVisible();
    expect(screen.getByRole("heading", { name: "Source mappings" })).toBeVisible();
    expect(screen.getByText("GRDM · CRM · crm-prod")).toBeVisible();
    expect(screen.getAllByText("bronze.customer_raw")).toHaveLength(2);
    expect(screen.getByText("Customer identity is governed across systems.")).toBeVisible();
    expect(screen.getAllByText("Workflow run 1048").length).toBeGreaterThan(0);
  });

  it("reviews Submodels, Attributes, and Relationships in dedicated ledgers and pages", async () => {
    const user = userEvent.setup();
    render(<WorkbenchApp router={logicalRouter(logicalFetchStub())} />);
    await screen.findByRole("table", { name: "Logical Entities" });

    await user.click(screen.getByRole("button", { name: "Submodels" }));
    expect(await screen.findByRole("table", { name: "Logical Submodels" })).toBeVisible();
    await user.click(screen.getByRole("link", { name: "Open Logical Submodel 91" }));
    expect(await screen.findByRole("heading", { name: "Customer domain" })).toBeVisible();
    expect(screen.getByRole("heading", { name: "Member entities" })).toBeVisible();
    expect(screen.getByText("customer_account")).toBeVisible();

    await user.click(screen.getByRole("link", { name: "Back to Logical" }));
    await user.click(screen.getByRole("button", { name: "Attributes" }));
    expect(await screen.findByRole("table", { name: "Logical Attributes" })).toBeVisible();
    await user.click(screen.getByRole("link", { name: "Open Logical Attribute 81" }));
    expect(await screen.findByRole("heading", { name: "customer_id" })).toBeVisible();
    expect(screen.getByRole("heading", { name: "Source mappings" })).toBeVisible();
    expect(screen.getAllByText("bronze.customer_raw.customer_id").length).toBeGreaterThan(0);

    await user.click(screen.getByRole("link", { name: "Back to Logical" }));
    await user.click(screen.getByRole("button", { name: "Relationships" }));
    expect(await screen.findByRole("table", { name: "Logical Relationships" })).toBeVisible();
    await user.click(screen.getByRole("link", { name: "Open Logical Relationship 101" }));
    expect(await screen.findByRole("heading", { name: "customer places order" })).toBeVisible();
    expect(screen.getByText("Customer activity establishes order ownership.")).toBeVisible();
    expect(screen.getByText("customer_account.customer_id")).toBeVisible();
    expect(screen.getByText("sales_order.customer_id")).toBeVisible();
  });

  it("uses backend Logical filters and keeps empty, error, and revision states explicit", async () => {
    const user = userEvent.setup();
    const fetcher = logicalFetchStub();
    const filtered = render(<WorkbenchApp router={logicalRouter(fetcher)} />);
    await screen.findByRole("table", { name: "Logical Entities" });

    await user.type(screen.getByLabelText("Entity name prefix"), " Customer ");
    await user.selectOptions(screen.getByLabelText("Entity Submodel"), "91");
    await user.selectOptions(screen.getByLabelText("Entity status"), "needs_review");
    await user.selectOptions(screen.getByLabelText("Entity lock"), "true");
    await user.click(screen.getByRole("button", { name: "Apply Entity filters" }));
    expect(fetcher).toHaveBeenCalledWith(
      "/api/v1/tenants/7/models/18/logical/entities?status=needs_review&locked=true&name_prefix=customer&logical_submodel_id=91&page_size=200",
      expect.objectContaining({ credentials: "same-origin" }),
    );
    filtered.unmount();

    const empty = render(
      <WorkbenchApp router={logicalRouter(logicalFetchStub({ empty: true }))} />,
    );
    expect(await screen.findByText("No Logical Entities match these filters.")).toBeVisible();
    empty.unmount();

    const mismatch = render(
      <WorkbenchApp router={logicalRouter(logicalFetchStub({ modelRevision: 19 }))} />,
    );
    expect(await screen.findByRole("alert")).toHaveTextContent(
      "The Model changed while Logical Entities were loading.",
    );
    mismatch.unmount();

    render(<WorkbenchApp router={logicalRouter(logicalFetchStub({ error: true }))} />);
    expect(await screen.findByRole("alert")).toHaveTextContent(
      "Logical Entities could not be loaded.",
    );
  });

  it("keeps Logical execution lock-gated and explicitly creates then starts a run", async () => {
    const unlocked = render(
      <WorkbenchApp router={logicalRouter(logicalFetchStub({ hasLock: false }))} />,
    );
    await screen.findByRole("table", { name: "Logical Entities" });
    expect(screen.getByRole("button", { name: "Run Logical" })).toBeDisabled();
    expect(screen.getByText("Tenant Lock required to run")).toBeVisible();
    unlocked.unmount();

    const fetcher = logicalFetchStub();
    const user = userEvent.setup();
    render(<WorkbenchApp router={logicalRouter(fetcher)} />);
    await screen.findByRole("table", { name: "Logical Entities" });
    expect(screen.getByText("Tenant Lock held")).toBeVisible();
    await user.click(screen.getByRole("button", { name: "Run Logical" }));
    expect(await screen.findByRole("heading", { name: "Configure Logical run" })).toBeVisible();
    await user.click(screen.getByRole("button", { name: "Create and run Logical" }));

    expect(fetcher).toHaveBeenCalledWith(
      "/api/v1/tenants/7/models/18/runs",
      expect.objectContaining({
        method: "POST",
        body: expect.stringContaining('"model_workflow":"logical"'),
      }),
    );
    expect(fetcher).toHaveBeenCalledWith(
      "/api/v1/tenants/7/models/18/logical/runs/1050/execute",
      expect.objectContaining({
        method: "POST",
        body: JSON.stringify({ execution_mode: "one_shot", expected_model_revision: 18 }),
      }),
    );
  });
});

function logicalRouter(fetcher: ReturnType<typeof logicalFetchStub>) {
  return createWorkbenchRouter({
    api: createApiClient(fetcher),
    history: createMemoryHistory({
      initialEntries: ["/tenants/7/models/18/logical"],
    }),
  });
}

function logicalFetchStub(options: {
  empty?: boolean;
  error?: boolean;
  modelRevision?: number;
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
    if (url === "/api/v1/tenants/7/models/18") return jsonResponse(modelPayload);
    if (url.startsWith("/api/v1/tenants/7/models/18/logical/entities?")) {
      if (options.error) return jsonResponse({ error: { code: "unavailable" } }, 503);
      return jsonResponse({
        model_id: 18,
        model_revision: options.modelRevision ?? 18,
        items: options.empty ? [] : [logicalEntityPayload],
        next_cursor: null,
      });
    }
    if (url === "/api/v1/tenants/7/models/18/logical/entities/71") {
      return jsonResponse(logicalEntityDetailPayload);
    }
    if (url.startsWith("/api/v1/tenants/7/models/18/logical/submodels?")) {
      return jsonResponse({
        model_id: 18,
        model_revision: 18,
        items: [logicalSubmodelPayload],
        next_cursor: null,
      });
    }
    if (url === "/api/v1/tenants/7/models/18/logical/submodels/91") {
      return jsonResponse(logicalSubmodelDetailPayload);
    }
    if (url.startsWith("/api/v1/tenants/7/models/18/logical/attributes?")) {
      return jsonResponse({
        model_id: 18,
        model_revision: 18,
        items: [logicalAttributePayload],
        next_cursor: null,
      });
    }
    if (url === "/api/v1/tenants/7/models/18/logical/attributes/81") {
      return jsonResponse(logicalAttributeDetailPayload);
    }
    if (url.startsWith("/api/v1/tenants/7/models/18/logical/relationships?")) {
      return jsonResponse({
        model_id: 18,
        model_revision: 18,
        items: [logicalRelationshipPayload],
        next_cursor: null,
      });
    }
    if (url === "/api/v1/tenants/7/models/18/logical/relationships/101") {
      return jsonResponse(logicalRelationshipDetailPayload);
    }
    if (url === "/api/v1/tenants/7/models/18/scope?zone=bronze&page_size=200") {
      return jsonResponse({
        model_id: 18,
        model_revision: 18,
        items: [scopeObjectPayload],
        next_cursor: null,
      });
    }
    if (url === "/api/v1/config/agent-capabilities") {
      return jsonResponse(agentCapabilitiesPayload);
    }
    if (url === "/api/v1/tenants/7/models/18/runs?workflow=logical&page_size=5") {
      return jsonResponse({ items: [], next_cursor: null });
    }
    if (url === "/api/v1/tenants/7/models/18/runs" && init?.method === "POST") {
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
      url === "/api/v1/tenants/7/models/18/logical/runs/1050/execute"
      && init?.method === "POST"
    ) {
      return jsonResponse({
        changed: true,
        workflow_run_id: 1050,
        workflow_run_state: "running",
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

const logicalEntityPayload = {
  logical_entity_id: 71,
  workflow_run_id: 1048,
  logical_entity_name: "customer_account",
  logical_entity_type: "core",
  logical_entity_dependency_order: 1,
  logical_entity_confidence: "high",
  logical_entity_status: "needs_review",
  logical_entity_is_locked: false,
  updated_at: "2026-08-24T15:00:00Z",
};

const logicalEntityDetailPayload = {
  ...logicalEntityPayload,
  logical_entity_definition: "A governed customer identity used by downstream models.",
  logical_entity_type_detail: null,
  logical_entity_grain: "One row per recognized customer.",
  created_at: "2026-08-24T14:40:00Z",
  submodels: [
    {
      logical_entity_submodel_id: 801,
      workflow_run_id: 1048,
      logical_submodel_id: 91,
      logical_submodel_name: "Customer domain",
      membership_status: "active",
      membership_is_locked: false,
      created_at: "2026-08-24T14:45:00Z",
      updated_at: "2026-08-24T15:00:00Z",
    },
  ],
  sources: [
    {
      logical_entity_source_mapping_id: 901,
      workflow_run_id: 1048,
      support_source_type: "object",
      source_order: 1,
      rationale: "The CRM customer table establishes the entity grain.",
      status: "active",
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
      support_source_type: "assertion",
      source_order: 2,
      rationale: "The assertion confirms cross-system semantics.",
      status: "needs_review",
      is_locked: true,
      created_at: "2026-08-24T14:46:00Z",
      updated_at: "2026-08-24T15:00:00Z",
      assertion_record: {
        modeling_assertion_record_id: 91,
        modeling_assertion_record_key: "customer.identity.governed",
        modeling_assertion_document_name: "Customer governance rules",
        modeling_assertion_record_type: "identity_rule",
        modeling_assertion_text: "Customer identity is governed across systems.",
        modeling_assertion_confidence: "high",
        modeling_assertion_record_status: "needs_review",
      },
    },
  ],
};

const logicalSubmodelPayload = {
  logical_submodel_id: 91,
  workflow_run_id: 1048,
  logical_submodel_name: "Customer domain",
  logical_submodel_status: "active",
  logical_submodel_is_locked: false,
  entity_count: 1,
  updated_at: "2026-08-24T15:00:00Z",
};

const logicalSubmodelDetailPayload = {
  ...logicalSubmodelPayload,
  logical_submodel_definition: "Customer identity and engagement boundary.",
  created_at: "2026-08-24T14:40:00Z",
  entities: [
    {
      logical_entity_submodel_id: 801,
      workflow_run_id: 1048,
      logical_entity_id: 71,
      logical_entity_name: "customer_account",
      logical_entity_type: "core",
      logical_entity_status: "needs_review",
      membership_status: "active",
      membership_is_locked: false,
      created_at: "2026-08-24T14:45:00Z",
      updated_at: "2026-08-24T15:00:00Z",
    },
  ],
};

const logicalAttributePayload = {
  logical_attribute_id: 81,
  workflow_run_id: 1048,
  logical_entity_id: 71,
  logical_entity_name: "customer_account",
  logical_attribute_name: "customer_id",
  logical_attribute_data_type: "bigint",
  logical_attribute_is_nullable: false,
  logical_attribute_is_primary_key: true,
  logical_attribute_is_natural_key: false,
  logical_attribute_is_surrogate_key: true,
  logical_attribute_ordinal_position: 1,
  logical_attribute_is_audit_column: false,
  logical_attribute_status: "active",
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
      source_order: 1,
      rationale: "Source customer identifier seeds the surrogate key.",
      status: "active",
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

const logicalRelationshipPayload = {
  logical_relationship_id: 101,
  workflow_run_id: 1048,
  from_logical_entity_id: 71,
  from_logical_entity_name: "customer_account",
  from_logical_attribute_id: 81,
  from_logical_attribute_name: "customer_id",
  to_logical_entity_id: 72,
  to_logical_entity_name: "sales_order",
  to_logical_attribute_id: 82,
  to_logical_attribute_name: "customer_id",
  logical_relationship_name: "customer places order",
  logical_relationship_cardinality: "one_to_many",
  logical_relationship_confidence: "high",
  logical_relationship_status: "needs_review",
  logical_relationship_is_locked: false,
  updated_at: "2026-08-24T15:00:00Z",
};

const logicalRelationshipDetailPayload = {
  ...logicalRelationshipPayload,
  logical_relationship_definition: "One customer may place many orders.",
  logical_relationship_basis: "Customer activity establishes order ownership.",
  logical_relationship_cardinality_basis: "One customer key occurs on many order records.",
  created_at: "2026-08-24T14:42:00Z",
};

const scopeObjectPayload = {
  model_scope_id: 201,
  object_id: 501,
  connection_id: 301,
  system_id: 401,
  system_code: "CRM",
  system_name: "Customer Relationship Management",
  source_tenant_id: 8,
  source_tenant_code: "GRDM",
  source_tenant_name: "Global Reference Data",
  object_schema: "bronze",
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
