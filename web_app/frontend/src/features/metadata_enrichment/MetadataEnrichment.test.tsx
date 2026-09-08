import { MetadataEnrichmentScreen } from "./MetadataEnrichmentScreen";
import type { ModelInputScopeDetail } from "../model_input_scope/api";
import type { ReviewMetadataRecordsCommand } from "../metadata/api";
import { ApiError } from "../../core/http";
import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { render, screen, waitFor, within } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { createMemoryHistory } from "@tanstack/react-router";
import { createApiClient } from "../../api";
import { WorkbenchApp, createWorkbenchRouter } from "../../app";
import type { ReactNode } from "react";
import { describe, expect, it, vi } from "vitest";

import type { ModelDetail } from "../models/api";
import { WorkflowRunDialog } from "../workflows/WorkflowRunDialog";
import { WorkflowRunMonitor } from "../workflows/WorkflowRunMonitor";
import { loadAllEnrichmentScope, type AgentCapabilities, type WorkflowCreationApi, type WorkflowRunDetail, type WorkflowRunMonitorApi } from "../workflows/api";
import { createHttpRequest } from "../../core/http";
import { createMetadataEnrichmentApi, type MetadataEnrichmentResult, type MetadataEnrichmentResultPage } from "./api";
import { MetadataEnrichmentResults } from "./MetadataEnrichmentResults";

const model: ModelDetail = {
  model_id: 18, tenant_id: 7, model_name: "Customer 360", model_description: null,
  model_revision: 18, model_input_scope_object_count: 2, silver_model_naming_instructions: null,
  silver_model_audit_columns_template: null, gold_model_naming_instructions: null,
  gold_model_technical_columns_template: null, gold_model_audit_columns_template: null,
  default_agent_sdk_code: "sdk", default_agent_provider_code: "provider",
  default_agent_model_code: "tool-only", default_reasoning_effort_code: "default",
  default_max_turns: 8, default_validation_retry_count: 1, is_active: true,
  updated_at: "2026-09-05T12:00:00Z",
};
const capabilities: AgentCapabilities = {
  schema_version: "3.0", sdks: [{ code: "openai_agents_sdk", name: "SDK", provider_codes: ["microsoft_foundry"] }],
  providers: [{ code: "microsoft_foundry", name: "Provider" }],
  models: ["tool-only", "one-shot"].map((code) => ({ code, name: code, provider_code: "microsoft_foundry", deployment_name: code,
    execution_profiles: [{ sdk_code: "openai_agents_sdk", execution_mode: code === "tool-only" ? "tool_assisted" : "one_shot", reasoning_effort_codes: ["default"] }] })),
  reasoning_efforts: [{ code: "default", name: "Default" }],
  max_turns: { minimum: 1, default: 8, maximum: 50 }, validation_retries: { minimum: 0, default: 1, maximum: 5 },
};
const scope = (id: number, zone: "source" | "bronze" = "source") => ({
  object_id: id, object_schema: "crm", source_tenant_id: 7, is_locked: false, review_revision: "a".repeat(64), system_id: 9, system_code: "CRM", source_tenant_code: "SHARED",
  object_name: `customer_${id}`, zone_code: zone, is_dimensional_source_eligible: false,
});
const run: WorkflowRunDetail = {
  token_usage: {
    status: "unavailable", request_count: 0, reported_request_count: 0,
    pending_request_count: 0, missing_usage_request_count: 0,
    input_tokens: null, output_tokens: null, total_tokens: null,
    cached_input_tokens: null, cache_write_input_tokens: null, reasoning_output_tokens: null,
    cost_estimate: { status: "unavailable", currency: "USD", amount: null,
      priced_request_count: 0, unpriced_request_count: 0, pricing_bases: [],
      unpriced_reasons: { pricing_not_configured: 0, outside_pricing_window: 0,
        context_limit_exceeded: 0, missing_usage: 0, unsupported_token_types: 0 } },
    history_incomplete: false,
  },
  workflow_run_id: 1048, model_workflow: "metadata_enrichment", workflow_execution_mode: "one_shot",
  modeled_entity_type: null, selected_scope_count: 2, requested_batch_id: null,
  workflow_run_state: "completed", actor_display_name: "Fixture user", created_at: "2026-09-05T12:00:00Z",
  started_at: "2026-09-05T12:00:01Z", completed_at: "2026-09-05T12:01:00Z", correlation_id: "fixture-correlation",
  agent_sdk_code: "sdk", agent_provider_code: "provider", agent_model_code: "one-shot",
  reasoning_effort_code: "default", max_turns: 8, validation_retry_count: 1, failure_code: null, failure_message: null,
  model_change_set_id: null, model_change_set_status: null, draft_revision: null, candidate_digest: null, validated_at: null,
};
const field = (overrides: Partial<MetadataEnrichmentResult> = {}): MetadataEnrichmentResult => ({
  result_id: 1, object_id: 501, attribute_id: null, object_schema: "crm", object_name: "customers",
  attribute_name: null, storage_type: null, field_name: "object_description", status: "applied",
  evidence_method: "source_comment", applied_value: "Customer accounts.\nIncludes archived accounts.", sample_count: 0, ...overrides,
});
const page = (overrides: Partial<MetadataEnrichmentResultPage> = {}): MetadataEnrichmentResultPage => ({
  tenant_id: 7, model_id: 18, model_revision: 18, workflow_run_id: 1048, workflow_run_state: "completed",
  total_count: 3, result_count: 3, warning_count: 0, counts: { applied: 2, locked: 1 },
  applied_field_counts: { object_description: 1, attribute_description: 0, attribute_inferred_data_type: 1 },
  results: [field(), field({ result_id: 2, attribute_id: 81, attribute_name: "customer_id", storage_type: "STRING", field_name: "attribute_inferred_data_type", evidence_method: "source_sample", applied_value: "BIGINT", sample_count: 50 }),
    field({ result_id: 3, attribute_id: 81, attribute_name: "customer_id", storage_type: "STRING", field_name: "attribute_description", status: "locked", evidence_method: "none", applied_value: null })],
  limit: 100, offset: 0, next_offset: null, ...overrides,
});
function creationApi() {
  return {
    listModelInputScope: vi.fn<WorkflowCreationApi["listModelInputScope"]>(async () => ({ model_revision: 18, items: [scope(501), scope(502, "bronze")], next_cursor: null })),
    readAgentCapabilities: vi.fn(async () => capabilities),
    createWorkflowRun: vi.fn<WorkflowCreationApi["createWorkflowRun"]>(async () => ({ workflow_run_id: 1048, model_id: 18, model_revision: 18, workflow_run_state: "queued", correlation_id: "fixture", created: true, prompt_snapshot_count: 1, created_at: "2026-09-05T12:00:00Z" })),
  };
}
function setup(children: ReactNode) {
  const client = new QueryClient({ defaultOptions: { queries: { retry: false, refetchOnWindowFocus: false, staleTime: Infinity }, mutations: { retry: false } } });
  return { ...render(<QueryClientProvider client={client}>{children}</QueryClientProvider>), client };
}

