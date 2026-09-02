import { describe, expect, it } from "vitest";

import type { HttpRequest } from "../../core/http";
import { createModelInputScopeApi } from "./api";

describe("Model Input Scope HTTP adapter", () => {
  it("owns exact normalized list pagination and detail transport", async () => {
    const calls: Array<[path: string, init: RequestInit | undefined]> = [];
    const request: HttpRequest = async <T>(path: string, init?: RequestInit) => {
      calls.push([path, init]);
      return {} as T;
    };
    const api = createModelInputScopeApi(request);

    await api.listModelInputScope(7, 18);
    await api.listModelInputScope(7, 18, {
      zone: " Bronze ",
      systemCode: " CRM ",
      sourceTenantCode: " GRDM ",
      objectName: " Customer_Raw ",
    }, 25, "opaque-next");
    await api.readModelInputScopeObject(7, 18, 501);

    expect(calls).toEqual([
      ["/api/v1/tenants/7/models/18/input-scope?page_size=200", undefined],
      [
        "/api/v1/tenants/7/models/18/input-scope?zone=bronze&system_code=crm&source_tenant_code=grdm&object_name=customer_raw&page_size=25&cursor=opaque-next",
        undefined,
      ],
      ["/api/v1/tenants/7/models/18/input-scope/501", undefined],
    ]);
  });
});
