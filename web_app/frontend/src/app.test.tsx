import { render, screen, waitFor, within } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { createMemoryHistory } from "@tanstack/react-router";
import { describe, expect, it, vi } from "vitest";

import { createApiClient } from "./api";
import { WorkbenchApp, createWorkbenchRouter } from "./app";

describe("tenant entry", () => {
  it("selects the last Tenant and enters its governed workspace", async () => {
    const fetcher = tenantFetchStub();
    const router = createWorkbenchRouter({
      api: createApiClient(fetcher),
      history: createMemoryHistory({ initialEntries: ["/"] }),
    });
    const user = userEvent.setup();

    render(<WorkbenchApp router={router} />);

    expect(await screen.findByRole("heading", { name: "Choose a Tenant" })).toBeVisible();
    expect(screen.getByText("Signed in as")).toBeVisible();
    const selected = screen.getByRole("button", { name: /Northwind Analytics/ });
    expect(selected).toHaveAttribute("aria-pressed", "true");

    await user.click(screen.getByRole("button", { name: /Enter Workbench/ }));

    expect(await screen.findByRole("heading", { name: "Tenant Lock" })).toBeVisible();
    expect(router.state.location.pathname).toBe("/tenants/7");
    expect(fetcher).toHaveBeenCalledWith(
      "/api/v1/tenants/7/select",
      expect.objectContaining({ method: "POST" }),
    );
  });

  it("filters Tenants without adding a generic dashboard", async () => {
    const router = createWorkbenchRouter({
      api: createApiClient(tenantFetchStub()),
      history: createMemoryHistory({ initialEntries: ["/"] }),
    });
    const user = userEvent.setup();
    render(<WorkbenchApp router={router} />);
    await screen.findByText("Northwind Analytics");

    await user.type(screen.getByRole("searchbox", { name: "Search Tenants" }), "global");

    expect(screen.queryByText("Northwind Analytics")).not.toBeInTheDocument();
    expect(screen.getAllByText("Global Reference Data")).not.toHaveLength(0);
    expect(screen.queryByText(/Your role, metadata/i)).not.toBeInTheDocument();
  });
});