describe("Metadata enrichment scope and run creation", () => {
  it("loads both Source and Bronze pages with exact cursor and revision fences", async () => {
    const api = creationApi();
    api.listModelInputScope.mockResolvedValueOnce({ model_revision: 18, items: [scope(501)], next_cursor: "opaque" })
      .mockResolvedValueOnce({ model_revision: 18, items: [scope(502, "bronze")], next_cursor: null });
    expect((await loadAllEnrichmentScope(api, 7, 18)).items.map((item) => item.object_id)).toEqual([501, 502]);
    expect(api.listModelInputScope.mock.calls).toEqual([[7, 18, {}, 200, undefined], [7, 18, {}, 200, "opaque"]]);
  });
  it.each(["revision", "cursor", "zone"])("rejects %s drift while loading scope", async (drift) => {
    const api = creationApi();
    api.listModelInputScope.mockResolvedValueOnce({ model_revision: 18, items: [scope(501)], next_cursor: "opaque" })
      .mockResolvedValue({ model_revision: drift === "revision" ? 19 : 18, items: [{ ...scope(502), zone_code: drift === "zone" ? "silver" : "bronze" }], next_cursor: drift === "cursor" ? "opaque" : null });
    await expect(loadAllEnrichmentScope(api, 7, 18)).rejects.toThrow();
  });
  it("restricts profiles to one shot and reuses create identity after an ambiguous response", async () => {
    const api = creationApi(); const user = userEvent.setup(); const onCreated = vi.fn(async () => undefined);
    api.createWorkflowRun.mockRejectedValueOnce(new TypeError("Network unavailable"));
    setup(<WorkflowRunDialog api={api} tenantId={7} model={model} kind="inference" workflow="metadata_enrichment" onClose={vi.fn()} onCreated={onCreated} />);
    const submit = await screen.findByRole("button", { name: "Run object enrichment" });
    await waitFor(() => expect(submit).toBeEnabled());
    expect(screen.queryByLabelText("Execution mode")).not.toBeInTheDocument();
    expect(screen.queryByLabelText("Batch ID (optional)")).not.toBeInTheDocument();
    expect(screen.getByRole("combobox", { name: "Model" })).toHaveValue("one-shot");
    await user.click(submit);
    await screen.findByText("The Metadata enrichment run could not be created.");
    await user.click(submit);
    await waitFor(() => expect(onCreated).toHaveBeenCalledWith(1048));
    const first = api.createWorkflowRun.mock.calls[0];
    expect(first?.slice(0, 3)).toEqual([7, 18, { expected_model_revision: 18, model_workflow: "metadata_enrichment", workflow_execution_mode: "one_shot", selected_object_ids: [501, 502], requested_batch_id: null, agent: { sdk_code: "openai_agents_sdk", provider_code: "microsoft_foundry", model_code: "one-shot", reasoning_effort_code: "default", max_turns: 8, validation_retry_count: 1 }, prompt_overrides: {}, description_targets: [501, 502].map((object_id) => ({ object_id, attribute_id: null, expected_revision: "a".repeat(64) })) }]);
    expect(api.createWorkflowRun.mock.calls[1]).toEqual(first);
  });
  it("All includes only unlocked owned Objects and freezes each description revision", async () => {
    const api = creationApi(); const user = userEvent.setup();
    api.listModelInputScope.mockResolvedValue({ model_revision: 18, items: [scope(501), { ...scope(502), is_locked: true }, { ...scope(503), source_tenant_id: 8 }], next_cursor: null });
    setup(<WorkflowRunDialog api={api} tenantId={7} model={model} kind="inference" workflow="metadata_enrichment" onClose={vi.fn()} onCreated={vi.fn(async () => undefined)} />);
    const submit = await screen.findByRole("button", { name: "Run object enrichment" });
    await waitFor(() => expect(submit).toBeEnabled());
    expect(screen.getAllByRole("checkbox")).toHaveLength(1);
    await user.click(submit);
    expect(api.createWorkflowRun.mock.calls[0]?.[2].description_targets).toEqual([{ object_id: 501, attribute_id: null, expected_revision: "a".repeat(64) }]);
  });

  it("does not turn a locked-only selection into an All run", async () => {
    const api = creationApi(); const user = userEvent.setup();
    api.listModelInputScope.mockResolvedValue({ model_revision: 18, items: [scope(501), { ...scope(502), is_locked: true }], next_cursor: null });
    setup(<WorkflowRunDialog api={api} tenantId={7} model={model} kind="inference" workflow="metadata_enrichment" initialSelectedIds={[502]} onClose={vi.fn()} onCreated={vi.fn(async () => undefined)} />);
    const submit = await screen.findByRole("button", { name: "Run object enrichment" });
    await waitFor(() => expect(screen.getByRole("combobox", { name: "Model" })).toHaveValue("one-shot"));
    expect(submit).toBeDisabled();
    await user.click(submit); expect(api.createWorkflowRun).not.toHaveBeenCalled();
  });

  it("blocks all scope over 200 and permits an exact subset", async () => {
    const api = creationApi(); const user = userEvent.setup();
    api.listModelInputScope.mockResolvedValue({ model_revision: 18, items: Array.from({ length: 201 }, (_, index) => scope(index + 1)), next_cursor: null });
    setup(<WorkflowRunDialog api={api} tenantId={7} model={model} kind="inference" workflow="metadata_enrichment" onClose={vi.fn()} onCreated={vi.fn(async () => undefined)} />);
    const submit = await screen.findByRole("button", { name: "Run object enrichment" });
    await screen.findByText(/Select up to 200 Objects. Choose Selected Objects/);
    expect(submit).toBeDisabled();
    await user.click(screen.getByRole("radio", { name: /Selected Objects/ }));
    await user.click(screen.getByRole("checkbox", { name: /customer_1crm/ }));
    await user.click(submit);
    await waitFor(() => expect(api.createWorkflowRun).toHaveBeenCalledOnce());
    expect(api.createWorkflowRun.mock.calls[0]?.[2].selected_object_ids).toEqual([1]);
  });
  it("blocks a Model revision mismatch and traps keyboard focus", async () => {
    const api = creationApi(); const user = userEvent.setup();
    api.listModelInputScope.mockResolvedValue({ model_revision: 19, items: [scope(501)], next_cursor: null });
    const onClose = vi.fn();
    setup(<WorkflowRunDialog api={api} tenantId={7} model={model} kind="inference" workflow="metadata_enrichment" onClose={onClose} onCreated={vi.fn(async () => undefined)} />);
    await screen.findByText(/The Model changed. Close this dialog/);
    expect(screen.getByRole("button", { name: "Run object enrichment" })).toBeDisabled();
    const close = screen.getByRole("button", { name: "Close Enrich objects" });
    await waitFor(() => expect(screen.getByRole("combobox", { name: "Model" })).toHaveValue("one-shot"));
    close.focus(); expect(close).toHaveFocus(); await user.tab({ shift: true });
    expect(screen.getByRole("button", { name: "Cancel" })).toHaveFocus();
    await user.tab(); expect(close).toHaveFocus();
    await user.keyboard("{Escape}"); expect(onClose).toHaveBeenCalledOnce();
  });
});

