import { render, screen, waitFor, within } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { createMemoryHistory } from "@tanstack/react-router";
import { describe, expect, it, vi } from "vitest";

import { createApiClient } from "../../api";
import { WorkbenchApp, createWorkbenchRouter } from "../../app";

describe("Model Conceptual", () => {
  it("filters Conceptual Objects and opens full support evidence", async () => {
    const fetcher = conceptualFetchStub();
    const user = userEvent.setup();
    render(<WorkbenchApp router={conceptualRouter(fetcher)} />);

    const ledger = await screen.findByRole("table", { name: "Conceptual Objects" });
    expect(within(ledger).getByText("customer")).toBeVisible();

    await user.type(screen.getByLabelText("Object name prefix"), " Customer ");
    await user.selectOptions(screen.getByLabelText("Object status"), "needs_review");
    await user.selectOptions(screen.getByLabelText("Object lock"), "true");
    await user.click(screen.getByRole("button", { name: "Apply Object filters" }));

    expect(fetcher).toHaveBeenCalledWith(
      "/api/v1/tenants/7/models/18/conceptual/objects?status=needs_review&locked=true&name_prefix=customer&page_size=200",
      expect.objectContaining({ credentials: "same-origin" }),
    );

    await user.click(await screen.findByRole("link", { name: "Open Conceptual Object 41" }));
    const heading = await screen.findByRole("heading", { name: "customer" });
    expect(heading).toHaveFocus();
    expect(screen.getByText("One recognized customer identity.")).toBeVisible();
    expect(screen.getByRole("heading", { name: "Support evidence" })).toBeVisible();
    expect(screen.getByText("GRDM · CRM · crm-prod")).toBeVisible();
    expect(screen.getAllByText("bronze.customer_raw")).toHaveLength(2);
    expect(screen.getByText("Customer identity remains stable across CRM and ERP.")).toBeVisible();
    const physical = screen.getByRole("article", { name: "Support 61" });
    expect(within(physical).getByText("Object 501")).toBeVisible();
    expect(within(physical).getByText("No workflow provenance")).toBeVisible();
    expect(within(physical).getByText("Locked")).toBeVisible();
    const assertion = screen.getByRole("article", { name: "Support 62" });
    expect(within(assertion).getByText("Assertion 91")).toBeVisible();
    expect(within(assertion).getByText("Workflow run 1048")).toBeVisible();

    await user.click(screen.getByRole("link", { name: "Back to Conceptual" }));
    expect(await screen.findByRole("table", { name: "Conceptual Objects" })).toBeVisible();
  });

  it("reviews Conceptual Relationships on a separate detail page", async () => {
    const fetcher = conceptualFetchStub();
    const user = userEvent.setup();
    render(<WorkbenchApp router={conceptualRouter(fetcher)} />);
    await screen.findByRole("table", { name: "Conceptual Objects" });

    await user.click(screen.getByRole("button", { name: "Relationships" }));
    const ledger = await screen.findByRole("table", { name: "Conceptual Relationships" });
    expect(within(ledger).getByText("customer places order")).toBeVisible();
    await user.click(screen.getByRole("link", { name: "Open Conceptual Relationship 51" }));

    expect(await screen.findByRole("heading", { name: "customer places order" })).toBeVisible();
    expect(screen.getByText("Customer")).toBeVisible();
    expect(screen.getByText("Order")).toBeVisible();
    expect(screen.getByText("Customer activity establishes order ownership.")).toBeVisible();
    expect(screen.getByRole("article", { name: "Support 61" })).toBeVisible();
  });

  it("follows opaque pagination cursors for each supported Conceptual ledger", async () => {
    const fetcher = conceptualFetchStub({ hasNextPage: true });
    const user = userEvent.setup();
    render(<WorkbenchApp router={conceptualRouter(fetcher)} />);
    await screen.findByRole("table", { name: "Conceptual Objects" });

    await user.click(screen.getByRole("button", { name: "Load more Conceptual Objects" }));
    expect(fetcher).toHaveBeenCalledWith(
      "/api/v1/tenants/7/models/18/conceptual/objects?page_size=200&cursor=objects-next",
      expect.objectContaining({ credentials: "same-origin" }),
    );

    await user.click(screen.getByRole("button", { name: "Relationships" }));
    await screen.findByRole("table", { name: "Conceptual Relationships" });
    await user.click(screen.getByRole("button", { name: "Load more Conceptual Relationships" }));
    expect(fetcher).toHaveBeenCalledWith(
      "/api/v1/tenants/7/models/18/conceptual/relationships?page_size=200&cursor=relationships-next",
      expect.objectContaining({ credentials: "same-origin" }),
    );
  });

  it("keeps refresh, empty, error, and revision states explicit", async () => {
    const user = userEvent.setup();
    const emptyFetcher = conceptualFetchStub({ empty: true });
    const emptyRender = render(<WorkbenchApp router={conceptualRouter(emptyFetcher)} />);
    expect(await screen.findByText("No Conceptual Objects match these filters.")).toBeVisible();
    await user.click(screen.getByRole("button", { name: "Refresh" }));
    expect(emptyFetcher.mock.calls.filter(([input]) => String(input).includes("/conceptual/objects?")))
      .toHaveLength(2);
    emptyRender.unmount();

    const mismatchRender = render(
      <WorkbenchApp router={conceptualRouter(conceptualFetchStub({ modelRevision: 19 }))} />,
    );
    expect(await screen.findByRole("alert")).toHaveTextContent(
      "The Model changed while Conceptual Objects were loading.",
    );
    mismatchRender.unmount();

    render(<WorkbenchApp router={conceptualRouter(conceptualFetchStub({ error: true }))} />);
    expect(await screen.findByRole("alert")).toHaveTextContent(
      "Conceptual Objects could not be loaded.",
    );
  });

  it("keeps collection and detail permission failures explicit", async () => {
    const denied = render(
      <WorkbenchApp router={conceptualRouter(conceptualFetchStub({ denied: true }))} />,
    );
    expect(await screen.findByRole("alert")).toHaveTextContent(
      "You do not have permission to view Conceptual Objects.",
    );
    denied.unmount();

    const user = userEvent.setup();
    render(<WorkbenchApp router={conceptualRouter(conceptualFetchStub({ detailDenied: true }))} />);
    await screen.findByRole("table", { name: "Conceptual Objects" });
    await user.click(screen.getByRole("link", { name: "Open Conceptual Object 41" }));
    expect(await screen.findByRole("alert")).toHaveTextContent(
      "You do not have permission to view this Conceptual Object.",
    );
  });

  it("keeps Conceptual execution lock-gated and explicitly creates then starts a run", async () => {
    const unlocked = render(
      <WorkbenchApp router={conceptualRouter(conceptualFetchStub({ hasLock: false }))} />,
    );
    await screen.findByRole("table", { name: "Conceptual Objects" });
    expect(screen.getByRole("button", { name: "Run Conceptual" })).toBeDisabled();
    expect(screen.getByText("Tenant Lock required to run")).toBeVisible();
    unlocked.unmount();

    const fetcher = conceptualFetchStub();
    const user = userEvent.setup();
    render(<WorkbenchApp router={conceptualRouter(fetcher)} />);
    await screen.findByRole("table", { name: "Conceptual Objects" });
    expect(screen.getByText("Tenant Lock held")).toBeVisible();
    await user.click(screen.getByRole("button", { name: "Run Conceptual" }));
    expect(await screen.findByRole("heading", { name: "Configure Conceptual run" })).toBeVisible();
    const submit = screen.getByRole("button", { name: "Create and run Conceptual" });
    await waitFor(() => expect(submit).toBeEnabled());
    await user.click(submit);

    expect(fetcher).toHaveBeenCalledWith(
      "/api/v1/tenants/7/models/18/runs",
      expect.objectContaining({
        method: "POST",
        body: expect.stringContaining('"model_workflow":"conceptual"'),
      }),
    );
    expect(fetcher).toHaveBeenCalledWith(
      "/api/v1/tenants/7/models/18/conceptual/runs/1150/execute",
      expect.objectContaining({
        method: "POST",
        body: JSON.stringify({ execution_mode: "tool_assisted", expected_model_revision: 18 }),
      }),
    );
  });

  it("retries a conflicted Conceptual start without creating another run", async () => {
    const fetcher = conceptualFetchStub({ executeConflictOnce: true });
    const user = userEvent.setup();
    render(<WorkbenchApp router={conceptualRouter(fetcher)} />);
    await screen.findByRole("table", { name: "Conceptual Objects" });

    await user.click(screen.getByRole("button", { name: "Run Conceptual" }));
    const createAndRun = await screen.findByRole("button", { name: "Create and run Conceptual" });
    await waitFor(() => expect(createAndRun).toBeEnabled());
    await user.click(createAndRun);

    expect(await screen.findByRole("alert")).toHaveTextContent(
      "Another Workflow Run is already active for this Tenant. "
      + "This run remains queued; retry after the active run finishes.",
    );
    const retry = screen.getByRole("button", { name: "Retry start" });
    await user.click(retry);

    await waitFor(() => {
      expect(fetcher.mock.calls.filter(([input, init]) => (
        String(input) === "/api/v1/tenants/7/models/18/runs" && init?.method === "POST"
      ))).toHaveLength(1);
      expect(fetcher.mock.calls.filter(([input, init]) => (
        String(input) === "/api/v1/tenants/7/models/18/conceptual/runs/1150/execute"
        && init?.method === "POST"
      ))).toHaveLength(2);
    });
  });

  it("cannot dismiss Conceptual configuration while create/start is pending", async () => {
    let releaseExecute: (() => void) | undefined;
    const executeGate = new Promise<void>((resolve) => {
      releaseExecute = resolve;
    });
    const fetcher = conceptualFetchStub({ executeGate });
    const user = userEvent.setup();
    render(<WorkbenchApp router={conceptualRouter(fetcher)} />);
    await screen.findByRole("table", { name: "Conceptual Objects" });

    await user.click(screen.getByRole("button", { name: "Run Conceptual" }));
    const submit = await screen.findByRole("button", { name: "Create and run Conceptual" });
    await waitFor(() => expect(submit).toBeEnabled());
    await user.click(submit);

    await waitFor(() => expect(screen.getByRole("button", {
      name: "Close Configure Conceptual run",
    })).toBeDisabled());
    expect(screen.getByRole("button", { name: "Cancel" })).toBeDisabled();
    await user.keyboard("{Escape}");
    expect(screen.getByRole("dialog", { name: "Configure Conceptual run" })).toBeVisible();

    releaseExecute?.();
    await waitFor(() => expect(screen.queryByRole(
      "dialog",
      { name: "Configure Conceptual run" },
    )).not.toBeInTheDocument());
  });
});

