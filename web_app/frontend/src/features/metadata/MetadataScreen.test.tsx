import { render, screen, waitFor, within } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { createMemoryHistory } from "@tanstack/react-router";
import { afterEach, describe, expect, it, vi } from "vitest";

import { createApiClient } from "../../api";
import { WorkbenchApp, createWorkbenchRouter } from "../../app";
import type { MetadataDatasetDescription } from "./api";

describe("governed Metadata experience", () => {
  afterEach(() => vi.restoreAllMocks());

  it("opens from active shell navigation and uses registry-driven sections, columns, and exact filters", async () => {
    const fetcher = metadataFetchStub();
    const user = userEvent.setup();
    renderMetadata(fetcher, "/tenants/7");

    const link = await screen.findByRole("link", { name: "Metadata" });
    expect(link).toHaveAttribute("href", "/tenants/7/metadata");
    await user.click(link);

    expect(await screen.findByRole("heading", { name: "Metadata" })).toBeVisible();
    expect(screen.getByRole("button", { name: /Reference 8 sheets/ })).toHaveAttribute("aria-current", "page");
    expect(screen.getByRole("button", { name: /Foundational 5 sheets/ })).toBeVisible();
    expect(screen.getByRole("button", { name: /Operational 16 sheets/ })).toBeVisible();
    const table = await screen.findByRole("table", { name: "System Types normalized Metadata" });
    expect(within(table).getByRole("columnheader", { name: "System Type Code" })).toBeVisible();
    expect(within(table).getByText("CRM")).toBeVisible();
    expect(screen.queryByRole("searchbox")).not.toBeInTheDocument();

    await user.type(screen.getByLabelText("System Type Code filter"), "CRM");
    await user.click(screen.getByRole("button", { name: "Apply sheet filters" }));
    await waitFor(() => expect(metadataRowCalls(fetcher).at(-1)).toContain(
      "filters=%7B%22system_type_code%22%3A%22CRM%22%7D",
    ));
  });

  it("opens an ample keyboard-closeable row detail and keeps read-only sections immutable", async () => {
    const fetcher = metadataFetchStub();
    const user = userEvent.setup();
    renderMetadata(fetcher);

    await screen.findByRole("table", { name: "System Types normalized Metadata" });
    expect(screen.getByText("Read-only view")).toBeVisible();
    expect(screen.getByText("Read-only", { selector: ".metadata-readonly-badge" })).toBeVisible();
    expect(screen.queryByRole("button", { name: "Add row" })).not.toBeInTheDocument();
    await user.click(screen.getByRole("button", { name: "Show details" }));
    const detail = await screen.findByRole("dialog", { name: "Row details" });
    expect(within(detail).getByText("Natural key")).toBeVisible();
    expect(within(detail).getByRole("button", { name: "Close Metadata row details" })).toHaveFocus();
    await user.keyboard("{Escape}");
    expect(screen.queryByRole("dialog", { name: "Row details" })).not.toBeInTheDocument();
  });

  it("stages a typed complete Operational row, validates review, and explicitly applies it", async () => {
    const fetcher = metadataFetchStub({ hasLock: true });
    const user = userEvent.setup();
    renderMetadata(fetcher);

    await screen.findByRole("table", { name: "System Types normalized Metadata" });
    await user.click(screen.getByRole("button", { name: /Operational 16 sheets/ }));
    await screen.findByRole("table", { name: "Source Objects normalized Metadata" });
    await user.click(screen.getByRole("button", { name: "Start or resume" }));
    await waitFor(() => expect(screen.getByRole("button", { name: "Add row" })).toBeEnabled());
    await user.click(screen.getByRole("button", { name: "Show details" }));
    await user.click(screen.getByRole("button", { name: "Edit row" }));
    const editor = await screen.findByRole("dialog", { name: "Edit Source Objects row" });
    expect(within(editor).getByLabelText("Tenant Code")).toBeDisabled();
    await user.selectOptions(within(editor).getByLabelText("Is Active"), "false");
    await user.click(within(editor).getByRole("button", { name: "Stage complete row" }));

    await waitFor(() => expect(findCall(fetcher, "/stage", "PUT")).toBeDefined());
    const stageCall = findCall(fetcher, "/stage", "PUT");
    expect(JSON.parse(String(stageCall?.[1]?.body))).toEqual({
      schema_version: "1.0",
      expected_draft_revision: 1,
      changes: [{
        dataset: "source_object",
        records: [{ tenant_code: "NWA", object_name: "Customer", is_active: false }],
      }],
    });
    await user.click(await screen.findByRole("button", { name: "Validate" }));
    expect(await screen.findByText("Validation passed")).toBeVisible();
    await user.click(screen.getByRole("button", { name: "Apply validated changes" }));
    const confirmation = await screen.findByRole("dialog", { name: "Apply validated Metadata" });
    expect(within(confirmation).getByRole("button", { name: "Close Metadata confirmation" })).toHaveFocus();
    await user.click(within(confirmation).getByRole("button", { name: "Apply changes" }));
    await waitFor(() => expect(findCall(fetcher, "/apply", "POST")).toBeDefined());
  });

  it("adds a complete row to an empty Operational sheet from canonical field schema", async () => {
    const fetcher = metadataFetchStub({ hasLock: true, emptySource: true });
    const user = userEvent.setup();
    renderMetadata(fetcher);

    await screen.findByRole("table", { name: "System Types normalized Metadata" });
    await user.click(screen.getByRole("button", { name: /Operational 16 sheets/ }));
    expect(await screen.findByText("No rows match this sheet’s server filters.")).toBeVisible();
    await user.click(screen.getByRole("button", { name: "Start or resume" }));
    const add = await screen.findByRole("button", { name: "Add row" });
    await waitFor(() => expect(add).toBeEnabled());
    await user.click(add);
    const editor = await screen.findByRole("dialog", { name: "Add Source Objects row" });
    await user.type(within(editor).getByLabelText("Tenant Code"), "NWA");
    await user.type(within(editor).getByLabelText("Object Name"), "Orders");
    await user.selectOptions(within(editor).getByLabelText("Is Active"), "true");
    await user.click(within(editor).getByRole("button", { name: "Stage complete row" }));

    await waitFor(() => expect(findCall(fetcher, "/stage", "PUT")).toBeDefined());
    expect(JSON.parse(String(findCall(fetcher, "/stage", "PUT")?.[1]?.body))).toEqual({
      schema_version: "1.0",
      expected_draft_revision: 1,
      changes: [{
        dataset: "source_object",
        records: [{ tenant_code: "NWA", object_name: "Orders", is_active: true }],
      }],
    });
  });

  it("exports all server-registered Operational sheets without a Lock", async () => {
    const fetcher = metadataFetchStub({ hasLock: false });
    const user = userEvent.setup();
    const createObjectURL = vi.fn(() => "blob:metadata-workbook");
    const revokeObjectURL = vi.fn();
    vi.spyOn(HTMLAnchorElement.prototype, "click").mockImplementation(() => undefined);
    Object.defineProperty(URL, "createObjectURL", { configurable: true, value: createObjectURL });
    Object.defineProperty(URL, "revokeObjectURL", { configurable: true, value: revokeObjectURL });
    renderMetadata(fetcher);

    await screen.findByRole("table", { name: "System Types normalized Metadata" });
    await user.click(screen.getByRole("button", { name: "Export Excel" }));
    const dialog = await screen.findByRole("dialog", { name: "Export Excel workbook" });
    expect(within(dialog).getByText("16 canonical sheets.")).toBeVisible();
    await user.click(within(dialog).getByRole("button", { name: "Export all 16" }));
    await waitFor(() => expect(findCall(fetcher, "/exports/xlsx", "POST")).toBeDefined());
    const exportCall = findCall(fetcher, "/exports/xlsx", "POST");
    expect(JSON.parse(String(exportCall?.[1]?.body))).toEqual({
      schema_version: "1.0",
      sheet_codes: "all",
    });
    expect(createObjectURL).toHaveBeenCalledTimes(1);
    expect(revokeObjectURL).toHaveBeenCalledWith("blob:metadata-workbook");
  });

  it("imports only a bounded .xlsx into an owned active Change Set", async () => {
    const fetcher = metadataFetchStub({ hasLock: true });
    const user = userEvent.setup();
    renderMetadata(fetcher);

    await screen.findByRole("table", { name: "System Types normalized Metadata" });
    await user.click(screen.getByRole("button", { name: /Operational 16 sheets/ }));
    await screen.findByRole("table", { name: "Source Objects normalized Metadata" });
    await user.click(screen.getByRole("button", { name: "Start or resume" }));
    const input = await screen.findByLabelText("Import governed .xlsx");
    const file = new File([new Uint8Array([80, 75, 3, 4])], "metadata.xlsx", {
      type: "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
    });
    await user.upload(input, file);
    await user.click(screen.getByRole("button", { name: "Import and validate" }));
    await waitFor(() => expect(findCall(fetcher, "/imports/xlsx", "POST")).toBeDefined());
    expect(findCall(fetcher, "/imports/xlsx", "POST")?.[1]?.headers).toEqual(expect.objectContaining({
      "content-type": "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
      "If-Match": "1",
    }));
    expect(await screen.findByText("Validation passed")).toBeVisible();
    await user.click(screen.getByRole("button", { name: "Archive" }));
    const confirmation = await screen.findByRole("dialog", { name: "Archive Change Set" });
    await user.click(within(confirmation).getByRole("button", { name: "Archive draft" }));
    await waitFor(() => expect(findCall(fetcher, "/archive", "POST")).toBeDefined());
  });

  it("shows a redacted denied registry state", async () => {
    const fetcher = metadataFetchStub({ registryStatus: 403 });
    renderMetadata(fetcher);
    expect(await screen.findByRole("alert")).toHaveTextContent(
      "You do not have permission to view this Tenant Metadata catalog.",
    );
    expect(screen.queryByText("secret-row-sentinel")).not.toBeInTheDocument();
  });
});

