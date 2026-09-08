import { render, screen, waitFor, within } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { createMemoryHistory } from "@tanstack/react-router";
import { describe, expect, it, vi } from "vitest";

import { createApiClient } from "../../api";
import { WorkbenchApp, createWorkbenchRouter } from "../../app";
import type { ObjectAttribute, ObjectCatalogDetail, ReviewMetadataRecordsCommand } from "./api";

describe("physical metadata review", () => {
  it("discovers inactive Objects with exact server filters and clears page selection", async () => {
    const fixture = catalogFixture({ pageTwo: true });
    const user = userEvent.setup();
    renderCatalog(fixture);
    await screen.findByRole("table", { name: "Physical Objects" });
    await user.click(screen.getByLabelText("Select Object sales.Orders"));
    await user.click(screen.getByRole("button", { name: "Next Objects" }));
    await screen.findByText("sales.Archive");
    expect(screen.getByRole("group", { name: "Review selected Objects" })).toHaveTextContent("0 selected Objects");
    expect(fixture.fetcher.mock.calls.some(([url]) => String(url).endsWith("cursor=page-two"))).toBe(true);
    await user.selectOptions(screen.getByLabelText("Object state"), "inactive");
    await user.selectOptions(screen.getByLabelText("Zone"), "bronze");
    await user.type(screen.getByLabelText("System code"), " CRM ");
    await user.click(screen.getByRole("button", { name: "Apply filters" }));
    await waitFor(() => expect(fixture.fetcher).toHaveBeenCalledWith("/api/v1/tenants/7/metadata/objects?zone=bronze&system_code=crm&active_state=inactive&page_size=50", expect.anything()));
    expect(screen.getByText(/Page 1 ·/)).toBeVisible();
  });

  for (const recordType of ["object", "attribute"] as const) {
    for (const [action, label] of [["lock", "Lock"], ["unlock", "Unlock"], ["deactivate", "Make inactive"], ["reactivate", "Make active"]] as const) {
      it(`reviews ${recordType} ${action} with the exact catalog ID and revision`, async () => {
        const fixture = catalogFixture();
        const user = userEvent.setup();
        renderCatalog(fixture, recordType === "attribute" ? "?objectId=501" : "");
        await screen.findByRole("table", { name: "Physical Objects" });
        if (recordType === "attribute") await screen.findByRole("table", { name: "Physical Attributes for Orders" });
        await user.click(screen.getByLabelText(recordType === "object" ? "Select Object sales.Orders" : "Select Attribute OrderID"));
        await user.click(screen.getByRole("button", { name: `${label} selected ${recordType === "object" ? "Objects" : "Attributes"}` }));
        await screen.findByText("1 record reviewed; 1 changed.");
        const call = fixture.fetcher.mock.calls.find(([url, init]) => String(url).endsWith("/metadata/review") && init?.method === "POST")!;
        expect(JSON.parse(String(call[1]?.body))).toEqual({ record_type: recordType, action, records: [{ record_id: recordType === "object" ? 501 : 601, expected_revision: recordType === "object" ? "a".repeat(64) : "b".repeat(64) }] });
        expect(new Headers(call[1]?.headers).get("Idempotency-Key")).toMatch(/^[0-9a-f-]{36}$/);
        expect(screen.queryByText("a".repeat(64))).not.toBeInTheDocument();
      });
    }
  }

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
    expect(within(drawer).queryByLabelText("Select Attribute OrderID")).not.toBeInTheDocument();
    await user.click(within(drawer).getByLabelText("Select Attribute LegacyID"));
    await user.click(within(drawer).getByRole("button", { name: "Make active selected Attributes" }));
    await screen.findByText("1 record reviewed; 1 changed.");
  });

  it("locks all Attribute actions when the parent is locked and prevents locked record state changes", async () => {
    const fixture = catalogFixture({ parentLocked: true });
    const user = userEvent.setup();
    renderCatalog(fixture, "?objectId=501");
    await screen.findByRole("table", { name: "Physical Attributes for Orders" });
    expect(screen.getByText("Unlock the Object first to review its Attributes.")).toBeVisible();
    expect(screen.getByLabelText("Select Attribute OrderID")).toBeDisabled();
    expect(screen.getByRole("button", { name: "Unlock selected Attributes" })).toBeDisabled();
    expect(screen.getByRole("button", { name: "Make inactive Object" })).toBeDisabled();
    await user.click(screen.getByRole("button", { name: "Unlock Object" }));
    await waitFor(() => expect(screen.getByLabelText("Select Attribute OrderID")).toBeEnabled());
  });

  it.each(["viewer", "foreign-lock", "expired-lock"])("disables writes for %s", async (restriction) => {
    renderCatalog(catalogFixture({ restriction }));
    await screen.findByRole("table", { name: "Physical Objects" });
    expect(screen.getByLabelText("Select Object sales.Orders")).toBeDisabled();
    expect(screen.getByRole("button", { name: "Lock selected Objects" })).toBeDisabled();
  });

  it.each([0, 408, 503])("freezes and replays an ambiguous response %s with the same key and payload", async (ambiguousStatus) => {
    const fixture = catalogFixture({ ambiguousStatus });
    const user = userEvent.setup();
    renderCatalog(fixture);
    await screen.findByRole("table", { name: "Physical Objects" });
    await user.click(screen.getByLabelText("Select Object sales.Orders"));
    await user.click(screen.getByRole("button", { name: "Lock selected Objects" }));
    await screen.findByRole("button", { name: "Retry review" });
    expect(screen.getByLabelText("Select Object sales.Orders")).toBeDisabled();
    expect(screen.getByLabelText("Object state")).toBeDisabled();
    expect(screen.getByRole("button", { name: "Refresh" })).toBeDisabled();
    await user.click(screen.getByRole("button", { name: "Retry review" }));
    await screen.findByText("1 record reviewed; 1 changed.");
    const calls = fixture.fetcher.mock.calls.filter(([url]) => String(url).endsWith("/metadata/review"));
    expect(calls).toHaveLength(2);
    expect(calls[0]?.[1]).toEqual(calls[1]?.[1]);
  });

  it("requires Refresh after stale denial and submits a new selection with the current token", async () => {
    const fixture = catalogFixture({ staleOnce: true });
    const user = userEvent.setup();
    renderCatalog(fixture);
    await screen.findByRole("table", { name: "Physical Objects" });
    await user.click(screen.getByLabelText("Select Object sales.Orders"));
    await user.click(screen.getByRole("button", { name: "Lock selected Objects" }));
    await screen.findByText("Selected metadata changed after it was read. Refresh and select the current records.");
    expect(screen.getByLabelText("Select Object sales.Orders")).toBeDisabled();
    expect(screen.queryByRole("button", { name: "Retry review" })).not.toBeInTheDocument();
    await user.click(screen.getByRole("button", { name: "Refresh" }));
    await waitFor(() => expect(screen.getByLabelText("Select Object sales.Orders")).toBeEnabled());
    await user.click(screen.getByLabelText("Select Object sales.Orders"));
    await user.click(screen.getByRole("button", { name: "Lock selected Objects" }));
    await screen.findByText("1 record reviewed; 1 changed.");
    const calls = fixture.fetcher.mock.calls.filter(([url]) => String(url).endsWith("/metadata/review"));
    expect(JSON.parse(String(calls[1]?.[1]?.body)).records[0].expected_revision).toBe("c".repeat(64));
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

  it("shows no-op counts and refreshes manually without polling", async () => {
    const fixture = catalogFixture({ noOp: true });
    const user = userEvent.setup();
    const router = renderCatalog(fixture);
    await screen.findByRole("table", { name: "Physical Objects" });
    const invalidate = vi.spyOn(router.options.context.queryClient, "invalidateQueries");
    await user.click(screen.getByLabelText("Select Object sales.Orders"));
    await user.click(screen.getByRole("button", { name: "Unlock selected Objects" }));
    await screen.findByText("1 record reviewed; 0 changed.");
    await waitFor(() => expect(screen.getByLabelText("Select Object sales.Orders")).toBeEnabled());
    expect(screen.getByLabelText("Select Object sales.Orders")).not.toBeChecked();
    expect(invalidate).toHaveBeenCalledWith({ queryKey: ["model-input-scope", 7] });
    expect(invalidate).toHaveBeenCalledWith({ queryKey: ["workflow-run-enrichment-scope", 7] });
    const count = fixture.fetcher.mock.calls.length;
    await new Promise((resolve) => setTimeout(resolve, 50));
    expect(fixture.fetcher).toHaveBeenCalledTimes(count);
    await user.click(screen.getByRole("button", { name: "Refresh" }));
    await waitFor(() => expect(fixture.fetcher.mock.calls.length).toBeGreaterThan(count));
  });

  it("pages Attributes locally, clears selected rows, and returns keyboard focus on close", async () => {
    const fixture = catalogFixture({ wide: true });
    const user = userEvent.setup();
    renderCatalog(fixture);
    const open = await screen.findByRole("button", { name: "Show details for sales.Orders" });
    await user.click(open);
    await screen.findByRole("table", { name: "Physical Attributes for Orders" });
    expect(screen.getByRole("button", { name: "Close physical Object details" })).toHaveFocus();
    await user.click(screen.getByLabelText("Select Attribute page"));
    expect(screen.getByRole("group", { name: "Review selected Attributes" })).toHaveTextContent("50 selected Attributes");
    await user.click(screen.getByRole("button", { name: "Next Attributes" }));
    expect(screen.getByRole("group", { name: "Review selected Attributes" })).toHaveTextContent("0 selected Attributes");
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
  const attributes: ObjectAttribute[] = Array.from({ length: options.wide ? 51 : 2 }, (_, index) => ({ attribute_id: 601 + index, review_revision: "b".repeat(64), attribute_name: index === 0 ? "OrderID" : index === 1 ? "LegacyID" : `Field${index}`, attribute_ordinal_position: index + 1, attribute_description: "A synthetic identifier.\nPreserved description.", attribute_data_type: "STRING", attribute_inferred_data_type: index === 0 ? "BIGINT" : null, attribute_nullability: false, is_surrogate_key: false, is_natural_key: true, is_meta_data: false, is_masking_required: false, is_mapped: true, is_purge: false, is_locked: false, is_active: index !== 1 }));
  const object: ObjectCatalogDetail = { object_id: 501, review_revision: "a".repeat(64), object_schema: "sales", object_name: "Orders", object_description: "Order transactions.", object_type_code: "table", object_type_name: "Table", zone_code: "bronze", connection_id: 44, connection_code: "shared", connection_name: "Shared placement", system_id: 11, system_code: "crm", system_name: "CRM", source_tenant_id: 7, source_tenant_code: "nwa", source_tenant_name: "Northwind", attribute_count: attributes.length, batch_attribute_name: null, is_active: !options.inactiveObject, is_locked: options.parentLocked ?? false, attributes };
  let reviews = 0;
  let details = 0;
  const fetcher = vi.fn<typeof fetch>(async (input, init) => {
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
    if (url.pathname.endsWith("/metadata/review")) {
      reviews++;
      if (reviews === 1 && options.ambiguousStatus !== undefined) {
        if (options.ambiguousStatus === 0) throw new TypeError("Network unavailable");
        return json({ error: { code: "dependency_unavailable" } }, options.ambiguousStatus);
      }
      if (reviews === 1 && options.staleOnce) { object.review_revision = "c".repeat(64); return json({ error: { code: "metadata_revision_conflict" } }, 409); }
      const command = JSON.parse(String(init?.body)) as ReviewMetadataRecordsCommand;
      const rows = command.records.map(({ record_id }) => {
        const row = command.record_type === "object" ? object : attributes.find((item) => item.attribute_id === record_id)!;
        if (command.action === "lock") row.is_locked = true;
        if (command.action === "unlock") row.is_locked = false;
        if (command.action === "deactivate") row.is_active = false;
        if (command.action === "reactivate") row.is_active = true;
        row.review_revision = "d".repeat(64);
        return { record_id, review_revision: row.review_revision, is_active: row.is_active, is_locked: row.is_locked };
      });
      return json({ review_event_id: 901, action_count: options.noOp ? 0 : rows.length, records: rows });
    }
    throw new Error("Unexpected fixture request");
  });
  return { fetcher };
}
function json(value: unknown, status = 200) { return new Response(JSON.stringify(value), { status, headers: { "content-type": "application/json" } }); }
