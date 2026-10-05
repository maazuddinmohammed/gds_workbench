import { render, screen, waitFor, within } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { createMemoryHistory } from "@tanstack/react-router";
import { afterEach, describe, expect, it, vi } from "vitest";

import { createApiClient } from "../../api";
import { WorkbenchApp, createWorkbenchRouter } from "../../app";
import type { MetadataDatasetDescription } from "./api";

describe("governed Metadata experience", () => {
  afterEach(() => vi.restoreAllMocks());

  it("opens ordered category tabs without repeating the selected sheet heading", async () => {
    const fetcher = metadataFetchStub();
    const user = userEvent.setup();
    renderMetadata(fetcher, "/tenants/7");
    await user.click(await screen.findByRole("link", { name: "Metadata" }));
    const referenceTable = await screen.findByRole("table", { name: "System Types normalized Metadata" });
    expect(within(referenceTable).getAllByRole("columnheader").map((cell) => cell.textContent)).toEqual([
      "SystemTypeCode", "SystemTypeName", "IsActive",
    ]);
    expect(screen.getByRole("heading", { name: "Metadata" })).toBeVisible();
    const navigation = screen.getByRole("navigation", { name: "Metadata catalog navigation" });
    expect(within(navigation).getAllByRole("button").map((button) => button.textContent)).toEqual(["Reference", "Foundational", "Objects", "Operational"]);
    expect(screen.queryByRole("heading", { name: "System Types" })).not.toBeInTheDocument();
    expect(screen.getByRole("button", { name: "Reference" })).toHaveAttribute("aria-current", "page");
    expect(screen.queryByRole("dialog", { name: "Import Metadata" })).not.toBeInTheDocument();
    expect(screen.queryByRole("searchbox")).not.toBeInTheDocument();
    expect(metadataRowCalls(fetcher).at(-1)).not.toContain("filters=");
    await user.click(screen.getByRole("button", { name: "Foundational" }));
    expect(screen.getByRole("button", { name: "Foundational" })).toHaveAttribute("aria-current", "page");
    expect(screen.queryByRole("button", { name: "System Types" })).not.toBeInTheDocument();
    expect(screen.getByRole("button", { name: "Connection" })).toBeVisible();
    expect(screen.queryByRole("button", { name: "Tenant Metadata Discovery Scopes" })).not.toBeInTheDocument();
  });

  it("shows read-only fields directly without redundant row details or actions", async () => {
    renderMetadata(metadataFetchStub());
    const table = await screen.findByRole("table", { name: "System Types normalized Metadata" });
    expect(within(table).queryByRole("columnheader", { name: "Actions" })).not.toBeInTheDocument();
    expect(screen.queryByRole("button", { name: "Show details" })).not.toBeInTheDocument();
    expect(screen.queryByRole("button", { name: "Add row" })).not.toBeInTheDocument();
    expect(screen.queryByRole("button", { name: "Edit row" })).not.toBeInTheDocument();
  });

  it("nests Attributes under addressable Object details and keeps them out of Operational tabs", async () => {
    const user = userEvent.setup();
    const fetcher = metadataFetchStub();
    renderMetadata(fetcher);
    await screen.findByRole("table", { name: "System Types normalized Metadata" });
    await user.click(screen.getByRole("button", { name: "Operational" }));
    expect(screen.queryByRole("button", { name: "Source Attributes" })).not.toBeInTheDocument();
    expect(screen.queryByRole("button", { name: "Source Objects" })).not.toBeInTheDocument();
    await user.click(screen.getByRole("button", { name: "Objects" }));
    const objects = await screen.findByRole("table", { name: "Physical Objects" });
    expect(within(objects).getAllByRole("columnheader").slice(0, 6).map((cell) => cell.textContent)).toEqual(["TenantCode", "SystemCode", "ConnectionCode", "ZoneCode", "ObjectSchema", "ObjectName"]);
    expect(within(objects).getByText("PLACEMENT")).toBeVisible();
    expect(screen.getByLabelText("Object state")).not.toBeVisible();
    await user.click(screen.getByRole("button", { name: "View attributes for sales.Customer" }));
    const attributes = await screen.findByRole("table", { name: "Physical Attributes for Customer" });
    expect(screen.queryByRole("table", { name: "Physical Objects" })).not.toBeInTheDocument();
    expect(within(attributes).getByText("string")).toBeVisible();
    expect(within(attributes).getByText("bigint")).toBeVisible();
    expect(within(attributes).getByText("Customer identifier")).toBeVisible();
    expect(within(attributes).getByRole("columnheader", { name: "IsSurrogateKey" })).toBeVisible();
    expect(within(attributes).getByRole("columnheader", { name: "IsNaturalKey" })).toBeVisible();
    expect(within(attributes).getByRole("columnheader", { name: "AttributeNullability" })).toBeVisible();
    expect(attributes.querySelector("details")).toBeNull();
    const objectDetails = screen.getByRole("table", { name: "Physical Object Customer" });
    expect(within(objectDetails).getAllByRole("columnheader").slice(0, 6).map((cell) => cell.textContent)).toEqual(["TenantCode", "SystemCode", "ConnectionCode", "ZoneCode", "ObjectSchema", "ObjectName"]);
    expect(within(objectDetails).getByText("Customers")).toBeVisible();
    expect(within(objectDetails).getByText("PLACEMENT")).toBeVisible();
    await user.click(screen.getByRole("button", { name: "← Objects" }));
    await screen.findByRole("table", { name: "Physical Objects" });
    expect(screen.getByRole("button", { name: "View attributes for sales.Customer" })).toHaveFocus();
  });

  it("exports all 16 sheets, including nested Attributes, without a Lock", async () => {
    const fetcher = metadataFetchStub();
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
    expect(within(dialog).getByText("Source Attributes")).toBeVisible();
    await user.click(within(dialog).getByRole("button", { name: "Export all 16" }));
    await waitFor(() => expect(findCall(fetcher, "/exports/xlsx", "POST")).toBeDefined());
    expect(JSON.parse(String(findCall(fetcher, "/exports/xlsx", "POST")?.[1]?.body))).toEqual({ schema_version: "1.0", sheet_codes: "all" });
    expect(createObjectURL).toHaveBeenCalledTimes(1);
    expect(revokeObjectURL).toHaveBeenCalledWith("blob:metadata-workbook");
  });

  it("retains the chosen workbook when the Import drawer closes and reopens", async () => {
    const fetcher = metadataFetchStub({ hasLock: true });
    const user = userEvent.setup();
    renderMetadata(fetcher);
    await screen.findByRole("table", { name: "System Types normalized Metadata" });
    const trigger = screen.getByRole("button", { name: "Import" });
    await user.click(trigger);
    expect(screen.getByRole("button", { name: "Close import" })).toHaveFocus();
    await user.click(screen.getByRole("button", { name: "Start change set" }));
    const input = screen.getByLabelText("Choose Excel");
    await waitFor(() => expect(input).toBeEnabled());
    await user.upload(input, new File([new Uint8Array([80, 75, 3, 4])], "metadata.xlsx", { type: "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet" }));
    await user.keyboard("{Escape}");
    expect(screen.queryByRole("dialog", { name: "Import Metadata" })).not.toBeInTheDocument();
    expect(trigger).toHaveFocus();
    await user.click(trigger);
    expect(input).toHaveProperty("files", expect.objectContaining({ length: 1 }));
    await user.click(screen.getByRole("button", { name: "Import Excel" }));
    await waitFor(() => expect(findCall(fetcher, "/imports/xlsx", "POST")).toBeDefined());
    expect(findCall(fetcher, "/imports/xlsx", "POST")?.[1]?.headers).toEqual(expect.objectContaining({ "content-type": "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet", "If-Match": "1" }));
    expect(await screen.findByText("Validation passed")).toBeVisible();
    await user.click(screen.getByRole("button", { name: "Apply validated changes" }));
    const confirmation = await screen.findByRole("dialog", { name: "Apply validated Metadata" });
    await user.click(within(confirmation).getByRole("button", { name: "Apply changes" }));
    await waitFor(() => expect(findCall(fetcher, "/apply", "POST")).toBeDefined());
  });

  it("keeps import locked while catalog reads remain available", async () => {
    const fetcher = metadataFetchStub();
    const user = userEvent.setup();
    renderMetadata(fetcher, "/tenants/7/metadata?variant=B");
    await screen.findByRole("table", { name: "System Types normalized Metadata" });
    await user.click(screen.getByRole("button", { name: "Import" }));
    expect(screen.getByRole("button", { name: "Start change set" })).toBeDisabled();
    expect(screen.getByLabelText("Choose Excel")).toBeDisabled();
    expect(screen.getByRole("button", { name: "Import Excel" })).toBeDisabled();
    await user.click(screen.getByRole("button", { name: "Close import" }));
    await user.click(screen.getByRole("button", { name: "Operational" }));
    expect(screen.queryByRole("button", { name: "Edit row" })).not.toBeInTheDocument();
    expect(screen.queryByRole("button", { name: "Add row" })).not.toBeInTheDocument();
    expect(findCall(fetcher, "/metadata-change-sets", "POST")).toBeUndefined();
  });

  it("retains a rejected workbook for retry and redacts the failure", async () => {
    const fetcher = metadataFetchStub({ hasLock: true, importStatus: 409 });
    const user = userEvent.setup();
    renderMetadata(fetcher);
    await screen.findByRole("table", { name: "System Types normalized Metadata" });
    await user.click(screen.getByRole("button", { name: "Import" }));
    await user.click(screen.getByRole("button", { name: "Start change set" }));
    const input = screen.getByLabelText("Choose Excel");
    await waitFor(() => expect(input).toBeEnabled());
    await user.upload(input, new File([new Uint8Array([80, 75, 3, 4])], "metadata.xlsx", { type: "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet" }));
    await user.click(screen.getByRole("button", { name: "Import Excel" }));
    expect(await screen.findByRole("alert")).toHaveTextContent("The workbook was rejected or could not be imported.");
    expect(screen.queryByText("secret-row-sentinel")).not.toBeInTheDocument();
    expect(input).toHaveProperty("files", expect.objectContaining({ length: 1 }));
    expect(screen.getByRole("button", { name: "Apply validated changes" })).toBeDisabled();
    expect(findCall(fetcher, "/apply", "POST")).toBeUndefined();
  });

  it("shows a redacted denied registry state", async () => {
    renderMetadata(metadataFetchStub({ registryStatus: 403 }));
    expect(await screen.findByRole("alert")).toHaveTextContent("You do not have permission to view this Tenant Metadata catalog.");
    expect(screen.queryByText("secret-row-sentinel")).not.toBeInTheDocument();
  });
});

