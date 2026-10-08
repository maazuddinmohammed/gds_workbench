import { render, screen, waitFor, within } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { createMemoryHistory } from "@tanstack/react-router";
import { describe, expect, it, vi } from "vitest";

import { createApiClient } from "../../api";
import { createWorkbenchRouter, WorkbenchApp } from "../../app";
import type { TenantHomeRecord, TenantRole } from "../tenants/api";
import type { ModelDetail } from "./api";

const model: ModelDetail = {
  logical_coverage_threshold_percent: 70, dimensional_coverage_threshold_percent: 60,
  logical_enforce_coverage_threshold: false, dimensional_enforce_coverage_threshold: false,
  model_id: 18, tenant_id: 7, model_name: "Customer", model_description: "Customer domain", model_revision: 8,
  model_input_scope_object_count: 2, logical_schemas: [{ schema_name: "silver", description: "Shared entities" }],
  dimensional_schemas: [{ schema_name: "gold", description: null }],
  silver_model_naming_instructions: "Use snake case", silver_model_audit_columns_template: { columns: ["created_at"] },
  gold_model_naming_instructions: "Use business names", gold_model_technical_columns_template: null,
  gold_model_audit_columns_template: { columns: ["updated_at"] },
  default_agent_sdk_code: "openai_agents_sdk", default_agent_provider_code: "microsoft_foundry",
  default_agent_model_code: "foundry-primary", default_reasoning_effort_code: "medium",
  default_max_turns: 11, default_validation_retry_count: 2, is_active: true, updated_at: "2026-09-27T00:00:00Z",
  default_mapping_source_system_id: null,
  logical_entity_scd_type: "type_2",
  dimensional_entity_scd_type: "type_1",
};
const home: TenantHomeRecord = {
  tenant: { tenant_id: 7, tenant_code: "DATA", tenant_name: "Data", tenant_description: null, tenant_visibility: "private", effective_role: "architect" },
  lock: { is_locked: true, owner_display_name: "Architect", owned_by_current_principal: true, purpose: "Model settings", acquired_at: "2026-09-27T00:00:00Z", expires_at: "2026-09-27T01:00:00Z" },
  lock_actions: { can_acquire: false, can_renew: true, can_release: true, can_override: false },
  systems: [{ system_id: 41, system_code: "ASSERTIONS", system_name: "Manual assertions", system_type_name: "Manual",
    connection_count: 1, registered_object_count: 0, active_model_count: 1, last_metadata_update_time: null }],
};
const endpoint = "/api/v1/tenants/7/models/18";
function response(value: unknown, status = 200) { return new Response(JSON.stringify(value), { status, headers: { "content-type": "application/json" } }); }
function setup(options: { role?: TenantRole; locked?: boolean; ownedLock?: boolean; active?: boolean; failSave?: string; failSaveOnce?: boolean; failRefresh?: boolean; laterRevision?: number; layer?: "dimensional" } = {}) {
  let current = { ...model, is_locked: options.locked ?? false, is_active: options.active ?? true };
  let didSave = false;
  let saveAttempts = 0;
  let failRefresh = options.failRefresh ?? false;
  const fetcher = vi.fn<typeof fetch>(async (input, init) => {
    const url = String(input);
    if (url === "/api/v1/session") return response({ display_name: "Architect", email: null, actor_kind: "human", is_super_admin: false, last_tenant_id: 7 });
    if (url.endsWith("/home")) return response({ ...home, tenant: { ...home.tenant, effective_role: options.role ?? "architect" }, lock: { ...home.lock, owned_by_current_principal: options.ownedLock ?? true } });
    if (url.endsWith("/models/templates")) return response({
      silver_model_naming_instructions: "Use PascalCase. Identifiers end with ID.",
      gold_model_naming_instructions: "Use PascalCase. Keys end with Key.",
      silver_model_audit_columns_template: { schema_version: "1.0", columns: [{ semantic_name: "SourceSystemID", data_type: "BIGINT", nullable: true, definition: "Source provenance." }] },
      gold_model_audit_columns_template: { schema_version: "1.0", columns: [] },
    });
    if (url === `${endpoint}/lock` && init?.method === "PUT") {
      const command = JSON.parse(String(init.body));
      current = { ...current, is_locked: command.is_locked, model_revision: current.model_revision + 1 };
      return response({ model_id: 18, tenant_id: 7, model_revision: current.model_revision, is_active: true, updated_at: current.updated_at });
    }
    if (url === endpoint && init?.method === "PUT") {
      saveAttempts += 1;
      if (options.failSave && (!options.failSaveOnce || saveAttempts === 1)) return response({ error: { code: options.failSave, message: "sensitive untrusted detail" } }, 409);
      const { expected_model_revision: _, ...command } = JSON.parse(String(init.body));
      current = { ...current, ...command, model_revision: model.model_revision + 1 };
      didSave = true;
      return response({ model_id: 18, tenant_id: 7, model_revision: current.model_revision, is_active: true, updated_at: current.updated_at });
    }
    if (url === endpoint) {
      if (didSave && failRefresh) return response({ error: { code: "dependency_unavailable" } }, 503);
      return response(didSave && options.laterRevision ? { ...current, model_revision: options.laterRevision } : current);
    }
    if (url.endsWith("/overview")) return response({ model_id: 18, model_revision: current.model_revision, items: [] });
    if (url.endsWith("/prompts/models/18/assignments")) return response({ model_id: 18, items: [] });
    return response({ error: { code: "not_found" } }, 404);
  });
  const router = createWorkbenchRouter({ api: createApiClient(fetcher), history: createMemoryHistory({ initialEntries: [`/tenants/7/models/18/settings${options.layer ? `?layer=${options.layer}` : ""}`] }) });
  render(<WorkbenchApp router={router} />);
  return { fetcher, router, allowRefresh: () => { failRefresh = false; } };
}

