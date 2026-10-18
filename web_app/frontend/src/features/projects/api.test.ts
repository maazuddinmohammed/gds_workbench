import { describe, expect, it } from "vitest";

import type { HttpRequest } from "../../core/http";
import { createProjectsApi } from "./api";

describe("Projects HTTP adapter", () => {
  it("owns the exact Project ledger, detail, and overview transport", async () => {
    const calls: Array<[path: string, init: RequestInit | undefined]> = [];
    const request: HttpRequest = async <T>(path: string, init?: RequestInit) => {
      calls.push([path, init]);
      return {} as T;
    };
    const api = createProjectsApi(request);

    await api.listProjects(7, "active");
    await api.listProjects(7, "archived", 50, "opaque-next");
    await api.readProject(7, 18);
    await api.readProjectOverview(7, 18);

    expect(calls).toEqual([
      ["/api/v1/tenants/7/projects?status=active&page_size=200", undefined],
      [
        "/api/v1/tenants/7/projects?status=archived&page_size=50&cursor=opaque-next",
        undefined,
      ],
      ["/api/v1/tenants/7/projects/18", undefined],
      ["/api/v1/tenants/7/projects/18/overview", undefined],
    ]);
  });

  it("sends creation and revision-fenced updates as same-Tenant JSON commands", async () => {
    const calls: Array<[string, RequestInit | undefined]> = [];
    const request: HttpRequest = async <T>(path: string, init?: RequestInit) => {
      calls.push([path, init]);
      return {} as T;
    };
    const command: Parameters<ReturnType<typeof createProjectsApi>["createProject"]>[1] = {
      project_name: "Customer", project_description: null,
      logical_schemas: [], dimensional_schemas: [], silver_model_naming_instructions: null, silver_model_audit_columns_template: null,
      logical_entity_scd_type: "type_2",
      gold_model_naming_instructions: null, gold_model_technical_columns_template: null,
      gold_model_audit_columns_template: null, default_agent_sdk_code: null,
      default_agent_provider_code: null, default_agent_model_code: null,
      default_reasoning_effort_code: null, default_max_turns: null, default_validation_retry_count: null,
    };
    await createProjectsApi(request).createProject(7, command);
    const update = { ...command, expected_project_revision: 8 };
    await createProjectsApi(request).updateProject(7, 18, update);
    expect(calls).toEqual([["/api/v1/tenants/7/projects", {
      method: "POST", headers: { "content-type": "application/json" }, body: JSON.stringify(command),
    }], ["/api/v1/tenants/7/projects/18", {
      method: "PUT", headers: { "content-type": "application/json" }, body: JSON.stringify(update),
    }]]);
  });
});
