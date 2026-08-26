import { render, screen, waitFor, within } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { createMemoryHistory } from "@tanstack/react-router";
import { describe, expect, it, vi } from "vitest";

import { createApiClient } from "../../api";
import { WorkbenchApp, createWorkbenchRouter } from "../../app";

describe("Code Generation journey", () => {
  it("opens as a model-first active ledger", async () => {
    const fetcher = codeGenerationFetchStub();
    const user = userEvent.setup();
    render(<WorkbenchApp router={createWorkbenchRouter({
      api: createApiClient(fetcher),
      history: createMemoryHistory({ initialEntries: ["/tenants/7"] }),
    })} />);

    await user.click(await screen.findByRole("link", { name: "Code generation" }));

    const ledger = await screen.findByRole("table", { name: "Models for Code Generation" });
    expect(within(ledger).getByText("Customer 360")).toBeVisible();
    expect(within(ledger).getByRole("link", {
      name: "Open Customer 360 Code Generation",
    })).toHaveAttribute("href", "/tenants/7/code-generation/models/18");
    expect(fetcher).toHaveBeenCalledWith(
      "/api/v1/tenants/7/models?status=active&page_size=200",
      expect.objectContaining({ credentials: "same-origin" }),
    );
  });

  it("keeps target identity primary with server filters, paging, and a labeled page-local status view", async () => {
    const fetcher = codeGenerationFetchStub({ hasNextPage: true });
    const user = userEvent.setup();
    render(<WorkbenchApp router={createWorkbenchRouter({
      api: createApiClient(fetcher),
      history: createMemoryHistory({ initialEntries: ["/tenants/7/code-generation/models/18"] }),
    })} />);

    const ledger = await screen.findByRole("table", { name: "Code Generation target Objects" });
    expect(within(ledger).getByText("silver_nwa.customer")).toBeVisible();
    expect(within(ledger).getByText("Current")).toBeVisible();
    expect(within(ledger).getByText("Stale")).toBeVisible();
    expect(within(ledger).getAllByText("Not generated")).toHaveLength(2);
    expect(within(ledger).queryByRole("columnheader", { name: "Entity" })).not.toBeInTheDocument();

    await user.selectOptions(screen.getByLabelText("Modeled layer"), "dimensional_entity");
    await user.type(screen.getByLabelText("Target System code"), " GDS ");
    await user.type(screen.getByLabelText("Contributing System code"), " CRM ");
    await user.click(screen.getByRole("button", { name: "Apply server filters" }));

    expect(fetcher).toHaveBeenCalledWith(
      "/api/v1/tenants/7/models/18/code-generation/targets?entity_type=dimensional_entity&system_code=gds&source_system_code=crm&page_size=50",
      expect.objectContaining({ credentials: "same-origin" }),
    );
    await screen.findByRole("table", { name: "Code Generation target Objects" });
    const targetCallsBeforeStatus = targetCalls(fetcher).length;

    await user.selectOptions(screen.getByLabelText("Artifact status on this page"), "stale");

    expect(screen.getByText("Local view")).toBeVisible();
    expect(screen.getByText("silver_nwa.address")).toBeVisible();
    expect(screen.queryByText("silver_nwa.customer")).not.toBeInTheDocument();
    expect(targetCalls(fetcher)).toHaveLength(targetCallsBeforeStatus);

    await user.selectOptions(screen.getByLabelText("Artifact status on this page"), "");
    await user.click(screen.getByRole("button", { name: "Next" }));
    expect(fetcher).toHaveBeenCalledWith(
      "/api/v1/tenants/7/models/18/code-generation/targets?entity_type=dimensional_entity&system_code=gds&source_system_code=crm&page_size=50&cursor=targets-next",
      expect.objectContaining({ credentials: "same-origin" }),
    );
    expect(await screen.findByText("gold_nwa.order_mart")).toBeVisible();
  });

  it("reviews stored SQL and canonical provenance on a dedicated full page", async () => {
    const { container } = render(<WorkbenchApp router={createWorkbenchRouter({
      api: createApiClient(codeGenerationFetchStub()),
      history: createMemoryHistory({
        initialEntries: ["/tenants/7/code-generation/models/18/artifacts/501"],
      }),
    })} />);

    const heading = await screen.findByRole("heading", { name: "silver_nwa.customer" });
    expect(heading).toHaveFocus();
    expect(screen.getByRole("heading", { name: "Contributing source Systems" })).toBeVisible();
    expect(screen.getByText("Customer CRM")).toBeVisible();
    expect(screen.getByRole("table", { name: "Applied Mapping supports" })).toBeVisible();
    expect(screen.getByText("Customer source")).toBeVisible();
    expect(screen.getByText("Standard Databricks SQL (databricks.standard)")).toBeVisible();
    expect(screen.getByText("gds_sql_generator@1.2.0")).toBeVisible();
    expect(screen.getByText("a".repeat(64))).toBeVisible();
    expect(screen.getByLabelText("Stored SQL for silver_nwa.customer")).toHaveTextContent(
      "SELECT '<script>not executable</script>' AS literal;",
    );
    expect(container.querySelector("script")).toBeNull();
    expect(screen.getByRole("link", { name: "Download .sql" })).toHaveAttribute(
      "href",
      "/api/v1/tenants/7/models/18/code-generation/artifacts/501/download.sql",
    );
  });

  it("gates generation, then explicitly creates and executes selected and all coverage", async () => {
    const unlocked = render(<WorkbenchApp router={createWorkbenchRouter({
      api: createApiClient(codeGenerationFetchStub({ hasLock: false })),
      history: createMemoryHistory({ initialEntries: ["/tenants/7/code-generation/models/18"] }),
    })} />);
    await screen.findByRole("table", { name: "Code Generation target Objects" });
    expect(screen.getByRole("button", { name: "Generate selected" })).toBeDisabled();
    expect(screen.getByRole("button", { name: "Generate all eligible" })).toBeDisabled();
    expect(screen.getByText("Tenant Lock required to generate SQL")).toBeVisible();
    unlocked.unmount();

    const denied = render(<WorkbenchApp router={createWorkbenchRouter({
      api: createApiClient(codeGenerationFetchStub({ role: "developer" })),
      history: createMemoryHistory({ initialEntries: ["/tenants/7/code-generation/models/18"] }),
    })} />);
    await screen.findByRole("table", { name: "Code Generation target Objects" });
    expect(screen.getByRole("button", { name: "Generate all eligible" })).toBeDisabled();
    expect(screen.getByText("Architect permission required to generate SQL")).toBeVisible();
    denied.unmount();

    const fetcher = codeGenerationFetchStub();
    const user = userEvent.setup();
    render(<WorkbenchApp router={createWorkbenchRouter({
      api: createApiClient(fetcher),
      history: createMemoryHistory({ initialEntries: ["/tenants/7/code-generation/models/18"] }),
    })} />);
    await screen.findByRole("table", { name: "Code Generation target Objects" });
    await user.click(screen.getByRole("checkbox", { name: "Select silver_nwa.customer" }));
    await user.click(screen.getByRole("button", { name: "Generate selected" }));
    expect(await screen.findByRole("heading", { name: "Regenerate stored SQL" })).toBeVisible();
    await user.click(screen.getByRole("button", { name: "Regenerate stored SQL" }));

    await screen.findByText("Code Generation run 1151 started. Refresh after completion to review stored SQL.");
    const selectedCreate = createCalls(fetcher)[0];
    expect(JSON.parse(String(selectedCreate?.[1]?.body))).toEqual({
      expected_model_revision: 18,
      model_workflow: "code_generation",
      workflow_execution_mode: null,
      selected_object_ids: [701],
      modeled_entity_type: "logical_entity",
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
      code_generation_coverage_mode: "selected_targets",
      sql_generation_guide_version_id: null,
    });
    expect(fetcher).toHaveBeenCalledWith(
      "/api/v1/tenants/7/models/18/code-generation/runs/1151/execute",
      expect.objectContaining({
        method: "POST",
        body: JSON.stringify({ expected_model_revision: 18 }),
      }),
    );

    await user.click(screen.getByRole("button", { name: "Generate all eligible" }));
    expect(await screen.findByRole("heading", { name: "Generate all eligible SQL" })).toBeVisible();
    await user.click(screen.getByRole("button", { name: "Generate all eligible SQL" }));
    await screen.findByText("Code Generation run 1151 started. Refresh after completion to review stored SQL.");
    const allCreate = createCalls(fetcher)[1];
    expect(JSON.parse(String(allCreate?.[1]?.body))).toEqual(expect.objectContaining({
      selected_object_ids: [],
      modeled_entity_type: "logical_entity",
      code_generation_coverage_mode: "all_eligible_targets",
    }));
    expect(JSON.stringify(createCalls(fetcher))).not.toContain("claim_token");
  });

  it("retries a conflicted Code Generation start without creating another run", async () => {
    const fetcher = codeGenerationFetchStub({ executeConflictOnce: true });
    const user = userEvent.setup();
    render(<WorkbenchApp router={createWorkbenchRouter({
      api: createApiClient(fetcher),
      history: createMemoryHistory({ initialEntries: ["/tenants/7/code-generation/models/18"] }),
    })} />);
    await screen.findByRole("table", { name: "Code Generation target Objects" });

    await user.click(screen.getByRole("checkbox", { name: "Select silver_nwa.customer" }));
    await user.click(screen.getByRole("button", { name: "Generate selected" }));
    const submit = await screen.findByRole("button", { name: "Regenerate stored SQL" });
    await waitFor(() => expect(submit).toBeEnabled());
    await user.click(submit);

    expect(await screen.findByRole("alert")).toHaveTextContent(
      "Another Workflow Run is already active for this Tenant. "
      + "This run remains queued; retry after the active run finishes.",
    );
    await user.click(screen.getByRole("button", { name: "Retry start" }));

    await waitFor(() => {
      expect(createCalls(fetcher)).toHaveLength(1);
      expect(fetcher.mock.calls.filter(([input, init]) => (
        String(input) === "/api/v1/tenants/7/models/18/code-generation/runs/1151/execute"
        && init?.method === "POST"
      ))).toHaveLength(2);
    });
  });

  it("cannot dismiss the dialog while a created run is still starting", async () => {
    const fetcher = codeGenerationFetchStub({ executePending: true });
    const user = userEvent.setup();
    render(<WorkbenchApp router={createWorkbenchRouter({
      api: createApiClient(fetcher),
      history: createMemoryHistory({ initialEntries: ["/tenants/7/code-generation/models/18"] }),
    })} />);
    await screen.findByRole("table", { name: "Code Generation target Objects" });

    await user.click(screen.getByRole("checkbox", { name: "Select silver_nwa.customer" }));
    await user.click(screen.getByRole("button", { name: "Generate selected" }));
    await user.click(await screen.findByRole("button", { name: "Regenerate stored SQL" }));

    const dialog = await screen.findByRole("dialog", { name: "Regenerate stored SQL" });
    expect(await within(dialog).findByRole("button", { name: "Starting…" })).toBeDisabled();
    expect(within(dialog).getByRole("button", { name: "Close Regenerate stored SQL" })).toBeDisabled();
    expect(within(dialog).getByRole("button", { name: "Cancel" })).toBeDisabled();
    await user.keyboard("{Escape}");
    expect(dialog).toBeVisible();
  });

  it("keeps empty, denied, error, and revision-drift states explicit and redacted", async () => {
    const empty = render(<WorkbenchApp router={createWorkbenchRouter({
      api: createApiClient(codeGenerationFetchStub({ empty: true })),
      history: createMemoryHistory({ initialEntries: ["/tenants/7/code-generation/models/18"] }),
    })} />);
    expect(await screen.findByText("No eligible target Objects match these server filters.")).toBeVisible();
    empty.unmount();

    const denied = render(<WorkbenchApp router={createWorkbenchRouter({
      api: createApiClient(codeGenerationFetchStub({ denied: true })),
      history: createMemoryHistory({ initialEntries: ["/tenants/7/code-generation/models/18"] }),
    })} />);
    expect(await screen.findByRole("alert")).toHaveTextContent(
      "You do not have permission to view Code Generation targets.",
    );
    denied.unmount();

    const drift = render(<WorkbenchApp router={createWorkbenchRouter({
      api: createApiClient(codeGenerationFetchStub({ modelRevision: 19 })),
      history: createMemoryHistory({ initialEntries: ["/tenants/7/code-generation/models/18"] }),
    })} />);
    expect(await screen.findByRole("alert")).toHaveTextContent(
      "The Model changed while Code Generation targets were loading.",
    );
    drift.unmount();

    render(<WorkbenchApp router={createWorkbenchRouter({
      api: createApiClient(codeGenerationFetchStub({ error: true })),
      history: createMemoryHistory({ initialEntries: ["/tenants/7/code-generation/models/18"] }),
    })} />);
    expect(await screen.findByRole("alert")).toHaveTextContent(
      "Code Generation targets could not be loaded.",
    );
    expect(screen.queryByText("secret physical row")).not.toBeInTheDocument();
  });
});

