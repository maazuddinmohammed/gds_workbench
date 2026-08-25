import { describe, expect, it } from "vitest";

import type { HttpRequest } from "../../core/http";
import { createTenantsApi } from "./api";

describe("Tenant entry HTTP adapter", () => {
  it("owns the exact Session, Tenant chooser, selection, and Home transport", async () => {
    const calls: Array<[path: string, init: RequestInit | undefined]> = [];
    const request: HttpRequest = async <T>(path: string, init?: RequestInit) => {
      calls.push([path, init]);
      return {} as T;
    };
    const api = createTenantsApi(request);

    await api.readSession();
    await api.listTenants();
    await api.selectTenant(7);
    await api.readTenantHome(7);

    expect(calls).toEqual([
      ["/api/v1/session", undefined],
      ["/api/v1/tenants?page_size=200", undefined],
      ["/api/v1/tenants/7/select", { method: "POST" }],
      ["/api/v1/tenants/7/home", undefined],
    ]);
  });
});
