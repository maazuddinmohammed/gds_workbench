import { describe, expect, it, vi } from "vitest";

import { createHttpRequest } from "../../core/http";
import { createQAApi } from "./api";

describe("QA HTTP adapter", () => {
  it("owns exact bounded System and applied ledger reads", async () => {
    const fetcher = vi.fn<typeof fetch>().mockImplementation(async () => jsonResponse({}));
    const api = createQAApi(createHttpRequest(fetcher));

    await api.listQAEligibleSystems(7, 18);
    await api.readQALedger(7, 18);

    expect(fetcher.mock.calls.map(([input]) => String(input))).toEqual([
      "/api/v1/tenants/7/models/18/qa/systems",
      "/api/v1/tenants/7/models/18/qa/ledger",
    ]);
    for (const [, init] of fetcher.mock.calls) {
      expect(init).toEqual({
        cache: "no-store",
        credentials: "same-origin",
        headers: { accept: "application/json" },
      });
    }
  });
});

function jsonResponse(payload: unknown): Response {
  return new Response(JSON.stringify(payload), {
    headers: { "content-type": "application/json" },
  });
}