describe("Tenant Home", () => {
  it("makes the governed lock the focus and presents registered Systems", async () => {
    const router = createWorkbenchRouter({
      api: createApiClient(tenantFetchStub()),
      history: createMemoryHistory({ initialEntries: ["/tenants/7"] }),
    });

    render(<WorkbenchApp router={router} />);

    const lock = await screen.findByRole("region", { name: "Tenant Lock" });
    expect(within(lock).getByText("Elena Morris")).toBeVisible();
    expect(within(lock).getByText("Locked by another Principal")).toBeVisible();
    expect(within(lock).queryByRole("button", { name: "Acquire Tenant Lock" })).not.toBeInTheDocument();

    const systems = screen.getByRole("table", { name: "Registered Systems" });
    expect(within(systems).getByText("Customer Relationship Management")).toBeVisible();
    expect(within(systems).getByText("63")).toBeVisible();
    expect(screen.queryByText("GDS Connection")).not.toBeInTheDocument();
    expect(screen.queryByText("Connected instance")).not.toBeInTheDocument();
  });

  it("returns to Tenant selection through the prominent Switch Tenant control", async () => {
    const router = createWorkbenchRouter({
      api: createApiClient(tenantFetchStub()),
      history: createMemoryHistory({ initialEntries: ["/tenants/7"] }),
    });
    const user = userEvent.setup();
    render(<WorkbenchApp router={router} />);
    await screen.findByRole("heading", { name: "Tenant Lock" });

    await user.click(screen.getByRole("link", { name: "Switch Tenant" }));

    expect(await screen.findByRole("heading", { name: "Choose a Tenant" })).toBeVisible();
  });

  it("connects explicit Tenant Lock acquisition to refreshed Home state", async () => {
    const baseFetcher = tenantFetchStub();
    let acquired = false;
    const fetcher = vi.fn<typeof fetch>(async (input, init) => {
      const url = String(input);
      if (url === "/api/v1/tenants/7/home") {
        return jsonResponse(acquired ? acquiredTenantHomePayload : unlockedTenantHomePayload);
      }
      if (url === "/api/v1/tenants/7/lock/acquire" && init?.method === "POST") {
        acquired = true;
        return jsonResponse({
          tenant_id: 7,
          action: "acquired",
          lock: acquiredTenantHomePayload.lock,
          previous_lock: null,
        });
      }
      return baseFetcher(input, init);
    });
    const router = createWorkbenchRouter({
      api: createApiClient(fetcher),
      history: createMemoryHistory({ initialEntries: ["/tenants/7"] }),
    });
    const user = userEvent.setup();
    render(<WorkbenchApp router={router} />);

    expect(await screen.findByText("Tenant is unlocked")).toBeVisible();
    expect(fetcher.mock.calls.some(([input]) => String(input).endsWith("/lock/acquire"))).toBe(false);

    const duration = screen.getByRole("spinbutton", { name: "Duration (minutes)" });
    await user.clear(duration);
    await user.type(duration, "75");
    await user.type(screen.getByRole("textbox", { name: "Purpose (optional)" }), "Scope review");
    await user.click(screen.getByRole("button", { name: "Acquire Tenant Lock" }));

    expect(await screen.findByText("Locked by you")).toBeVisible();
    const acquireCall = fetcher.mock.calls.find(([input]) => String(input).endsWith("/lock/acquire"));
    expect(acquireCall?.[1]?.body).toBe(JSON.stringify({
      duration_minutes: 75,
      purpose: "Scope review",
    }));
  });

  it("connects explicit Tenant Lock extension to refreshed Home state", async () => {
    const baseFetcher = tenantFetchStub();
    let renewed = false;
    const fetcher = vi.fn<typeof fetch>(async (input, init) => {
      const url = String(input);
      if (url === "/api/v1/tenants/7/home") {
        return jsonResponse(renewed ? renewedTenantHomePayload : acquiredTenantHomePayload);
      }
      if (url === "/api/v1/tenants/7/lock/renew" && init?.method === "POST") {
        renewed = true;
        return jsonResponse({
          tenant_id: 7,
          action: "renewed",
          lock: renewedTenantHomePayload.lock,
          previous_lock: null,
        });
      }
      return baseFetcher(input, init);
    });
    const router = createWorkbenchRouter({
      api: createApiClient(fetcher),
      history: createMemoryHistory({ initialEntries: ["/tenants/7"] }),
    });
    const user = userEvent.setup();
    render(<WorkbenchApp router={router} />);

    expect(await screen.findByText("Locked by you")).toBeVisible();
    expect(fetcher.mock.calls.some(([input]) => String(input).endsWith("/lock/renew"))).toBe(false);

    const duration = screen.getByRole("spinbutton", { name: "Extend duration (minutes)" });
    await user.clear(duration);
    await user.type(duration, "120");
    await user.click(screen.getByRole("button", { name: "Extend Tenant Lock" }));

    await waitFor(() => {
      expect(fetcher.mock.calls.filter(([input]) => String(input).endsWith("/home"))).toHaveLength(2);
    });
    const renewCall = fetcher.mock.calls.find(([input]) => String(input).endsWith("/lock/renew"));
    expect(renewCall?.[1]?.body).toBe(JSON.stringify({ duration_minutes: 120 }));
  });

  it("connects confirmed Tenant Lock release to refreshed Home state", async () => {
    const baseFetcher = tenantFetchStub();
    let released = false;
    const fetcher = vi.fn<typeof fetch>(async (input, init) => {
      const url = String(input);
      if (url === "/api/v1/tenants/7/home") {
        return jsonResponse(released ? unlockedTenantHomePayload : acquiredTenantHomePayload);
      }
      if (url === "/api/v1/tenants/7/lock/release" && init?.method === "POST") {
        released = true;
        return jsonResponse({
          tenant_id: 7,
          action: "released",
          lock: null,
          previous_lock: null,
        });
      }
      return baseFetcher(input, init);
    });
    const router = createWorkbenchRouter({
      api: createApiClient(fetcher),
      history: createMemoryHistory({ initialEntries: ["/tenants/7"] }),
    });
    const user = userEvent.setup();
    render(<WorkbenchApp router={router} />);

    expect(await screen.findByText("Locked by you")).toBeVisible();
    expect(fetcher.mock.calls.some(([input]) => String(input).endsWith("/lock/release"))).toBe(false);

    await user.click(screen.getByRole("button", { name: "Release Tenant Lock" }));
    expect(fetcher.mock.calls.some(([input]) => String(input).endsWith("/lock/release"))).toBe(false);
    await user.click(screen.getByRole("button", { name: "Confirm release" }));

    expect(await screen.findByText("Tenant is unlocked")).toBeVisible();
    await waitFor(() => {
      expect(fetcher.mock.calls.filter(([input]) => String(input).endsWith("/home"))).toHaveLength(2);
    });
    const releaseCall = fetcher.mock.calls.find(([input]) => String(input).endsWith("/lock/release"));
    expect(releaseCall?.[1]?.body).toBeUndefined();
  });

  it("connects reason-bound Tenant Lock override without acquiring afterward", async () => {
    const baseFetcher = tenantFetchStub();
    let overridden = false;
    const fetcher = vi.fn<typeof fetch>(async (input, init) => {
      const url = String(input);
      if (url === "/api/v1/tenants/7/home") {
        return jsonResponse(overridden ? unlockedTenantHomePayload : tenantHomePayload);
      }
      if (url === "/api/v1/tenants/7/lock/override" && init?.method === "POST") {
        overridden = true;
        return jsonResponse({
          tenant_id: 7,
          action: "overridden",
          lock: null,
          previous_lock: {
            owner_display_name: "Elena Morris",
            owned_by_current_principal: false,
            purpose: "Metadata review",
            acquired_at: "2026-08-24T14:12:00Z",
            expires_at: "2026-08-24T15:12:00Z",
          },
        });
      }
      return baseFetcher(input, init);
    });
    const router = createWorkbenchRouter({
      api: createApiClient(fetcher),
      history: createMemoryHistory({ initialEntries: ["/tenants/7"] }),
    });
    const user = userEvent.setup();
    render(<WorkbenchApp router={router} />);

    expect(await screen.findByText("Locked by another Principal")).toBeVisible();
    expect(screen.getByRole("note", { name: "Tenant Lock override warning" })).toHaveTextContent(
      "It does not acquire the Tenant Lock for you.",
    );

    await user.type(
      screen.getByRole("textbox", { name: "Override reason" }),
      "Incident 4821 access recovery",
    );
    await user.click(screen.getByRole("button", { name: "Revoke Tenant Lock" }));

    expect(await screen.findByText("Tenant is unlocked")).toBeVisible();
    expect(screen.getByRole("button", { name: "Acquire Tenant Lock" })).toBeVisible();
    expect(fetcher.mock.calls.some(([input]) => String(input).endsWith("/lock/acquire"))).toBe(false);
    const overrideCall = fetcher.mock.calls.find(([input]) => String(input).endsWith("/lock/override"));
    expect(overrideCall?.[1]?.body).toBe(JSON.stringify({
      reason: "Incident 4821 access recovery",
    }));
  });

  it("loads Tenant Lock history only when an authorized Home reader opens it", async () => {
    const baseFetcher = tenantFetchStub();
    const readerHome = {
      ...tenantHomePayload,
      lock_actions: {
        can_acquire: false,
        can_renew: false,
        can_release: false,
        can_override: false,
      },
    };
    const fetcher = vi.fn<typeof fetch>(async (input, init) => {
      const url = String(input);
      if (url === "/api/v1/tenants/7/home") return jsonResponse(readerHome);
      if (url === "/api/v1/tenants/7/lock/history?page_size=50") {
        return jsonResponse({
          tenant_id: 7,
          items: [
            {
              event_id: 51,
              event_type: "expired",
              owner_display_name: "Elena Morris",
              actor_display_name: null,
              reason: null,
              acquired_at: "2026-08-24T14:12:00Z",
              expires_at: "2026-08-24T15:12:00Z",
              created_at: "2026-08-24T15:12:01Z",
            },
          ],
          next_cursor: null,
        });
      }
      return baseFetcher(input, init);
    });
    const router = createWorkbenchRouter({
      api: createApiClient(fetcher),
      history: createMemoryHistory({ initialEntries: ["/tenants/7"] }),
    });
    const user = userEvent.setup();
    render(<WorkbenchApp router={router} />);

    expect(await screen.findByRole("button", { name: "View history" })).toBeVisible();
    expect(fetcher.mock.calls.some(([input]) => String(input).includes("/lock/history"))).toBe(false);

    await user.click(screen.getByRole("button", { name: "View history" }));

    const history = await screen.findByRole("region", { name: "Tenant Lock history" });
    expect(within(history).getByText("Expired")).toBeVisible();
    expect(within(history).getByText("System")).toBeVisible();
    expect(fetcher).toHaveBeenCalledWith(
      "/api/v1/tenants/7/lock/history?page_size=50",
      expect.objectContaining({ credentials: "same-origin" }),
    );
    expect(fetcher.mock.calls.some(([input]) => /lock\/(acquire|renew|release|override)$/.test(String(input)))).toBe(false);
  });
});

