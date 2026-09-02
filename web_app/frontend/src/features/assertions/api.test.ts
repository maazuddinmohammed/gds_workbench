import { describe, expect, it, vi } from "vitest";

import { createHttpRequest } from "../../core/http";
import { createAssertionsApi } from "./api";

describe("Assertions HTTP adapter", () => {
  it("owns exact normalized document and record read transports", async () => {
    const fetcher = vi.fn<typeof fetch>().mockImplementation(async () => jsonResponse({}));
    const api = createAssertionsApi(createHttpRequest(fetcher));

    await api.listAssertionDocuments(7, 18, {
      sourceSystemId: 2,
      sourceSystemCode: " CRM ",
      active: false,
      namePrefix: " Customer ",
    }, 50, "opaque+/=");
    await api.listAssertionDocuments(7, 18);
    await api.readAssertionDocument(7, 18, 31);
    await api.listAssertionRecords(7, 18, {
      documentId: 31,
      documentName: " Customer Rules ",
      sourceSystemId: 2,
      sourceSystemCode: " CRM ",
      status: "inactive",
      locked: false,
      applicableLayer: "logical",
      keyPrefix: " Customer. ",
    }, 25, "opaque+/=");
    await api.listAssertionRecords(7, 18);
    await api.readAssertionRecord(7, 18, 91);

    expect(fetcher.mock.calls.map(([input]) => String(input))).toEqual([
      "/api/v1/tenants/7/models/18/assertions/documents?source_system_id=2&source_system_code=crm&active=false&name_prefix=customer&page_size=50&cursor=opaque%2B%2F%3D",
      "/api/v1/tenants/7/models/18/assertions/documents?page_size=200",
      "/api/v1/tenants/7/models/18/assertions/documents/31",
      "/api/v1/tenants/7/models/18/assertions/records?document_id=31&document_name=customer+rules&source_system_id=2&source_system_code=crm&status=inactive&locked=false&applicable_layer=logical&key_prefix=customer.&page_size=25&cursor=opaque%2B%2F%3D",
      "/api/v1/tenants/7/models/18/assertions/records?page_size=200",
      "/api/v1/tenants/7/models/18/assertions/records/91",
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