describe("Model Settings", () => {
  it("saves whole-number coverage and sends blank as the database default", async () => {
    const { fetcher } = setup();
    const user = userEvent.setup();
    await screen.findByRole("heading", { name: "Definition" });
    await user.click(screen.getByText("Silver settings", { exact: true }));
    await user.click(screen.getByText("Gold settings", { exact: true }));
    const logical = screen.getByRole("spinbutton", { name: "Logical coverage threshold (%)" });
    const dimensional = screen.getByRole("spinbutton", { name: "Dimensional coverage threshold (%)" });
    expect(logical).toHaveValue(70);
    expect(dimensional).toHaveValue(60);
    expect(screen.queryByLabelText(/Gold technical columns template/)).not.toBeInTheDocument();
    await user.clear(logical);
    await user.type(logical, "69");
    await user.clear(dimensional);
    await user.click(screen.getByRole("button", { name: "Save settings" }));
    await screen.findByText("Editing revision 9.");
    const write = fetcher.mock.calls.find(([, init]) => init?.method === "PUT");
    expect(JSON.parse(String(write?.[1]?.body))).toMatchObject({
      logical_coverage_threshold_percent: 69, dimensional_coverage_threshold_percent: null,
    });
  });

  it.each(["logical", "dimensional"] as const)("saves independent %s coverage enforcement and can turn it off", async (layer) => {
    const { fetcher } = setup();
    const user = userEvent.setup();
    await screen.findByRole("heading", { name: "Definition" });
    await user.click(screen.getByText(layer === "logical" ? "Silver settings" : "Gold settings", { exact: true }));
    const name = `Enforce ${layer === "logical" ? "Logical" : "Dimensional"} coverage threshold`;
    expect(screen.getByRole("checkbox", { name })).not.toBeChecked();
    await user.click(screen.getByRole("checkbox", { name }));
    await user.click(screen.getByRole("button", { name: "Save settings" }));
    await screen.findByText("Editing revision 9.");
    let writes = fetcher.mock.calls.filter(([, init]) => init?.method === "PUT");
    expect(JSON.parse(String(writes[0]?.[1]?.body))).toMatchObject({
      logical_enforce_coverage_threshold: layer === "logical",
      dimensional_enforce_coverage_threshold: layer === "dimensional",
    });
    await user.click(screen.getByText(layer === "logical" ? "Silver settings" : "Gold settings", { exact: true }));
    expect(screen.getByRole("checkbox", { name })).toBeChecked();
    await user.click(screen.getByRole("checkbox", { name }));
    await user.click(screen.getByRole("button", { name: "Save settings" }));
    await waitFor(() => {
      writes = fetcher.mock.calls.filter(([, init]) => init?.method === "PUT");
      expect(writes).toHaveLength(2);
    });
    expect(JSON.parse(String(writes[1]?.[1]?.body))).toMatchObject({
      logical_enforce_coverage_threshold: false, dimensional_enforce_coverage_threshold: false,
    });
  });

  it.each(["69.5", "0", "101"])("rejects invalid coverage %s before saving", async (value) => {
    const { fetcher } = setup();
    const user = userEvent.setup();
    await screen.findByRole("heading", { name: "Definition" });
    await user.click(screen.getByText("Silver settings", { exact: true }));
    const logical = screen.getByRole("spinbutton", { name: "Logical coverage threshold (%)" });
    await user.clear(logical);
    await user.type(logical, value);
    await user.click(screen.getByRole("button", { name: "Save settings" }));
    expect(await screen.findByText("Enter a whole number from 1 to 100, or leave blank for the default.")).toBeVisible();
    expect(logical).toHaveFocus();
    expect(fetcher.mock.calls.some(([, init]) => init?.method === "PUT")).toBe(false);
  });

  it("keeps locked Models readable with lock actions on the Models page", async () => {
    setup({ locked: true, role: "viewer" });
    await screen.findByRole("heading", { name: "Definition" });
    expect(screen.getByText(/Model locked. Model changes and workflows/)).toBeVisible();
    expect(screen.queryByRole("button", { name: "Unlock Model" })).not.toBeInTheDocument();
    expect(screen.getByRole("button", { name: "Save settings" })).toBeDisabled();
  });

  it("shows defaults, supports customization, and saves reset as no override", async () => {
    const { fetcher } = setup();
    const user = userEvent.setup();
    await screen.findByRole("heading", { name: "Definition" });
    await user.click(screen.getByText("Silver settings", { exact: true }));
    const section = within(screen.getByText("Silver settings", { exact: true }).closest("details")!);
    await user.click(section.getAllByRole("button", { name: "Reset to defaults" })[0]!);
    const naming = section.getByRole("textbox", { name: "Silver naming instructions" });
    await waitFor(() => expect(naming).toHaveValue("Use PascalCase. Identifiers end with ID."));
    expect(naming).toHaveAttribute("readonly");
    await user.click(section.getByRole("button", { name: "Customize" }));
    await user.clear(naming);
    await user.type(naming, "Use custom naming.");
    expect(naming).toHaveValue("Use custom naming.");
    await user.click(section.getAllByRole("button", { name: "Reset to defaults" })[0]!);
    await user.click(screen.getByRole("button", { name: "Save settings" }));
    await screen.findByText("Editing revision 9.");
    const write = fetcher.mock.calls.find(([, init]) => init?.method === "PUT");
    expect(JSON.parse(String(write?.[1]?.body)).silver_model_naming_instructions).toBeNull();
  });

  it.each(["type_1", "type_2", ""] as const)("saves the selected Logical SCD policy: %s", async (scdType) => {
    const { fetcher } = setup();
    const user = userEvent.setup();
    await screen.findByRole("heading", { name: "Definition" });
    await user.click(screen.getByText("Silver settings", { exact: true }));
    const select = screen.getByRole("combobox", { name: "Logical entity SCD type" });
    expect(select).toHaveValue("type_2");
    await user.selectOptions(select, scdType);
    await user.click(screen.getByRole("button", { name: "Save settings" }));
    expect(await screen.findByRole("status")).toHaveTextContent("saved at revision 9");
    const write = fetcher.mock.calls.find(([, init]) => init?.method === "PUT");
    expect(JSON.parse(String(write?.[1]?.body))).toMatchObject({ logical_entity_scd_type: scdType || null, expected_model_revision: 8 });
  });

  it.each(["type_1", "type_2", ""] as const)("saves independent Dimensional SCD policy: %s", async (scdType) => {
    const { fetcher } = setup();
    const user = userEvent.setup();
    await screen.findByRole("heading", { name: "Definition" });
    await user.click(screen.getByText("Gold settings", { exact: true }));
    const select = screen.getByRole("combobox", { name: "Dimensional entity SCD type" });
    expect(select).toHaveValue("type_1");
    await user.selectOptions(select, scdType);
    await user.click(screen.getByRole("button", { name: "Save settings" }));
    expect(await screen.findByRole("status")).toHaveTextContent("saved at revision 9");
    const write = fetcher.mock.calls.find(([, init]) => init?.method === "PUT");
    expect(JSON.parse(String(write?.[1]?.body))).toMatchObject({
      dimensional_entity_scd_type: scdType || null, logical_entity_scd_type: "type_2", expected_model_revision: 8,
    });
    expect(screen.getByRole("combobox", { name: "Dimensional entity SCD type" })).toHaveValue(scdType);
  });

  it("retains Dimensional context while moving between Definition and Prompts", async () => {
    const { router } = setup({ layer: "dimensional" });
    const user = userEvent.setup();
    await screen.findByRole("heading", { name: "Definition" });
    await user.click(within(screen.getByRole("navigation", { name: "Model settings pages" })).getByRole("link", { name: "Prompts" }));
    await waitFor(() => expect(router.state.location.pathname).toBe("/tenants/7/models/18/settings/prompts"));
    expect(router.state.location.search).toEqual({ layer: "dimensional" });
    await user.click(within(await screen.findByRole("navigation", { name: "Model settings pages" })).getByRole("link", { name: "Definition" }));
    await screen.findByRole("heading", { name: "Definition" });
    expect(router.state.location.search).toEqual({ layer: "dimensional" });
    expect(within(screen.getByRole("navigation", { name: "Model sections" })).getByRole("link", { name: "Mapping" })).toHaveAttribute("href", "/tenants/7/mapping/models/18?layer=dimensional");
  });

  it("saves schema changes with the original revision and preserves every unopened setting", async () => {
    const { fetcher, router } = setup();
    const user = userEvent.setup();
    expect(await screen.findByRole("heading", { name: "Definition" })).toHaveFocus();
    const navigation = screen.getByRole("navigation", { name: "Model settings pages" });
    expect(within(navigation).getByRole("link", { name: "Prompts" })).toHaveAttribute("href", "/tenants/7/models/18/settings/prompts");
    const section = within(screen.getByText("Logical schemas", { exact: true }).closest("details")!);
    expect(section.getByRole("textbox", { name: "Schema name" })).toHaveAttribute("readonly");
    expect(section.getByText("Saved", { exact: true })).toBeVisible();
    await user.click(section.getByRole("button", { name: "Add schema" }));
    expect(section.getAllByRole("textbox", { name: "Schema name" })[1]).toHaveFocus();
    await user.type(section.getAllByRole("textbox", { name: "Schema name" })[1]!, " silver_sales ");
    await user.type(section.getAllByRole("textbox", { name: "Description" })[1]!, "Sales entities");
    await user.dblClick(screen.getByRole("button", { name: "Save settings" }));
    expect(await screen.findByRole("status")).toHaveTextContent("saved at revision 9");
    await screen.findByText("Editing revision 9.");
    const savedSchemas = within(screen.getByText("Logical schemas", { exact: true }).closest("details")!);
    expect(savedSchemas.getAllByText("Saved", { exact: true })).toHaveLength(2);
    expect(savedSchemas.getAllByRole("textbox", { name: "Schema name" })[1]).toHaveAttribute("readonly");
    const writes = fetcher.mock.calls.filter(([, init]) => init?.method === "PUT");
    expect(writes).toHaveLength(1);
    const { model_id: _id, tenant_id: _tenant, model_revision: _revision, model_input_scope_object_count: _scope, is_active: _active, updated_at: _updated, ...definition } = model;
    expect(JSON.parse(String(writes[0]?.[1]?.body))).toEqual({ ...definition, logical_schemas: [...model.logical_schemas, { schema_name: "silver_sales", description: "Sales entities" }], expected_model_revision: 8 });
    expect(fetcher.mock.calls.some(([input]) => String(input).endsWith("/agent-capabilities"))).toBe(false);
    await user.click(within(navigation).getByRole("link", { name: "Prompts" }));
    await waitFor(() => expect(router.state.location.pathname).toBe("/tenants/7/models/18/settings/prompts"));
    expect(await screen.findByRole("link", { name: "Definition" })).toHaveAttribute("href", "/tenants/7/models/18/settings");
  });

  it.each([
    ["viewer", true, true, "Architect permission required"],
    ["developer", true, true, "Architect permission required"],
    ["architect", false, true, "Tenant Lock required"],
    ["super_admin", true, false, "Archived Models are read-only"],
  ] as const)("keeps unavailable settings read-only: %s / lock %s / active %s", async (role, ownedLock, active, reason) => {
    const { fetcher } = setup({ role, ownedLock, active });
    await screen.findByRole("heading", { name: "Definition" });
    expect(screen.getByRole("button", { name: "Save settings" })).toBeDisabled();
    expect(screen.getByRole("textbox", { name: /Model name/ })).toBeDisabled();
    expect(screen.getByText(new RegExp(reason))).toBeVisible();
    expect(fetcher.mock.calls.some(([, init]) => init?.method === "PUT")).toBe(false);
  });

  it("preserves edits after a revision conflict and requires an explicit discard before refresh", async () => {
    const { fetcher } = setup({ failSave: "model_revision_conflict" });
    const user = userEvent.setup();
    const name = await screen.findByRole("textbox", { name: /Model name/ });
    await user.clear(name);
    await user.type(name, "Keep my changes");
    await user.click(screen.getByRole("button", { name: "Save settings" }));
    expect(await screen.findByRole("alert")).toHaveTextContent("The Model changed. Your edits are preserved.");
    expect(name).toHaveValue("Keep my changes");
    expect(screen.queryByText("sensitive untrusted detail")).not.toBeInTheDocument();
    await user.click(screen.getByRole("button", { name: "Refresh saved settings" }));
    expect(name).toHaveValue("Keep my changes");
    await user.click(screen.getByRole("button", { name: "Keep editing" }));
    expect(name).toHaveValue("Keep my changes");
    await user.click(screen.getByRole("button", { name: "Refresh saved settings" }));
    await user.click(screen.getByRole("button", { name: "Discard edits and refresh" }));
    await waitFor(() => expect(screen.getByRole("textbox", { name: /Model name/ })).toHaveValue("Customer"));
    expect(fetcher.mock.calls.filter(([, init]) => init?.method === "PUT")).toHaveLength(1);
  });

  it("explains a referenced schema conflict and preserves edits for correction without refreshing", async () => {
    const { fetcher } = setup({ failSave: "model_schema_conflict", failSaveOnce: true });
    const user = userEvent.setup();
    const name = await screen.findByRole("textbox", { name: /Model name/ });
    await user.clear(name);
    await user.type(name, "Updated customer model");
    const schemas = within(screen.getByText("Logical schemas", { exact: true }).closest("details")!);
    await user.click(schemas.getByRole("button", { name: "Edit schema" }));
    expect(schemas.getByRole("textbox", { name: "Schema name" })).toHaveFocus();
    expect(schemas.getByRole("textbox", { name: "Schema name" })).not.toHaveAttribute("readonly");
    await user.click(schemas.getByRole("button", { name: "Remove schema" }));
    await user.click(screen.getByRole("button", { name: "Save settings" }));
    expect(await screen.findByRole("alert")).toHaveTextContent("An existing Entity still uses a removed or renamed schema, including inactive Entities. Restore its schema name before saving.");
    expect(name).toHaveValue("Updated customer model");
    expect(schemas.queryByRole("textbox", { name: "Schema name" })).not.toBeInTheDocument();
    expect(screen.queryByText("sensitive untrusted detail")).not.toBeInTheDocument();
    await user.click(schemas.getByRole("button", { name: "Add schema" }));
    await user.type(schemas.getByRole("textbox", { name: "Schema name" }), "silver");
    await user.click(screen.getByRole("button", { name: "Save settings" }));
    expect(await screen.findByRole("status")).toHaveTextContent("saved at revision 9");
    const writes = fetcher.mock.calls.filter(([, init]) => init?.method === "PUT").map(([, init]) => JSON.parse(String(init?.body)));
    expect(writes).toHaveLength(2);
    expect(writes[0]).toMatchObject({ model_name: "Updated customer model", expected_model_revision: 8, logical_schemas: [] });
    expect(writes[1]).toMatchObject({ model_name: "Updated customer model", expected_model_revision: 8, logical_schemas: [{ schema_name: "silver", description: null }] });
  });

  it("keeps a confirmed save distinct from refresh failure and accepts a newer revision on retry", async () => {
    const { allowRefresh } = setup({ failRefresh: true, laterRevision: 10 });
    const user = userEvent.setup();
    await screen.findByRole("heading", { name: "Definition" });
    await user.click(screen.getByRole("button", { name: "Save settings" }));
    expect(await screen.findByRole("status")).toHaveTextContent("saved at revision 9");
    expect(await screen.findByRole("alert")).toHaveTextContent("Saved settings could not be loaded.");
    expect(screen.getByRole("button", { name: "Save settings" })).toBeDisabled();
    allowRefresh();
    await user.click(screen.getByRole("button", { name: "Refresh saved settings" }));
    await screen.findByText("Editing revision 10.");
    expect(screen.getByRole("button", { name: "Save settings" })).toBeEnabled();
  });

  it("saves and clears the default mapping System while preserving failed edits", async () => {
    const { fetcher } = setup({ failSave: "invalid_request", failSaveOnce: true });
    const user = userEvent.setup();
    await user.click(await screen.findByText("Mapping settings", { exact: true }));
    const system = await screen.findByRole("combobox", { name: /Default mapping System/ });
    await user.selectOptions(system, "41");
    await user.click(screen.getByRole("button", { name: "Save settings" }));
    expect(await screen.findByRole("alert")).toHaveTextContent("Some settings are no longer valid.");
    expect(system).toHaveValue("41");
    await user.click(screen.getByRole("button", { name: "Save settings" }));
    await screen.findByText("Editing revision 9.");
    await user.click(screen.getByText("Mapping settings", { exact: true }));
    expect(screen.getByRole("combobox", { name: /Default mapping System/ })).toHaveValue("41");
    await user.selectOptions(screen.getByRole("combobox", { name: /Default mapping System/ }), "");
    await user.click(screen.getByRole("button", { name: "Save settings" }));
    await waitFor(() => expect(fetcher.mock.calls.filter(([, init]) => init?.method === "PUT")).toHaveLength(3));
    const writes = fetcher.mock.calls.filter(([, init]) => init?.method === "PUT").map(([, init]) => JSON.parse(String(init?.body)));
    expect(writes.map((command) => command.default_mapping_source_system_id)).toEqual([41, 41, null]);
  });

  it("focuses a duplicate draft schema without changing the saved schema", async () => {
    const { fetcher } = setup();
    const user = userEvent.setup();
    await screen.findByRole("heading", { name: "Definition" });
    const schemas = within(screen.getByText("Logical schemas", { exact: true }).closest("details")!);
    await user.click(schemas.getByRole("button", { name: "Add schema" }));
    const fields = schemas.getAllByRole("textbox", { name: "Schema name" });
    await user.type(fields[1]!, "SILVER");
    await user.click(screen.getByRole("button", { name: "Save settings" }));
    expect(await screen.findByRole("alert")).toHaveTextContent("distinct, nonblank name");
    expect(fields[1]).toHaveFocus();
    expect(fields[0]).toHaveValue("silver");
    expect(fields[0]).toHaveAttribute("readonly");
    expect(fetcher.mock.calls.some(([, init]) => init?.method === "PUT")).toBe(false);
  });

  it("can explicitly clear agent defaults without fetching replacement model choices", async () => {
    const { fetcher } = setup();
    const user = userEvent.setup();
    await screen.findByRole("heading", { name: "Definition" });
    await user.click(screen.getByText("Agent defaults", { exact: true }));
    await user.selectOptions(screen.getByRole("combobox", { name: "Agent model" }), "");
    await user.click(screen.getByRole("button", { name: "Save settings" }));
    await screen.findByRole("status");
    const write = fetcher.mock.calls.find(([, init]) => init?.method === "PUT");
    expect(JSON.parse(String(write?.[1]?.body))).toMatchObject({ default_agent_sdk_code: null, default_agent_provider_code: null, default_agent_model_code: null, default_reasoning_effort_code: null, default_max_turns: null, default_validation_retry_count: null });
  });
});
