import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { render, screen, waitFor, within } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { describe, expect, it, vi } from "vitest";
import { ApiError } from "../../core/http";
import type { ModelRecordEditor } from "../model_record_review/api";
import { MappingEditor } from "./MappingEditor";

const source = { tenant_code: "T", system_code: "CRM", connection_code: "LAKE", object_schema: "bronze", object_name: "Customer" };
const other = { ...source, object_name: "Orders" };
function setup(options: { locked?: boolean; custom?: boolean; mode?: "object" | "attribute"; saved?: boolean; referenced?: boolean; json?: boolean } = {}) {
  const data: ModelRecordEditor = { model_revision: 3, label: "Customer", is_locked: options.locked ?? false, fields: [],
    mapping: { object_document: { source_tables: options.saved ? [source] : [], filter_criteria: null, custom: { keep: [false, 0] } },
      object_is_locked: options.locked ?? false, dependency_order: 1, structured: !options.custom,
      attributes: [{ name: "Name", data_type: "STRING", ordinal: 1, is_locked: false, structured: true,
        document: options.referenced ? { source_columns: [{ ...source, attribute_name: "Name" }] }
          : options.json ? { default_record: { value: 0, enabled: false } } : null }],
      source_tables: [source, other].map((reference) => ({ reference, label: `bronze.${reference.object_name}`, columns: [
        { name: "Name", data_type: "STRING", reference: { ...reference, attribute_name: "Name" } },
      ] })) } };
  const api = { readModelRecordEditor: vi.fn().mockResolvedValue(data), saveModelRecord: vi.fn().mockResolvedValue({ model_revision: 4 }) };
  render(<QueryClientProvider client={new QueryClient({ defaultOptions: { queries: { retry: false }, mutations: { retry: false } } })}>
    <MappingEditor api={api} tenantId={1} modelId={2} mappingObjectId={8} modelRevision={3} hasTenantLock mode={options.mode ?? "object"} />
  </QueryClientProvider>);
  return { api, user: userEvent.setup() };
}