describe("Models ledger", () => {
  it("lists active Models and keeps Open links inside the active Tenant", async () => {
    const router = createWorkbenchRouter({
      api: createApiClient(tenantFetchStub()),
      history: createMemoryHistory({ initialEntries: ["/tenants/7/models"] }),
    });

    render(<WorkbenchApp router={router} />);

    const ledger = await screen.findByRole("table", { name: "Active Models" });
    expect(within(ledger).getByText("Customer 360")).toBeVisible();
    expect(within(ledger).getByText("25 Objects")).toBeVisible();
    expect(within(ledger).getByRole("link", { name: "Open Customer 360" })).toHaveAttribute(
      "href",
      "/tenants/7/models/18",
    );
  });

  it("switches between the active and archived server ledgers", async () => {
    const fetcher = tenantFetchStub();
    const router = createWorkbenchRouter({
      api: createApiClient(fetcher),
      history: createMemoryHistory({ initialEntries: ["/tenants/7/models"] }),
    });
    const user = userEvent.setup();
    render(<WorkbenchApp router={router} />);
    await screen.findByRole("table", { name: "Active Models" });

    await user.click(screen.getByRole("button", { name: "Archived" }));

    const archived = await screen.findByRole("table", { name: "Archived Models" });
    expect(within(archived).getByText("Legacy Customer View")).toBeVisible();
    expect(fetcher).toHaveBeenCalledWith(
      "/api/v1/tenants/7/models?status=archived&page_size=200",
      expect.objectContaining({ credentials: "same-origin" }),
    );
  });
});

