import { render, screen, waitFor, within } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { createMemoryHistory } from "@tanstack/react-router";
import { describe, expect, it, vi } from "vitest";

import { createApiClient } from "../../api";
import { WorkbenchApp, createWorkbenchRouter } from "../../app";
import type { ObjectAttribute, ObjectCatalogDetail } from "./api";

describe("read-only physical metadata", () => {
  it("discovers inactive Objects with exact server filters", async () => {
    const fixture = catalogFixture({ pageTwo: true });
    const user = userEvent.setup();
    renderCatalog(fixture);
    await screen.findByRole("table", { name: "Physical Objects" });
    expect(screen.queryByRole("checkbox")).not.toBeInTheDocument();
    expect(screen.queryByRole("button", { name: /Edit row|Add row|Lock selected/ })).not.toBeInTheDocument();
    await user.click(screen.getByRole("button", { name: "Next Objects" }));
    await screen.findByText("Archive");
    expect(fixture.fetcher.mock.calls.some(([url]) => String(url).endsWith("cursor=page-two"))).toBe(true);
    expect(screen.getByLabelText("Object state")).not.toBeVisible();
    await user.click(screen.getByRole("button", { name: "Filters" }));
    await user.selectOptions(screen.getByLabelText("Object state"), "inactive");
    await user.selectOptions(screen.getByLabelText("Zone"), "bronze");
    await user.type(screen.getByLabelText("System code"), " CRM ");
    await user.click(screen.getByRole("button", { name: "Apply filters" }));
    await waitFor(() => expect(fixture.fetcher).toHaveBeenCalledWith("/api/v1/tenants/7/metadata/objects?zone=bronze&system_code=crm&active_state=inactive&page_size=50", expect.anything()));
    expect(screen.getByText(/Page 1 ·/)).toBeVisible();
  });

  it("opens an inactive Object directly and preserves independent inactive Attributes and types", async () => {
    const fixture = catalogFixture({ inactiveObject: true });
    const user = userEvent.setup();
    renderCatalog(fixture, "?objectId=501");
    const drawer = await screen.findByRole("complementary", { name: "Physical Object details" });
    await within(drawer).findByRole("table", { name: "Physical Attributes for Orders" });
    expect(within(drawer).getByLabelText("Attribute state")).toHaveValue("all");
    expect(within(drawer).getByText(/Attribute state is independent/)).toBeVisible();
    expect(within(drawer).getAllByText("STRING").length).toBeGreaterThan(0);
    expect(within(drawer).getByText("BIGINT")).toBeVisible();
    await user.selectOptions(within(drawer).getByLabelText("Attribute state"), "inactive");
  });

  it.each(["foreign", "wrong-id", "too-wide", "403", "404"])("hides unavailable detail after Refresh: %s", async (detailFailure) => {
    const fixture = catalogFixture({ detailFailure });
    const user = userEvent.setup();
    renderCatalog(fixture, "?objectId=501");
    await screen.findByRole("table", { name: "Physical Attributes for Orders" });
    await user.click(screen.getByRole("button", { name: "Refresh" }));
    await screen.findByText(/Object details are unavailable/);
    expect(screen.queryByRole("table", { name: "Physical Attributes for Orders" })).not.toBeInTheDocument();
    expect(screen.queryByRole("button", { name: "Lock Object" })).not.toBeInTheDocument();
    expect(screen.queryByText("private-row-sentinel")).not.toBeInTheDocument();
  });

  it("rejects a foreign-owned catalog page instead of exposing cached rows", async () => {
    const fixture = catalogFixture({ foreignPage: true });
    renderCatalog(fixture);
    await screen.findByText("Objects could not be loaded. Refresh to try again.");
    expect(screen.queryByRole("table", { name: "Physical Objects" })).not.toBeInTheDocument();
  });

  it("pages Attributes locally and and returns keyboard focus on close", async () => {
    const fixture = catalogFixture({ wide: true });
    const user = userEvent.setup();
    renderCatalog(fixture);
    const open = await screen.findByRole("button", { name: "View attributes for sales.Orders" });
    await user.click(open);
    await screen.findByRole("table", { name: "Physical Attributes for Orders" });
    expect(screen.getByRole("button", { name: "Close physical Object details" })).toHaveFocus();
    await user.click(screen.getByRole("button", { name: "Next Attributes" }));
    expect(screen.getByText(/1 of 51 Attributes · Page 2/)).toBeVisible();
    expect(fixture.fetcher.mock.calls.filter(([url]) => String(url).endsWith("/objects/501"))).toHaveLength(1);
    await user.keyboard("{Escape}");
    await waitFor(() => expect(open).toHaveFocus());
  });
});