function renderMetadata(fetcher: ReturnType<typeof metadataFetchStub>, path = "/tenants/7/metadata") {
  return render(<WorkbenchApp router={createWorkbenchRouter({
    api: createApiClient(fetcher),
    history: createMemoryHistory({ initialEntries: [path] }),
  })} />);
}

function metadataFetchStub(options: { hasLock?: boolean; registryStatus?: number; emptySource?: boolean } = {}) {
  let revision = 1;
  let status: "active" | "validated" | "applied" | "archived" = "active";
  let stagedRecords: Array<Record<string, string | boolean>> = [];
  let validationOutcome: Record<string, unknown> | null = null;
  return vi.fn<typeof fetch>(async (input, init) => {
    const url = String(input);
    if (url === "/api/v1/tenants/7/home") return jsonResponse(homePayload(options.hasLock ?? false));
    if (url === "/api/v1/tenants/7/metadata/datasets") {
      if (options.registryStatus) return errorResponse(options.registryStatus);
      return jsonResponse({ schema_version: "1.0", tenant_id: 7, datasets: registry });
    }
    if (url.includes("/metadata/datasets/") && !url.includes("/rows?")) {
      const dataset = url.split("/metadata/datasets/")[1] ?? "";
      const item = registry.find((candidate) => candidate.dataset === dataset);
      if (!item) return errorResponse(404);
      return jsonResponse({
        ...item,
        schema_version: "1.0",
        tenant_id: 7,
        row_schema: {
          type: "object",
          additionalProperties: false,
          properties: Object.fromEntries(item.columns.map((field) => [
            field,
            field === "is_active"
              ? { type: "boolean", title: "Is Active" }
              : { type: "string", minLength: 1, maxLength: 400, title: title(field) },
          ])),
          required: item.columns,
        },
      });
    }
    if (url.includes("/metadata/datasets/") && url.includes("/rows?")) {
      const dataset = url.split("/metadata/datasets/")[1]?.split("/rows")[0];
      return jsonResponse({
        schema_version: "1.0",
        tenant_id: 7,
        dataset,
        items: dataset === "system_type"
          ? [{ system_type_code: "CRM", system_type_name: "Customer system", is_active: true }]
          : dataset === "source_object" && !options.emptySource
            ? [{ tenant_code: "NWA", object_name: "Customer", is_active: true }]
            : [],
        next_cursor: null,
      });
    }
    if (url.endsWith("/metadata/exports/xlsx") && init?.method === "POST") {
      return new Response(new Uint8Array([80, 75, 3, 4]), {
        headers: {
          "content-type": "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
          "content-disposition": "attachment; filename=\"gds_operational_metadata__tenant_7__16_sheets.xlsx\"",
          "x-gds-sheet-count": "16",
        },
      });
    }
    if (url.endsWith("/metadata-change-sets") && init?.method === "POST") {
      return jsonResponse({
        schema_version: "1.0", tenant_id: 7, metadata_change_set_id: CHANGE_SET_ID,
        created: true, status: "active", draft_revision: revision,
        created_at: NOW, expires_at: LATER,
      }, 201);
    }
    if (url.includes(`/metadata-change-sets/${CHANGE_SET_ID}`) && init?.method === undefined) {
      const dataset = new URL(url, "http://workbench.local").searchParams.get("dataset");
      return jsonResponse(changeSetDetail({ revision, status, stagedRecords, validationOutcome, dataset }));
    }
    if (url.endsWith("/stage") && init?.method === "PUT") {
      const command = JSON.parse(String(init.body)) as { changes: Array<{ records: typeof stagedRecords }> };
      stagedRecords = command.changes[0]?.records ?? [];
      revision += 1;
      status = "active";
      validationOutcome = null;
      return jsonResponse({ schema_version: "1.0", tenant_id: 7, metadata_change_set_id: CHANGE_SET_ID, staged: true, datasets: [{ dataset: "source_object", record_count: stagedRecords.length }], draft_revision: revision, status: "active", expires_at: LATER });
    }
    if (url.endsWith("/validate") && init?.method === "POST") {
      status = "validated";
      validationOutcome = validationPayload(stagedRecords.length || 1);
      return jsonResponse({ ...validationOutcome, schema_version: "1.0", tenant_id: 7, metadata_change_set_id: CHANGE_SET_ID, status, draft_revision: revision, candidate_digest: DIGEST, validated_at: NOW, expires_at: LATER });
    }
    if (url.endsWith("/apply") && init?.method === "POST") {
      status = "applied";
      return jsonResponse({ ...validationPayload(stagedRecords.length || 1), schema_version: "1.0", tenant_id: 7, metadata_change_set_id: CHANGE_SET_ID, status, draft_revision: revision, candidate_digest: DIGEST, applied: true, action_count: 1, applied_at: NOW });
    }
    if (url.endsWith("/archive") && init?.method === "POST") {
      status = "archived";
      return jsonResponse({ schema_version: "1.0", tenant_id: 7, metadata_change_set_id: CHANGE_SET_ID, archived: true, status, draft_revision: revision, archived_at: NOW });
    }
    if (url.endsWith("/imports/xlsx") && init?.method === "POST") {
      stagedRecords = [{ tenant_code: "NWA", object_name: "Imported", is_active: true }];
      revision += 1;
      status = "validated";
      validationOutcome = validationPayload(1);
      return jsonResponse({
        schema_version: "1.0", tenant_id: 7, metadata_change_set_id: CHANGE_SET_ID,
        imported_sheet_count: 1,
        staged: { schema_version: "1.0", tenant_id: 7, metadata_change_set_id: CHANGE_SET_ID, staged: true, datasets: [{ dataset: "source_object", record_count: 1 }], draft_revision: revision, status: "active", expires_at: LATER },
        validation: { ...validationOutcome, schema_version: "1.0", tenant_id: 7, metadata_change_set_id: CHANGE_SET_ID, status: "validated", draft_revision: revision, candidate_digest: DIGEST, validated_at: NOW, expires_at: LATER },
      });
    }
    return errorResponse(404);
  });
}