describe("Metadata enrichment Model screen", () => {
  it.each([false, true])("creates then starts through the registered Model route (start retry: %s)", async (retryStart) => {
    let current: WorkflowRunDetail | null = null;
    let startAttempts = 0;
    const respond = (value: unknown) => new Response(JSON.stringify(value), { headers: { "content-type": "application/json" } });
    const fetcher = vi.fn<typeof fetch>(async (input, init) => {
      const url = String(input);
      if (url.endsWith("/home")) return respond({ tenant: { tenant_id: 7, tenant_code: "NWA", tenant_name: "Northwind", tenant_description: null, tenant_visibility: "private", effective_role: "tenant_admin" },
        lock: { is_locked: true, owner_display_name: "Fixture user", owned_by_current_principal: true, purpose: "Test", acquired_at: "2026-09-05T12:00:00Z", expires_at: "2026-09-06T12:00:00Z" },
        lock_actions: { can_acquire: false, can_renew: true, can_release: true, can_override: false }, systems: [] });
      if (url.endsWith("/models/18")) return respond(model);
      if (url.includes("/input-scope?")) return respond({ model_revision: 18, items: [scope(501), scope(502, "bronze")], next_cursor: null });
      if (url.endsWith("/agent-capabilities")) return respond(capabilities);
      if (url.includes("/runs?")) return respond({ items: current ? [current] : [], next_cursor: null });
      if (url.endsWith("/runs") && init?.method === "POST") {
        current = { ...run, workflow_run_state: "queued" };
        return respond({ workflow_run_id: 1048, model_id: 18, model_revision: 18, workflow_run_state: "queued", correlation_id: "fixture", created: true, prompt_snapshot_count: 1, created_at: run.created_at });
      }
      if (url.endsWith("/metadata-enrichment/runs/1048/execute")) {
        startAttempts += 1;
        if (retryStart && startAttempts === 1) throw new TypeError("Synthetic network failure");
        current = { ...run, workflow_run_state: "running" };
        return respond({ workflow_run_id: 1048, model_revision: 18, workflow_run_state: "running", changed: true });
      }
      if (url.endsWith("/runs/1048")) return respond(current);
      if (url.includes("/events?")) return respond({ items: [], next_after_sequence: 0 });
      throw new Error("Unexpected synthetic route");
    });
    const user = userEvent.setup();
    render(<WorkbenchApp router={createWorkbenchRouter({ api: createApiClient(fetcher), history: createMemoryHistory({ initialEntries: ["/tenants/7/models/18/metadata-enrichment"] }) })} />);
    const trigger = await screen.findByRole("button", { name: "Run object enrichment" });
    expect(screen.getByRole("link", { name: "Metadata enrichment" })).toHaveAttribute("href", "/tenants/7/models/18/metadata-enrichment");
    await user.click(trigger);
    const submit = within(screen.getByRole("dialog")).getByRole("button", { name: "Run object enrichment" });
    await waitFor(() => expect(submit).toBeEnabled());
    await user.click(submit);
    if (retryStart) {
      const retry = await screen.findByRole("button", { name: "Retry start" });
      expect(screen.getByRole("alert")).toHaveTextContent("remains queued");
      await user.click(retry);
    }
    await screen.findByRole("table", { name: "Enrichment runs" });
    expect(screen.queryByRole("dialog")).not.toBeInTheDocument();
    expect(trigger).toHaveFocus();
    const createCalls = fetcher.mock.calls.filter(([input, init]) => String(input).endsWith("/runs") && init?.method === "POST");
    const startCalls = fetcher.mock.calls.filter(([input]) => String(input).endsWith("/execute"));
    expect(createCalls).toHaveLength(1);
    expect(JSON.parse(String(createCalls[0]?.[1]?.body)).selected_object_ids).toEqual([501, 502]);
    expect(startCalls).toHaveLength(retryStart ? 2 : 1);
    for (const [, init] of startCalls) expect(JSON.parse(String(init?.body))).toEqual({ execution_mode: "one_shot", expected_model_revision: 18 });
    expect(screen.queryByLabelText("Validated draft status")).not.toBeInTheDocument();
  });
});

