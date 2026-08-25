import { render, screen } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { createMemoryHistory } from "@tanstack/react-router";
import { describe, expect, it, vi } from "vitest";

import { createApiClient } from "../../api";
import { WorkbenchApp, createWorkbenchRouter } from "../../app";

describe("Mapping journey", () => {
  it("opens Mapping as a model-first ledger", async () => {
    const fetcher = mappingFetchStub();
    const user = userEvent.setup();
    render(<WorkbenchApp router={createWorkbenchRouter({
      api: createApiClient(fetcher),
      history: createMemoryHistory({ initialEntries: ["/tenants/7"] }),
    })} />);

    await user.click(await screen.findByRole("link", { name: "Mapping" }));
    expect(await screen.findByRole("table", { name: "Models for Mapping" })).toBeVisible();
    expect(screen.getByRole("link", { name: "Open Customer 360 Mapping" })).toBeVisible();
  });

  it("opens a Model directly into server-filtered Mapping dependencies", async () => {
    const fetcher = mappingFetchStub();
    const user = userEvent.setup();
    render(<WorkbenchApp router={createWorkbenchRouter({
      api: createApiClient(fetcher),
      history: createMemoryHistory({ initialEntries: ["/tenants/7/mapping/models/18"] }),
    })} />);

    expect(await screen.findByRole("table", { name: "Mapping Dependencies" })).toBeVisible();
    expect(screen.queryByLabelText("Model journey")).not.toBeInTheDocument();
    expect(screen.getByRole("link", { name: "Back to Mapping Models" })).toBeVisible();

    await user.selectOptions(screen.getByLabelText("Entity type"), "logical_entity");
    await user.type(screen.getByLabelText("Source System code"), " CRM ");
    await user.selectOptions(screen.getByLabelText("Mapping status"), "needs_review");
    await user.selectOptions(screen.getByLabelText("Mapping lock"), "false");
    await user.click(screen.getByRole("button", { name: "Apply Mapping filters" }));

    expect(fetcher).toHaveBeenCalledWith(
      "/api/v1/tenants/7/models/18/mapping/dependencies?entity_type=logical_entity&source_system_code=crm&status=needs_review&locked=false&page_size=200",
      expect.objectContaining({ credentials: "same-origin" }),
    );
  });

  it("reviews Object and Attribute Mapping documents on dedicated pages", async () => {
    const fetcher = mappingFetchStub();
    const user = userEvent.setup();
    render(<WorkbenchApp router={createWorkbenchRouter({
      api: createApiClient(fetcher),
      history: createMemoryHistory({ initialEntries: ["/tenants/7/mapping/models/18"] }),
    })} />);

    await screen.findByRole("table", { name: "Mapping Dependencies" });
    await user.click(screen.getByRole("button", { name: "Object mappings" }));
    expect(await screen.findByRole("table", { name: "Object Mappings" })).toBeVisible();
    expect(screen.getByText("silver_nwa.customer")).toBeVisible();
    await user.click(screen.getByRole("link", { name: "Open Object Mapping 81" }));

    const objectHeading = await screen.findByRole("heading", { name: "silver_nwa.customer" });
    expect(objectHeading).toHaveFocus();
    expect(screen.getByRole("heading", { name: "Transformation document" })).toBeVisible();
    expect(screen.getByText("Join strategy")).toBeVisible();
    expect(screen.getByRole("article", { name: "Joins 1" })).toHaveTextContent("customer_address_raw");
    expect(screen.getByRole("heading", { name: "Mapping package" })).toBeVisible();
    expect(screen.getByText("customer_id")).toBeVisible();
    expect(screen.queryByText(JSON.stringify(mappingObjectDetail.mapping_document))).not.toBeInTheDocument();

    await user.click(screen.getByRole("link", { name: "Back to Mapping" }));
    expect(await screen.findByRole("table", { name: "Object Mappings" })).toBeVisible();
    await user.click(screen.getByRole("button", { name: "Attribute mappings" }));
    expect(await screen.findByRole("table", { name: "Attribute Mappings" })).toBeVisible();
    await user.click(screen.getByRole("link", { name: "Open Attribute Mapping 91" }));

    const attributeHeading = await screen.findByRole("heading", {
      name: "silver_nwa.customer.customer_name",
    });
    expect(attributeHeading).toHaveFocus();
    expect(screen.getByText("crm_customer.customer_name")).toBeVisible();
    expect(screen.getByText("Normalize whitespace")).toBeVisible();
    expect(screen.getByRole("heading", { name: "Parent Object Mapping" })).toBeVisible();
  });

  it("follows opaque Mapping cursors and refreshes the active ledger", async () => {
    const fetcher = mappingFetchStub({ hasNextPage: true });
    const user = userEvent.setup();
    render(<WorkbenchApp router={createWorkbenchRouter({
      api: createApiClient(fetcher),
      history: createMemoryHistory({ initialEntries: ["/tenants/7/mapping/models/18"] }),
    })} />);

    await screen.findByRole("table", { name: "Mapping Dependencies" });
    const dependencyCallsBeforeRefresh = fetcher.mock.calls.filter(([input]) => (
      String(input).includes("/mapping/dependencies?")
    )).length;
    await user.click(screen.getByRole("button", { name: "Refresh" }));
    expect(fetcher.mock.calls.filter(([input]) => (
      String(input).includes("/mapping/dependencies?")
    ))).toHaveLength(dependencyCallsBeforeRefresh + 1);

    await user.click(screen.getByRole("button", { name: "Object mappings" }));
    await screen.findByRole("table", { name: "Object Mappings" });
    await user.click(screen.getByRole("button", { name: "Load more Object Mappings" }));
    expect(fetcher).toHaveBeenCalledWith(
      "/api/v1/tenants/7/models/18/mapping/objects?page_size=200&cursor=objects-next",
      expect.objectContaining({ credentials: "same-origin" }),
    );
    expect(await screen.findByText("silver_nwa.contact")).toBeVisible();
  });

  it("keeps Mapping empty, safe-error, denied, and revision states explicit", async () => {
    const empty = render(<WorkbenchApp router={createWorkbenchRouter({
      api: createApiClient(mappingFetchStub({ empty: true })),
      history: createMemoryHistory({ initialEntries: ["/tenants/7/mapping/models/18"] }),
    })} />);
    expect(await screen.findByText("No Mapping Dependencies match these filters.")).toBeVisible();
    empty.unmount();

    const mismatch = render(<WorkbenchApp router={createWorkbenchRouter({
      api: createApiClient(mappingFetchStub({ modelRevision: 19 })),
      history: createMemoryHistory({ initialEntries: ["/tenants/7/mapping/models/18"] }),
    })} />);
    expect(await screen.findByRole("alert")).toHaveTextContent(
      "The Model changed while Mapping Dependencies were loading.",
    );
    mismatch.unmount();

    const denied = render(<WorkbenchApp router={createWorkbenchRouter({
      api: createApiClient(mappingFetchStub({ denied: true })),
      history: createMemoryHistory({ initialEntries: ["/tenants/7/mapping/models/18"] }),
    })} />);
    expect(await screen.findByRole("alert")).toHaveTextContent(
      "You do not have permission to view Mapping Dependencies.",
    );
    denied.unmount();

    render(<WorkbenchApp router={createWorkbenchRouter({
      api: createApiClient(mappingFetchStub({ error: true })),
      history: createMemoryHistory({ initialEntries: ["/tenants/7/mapping/models/18"] }),
    })} />);
    expect(await screen.findByRole("alert")).toHaveTextContent(
      "Mapping Dependencies could not be loaded.",
    );
  });

  it("requires App permission and Tenant Lock, then explicitly creates and executes one target", async () => {
    const unlocked = render(<WorkbenchApp router={createWorkbenchRouter({
      api: createApiClient(mappingFetchStub({ hasLock: false })),
      history: createMemoryHistory({ initialEntries: ["/tenants/7/mapping/models/18"] }),
    })} />);
    await screen.findByRole("table", { name: "Mapping Dependencies" });
    expect(screen.getByRole("button", { name: "Run Mapping" })).toBeDisabled();
    expect(screen.getByText("Tenant Lock required to run")).toBeVisible();
    unlocked.unmount();

    const denied = render(<WorkbenchApp router={createWorkbenchRouter({
      api: createApiClient(mappingFetchStub({ role: "developer" })),
      history: createMemoryHistory({ initialEntries: ["/tenants/7/mapping/models/18"] }),
    })} />);
    await screen.findByRole("table", { name: "Mapping Dependencies" });
    expect(screen.getByRole("button", { name: "Run Mapping" })).toBeDisabled();
    expect(screen.getByText("Architect permission required to run")).toBeVisible();
    denied.unmount();

    const fetcher = mappingFetchStub();
    const user = userEvent.setup();
    render(<WorkbenchApp router={createWorkbenchRouter({
      api: createApiClient(fetcher),
      history: createMemoryHistory({ initialEntries: ["/tenants/7/mapping/models/18"] }),
    })} />);
    await screen.findByRole("table", { name: "Mapping Dependencies" });
    await user.click(screen.getByRole("button", { name: "Run Mapping" }));
    expect(await screen.findByRole("heading", { name: "Configure Mapping run" })).toBeVisible();
    expect(screen.getByLabelText("Object Mapping Output Template")).toHaveValue("");
    expect(screen.getByLabelText("Attribute Mapping Output Template")).toHaveValue("");
    expect(screen.getByRole("option", {
      name: "Standard Object Mapping · Schema valid",
    })).toBeInTheDocument();
    expect(screen.getByRole("option", {
      name: "Broken Object Mapping · Schema invalid",
    })).toBeDisabled();
    await user.selectOptions(screen.getByLabelText("Target Object"), "701");
    await user.selectOptions(screen.getByLabelText("Source System"), "2");
    await user.selectOptions(screen.getByLabelText("Object Mapping Output Template"), "801");
    await user.selectOptions(screen.getByLabelText("Attribute Mapping Output Template"), "802");
    await user.click(screen.getByRole("button", { name: "Create and run Mapping" }));

    const createCall = fetcher.mock.calls.find(([input, init]) => (
      String(input) === "/api/v1/tenants/7/models/18/runs" && init?.method === "POST"
    ));
    expect(createCall).toBeDefined();
    expect(JSON.parse(String(createCall?.[1]?.body))).toEqual({
      expected_model_revision: 18,
      model_workflow: "mapping",
      workflow_execution_mode: "one_shot",
      selected_object_ids: [701],
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
      mapping_operation: "build",
      mapping_coverage_mode: "selected_targets",
      mapping_artifact_type: "sql_file",
      mapping_source_system_id: 2,
      mapping_object_output_template_id: 801,
      mapping_attribute_output_template_id: 802,
    });
    expect(fetcher).toHaveBeenCalledWith(
      "/api/v1/tenants/7/models/18/mapping/runs/1150/execute",
      expect.objectContaining({
        method: "POST",
        body: JSON.stringify({ execution_mode: "one_shot", expected_model_revision: 18 }),
      }),
    );
  });

  it("preserves independent free-form Output Template choices as null", async () => {
    const fetcher = mappingFetchStub();
    const user = userEvent.setup();
    render(<WorkbenchApp router={createWorkbenchRouter({
      api: createApiClient(fetcher),
      history: createMemoryHistory({ initialEntries: ["/tenants/7/mapping/models/18"] }),
    })} />);

    await screen.findByRole("table", { name: "Mapping Dependencies" });
    await user.click(screen.getByRole("button", { name: "Run Mapping" }));
    await screen.findByRole("option", { name: "Standard Attribute Mapping · Schema valid" });
    await user.selectOptions(screen.getByLabelText("Target Object"), "701");
    await user.selectOptions(screen.getByLabelText("Source System"), "2");
    await user.click(screen.getByRole("button", { name: "Create and run Mapping" }));

    const createCall = fetcher.mock.calls.find(([input, init]) => (
      String(input) === "/api/v1/tenants/7/models/18/runs" && init?.method === "POST"
    ));
    expect(JSON.parse(String(createCall?.[1]?.body))).toEqual(expect.objectContaining({
      mapping_object_output_template_id: null,
      mapping_attribute_output_template_id: null,
    }));
  });
});