function descriptor(dataset: string, label: string, section: MetadataDatasetDescription["section"], columns: string[], naturalKey = [columns[0] ?? "code"]): MetadataDatasetDescription {
  return { dataset, label, section, change_set_eligible: section === "operational", read_only: section !== "operational", columns, natural_key: naturalKey, filter_fields: naturalKey };
}

const registry: MetadataDatasetDescription[] = [
  ...["project", "tenant", "system", "connection", "tenant_metadata_discovery_scope"].map((name) => descriptor(name, title(name), "foundational", [`${name}_code`, `${name}_name`])),
  descriptor("system_type", "System Types", "reference", ["system_type_code", "system_type_name", "is_active"], ["system_type_code"]),
  ...["connection_type", "object_type", "zone", "chunk_type", "file_type", "data_operation", "process_type"].map((name) => descriptor(name, title(name), "reference", [`${name}_code`, `${name}_name`])),
  descriptor("source_object", "Source Objects", "operational", ["tenant_code", "object_name", "is_active"], ["tenant_code", "object_name"]),
  ...["source_attribute", "bronze_object", "bronze_attribute", "silver_object", "silver_attribute", "gold_object", "gold_attribute", "ingestion_object_mapping", "ingestion_attribute_mapping", "copy_group", "member_group", "copy_group_control", "copy", "process_group", "process"].map((name) => descriptor(name, title(name), "operational", ["tenant_code", `${name}_name`, "is_active"], ["tenant_code", `${name}_name`])),
];

