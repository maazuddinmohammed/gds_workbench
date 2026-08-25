import { render, screen, within } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { createMemoryHistory } from "@tanstack/react-router";
import { describe, expect, it, vi } from "vitest";

import { createApiClient } from "../../api";
import { WorkbenchApp, createWorkbenchRouter } from "../../app";

describe("Model Assertions", () => {
  it("filters Assertion Documents and opens normalized full-page details", async () => {
    const fetcher = assertionsFetchStub();
    const user = userEvent.setup();
    render(<WorkbenchApp router={assertionsRouter(fetcher)} />);

    const ledger = await screen.findByRole("table", { name: "Assertion Documents" });
    expect(within(ledger).getByText("Customer governance rules")).toBeVisible();

    await user.type(screen.getByLabelText("Document name prefix"), " Customer ");
    await user.type(screen.getByLabelText("Source System code"), " CRM ");
    await user.selectOptions(screen.getByLabelText("Document activity"), "true");
    await user.click(screen.getByRole("button", { name: "Apply Document filters" }));
    await screen.findByRole("table", { name: "Assertion Documents" });

    expect(fetcher).toHaveBeenCalledWith(
      "/api/v1/tenants/7/models/18/assertions/documents?source_system_code=crm&active=true&name_prefix=customer&page_size=200",
      expect.objectContaining({ credentials: "same-origin" }),
    );

    await user.click(screen.getByRole("link", { name: "Open Assertion Document 31" }));
    expect(await screen.findByRole("heading", { name: "Customer governance rules" })).toBeVisible();
    expect(screen.getByText("Quarterly customer-domain review rules.")).toBeVisible();
    expect(screen.getByText("data_governance")).toBeVisible();
    expect(screen.getByText("No workflow provenance")).toBeVisible();
  });

  it("filters Assertion Records and renders bounded arrays as structured sections", async () => {
    const fetcher = assertionsFetchStub();
    const user = userEvent.setup();
    render(<WorkbenchApp router={assertionsRouter(fetcher)} />);
    await screen.findByRole("table", { name: "Assertion Documents" });

    await user.click(screen.getByRole("button", { name: "Records" }));
    expect(await screen.findByRole("table", { name: "Assertion Records" })).toBeVisible();
    await user.type(screen.getByLabelText("Record key prefix"), " Customer. ");
    await user.selectOptions(screen.getByLabelText("Applicable layer"), "logical");
    await user.selectOptions(screen.getByLabelText("Record status"), "needs_review");
    await user.selectOptions(screen.getByLabelText("Record lock"), "false");
    await user.click(screen.getByRole("button", { name: "Apply Record filters" }));
    await screen.findByRole("table", { name: "Assertion Records" });

    expect(fetcher).toHaveBeenCalledWith(
      "/api/v1/tenants/7/models/18/assertions/records?status=needs_review&locked=false&applicable_layer=logical&key_prefix=customer.&page_size=200",
      expect.objectContaining({ credentials: "same-origin" }),
    );

    await user.click(screen.getByRole("link", { name: "Open Assertion Record 91" }));
    expect(await screen.findByRole("heading", { name: "customer.identity.stable" })).toBeVisible();
    expect(screen.getByText("customer_raw")).toBeVisible();
    expect(screen.getByText("invoice_raw")).toBeVisible();
    expect(screen.getByText("Workflow run 1048")).toBeVisible();
  });

  it("keeps refresh, empty, error, and revision states explicit without write controls", async () => {
    const user = userEvent.setup();
    const emptyFetcher = assertionsFetchStub({ empty: true });
    const { unmount } = render(<WorkbenchApp router={assertionsRouter(emptyFetcher)} />);
    expect(await screen.findByText("No Assertion Documents match these filters.")).toBeVisible();
    expect(screen.queryByRole("button", { name: /upload|import|create/i })).not.toBeInTheDocument();
    await user.click(screen.getByRole("button", { name: "Refresh" }));
    expect(emptyFetcher.mock.calls.filter(([input]) => String(input).includes("/assertions/documents")))
      .toHaveLength(2);
    unmount();

    const mismatchRender = render(
      <WorkbenchApp router={assertionsRouter(assertionsFetchStub({ modelRevision: 19 }))} />,
    );
    expect(await screen.findByRole("alert")).toHaveTextContent(
      "The Model changed while Assertion Documents were loading.",
    );
    mismatchRender.unmount();

    render(<WorkbenchApp router={assertionsRouter(assertionsFetchStub({ error: true }))} />);
    expect(await screen.findByRole("alert")).toHaveTextContent(
      "Assertion Documents could not be loaded.",
    );
  });
});