describe("Model overview", () => {
  it("orients the selected Model and links Scope within the active Tenant", async () => {
    const router = createWorkbenchRouter({
      api: createApiClient(tenantFetchStub()),
      history: createMemoryHistory({ initialEntries: ["/tenants/7/models/18"] }),
    });
    render(<WorkbenchApp router={router} />);

    expect(await screen.findByRole("heading", { name: "Customer 360" })).toBeVisible();
    expect(screen.getByText("Cross-system customer domain")).toBeVisible();
    const ledger = screen.getByRole("table", { name: "Model workflow ledger" });
    expect(within(ledger).getByText("25 Objects")).toBeVisible();
    expect(within(ledger).getByText("18 results")).toBeVisible();
    expect(within(ledger).getByText("Results available")).toBeVisible();
    expect(within(ledger).getByText("Conceptual results unavailable")).toBeVisible();
    expect(within(ledger).queryByText(/blocked/i)).not.toBeInTheDocument();
    expect(within(ledger).getByRole("link", { name: "Review Scope" })).toHaveAttribute(
      "href",
      "/tenants/7/models/18/scope",
    );
    expect(within(ledger).getByRole("link", { name: "Review Profiling" })).toHaveAttribute(
      "href",
      "/tenants/7/models/18/profiling",
    );
  });
});