describe("Metadata enrichment results", () => {
  it("shows accurate field totals, historical values, storage type and evidence without Apply", async () => {
    const api = { readMetadataEnrichmentResults: vi.fn(async () => page()) }; const user = userEvent.setup();
    setup(<MetadataEnrichmentResults api={api} tenantId={7} modelId={18} runId={1048} />);
    await screen.findByRole("heading", { name: "2 missing fields filled" });
    expect(screen.getByText("0 preserved · 1 locked · 0 unresolved")).toBeVisible();
    await user.click(screen.getByText("Inspect inferred type"));
    expect(screen.getByText("BIGINT")).toBeVisible();
    expect(screen.getByText("Source samples · 50 samples")).toBeVisible();
    expect(screen.getAllByText("STRING")[0]).toBeVisible();
    await user.click(screen.getByText("Inspect object description"));
    expect(screen.getByText(/Customer accounts. Includes archived accounts./)).toBeVisible();
    expect(screen.getByText(/Saved values from Run 1048/)).toBeVisible();
    expect(screen.queryByRole("button", { name: /Apply/ })).not.toBeInTheDocument();
  });
  it("distinguishes a no-op from unresolved evidence and unavailable current labels", async () => {
    const api = { readMetadataEnrichmentResults: vi.fn(async () => page({ counts: { existing: 1, inconclusive: 1, unavailable: 1 }, warning_count: 2,
      applied_field_counts: { object_description: 0, attribute_description: 0, attribute_inferred_data_type: 0 },
      results: [field({ object_name: null, object_schema: null, attribute_id: 81, attribute_name: null, field_name: "attribute_inferred_data_type", status: "inconclusive", evidence_method: "source_sample", applied_value: null, sample_count: 50 })] })) };
    setup(<MetadataEnrichmentResults api={api} tenantId={7} modelId={18} runId={1048} />);
    expect(await screen.findByText("No missing values filled")).toBeVisible();
    expect(screen.getByText("1 preserved · 0 locked · 2 unresolved")).toBeVisible();
    expect(screen.getByText(/Unresolved fields remain empty/)).toBeVisible();
    expect(screen.getByRole("rowheader")).toHaveTextContent("Object 501Attribute 81");
  });
  it.each(["tenant", "model", "run", "offset", "state"])("hides a mismatched %s response", async (mismatch) => {
    const api = { readMetadataEnrichmentResults: vi.fn(async () => page({
      ...(mismatch === "tenant" ? { tenant_id: 99 } : {}), ...(mismatch === "model" ? { model_id: 99 } : {}),
      ...(mismatch === "run" ? { workflow_run_id: 99 } : {}), ...(mismatch === "offset" ? { offset: 100 } : {}),
      ...(mismatch === "state" ? { workflow_run_state: "running" as const } : {}),
    })) };
    setup(<MetadataEnrichmentResults api={api} tenantId={7} modelId={18} runId={1048} />);
    expect(await screen.findByRole("alert")).toHaveTextContent("Enrichment results could not be loaded");
    expect(screen.queryByRole("table")).not.toBeInTheDocument();
  });
  it("paginates exact offsets with global totals and refreshes only the selected run", async () => {
    const api = {
      listWorkflowRuns: vi.fn<WorkflowRunMonitorApi["listWorkflowRuns"]>(async () => ({ items: [run], next_cursor: null })),
      readWorkflowRun: vi.fn(async () => ({ ...run, model_change_set_id: "unrelated-draft", model_change_set_status: "validated" as const, draft_revision: 2, candidate_digest: "d".repeat(64), validated_at: run.completed_at })),
      listWorkflowRunEvents: vi.fn<WorkflowRunMonitorApi["listWorkflowRunEvents"]>(async () => ({ items: [], next_after_sequence: 0 })),
      readWorkflowDraftReview: vi.fn(), applyWorkflowDraft: vi.fn(),
      readMetadataEnrichmentResults: vi.fn(async (_tenant: number, _model: number, _run: number, _limit = 100, offset = 0) => page({ offset,
        total_count: 101, result_count: 101, counts: { applied: 101 }, applied_field_counts: { object_description: 1, attribute_description: 0, attribute_inferred_data_type: 100 },
        results: offset === 0 ? Array.from({ length: 100 }, (_, index) => field({ result_id: index + 1, object_name: `object_${index}` })) : [field({ result_id: 101, object_name: "last_object" })], next_offset: offset === 0 ? 100 : null })),
    };
    const user = userEvent.setup();
    setup(<WorkflowRunMonitor api={api} enrichmentApi={api} tenantId={7} modelId={18} modelRevision={18} workflow="metadata_enrichment" hasTenantLock focusRunId={1048} onApplied={vi.fn(async () => undefined)} />);
    await screen.findByRole("heading", { name: "101 missing fields filled" });
    expect(screen.queryByLabelText("Validated draft status")).not.toBeInTheDocument();
    await user.click(screen.getByRole("button", { name: "Next results" }));
    await screen.findByText("crm.last_object");
    expect(api.readMetadataEnrichmentResults).toHaveBeenLastCalledWith(7, 18, 1048, 100, 100);
    expect(screen.getByText("101–101 of 101 fields")).toBeVisible();
    expect(within(screen.getByLabelText("Fields filled across this run")).getByText("100")).toBeVisible();
    await user.click(screen.getByRole("button", { name: "Refresh runs" }));
    await waitFor(() => expect(api.readMetadataEnrichmentResults).toHaveBeenCalledTimes(3));
    expect(api.readMetadataEnrichmentResults).toHaveBeenLastCalledWith(7, 18, 1048, 100, 100);
    expect(api.readWorkflowDraftReview).not.toHaveBeenCalled(); expect(api.applyWorkflowDraft).not.toHaveBeenCalled();
  });
  it("uses the governed result endpoint with limit and offset", async () => {
    const fetcher = vi.fn<typeof fetch>(async () => new Response(JSON.stringify(page()), { headers: { "content-type": "application/json" } }));
    await createMetadataEnrichmentApi(createHttpRequest(fetcher)).readMetadataEnrichmentResults(7, 18, 1048, 100, 100);
    expect(fetcher.mock.calls[0]?.[0]).toBe("/api/v1/tenants/7/models/18/runs/1048/metadata-enrichment?limit=100&offset=100");
  });
});

