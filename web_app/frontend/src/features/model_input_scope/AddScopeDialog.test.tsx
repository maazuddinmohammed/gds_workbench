import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { fireEvent, render, screen, waitFor } from "@testing-library/react";
import { describe, expect, it, vi } from "vitest";
import { ApiError } from "../../core/http";
import { AddScopeDialog } from "./AddScopeDialog";
import type { ModelInputScopeApi } from "./api";

describe("Add Input Scope Objects", () => {
  it("filters placement, preserves existing scope and retries an uncertain addition with the same key", async () => {
    const added = vi.fn().mockResolvedValue(undefined);
    const closed = vi.fn();
    const add = vi.fn().mockRejectedValueOnce(new ApiError(503, "dependency_unavailable", null))
      .mockResolvedValue({ model_revision: 5, action_count: 1 });
    const find = vi.fn().mockResolvedValue({ model_revision: 4, next_cursor: null, items: [
      { object_id: 11, object_schema: "bronze", object_name: "orders", attribute_count: 3, is_in_active_scope: false },
      { object_id: 12, object_schema: "bronze", object_name: "customers", attribute_count: 2, is_in_active_scope: true },
    ] });
    const api: ModelInputScopeApi = {
      readScopeSearchOptions: vi.fn().mockResolvedValue({ model_revision: 4, locations: [
        { tenant_id: 2, tenant_code: "GDS", tenant_name: "Global Store", system_code: "GDS", system_name: "Lakehouse", zone_code: "bronze" },
      ] }),
      listScopeCandidates: find, addScopeObjects: add,
      listModelInputScope: vi.fn(), readModelInputScopeObject: vi.fn(),
    };
    render(<QueryClientProvider client={new QueryClient({ defaultOptions: { queries: { retry: false } } })}>
      <AddScopeDialog api={api} tenantId={1} modelId={7} modelRevision={4} hasTenantLock onClose={closed} onAdded={added} />
    </QueryClientProvider>);
    await screen.findByRole("option", { name: "Global Store (GDS)" });
    expect(screen.getByLabelText("System")).toBeDisabled();
    fireEvent.change(screen.getByLabelText("Tenant"), { target: { value: "2" } });
    fireEvent.change(screen.getByLabelText("System"), { target: { value: "GDS" } });
    fireEvent.change(screen.getByLabelText("Zone"), { target: { value: "bronze" } });
    fireEvent.click(screen.getByRole("button", { name: "Find Objects" }));
    await screen.findByRole("table", { name: "Objects to add" });
    expect(find).toHaveBeenCalledWith(1, 7, { tenantId: 2, systemCode: "GDS", zone: "bronze", objectName: "" }, undefined);
    expect(screen.getByLabelText("Add bronze.customers")).toBeDisabled();
    fireEvent.click(screen.getByLabelText("Add bronze.orders"));
    fireEvent.click(screen.getByRole("button", { name: "Add selected Objects" }));
    await screen.findByRole("button", { name: "Retry addition" });
    expect(screen.getByRole("button", { name: "Close" })).toBeDisabled();
    expect(screen.getByLabelText("Tenant")).toBeDisabled();
    fireEvent.click(screen.getByRole("button", { name: "Retry addition" }));
    await waitFor(() => expect(closed).toHaveBeenCalledOnce());
    expect(add.mock.calls[0]).toEqual(add.mock.calls[1]);
    expect(add.mock.calls[0]?.slice(0, 3)).toEqual([1, 7, { object_ids: [11], expected_model_revision: 4 }]);
    expect(added).toHaveBeenCalledOnce();
  });
});