describe("Mapping editors", () => {
  it("searches a collapsed table picker and saves only the Object fields, preserving additional data", async () => {
    const { api, user } = setup();
    await user.click(screen.getByRole("button", { name: "Edit Object Mapping" }));
    const dialog = await screen.findByRole("dialog", { name: "Edit Object Mapping" });
    expect(within(dialog).getByRole("button", { name: "Close Mapping editor" })).toHaveFocus();
    expect(screen.queryByRole("searchbox")).not.toBeInTheDocument();
    expect(screen.queryByLabelText("Target attribute")).not.toBeInTheDocument();
    await user.click(screen.getByRole("button", { name: "Choose source tables" }));
    await user.type(screen.getByRole("searchbox"), "customer");
    expect(screen.queryByRole("checkbox", { name: /Orders/ })).not.toBeInTheDocument();
    await user.click(screen.getByRole("checkbox", { name: /bronze.Customer/ }));
    await user.click(screen.getByRole("button", { name: "Hide source tables" }));
    expect(screen.getByText("1 source table selected")).toBeVisible();
    await user.type(screen.getByLabelText("Filter criteria"), "Active only");
    await user.type(screen.getByLabelText("Sample query"), "SELECT * FROM Customer");
    await user.click(screen.getByRole("button", { name: "Save Object Mapping" }));
    await waitFor(() => expect(api.saveModelRecord).toHaveBeenCalledOnce());
    expect(api.saveModelRecord.mock.calls[0]![2]).toEqual({ dataset: "mapping_object", record_id: 8, expected_model_revision: 3,
      changes: { object_mapping: { object_dependency_order: 1, mapping_transformation_document: {
        source_tables: [source], filter_criteria: "Active only", sample_query: "SELECT * FROM Customer", custom: { keep: [false, 0] },
      } } } });
  });

  it("offers columns only from saved Object tables and saves Attribute fields separately", async () => {
    const { api, user } = setup({ mode: "attribute", saved: true });
    await user.click(screen.getByRole("button", { name: "Edit Attribute Mapping" }));
    await screen.findByRole("dialog", { name: "Edit Attribute Mapping" });
    expect(screen.getByLabelText("Target attribute")).toHaveValue("Name");
    expect(screen.queryByLabelText("Filter criteria")).not.toBeInTheDocument();
    await user.click(screen.getByRole("button", { name: "Choose source columns" }));
    expect(screen.queryByRole("checkbox", { name: /Orders/ })).not.toBeInTheDocument();
    await user.click(screen.getByRole("checkbox", { name: /bronze.Customer · Name/ }));
    await user.type(screen.getByLabelText("Transformation logic"), "Trim Name");
    await user.type(screen.getByLabelText("Default record"), "Unknown");
    await user.click(screen.getByRole("button", { name: "Save Attribute Mapping" }));
    await waitFor(() => expect(api.saveModelRecord).toHaveBeenCalledOnce());
    expect(api.saveModelRecord.mock.calls[0]![2].changes).toEqual({ attribute_mappings: [{ modeled_attribute_name: "Name",
      attribute_mapping_transformation_document: { source_columns: [{ ...source, attribute_name: "Name" }], transformation_logic: "Trim Name", default_record: "Unknown" } }] });
  });

  it("requires saved Object tables before offering source columns", async () => {
    const { user } = setup({ mode: "attribute" });
    await user.click(screen.getByRole("button", { name: "Edit Attribute Mapping" }));
    await user.click(await screen.findByRole("button", { name: "Choose source columns" }));
    expect(screen.getByText("Save source tables in Object Mapping first.")).toBeVisible();
    expect(screen.queryByRole("checkbox")).not.toBeInTheDocument();
  });

  it("prevents removing a table used by saved Attribute mappings", async () => {
    const { api, user } = setup({ saved: true, referenced: true });
    await user.click(screen.getByRole("button", { name: "Edit Object Mapping" }));
    await user.click(await screen.findByRole("button", { name: "Remove bronze.Customer" }));
    expect(screen.getByRole("alert")).toHaveTextContent("Remove this table’s source columns");
    expect(screen.getByRole("button", { name: "Save Object Mapping" })).toBeDisabled();
    expect(api.saveModelRecord).not.toHaveBeenCalled();
  });

  it("edits JSON default records without losing their types", async () => {
    const { api, user } = setup({ mode: "attribute", json: true });
    await user.click(screen.getByRole("button", { name: "Edit Attribute Mapping" }));
    const input = await screen.findByLabelText(/Default record/);
    await user.clear(input);
    await user.paste('{"value":-1,"enabled":false}');
    await user.click(screen.getByRole("button", { name: "Save Attribute Mapping" }));
    await waitFor(() => expect(api.saveModelRecord).toHaveBeenCalledOnce());
    expect(api.saveModelRecord.mock.calls[0]![2].changes.attribute_mappings[0].attribute_mapping_transformation_document.default_record).toEqual({ value: -1, enabled: false });
  });

  it("keeps a retry identical after an uncertain save", async () => {
    const { api, user } = setup();
    api.saveModelRecord.mockRejectedValueOnce(new ApiError(503, "unavailable", null));
    await user.click(screen.getByRole("button", { name: "Edit Object Mapping" }));
    await user.type(await screen.findByLabelText("Filter criteria"), "Active");
    await user.click(screen.getByRole("button", { name: "Save Object Mapping" }));
    await screen.findByRole("button", { name: "Retry same save" });
    expect(screen.getByLabelText("Filter criteria")).toBeDisabled();
    await user.click(screen.getByRole("button", { name: "Retry same save" }));
    await waitFor(() => expect(api.saveModelRecord).toHaveBeenCalledTimes(2));
    expect(api.saveModelRecord.mock.calls[1]).toEqual(api.saveModelRecord.mock.calls[0]);
  });

  it("retains custom JSON and requires explicit discard of unsaved edits", async () => {
    const { api, user } = setup({ custom: true });
    await user.click(screen.getByRole("button", { name: "Edit Object Mapping" }));
    const input = await screen.findByLabelText(/Custom transformation document/);
    await user.clear(input);
    await user.paste('{"custom":{"answer":0,"enabled":false}}');
    await user.click(screen.getByRole("button", { name: "Cancel" }));
    expect(screen.getByText("Discard unsaved Mapping edits?")).toBeVisible();
    await user.click(screen.getByRole("button", { name: "Keep editing" }));
    await user.click(screen.getByRole("button", { name: "Save Object Mapping" }));
    await waitFor(() => expect(api.saveModelRecord).toHaveBeenCalledOnce());
    expect(api.saveModelRecord.mock.calls[0]![2].changes.object_mapping.mapping_transformation_document).toEqual({ custom: { answer: 0, enabled: false } });
  });

  it("shows locked records read-only", async () => {
    const { api, user } = setup({ locked: true });
    await user.click(screen.getByRole("button", { name: "Edit Object Mapping" }));
    expect(await screen.findByLabelText("Filter criteria")).toBeDisabled();
    expect(screen.getByRole("button", { name: "Save Object Mapping" })).toBeDisabled();
    expect(api.saveModelRecord).not.toHaveBeenCalled();
  });
});
