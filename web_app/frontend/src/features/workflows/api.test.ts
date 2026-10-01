import { describe, expect, it, vi } from "vitest";

import { createHttpRequest } from "../../core/http";
import {
  createWorkflowsApi,
  listCompatibleExecutionModes,
  loadWorkflowScope,
  reasoningEffortDisplayName,
  resolveAgentProfileSelection,
  resolveDefaultAgent,
  type AgentCapabilities,
} from "./api";

describe("Workflow HTTP adapter", () => {
  it("cancels exactly the selected Tenant, Model and run", async () => {
    const fetcher = vi.fn<typeof fetch>(async () => jsonResponse({ workflow_run_state: "cancelled" }));
    const api = createWorkflowsApi(createHttpRequest(fetcher));
    await api.cancelWorkflowRun(7, 18, 1048);
    expect(fetcher).toHaveBeenCalledExactlyOnceWith(
      "/api/v1/tenants/7/models/18/runs/1048/cancel", expect.objectContaining({ method: "POST" }),
    );
  });
  it("fetches generated records for an explicitly selected draft dataset", async () => {
    const fetcher = vi.fn<typeof fetch>().mockImplementation(async () => jsonResponse({}));
    const api = createWorkflowsApi(createHttpRequest(fetcher));
    await api.readWorkflowDraftReview(7, 18, "aaaaaaaa-aaaa-aaaa-aaaa-aaaaaaaaaaaa", "conceptual_object");
    expect(String(fetcher.mock.calls[0]?.[0])).toBe(
      "/api/v1/tenants/7/models/18/change-sets/aaaaaaaa-aaaa-aaaa-aaaa-aaaaaaaaaaaa?dataset=conceptual_object",
    );
  });
  it("owns exact capabilities and Workflow Run read transports", async () => {
    const fetcher = vi.fn<typeof fetch>().mockImplementation(async () => jsonResponse({}));
    const api = createWorkflowsApi(createHttpRequest(fetcher));

    await api.readAgentCapabilities();
    await api.listWorkflowRuns(7, 18, "analysis", "running", 25, "opaque+/=");
    await api.listWorkflowRuns(7, 18, "profiling");
    await api.readWorkflowRun(7, 18, 1048);
    await api.listWorkflowRunEvents(7, 18, 1048);
    await api.listWorkflowRunEvents(7, 18, 1048, 7);

    expect(fetcher.mock.calls.map(([input]) => String(input))).toEqual([
      "/api/v1/config/agent-capabilities",
      "/api/v1/tenants/7/models/18/runs?workflow=analysis&page_size=25&state=running&cursor=opaque%2B%2F%3D",
      "/api/v1/tenants/7/models/18/runs?workflow=profiling&page_size=200",
      "/api/v1/tenants/7/models/18/runs/1048",
      "/api/v1/tenants/7/models/18/runs/1048/events?after_sequence=0&page_size=200",
      "/api/v1/tenants/7/models/18/runs/1048/events?after_sequence=7&page_size=200",
    ]);
    for (const [, init] of fetcher.mock.calls) {
      expect(init).toEqual({
        cache: "no-store",
        credentials: "same-origin",
        headers: { accept: "application/json" },
      });
    }
  });

  it("owns exact general creation and explicit execution transports", async () => {
    const fetcher = vi.fn<typeof fetch>().mockImplementation(async () => jsonResponse({}));
    const api = createWorkflowsApi(createHttpRequest(fetcher));
    const idempotencyKey = "bbbbbbbb-bbbb-bbbb-bbbb-bbbbbbbbbbbb";
    const command = {
      expected_model_revision: 18,
      model_workflow: "analysis" as const,
      workflow_execution_mode: "one_shot" as const,
      selected_object_ids: [501],
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
    };

    await api.createWorkflowRun(7, 18, command, idempotencyKey);
    await api.readWorkflowDraftReview(7, 18, "aaaaaaaa-aaaa-aaaa-aaaa-aaaaaaaaaaaa");
    await api.applyWorkflowDraft(7, 18, 1047, 18, 2, "d".repeat(64), idempotencyKey);
    await api.executeProfilingRun(7, 18, 1048, 18);
    await api.executeAnalysisInferenceRun(7, 18, 1054, "tool_assisted", 18);
    await api.executeAnalysisValidationRun(7, 18, 1055, 18);
    await api.executeConceptualRun(7, 18, 1049, "one_shot", 18);
    await api.executeLogicalRun(7, 18, 1050, "tool_assisted", 18);
    await api.executeDimensionalRun(7, 18, 1051, "one_shot", 18);
    await api.executeMappingRun(7, 18, 1052, "tool_assisted", 18);
    await api.executeCodeGenerationRun(7, 18, 1053, 18);

    expect(fetcher.mock.calls.map(([input]) => String(input))).toEqual([
      "/api/v1/tenants/7/models/18/runs",
      "/api/v1/tenants/7/models/18/change-sets/aaaaaaaa-aaaa-aaaa-aaaa-aaaaaaaaaaaa",
      "/api/v1/tenants/7/models/18/runs/1047/draft/apply",
      "/api/v1/tenants/7/models/18/profiling/runs/1048/execute",
      "/api/v1/tenants/7/models/18/analysis/inference-runs/1054/execute",
      "/api/v1/tenants/7/models/18/analysis/validation-runs/1055/execute",
      "/api/v1/tenants/7/models/18/conceptual/runs/1049/execute",
      "/api/v1/tenants/7/models/18/logical/runs/1050/execute",
      "/api/v1/tenants/7/models/18/dimensional/runs/1051/execute",
      "/api/v1/tenants/7/models/18/mapping/runs/1052/execute",
      "/api/v1/tenants/7/models/18/code-generation/runs/1053/execute",
    ]);
    expect(fetcher.mock.calls[0]?.[1]).toEqual({
      method: "POST",
      cache: "no-store",
      credentials: "same-origin",
      headers: {
        accept: "application/json",
        "content-type": "application/json",
        "Idempotency-Key": idempotencyKey,
      },
      body: JSON.stringify(command),
    });
    expect(fetcher.mock.calls[1]?.[1]).toEqual({
      cache: "no-store",
      credentials: "same-origin",
      headers: { accept: "application/json" },
    });
    expect(fetcher.mock.calls[2]?.[1]).toEqual({
      method: "POST",
      cache: "no-store",
      credentials: "same-origin",
      headers: {
        accept: "application/json",
        "content-type": "application/json",
        "Idempotency-Key": idempotencyKey,
      },
      body: JSON.stringify({
        expected_model_revision: 18,
        expected_draft_revision: 2,
        expected_candidate_digest: "d".repeat(64),
      }),
    });
    expect(fetcher.mock.calls[3]?.[1]?.body).toBe(JSON.stringify({
      expected_model_revision: 18,
    }));
    expect(fetcher.mock.calls[4]?.[1]?.body).toBe(JSON.stringify({
      execution_mode: "tool_assisted",
      expected_model_revision: 18,
    }));
    expect(fetcher.mock.calls[5]?.[1]?.body).toBe(JSON.stringify({
      expected_model_revision: 18,
    }));
    expect(fetcher.mock.calls[6]?.[1]?.body).toBe(JSON.stringify({
      execution_mode: "one_shot",
      expected_model_revision: 18,
    }));
    expect(fetcher.mock.calls[7]?.[1]?.body).toBe(JSON.stringify({
      execution_mode: "tool_assisted",
      expected_model_revision: 18,
    }));
    expect(fetcher.mock.calls[8]?.[1]?.body).toBe(JSON.stringify({
      execution_mode: "one_shot",
      expected_model_revision: 18,
    }));
    expect(fetcher.mock.calls[9]?.[1]?.body).toBe(JSON.stringify({
      execution_mode: "tool_assisted",
      expected_model_revision: 18,
    }));
    expect(fetcher.mock.calls[10]?.[1]?.body).toBe(JSON.stringify({
      expected_model_revision: 18,
    }));
  });
});

