import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { TargetExportButton } from "./TargetExportDialog";
import { render, screen, waitFor, within } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { createMemoryHistory } from "@tanstack/react-router";
import { describe, expect, it, vi } from "vitest";
import { createApiClient } from "../../api";
import { WorkbenchApp, createWorkbenchRouter } from "../../app";
import type { BindingPreview, TargetLayer } from "./api";

function fixture(layer: TargetLayer = "logical", options: { locked?: boolean; stale?: boolean; empty?: boolean; failApplyOnce?: boolean } = {}) {
  let revision = 3;
  let applyAttempts = 0;
  const body = (value: unknown, status = 200) => new Response(JSON.stringify(value), { status, headers: { "content-type": "application/json" } });
  const preview: BindingPreview = {
    model_id: 18, model_revision: 3, entity_name: "Customer", target: { object_id: 100, object_schema: "silver", object_name: "Customer", connection_code: "warehouse" },
    assignments: [{ modeled_attribute_id: 2, modeled_attribute_name: "CustomerId", modeled_data_type: "BIGINT", attribute_id: 101 }],
    target_attributes: [{ attribute_id: 101, attribute_name: "CustomerId", data_type: "BIGINT" }, { attribute_id: 102, attribute_name: "CustomerKey", data_type: "BIGINT" }],
    can_apply: true, action_count: 2, issues: [], plan_digest: "a".repeat(64),
  };
  const fetcher = vi.fn<typeof fetch>(async (input, init) => {
    const url = String(input);
    const path = `/api/v1/tenants/7/models/18`;
    if (url === "/api/v1/tenants/7/home") return body({
      tenant: { tenant_id: 7, tenant_code: "SALES", tenant_name: "Sales", tenant_description: null, tenant_visibility: "private", effective_role: "tenant_admin" },
      lock: { is_locked: options.locked !== false, owned_by_current_principal: options.locked !== false, owner_display_name: "Fixture user", purpose: "Model authoring", acquired_at: null, expires_at: null },
      lock_actions: { can_acquire: true, can_renew: true, can_release: true, can_override: false }, systems: [],
    });
    if (url === path) return body({ model_id: 18, tenant_id: 7, model_name: "Customer Model", model_revision: revision, model_input_scope_object_count: 2, model_description: null, is_active: true });
    if (url === `${path}/model-targets/options`) return body({ model_id: 18, model_revision: options.stale ? 2 : revision, placement: { tenant_code: "SHARED", source_tenant_code: "SALES", system_code: "GDS", connection_code: "warehouse" }, object_types: [{ code: "table", name: "Table" }], schemas: [{ layer, object_schema: layer === "logical" ? "silver" : "gold" }] });
    if (url.startsWith(`${path}/model-targets/bindings?`)) return body({ model_id: 18, model_revision: revision, next_after: null,
      items: options.empty ? [] : [{ entity_id: 1, entity_name: "Customer", binding_id: revision > 3 ? 10 : null, object_id: revision > 3 ? 100 : null, object_schema: revision > 3 ? (layer === "logical" ? "silver" : "gold") : null, object_name: revision > 3 ? "Customer" : null, is_locked: false }],
    });
    if (url.endsWith("/bindings/generate/preview")) return body({ model_id: 18, model_revision: revision, object_schema: layer === "logical" ? "silver" : "gold", matches: [{ entity_id: 1, entity_name: "Customer", object_id: 100, object_name: "Customer", status: "matched", issues: [] }], issues: [], can_apply: true, action_count: 2, plan_digest: "b".repeat(64) });
    if (url.endsWith("/bindings/generate/apply")) { revision = 4; return body({ model_id: 18, model_revision: 4, model_change_set_id: "generated-receipt", action_count: 2 }); }
    if (url.startsWith(`${path}/logical/entities?`) || url.startsWith(`${path}/dimensional/objects?`)) return body({ model_id: 18, model_revision: revision, next_cursor: null,
      items: options.empty ? [] : [{ [`${layer}_entity_id`]: 1, [`${layer}_entity_name`]: "Customer", [`${layer}_entity_type`]: layer === "logical" ? "entity" : "dimension" }],
    });
    if (url.startsWith(`${path}/model-targets?`)) return body({ items: [{ ...preview.target, matching_entity_ids: [1], object_schema: layer === "logical" ? "silver" : "gold" }], next_after: null });
    if (url === `${path}/model-targets/export`) return new Response(new Blob(["fixture workbook"]), { headers: { "content-type": "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet", "content-disposition": 'attachment; filename="registration.xlsx"' } });
    if (url.endsWith("/bindings/preview")) {
      const command = JSON.parse(String(init?.body));
      return body({ ...preview, assignments: [{ ...preview.assignments[0], attribute_id: command.assignments?.[0]?.attribute_id ?? 101 }] });
    }
    if (url.endsWith("/bindings/apply")) {
      applyAttempts++;
      if (options.failApplyOnce && applyAttempts === 1) return body({ error: { code: "dependency_unavailable" } }, 503);
      revision = 4;
      return body({ model_id: 18, model_revision: 4, model_change_set_id: "review-receipt", action_count: 2 });
    }
    return body({ error: { code: "not_found" } }, 404);
  });
  const router = createWorkbenchRouter({ api: createApiClient(fetcher), history: createMemoryHistory({ initialEntries: [`/tenants/7/models/18/targets?layer=${layer}`] }) });
  return { fetcher, router };
}