function renderCatalog(fixture: ReturnType<typeof catalogFixture>, search = "") {
  const router = createWorkbenchRouter({ api: createApiClient(fixture.fetcher), history: createMemoryHistory({ initialEntries: [`/tenants/7/metadata/objects${search}`] }) });
  render(<WorkbenchApp router={router} />);
  return router;
}
function catalogFixture(options: { parentLocked?: boolean; inactiveObject?: boolean; restriction?: string; ambiguousStatus?: number; staleOnce?: boolean; detailFailure?: string; foreignPage?: boolean; noOp?: boolean; wide?: boolean; pageTwo?: boolean } = {}) {
  const attributes: ObjectAttribute[] = Array.from({ length: options.wide ? 51 : 2 }, (_, index) => ({ attribute_id: 601 + index, attribute_name: index === 0 ? "OrderID" : index === 1 ? "LegacyID" : `Field${index}`, attribute_ordinal_position: index + 1, attribute_description: "A synthetic identifier.\nPreserved description.", attribute_data_type: "STRING", attribute_inferred_data_type: index === 0 ? "BIGINT" : null, attribute_nullability: false, is_surrogate_key: false, is_natural_key: true, is_meta_data: false, is_masking_required: false, is_mapped: true, is_purge: false, is_locked: false, is_active: index !== 1 }));
  const object: ObjectCatalogDetail = { tenant_code: "placement", object_id: 501, object_schema: "sales", object_name: "Orders", object_description: "Order transactions.", object_type_code: "table", object_type_name: "Table", zone_code: "bronze", connection_id: 44, connection_code: "shared", connection_name: "Shared placement", system_id: 11, system_code: "crm", system_name: "CRM", source_tenant_id: 7, source_tenant_code: "nwa", source_tenant_name: "Northwind", attribute_count: attributes.length, batch_attribute_name: null, is_active: !options.inactiveObject, is_locked: options.parentLocked ?? false, attributes };
  let details = 0;
  const fetcher = vi.fn<typeof fetch>(async (input) => {
    const url = new URL(String(input), "http://local.test");
    if (url.pathname.endsWith("/home")) return json({ tenant: { tenant_id: 7, tenant_code: "nwa", tenant_name: "Northwind", tenant_description: null, tenant_visibility: "private", effective_role: options.restriction === "viewer" ? "viewer" : "developer" }, lock: { is_locked: true, owned_by_current_principal: options.restriction !== "foreign-lock", owner_display_name: "Reviewer", purpose: "Review", acquired_at: "2026-01-01T00:00:00Z", expires_at: options.restriction === "expired-lock" ? "2020-01-01T00:00:00Z" : "2099-01-01T00:00:00Z" }, lock_actions: { can_acquire: false, can_renew: true, can_release: true, can_override: false }, systems: [] });
    if (url.pathname.endsWith("/metadata/objects")) {
      const row = { ...object, ...(options.foreignPage ? { source_tenant_id: 8 } : {}), ...(url.searchParams.has("cursor") ? { object_id: 502, object_name: "Archive" } : {}) };
      return json({ schema_version: "1.0", tenant_id: 7, items: options.inactiveObject && url.searchParams.get("active_state") === "active" ? [] : [row], next_cursor: options.pageTwo && !url.searchParams.has("cursor") ? "page-two" : null });
    }
    if (url.pathname.endsWith("/metadata/objects/501")) {
      details++;
      if (details > 1 && options.detailFailure) {
        if (["403", "404"].includes(options.detailFailure)) return json({ error: { code: "metadata_object_not_found", message: "private-row-sentinel" } }, Number(options.detailFailure));
        return json({ ...object, ...(options.detailFailure === "foreign" ? { source_tenant_id: 8 } : {}), ...(options.detailFailure === "wrong-id" ? { object_id: 999 } : {}), ...(options.detailFailure === "too-wide" ? { attribute_count: 2001, attributes: Array.from({ length: 2001 }, () => attributes[0]) } : {}) });
      }
      return json(object);
    }
    throw new Error("Unexpected fixture request");
  });
  return { fetcher };
}
function json(value: unknown, status = 200) { return new Response(JSON.stringify(value), { status, headers: { "content-type": "application/json" } }); }
