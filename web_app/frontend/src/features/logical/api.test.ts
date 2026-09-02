import { describe, expect, it, vi } from "vitest";

import { createHttpRequest } from "../../core/http";
import { createLogicalApi, loadAllLogicalSubmodels, type LogicalTransport } from "./api";

describe("Logical HTTP adapter", () => {
  it("owns exact normalized collection and detail read transports", async () => {
    const fetcher = vi.fn<typeof fetch>().mockImplementation(async () => jsonResponse({}));
    const api = createLogicalApi(createHttpRequest(fetcher));

    await api.listLogicalEntities(7, 18, {
      status: "inactive",
      locked: false,
      nameExact: " Customer Account ",
      namePrefix: " Customer ",
      logicalSubmodelId: 91,
    }, 25, "opaque+/=");
    await api.readLogicalEntity(7, 18, 71);
    await api.listLogicalAttributes(7, 18, {
      status: "active",
      locked: true,
      nameExact: " Customer Id ",
      logicalEntityId: 71,
    }, 50, "attributes+/=");
    await api.readLogicalAttribute(7, 18, 81);
    await api.listLogicalRelationships(7, 18, {
      status: "inactive",
      locked: false,
      namePrefix: " Customer ",
      logicalEntityId: 71,
    }, 75, "relationships+/=");
    await api.readLogicalRelationship(7, 18, 101);
    await api.listLogicalSubmodels(7, 18);
    await api.readLogicalSubmodel(7, 18, 91);

    expect(fetcher.mock.calls.map(([input]) => String(input))).toEqual([
      "/api/v1/tenants/7/models/18/logical/entities?status=inactive&locked=false&name_exact=customer+account&name_prefix=customer&logical_submodel_id=91&page_size=25&cursor=opaque%2B%2F%3D",
      "/api/v1/tenants/7/models/18/logical/entities/71",
      "/api/v1/tenants/7/models/18/logical/attributes?status=active&locked=true&name_exact=customer+id&logical_entity_id=71&page_size=50&cursor=attributes%2B%2F%3D",
      "/api/v1/tenants/7/models/18/logical/attributes/81",
      "/api/v1/tenants/7/models/18/logical/relationships?status=inactive&locked=false&name_prefix=customer&logical_entity_id=71&page_size=75&cursor=relationships%2B%2F%3D",
      "/api/v1/tenants/7/models/18/logical/relationships/101",
      "/api/v1/tenants/7/models/18/logical/submodels?page_size=200",
      "/api/v1/tenants/7/models/18/logical/submodels/91",
    ]);
    for (const [, init] of fetcher.mock.calls) {
      expect(init).toEqual({
        cache: "no-store",
        credentials: "same-origin",
        headers: { accept: "application/json" },
      });
    }
  });

  it("keeps the bounded all-Submodel loader and repeated-cursor protection", async () => {
    const listLogicalSubmodels = vi.fn<LogicalTransport["listLogicalSubmodels"]>()
      .mockResolvedValueOnce({
        model_id: 18,
        model_revision: 4,
        items: [logicalSubmodel(91)],
        next_cursor: "next",
      })
      .mockResolvedValueOnce({
        model_id: 18,
        model_revision: 4,
        items: [logicalSubmodel(92)],
        next_cursor: null,
      });

    await expect(loadAllLogicalSubmodels({ listLogicalSubmodels }, 7, 18)).resolves.toEqual({
      modelRevision: 4,
      items: [logicalSubmodel(91), logicalSubmodel(92)],
    });
    expect(listLogicalSubmodels.mock.calls).toEqual([
      [7, 18, {}, 200, undefined],
      [7, 18, {}, 200, "next"],
    ]);

    const repeatedCursor = vi.fn<LogicalTransport["listLogicalSubmodels"]>()
      .mockResolvedValue({
        model_id: 18,
        model_revision: 4,
        items: [],
        next_cursor: "same",
      });
    await expect(loadAllLogicalSubmodels({
      listLogicalSubmodels: repeatedCursor,
    }, 7, 18)).rejects.toThrow("Logical Submodel cursor repeated");
  });
});

function logicalSubmodel(logicalSubmodelId: number) {
  return {
    logical_submodel_id: logicalSubmodelId,
    workflow_run_id: null,
    logical_submodel_name: `Submodel ${logicalSubmodelId}`,
    logical_submodel_status: "active" as const,
    logical_submodel_is_locked: false,
    entity_count: 1,
    updated_at: "2026-08-24T00:00:00Z",
  };
}

function jsonResponse(payload: unknown): Response {
  return new Response(JSON.stringify(payload), {
    headers: { "content-type": "application/json" },
  });
}
