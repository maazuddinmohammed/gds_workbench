import { render, screen, waitFor, within } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { createMemoryHistory } from "@tanstack/react-router";
import { describe, expect, it, vi } from "vitest";
import { createApiClient } from "../../api";
import { createWorkbenchRouter, WorkbenchApp } from "../../app";

function setup({ role = "tenant_admin", owned = true, failure = false } = {}) {
  let locked = false;
  let revision = 8;
  const response = (body: unknown, status = 200) => new Response(JSON.stringify(body), { status, headers: { "content-type": "application/json" } });
  const fetcher = vi.fn<typeof fetch>(async (input, init) => {
    const url = new URL(String(input), "http://local.test");
    if (url.pathname === "/api/v1/session") return response({ display_name: "Reviewer", actor_kind: "human", is_super_admin: false, last_tenant_id: 7 });
    if (url.pathname.endsWith("/home")) return response({
      tenant: { tenant_id: 7, tenant_code: "DATA", tenant_name: "Data", tenant_visibility: "private", effective_role: role },
      lock: { is_locked: true, owned_by_current_principal: owned, expires_at: "2099-01-01T00:00:00Z" },
      lock_actions: {}, systems: [],
    });
    if (url.pathname.endsWith("/lock") && init?.method === "PUT") {
      if (failure) return response({ error: { code: "model_workflow_conflict", message: "Private detail" } }, 409);
      locked = JSON.parse(String(init.body)).is_locked;
      revision += 1;
      return response({ tenant_id: 7, model_id: 18, model_revision: revision, is_active: true });
    }
    if (url.pathname.endsWith("/models")) return response({ items: [{ model_id: 18, model_name: "Customer", model_description: "Customer domain", model_revision: revision, is_locked: locked, updated_at: "2026-09-27T00:00:00Z" }], next_cursor: null });
    return response({}, 404);
  });
  const router = createWorkbenchRouter({ api: createApiClient(fetcher), history: createMemoryHistory({ initialEntries: ["/tenants/7/models"] }) });
  render(<WorkbenchApp router={router} />);
  return fetcher;
}

describe("Models ledger lock", () => {
  it("selects a Model, locks and unlocks with the latest revision, and shows its status", async () => {
    const fetcher = setup();
    const user = userEvent.setup();
    const table = await screen.findByRole("table", { name: "Active Models" });
    expect(within(table).getAllByRole("columnheader").map((cell) => cell.textContent)).toEqual(["Select", "Model", "Revision", "Lock status", "Updated", "Actions"]);
    expect(screen.getByRole("button", { name: "Lock Model" })).toBeDisabled();
    await user.click(screen.getByRole("radio", { name: "Select Customer" }));
    await user.click(screen.getByRole("button", { name: "Lock Model" }));
    await waitFor(() => expect(within(table).getByText("Locked")).toBeVisible());
    await user.click(screen.getByRole("button", { name: "Unlock Model" }));
    await waitFor(() => expect(within(table).getByText("Unlocked")).toBeVisible());
    const writes = fetcher.mock.calls.filter(([path]) => String(path).endsWith("/lock"));
    expect(writes.map(([, init]) => JSON.parse(String(init?.body)))).toEqual([
      { expected_model_revision: 8, is_locked: true }, { expected_model_revision: 9, is_locked: false },
    ]);
    await user.click(screen.getByRole("button", { name: "Archived" }));
    await screen.findByRole("table", { name: "Archived Models" });
    expect(screen.getByRole("radio", { name: "Select Customer" })).not.toBeChecked();
    await user.click(screen.getByRole("radio", { name: "Select Customer" }));
    expect(screen.getByRole("button", { name: "Lock Model" })).toBeDisabled();
  });

  it.each([{ role: "viewer" }, { owned: false }])("requires permission and Tenant Lock ownership: %j", async (options) => {
    setup(options);
    await userEvent.click(await screen.findByRole("radio", { name: "Select Customer" }));
    expect(screen.getByRole("button", { name: "Lock Model" })).toBeDisabled();
  });

  it("preserves selection and reports a safe failure without claiming the Model is locked", async () => {
    setup({ failure: true });
    await userEvent.click(await screen.findByRole("radio", { name: "Select Customer" }));
    await userEvent.click(screen.getByRole("button", { name: "Lock Model" }));
    expect(await screen.findByRole("alert")).toHaveTextContent("Finish or cancel queued and running workflows");
    expect(screen.queryByText("Private detail")).not.toBeInTheDocument();
    expect(screen.getByRole("radio", { name: "Select Customer" })).toBeChecked();
    expect(screen.getByText("Unlocked")).toBeVisible();
  });
});
