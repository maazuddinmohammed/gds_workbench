import { describe, expect, it, vi } from "vitest";

import { createHttpRequest } from "../../core/http";
import { createAnalysisApi } from "./api";

describe("Analysis HTTP adapter", () => {
  it("owns exact filtered collection and detail read transports", async () => {
    const fetcher = vi.fn<typeof fetch>().mockImplementation(async () => jsonResponse({}));
    const api = createAnalysisApi(createHttpRequest(fetcher));

    await api.listAnalysisFindings(7, 18, {
      objectId: 501,
      validationState: "unvalidated",
      status: "inactive",
      locked: false,
      showInactive: true,
    }, 25, "opaque+/=");
    await api.listAnalysisFindings(7, 18);
    await api.readAnalysisFinding(7, 18, 81);

    expect(fetcher.mock.calls.map(([input]) => String(input))).toEqual([
      "/api/v1/tenants/7/models/18/analysis?object_id=501&validation_state=unvalidated&status=inactive&locked=false&show_inactive=true&page_size=25&cursor=opaque%2B%2F%3D",
      "/api/v1/tenants/7/models/18/analysis?page_size=200",
      "/api/v1/tenants/7/models/18/analysis/81",
    ]);
    for (const [, init] of fetcher.mock.calls) {
      expect(init).toEqual({
        cache: "no-store",
        credentials: "same-origin",
        headers: { accept: "application/json" },
      });
    }
  });

  it("sends selected review actions with the Model revision and idempotency key", async () => {
    const fetcher = vi.fn<typeof fetch>().mockResolvedValue(jsonResponse({ action_count: 1 }));
    const api = createAnalysisApi(createHttpRequest(fetcher));
    const command = { record_ids: [81], action: "unlock" as const, expected_model_revision: 18 };
    await api.reviewAnalysisFindings(7, 18, command, "11111111-1111-4111-8111-111111111111");

    expect(fetcher).toHaveBeenCalledWith("/api/v1/tenants/7/models/18/change-sets/review", {
      method: "POST",
      cache: "no-store",
      credentials: "same-origin",
      headers: {
        accept: "application/json",
        "content-type": "application/json",
        "Idempotency-Key": "11111111-1111-4111-8111-111111111111",
      },
      body: JSON.stringify({ dataset: "analysis_result", ...command }),
    });
  });
});

function jsonResponse(payload: unknown): Response {
  return new Response(JSON.stringify(payload), {
    headers: { "content-type": "application/json" },
  });
}
