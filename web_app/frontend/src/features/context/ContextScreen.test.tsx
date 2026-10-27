import { act, render, screen, within, waitFor } from "@testing-library/react";
import { onlineManager } from "@tanstack/react-query";
import userEvent from "@testing-library/user-event";
import { createMemoryHistory } from "@tanstack/react-router";
import { describe, expect, it, vi } from "vitest";
import { createApiClient } from "../../api";
import { WorkbenchApp, createWorkbenchRouter } from "../../app";
import { withRecordReview } from "../../test/projectRecordReview";

const recordId = "00000000-0000-4000-8000-000000000091";
const base = "/api/v1/tenants/7/projects/18";
const groupRoute = "/tenants/7/projects/18/context/groups/31";
const recordRoute = `/tenants/7/projects/18/context/records/${recordId}`;
const text = "Customer identity remains stable across CRM and ERP.";

describe("Project Context", () => {
  it("lists selectable entries with source references and direct editing", async () => {
    renderContext(contextFetchStub({ multipleRecords: true }), groupRoute);
    const table = await screen.findByRole("table", { name: "Context records" });
    expect(within(table).getByRole("columnheader", { name: "Context Record Text" })).toBeVisible();
    expect(within(table).getAllByRole("row")).toHaveLength(3);
    expect(within(table).getByRole("columnheader", { name: "Source reference" })).toBeVisible();
    expect(within(table).getAllByRole("cell", { name: "Customer rules · page 12" })).toHaveLength(2);
    expect(within(table).getByRole("checkbox", { name: `Select ${text}` })).toBeVisible();
    expect(within(table).getByRole("button", { name: `Edit ${text}` })).toBeEnabled();
    expect(within(table).getByRole("button", { name: "Edit Preserve customer history." })).toBeEnabled();
    expect(within(table).queryByRole("link")).not.toBeInTheDocument();
  });

  it("preserves collapsed group filters and reads type choices from the backend", async () => {
    const fetcher = contextFetchStub(); const user = userEvent.setup(); renderContext(fetcher);
    expect(await screen.findByRole("table", { name: "Context groups" })).toBeVisible();
    expect(screen.getByLabelText("Context Group Name prefix")).not.toBeVisible();
    await user.click(screen.getByRole("button", { name: "Filters" }));
    await user.type(screen.getByLabelText("Context Group Name prefix"), " Customer ");
    await user.selectOptions(screen.getByLabelText("Context type"), "2");
    await user.selectOptions(screen.getByLabelText("Source System"), "11");
    await user.selectOptions(screen.getByLabelText("Group activity"), "true");
    await user.click(screen.getByRole("button", { name: "Filters" }));
    await user.click(screen.getByRole("button", { name: "Filters" }));
    expect(screen.getByLabelText("Context Group Name prefix")).toHaveValue(" Customer ");
    await user.click(screen.getByRole("button", { name: "Apply Group filters" }));
    await waitFor(() => expect(fetcher).toHaveBeenCalledWith(`${base}/context/groups?context_type_id=2&source_system_id=11&active=true&name_prefix=customer&page_size=200`, expect.anything()));
    expect(screen.getByRole("button", { name: /^Filters/ })).toHaveTextContent("4");
    await user.click(screen.getByRole("link", { name: "View records in Customer governance rules" }));
    expect(await screen.findByRole("table", { name: "Context records" })).toBeVisible();
    expect(screen.queryByText(recordId)).not.toBeInTheDocument();
  });

  it("searches records and edits their full content without leaving the group", async () => {
    const fetcher = contextFetchStub({ truncated: true }); const user = userEvent.setup(); renderContext(fetcher, groupRoute);
    await screen.findByRole("table", { name: "Context records" });
    await user.click(screen.getByRole("button", { name: "Filters" }));
    await user.type(screen.getByLabelText("Search context"), " Customer ");
    await user.selectOptions(screen.getByLabelText("Record status"), "inactive");
    await user.selectOptions(screen.getByLabelText("Record lock"), "false");
    await user.click(screen.getByRole("button", { name: "Apply Record filters" }));
    await waitFor(() => expect(fetcher).toHaveBeenCalledWith(`${base}/context/records?group_id=31&status=inactive&locked=false&text_search=Customer&page_size=200`, expect.anything()));
    const edit = await screen.findByRole("button", { name: `Edit ${text}` });
    await user.click(edit);
    const dialog = await screen.findByRole("dialog", { name: "Edit context record" });
    expect(within(dialog).getByLabelText("Context Record Text")).toHaveValue(text + " Full stored content.");
    expect(within(dialog).getByLabelText("Source reference (optional)")).toHaveValue("Customer rules · page 12");
    await user.click(within(dialog).getByRole("button", { name: "Save record" }));
    await waitFor(() => expect(saveCalls(fetcher, "records")).toHaveLength(1));
    expect(JSON.parse(String(saveCalls(fetcher, "records")[0]![1]?.body))).toMatchObject({ action: "edit", context_record_id: recordId, context_text: text + " Full stored content." });
    await waitFor(() => expect(screen.queryByRole("dialog")).not.toBeInTheDocument());
    expect(screen.getByRole("table", { name: "Context records" })).toBeVisible();
    expect(edit).toHaveFocus();
  });

  it("reviews selected records from their group and clears selection when filtering", async () => {
    const { fetcher, commands } = withRecordReview(contextFetchStub({ multipleRecords: true })); const user = userEvent.setup(); renderContext(fetcher, groupRoute);
    const selectAll = await screen.findByRole("checkbox", { name: "Select loaded Context records" });
    expect(screen.queryByText("0 selected")).not.toBeVisible();
    await user.click(screen.getByRole("checkbox", { name: `Select ${text}` }));
    expect(selectAll).toBePartiallyChecked();
    await user.click(screen.getByRole("button", { name: "Lock selected" }));
    await waitFor(() => expect(commands).toHaveLength(1));
    expect(commands[0]).toMatchObject({ dataset: "context_record", record_ids: [recordId], action: "lock", expected_project_revision: 18 });
    await user.keyboard("{Escape}");
    await user.click(screen.getByRole("button", { name: "Filters" }));
    await user.click(screen.getByRole("button", { name: "Apply Record filters" }));
    expect(screen.getByRole("checkbox", { name: `Select ${text}` })).not.toBeChecked();
  });

  it("preserves direct edits and uncertain retries across reconnects", async () => {
    const fetcher = contextFetchStub({ failSaveOnce: 503 }); const user = userEvent.setup(); renderContext(fetcher, groupRoute);
    await user.click(await screen.findByRole("button", { name: `Edit ${text}` }));
    const dialog = await screen.findByRole("dialog", { name: "Edit context record" });
    await user.type(within(dialog).getByLabelText("Context Record Text"), " Preserve this edit.");
    const readsBeforeReconnect = fetcher.mock.calls.length;
    const clock = vi.spyOn(Date, "now").mockReturnValue(Date.now() + 60_000);
    try {
      await act(async () => { onlineManager.setOnline(false); onlineManager.setOnline(true); });
      expect(fetcher.mock.calls).toHaveLength(readsBeforeReconnect);
    } finally { clock.mockRestore(); }
    expect(within(dialog).getByLabelText("Context Record Text")).toHaveValue(text + " Preserve this edit.");
    await user.click(within(dialog).getByRole("button", { name: "Save record" }));
    await within(dialog).findByRole("button", { name: "Retry save" });
    await act(async () => { onlineManager.setOnline(false); onlineManager.setOnline(true); });
    expect(dialog).toBeVisible();
    await user.click(within(dialog).getByRole("button", { name: "Retry save" }));
    await waitFor(() => expect(saveCalls(fetcher, "records")).toHaveLength(2));
    const [first, second] = saveCalls(fetcher, "records");
    expect(first![1]).toEqual(second![1]);
  });

  it("keeps locked rows readable and blocks direct editing", async () => {
    renderContext(contextFetchStub({ recordLocked: true }), groupRoute);
    const edit = await screen.findByRole("button", { name: `Edit ${text}` });
    expect(edit).toBeDisabled();
    expect(edit).toHaveAttribute("title", "Unlock this record before editing.");
    expect(screen.getByRole("cell", { name: "Customer rules · page 12" })).toBeVisible();
  });

  it("creates a lean group using the backend catalog without custom classifications", async () => {
    const fetcher = contextFetchStub(); const user = userEvent.setup(); renderContext(fetcher);
    await user.click(await screen.findByRole("button", { name: "Create group" }));
    const dialog = screen.getByRole("dialog", { name: "Create context group" });
    await user.type(within(dialog).getByLabelText("Context Group Name"), "Coding standards");
    await user.selectOptions(within(dialog).getByLabelText("Context type"), "12");
    // Workflows follow the ribbon order, not the server's alphabetical order.
    expect(within(dialog).getByLabelText("Context type")).toHaveAccessibleDescription(
      "Coding conventions Used in Code generation, Validation.",
    );
    await user.type(within(dialog).getByLabelText("Context Group Description (optional)"), "SQL conventions");
    await user.selectOptions(within(dialog).getByLabelText("Source System (optional)"), "11");
    expect(within(dialog).queryByText("Custom type")).not.toBeInTheDocument();
    await user.click(within(dialog).getByRole("button", { name: "Save group" }));
    await waitFor(() => expect(saveCalls(fetcher, "groups")).toHaveLength(1));
    expect(JSON.parse(String(saveCalls(fetcher, "groups")[0]![1]?.body))).toEqual({ action: "create", expected_project_revision: 18, context_group_name: "Coding standards", context_type_id: 12, context_group_description: "SQL conventions", source_system_id: 11, is_active: true });
    expect(await screen.findByText("Group saved. Choose View records to add information to it.")).toBeVisible();
  });

  it("retries an uncertain record save with the original UUID, revision, payload, and key", async () => {
    const fetcher = contextFetchStub({ failSaveOnce: 503 }); const user = userEvent.setup(); renderContext(fetcher, groupRoute);
    await user.click(await screen.findByRole("button", { name: "Add record" }));
    const dialog = screen.getByRole("dialog", { name: "Add context record" });
    await user.type(within(dialog).getByLabelText("Context Record Text"), "Retain customer history.");
    await user.type(within(dialog).getByLabelText("Source reference (optional)"), "Review meeting");
    await user.click(within(dialog).getByRole("button", { name: "Save record" }));
    await within(dialog).findByRole("button", { name: "Retry save" });
    expect(within(dialog).getByLabelText("Context Record Text")).toBeDisabled();
    expect(within(dialog).getByRole("button", { name: "Cancel" })).toBeDisabled();
    await user.keyboard("{Escape}"); expect(dialog).toBeVisible();
    await user.click(within(dialog).getByRole("button", { name: "Retry save" }));
    await waitFor(() => expect(saveCalls(fetcher, "records")).toHaveLength(2));
    const [first, second] = saveCalls(fetcher, "records");
    expect(first![1]).toEqual(second![1]);
    const command = JSON.parse(String(first![1]?.body));
    expect(command).toEqual({ action: "create", expected_project_revision: 18, context_record_id: expect.stringMatching(/^[0-9a-f]{8}-[0-9a-f]{4}-4[0-9a-f]{3}-[89ab][0-9a-f]{3}-[0-9a-f]{12}$/), context_group_id: 31, context_text: "Retain customer history.", source_reference: "Review meeting" });
  });

  it("keeps a draft UUID after a definite rejection while changed content gets a new request key", async () => {
    const fetcher = contextFetchStub({ failSaveOnce: 422 }); const user = userEvent.setup(); renderContext(fetcher, groupRoute);
    await user.click(await screen.findByRole("button", { name: "Add record" }));
    const dialog = screen.getByRole("dialog");
    await user.type(within(dialog).getByLabelText("Context Record Text"), "First draft");
    await user.click(within(dialog).getByRole("button", { name: "Save record" }));
    await within(dialog).findByRole("alert");
    await user.type(within(dialog).getByLabelText("Context Record Text"), " revised");
    await user.click(within(dialog).getByRole("button", { name: "Save record" }));
    await waitFor(() => expect(saveCalls(fetcher, "records")).toHaveLength(2));
    const [first, second] = saveCalls(fetcher, "records");
    expect(JSON.parse(String(first![1]?.body)).context_record_id).toBe(JSON.parse(String(second![1]?.body)).context_record_id);
    expect(first![1]?.headers).not.toEqual(second![1]?.headers);
  });

  it("edits any unlocked record without an imported/manual distinction", async () => {
    const fetcher = contextFetchStub(); const user = userEvent.setup(); renderContext(fetcher, recordRoute);
    await user.click(await screen.findByRole("button", { name: "Edit record" }));
    const dialog = screen.getByRole("dialog", { name: "Edit context record" });
    expect(within(dialog).getByLabelText("Context Record Text")).toHaveValue(text);
    expect(within(dialog).queryByLabelText(/key/i)).not.toBeInTheDocument();
    await user.clear(within(dialog).getByLabelText("Context Record Text")); await user.type(within(dialog).getByLabelText("Context Record Text"), "Updated requirement");
    await user.click(within(dialog).getByRole("button", { name: "Save record" }));
    await waitFor(() => expect(saveCalls(fetcher, "records")).toHaveLength(1));
    expect(JSON.parse(String(saveCalls(fetcher, "records")[0]![1]?.body))).toMatchObject({ action: "edit", context_record_id: recordId, context_group_id: 31, context_text: "Updated requirement", source_reference: "Customer rules · page 12" });
  });

  it.each([
    { options: { hasLock: false }, reason: "Acquire the Tenant Lock before changing Context." },
    { options: { projectLocked: true }, reason: "Unlock this Project from the Projects list before changing Context." },
    { options: { recordLocked: true }, reason: "Unlock this record before editing." },
    { options: { groupInactive: true }, reason: "Activate this group before editing its records." },
    { options: { viewer: true }, reason: "Your role can view Context but cannot change it." },
  ])("explains the authoring gate: $reason", async ({ options, reason }) => {
    renderContext(contextFetchStub(options), recordRoute);
    expect(await screen.findByRole("button", { name: "Edit record" })).toBeDisabled();
    expect(screen.getByText(reason)).toBeVisible();
  });

  it("protects group settings with locked records while allowing new records", async () => {
    renderContext(contextFetchStub({ lockedRecords: 2 }), groupRoute);
    expect(await screen.findByRole("button", { name: "Edit group" })).toBeDisabled();
    expect(screen.getByText("Unlock this group's records before changing its settings.")).toBeVisible();
    expect(screen.getByRole("button", { name: "Add record" })).toBeEnabled();
  });

  it("explains an inactive group's Add record gate and retains its activation path", async () => {
    renderContext(contextFetchStub({ groupInactive: true }), groupRoute);
    expect(await screen.findByRole("button", { name: "Add record" })).toBeDisabled();
    expect(screen.getByText("Activate this group before adding records.")).toBeVisible();
    expect(screen.getByRole("button", { name: "Edit group" })).toBeEnabled();
  });

  it("edits group settings while preserving the existing group name", async () => {
    const fetcher = contextFetchStub(); const user = userEvent.setup(); renderContext(fetcher, groupRoute);
    await user.click(await screen.findByRole("button", { name: "Edit group" }));
    const dialog = screen.getByRole("dialog", { name: "Edit context group" });
    expect(within(dialog).getByLabelText("Context Group Name")).toHaveAttribute("readonly");
    await within(dialog).findByRole("option", { name: "Business Requirement" });
    expect(within(dialog).getByLabelText("Context type")).toHaveValue("2");
    expect(within(dialog).getByLabelText("Source System (optional)")).toHaveValue("11");
    await user.selectOptions(within(dialog).getByLabelText("Context type"), "12");
    await user.click(within(dialog).getByRole("button", { name: "Save group" }));
    await waitFor(() => expect(saveCalls(fetcher, "groups")).toHaveLength(1));
    expect(JSON.parse(String(saveCalls(fetcher, "groups")[0]![1]?.body))).toMatchObject({ action: "edit", context_group_id: 31, context_group_name: "Customer governance rules", context_type_id: 12 });
  });

  it("confirms discard and restores focus without losing edits after Escape", async () => {
    const user = userEvent.setup(); renderContext(contextFetchStub(), groupRoute);
    const trigger = await screen.findByRole("button", { name: "Add record" }); await user.click(trigger);
    const dialog = screen.getByRole("dialog");
    expect(within(dialog).getByRole("button", { name: "Close context editor" })).toHaveFocus();
    await user.type(within(dialog).getByLabelText("Context Record Text"), "Unsaved text"); await user.keyboard("{Escape}");
    expect(within(dialog).getByText("Discard unsaved context edits?")).toBeVisible();
    await user.click(within(dialog).getByRole("button", { name: "Keep editing" }));
    expect(within(dialog).getByLabelText("Context Record Text")).toHaveValue("Unsaved text");
    await user.click(within(dialog).getByRole("button", { name: "Cancel" })); await user.click(within(dialog).getByRole("button", { name: "Discard edits" }));
    expect(screen.queryByRole("dialog")).not.toBeInTheDocument(); expect(trigger).toHaveFocus();
  });

  it("blocks group submission while type loading fails and permits explicit retry", async () => {
    const fetcher = contextFetchStub({ failTypes: 2 }); const user = userEvent.setup(); renderContext(fetcher);
    await screen.findByRole("table", { name: "Context groups" });
    await user.click(screen.getByRole("button", { name: "Create group" }));
    const dialog = screen.getByRole("dialog");
    await within(dialog).findByRole("button", { name: "Retry types" });
    expect(within(dialog).getByRole("button", { name: "Save group" })).toBeDisabled();
    await user.click(within(dialog).getByRole("button", { name: "Retry types" }));
    expect(await within(dialog).findByRole("option", { name: "Code Context" })).toBeInTheDocument();
  });

  it("retains explicit empty/error/revision states and manual refresh", async () => {
    const user = userEvent.setup(); const fetcher = contextFetchStub({ empty: true });
    const first = renderContext(fetcher); await screen.findByText("No Context groups yet. Create a group to organize requirements, decisions, and other information.");
    const before = fetcher.mock.calls.filter(([input]) => String(input).includes("/context/groups?")).length;
    await user.click(screen.getByRole("button", { name: "Refresh" }));
    await waitFor(() => expect(fetcher.mock.calls.filter(([input]) => String(input).includes("/context/groups?"))).toHaveLength(before + 1)); first.unmount();
    const second = renderContext(contextFetchStub({ revision: 19 }));
    expect(await screen.findByRole("alert")).toHaveTextContent("Project changed"); second.unmount();
    renderContext(contextFetchStub({ error: true })); expect(await screen.findByRole("alert")).toHaveTextContent("Context groups could not be loaded");
  });

  it("guides the first record and prevents saving an empty record", async () => {
    const fetcher = contextFetchStub({ empty: true }); const user = userEvent.setup(); renderContext(fetcher, groupRoute);
    expect(await screen.findByText("No Context records yet. Use Add record to capture information in this group.")).toBeVisible();
    await user.click(screen.getByRole("button", { name: "Add record" }));
    const dialog = screen.getByRole("dialog", { name: "Add context record" });
    await user.click(within(dialog).getByRole("button", { name: "Save record" }));
    expect(saveCalls(fetcher, "records")).toHaveLength(0);
    expect(within(dialog).getByLabelText("Context Record Text")).toBeInvalid();
    await user.type(within(dialog).getByLabelText("Context Record Text"), "Keep customer identifiers stable.");
    await user.click(within(dialog).getByRole("button", { name: "Save record" }));
    await waitFor(() => expect(saveCalls(fetcher, "records")).toHaveLength(1));
    await waitFor(() => expect(screen.queryByRole("dialog")).not.toBeInTheDocument());
  });

  it("distinguishes empty filtered results from first use", async () => {
    const user = userEvent.setup(); renderContext(contextFetchStub({ empty: true }));
    await screen.findByText("No Context groups yet. Create a group to organize requirements, decisions, and other information.");
    await user.click(screen.getByRole("button", { name: "Filters" }));
    await user.type(screen.getByLabelText("Context Group Name prefix"), "Missing");
    await user.click(screen.getByRole("button", { name: "Apply Group filters" }));
    expect(await screen.findByText("No Context groups match these filters.")).toBeVisible();
  });

  it("keeps UUID Context record selection in governed review commands", async () => {
    const { fetcher, commands } = withRecordReview(contextFetchStub()); const user = userEvent.setup(); renderContext(fetcher, recordRoute);
    const more = await screen.findByText("More", { selector: "summary" });
    expect(more.closest("details")).not.toHaveAttribute("open");
    await user.click(more);
    expect(screen.queryByRole("button", { name: "Unlock" })).not.toBeInTheDocument();
    expect(screen.queryByRole("button", { name: "Activate" })).not.toBeInTheDocument();
    await user.click(screen.getByRole("button", { name: "Lock" }));
    await waitFor(() => expect(commands).toHaveLength(1));
    expect(commands[0]).toEqual({ dataset: "context_record", record_ids: [recordId], action: "lock", expected_project_revision: 18 });
  });

  it("keeps record refresh in More and restores focus when the menu closes", async () => {
    const fetcher = contextFetchStub(); const user = userEvent.setup(); renderContext(fetcher, recordRoute);
    const more = await screen.findByText("More", { selector: "summary" });
    const before = fetcher.mock.calls.filter(([url]) => String(url) === `${base}/context/records/${recordId}`).length;
    await user.click(more);
    await user.click(screen.getByRole("button", { name: "Refresh" }));
    await waitFor(() => expect(fetcher.mock.calls.filter(([url]) => String(url) === `${base}/context/records/${recordId}`)).toHaveLength(before + 1));
    await user.keyboard("{Escape}");
    expect(more.closest("details")).not.toHaveAttribute("open");
    expect(more).toHaveFocus();
  });
});

