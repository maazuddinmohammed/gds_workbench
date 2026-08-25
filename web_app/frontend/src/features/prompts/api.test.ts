import { describe, expect, it, vi } from "vitest";

import { createHttpRequest } from "../../core/http";
import { createPromptsApi } from "./api";

describe("Prompts HTTP adapter", () => {
  it("owns exact catalog, normalized library, detail, and assignment reads", async () => {
    const fetcher = vi.fn<typeof fetch>().mockImplementation(async () => jsonResponse({ items: [] }));
    const api = createPromptsApi(createHttpRequest(fetcher));

    await api.listPromptStages(7);
    await api.listPromptTemplates(7, {
      workflow: "logical",
      mode: "tool_assisted",
      stageCode: " Entity_Review ",
      status: "published",
    }, 25, "opaque-next");
    await api.listPromptTemplates(7);
    await api.readPromptTemplate(7, 31);
    await api.listModelPromptAssignments(7, 18);

    expect(fetcher.mock.calls.map(([input]) => String(input))).toEqual([
      "/api/v1/tenants/7/prompts/stages",
      "/api/v1/tenants/7/prompts/templates?workflow=logical&mode=tool_assisted&stage_code=entity_review&status=published&page_size=25&cursor=opaque-next",
      "/api/v1/tenants/7/prompts/templates?page_size=50",
      "/api/v1/tenants/7/prompts/templates/31",
      "/api/v1/tenants/7/prompts/models/18/assignments",
    ]);
    for (const [, init] of fetcher.mock.calls) {
      expect(init).toEqual({
        cache: "no-store",
        credentials: "same-origin",
        headers: { accept: "application/json" },
      });
    }
  });

  it("owns governed mutations and keeps Prompt bodies out of URLs", async () => {
    const fetcher = vi.fn<typeof fetch>().mockImplementation(async () => jsonResponse({}));
    const api = createPromptsApi(createHttpRequest(fetcher));

    await api.createPromptTemplate(7, {
      workflow_stage_id: 4,
      prompt_template_ownership_scope: "tenant",
      prompt_template_code: "logical.entity_review",
      prompt_template_name: "Entity review",
      prompt_template_description: null,
      is_active: true,
    });
    await api.updatePromptTemplate(7, 31, {
      prompt_template_name: "Entity review v2",
      prompt_template_description: "Governed review",
      is_active: true,
      expected_updated_at: "2026-08-24T12:00:00Z",
    });
    await api.savePromptDraft(7, 31, {
      expected_prompt_template_version_id: 91,
      expected_updated_at: "2026-08-24T12:00:00Z",
      system_prompt_template: "system-body-sentinel",
      instruction_prompt_template: "instruction-body-sentinel",
      tool_instruction_prompt_template: null,
    });
    await api.publishPromptVersion(7, 31, 91);
    await api.retirePromptVersion(7, 31, 91);
    await api.setModelPromptAssignment(7, 18, 4, {
      prompt_template_version_id: 91,
      expected_prompt_assignment_id: null,
    });

    expect(fetcher.mock.calls.map(([input]) => String(input))).toEqual([
      "/api/v1/tenants/7/prompts/templates",
      "/api/v1/tenants/7/prompts/templates/31",
      "/api/v1/tenants/7/prompts/templates/31/draft",
      "/api/v1/tenants/7/prompts/templates/31/versions/91/publish",
      "/api/v1/tenants/7/prompts/templates/31/versions/91/retire",
      "/api/v1/tenants/7/prompts/models/18/assignments/4",
    ]);
    expect(fetcher.mock.calls.map(([, init]) => init?.method)).toEqual([
      "POST",
      "PUT",
      "PUT",
      "POST",
      "POST",
      "PUT",
    ]);
    expect(String(fetcher.mock.calls[2]?.[1]?.body)).toContain("system_prompt_template");
    expect(fetcher.mock.calls.map(([input]) => String(input)).join(" ")).not.toContain(
      "body-sentinel",
    );
    expect(JSON.stringify(fetcher.mock.calls)).not.toContain("claim_token");
  });
});

function jsonResponse(payload: unknown): Response {
  return new Response(JSON.stringify(payload), {
    headers: { "content-type": "application/json" },
  });
}