function renderMetadata(fetcher: ReturnType<typeof metadataFetchStub>, path = "/tenants/7/metadata") {
  return render(<WorkbenchApp router={createWorkbenchRouter({
    api: createApiClient(fetcher),
    history: createMemoryHistory({ initialEntries: [path] }),
  })} />);
}

function metadataFetchStub(options: { hasLock?: boolean; registryStatus?: number; emptySource?: boolean; emptyCopy?: boolean; importStatus?: number } = {}) {
  let revision = 1;
  const stagedDataset = "source_object";
  let status: "active" | "validated" | "applied" | "archived" = "active";
  let stagedRecords: Array<Record<string, string | boolean>> = [];
  let validationOutcome: Record<string, unknown> | null = null;
  return vi.fn<typeof fetch>(async (input, init) => {
    const url = String(input);
    if (url === "/api/v1/tenants/7/home") return jsonResponse(homePayload(options.hasLock ?? false));
    if (url.startsWith("/api/v1/tenants/7/metadata/objects?")) return jsonResponse({ schema_version: "1.0", tenant_id: 7, items: [catalogObject], next_cursor: null });
    if (url === "/api/v1/tenants/7/metadata/objects/501") return jsonResponse(catalogObject);
    if (url === "/api/v1/tenants/7/metadata/datasets") {
      if (options.registryStatus) return errorResponse(options.registryStatus);
      return jsonResponse({ schema_version: "1.0", tenant_id: 7, datasets: registry });
    }
    if (url.includes("/metadata/datasets/") && url.includes("/rows?")) {
      const dataset = url.split("/metadata/datasets/")[1]?.split("/rows")[0];
      return jsonResponse({
        schema_version: "1.0",
        tenant_id: 7,
        dataset,
        items: dataset === "system_type"
          ? [{ system_type_code: "CRM", system_type_name: "Customer system", is_active: true }]
          : dataset === "copy" && !options.emptyCopy ? [copyRow]
          : dataset === "ingestion_object_mapping" ? [mappingRow]
          : dataset === "source_object" && !options.emptySource
            ? [{ ...objectKey, is_active: true }]
            : dataset === "source_attribute"
              ? [{ ...objectKey, attribute_name: "customer_id", attribute_data_type: "string",
                attribute_inferred_data_type: "bigint", is_locked: true, is_active: true }]
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
      return jsonResponse(changeSetDetail({ revision, status, stagedRecords, stagedDataset, validationOutcome, dataset }));
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
      if (options.importStatus) return errorResponse(options.importStatus);
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

const mappingRow = { source_connection_code: "CRM", source_object_name: "Customer", target_connection_code: "LAKE", target_object_name: "Customer", is_active: true };
const copyRow = { copy_name: "Customers", source_connection_code: "CRM", target_connection_code: "LAKE", is_active: true };
const objectKey = { tenant_code: "NWA", system_code: "CRM", connection_code: "CRM", object_schema: "sales", object_name: "Customer" };
const catalogObject = {
  tenant_code: "PLACEMENT", object_id: 501, review_revision: "a".repeat(64), object_schema: "sales", object_name: "Customer", zone_code: "source", object_type_code: "table", object_type_name: "Table",
  connection_id: 1, connection_code: "CRM", connection_name: "CRM", system_id: 1, system_code: "CRM", system_name: "CRM", source_tenant_id: 7, source_tenant_code: "NWA", source_tenant_name: "Northwind",
  attribute_count: 1, batch_attribute_name: null, is_active: true, is_locked: false, object_description: "Customers",
  attributes: [{ attribute_id: 601, review_revision: "b".repeat(64), attribute_name: "customer_id", attribute_ordinal_position: 1, attribute_description: "Customer identifier", attribute_data_type: "string", attribute_inferred_data_type: "bigint", attribute_nullability: false,
    is_surrogate_key: false, is_natural_key: true, is_meta_data: false, is_masking_required: false, is_mapped: true, is_purge: false, is_locked: false, is_active: true }],
};
const registry: MetadataDatasetDescription[] = [
  ...["project", "tenant", "system", "connection"].map((name) => descriptor(name, title(name), "foundational", [`${name}_code`, `${name}_name`])),
  descriptor("system_type", "System Types", "reference", ["system_type_code", "system_type_name", "is_active"], ["system_type_code"]),
  ...["connection_type", "object_type", "zone", "chunk_type", "file_type", "data_operation", "process_type"].map((name) => descriptor(name, title(name), "reference", [`${name}_code`, `${name}_name`])),
  descriptor("source_object", "Source Objects", "operational", [...Object.keys(objectKey), "is_active"], Object.keys(objectKey)),
  descriptor("source_attribute", "Source Attributes", "operational", [...Object.keys(objectKey), "attribute_name", "attribute_data_type", "attribute_inferred_data_type", "is_locked", "is_active"], [...Object.keys(objectKey), "attribute_name"]),
  descriptor("ingestion_object_mapping", "Ingestion Object Mappings", "operational", Object.keys(mappingRow), ["source_connection_code", "source_object_name", "target_connection_code", "target_object_name"]),
  descriptor("copy", "Copies", "operational", Object.keys(copyRow), ["copy_name"]),
  ...["bronze_object", "bronze_attribute", "silver_object", "silver_attribute", "gold_object", "gold_attribute", "ingestion_attribute_mapping", "copy_group", "member_group", "copy_group_control", "process_group", "process"].map((name) => descriptor(name, title(name), "operational", ["tenant_code", `${name}_name`, "is_active"], ["tenant_code", `${name}_name`])),
];

function changeSetDetail({ revision, status, stagedRecords, stagedDataset, validationOutcome, dataset }: { revision: number; status: string; stagedRecords: Array<Record<string, string | boolean>>; stagedDataset: string; validationOutcome: Record<string, unknown> | null; dataset: string | null }) {
  return {
    schema_version: "1.0", tenant_id: 7, metadata_change_set_id: CHANGE_SET_ID,
    status, draft_revision: revision, candidate_digest: status === "validated" ? DIGEST : null,
    validation_outcome: validationOutcome,
    dataset_counts: registry.filter((item) => item.section === "operational").map((item) => ({ dataset: item.dataset, record_count: item.dataset === stagedDataset ? stagedRecords.length : 0 })),
    dataset, records: dataset === stagedDataset ? stagedRecords : dataset ? [] : null,
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
const LATER = "2099-08-24T16:00:00Z";
const DIGEST = "a".repeat(64);