describe("Active Scope", () => {
  it("lists only the server-returned active Scope Objects", async () => {
    const fetcher = tenantFetchStub();
    const router = createWorkbenchRouter({
      api: createApiClient(fetcher),
      history: createMemoryHistory({ initialEntries: ["/tenants/7/models/18/scope"] }),
    });
    render(<WorkbenchApp router={router} />);

    const scope = await screen.findByRole("table", { name: "Active Scope" });
    expect(within(scope).getByText("customer_raw")).toBeVisible();
    expect(within(scope).getByText("GRDM")).toBeVisible();
    expect(within(scope).getByText("Bronze")).toBeVisible();
    expect(within(scope).getByRole("button", { name: "Show details for customer_raw" })).toBeVisible();
    expect(fetcher).toHaveBeenCalledWith(
      "/api/v1/tenants/7/models/18/scope?page_size=200",
      expect.objectContaining({ credentials: "same-origin" }),
    );
  });

  it("submits normalized server filters instead of filtering eligibility locally", async () => {
    const fetcher = tenantFetchStub();
    const router = createWorkbenchRouter({
      api: createApiClient(fetcher),
      history: createMemoryHistory({ initialEntries: ["/tenants/7/models/18/scope"] }),
    });
    const user = userEvent.setup();
    render(<WorkbenchApp router={router} />);
    await screen.findByRole("table", { name: "Active Scope" });

    await user.selectOptions(screen.getByLabelText("Zone"), "bronze");
    await user.type(screen.getByLabelText("System code"), " CRM ");
    await user.type(screen.getByLabelText("Source Tenant code"), " GRDM ");
    await user.type(screen.getByLabelText("Object name"), " Customer_Raw ");
    await user.click(screen.getByRole("button", { name: "Apply filters" }));

    expect(await screen.findByRole("table", { name: "Active Scope" })).toBeVisible();
    expect(fetcher).toHaveBeenCalledWith(
      "/api/v1/tenants/7/models/18/scope?zone=bronze&system_code=crm&source_tenant_code=grdm&object_name=customer_raw&page_size=200",
      expect.objectContaining({ credentials: "same-origin" }),
    );
  });

  it("opens details only on request and returns focus when the drawer closes", async () => {
    const fetcher = tenantFetchStub();
    const router = createWorkbenchRouter({
      api: createApiClient(fetcher),
      history: createMemoryHistory({ initialEntries: ["/tenants/7/models/18/scope"] }),
    });
    const user = userEvent.setup();
    render(<WorkbenchApp router={router} />);
    const showDetails = await screen.findByRole("button", {
      name: "Show details for customer_raw",
    });
    expect(fetcher.mock.calls.some(([input]) => String(input).endsWith("/scope/501"))).toBe(false);

    await user.click(showDetails);

    const drawer = await screen.findByRole("complementary", { name: "Scope Object details" });
    expect(within(drawer).getByRole("heading", { name: "customer_raw" })).toBeVisible();
    expect(within(drawer).getByText("customer_id")).toBeVisible();
    expect(within(drawer).getByText("Bronze source").parentElement).toHaveTextContent("Eligible");
    expect(within(drawer).getByText("Dimensional source").parentElement).toHaveTextContent("Not eligible");

    await user.click(within(drawer).getByRole("button", { name: "Close object details" }));

    expect(screen.queryByRole("complementary", { name: "Scope Object details" })).not.toBeInTheDocument();
    expect(screen.getByRole("button", { name: "Show details for customer_raw" })).toHaveFocus();
  });
});