describe("current metadata enrichment workspace", () => {
  function metadataFixture(options: { failOnce?: boolean; foreign?: boolean; secondObject?: boolean } = {}) {
    let revision = "a".repeat(64);
    let attempts = 0;
    let metadata: ModelInputScopeDetail = {
      model_input_scope_id: 1, object_id: 501, connection_id: 1, system_id: 9,
      system_code: "CRM", system_name: "Customer system", source_tenant_id: options.foreign ? 8 : 7,
      source_tenant_code: "NWA", source_tenant_name: "Northwind", object_schema: "crm", object_name: "customers",
      zone_code: "source", object_description: "Customer accounts.", description_truncated: false, is_locked: false,
      review_revision: revision, batch_attribute_name: null, attribute_count: 1, total_attribute_count: 1, is_model_input_eligible: true,
      is_dimensional_source_eligible: false, is_logical_mapping_target_eligible: false, is_dimensional_mapping_target_eligible: false,
      created_at: "2026-09-05T12:00:00Z", updated_at: "2026-09-05T12:00:00Z",
      attributes: [{ attribute_id: 81, review_revision: revision, attribute_name: "customer_id", attribute_ordinal_position: 1,
        attribute_description: "Customer identifier.", attribute_data_type: "STRING", attribute_inferred_data_type: "BIGINT",
        attribute_nullability: false, is_surrogate_key: false, is_natural_key: true, is_meta_data: false,
        is_masking_required: false, is_mapped: false, is_purge: false, is_locked: false, is_active: true }],
    };
    const api = {
      ...creationApi(),
      listModelInputScope: vi.fn(async () => ({ model_id: 18, model_revision: 18, items: options.secondObject ? [metadata, { ...metadata, object_id: 502, object_name: "orders" }] : [metadata], next_cursor: null })),
      readModelInputScopeObject: vi.fn(async (_tenant: number, _model: number, objectId: number) => objectId === 502
        ? { ...metadata, object_id: 502, object_name: "orders", attributes: metadata.attributes.map((attribute) => ({ ...attribute, attribute_id: 82 })) } : metadata),
      listWorkflowRuns: vi.fn(async () => ({ items: [run], next_cursor: null })),
      readWorkflowRun: vi.fn(async () => run),
      listWorkflowRunEvents: vi.fn(async () => ({ items: [], next_after_sequence: 0 })),
      readWorkflowDraftReview: vi.fn(), applyWorkflowDraft: vi.fn(), listWorkflowDraftRecords: vi.fn(),
      readMetadataEnrichmentResults: vi.fn(),
      executeMetadataEnrichmentRun: vi.fn(async () => ({ workflow_run_id: 1048, model_revision: 18, workflow_run_state: "running" as const, changed: true })),
      reviewMetadataRecords: vi.fn(async (_tenantId: number, command: ReviewMetadataRecordsCommand, _key: string) => {
        if (options.failOnce && attempts++ === 0) throw new ApiError(503, "dependency_unavailable", "Synthetic response");
        revision = "b".repeat(64);
        const description = command.action === "describe" ? command.records[0]!.description : undefined;
        if (command.record_type === "object") metadata = { ...metadata, review_revision: revision,
          ...(description !== undefined ? { object_description: description } : { is_locked: command.action === "lock" }) };
        else metadata = { ...metadata, attributes: metadata.attributes.map((attribute) => ({ ...attribute, review_revision: revision,
          ...(description !== undefined ? { attribute_description: description } : { is_locked: command.action === "lock" }) })) };
        return { review_event_id: 1, action_count: command.records.length, records: command.records.map((item) => ({ record_id: item.record_id, review_revision: revision, is_locked: command.action === "lock", is_active: true })) };
      }),
    };
    setup(<MetadataEnrichmentScreen api={api} tenantId={7} model={model} hasTenantLock />);
    return api;
  }

  it("locks selected Objects together with only Edit in row actions", async () => {
    const api = metadataFixture({ secondObject: true }); const user = userEvent.setup();
    const table = await screen.findByRole("table", { name: "Object metadata" });
    expect(screen.getByRole("button", { name: "Lock" })).toBeDisabled();
    expect(within(table).queryByRole("button", { name: "Regenerate" })).not.toBeInTheDocument();
    expect(within(table).queryByRole("button", { name: "Lock" })).not.toBeInTheDocument();
    await user.click(within(table).getByRole("checkbox", { name: "Select all visible records" }));
    await user.click(screen.getByRole("button", { name: "Lock" }));
    await screen.findByText("Metadata saved.");
    expect(api.reviewMetadataRecords.mock.calls[0]?.[1]).toEqual({ record_type: "object", action: "lock", records: [501, 502].map((record_id) => ({ record_id, expected_revision: "a".repeat(64) })) });
    expect(within(table).getAllByText("Locked")).toHaveLength(2);
  });

  it("edits current metadata and preserves the exact request across an uncertain save", async () => {
    const api = metadataFixture({ failOnce: true }); const user = userEvent.setup();
    const table = await screen.findByRole("table", { name: "Object metadata" });
    expect(within(table).getAllByRole("columnheader").map((cell) => cell.textContent)).toEqual(["", "Schema", "Object", "Description", "Zone", "Attributes", "Actions", "Details"]);
    expect(screen.queryByText(/Complete missing/)).not.toBeInTheDocument();
    expect(screen.getByRole("button", { name: "Show activity" })).toHaveAttribute("aria-expanded", "false");
    await user.click(within(table).getByRole("button", { name: "Edit" }));
    const input = screen.getByRole("textbox", { name: "customers" }); expect(input).toHaveFocus();
    await user.clear(input); await user.type(input, "Active customer accounts.");
    await user.click(screen.getByRole("button", { name: "Save description" }));
    const retry = await screen.findByRole("button", { name: "Retry same save" });
    expect(input).toBeDisabled(); expect(screen.getByRole("button", { name: "Cancel" })).toBeDisabled();
    await user.click(retry);
    await waitFor(() => expect(screen.queryByRole("dialog")).not.toBeInTheDocument());
    expect(within(table).getByText("Active customer accounts.")).toBeVisible();
    expect(within(table).getByRole("button", { name: "Edit" })).toHaveFocus();
    const calls = api.reviewMetadataRecords.mock.calls;
    expect(calls).toHaveLength(2); expect(calls[0]).toEqual(calls[1]);
    expect(calls[0]![1]).toEqual({ record_type: "object", action: "describe", records: [{ record_id: 501, expected_revision: "a".repeat(64), description: "Active customer accounts." }] });
  });

  it("uses physical Object locks and allows editing Attribute descriptions inside Object details", async () => {
    const api = metadataFixture(); const user = userEvent.setup();
    const table = await screen.findByRole("table", { name: "Object metadata" });
    await user.click(within(table).getByRole("checkbox", { name: "Select Object 501" }));
    await user.click(screen.getByRole("button", { name: "Lock" }));
    const unlock = screen.getByRole("button", { name: "Unlock" });
    await waitFor(() => expect(api.reviewMetadataRecords).toHaveBeenCalledOnce());
    await user.click(within(table).getByRole("checkbox", { name: "Select Object 501" }));
    expect(within(table).getByRole("button", { name: "Edit" })).toBeDisabled();
    expect(within(table).queryByRole("button", { name: "Regenerate" })).not.toBeInTheDocument();
    await waitFor(() => expect(unlock).toBeEnabled()); await user.click(unlock);
    await waitFor(() => expect(within(table).getByRole("button", { name: "Edit" })).toBeEnabled());
    await user.click(within(table).getByRole("button", { name: "Show details for customers" }));
    const attributes = await screen.findByRole("table", { name: "Attributes for customers" });
    expect(within(attributes).getByText("BIGINT")).toBeVisible(); expect(within(attributes).queryByText("STRING")).not.toBeInTheDocument();
    await user.click(within(attributes).getByRole("button", { name: "Edit" }));
    await user.clear(screen.getByRole("textbox", { name: "customer_id" }));
    await user.type(screen.getByRole("textbox", { name: "customer_id" }), "Stable customer identifier.");
    await user.click(screen.getByRole("button", { name: "Save description" }));
    await within(attributes).findByText("Stable customer identifier.");
    expect(api.reviewMetadataRecords.mock.lastCall?.[1]).toEqual({ record_type: "attribute", action: "describe", records: [{ record_id: 81, expected_revision: "a".repeat(64), description: "Stable customer identifier." }] });
    await user.click(screen.getByRole("button", { name: "← Back to Objects" }));
    expect(screen.getByRole("button", { name: "Show details for customers" })).toHaveFocus();
  });

  it("offers separate Object and Attribute actions and respects Object page selection", async () => {
    const api = metadataFixture({ secondObject: true }); const user = userEvent.setup();
    const table = await screen.findByRole("table", { name: "Object metadata" });
    expect(screen.getByRole("button", { name: "Refresh" })).toBeVisible();
    expect(screen.getByRole("button", { name: "Run object enrichment" })).toBeEnabled();
    await user.click(within(table).getByRole("checkbox", { name: "Select Object 502" }));
    await user.click(screen.getByRole("button", { name: "Run attribute enrichment" }));
    const dialog = screen.getByRole("dialog");
    const submit = within(dialog).getByRole("button", { name: "Run attribute enrichment" });
    await waitFor(() => expect(submit).toBeEnabled());
    expect(within(dialog).getByRole("checkbox", { name: "Include Object customers" })).not.toBeChecked();
    expect(within(dialog).getByRole("checkbox", { name: "Include Object orders" })).toBeChecked();
    await user.click(submit);
    await waitFor(() => expect(api.executeMetadataEnrichmentRun).toHaveBeenCalledOnce());
    expect(api.createWorkflowRun.mock.calls[0]?.[2]).toMatchObject({ selected_object_ids: [502],
      description_targets: [{ object_id: 502, attribute_id: 82, expected_revision: "a".repeat(64) }] });
  });

  it("regenerates only the chosen Attribute using the normal model and effort controls", async () => {
    const api = metadataFixture(); const user = userEvent.setup();
    await user.click(await screen.findByRole("button", { name: "Show details for customers" }));
    const attributes = await screen.findByRole("table", { name: "Attributes for customers" });
    await user.click(within(attributes).getByRole("checkbox", { name: "Select Attribute 81" }));
    await user.click(screen.getByRole("button", { name: "Run attribute enrichment" }));
    const dialog = screen.getByRole("dialog");
    expect(within(dialog).getByRole("heading", { name: "Enrich attributes" })).toBeVisible();
    expect(within(dialog).queryByText("Object coverage")).not.toBeInTheDocument();
    const submit = within(dialog).getByRole("button", { name: "Run attribute enrichment" });
    await waitFor(() => expect(submit).toBeEnabled()); await user.click(submit);
    await waitFor(() => expect(api.executeMetadataEnrichmentRun).toHaveBeenCalledOnce());
    const command = api.createWorkflowRun.mock.calls[0]![2];
    expect(command.selected_object_ids).toEqual([501]);
    expect(command.description_targets).toEqual([{ object_id: 501, attribute_id: 81, expected_revision: "a".repeat(64) }]);
    expect(command.agent?.model_code).toBe("one-shot");
  });

  it("shows usage on demand and keeps foreign metadata read-only", async () => {
    const api = metadataFixture({ foreign: true }); const user = userEvent.setup();
    const table = await screen.findByRole("table", { name: "Object metadata" });
    expect(within(table).getByRole("button", { name: "Edit" })).toBeDisabled();
    expect(within(table).getByRole("checkbox", { name: "Select Object 501" })).toBeDisabled();
    expect(screen.getByRole("button", { name: "Lock" })).toBeDisabled();
    await user.click(screen.getByRole("button", { name: "Show activity" }));
    expect(screen.queryByRole("region", { name: "Token usage" })).not.toBeInTheDocument();
    await user.click(screen.getByRole("button", { name: "Show run 1048 details" }));
    expect(await screen.findByRole("region", { name: "Token usage" })).toBeVisible();
    expect(api.readMetadataEnrichmentResults).not.toHaveBeenCalled();
    await user.click(screen.getByRole("button", { name: "Hide activity" }));
    expect(screen.getByRole("button", { name: "Show activity" })).toHaveAttribute("aria-expanded", "false");
  });
});

