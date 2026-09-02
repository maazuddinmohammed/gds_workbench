import { describe, expect, it, vi } from "vitest";

import { createHttpRequest } from "../../core/http";
import { createDimensionalApi } from "./api";

describe("Dimensional HTTP adapter", () => {
  it("owns exact normalized collection and detail read transports", async () => {
    const fetcher = vi.fn<typeof fetch>().mockImplementation(async () => jsonResponse({}));
    const api = createDimensionalApi(createHttpRequest(fetcher));

    await api.listDimensionalObjects(7, 18, {
      status: "inactive",
      locked: false,
      nameExact: " Sales Fact ",
      namePrefix: " Sales ",
    }, 25, "opaque+/=");
    await api.listDimensionalObjects(7, 18);
    await api.readDimensionalObject(7, 18, 71);
    await api.listDimensionalAttributes(7, 18, {
      status: "active",
      locked: true,
      nameExact: " Sales Key ",
      dimensionalEntityId: 71,
    }, 50, "attributes+/=");
    await api.readDimensionalAttribute(7, 18, 81);
    await api.listDimensionalRelationships(7, 18, {
      status: "inactive",
      locked: false,
      namePrefix: " Sales ",
      dimensionalEntityId: 71,
    }, 75, "relationships+/=");
    await api.readDimensionalRelationship(7, 18, 101);

    expect(fetcher.mock.calls.map(([input]) => String(input))).toEqual([
      "/api/v1/tenants/7/models/18/dimensional/objects?status=inactive&locked=false&name_exact=sales+fact&name_prefix=sales&page_size=25&cursor=opaque%2B%2F%3D",
      "/api/v1/tenants/7/models/18/dimensional/objects?page_size=200",
      "/api/v1/tenants/7/models/18/dimensional/objects/71",
      "/api/v1/tenants/7/models/18/dimensional/attributes?status=active&locked=true&name_exact=sales+key&dimensional_entity_id=71&page_size=50&cursor=attributes%2B%2F%3D",
      "/api/v1/tenants/7/models/18/dimensional/attributes/81",
      "/api/v1/tenants/7/models/18/dimensional/relationships?status=inactive&locked=false&name_prefix=sales&dimensional_entity_id=71&page_size=75&cursor=relationships%2B%2F%3D",
      "/api/v1/tenants/7/models/18/dimensional/relationships/101",
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
