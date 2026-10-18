import { describe, expect, it, vi } from "vitest";

import { createHttpRequest } from "../../core/http";
import {
  createCodeGenerationApi,
  generatedSqlArtifactDownloadPath,
} from "./api";

describe("Code Generation HTTP adapter", () => {
  it("downloads a revision-fenced layer archive through the authenticated transport", async () => {
    const filename = "gds_sql_dimensional__project_18__r23.zip";
    const fetcher = vi.fn<typeof fetch>().mockResolvedValue(new Response("zip fixture", {
      headers: { "content-type": "application/zip", "content-disposition": `attachment; filename="${filename}"` },
    }));
    const command = { entity_type: "dimensional_entity", expected_project_revision: 23 } as const;
    const archive = await createCodeGenerationApi(createHttpRequest(fetcher)).downloadAllGeneratedSql(7, 18, command);

    expect(fetcher).toHaveBeenCalledWith("/api/v1/tenants/7/projects/18/code-generation/downloads/all.zip", {
      method: "POST", cache: "no-store", credentials: "same-origin",
      headers: { accept: "application/zip", "content-type": "application/json" }, body: JSON.stringify(command),
    });
    expect(archive.filename).toBe(filename);
    expect(await archive.blob.text()).toBe("zip fixture");
  });

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
      "/api/v1/tenants/7/projects/18/code-generation/targets?entity_type=logical_entity&system_id=3&source_system_id=4&system_code=gds&source_system_code=crm&page_size=25&cursor=targets%2B%2F%3D",
      "/api/v1/tenants/7/projects/18/code-generation/targets?page_size=50",
      "/api/v1/tenants/7/projects/18/code-generation/artifacts/501",
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
      "/api/v1/tenants/7/projects/18/code-generation/artifacts/501/download.sql",
    );
  });
});

function jsonResponse(payload: unknown): Response {
  return new Response(JSON.stringify(payload), {
    headers: { "content-type": "application/json" },
  });
}
