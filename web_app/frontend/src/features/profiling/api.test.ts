import { describe, expect, it, vi } from "vitest";

import { createHttpRequest } from "../../core/http";
import { createProfilingApi } from "./api";

describe("Profiling HTTP adapter", () => {
  it("owns exact normalized reads and distinct run creation transport", async () => {
    const fetcher = vi.fn<typeof fetch>().mockImplementation(async () => jsonResponse({}));
    const api = createProfilingApi(createHttpRequest(fetcher));
    const idempotencyKey = "aaaaaaaa-aaaa-aaaa-aaaa-aaaaaaaaaaaa";
    const command = {
      expected_model_revision: 4,
      model_workflow: "profiling" as const,
      selected_object_ids: [501],
      requested_batch_id: null,
    };

    await api.listProfilingObjects(7, 18, {
      objectId: 501,
      sourceTenantCode: " GRDM ",
      systemCode: " CRM ",
      objectSchema: " Bronze_CRM ",
      objectName: " Customer_Raw ",
    }, 25, "opaque+/=");
    await api.listProfilingObjects(7, 18);
    await api.readProfilingObject(7, 18, 501);
    await api.createProfilingRun(7, 18, command, idempotencyKey);

    expect(fetcher.mock.calls.map(([input]) => String(input))).toEqual([
      "/api/v1/tenants/7/models/18/profiling?object_id=501&source_tenant_code=grdm&system_code=crm&object_schema=bronze_crm&object_name=customer_raw&page_size=25&cursor=opaque%2B%2F%3D",
      "/api/v1/tenants/7/models/18/profiling?page_size=200",
      "/api/v1/tenants/7/models/18/profiling/501",
      "/api/v1/tenants/7/models/18/runs",
    ]);
    expect(fetcher.mock.calls[3]?.[1]).toEqual({
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
  });
});

function jsonResponse(payload: unknown): Response {
  return new Response(JSON.stringify(payload), {
    headers: { "content-type": "application/json" },
  });
}