function mappingFetchStub(options: {
  hasNextPage?: boolean;
  empty?: boolean;
  denied?: boolean;
  error?: boolean;
  modelRevision?: number;
  hasLock?: boolean;
  role?: string;
} = {}) {
  return vi.fn<typeof fetch>(async (input) => {
    const url = String(input);
    if (url === "/api/v1/tenants/7/home") return jsonResponse({
      ...tenantHome,
      tenant: { ...tenantHome.tenant, effective_role: options.role ?? "tenant_admin" },
      lock: {
        ...tenantHome.lock,
        is_locked: options.hasLock ?? true,
        owned_by_current_principal: options.hasLock ?? true,
      },
    });
    if (url === "/api/v1/tenants/7/models?status=active&page_size=200") {
      return jsonResponse({ items: [modelLedger], next_cursor: null });
    }
    if (url === "/api/v1/tenants/7/models/18") return jsonResponse(modelDetail);
    if (url.startsWith("/api/v1/tenants/7/models/18/mapping/dependencies?")) {
      if (options.denied) return jsonResponse({ error: { code: "authorization_denied" } }, 403);
      if (options.error) return jsonResponse({ error: { code: "unavailable" } }, 503);
      return jsonResponse({
        model_id: 18,
        model_revision: options.modelRevision ?? 18,
        items: options.empty ? [] : [dependency],
        next_cursor: null,
      });
    }
    if (url.startsWith("/api/v1/tenants/7/models/18/mapping/objects?")) {
      const nextPage = url.includes("cursor=objects-next");
      return jsonResponse({
        model_id: 18,
        model_revision: 18,
        items: [{
          ...mappingObject,
          ...(nextPage ? { mapping_object_id: 82, target: { ...mappingObject.target, object_name: "contact" } } : {}),
        }],
        next_cursor: options.hasNextPage && !nextPage ? "objects-next" : null,
      });
    }
    if (url === "/api/v1/tenants/7/models/18/mapping/objects/81") return jsonResponse(mappingObjectDetail);
    if (url.startsWith("/api/v1/tenants/7/models/18/mapping/attributes?")) {
      return jsonResponse({ model_id: 18, model_revision: 18, items: [mappingAttribute], next_cursor: null });
    }
    if (url === "/api/v1/tenants/7/models/18/mapping/attributes/91") return jsonResponse(mappingAttributeDetail);
    if (url === "/api/v1/tenants/7/models/18/scope?page_size=200") {
      return jsonResponse({ model_id: 18, model_revision: 18, items: mappingScope, next_cursor: null });
    }
    if (url === "/api/v1/tenants/7/output-templates?target_type=mapping_object&active=true&page_size=200") {
      return jsonResponse({
        tenant_id: 7,
        items: [objectOutputTemplate, {
          ...objectOutputTemplate,
          output_template_id: 803,
          output_template_code: "mapping.object.broken",
          output_template_name: "Broken Object Mapping",
          output_template_schema_digest_is_valid: false,
        }],
        next_cursor: null,
      });
    }
    if (url === "/api/v1/tenants/7/output-templates?target_type=mapping_attribute&active=true&page_size=200") {
      return jsonResponse({ tenant_id: 7, items: [attributeOutputTemplate], next_cursor: null });
    }
    if (url === "/api/v1/config/agent-capabilities") return jsonResponse(agentCapabilities);
    if (url === "/api/v1/tenants/7/models/18/runs") {
      return jsonResponse({
        created: true,
        workflow_run_id: 1150,
        workflow_run_state: "queued",
        correlation_id: "mapping-run-1150",
        prompt_snapshot_count: 5,
        created_at: "2026-08-24T11:00:00Z",
      }, 201);
    }
    if (url === "/api/v1/tenants/7/models/18/mapping/runs/1150/execute") {
      return jsonResponse({
        changed: true,
        workflow_run_id: 1150,
        workflow_run_state: "running",
        model_revision: 18,
      }, 202);
    }
    return new Response(null, { status: 404 });
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
    purpose: "Mapping review",
    acquired_at: "2026-08-24T10:00:00Z",
    expires_at: "2026-08-24T12:00:00Z",
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
  latest_workflow: "mapping",
  latest_run_status: "completed",
  updated_at: "2026-08-24T10:00:00Z",
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

const dependency = {
  mapping_source_system_dependency_id: 71,
  workflow_run_id: null,
  entity_type: "logical_entity",
  source_system: { system_id: 2, system_code: "CRM", system_name: "Customer CRM" },
  dependency_order: 10,
  status: "active",
  is_locked: false,
  updated_at: "2026-08-24T10:00:00Z",
};

const mappingTarget = {
  object_id: 701,
  tenant_id: 7,
  tenant_code: "NWA",
  tenant_name: "Northwind Analytics",
  system_id: 4,
  system_code: "GDS",
  system_name: "Global Data Store",
  connection_id: 8,
  connection_code: "gds_primary",
  object_schema: "silver_nwa",
  object_name: "customer",
  zone_code: "silver",
};

const mappingObject = {
  mapping_object_id: 81,
  workflow_run_id: 1048,
  target: mappingTarget,
  source: { entity_type: "logical_entity", entity_id: 41, entity_name: "Customer" },
  source_system: { system_id: 2, system_code: "CRM", system_name: "Customer CRM" },
  dependency_order: 10,
  artifact_type: "sql_file",
  status: "active",
  is_locked: true,
  updated_at: "2026-08-24T10:00:00Z",
};

const mappingObjectDetail = {
  ...mappingObject,
  artifact_generation_instructions: "Generate idempotent SQL.",
  mapping_profile: {
    profile_key: "mapping.standard",
    profile_version: "1.0.0",
    profile_schema_digest: "a".repeat(64),
    package_digest: "b".repeat(64),
  },
  mapping_package_document: {
    source_objects: [{ schema: "bronze_crm", name: "customer_raw" }],
    business_keys: ["customer_id"],
  },
  mapping_document_format: "structured",
  mapping_document: {
    transformation_kind: "derived",
    join_strategy: {
      base_object: "customer_raw",
      joins: [{ object_name: "customer_address_raw", join_type: "left" }],
    },
    filter_criteria: ["customer_raw.is_deleted = false"],
  },
  output_template: {
    output_template_id: 31,
    output_template_code: "mapping.object.standard",
    output_template_name: "Standard Object Mapping",
    output_template_target_type: "mapping_object",
    output_template_schema_digest: "c".repeat(64),
    is_active: true,
  },
  created_at: "2026-08-24T09:00:00Z",
};

const mappingAttribute = {
  mapping_attribute_id: 91,
  workflow_run_id: 1048,
  mapping_object_id: 81,
  target: {
    object: mappingTarget,
    attribute_id: 702,
    attribute_name: "customer_name",
    attribute_ordinal_position: 2,
    attribute_data_type: "string",
  },
  source: {
    entity: { entity_type: "logical_entity", entity_id: 41, entity_name: "crm_customer" },
    attribute_id: 42,
    attribute_name: "customer_name",
  },
  source_system: { system_id: 2, system_code: "CRM", system_name: "Customer CRM" },
  status: "needs_review",
  is_locked: false,
  updated_at: "2026-08-24T10:00:00Z",
};

const mappingAttributeDetail = {
  ...mappingAttribute,
  parent_object_mapping: {
    mapping_object_id: 81,
    dependency_order: 10,
    artifact_type: "sql_file",
    mapping_profile: mappingObjectDetail.mapping_profile,
    status: "active",
    is_locked: true,
  },
  mapping_document_format: "structured",
  mapping_document: {
    source_attributes: ["crm_customer.customer_name"],
    transformation_steps: [{ step: 1, instruction: "Normalize whitespace" }],
  },
  output_template: {
    ...mappingObjectDetail.output_template,
    output_template_id: 32,
    output_template_code: "mapping.attribute.standard",
    output_template_name: "Standard Attribute Mapping",
    output_template_target_type: "mapping_attribute",
  },
  created_at: "2026-08-24T09:05:00Z",
};

const mappingScope = [
  {
    model_scope_id: 201,
    object_id: 701,
    connection_id: 8,
    system_id: 4,
    system_code: "GDS",
    system_name: "Global Data Store",
    source_tenant_id: 7,
    source_tenant_code: "NWA",
    source_tenant_name: "Northwind Analytics",
    object_schema: "silver_nwa",
    object_name: "customer",
    zone_code: "silver",
    batch_attribute_name: null,
    attribute_count: 14,
    is_bronze_source_eligible: false,
    is_dimensional_source_eligible: true,
    is_logical_mapping_target_eligible: true,
    is_dimensional_mapping_target_eligible: false,
    created_at: "2026-08-24T09:00:00Z",
    updated_at: "2026-08-24T10:00:00Z",
  },
  {
    model_scope_id: 202,
    object_id: 501,
    connection_id: 6,
    system_id: 2,
    system_code: "CRM",
    system_name: "Customer CRM",
    source_tenant_id: 9,
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
    created_at: "2026-08-24T09:00:00Z",
    updated_at: "2026-08-24T10:00:00Z",
  },
];

const agentCapabilities = {
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

const objectOutputTemplate = {
  output_template_id: 801,
  output_template_code: "mapping.object.standard",
  output_template_name: "Standard Object Mapping",
  output_template_description: "Structured Object Mapping output.",
  output_template_target_type: "mapping_object",
  output_template_schema_digest: "c".repeat(64),
  output_template_schema_digest_is_valid: true,
  is_active: true,
  field_count: 5,
};

const attributeOutputTemplate = {
  ...objectOutputTemplate,
  output_template_id: 802,
  output_template_code: "mapping.attribute.standard",
  output_template_name: "Standard Attribute Mapping",
  output_template_description: "Structured Attribute Mapping output.",
  output_template_target_type: "mapping_attribute",
  output_template_schema_digest: "d".repeat(64),
  field_count: 4,
};

function jsonResponse(value: unknown, status = 200): Response {
  return new Response(JSON.stringify(value), {
    status,
    headers: { "content-type": "application/json" },
  });
}
