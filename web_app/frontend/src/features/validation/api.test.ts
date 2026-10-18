import { describe, expect, it, vi } from "vitest";

import { createHttpRequest } from "../../core/http";
import { createValidationApi } from "./api";

describe("Validation HTTP adapter", () => {
  it("downloads all layer checks through a revision-fenced authenticated request", async () => {
    const filename = "gds_validation_logical__project_18__r23.zip";
    const fetcher = vi.fn<typeof fetch>().mockResolvedValue(new Response("zip fixture", {
      headers: { "content-type": "application/zip", "content-disposition": `attachment; filename="${filename}"` },
    }));
    const command = { entity_type: "logical_entity", expected_project_revision: 23 } as const;
    const archive = await createValidationApi(createHttpRequest(fetcher)).exportAllValidations(7, 18, command);

    expect(fetcher).toHaveBeenCalledWith("/api/v1/tenants/7/projects/18/validation/downloads/all.zip", {
      method: "POST", cache: "no-store", credentials: "same-origin",
      headers: { accept: "application/zip", "content-type": "application/json" }, body: JSON.stringify(command),
    });
    expect(archive.filename).toBe(filename);
    expect(await archive.blob.text()).toBe("zip fixture");
  });

  it("owns exact bounded System and applied ledger reads", async () => {
    const fetcher = vi.fn<typeof fetch>().mockImplementation(async () => jsonResponse({}));
    const api = createValidationApi(createHttpRequest(fetcher));

    await api.listValidationEligibleSystems(7, 18);
    await api.readValidationLedger(7, 18);

    expect(fetcher.mock.calls.map(([input]) => String(input))).toEqual([
      "/api/v1/tenants/7/projects/18/validation/systems",
      "/api/v1/tenants/7/projects/18/validation/ledger",
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