async function openBinding(layer = "logical") {
  const user = userEvent.setup();
  const search = await screen.findByRole("button", { name: "Search target for Customer" });
  await waitFor(() => expect(search).toBeEnabled());
  await user.click(search);
  const dialog = screen.getByRole("dialog", { name: "Find target for Customer" });
  await user.type(within(dialog).getByRole("combobox", { name: layer === "logical" ? "Silver schema" : "Gold schema" }), layer === "logical" ? "silver" : "gold");
  await user.click(await within(dialog).findByRole("button", { name: /^Select (silver|gold)\.Customer$/ }));
  await screen.findByRole("table", { name: "Attribute assignments" });
  return user;
}

describe("shared model target handoff", () => {
  it.each(["logical", "dimensional"] as const)("exports %s with scoped import format and keyboard focus", async (layer) => {
    const { fetcher } = fixture(layer);
    const createUrl = vi.fn(() => "blob:registration"); const revokeUrl = vi.fn();
    vi.stubGlobal("URL", Object.assign(URL, { createObjectURL: createUrl, revokeObjectURL: revokeUrl }));
    vi.spyOn(HTMLAnchorElement.prototype, "click").mockImplementation(() => {});
    render(<QueryClientProvider client={new QueryClient()}><TargetExportButton api={createApiClient(fetcher)} tenantId={7} modelId={18} modelRevision={3} layer={layer} /></QueryClientProvider>);
    const user = userEvent.setup();
    const trigger = screen.getByRole("button", { name: "Export" });
    await user.click(trigger);
    const dialog = screen.getByRole("dialog"); const schema = within(dialog).getByRole("textbox", { name: "Target schema" });
    expect(schema).toHaveFocus();
    await user.type(schema, layer === "logical" ? "silver" : "gold");
    const close = within(dialog).getByRole("button", { name: "Close" }); close.focus();
    await user.tab({ shift: true }); expect(within(dialog).getByRole("button", { name: "Download XLSX" })).toHaveFocus();
    await user.click(within(dialog).getByRole("button", { name: "Download XLSX" }));
    await screen.findByText("Workbook downloaded. Continue with Metadata registration.");
    const call = fetcher.mock.calls.find(([url]) => String(url).endsWith("/model-targets/export"))!;
    expect(JSON.parse(String(call[1]?.body))).toEqual({ layer, expected_model_revision: 3, object_schema: layer === "logical" ? "silver" : "gold" });
    expect(revokeUrl).toHaveBeenCalledWith("blob:registration");
    await user.keyboard("{Escape}"); expect(trigger).toHaveFocus();
    expect(within(dialog).queryByRole("combobox")).toBeNull();
    vi.restoreAllMocks(); vi.unstubAllGlobals();
  });

  it.each(["logical", "dimensional"] as const)("reviews explicit %s assignments and applies the exact approved plan", async (layer) => {
    const { router, fetcher } = fixture(layer); render(<WorkbenchApp router={router} />);
    const user = await openBinding(layer);
    await user.click(screen.getByRole("button", { name: "Search Attribute for CustomerId" }));
    await user.click(screen.getByRole("button", { name: /CustomerKey.*BIGINT/ }));
    expect(screen.getByRole("button", { name: "Apply Bindings" })).toBeDisabled();
    await user.click(screen.getByRole("button", { name: "Review Attribute assignments" }));
    await waitFor(() => expect(screen.getByRole("button", { name: "Apply Bindings" })).toBeEnabled());
    await user.click(screen.getByRole("button", { name: "Apply Bindings" }));
    expect(await screen.findByText(/2 binding records updated/)).toBeVisible();
    const call = fetcher.mock.calls.find(([url]) => String(url).endsWith("/bindings/apply"))!;
    expect(JSON.parse(String(call[1]?.body))).toEqual({ layer, entity_id: 1, object_id: 100, expected_model_revision: 3, assignments: [{ modeled_attribute_id: 2, attribute_id: 102 }], expected_plan_digest: "a".repeat(64) });
    expect(new Headers(call[1]?.headers).get("Idempotency-Key")).toMatch(/^[a-f0-9-]{36}$/);
    expect(screen.getByRole("link", { name: "Open Mapping" })).toHaveAttribute("href", "/tenants/7/mapping/models/18");
  });

  it("retries an unconfirmed apply with the same command and key", async () => {
    const { router, fetcher } = fixture("logical", { failApplyOnce: true }); render(<WorkbenchApp router={router} />);
    const user = await openBinding();
    await user.click(screen.getByRole("button", { name: "Apply Bindings" }));
    const retry = await screen.findByRole("button", { name: "Retry same apply" });
    expect(screen.getByRole("button", { name: "Search Attribute for CustomerId" })).toBeDisabled();
    expect(screen.getByRole("button", { name: "Refresh" })).toBeDisabled();
    await user.click(retry);
    await screen.findByText(/2 binding records updated/);
    const calls = fetcher.mock.calls.filter(([url]) => String(url).endsWith("/bindings/apply"));
    expect(calls).toHaveLength(2); expect(calls[0]).toEqual(calls[1]);
  });

  it("blocks stale exports and explains missing designs", async () => {
    const { router } = fixture("dimensional", { stale: true, empty: true }); render(<WorkbenchApp router={router} />);
    expect(await screen.findByText("No active Entities. Apply the Dimensional design first.")).toBeVisible();
    expect(screen.getByRole("button", { name: "Generate" })).toBeDisabled();
    expect(screen.getByText("The Model changed. Refresh before changing Bindings.")).toBeVisible();
  });

  it("requires the Tenant Lock for Binding review", async () => {
    const { router } = fixture("logical", { locked: false }); render(<WorkbenchApp router={router} />);
    expect(await screen.findByRole("button", { name: "Show details for Customer" })).toBeDisabled();
    expect(screen.getByRole("link", { name: "Metadata registration" })).toHaveAttribute("href", "/tenants/7/metadata");
  });

  it("shows unbound targets as dashes and requires an explicit search choice", async () => {
    const { router, fetcher } = fixture(); render(<WorkbenchApp router={router} />);
    const user = userEvent.setup();
    const table = await screen.findByRole("table", { name: "Logical target Entities" });
    await waitFor(() => expect(within(table).getAllByText("—")).toHaveLength(3));
    expect(screen.getByRole("button", { name: "Show details for Customer" })).toBeDisabled();
    const search = screen.getByRole("button", { name: "Search target for Customer" });
    await user.click(search);
    expect(fetcher.mock.calls.some(([url]) => String(url).endsWith("/bindings/preview"))).toBe(false);
    await user.keyboard("{Escape}"); expect(search).toHaveFocus();
  });

  it.each(["logical", "dimensional"] as const)("generates %s bindings from a schema and applies the frozen plan", async (layer) => {
    const { router, fetcher } = fixture(layer); render(<WorkbenchApp router={router} />);
    const user = userEvent.setup(); const trigger = await screen.findByRole("button", { name: "Generate" });
    await waitFor(() => expect(trigger).toBeEnabled()); await user.click(trigger);
    const dialog = screen.getByRole("dialog", { name: "Generate Bindings" });
    await user.type(within(dialog).getByRole("combobox", { name: layer === "logical" ? "Silver schema" : "Gold schema" }), layer === "logical" ? "silver" : "gold");
    await user.click(within(dialog).getByRole("button", { name: "Generate" }));
    await within(dialog).findByRole("table", { name: "Generated Bindings" });
    await user.click(within(dialog).getByRole("button", { name: "Apply generated Bindings" }));
    await screen.findByText("2 binding records updated.");
    const call = fetcher.mock.calls.find(([url]) => String(url).endsWith("/bindings/generate/apply"))!;
    expect(JSON.parse(String(call[1]?.body))).toEqual({ layer, expected_model_revision: 3, object_schema: layer === "logical" ? "silver" : "gold", expected_plan_digest: "b".repeat(64) });
  });
});
