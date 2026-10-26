import { describe, expect, it, vi } from "vitest";

import { createHttpRequest } from "../../core/http";
import { createLogicalApi } from "./api";

describe("Logical HTTP adapter", () => {
  it("owns exact normalized collection and detail read transports", async () => {
    const fetcher = vi.fn<typeof fetch>().mockImplementation(async () => jsonResponse({}));
    const api = createLogicalApi(createHttpRequest(fetcher));

    await api.listLogicalEntities(7, 18, {
      active: false,
      locked: false,
      nameExact: " Customer Account ",
      namePrefix: " Customer ",
      subjectAreaId: 41,
    }, 25, "opaque+/=");
    await api.listLogicalEntities(7, 18);
    await api.readLogicalEntity(7, 18, 71);
    await api.listLogicalAttributes(7, 18, {
      active: true,
      locked: true,
      nameExact: " Customer Id ",
      logicalEntityId: 71,
    }, 50, "attributes+/=");
    await api.readLogicalAttribute(7, 18, 81);
    await api.listLogicalRelationships(7, 18, {
      active: false,
      locked: false,
      logicalEntityId: 71,
    }, 75, "relationships+/=");
    await api.readLogicalRelationship(7, 18, 101);

    expect(fetcher.mock.calls.map(([input]) => String(input))).toEqual([
      "/api/v1/tenants/7/projects/18/logical/entities?active=false&locked=false&name_exact=customer+account&name_prefix=customer&subject_area_id=41&page_size=25&cursor=opaque%2B%2F%3D",
      "/api/v1/tenants/7/projects/18/logical/entities?page_size=200",
      "/api/v1/tenants/7/projects/18/logical/entities/71",
      "/api/v1/tenants/7/projects/18/logical/attributes?active=true&locked=true&name_exact=customer+id&logical_entity_id=71&page_size=50&cursor=attributes%2B%2F%3D",
      "/api/v1/tenants/7/projects/18/logical/attributes/81",
      "/api/v1/tenants/7/projects/18/logical/relationships?active=false&locked=false&logical_entity_id=71&page_size=75&cursor=relationships%2B%2F%3D",
      "/api/v1/tenants/7/projects/18/logical/relationships/101",
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