describe.each([
  ["bronze", { zone: "bronze" }, "Bronze"],
  ["enrichment", {}, "Source and Bronze"],
] as const)("Workflow scope: %s", (scope, filters, zoneName) => {
  const object = {
    object_id: 501,
    system_id: 9,
    system_code: "CRM",
    source_tenant_code: "TENANT",
    object_name: "customers",
    zone_code: "bronze" as const,
    batch_attribute_name: "batch_id",
  };

  it("loads complete ordered pages, preserves item fields, and applies only its scope filter", async () => {
    const second = { ...object, object_id: 502, };
    const third = { ...object, object_id: 503 };
    const listModelInputScope = vi.fn(async () => ({
      model_revision: 18, items: [third], next_cursor: null as string | null,
    }))
      .mockResolvedValueOnce({ model_revision: 18, items: [object, second], next_cursor: "page+/=" })
      .mockResolvedValueOnce({ model_revision: 18, items: [], next_cursor: "page-3" });

    const result = await loadWorkflowScope({ listModelInputScope }, 7, 18, scope);

    expect(result).toEqual({ modelRevision: 18, items: [object, second, third] });
    expect(result.items[0]?.batch_attribute_name).toBe("batch_id");
    expect(listModelInputScope.mock.calls).toEqual([
      [7, 18, filters, 200, undefined],
      [7, 18, filters, 200, "page+/="],
      [7, 18, filters, 200, "page-3"],
    ]);
  });

  it("returns the first page revision for an empty scope", async () => {
    const listModelInputScope = vi.fn(async () => ({ model_revision: 19, items: [], next_cursor: null }));
    await expect(loadWorkflowScope({ listModelInputScope }, 7, 18, scope))
      .resolves.toEqual({ modelRevision: 19, items: [] });
    expect(listModelInputScope).toHaveBeenCalledTimes(1);
  });

  it.each([
    ["revision", "Model Input Scope revision changed while loading"],
    ["cursor", "Model Input Scope cursor repeated"],
  ])("rejects %s drift without returning a partial scope", async (drift, message) => {
    const listModelInputScope = vi.fn(async () => ({
      model_revision: drift === "revision" ? 19 : 18,
      items: [object],
      next_cursor: drift === "cursor" ? "repeated" : null,
    })).mockResolvedValueOnce({ model_revision: 18, items: [object], next_cursor: "repeated" });

    await expect(loadWorkflowScope({ listModelInputScope }, 7, 18, scope)).rejects.toThrow(message);
    expect(listModelInputScope).toHaveBeenCalledTimes(2);
  });

  it("accepts a complete final page at the selection limit", async () => {
    let pagesRead = 0;
    const listModelInputScope = vi.fn(async () => ({
      model_revision: 18,
      items: [object],
      next_cursor: ++pagesRead < 250 ? String(pagesRead) : null,
    }));

    const result = await loadWorkflowScope({ listModelInputScope }, 7, 18, scope);
    expect(result.items).toHaveLength(250);
    expect(listModelInputScope).toHaveBeenCalledTimes(250);
  });

  it("rejects continuation past the selection limit with its existing label", async () => {
    let pagesRead = 0;
    const listModelInputScope = vi.fn(async () => ({
      model_revision: 18, items: [object], next_cursor: String(++pagesRead),
    }));

    await expect(loadWorkflowScope({ listModelInputScope }, 7, 18, scope))
      .rejects.toThrow(`Active ${zoneName} Scope exceeds the supported bounded selection`);
    expect(listModelInputScope).toHaveBeenCalledTimes(250);
  });
});

