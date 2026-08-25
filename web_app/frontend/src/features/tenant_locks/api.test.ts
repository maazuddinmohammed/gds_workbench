import { describe, expect, it } from "vitest";

import type { HttpRequest } from "../../core/http";
import { createTenantLockApi } from "./api";

describe("Tenant Lock HTTP adapter", () => {
  it("owns the exact command and bounded history transport", async () => {
    const calls: Array<[path: string, init: RequestInit | undefined]> = [];
    const request: HttpRequest = async <T>(path: string, init?: RequestInit) => {
      calls.push([path, init]);
      return {} as T;
    };
    const api = createTenantLockApi(request);

    await api.acquireTenantLock(7, {
      duration_minutes: 90,
      purpose: "Metadata review",
    });
    await api.renewTenantLock(7, { duration_minutes: 120 });
    await api.releaseTenantLock(7);
    await api.overrideTenantLock(7, { reason: "Incident 4821 access recovery" });
    await api.listTenantLockHistory(7);
    await api.listTenantLockHistory(7, "opaque-next");

    expect(calls).toEqual([
      ["/api/v1/tenants/7/lock/acquire", {
        method: "POST",
        headers: { "content-type": "application/json" },
        body: JSON.stringify({
          duration_minutes: 90,
          purpose: "Metadata review",
        }),
      }],
      ["/api/v1/tenants/7/lock/renew", {
        method: "POST",
        headers: { "content-type": "application/json" },
        body: JSON.stringify({ duration_minutes: 120 }),
      }],
      ["/api/v1/tenants/7/lock/release", { method: "POST" }],
      ["/api/v1/tenants/7/lock/override", {
        method: "POST",
        headers: { "content-type": "application/json" },
        body: JSON.stringify({ reason: "Incident 4821 access recovery" }),
      }],
      ["/api/v1/tenants/7/lock/history?page_size=50", undefined],
      [
        "/api/v1/tenants/7/lock/history?page_size=50&cursor=opaque-next",
        undefined,
      ],
    ]);
  });
});
