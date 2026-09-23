import { render, screen, within, waitFor } from "@testing-library/react";
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
    expect(await screen.findByRole("table", { name: "Assertion Records" })).toBeVisible();
    expect(screen.queryByLabelText("Applicable layer")).not.toBeInTheDocument();
    expect(screen.getByText("data_governance")).not.toBeVisible();
    await user.click(screen.getByRole("heading", { name: "Document details" }));
    expect(screen.getByText("data_governance")).toBeVisible();
    expect(screen.queryByRole("heading", { name: "Provenance" })).not.toBeInTheDocument();
  });

  it("filters Assertion Records and renders bounded arrays as structured sections", async () => {
    const fetcher = assertionsFetchStub();
    const user = userEvent.setup();
    render(<WorkbenchApp router={assertionsRouter(fetcher)} />);
    await screen.findByRole("table", { name: "Assertion Documents" });

    await user.click(screen.getByRole("link", { name: "Open Assertion Document 31" }));
    expect(await screen.findByRole("table", { name: "Assertion Records" })).toBeVisible();
    await user.type(screen.getByLabelText("Record key prefix"), " Customer. ");
    await user.selectOptions(screen.getByLabelText("Record status"), "inactive");
    await user.selectOptions(screen.getByLabelText("Record lock"), "false");
    await user.click(screen.getByRole("button", { name: "Apply Record filters" }));
    await screen.findByRole("table", { name: "Assertion Records" });

    expect(fetcher).toHaveBeenCalledWith(
      "/api/v1/tenants/7/models/18/assertions/records?document_id=31&status=inactive&locked=false&key_prefix=customer.&page_size=200",
      expect.objectContaining({ credentials: "same-origin" }),
    );

    await user.click(screen.getByRole("link", { name: "Open Assertion Record 91" }));
    expect(await screen.findByRole("heading", { name: "customer.identity.stable" })).toBeVisible();
    await user.click(screen.getByRole("heading", { name: "Normalized details" }));
    expect(screen.getByText("customer_raw")).toBeVisible();
    expect(screen.getByText("invoice_raw")).toBeVisible();
    expect(screen.queryByText("Workflow run 1048")).not.toBeInTheDocument();
    await user.click(screen.getByRole("link", { name: "← Back to Customer governance rules" }));
    expect(await screen.findByRole("table", { name: "Assertion Records" })).toBeVisible();
    await user.click(screen.getByRole("button", { name: "Add Assertion" }));
    const dialog = screen.getByRole("dialog", { name: "Add Assertion" });
    expect(within(dialog).getByLabelText("Document name")).toHaveValue("Customer governance rules");
    expect(within(dialog).getByLabelText("Document scope")).toBeDisabled();
    expect(within(dialog).queryByText("Applies to")).not.toBeInTheDocument();
  });

  it("keeps refresh, empty, error, and revision states explicit with lock-gated write controls", async () => {
    const user = userEvent.setup();
    const emptyFetcher = assertionsFetchStub({ empty: true });
    const { unmount } = render(<WorkbenchApp router={assertionsRouter(emptyFetcher)} />);
    expect(await screen.findByText("No Assertion Documents match these filters.")).toBeVisible();
    expect(screen.getByRole("button", { name: "Add Assertion" })).toBeEnabled();
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
  it("saves a scoped reporting requirement and retries uncertain saves without changing the request", async () => {
    const fetcher = assertionsFetchStub({ retrySave: true });
    const user = userEvent.setup();
    render(<WorkbenchApp router={assertionsRouter(fetcher)} />);
    await user.click(await screen.findByRole("button", { name: "Add Assertion" }));
    const dialog = screen.getByRole("dialog", { name: "Add Assertion" });
    expect(within(dialog).getByRole("button", { name: "Close Assertion editor" })).toHaveFocus();
    await waitFor(() => expect(within(dialog).getByLabelText("Document name")).toBeEnabled());
    await user.type(within(dialog).getByLabelText("Document name"), "Finance notes");
    await user.selectOptions(within(dialog).getByLabelText("Document type (optional)"), "custom");
    await user.type(within(dialog).getByLabelText("Custom document type"), "Business context");
    await user.type(within(dialog).getByLabelText("Assertion key"), "monthly_sales");
    await user.type(within(dialog).getByLabelText("Assertion"), "Report monthly net sales by segment.");
    await within(dialog).findByRole("option", { name: "CRM" });
    await user.selectOptions(within(dialog).getByLabelText("Document scope"), "CRM");
    await user.type(within(dialog).getByLabelText("Reference (optional)"), "Finance section 2");
    await user.type(within(dialog).getByLabelText("Additional context (optional)"), "Sales less refunds, grouped by month and segment.");
    await user.click(within(dialog).getByRole("button", { name: "Save Assertion" }));
    await within(dialog).findByRole("button", { name: "Retry save" });
    expect(within(dialog).getByLabelText("Assertion")).toHaveValue("Report monthly net sales by segment.");
    expect(within(dialog).getByLabelText("Assertion")).toBeDisabled();
    await user.click(within(dialog).getByRole("button", { name: "Retry save" }));
    await waitFor(() => expect(screen.queryByRole("dialog")).not.toBeInTheDocument());
    expect(await screen.findByRole("table", { name: "Assertion Documents" })).toBeVisible();
    const saves = fetcher.mock.calls.filter(([input]) => String(input).endsWith("/change-sets/assertions"));
    expect(saves).toHaveLength(2);
    expect(saves[0]?.[1]).toEqual(saves[1]?.[1]);
    expect(JSON.parse(String(saves[0]?.[1]?.body))).toEqual({
      expected_model_revision: 18, record_key: "monthly_sales", record_type: "business_rule",
      document_name: "Finance notes", document_type: "Business context",
      text: "Report monthly net sales by segment.", details: { notes: "Sales less refunds, grouped by month and segment." },
      source_system_code: "CRM", source_reference: "Finance section 2",
    });
  });

  it("requires the Tenant Lock for manual authoring", async () => {
    render(<WorkbenchApp router={assertionsRouter(assertionsFetchStub({ hasLock: false }))} />);
    expect(await screen.findByRole("button", { name: "Add Assertion" })).toBeDisabled();
  });

  it("adds a new key to an existing document with its original type and scope", async () => {
    const fetcher = assertionsFetchStub();
    const user = userEvent.setup();
    render(<WorkbenchApp router={assertionsRouter(fetcher)} />);
    await user.click(await screen.findByRole("button", { name: "Add Assertion" }));
    const dialog = screen.getByRole("dialog");
    await user.selectOptions(within(dialog).getByLabelText("Document"), "existing");
    await within(dialog).findByRole("option", { name: "Customer governance rules" });
    await user.selectOptions(within(dialog).getByLabelText("Existing document"), "31");
    expect(within(dialog).getByLabelText("Document type")).toHaveValue("policy");
    expect(within(dialog).getByLabelText("Document scope")).toHaveValue("CRM");
    expect(within(dialog).getByLabelText("Document scope")).toBeDisabled();
    await user.type(within(dialog).getByLabelText("Assertion key"), "customer.retention");
    await user.selectOptions(within(dialog).getByLabelText("Assertion type"), "kpi_definition");
    await user.type(within(dialog).getByLabelText("Assertion"), "Retained customers placed orders in both comparison periods.");
    await user.click(within(dialog).getByRole("button", { name: "Save Assertion" }));
    await waitFor(() => expect(screen.queryByRole("dialog")).not.toBeInTheDocument());
    const save = fetcher.mock.calls.find(([input]) => String(input).endsWith("/change-sets/assertions"));
    expect(JSON.parse(String(save?.[1]?.body))).toMatchObject({
      document_name: "Customer governance rules", document_type: "policy", source_system_code: "CRM",
      record_key: "customer.retention", record_type: "kpi_definition",
    });
    expect(JSON.parse(String(save?.[1]?.body))).not.toHaveProperty("record_id");
  });

  it("loads an existing key for editing and preserves custom types and its record identity", async () => {
    const fetcher = assertionsFetchStub({ manual: true });
    const user = userEvent.setup();
    render(<WorkbenchApp router={assertionsRouter(fetcher)} />);
    await user.click(await screen.findByRole("link", { name: "Open Assertion Document 31" }));
    await user.click(await screen.findByRole("button", { name: "Add Assertion" }));
    const dialog = screen.getByRole("dialog");
    await user.selectOptions(within(dialog).getByLabelText("Assertion action"), "edit");
    await within(dialog).findByRole("option", { name: "customer.identity.stable" });
    await user.selectOptions(within(dialog).getByLabelText("Existing assertion key"), "91");
    await waitFor(() => expect(within(dialog).getByLabelText("Assertion")).toHaveValue(assertionRecordDetailPayload.modeling_assertion_text));
    expect(within(dialog).getByLabelText("Assertion key")).toHaveAttribute("readonly");
    expect(within(dialog).getByLabelText("Assertion type")).toHaveValue("custom");
    expect(within(dialog).getByLabelText("Custom assertion type")).toHaveValue("retention_rule");
    expect(within(dialog).getByLabelText("Additional context (optional)")).toHaveValue("Previous notes");
    await user.clear(within(dialog).getByLabelText("Assertion"));
    await user.type(within(dialog).getByLabelText("Assertion"), "Use a durable customer identifier across source systems.");
    await user.click(within(dialog).getByRole("button", { name: "Save Assertion" }));
    await waitFor(() => expect(screen.queryByRole("dialog")).not.toBeInTheDocument());
    const save = fetcher.mock.calls.find(([input]) => String(input).endsWith("/change-sets/assertions"));
    expect(JSON.parse(String(save?.[1]?.body))).toMatchObject({
      record_id: 91, record_key: "customer.identity.stable", record_type: "retention_rule",
      text: "Use a durable customer identifier across source systems.", details: { notes: "Previous notes" },
      document_name: "Customer governance rules", document_type: "policy", source_system_code: "CRM",
    });
  });

  it("protects imported assertions and clears loaded content when switching back to a new key", async () => {
    const fetcher = assertionsFetchStub();
    const user = userEvent.setup();
    render(<WorkbenchApp router={assertionsRouter(fetcher)} />);
    await user.click(await screen.findByRole("link", { name: "Open Assertion Document 31" }));
    await user.click(await screen.findByRole("button", { name: "Add Assertion" }));
    const dialog = screen.getByRole("dialog");
    await user.selectOptions(within(dialog).getByLabelText("Assertion action"), "edit");
    await within(dialog).findByRole("option", { name: "customer.identity.stable" });
    await user.selectOptions(within(dialog).getByLabelText("Existing assertion key"), "91");
    expect(await within(dialog).findByRole("alert")).toHaveTextContent("This assertion was imported.");
    expect(within(dialog).getByRole("button", { name: "Save Assertion" })).toBeDisabled();
    await user.selectOptions(within(dialog).getByLabelText("Assertion action"), "add");
    expect(within(dialog).getByLabelText("Assertion key")).toHaveValue("");
    expect(within(dialog).getByLabelText("Assertion")).toHaveValue("");
    expect(within(dialog).getByLabelText("Assertion type")).toHaveValue("business_rule");
    expect(within(dialog).getByRole("button", { name: "Save Assertion" })).toBeEnabled();
  });

  it("disables locked keys in the existing assertion picker", async () => {
    const user = userEvent.setup();
    render(<WorkbenchApp router={assertionsRouter(assertionsFetchStub({ locked: true }))} />);
    await user.click(await screen.findByRole("link", { name: "Open Assertion Document 31" }));
    await user.click(await screen.findByRole("button", { name: "Add Assertion" }));
    const dialog = screen.getByRole("dialog");
    await user.selectOptions(within(dialog).getByLabelText("Assertion action"), "edit");
    expect(await within(dialog).findByRole("option", { name: "customer.identity.stable (locked)" })).toBeDisabled();
    expect(within(dialog).getByRole("button", { name: "Save Assertion" })).toBeDisabled();
  });

  it("directs duplicate document names to the existing document picker", async () => {
    const user = userEvent.setup();
    render(<WorkbenchApp router={assertionsRouter(assertionsFetchStub())} />);
    await user.click(await screen.findByRole("button", { name: "Add Assertion" }));
    const dialog = screen.getByRole("dialog");
    await user.type(within(dialog).getByLabelText("Document name"), " customer governance rules ");
    expect(await within(dialog).findByRole("alert")).toHaveTextContent("This document already exists.");
    expect(within(dialog).getByRole("button", { name: "Save Assertion" })).toBeDisabled();
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
  retrySave?: boolean;
  hasLock?: boolean;
  manual?: boolean;
  locked?: boolean;
} = {}) {
  let saves = 0;
  return vi.fn<typeof fetch>(async (input) => {
    const url = String(input);
    if (url === "/api/v1/tenants/7/home") return jsonResponse({ ...tenantHomePayload, lock: { ...tenantHomePayload.lock, owned_by_current_principal: options.hasLock ?? true } });
    if (url.startsWith("/api/v1/tenants/7/metadata/datasets/system/rows?")) return jsonResponse({ items: [{ system_code: "CRM", is_active: true }], next_cursor: null });
    if (url.endsWith("/change-sets/assertions")) {
      if (options.retrySave && saves++ === 0) return jsonResponse({ error: { code: "unavailable", message: "Retry the save." } }, 503);
      return jsonResponse({ model_id: 18, model_revision: 19, model_change_set_id: "saved", action_count: 2 });
    }
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
        items: options.empty ? [] : [{ ...assertionRecordPayload, modeling_assertion_record_is_locked: options.locked ?? false }],
        next_cursor: null,
      });
    }
    if (url === "/api/v1/tenants/7/models/18/assertions/records/91") {
      return jsonResponse({ ...assertionRecordDetailPayload,
        modeling_assertion_record_is_locked: options.locked ?? false,
        ...(options.manual ? {
          modeling_assertion_record_type: "retention_rule",
          modeling_assertion_source_location: { entry_method: "manual", reference: "Customer notes" },
          modeling_assertion_details: { notes: "Previous notes" },
        } : {}),
      });
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
  model_input_scope_object_count: 25,
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
  modeling_assertion_record_status: "active",
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
