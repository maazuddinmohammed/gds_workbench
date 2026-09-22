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

  it("sends creation as a same-Tenant JSON command", async () => {
    const calls: Array<[string, RequestInit | undefined]> = [];
    const request: HttpRequest = async <T>(path: string, init?: RequestInit) => {
      calls.push([path, init]);
      return {} as T;
    };
    const command: Parameters<ReturnType<typeof createModelsApi>["createModel"]>[1] = {
      model_name: "Customer", model_description: null,
      silver_model_naming_instructions: null, silver_model_audit_columns_template: null,
      gold_model_naming_instructions: null, gold_model_technical_columns_template: null,
      gold_model_audit_columns_template: null, default_agent_sdk_code: null,
      default_agent_provider_code: null, default_agent_model_code: null,
      default_reasoning_effort_code: null, default_max_turns: null, default_validation_retry_count: null,
    };
    await createModelsApi(request).createModel(7, command);
    expect(calls).toEqual([["/api/v1/tenants/7/models", {
      method: "POST", headers: { "content-type": "application/json" }, body: JSON.stringify(command),
    }]]);
  });
});
