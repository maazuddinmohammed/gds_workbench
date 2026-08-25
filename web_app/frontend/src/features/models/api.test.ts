import { describe, expect, it } from "vitest";

import type { HttpRequest } from "../../core/http";
import { createModelsApi } from "./api";

describe("Models HTTP adapter", () => {
  it("owns the exact Model ledger, detail, and overview transport", async () => {
    const calls: Array<[path: string, init: RequestInit | undefined]> = [];
    const request: HttpRequest = async <T>(path: string, init?: RequestInit) => {
      calls.push([path, init]);
      return {} as T;
    };
    const api = createModelsApi(request);

    await api.listModels(7, "active");
    await api.listModels(7, "archived", 50, "opaque-next");
    await api.readModel(7, 18);
    await api.readModelOverview(7, 18);

    expect(calls).toEqual([
      ["/api/v1/tenants/7/models?status=active&page_size=200", undefined],
      [
        "/api/v1/tenants/7/models?status=archived&page_size=50&cursor=opaque-next",
        undefined,
      ],
      ["/api/v1/tenants/7/models/18", undefined],
      ["/api/v1/tenants/7/models/18/overview", undefined],
    ]);
  });
});