function tenantFetchStub(): ReturnType<typeof vi.fn<typeof fetch>> {
  return vi.fn<typeof fetch>(async (input, init) => {
    const url = String(input);
    if (url === "/api/v1/session") return jsonResponse(sessionPayload);
    if (url === "/api/v1/tenants?page_size=200") return jsonResponse(tenantCollectionPayload);
    if (url === "/api/v1/tenants/7/select" && init?.method === "POST") {
      return jsonResponse({ tenant_id: 7 });
    }
    if (url === "/api/v1/tenants/7/home") return jsonResponse(tenantHomePayload);
    if (url === "/api/v1/tenants/7/models?status=active&page_size=200") {
      return jsonResponse(modelCollectionPayload);
    }
    if (url === "/api/v1/tenants/7/models?status=archived&page_size=200") {
      return jsonResponse(archivedModelCollectionPayload);
    }
    if (url === "/api/v1/tenants/7/models/18") return jsonResponse(modelDetailPayload);
    if (url === "/api/v1/tenants/7/models/18/overview") {
      return jsonResponse(modelOverviewPayload);
    }
    if (url === "/api/v1/tenants/7/models/18/scope?page_size=200") {
      return jsonResponse(modelScopePayload);
    }
    if (url.startsWith("/api/v1/tenants/7/models/18/scope?zone=bronze")) {
      return jsonResponse(modelScopePayload);
    }
    if (url === "/api/v1/tenants/7/models/18/scope/501") {
      return jsonResponse(modelScopeDetailPayload);
    }
    return jsonResponse({ error: { code: "not_found", message: "Not found." } }, 404);
  });
}

function jsonResponse(value: unknown, status = 200): Response {
  return new Response(JSON.stringify(value), {
    status,
    headers: { "content-type": "application/json" },
  });
}

const sessionPayload = {
  display_name: "Maaz",
  actor_kind: "human",
  is_super_admin: false,
  last_tenant_id: 7,
};

const tenantCollectionPayload = {
  items: [
    {
      tenant_id: 7,
      tenant_code: "NWA",
      tenant_name: "Northwind Analytics",
      tenant_description: "Customer and commerce workspace",
      tenant_visibility: "private",
      effective_role: "tenant_admin",
    },
    {
      tenant_id: 8,
      tenant_code: "GRDM",
      tenant_name: "Global Reference Data",
      tenant_description: "Enterprise reference workspace",
      tenant_visibility: "global",
      effective_role: "architect",
    },
  ],
  next_cursor: null,
};

const tenantHomePayload = {
  tenant: tenantCollectionPayload.items[0],
  lock: {
    is_locked: true,
    owner_display_name: "Elena Morris",
    owned_by_current_principal: false,
    purpose: "Metadata review",
    acquired_at: "2026-08-24T14:12:00Z",
    expires_at: "2026-08-24T15:12:00Z",
  },
  lock_actions: {
    can_acquire: false,
    can_renew: false,
    can_release: false,
    can_override: true,
  },
  systems: [
    {
      system_id: 4,
      system_code: "CRM",
      system_name: "Customer Relationship Management",
      system_type_name: "Salesforce",
      connection_count: 1,
      registered_object_count: 63,
      active_model_count: 2,
      last_metadata_update_time: "2026-08-24T13:34:00Z",
    },
  ],
};

const unlockedTenantHomePayload = {
  ...tenantHomePayload,
  lock: {
    is_locked: false,
    owner_display_name: null,
    owned_by_current_principal: null,
    purpose: null,
    acquired_at: null,
    expires_at: null,
  },
  lock_actions: {
    can_acquire: true,
    can_renew: false,
    can_release: false,
    can_override: false,
  },
};

const acquiredTenantHomePayload = {
  ...tenantHomePayload,
  lock: {
    is_locked: true,
    owner_display_name: "Maaz",
    owned_by_current_principal: true,
    purpose: "Scope review",
    acquired_at: "2026-08-24T14:12:00Z",
    expires_at: "2026-08-24T15:27:00Z",
  },
  lock_actions: {
    can_acquire: false,
    can_renew: true,
    can_release: true,
    can_override: false,
  },
};

const renewedTenantHomePayload = {
  ...acquiredTenantHomePayload,
  lock: {
    ...acquiredTenantHomePayload.lock,
    acquired_at: "2026-08-24T15:00:00Z",
    expires_at: "2026-08-24T17:00:00Z",
  },
};

