import { useState } from "react";
import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { render, screen, waitFor, within } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { describe, expect, it, vi } from "vitest";

import type { ModelInputScopeApi, ModelInputScopeObject } from "./api";
import { SourceCodeFilter, SourceFilterNotice, useScopeFilterChoices } from "./scopeFilterChoices";

const object: ModelInputScopeObject = {
  model_input_scope_id: 101, object_id: 501, connection_id: 21,
  system_id: 31, system_code: "CRM", system_name: "Customer system",
  source_tenant_id: 8, source_tenant_code: "GRDM", source_tenant_name: "Reference",
  object_schema: "bronze", object_name: "customer", zone_code: "bronze",
  batch_attribute_name: null, attribute_count: 2, is_model_input_eligible: true,
  created_at: "2026-08-24T14:00:00Z", updated_at: "2026-08-24T14:00:00Z",
};

function SourceFilters({ api, revision = 18 }: {
  api: Pick<ModelInputScopeApi, "listModelInputScope">; revision?: number;
}) {
  const choices = useScopeFilterChoices(api, 7, 18, revision);
  const [system, setSystem] = useState("");
  return <>
    <SourceCodeFilter label="Source Tenant" value="" codes={choices.tenantCodes}
      isLoading={choices.isLoading} isUnavailable={choices.isUnavailable} onChange={() => {}} />
    <SourceCodeFilter label="System" value={system} codes={choices.systemCodes}
      isLoading={choices.isLoading} isUnavailable={choices.isUnavailable} onChange={setSystem} />
    <SourceFilterNotice unavailable={choices.isUnavailable} />
    <button onClick={() => { void choices.refetch(); }}>Refresh</button>
  </>;
}

function filtersView(api: Pick<ModelInputScopeApi, "listModelInputScope">) {
  const client = new QueryClient({
    defaultOptions: { queries: { retry: false, staleTime: Infinity, refetchOnWindowFocus: false } },
  });
  const view = (revision = 18) => <QueryClientProvider client={client}>
    <SourceFilters api={api} revision={revision} />
  </QueryClientProvider>;
  return { ...render(view()), view };
}

describe("saved Model scope source filters", () => {
  it("loads every unfiltered saved page and keeps all choices after selecting a System", async () => {
    const listModelInputScope = vi.fn<ModelInputScopeApi["listModelInputScope"]>()
      .mockResolvedValueOnce({ model_id: 18, model_revision: 18, items: [object], next_cursor: "next" })
      .mockResolvedValueOnce({ model_id: 18, model_revision: 18,
        items: [{ ...object, object_id: 502, system_code: "ERP", source_tenant_code: "FIN" }, object],
        next_cursor: null });
    filtersView({ listModelInputScope });
    const system = screen.getByRole("combobox", { name: "System" });
    await waitFor(() => expect(system).toBeEnabled());
    expect(within(system).getAllByRole("option").map((option) => option.textContent)).toEqual(["All", "CRM", "ERP"]);
    expect(within(screen.getByRole("combobox", { name: "Source Tenant" })).getAllByRole("option")
      .map((option) => option.textContent)).toEqual(["All", "FIN", "GRDM"]);
    await userEvent.setup().selectOptions(system, "ERP");
    expect(system).toHaveValue("ERP");
    expect(within(system).getByRole("option", { name: "CRM" })).toBeInTheDocument();
    expect(listModelInputScope.mock.calls).toEqual([[7, 18, {}, 200, undefined], [7, 18, {}, 200, "next"]]);
  });

  it.each(["failed page", "changed revision", "repeated cursor"])("rejects partial choices after a %s", async (failure) => {
    const listModelInputScope = vi.fn<ModelInputScopeApi["listModelInputScope"]>()
      .mockResolvedValueOnce({ model_id: 18, model_revision: 18, items: [object], next_cursor: "next" });
    if (failure === "failed page") listModelInputScope.mockRejectedValueOnce(new Error("Unavailable"));
    else listModelInputScope.mockResolvedValueOnce({ model_id: 18,
      model_revision: failure === "changed revision" ? 19 : 18, items: [object],
      next_cursor: failure === "repeated cursor" ? "next" : null });
    filtersView({ listModelInputScope });
    expect(await screen.findByRole("status")).toHaveTextContent("Refresh to retry.");
    const system = screen.getByRole("combobox", { name: "System" });
    expect(system).toBeDisabled();
    expect(within(system).queryByRole("option", { name: "CRM" })).not.toBeInTheDocument();
    expect(listModelInputScope).toHaveBeenCalledTimes(2);
  });

  it("disables stale saved choices until manual Refresh loads the current revision", async () => {
    const listModelInputScope = vi.fn<ModelInputScopeApi["listModelInputScope"]>()
      .mockResolvedValueOnce({ model_id: 18, model_revision: 18, items: [object], next_cursor: null })
      .mockResolvedValueOnce({ model_id: 18, model_revision: 19,
        items: [{ ...object, system_code: "ERP" }], next_cursor: null });
    const { rerender, view } = filtersView({ listModelInputScope });
    await waitFor(() => expect(screen.getByRole("combobox", { name: "System" })).toBeEnabled());
    rerender(view(19));
    expect(screen.getByRole("combobox", { name: "System" })).toBeDisabled();
    expect(listModelInputScope).toHaveBeenCalledTimes(1);
    await userEvent.setup().click(screen.getByRole("button", { name: "Refresh" }));
    await waitFor(() => expect(screen.getByRole("combobox", { name: "System" })).toBeEnabled());
    expect(screen.getByRole("option", { name: "ERP" })).toBeInTheDocument();
    expect(screen.queryByRole("option", { name: "CRM" })).not.toBeInTheDocument();
    expect(screen.queryByRole("status")).not.toBeInTheDocument();
  });
});