function assertionsRouter(fetcher: ReturnType<typeof assertionsFetchStub>) {
  return createWorkbenchRouter({
    api: createApiClient(fetcher),
    history: createMemoryHistory({
      initialEntries: ["/tenants/7/models/18/assertions"],
    }),
  });
}

function assertionsFetchStub(options: {
  empty?: boolean;
  error?: boolean;
  modelRevision?: number;
} = {}) {
  return vi.fn<typeof fetch>(async (input) => {
    const url = String(input);
    if (url === "/api/v1/tenants/7/home") return jsonResponse(tenantHomePayload);
    if (url === "/api/v1/tenants/7/models/18") return jsonResponse(modelPayload);
    if (url.startsWith("/api/v1/tenants/7/models/18/assertions/documents?")) {
      if (options.error) return jsonResponse({ error: { code: "unavailable" } }, 503);
      return jsonResponse({
        model_id: 18,
        model_revision: options.modelRevision ?? 18,
        items: options.empty ? [] : [assertionDocumentPayload],
        next_cursor: null,
      });
    }
    if (url === "/api/v1/tenants/7/models/18/assertions/documents/31") {
      return jsonResponse(assertionDocumentDetailPayload);
    }
    if (url.startsWith("/api/v1/tenants/7/models/18/assertions/records?")) {
      return jsonResponse({
        model_id: 18,
        model_revision: options.modelRevision ?? 18,
        items: options.empty ? [] : [assertionRecordPayload],
        next_cursor: null,
      });
    }
    if (url === "/api/v1/tenants/7/models/18/assertions/records/91") {
      return jsonResponse(assertionRecordDetailPayload);
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

const sourceTenant = { tenant_id: 3, tenant_code: "GRDM", tenant_name: "Global Reference Data" };
const sourceSystem = { system_id: 11, system_code: "CRM", system_name: "Customer Relationship Management" };

const assertionDocumentPayload = {
  modeling_assertion_document_id: 31,
  workflow_run_id: null,
  modeling_assertion_document_name: "Customer governance rules",
  modeling_assertion_document_type: "policy",
  source_tenant: sourceTenant,
  source_system: sourceSystem,
  is_active: true,
  record_count: 12,
  active_record_count: 10,
  needs_review_record_count: 2,
  locked_record_count: 4,
  updated_at: "2026-08-24T14:20:00Z",
};

const assertionDocumentDetailPayload = {
  ...assertionDocumentPayload,
  modeling_assertion_file_pattern: "customer-rules-*.xlsx",
  modeling_assertion_document_description: "Quarterly customer-domain review rules.",
  modeling_assertion_document_metadata: {
    owners: ["data_governance", "crm_architecture"],
    review: { cadence: "quarterly", required: true },
  },
  agent_run_id: null,
  created_at: "2026-08-24T14:00:00Z",
};

const assertionDocumentReference = {
  modeling_assertion_document_id: 31,
  modeling_assertion_document_name: "Customer governance rules",
  modeling_assertion_document_type: "policy",
  source_tenant: sourceTenant,
  source_system: sourceSystem,
  is_active: true,
};

const assertionRecordPayload = {
  modeling_assertion_record_id: 91,
  workflow_run_id: 1048,
  document: assertionDocumentReference,
  modeling_assertion_record_key: "customer.identity.stable",
  modeling_assertion_record_type: "identity_rule",
  modeling_assertion_applicable_layers: ["analysis", "logical"],
  modeling_assertion_confidence: "high",
  modeling_assertion_record_status: "needs_review",
  modeling_assertion_record_is_locked: false,
  updated_at: "2026-08-24T14:30:00Z",
};

const assertionRecordDetailPayload = {
  ...assertionRecordPayload,
  modeling_assertion_text: "Customer identity remains stable across CRM and ERP.",
  modeling_assertion_details: {
    scope: { objects: ["customer_raw", "invoice_raw"] },
    rules: [
      { field: "customer_id", expectation: "stable" },
      { field: "source_system_code", expectation: "present" },
    ],
  },
  modeling_assertion_source_location: {
    worksheet: "Customer Rules",
    row_number: 12,
  },
  agent_run_id: null,
  created_at: "2026-08-24T14:10:00Z",
};