function codeGenerationFetchStub(options: {
  hasNextPage?: boolean;
  empty?: boolean;
  denied?: boolean;
  error?: boolean;
  modelRevision?: number;
  hasLock?: boolean;
  role?: string;
  executeConflictOnce?: boolean;
  executePending?: boolean;
} = {}) {
  let executeAttempts = 0;
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
    if (url.startsWith("/api/v1/tenants/7/models/18/code-generation/targets?")) {
      if (options.denied) return jsonResponse({ error: { code: "authorization_denied" } }, 403);
      if (options.error) {
        return new Response("secret physical row", { status: 503, headers: { "content-type": "text/plain" } });
      }
      const nextPage = url.includes("cursor=targets-next");
      return jsonResponse({
        model_id: 18,
        model_revision: options.modelRevision ?? 18,
        items: options.empty ? [] : nextPage ? [nextTarget] : codeGenerationTargets,
        next_cursor: options.hasNextPage && !nextPage ? "targets-next" : null,
      });
    }
    if (url === "/api/v1/tenants/7/models/18/code-generation/artifacts/501") {
      return jsonResponse(generatedSqlDetail);
    }
    if (url === "/api/v1/config/agent-capabilities") return jsonResponse(agentCapabilities);
    if (url === "/api/v1/tenants/7/models/18/runs") {
      return jsonResponse({
        created: true,
        workflow_run_id: 1151,
        workflow_run_state: "queued",
        correlation_id: "code-generation-run-1151",
        prompt_snapshot_count: 4,
        created_at: "2026-08-24T11:00:00Z",
      }, 201);
    }
    if (url === "/api/v1/tenants/7/models/18/code-generation/runs/1151/execute") {
      executeAttempts += 1;
      if (options.executePending) return new Promise<Response>(() => undefined);
      if (options.executeConflictOnce && executeAttempts === 1) {
        return jsonResponse({ error: { code: "tenant_workflow_conflict" } }, 409);
      }
      return jsonResponse({
        changed: true,
        workflow_run_id: 1151,
        workflow_run_state: "running",
        model_revision: 18,
      }, 202);
    }
    return new Response(null, { status: 404 });
  });
}

