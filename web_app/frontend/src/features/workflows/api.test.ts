import { describe, expect, it, vi } from "vitest";

import { createHttpRequest } from "../../core/http";
import {
  createWorkflowsApi,
  listCompatibleExecutionModes,
  reasoningEffortDisplayName,
  resolveAgentProfileSelection,
  resolveDefaultAgent,
  type AgentCapabilities,
} from "./api";

describe("Workflow HTTP adapter", () => {
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
    await api.executeDimensionalRun(7, 18, 1051, "detailed_coverage", 18);
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
      execution_mode: "detailed_coverage",
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

describe("Agent capability defaults", () => {
  it("distinguishes an omitted reasoning parameter from explicitly disabled reasoning", () => {
    expect(reasoningEffortDisplayName({ code: "default", name: "Default" }))
      .toBe("Provider default (omit setting)");
    expect(reasoningEffortDisplayName({ code: "none", name: "None" }))
      .toBe("None (explicitly disable reasoning)");
  });

  it("derives modes from the selected SDK and provider, then repairs dependent fields", () => {
    const capabilities: AgentCapabilities = {
      schema_version: "3.0",
      sdks: [
        { code: "sdk-a", name: "SDK A", provider_codes: ["provider-a", "provider-b"] },
        { code: "sdk-b", name: "SDK B", provider_codes: ["provider-b"] },
      ],
      providers: [
        { code: "provider-a", name: "Provider A" },
        { code: "provider-b", name: "Provider B" },
      ],
      models: [
        {
          code: "broad",
          name: "Broad",
          provider_code: "provider-a",
          deployment_name: "provider-a-broad",
          execution_profiles: [
            {
              sdk_code: "sdk-a",
              execution_mode: "one_shot",
              reasoning_effort_codes: ["low"],
            },
            {
              sdk_code: "sdk-a",
              execution_mode: "detailed_coverage",
              reasoning_effort_codes: ["high"],
            },
          ],
        },
        {
          code: "paged",
          name: "Paged",
          provider_code: "provider-a",
          deployment_name: "provider-a-paged",
          execution_profiles: [{
            sdk_code: "sdk-a",
            execution_mode: "tool_assisted",
            reasoning_effort_codes: ["none"],
          }],
        },
        {
          code: "secondary",
          name: "Secondary",
          provider_code: "provider-b",
          deployment_name: "provider-b-model",
          execution_profiles: [{
            sdk_code: "sdk-b",
            execution_mode: "one_shot",
            reasoning_effort_codes: ["low"],
          }],
        },
      ],
      reasoning_efforts: [
        { code: "none", name: "Default" },
        { code: "low", name: "Low" },
        { code: "high", name: "High" },
      ],
      max_turns: { minimum: 1, default: 10, maximum: 50 },
      validation_retries: { minimum: 0, default: 2, maximum: 5 },
    };

    expect(listCompatibleExecutionModes(capabilities, "sdk-a", "provider-a"))
      .toEqual(["one_shot", "tool_assisted", "detailed_coverage"]);
    expect(listCompatibleExecutionModes(capabilities, "sdk-a", "provider-b")).toEqual([]);
    expect(resolveAgentProfileSelection(capabilities, "tool_assisted", {
      sdkCode: "sdk-a",
      providerCode: "provider-a",
      modelCode: "broad",
      reasoningEffortCode: "low",
    })).toEqual({
      executionMode: "tool_assisted",
      sdkCode: "sdk-a",
      providerCode: "provider-a",
      modelCode: "paged",
      reasoningEffortCode: "none",
    });
    expect(resolveAgentProfileSelection(capabilities, "tool_assisted", {
      sdkCode: "sdk-b",
      providerCode: "provider-b",
      modelCode: "paged",
      reasoningEffortCode: "none",
    })).toEqual({
      executionMode: "one_shot",
      sdkCode: "sdk-b",
      providerCode: "provider-b",
      modelCode: "secondary",
      reasoningEffortCode: "low",
    });
  });

  it("chooses only a model profile compatible with the effective execution mode", () => {
    const capabilities: AgentCapabilities = {
      schema_version: "3.0",
      sdks: [{
        code: "openai_agents_sdk",
        name: "OpenAI Agents SDK",
        provider_codes: ["databricks"],
      }],
      providers: [{ code: "databricks", name: "Databricks Model Serving" }],
      models: [
        {
          code: "one-shot-only",
          name: "One-shot deployment",
          provider_code: "databricks",
          deployment_name: "model-a",
          execution_profiles: [{
            sdk_code: "openai_agents_sdk",
            execution_mode: "one_shot",
            reasoning_effort_codes: ["low"],
          }],
        },
        {
          code: "scalable",
          name: "Scalable deployment",
          provider_code: "databricks",
          deployment_name: "model-b",
          execution_profiles: [{
            sdk_code: "openai_agents_sdk",
            execution_mode: "tool_assisted",
            reasoning_effort_codes: ["medium", "high"],
          }],
        },
      ],
      reasoning_efforts: [
        { code: "low", name: "Low" },
        { code: "medium", name: "Medium" },
        { code: "high", name: "High" },
      ],
      max_turns: { minimum: 1, default: 10, maximum: 50 },
      validation_retries: { minimum: 0, default: 2, maximum: 5 },
    };

    expect(resolveDefaultAgent(capabilities, "tool_assisted", {
      sdkCode: "openai_agents_sdk",
      providerCode: "databricks",
      modelCode: "one-shot-only",
      reasoningEffortCode: "low",
      maxTurns: null,
      validationRetryCount: null,
    })).toEqual({
      sdk_code: "openai_agents_sdk",
      provider_code: "databricks",
      model_code: "scalable",
      reasoning_effort_code: "medium",
      max_turns: 10,
      validation_retry_count: 2,
    });
  });

  it("returns null when no deployment supports the effective execution mode", () => {
    const capabilities: AgentCapabilities = {
      schema_version: "3.0",
      sdks: [{ code: "sdk", name: "SDK", provider_codes: ["provider"] }],
      providers: [{ code: "provider", name: "Provider" }],
      models: [{
        code: "model",
        name: "Model",
        provider_code: "provider",
        deployment_name: "model-a",
        execution_profiles: [{
          sdk_code: "sdk",
          execution_mode: "one_shot",
          reasoning_effort_codes: ["medium"],
        }],
      }],
      reasoning_efforts: [{ code: "medium", name: "Medium" }],
      max_turns: { minimum: 1, default: 10, maximum: 50 },
      validation_retries: { minimum: 0, default: 2, maximum: 5 },
    };

    expect(resolveDefaultAgent(capabilities, "detailed_coverage", {
      sdkCode: null,
      providerCode: null,
      modelCode: null,
      reasoningEffortCode: null,
      maxTurns: null,
      validationRetryCount: null,
    })).toBeNull();
  });
});

function jsonResponse(payload: unknown): Response {
  return new Response(JSON.stringify(payload), {
    headers: { "content-type": "application/json" },
  });
}
