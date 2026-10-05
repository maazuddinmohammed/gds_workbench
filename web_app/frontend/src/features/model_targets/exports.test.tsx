import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { render, screen, waitFor } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { afterEach, describe, expect, it, vi } from "vitest";
import { createHttpRequest } from "../../core/http";
import { createAnalysisApi } from "../analysis/api";
import { METADATA_XLSX_MEDIA_TYPE } from "../metadata/api";
import { createModelTargetsApi } from "./api";
import { DdlExportButton } from "./DdlExportButton";

afterEach(() => vi.restoreAllMocks());

describe("Model downloads", () => {
  it.each(["conceptual", "logical", "dimensional"] as const)("downloads %s DDL with current selection and revision", async (layer) => {
    vi.spyOn(URL, "createObjectURL").mockReturnValue("blob:ddl");
    vi.spyOn(URL, "revokeObjectURL").mockImplementation(() => {});
    const clicked = vi.spyOn(HTMLAnchorElement.prototype, "click").mockImplementation(() => {});
    const fetcher = vi.fn<typeof fetch>().mockResolvedValue(new Response("CREATE TABLE `s`.`T` (`ID` BIGINT) USING DELTA;", {
      headers: { "content-type": "application/sql", "content-disposition": 'attachment; filename="model.sql"' },
    }));
    render(<QueryClientProvider client={new QueryClient()}><DdlExportButton api={createModelTargetsApi(createHttpRequest(fetcher))}
      tenantId={1} modelId={2} modelRevision={3} layer={layer} entityIds={[4]} /></QueryClientProvider>);
    await userEvent.setup().click(screen.getByRole("button", { name: "Export DDL" }));
    await waitFor(() => expect(clicked).toHaveBeenCalledOnce());
    expect(JSON.parse(String(fetcher.mock.calls[0]?.[1]?.body))).toEqual({ layer, entity_ids: [4], expected_model_revision: 3 });
    expect(URL.revokeObjectURL).toHaveBeenCalledWith("blob:ddl");
  });

  it("exports all matching Analysis results with the applied filters", async () => {
    const fetcher = vi.fn<typeof fetch>().mockResolvedValue(new Response("workbook", {
      headers: { "content-type": METADATA_XLSX_MEDIA_TYPE, "content-disposition": 'attachment; filename="Analysis.xlsx"' },
    }));
    const result = await createAnalysisApi(createHttpRequest(fetcher)).exportAnalysis(1, 2, 3, {
      objectId: 4, validationState: "validated", locked: false, showInactive: true,
    });
    expect(result.filename).toBe("Analysis.xlsx");
    expect(JSON.parse(String(fetcher.mock.calls[0]?.[1]?.body))).toEqual({ expected_model_revision: 3,
      filters: { object_id: 4, validation_state: "validated", locked: false, show_inactive: true } });
  });

  it("rejects a login HTML page returned in place of an export", async () => {
    const fetcher = vi.fn<typeof fetch>().mockImplementation(async () => new Response("login", { headers: { "content-type": "text/html" } }));
    const request = createHttpRequest(fetcher);
    await expect(createAnalysisApi(request).exportAnalysis(1, 2, 3, {})).rejects.toMatchObject({ code: "invalid_response" });
    await expect(createModelTargetsApi(request).exportModelDdl(1, 2, { layer: "logical", expected_model_revision: 3 })).rejects.toMatchObject({ code: "invalid_response" });
  });
});