const modelCollectionPayload = {
  items: [
    {
      model_id: 18,
      model_name: "Customer 360",
      model_description: "Cross-system customer domain",
      model_revision: 18,
      model_scope_object_count: 25,
      latest_workflow: "analysis",
      latest_run_status: "completed",
      updated_at: "2026-08-24T14:00:00Z",
    },
  ],
  next_cursor: null,
};

const archivedModelCollectionPayload = {
  items: [
    {
      ...modelCollectionPayload.items[0],
      model_id: 17,
      model_name: "Legacy Customer View",
      model_revision: 6,
      latest_workflow: null,
      latest_run_status: null,
    },
  ],
  next_cursor: null,
};

const modelDetailPayload = {
  model_id: 18,
  tenant_id: 7,
  model_name: "Customer 360",
  model_description: "Cross-system customer domain",
  model_revision: 18,
  model_scope_object_count: 25,
  silver_model_naming_instructions: "Use business names.",
  silver_model_audit_columns_template: { columns: ["created_at"] },
  gold_model_naming_instructions: null,
  gold_model_technical_columns_template: null,
  gold_model_audit_columns_template: null,
  default_agent_sdk_code: "langchain_create_agent",
  default_agent_provider_code: "databricks",
  default_agent_model_code: "databricks-primary",
  default_reasoning_effort_code: "medium",
  default_max_turns: 10,
  default_validation_retry_count: 2,
  is_active: true,
  updated_at: "2026-08-24T14:00:00Z",
};

const modelOverviewPayload = {
  model_id: 18,
  model_revision: 18,
  items: [
    workflowOverviewItem("scope", 25, "ready"),
    {
      ...workflowOverviewItem("profiling", 18, "results_available"),
      latest_run_id: 1048,
      latest_run_state: "completed",
      latest_run_created_at: "2026-08-24T14:00:00Z",
    },
    workflowOverviewItem("analysis", 0, "not_started"),
    workflowOverviewItem("assertions", 0, "not_started"),
    workflowOverviewItem("conceptual", 0, "not_started"),
    {
      ...workflowOverviewItem("logical", 0, "not_started"),
      quality_warning_codes: ["conceptual_results_unavailable"],
    },
    {
      ...workflowOverviewItem("dimensional", 0, "not_started"),
      quality_warning_codes: ["logical_results_unavailable"],
    },
  ],
};

function workflowOverviewItem(workflow: string, resultCount: number, state: string) {
  return {
    workflow,
    result_count: resultCount,
    needs_review_count: 0,
    locked_count: 0,
    latest_run_id: null,
    latest_run_state: null,
    latest_run_created_at: null,
    state,
    quality_warning_codes: [],
  };
}

const modelScopePayload = {
  model_id: 18,
  model_revision: 18,
  items: [
    {
      model_scope_id: 101,
      object_id: 501,
      connection_id: 21,
      system_id: 31,
      system_code: "CRM",
      system_name: "Customer Relationship Management",
      source_tenant_id: 8,
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
      created_at: "2026-08-24T14:00:00Z",
      updated_at: "2026-08-24T14:00:00Z",
    },
  ],
  next_cursor: null,
};

const modelScopeDetailPayload = {
  ...modelScopePayload.items[0],
  attribute_count: 2,
  attributes: [
    {
      attribute_id: 601,
      attribute_name: "customer_id",
      attribute_ordinal_position: 1,
      attribute_description: "Customer identifier",
      attribute_data_type: "bigint",
      attribute_nullability: false,
      is_surrogate_key: false,
      is_natural_key: true,
      is_meta_data: false,
      is_masking_required: false,
      is_mapped: false,
      is_purge: false,
      is_active: true,
    },
    {
      attribute_id: 602,
      attribute_name: "customer_name",
      attribute_ordinal_position: 2,
      attribute_description: null,
      attribute_data_type: "string",
      attribute_nullability: true,
      is_surrogate_key: false,
      is_natural_key: false,
      is_meta_data: false,
      is_masking_required: false,
      is_mapped: false,
      is_purge: false,
      is_active: true,
    },
  ],
};