describe("Foundry agent selection", () => {
  const capabilities: AgentCapabilities = {
    schema_version: "3.0",
    sdks: [
      { code: "langchain_create_agent", name: "Retired SDK", provider_codes: ["databricks", "microsoft_foundry"] },
      { code: "openai_agents_sdk", name: "OpenAI Agents SDK", provider_codes: ["microsoft_foundry", "databricks"] },
    ],
    providers: [{ code: "databricks", name: "Retired provider" }, { code: "microsoft_foundry", name: "Microsoft Foundry" }],
    models: [
      { code: "retired-provider", name: "Retired provider", provider_code: "databricks", deployment_name: "legacy",
        execution_profiles: [{ sdk_code: "openai_agents_sdk", execution_mode: "tool_assisted", reasoning_effort_codes: ["high"] }] },
      { code: "retired-sdk", name: "Retired SDK", provider_code: "microsoft_foundry", deployment_name: "legacy",
        execution_profiles: [{ sdk_code: "langchain_create_agent", execution_mode: "tool_assisted", reasoning_effort_codes: ["high"] }] },
      { code: "broad", name: "Broad", provider_code: "microsoft_foundry", deployment_name: "broad",
        execution_profiles: [
          { sdk_code: "openai_agents_sdk", execution_mode: "one_shot", reasoning_effort_codes: ["default", "none"] },
        ] },
      { code: "paged", name: "Paged", provider_code: "microsoft_foundry", deployment_name: "paged",
        execution_profiles: [{ sdk_code: "openai_agents_sdk", execution_mode: "tool_assisted", reasoning_effort_codes: ["medium", "high"] }] },
    ],
    reasoning_efforts: ["default", "none", "medium", "high"].map((code) => ({ code, name: code })),
    max_turns: { minimum: 1, default: 10, maximum: 50 },
    validation_retries: { minimum: 0, default: 2, maximum: 5 },
  };

  it("keeps model default and explicitly disabled reasoning distinct", () => {
    expect(reasoningEffortDisplayName({ code: "default", name: "Default" })).toBe("Model default");
    expect(reasoningEffortDisplayName({ code: "none", name: "None" })).toBe("None");
    expect(resolveAgentProfileSelection(capabilities, "one_shot", {
      modelCode: "broad", reasoningEffortCode: "none",
    })).toEqual({ executionMode: "one_shot", modelCode: "broad", reasoningEffortCode: "none" });
  });

  it.each(["retired-provider", "retired-sdk", "removed-model"])("ignores retired selection %s while preserving the workflow mode", (modelCode) => {
    expect(listCompatibleExecutionModes(capabilities)).toEqual(["one_shot", "tool_assisted"]);
    expect(resolveAgentProfileSelection(capabilities, "tool_assisted", {
      modelCode, reasoningEffortCode: "retired-effort",
    })).toEqual({ executionMode: "tool_assisted", modelCode: "paged", reasoningEffortCode: "medium" });
  });

  it("repairs dependent model and effort when the selected mode changes", () => {
    expect(resolveAgentProfileSelection(capabilities, "one_shot", {
      modelCode: "paged", reasoningEffortCode: "medium",
    })).toEqual({ executionMode: "one_shot", modelCode: "broad", reasoningEffortCode: "default" });
  });

  it.each([
    [8, 0, 8, 0], [null, null, 10, 2], [0, -1, 10, 2],
    [51, 6, 10, 2], [1.5, 1.5, 10, 2], [Number.NaN, Number.NaN, 10, 2],
  ])("resolves hidden limits without clamping: %s / %s", (maxTurns, validationRetryCount, expectedTurns, expectedRetries) => {
    expect(resolveDefaultAgent(capabilities, "tool_assisted", {
      modelCode: "retired-provider", reasoningEffortCode: "high", maxTurns, validationRetryCount,
    })).toEqual({ sdk_code: "openai_agents_sdk", provider_code: "microsoft_foundry",
      model_code: "paged", reasoning_effort_code: "high", max_turns: expectedTurns, validation_retry_count: expectedRetries });
  });

  it("never changes a fixed workflow mode to use an incompatible model", () => {
    const toolOnly = { ...capabilities, models: capabilities.models.filter((model) => model.code === "paged") };
    expect(resolveDefaultAgent(toolOnly, "one_shot", {
      modelCode: "paged", reasoningEffortCode: "medium", maxTurns: 8, validationRetryCount: 1,
    })).toBeNull();
    expect(resolveAgentProfileSelection(toolOnly, "one_shot", {
      modelCode: "paged", reasoningEffortCode: "medium",
    }, ["one_shot"])).toBeNull();
  });

  it("does not offer unsupported or unregistered provider, SDK or reasoning profiles", () => {
    expect(listCompatibleExecutionModes({ ...capabilities, sdks: [] })).toEqual([]);
    expect(listCompatibleExecutionModes({ ...capabilities, providers: [] })).toEqual([]);
    expect(listCompatibleExecutionModes({ ...capabilities, reasoning_efforts: [] })).toEqual([]);
    expect(listCompatibleExecutionModes({ ...capabilities, models: capabilities.models.slice(0, 2) })).toEqual([]);
  });
});

function jsonResponse(payload: unknown): Response {
  return new Response(JSON.stringify(payload), {
    headers: { "content-type": "application/json" },
  });
}
