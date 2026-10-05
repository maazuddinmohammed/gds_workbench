import { describe, expect, it, vi } from "vitest";

import { createHttpRequest } from "../../core/http";
import {
  createMetadataApi,
  METADATA_XLSX_MEDIA_TYPE,
} from "./api";

describe("Metadata HTTP adapter", () => {
  it("encodes physical catalog filters and opaque cursors while preserving active-state choices", async () => {
    const fetcher = vi.fn<typeof fetch>().mockImplementation(async () => jsonResponse({
      schema_version: "1.0", tenant_id: 7, items: [], next_cursor: null,
    }));
    const api = createMetadataApi(createHttpRequest(fetcher));

    await api.listMetadataObjects(7);
    await api.listMetadataObjects(7, {
      zone: "bronze", systemCode: " ERP & Ops ", sourceTenantCode: " Customer/A ",
      activeState: "all",
    }, 25, "Opaque+/= A?");
    await api.listMetadataObjects(7, {
      systemCode: " \t ", sourceTenantCode: " ", activeState: "inactive",
    }, 200);
    await api.listMetadataObjects(9, { zone: "gold", activeState: "active" });

    expect(fetcher.mock.calls.map(([input]) => String(input))).toEqual([
      "/api/v1/tenants/7/metadata/objects?active_state=active&page_size=50",
      "/api/v1/tenants/7/metadata/objects?zone=bronze&system_code=erp+%26+ops&source_tenant_code=customer%2Fa&active_state=all&page_size=25&cursor=Opaque%2B%2F%3D+A%3F",
      "/api/v1/tenants/7/metadata/objects?active_state=inactive&page_size=200",
      "/api/v1/tenants/9/metadata/objects?zone=gold&active_state=active&page_size=50",
    ]);
    for (const [, init] of fetcher.mock.calls) {
      expect(init).toEqual({
        cache: "no-store", credentials: "same-origin", headers: { accept: "application/json" },
      });
    }
  });

  it("reads physical detail by its catalog ID and preserves returned lifecycle revisions", async () => {
    const response = {
      object_id: 812,
      review_revision: "a".repeat(64),
      is_active: false,
      is_locked: true,
      attributes: [{
        attribute_id: 415,
        review_revision: "b".repeat(64),
        is_active: true,
        is_locked: false,
      }],
    };
    const fetcher = vi.fn<typeof fetch>().mockResolvedValue(jsonResponse(response));
    const api = createMetadataApi(createHttpRequest(fetcher));

    await expect(api.readMetadataObject(7, 812)).resolves.toEqual(response);

    expect(fetcher).toHaveBeenCalledExactlyOnceWith(
      "/api/v1/tenants/7/metadata/objects/812",
      { cache: "no-store", credentials: "same-origin", headers: { accept: "application/json" } },
    );
  });

  it("owns exact catalog, normalized-row, and XLSX export transport", async () => {
    const workbook = new Uint8Array([80, 75, 3, 4]);
    const fetcher = vi.fn<typeof fetch>()
      .mockResolvedValueOnce(jsonResponse({ schema_version: "1.0", datasets: [] }))
      .mockResolvedValueOnce(jsonResponse({ schema_version: "1.0", items: [] }))
      .mockResolvedValueOnce(new Response(workbook, {
        headers: {
          "content-type": METADATA_XLSX_MEDIA_TYPE,
          "content-disposition": "attachment; filename=\"tenant_7__2_sheets.xlsx\"",
          "x-gds-sheet-count": "2",
        },
      }));
    const api = createMetadataApi(createHttpRequest(fetcher));

    await api.listMetadataDatasets(7);
    await api.listMetadataRows(7, "source_object", {
      tenant_code: "NWA",
      is_active: true,
    }, 25, "opaque-next");
    const download = await api.exportMetadataWorkbook(7, ["source_object", "copy"]);

    expect(fetcher.mock.calls.map(([input]) => String(input))).toEqual([
      "/api/v1/tenants/7/metadata/datasets",
      "/api/v1/tenants/7/metadata/datasets/source_object/rows?filters=%7B%22is_active%22%3Atrue%2C%22tenant_code%22%3A%22NWA%22%7D&page_size=25&cursor=opaque-next",
      "/api/v1/tenants/7/metadata/exports/xlsx",
    ]);
    expect(fetcher.mock.calls[2]?.[1]).toEqual({
      method: "POST",
      cache: "no-store",
      credentials: "same-origin",
      headers: {
        accept: METADATA_XLSX_MEDIA_TYPE,
        "content-type": "application/json",
      },
      body: JSON.stringify({
        schema_version: "1.0",
        sheet_codes: ["source_object", "copy"],
      }),
    });
    expect(download.filename).toBe("tenant_7__2_sheets.xlsx");
    expect(download.sheetCount).toBe(2);
    expect(Array.from(new Uint8Array(await download.blob.arrayBuffer()))).toEqual([80, 75, 3, 4]);
  });

  it("owns exact fenced Metadata Change Set and raw XLSX import transport", async () => {
    const fetcher = vi.fn<typeof fetch>().mockImplementation(async () => jsonResponse({}));
    const api = createMetadataApi(createHttpRequest(fetcher));
    const changeSetId = "11111111-1111-1111-1111-111111111111";
    const idempotencyKey = "22222222-2222-2222-2222-222222222222";
    const workbook = new Blob([new Uint8Array([80, 75, 3, 4])]);

    await api.createMetadataChangeSet(7, idempotencyKey);
    await api.readMetadataChangeSet(7, changeSetId, "source_object");
    await api.validateMetadataChangeSet(7, changeSetId, 4);
    await api.applyMetadataChangeSet(7, changeSetId, 4, idempotencyKey);
    await api.archiveMetadataChangeSet(7, changeSetId, 4, idempotencyKey);
    await api.importMetadataWorkbook(7, changeSetId, 4, workbook, idempotencyKey);

    expect(fetcher.mock.calls.map(([input]) => String(input))).toEqual([
      "/api/v1/tenants/7/metadata-change-sets",
      `/api/v1/tenants/7/metadata-change-sets/${changeSetId}?dataset=source_object`,
      `/api/v1/tenants/7/metadata-change-sets/${changeSetId}/validate`,
      `/api/v1/tenants/7/metadata-change-sets/${changeSetId}/apply`,
      `/api/v1/tenants/7/metadata-change-sets/${changeSetId}/archive`,
      `/api/v1/tenants/7/metadata-change-sets/${changeSetId}/imports/xlsx`,
    ]);
    expect(fetcher.mock.calls[0]?.[1]).toEqual(expect.objectContaining({
      method: "POST",
      headers: expect.objectContaining({ "Idempotency-Key": idempotencyKey }),
      body: JSON.stringify({ schema_version: "1.0" }),
    }));
    for (const index of [2, 3, 4]) {
      expect(fetcher.mock.calls[index]?.[1]).toEqual(expect.objectContaining({
        method: "POST",
        body: JSON.stringify({
          schema_version: "1.0",
          expected_draft_revision: 4,
        }),
      }));
    }
    expect(fetcher.mock.calls[5]?.[1]).toEqual(expect.objectContaining({
      method: "POST",
      body: workbook,
      headers: expect.objectContaining({
        "content-type": METADATA_XLSX_MEDIA_TYPE,
        "If-Match": "4",
        "Idempotency-Key": idempotencyKey,
      }),
    }));
  });
});

function jsonResponse(payload: unknown): Response {
  return new Response(JSON.stringify(payload), {
    headers: { "content-type": "application/json" },
  });
}
