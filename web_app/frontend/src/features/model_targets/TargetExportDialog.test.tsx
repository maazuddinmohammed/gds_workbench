import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { render, screen, waitFor, within } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { describe, expect, it, vi } from "vitest";
import { createApiClient } from "../../api";
import { TargetExportButton } from "./TargetExportDialog";

describe("Entity registration export", () => {
  it.each(["logical", "dimensional"] as const)("exports %s using saved Entity schemas", async (layer) => {
    const fetcher = vi.fn<typeof fetch>(async (input) => String(input).endsWith("/options")
      ? new Response(JSON.stringify({ model_id: 18, model_revision: 3, placement: { tenant_code: "SHARED", source_tenant_code: "SALES", system_code: "GDS", connection_code: "warehouse" } }), { headers: { "content-type": "application/json" } })
      : new Response(new Blob(["fixture workbook"]), { headers: { "content-type": "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet", "content-disposition": 'attachment; filename="registration.xlsx"' } }));
    const createUrl = vi.fn(() => "blob:registration"); const revokeUrl = vi.fn();
    vi.stubGlobal("URL", Object.assign(URL, { createObjectURL: createUrl, revokeObjectURL: revokeUrl }));
    vi.spyOn(HTMLAnchorElement.prototype, "click").mockImplementation(() => {});
    render(<QueryClientProvider client={new QueryClient()}><TargetExportButton api={createApiClient(fetcher)} tenantId={7} modelId={18} modelRevision={3} layer={layer} /></QueryClientProvider>);
    const user = userEvent.setup();
    const trigger = screen.getByRole("button", { name: "Export Metadata" });
    await user.click(trigger);
    const dialog = screen.getByRole("dialog");
    expect(within(dialog).queryByRole("textbox", { name: "Target schema" })).toBeNull();
    const download = within(dialog).getByRole("button", { name: "Download XLSX" });
    await waitFor(() => expect(download).toBeEnabled());
    await user.click(download);
    await screen.findByText("Workbook downloaded. Continue with Metadata registration.");
    const call = fetcher.mock.calls.find(([url]) => String(url).endsWith("/model-targets/export"))!;
    expect(JSON.parse(String(call[1]?.body))).toEqual({ layer, expected_model_revision: 3 });
    expect(revokeUrl).toHaveBeenCalledWith("blob:registration");
    await user.keyboard("{Escape}"); expect(trigger).toHaveFocus();
    vi.restoreAllMocks(); vi.unstubAllGlobals();
  });
});