describe("bulk Attribute enrichment selection", () => {
  function detail(id: number, attributeCount = 2, overrides: Partial<ModelInputScopeDetail> = {}): ModelInputScopeDetail {
    return {
      ...scope(id), model_input_scope_id: id, connection_id: 1, system_name: "Customer system",
      source_tenant_name: "Northwind", batch_attribute_name: null, attribute_count: attributeCount,
      total_attribute_count: attributeCount, is_model_input_eligible: true,
      is_logical_mapping_target_eligible: false, is_dimensional_mapping_target_eligible: false,
      created_at: "2026-09-05T12:00:00Z", updated_at: "2026-09-05T12:00:00Z",
      attributes: Array.from({ length: attributeCount }, (_, index) => ({
        attribute_id: id * 10000 + index, attribute_name: `field_${index}`, attribute_ordinal_position: index + 1,
        review_revision: "b".repeat(64), attribute_description: null, attribute_data_type: "STRING",
        attribute_inferred_data_type: null, attribute_nullability: true, is_surrogate_key: false,
        is_natural_key: false, is_meta_data: false, is_masking_required: false, is_mapped: false,
        is_purge: false, is_locked: false, is_active: true,
      })), ...overrides,
    };
  }
  function bulk(objects = [detail(501), detail(502)], options: {
    selected?: number[];
    read?: (tenantId: number, modelId: number, objectId: number) => Promise<ModelInputScopeDetail>;
    execute?: (id: number, mode: "one_shot" | "tool_assisted") => Promise<void>;
    pages?: boolean;
  } = {}) {
    const api = creationApi();
    api.listModelInputScope.mockImplementation(async (_tenant, _model, _filters, _size, cursor) => ({
      model_revision: 18, items: options.pages ? cursor ? objects.slice(1) : objects.slice(0, 1) : objects,
      next_cursor: options.pages && !cursor ? "next-page" : null,
    }));
    const read = vi.fn(options.read ?? (async (_tenant: number, _model: number, id: number) => objects.find((object) => object.object_id === id)!));
    const mounted = setup(<WorkflowRunDialog api={api} tenantId={7} model={model} kind="inference"
      workflow="metadata_enrichment" enrichmentTarget="attribute" readEnrichmentObject={read}
      {...(options.selected ? { initialSelectedIds: options.selected } : {})}
      {...(options.execute ? { executeCreated: options.execute } : {})}
      onClose={vi.fn()} onCreated={vi.fn(async () => undefined)} />);
    return { api, read, ...mounted, user: userEvent.setup() };
  }

  it("loads all Scope pages and preserves exclusions across Back, modes and Object reselection", async () => {
    const locked = detail(503, 1, { is_locked: true });
    const first = detail(501, 3); first.attributes[2]!.is_locked = true;
    const { api, read, user } = bulk([first, detail(502), locked], { pages: true });
    const submit = screen.getByRole("button", { name: "Run attribute enrichment" });
    await waitFor(() => expect(submit).toBeEnabled());
    expect(api.listModelInputScope.mock.calls[1]?.[4]).toBe("next-page");
    expect(read.mock.calls.map((call) => call[2])).toEqual([501, 502]);
    expect(screen.getByRole("checkbox", { name: "Include Object customer_503" })).toBeDisabled();
    expect(screen.getByText("4 Attributes selected across 2 Objects")).toBeVisible();
    await user.click(screen.getByRole("button", { name: "Choose Attributes for customer_501" }));
    expect(screen.getByRole("heading", { name: "customer_501" })).toHaveFocus();
    expect(screen.getByRole("checkbox", { name: "Include Attribute field_2" })).toBeDisabled();
    await user.click(screen.getByRole("checkbox", { name: "Include Attribute field_1" }));
    await user.click(screen.getByRole("button", { name: "Back to Objects" }));
    expect(screen.getByRole("button", { name: "Choose Attributes for customer_501" })).toHaveFocus();
    expect(screen.getByText("1 selected · 2 unselected")).toBeVisible();
    await user.click(screen.getByRole("radio", { name: "Selected Objects" }));
    expect(screen.getByRole("checkbox", { name: "Include Object customer_501" })).toBeChecked();
    expect(screen.getByRole("checkbox", { name: "Include Object customer_502" })).toBeChecked();
    await user.click(screen.getByRole("checkbox", { name: "Include Object customer_501" }));
    await user.click(screen.getByRole("radio", { name: "All unlocked Objects" }));
    expect(screen.getByText("3 Attributes selected across 2 Objects")).toBeVisible();
    await user.click(screen.getByRole("radio", { name: "Selected Objects" }));
    expect(screen.getByRole("checkbox", { name: "Include Object customer_501" })).not.toBeChecked();
    await user.click(screen.getByRole("checkbox", { name: "Include Object customer_501" }));
    await user.click(screen.getByRole("button", { name: "Choose Attributes for customer_502" }));
    await user.click(screen.getByRole("button", { name: "Clear Attribute selection" }));
    await user.click(screen.getByRole("button", { name: "Back to Objects" }));
    expect(screen.getByText("0 selected · 2 unselected")).toBeVisible();
    await user.click(submit);
    expect(api.createWorkflowRun.mock.calls[0]?.[2]).toMatchObject({ selected_object_ids: [501],
      description_targets: [{ object_id: 501, attribute_id: 5010000, expected_revision: "b".repeat(64) }] });
  });

  it("respects page preselection and never changes an empty selection to All", async () => {
    const { api, read, user } = bulk(undefined, { selected: [502] });
    const submit = screen.getByRole("button", { name: "Run attribute enrichment" });
    await waitFor(() => expect(submit).toBeEnabled());
    expect(read.mock.calls.map((call) => call[2])).toEqual([502]);
    expect(screen.getByRole("checkbox", { name: "Include Object customer_501" })).not.toBeChecked();
    await user.click(screen.getByRole("button", { name: "Choose Attributes for customer_502" }));
    await user.click(screen.getByRole("button", { name: "Clear Attribute selection" }));
    expect(submit).toBeDisabled();
    expect(screen.getByText("Select at least one unlocked Attribute to run enrichment.")).toBeVisible();
    await user.click(submit); expect(api.createWorkflowRun).not.toHaveBeenCalled();
  });

  it("keeps locked-only page selection empty and foreign Objects disabled", async () => {
    const { read } = bulk([detail(501), detail(502, 2, { is_locked: true }), detail(503, 2, { source_tenant_id: 8 })], { selected: [502] });
    await screen.findByText("Select at least one unlocked Attribute to run enrichment.");
    expect(screen.getByRole("button", { name: "Run attribute enrichment" })).toBeDisabled();
    expect(screen.getByRole("checkbox", { name: "Include Object customer_502" })).toBeDisabled();
    expect(screen.getByRole("checkbox", { name: "Include Object customer_503" })).toBeDisabled();
    expect(read).not.toHaveBeenCalled();
  });

  it("blocks a partial run after a failed detail and retries only that Object", async () => {
    const objects = [detail(501), detail(502)]; let fail = true;
    const { api, read, user } = bulk(objects, { read: async (_tenant, _model, id) => {
      if (id === 502 && fail) { fail = false; throw new Error("Synthetic failure"); }
      return objects.find((object) => object.object_id === id)!;
    } });
    const retry = await screen.findByRole("button", { name: "Retry Attributes for customer_502" });
    const submit = screen.getByRole("button", { name: "Run attribute enrichment" });
    expect(submit).toBeDisabled(); await user.click(submit); expect(api.createWorkflowRun).not.toHaveBeenCalled();
    await user.click(retry); await waitFor(() => expect(submit).toBeEnabled());
    expect(read.mock.calls.map((call) => call[2])).toEqual([501, 502, 502]);
  });

  it.each(["Object", "Tenant", "revision", "connection", "incomplete", "missing total", "invalid total", "too many Attributes"])(
    "blocks mismatched or incomplete detail: %s", async (failure) => {
      const object = detail(501);
      const broken = { ...object };
      if (failure === "Object") broken.object_id = 502;
      if (failure === "Tenant") broken.source_tenant_id = 8;
      if (failure === "revision") broken.review_revision = "c".repeat(64);
      if (failure === "connection") broken.connection_id = 9;
      if (failure === "incomplete") broken.attributes = [];
      if (failure === "missing total") delete broken.total_attribute_count;
      if (failure === "invalid total") broken.total_attribute_count = 1;
      if (failure === "too many Attributes") Object.assign(broken, detail(501, 2001));
      const { api, user } = bulk([object], { read: async () => broken });
      await screen.findByText(/No partial run will be created/);
      const submit = screen.getByRole("button", { name: "Run attribute enrichment" });
      expect(submit).toBeDisabled(); await user.click(submit); expect(api.createWorkflowRun).not.toHaveBeenCalled();
    },
  );

  it("uses total stored sibling count and drops only Objects with no targets from the context cap", async () => {
    const { api, user } = bulk([detail(501, 2, { total_attribute_count: 3000 }), detail(502, 2, { total_attribute_count: 2500 })]);
    await screen.findByText(/more than 5,000 stored Attributes/);
    const submit = screen.getByRole("button", { name: "Run attribute enrichment" }); expect(submit).toBeDisabled();
    await user.click(screen.getByRole("button", { name: "Choose Attributes for customer_501" }));
    await user.click(screen.getByRole("checkbox", { name: "Include Attribute field_1" }));
    expect(submit).toBeDisabled(); expect(screen.getByText("5500 stored Attributes in context · limit 5,000")).toBeVisible();
    await user.click(screen.getByRole("button", { name: "Clear Attribute selection" }));
    await waitFor(() => expect(submit).toBeEnabled());
    expect(screen.getByText("2500 stored Attributes in context · limit 5,000")).toBeVisible();
    await user.click(submit); expect(api.createWorkflowRun.mock.calls[0]?.[2].selected_object_ids).toEqual([502]);
  });

  it("blocks more than 200 chosen Objects before any detail requests", async () => {
    const { read, user } = bulk(Array.from({ length: 201 }, (_, index) => detail(index + 1, 1)));
    await screen.findByText(/Select up to 200 Objects before loading Attributes/);
    expect(read).not.toHaveBeenCalled();
    await user.click(screen.getByRole("radio", { name: "Selected Objects" }));
    expect(read).not.toHaveBeenCalled();
    await user.click(screen.getByRole("checkbox", { name: "Include Object customer_201" }));
    const submit = screen.getByRole("button", { name: "Run attribute enrichment" });
    await waitFor(() => expect(submit).toBeEnabled(), { timeout: 10000 });
    expect(read).toHaveBeenCalledTimes(200);
    expect(read.mock.calls.some((call) => call[2] === 201)).toBe(false);
  }, 15000);

  it("loads at most four details concurrently and waits even if an in-flight Object is deselected", async () => {
    const objects = Array.from({ length: 5 }, (_, index) => detail(index + 1));
    const resolves = new Map<number, (value: ModelInputScopeDetail) => void>();
    const { read, user } = bulk(objects, { read: (_tenant, _model, id) => new Promise((resolve) => { resolves.set(id, resolve); }) });
    await waitFor(() => expect(read).toHaveBeenCalledTimes(4));
    await user.click(screen.getByRole("radio", { name: "Selected Objects" }));
    await user.click(screen.getByRole("checkbox", { name: "Include Object customer_4" }));
    for (const object of objects.slice(0, 3)) resolves.get(object.object_id)!(object);
    await waitFor(() => expect(read).toHaveBeenCalledTimes(5));
    resolves.get(5)!(objects[4]!);
    await screen.findByText("8 Attributes selected across 4 Objects");
    expect(screen.getByRole("button", { name: "Run attribute enrichment" })).toBeDisabled();
    resolves.get(4)!(objects[3]!);
    await waitFor(() => expect(screen.getByRole("button", { name: "Run attribute enrichment" })).toBeEnabled());
  });

  it("keeps Attribute choices across pages and freezes every selector through start retry", async () => {
    const execute = vi.fn(async () => undefined).mockRejectedValueOnce(new Error("Synthetic start failure"));
    const { api, user } = bulk([detail(501, 51)], { execute });
    await waitFor(() => expect(screen.getByRole("button", { name: "Run attribute enrichment" })).toBeEnabled());
    await user.click(screen.getByRole("button", { name: "Choose Attributes for customer_501" }));
    await user.click(screen.getByRole("button", { name: "Next Attributes" }));
    await user.click(screen.getByRole("checkbox", { name: "Include Attribute field_50" }));
    await user.click(screen.getByRole("button", { name: "Previous Attributes" }));
    await user.click(screen.getByRole("button", { name: "Run attribute enrichment" }));
    const retry = await screen.findByRole("button", { name: "Retry start" });
    for (const control of [...screen.getAllByRole("checkbox"), ...screen.getAllByRole("radio"), ...screen.getAllByRole("combobox")]) expect(control).toBeDisabled();
    expect(screen.getByRole("button", { name: "Back to Objects" })).toBeDisabled();
    expect(screen.getByRole("button", { name: "Next Attributes" })).toBeDisabled();
    await user.click(retry);
    await waitFor(() => expect(execute).toHaveBeenCalledTimes(2));
    expect(api.createWorkflowRun).toHaveBeenCalledOnce();
    expect(api.createWorkflowRun.mock.calls[0]?.[2].description_targets).toHaveLength(50);
  });
});