function conceptualRouter(fetcher: ReturnType<typeof conceptualFetchStub>) {
  return createWorkbenchRouter({
    api: createApiClient(fetcher),
    history: createMemoryHistory({
      initialEntries: ["/tenants/7/models/18/conceptual"],
    }),
  });
}

function conceptualFetchStub(options: {
  empty?: boolean;
  error?: boolean;
  modelRevision?: number;
  hasLock?: boolean;
  denied?: boolean;
  detailDenied?: boolean;
  hasNextPage?: boolean;
  executeConflictOnce?: boolean;
  executeGate?: Promise<void>;
} = {}) {
  let executeAttempts = 0;
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
    if (url.startsWith("/api/v1/tenants/7/models/18/conceptual/objects?")) {
      if (options.denied) return jsonResponse({ error: { code: "forbidden" } }, 403);
      if (options.error) return jsonResponse({ error: { code: "unavailable" } }, 503);
      const isNextPage = url.includes("cursor=objects-next");
      return jsonResponse({
        model_id: 18,
        model_revision: options.modelRevision ?? 18,
        items: options.empty ? [] : [{
          ...conceptualObjectPayload,
          ...(isNextPage ? { conceptual_object_id: 42, conceptual_object_name: "order" } : {}),
        }],
        next_cursor: options.hasNextPage && !isNextPage ? "objects-next" : null,
      });
    }
    if (url === "/api/v1/tenants/7/models/18/conceptual/objects/41") {
      if (options.detailDenied) return jsonResponse({ error: { code: "forbidden" } }, 403);
      return jsonResponse(conceptualObjectDetailPayload);
    }
    if (url.startsWith("/api/v1/tenants/7/models/18/conceptual/relationships?")) {
      const isNextPage = url.includes("cursor=relationships-next");
      return jsonResponse({
        model_id: 18,
        model_revision: options.modelRevision ?? 18,
        items: options.empty ? [] : [{
          ...conceptualRelationshipPayload,
          ...(isNextPage
            ? { conceptual_relationship_id: 52, conceptual_relationship_name: "order ships" }
            : {}),
        }],
        next_cursor: options.hasNextPage && !isNextPage ? "relationships-next" : null,
      });
    }
    if (url === "/api/v1/tenants/7/models/18/conceptual/relationships/51") {
      return jsonResponse(conceptualRelationshipDetailPayload);
    }
    if (url === "/api/v1/tenants/7/models/18/scope?zone=bronze&page_size=200") {
      return jsonResponse({
        model_id: 18,
        model_revision: 18,
        items: [conceptualScopeObjectPayload],
        next_cursor: null,
      });
    }
    if (url === "/api/v1/config/agent-capabilities") {
      return jsonResponse(agentCapabilitiesPayload);
    }
    if (url === "/api/v1/tenants/7/models/18/runs?workflow=conceptual&page_size=5") {
      return jsonResponse({ items: [], next_cursor: null });
    }
    if (url === "/api/v1/tenants/7/models/18/runs") {
      return jsonResponse({
        created: true,
        workflow_run_id: 1150,
        workflow_run_state: "queued",
        correlation_id: "conceptual-run-1150",
        prompt_snapshot_count: 5,
        created_at: "2026-08-24T16:00:00Z",
      }, 201);
    }
    if (url === "/api/v1/tenants/7/models/18/conceptual/runs/1150/execute") {
      executeAttempts += 1;
      await options.executeGate;
      if (options.executeConflictOnce && executeAttempts === 1) {
        return jsonResponse({ error: { code: "tenant_workflow_conflict" } }, 409);
      }
      return jsonResponse({
        changed: true,
        workflow_run_id: 1150,
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

const conceptualObjectPayload = {
  conceptual_object_id: 41,
  workflow_run_id: null,
  conceptual_object_name: "customer",
  conceptual_object_type: "business_entity",
  conceptual_object_confidence: "high",
  conceptual_object_status: "needs_review",
  conceptual_object_is_locked: true,
  updated_at: "2026-08-24T14:30:00Z",
};

const physicalSupport = {
  conceptual_support_id: 61,
  workflow_run_id: null,
  support_source_type: "object",
  support_role: "primary",
  support_reason: "Customer table expresses the identity.",
  support_reason_detail: "Natural customer grain and stable identifier.",
  support_confidence: "high",
  support_status: "active",
  support_is_locked: true,
  created_at: "2026-08-24T14:00:00Z",
  updated_at: "2026-08-24T14:30:00Z",
  source_object: {
    object_id: 501,
    tenant_code: "GRDM",
    system_code: "CRM",
    connection_code: "crm-prod",
    object_schema: "bronze",
    object_name: "customer_raw",
  },
};

const assertionSupport = {
  conceptual_support_id: 62,
  workflow_run_id: 1048,
  support_source_type: "assertion",
  support_role: "governance",
  support_reason: "A reviewed assertion confirms identity semantics.",
  support_reason_detail: null,
  support_confidence: "high",
  support_status: "needs_review",
  support_is_locked: false,
  created_at: "2026-08-24T14:05:00Z",
  updated_at: "2026-08-24T14:35:00Z",
  assertion_record: {
    modeling_assertion_record_id: 91,
    modeling_assertion_record_key: "customer.identity.stable",
    modeling_assertion_document_name: "Customer governance rules",
    modeling_assertion_record_type: "identity_rule",
    modeling_assertion_text: "Customer identity remains stable across CRM and ERP.",
    modeling_assertion_confidence: "high",
    modeling_assertion_record_status: "needs_review",
  },
};

const conceptualObjectDetailPayload = {
  ...conceptualObjectPayload,
  conceptual_object_definition: "One recognized customer identity.",
  conceptual_object_grain: "One row per recognized customer.",
  conceptual_object_aliases: ["consumer", "account holder"],
  created_at: "2026-08-24T14:00:00Z",
  supports: [physicalSupport, assertionSupport],
};

const conceptualRelationshipPayload = {
  conceptual_relationship_id: 51,
  workflow_run_id: 1048,
  from_conceptual_object_id: 41,
  from_conceptual_object_name: "customer",
  to_conceptual_object_id: 42,
  to_conceptual_object_name: "order",
  conceptual_relationship_name: "customer places order",
  conceptual_relationship_type: "ownership",
  conceptual_relationship_cardinality: "one_to_many",
  conceptual_relationship_confidence: "high",
  conceptual_relationship_status: "active",
  conceptual_relationship_is_locked: false,
  updated_at: "2026-08-24T14:40:00Z",
};

const conceptualRelationshipDetailPayload = {
  ...conceptualRelationshipPayload,
  conceptual_relationship_definition: "A customer can place many orders.",
  conceptual_relationship_basis: "Customer activity establishes order ownership.",
  conceptual_relationship_cardinality_basis: "One customer identifier appears on many orders.",
  created_at: "2026-08-24T14:10:00Z",
  supports: [physicalSupport],
};

const conceptualScopeObjectPayload = {
  model_scope_id: 201,
  object_id: 501,
  connection_id: 301,
  system_id: 401,
  system_code: "CRM",
  system_name: "Customer Relationship Management",
  source_tenant_id: 9,
  source_tenant_code: "GRDM",
  source_tenant_name: "Global Reference Data",
  object_schema: "bronze",
  object_name: "customer_raw",
  zone_code: "bronze",
  batch_attribute_name: "batch_id",
  attribute_count: 14,
  is_bronze_source_eligible: true,
  is_dimensional_source_eligible: false,
  is_logical_mapping_target_eligible: false,
  is_dimensional_mapping_target_eligible: false,
  created_at: "2026-08-24T14:00:00Z",
  updated_at: "2026-08-24T14:00:00Z",
};

const agentCapabilitiesPayload = {
  schema_version: "3.0",
  sdks: [{ code: "openai_agents", name: "OpenAI Agents", provider_codes: ["databricks"] }],
  providers: [{ code: "databricks", name: "Databricks Model Serving" }],
  models: [{
    code: "databricks-primary",
    name: "GPT-5.6",
    provider_code: "databricks",
    deployment_name: "databricks-primary",
    execution_profiles: ["one_shot", "tool_assisted", "detailed_coverage"].map((execution_mode) => ({
      sdk_code: "openai_agents",
      execution_mode,
      reasoning_effort_codes: ["medium"],
    })),
  }],
  reasoning_efforts: [{ code: "medium", name: "Medium" }],
  max_turns: { minimum: 1, default: 8, maximum: 50 },
  validation_retries: { minimum: 0, default: 1, maximum: 5 },
};