function targetCalls(fetcher: ReturnType<typeof vi.fn<typeof fetch>>) {
  return fetcher.mock.calls.filter(([input]) => String(input).includes("/code-generation/targets?"));
}

function createCalls(fetcher: ReturnType<typeof vi.fn<typeof fetch>>) {
  return fetcher.mock.calls.filter(([input, init]) => (
    String(input) === "/api/v1/tenants/7/models/18/runs" && init?.method === "POST"
  ));
}

function jsonResponse(value: unknown, status = 200): Response {
  return new Response(JSON.stringify(value), {
    status,
    headers: { "content-type": "application/json" },
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
    purpose: "Code Generation review",
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
  latest_workflow: "code_generation",
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

const targetObject = {
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

const mappingSupport = {
  mapping_object_id: 81,
  source: { entity_type: "logical_entity", entity_id: 41, entity_name: "Customer source" },
  source_system: { system_id: 2, system_code: "CRM", system_name: "Customer CRM" },
  dependency_order: 10,
};

const codeGenerationTargets = [
  codeGenerationTarget(targetObject, true, 501),
  codeGenerationTarget({ ...targetObject, object_id: 702, object_name: "address" }, false, 502),
  codeGenerationTarget({ ...targetObject, object_id: 703, object_name: "contact" }, null, null),
];

const nextTarget = codeGenerationTarget({
  ...targetObject,
  object_id: 704,
  object_schema: "gold_nwa",
  object_name: "order_mart",
  zone_code: "gold",
}, null, null);

function codeGenerationTarget(
  target: typeof targetObject,
  current: boolean | null,
  artifactId: number | null,
) {
  return {
    target,
    entity_type: "logical_entity",
    mapping_supports: [mappingSupport],
    mapping_support_count: 1,
    mapping_supports_truncated: false,
    source_systems: [mappingSupport.source_system],
    source_system_count: 1,
    mapping_context_digest: "b".repeat(64),
    source_context_digest: "c".repeat(64),
    latest_artifact: artifactId === null ? null : {
      generated_sql_artifact_id: artifactId,
      workflow_run_id: 1100,
      generated_at: "2026-08-24T10:30:00Z",
      generated_sql_digest: "d".repeat(64),
      artifact_is_current: current,
    },
  };
}

const generatedSqlDetail = {
  generated_sql_artifact_id: 501,
  model_id: 18,
  target: targetObject,
  entity_type: "logical_entity",
  source_systems: [mappingSupport.source_system],
  source_system_count: 1,
  mapping_supports: [mappingSupport],
  mapping_support_count: 1,
  mapping_supports_truncated: false,
  artifact_is_current: true,
  mapping_context_digest: "b".repeat(64),
  source_context_digest: "c".repeat(64),
  guide: {
    sql_generation_guide_id: 3,
    sql_generation_guide_code: "databricks.standard",
    sql_generation_guide_name: "Standard Databricks SQL",
    guide_is_active: true,
    sql_generation_guide_version_id: 13,
    sql_generation_guide_version_number: 4,
    sql_generation_guide_version_status: "published",
    sql_generation_guide_digest: "a".repeat(64),
  },
  workflow_run_id: 1100,
  generator: {
    generator_code: "gds_sql_generator",
    generator_version: "1.2.0",
    generated_by_display_name: "Maaz",
  },
  generated_at: "2026-08-24T10:30:00Z",
  generated_sql: "SELECT '<script>not executable</script>' AS literal;",
  generated_sql_digest: "d".repeat(64),
  generated_sql_byte_count: 51,
};

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