function renderContext(fetcher: typeof fetch, path = "/tenants/7/projects/18/context") {
  return render(<WorkbenchApp router={createWorkbenchRouter({ api: createApiClient(fetcher), history: createMemoryHistory({ initialEntries: [path] }) })} />);
}
function saveCalls(fetcher: ReturnType<typeof contextFetchStub>, kind: string) { return fetcher.mock.calls.filter(([url]) => String(url).endsWith(`/change-sets/context-${kind}`)); }
function contextFetchStub(options: { empty?: boolean; multipleRecords?: boolean; truncated?: boolean; error?: boolean; revision?: number; failSaveOnce?: number; hasLock?: boolean; projectLocked?: boolean; recordLocked?: boolean; groupInactive?: boolean; failTypes?: number; lockedRecords?: number; viewer?: boolean } = {}) {
  let saves = 0; let typeReads = 0;
  return vi.fn<typeof fetch>(async (input) => {
    const url = String(input); const group = { ...groupPayload, is_active: !options.groupInactive, locked_record_count: options.lockedRecords ?? 0 };
    if (url === "/api/v1/tenants/7/home") return jsonResponse({ ...tenantHomePayload, tenant: { ...tenantHomePayload.tenant, effective_role: options.viewer ? "viewer" : "tenant_admin" }, lock: { ...tenantHomePayload.lock, owned_by_current_principal: options.hasLock ?? true } });
    if (url === base) return jsonResponse({ ...projectPayload, is_locked: options.projectLocked ?? false });
    if (url === `${base}/overview`) return jsonResponse({ ...projectPayload, workflows: [], sections: [] });
    if (url.startsWith(`${base}/context/source-systems?`)) return jsonResponse({ items: [sourceSystem], next_cursor: null });
    if (url === `${base}/context/types`) {
      if (options.failTypes && typeReads++ < options.failTypes) return jsonResponse({ error: { code: "unavailable" } }, 503);
      return jsonResponse({ items: [businessType, { context_type_id: 12, context_type_name: "Code Context", context_type_description: "Coding conventions", context_type_workflows: ["validation", "code_generation"] }] });
    }
    if (url.startsWith(`${base}/context/groups?`)) return options.error ? jsonResponse({ error: { code: "unavailable" } }, 503) : jsonResponse({ project_id: 18, project_revision: options.revision ?? 18, items: options.empty ? [] : [group], next_cursor: null });
    if (url === `${base}/context/groups/31`) return jsonResponse(group);
    const record = { context_record_id: recordId, group, context_text_preview: text, text_truncated: options.truncated ?? false, source_reference_preview: "Customer rules · page 12", source_reference_truncated: false, context_text: options.truncated ? text + " Full stored content." : text, source_reference: "Customer rules · page 12", status: "active", is_locked: options.recordLocked ?? false, updated_at: "2026-08-24T14:30:00Z", created_at: "2026-08-24T14:10:00Z" };
    if (url.startsWith(`${base}/context/records?`)) return jsonResponse({ project_id: 18, project_revision: options.revision ?? 18, items: options.empty ? [] : options.multipleRecords ? [record, { ...record, context_record_id: "00000000-0000-4000-8000-000000000092", context_text_preview: "Preserve customer history." }] : [record], next_cursor: null });
    if (url === `${base}/context/records/${recordId}`) return jsonResponse(record);
    if (url.includes("/change-sets/context-")) {
      if (options.failSaveOnce && saves++ === 0) return jsonResponse({ error: { code: "invalid_request", message: "Review the save." } }, options.failSaveOnce);
      return jsonResponse({ project_id: 18, project_revision: 19, project_change_set_id: "saved", action_count: 1 });
    }
    return jsonResponse({ error: { code: "not_found" } }, 404);
  });
}
function jsonResponse(value: unknown, status = 200) { return new Response(JSON.stringify(value), { status, headers: { "content-type": "application/json" } }); }
const sourceSystem = { system_id: 11, system_code: "CRM", system_name: "Customer Relationship Management" };
const businessType = { context_type_id: 2, context_type_name: "Business Requirement", context_type_description: null };
const groupPayload = { context_group_id: 31, context_group_name: "Customer governance rules", context_group_description: "Customer domain requirements.", context_type: businessType, source_system: sourceSystem, is_active: true, record_count: 12, active_record_count: 10, locked_record_count: 4, updated_at: "2026-08-24T14:20:00Z", created_at: "2026-08-24T14:00:00Z" };
const tenantHomePayload = {
  tenant: { tenant_id: 7, tenant_code: "NWA", tenant_name: "Northwind Analytics", tenant_description: null, tenant_visibility: "private", effective_role: "tenant_admin" },
  lock: { is_locked: true, owner_display_name: "Maaz", owned_by_current_principal: true, purpose: "Project authoring", acquired_at: "2026-08-24T14:12:00Z", expires_at: "2026-08-24T16:12:00Z" },
  lock_actions: { can_acquire: false, can_renew: true, can_release: true, can_override: false }, systems: [],
};
const projectPayload = { project_id: 18, tenant_id: 7, project_name: "Customer 360", project_description: "Customer domain", project_revision: 18, project_input_scope_object_count: 25, logical_schemas: [], dimensional_schemas: [], silver_model_naming_instructions: null, silver_model_audit_columns_template: null, gold_model_naming_instructions: null, gold_model_technical_columns_template: null, gold_model_audit_columns_template: null, default_agent_sdk_code: null, default_agent_provider_code: null, default_agent_model_code: null, default_reasoning_effort_code: null, default_max_turns: null, default_validation_retry_count: null, is_active: true, updated_at: "2026-08-24T14:00:00Z" };