function changeSetDetail({ revision, status, stagedRecords, validationOutcome, dataset }: { revision: number; status: string; stagedRecords: Array<Record<string, string | boolean>>; validationOutcome: Record<string, unknown> | null; dataset: string | null }) {
  return {
    schema_version: "1.0", tenant_id: 7, metadata_change_set_id: CHANGE_SET_ID,
    status, draft_revision: revision, candidate_digest: status === "validated" ? DIGEST : null,
    validation_outcome: validationOutcome,
    dataset_counts: registry.filter((item) => item.section === "operational").map((item) => ({ dataset: item.dataset, record_count: item.dataset === "source_object" ? stagedRecords.length : 0 })),
    dataset, records: dataset === "source_object" ? stagedRecords : dataset ? [] : null,
    created_at: NOW, last_activity_at: NOW, expires_at: LATER,
    validated_at: status === "validated" ? NOW : null, applied_at: status === "applied" ? NOW : null,
    terminal_at: status === "applied" || status === "archived" ? NOW : null,
  };
}

function validationPayload(count: number) {
  return { valid: true, phase: "complete", staged_record_count: count, error_count: 0, errors: [], action_review: [{ dataset: "source_object", insert_count: 0, update_count: count, deactivate_count: 0, reactivate_count: 0, no_change_count: 0, keys: [], keys_truncated: false }] };
}

