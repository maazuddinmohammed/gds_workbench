import { describe, expect, it, vi } from "vitest";

import { createHttpRequest } from "../../core/http";
import { createConceptualApi } from "./api";

describe("Conceptual HTTP adapter", () => {
  it("owns exact normalized collection and detail read transports", async () => {
    const fetcher = vi.fn<typeof fetch>().mockImplementation(async () => jsonResponse({}));
    const api = createConceptualApi(createHttpRequest(fetcher));

    await api.listConceptualObjects(7, 18, {
      status: "needs_review",
      locked: false,
      nameExact: " Customer Account ",
      namePrefix: " Customer ",
    }, 25, "opaque+/=");
    await api.listConceptualObjects(7, 18);
    await api.readConceptualObject(7, 18, 41);
    await api.listConceptualRelationships(7, 18, {
      status: "active",
      locked: true,
      nameExact: " Places Order ",
    }, 50, "next+/=");
    await api.readConceptualRelationship(7, 18, 51);

    expect(fetcher.mock.calls.map(([input]) => String(input))).toEqual([
      "/api/v1/tenants/7/models/18/conceptual/objects?status=needs_review&locked=false&name_exact=customer+account&name_prefix=customer&page_size=25&cursor=opaque%2B%2F%3D",
      "/api/v1/tenants/7/models/18/conceptual/objects?page_size=200",
      "/api/v1/tenants/7/models/18/conceptual/objects/41",
      "/api/v1/tenants/7/models/18/conceptual/relationships?status=active&locked=true&name_exact=places+order&page_size=50&cursor=next%2B%2F%3D",
      "/api/v1/tenants/7/models/18/conceptual/relationships/51",
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
