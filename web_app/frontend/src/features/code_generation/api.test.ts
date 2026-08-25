import { describe, expect, it, vi } from "vitest";

import { createHttpRequest } from "../../core/http";
import {
  createCodeGenerationApi,
  generatedSqlArtifactDownloadPath,
} from "./api";

describe("Code Generation HTTP adapter", () => {
  it("owns exact normalized target and artifact read transports", async () => {
    const fetcher = vi.fn<typeof fetch>().mockImplementation(async () => jsonResponse({}));
    const api = createCodeGenerationApi(createHttpRequest(fetcher));

    await api.listCodeGenerationTargets(7, 18, {
      entityType: "logical_entity",
      systemId: 3,
      systemCode: " GDS ",
      sourceSystemId: 4,
      sourceSystemCode: " CRM ",
    }, 25, "targets+/=");
    await api.listCodeGenerationTargets(7, 18);
    await api.readGeneratedSqlArtifact(7, 18, 501);

    expect(fetcher.mock.calls.map(([input]) => String(input))).toEqual([
      "/api/v1/tenants/7/models/18/code-generation/targets?entity_type=logical_entity&system_id=3&source_system_id=4&system_code=gds&source_system_code=crm&page_size=25&cursor=targets%2B%2F%3D",
      "/api/v1/tenants/7/models/18/code-generation/targets?page_size=50",
      "/api/v1/tenants/7/models/18/code-generation/artifacts/501",
    ]);
    for (const [, init] of fetcher.mock.calls) {
      expect(init).toEqual({
        cache: "no-store",
        credentials: "same-origin",
        headers: { accept: "application/json" },
      });
    }
  });

  it("preserves the direct SQL artifact download path", () => {
    expect(generatedSqlArtifactDownloadPath(7, 18, 501)).toBe(
      "/api/v1/tenants/7/models/18/code-generation/artifacts/501/download.sql",
    );
  });
});

function jsonResponse(payload: unknown): Response {
  return new Response(JSON.stringify(payload), {
    headers: { "content-type": "application/json" },
  });
}