function homePayload(hasLock: boolean) {
  return {
    tenant: { tenant_id: 7, tenant_code: "NWA", tenant_name: "Northwind Analytics", tenant_description: null, tenant_visibility: "private", effective_role: "developer" },
    lock: { is_locked: hasLock, owner_display_name: hasLock ? "Maaz" : null, owned_by_current_principal: hasLock ? true : null, purpose: hasLock ? "Metadata review" : null, acquired_at: hasLock ? NOW : null, expires_at: hasLock ? LATER : null },
    lock_actions: { can_acquire: !hasLock, can_renew: hasLock, can_release: hasLock, can_override: false }, systems: [],
  };
}

function title(value: string) { return value.replaceAll("_", " ").replace(/\b\w/g, (character) => character.toUpperCase()); }
function metadataRowCalls(fetcher: ReturnType<typeof metadataFetchStub>) { return fetcher.mock.calls.map(([input]) => String(input)).filter((url) => url.includes("/metadata/datasets/") && url.includes("/rows?")); }
function findCall(fetcher: ReturnType<typeof metadataFetchStub>, suffix: string, method: string) { return fetcher.mock.calls.find(([input, init]) => String(input).endsWith(suffix) && init?.method === method); }
function jsonResponse(value: unknown, status = 200) { return new Response(JSON.stringify(value), { status, headers: { "content-type": "application/json" } }); }
function errorResponse(status: number) { return jsonResponse({ error: { code: "request_failed", message: "secret-row-sentinel" } }, status); }

const CHANGE_SET_ID = "11111111-1111-1111-1111-111111111111";
const NOW = "2026-08-24T12:00:00Z";
const LATER = "2026-08-24T16:00:00Z";
const DIGEST = "a".repeat(64);
