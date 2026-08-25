import { describe, expect, it, vi } from "vitest";

import { createHttpRequest } from "../../core/http";
import { createWorkflowsApi } from "./api";

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
      workflow_execution_mode: "tool_assisted" as const,
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
    await api.executeProfilingRun(7, 18, 1048, 18);
    await api.executeConceptualRun(7, 18, 1049, "one_shot", 18);
    await api.executeLogicalRun(7, 18, 1050, "tool_assisted", 18);
    await api.executeDimensionalRun(7, 18, 1051, "detailed_coverage", 18);
    await api.executeMappingRun(7, 18, 1052, "tool_assisted", 18);
    await api.executeCodeGenerationRun(7, 18, 1053, 18);

    expect(fetcher.mock.calls.map(([input]) => String(input))).toEqual([
      "/api/v1/tenants/7/models/18/runs",
      "/api/v1/tenants/7/models/18/profiling/runs/1048/execute",
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
    expect(fetcher.mock.calls[1]?.[1]?.body).toBe(JSON.stringify({
      expected_model_revision: 18,
    }));
    expect(fetcher.mock.calls[2]?.[1]?.body).toBe(JSON.stringify({
      execution_mode: "one_shot",
      expected_model_revision: 18,
    }));
    expect(fetcher.mock.calls[3]?.[1]?.body).toBe(JSON.stringify({
      execution_mode: "tool_assisted",
      expected_model_revision: 18,
    }));
    expect(fetcher.mock.calls[4]?.[1]?.body).toBe(JSON.stringify({
      execution_mode: "detailed_coverage",
      expected_model_revision: 18,
    }));
    expect(fetcher.mock.calls[5]?.[1]?.body).toBe(JSON.stringify({
      execution_mode: "tool_assisted",
      expected_model_revision: 18,
    }));
    expect(fetcher.mock.calls[6]?.[1]?.body).toBe(JSON.stringify({
      expected_model_revision: 18,
    }));
  });
});

function jsonResponse(payload: unknown): Response {
  return new Response(JSON.stringify(payload), {
    headers: { "content-type": "application/json" },
  });
}
