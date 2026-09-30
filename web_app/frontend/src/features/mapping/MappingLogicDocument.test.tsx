import { render, screen, within } from "@testing-library/react";
import { describe, expect, it } from "vitest";
import { MappingDocumentValue } from "./MappingDocumentView";
import { MappingLogicDocument } from "./MappingLogicDocument";

describe("Mapping logic documents", () => {
  it("orders source identities consistently even when stored Object keys are shuffled", () => {
    const document = { source_objects: [
      { alias: "c", object_name: "customer", system_code: "CRM", tenant_code: "EXAMPLE",
        object_schema: "bronze_crm", custom_note: "Keep this note", connection_code: "lakehouse" },
      { connection_code: "warehouse", object_schema: "bronze_erp", tenant_code: "EXAMPLE",
        system_code: "ERP", object_name: "account", alias: "a", nullable: null },
    ] };
    const original = JSON.stringify(document);
    render(<MappingLogicDocument path="Entity logic" document={document} />);
    const table = screen.getByRole("table", { name: 'Entity logic["source_objects"]' });
    expect(within(table).getAllByRole("columnheader").map((column) => column.textContent)).toEqual([
      "Object schema", "Object name", "Alias", "Custom note", "Nullable",
    ]);
    expect(within(table).getAllByRole("row").slice(1).map((row) =>
      within(row).getAllByRole("cell").map((cell) => cell.textContent))).toEqual([
      ["bronze_crm", "customer", "c", "Keep this note", "Not provided"],
      ["bronze_erp", "account", "a", "Not provided", "Not set"],
    ]);
    expect(JSON.stringify(document)).toBe(original);
  });

  it("prioritizes transformation and ordered steps while preserving every custom and empty value", () => {
    const expression = "CASE WHEN c.name IS NULL THEN '<script>literal</script>'\nELSE TRIM(c.name) END";
    const { container } = render(<MappingLogicDocument path="Entity logic" document={{
      custom_field: [false, 0, "", null, {}, []],
      source_note: "Keep this custom field with the logic",
      transformation_steps: [{ step: 1, instruction: "Normalize whitespace" }, { step: 2, instruction: "Preserve accents" }],
      source_attributes: ["crm_customer.customer_name"],
      steps: ["Read the source", "Apply the filter"],
      transformation: expression,
      source_objects: null,
      "": "Unnamed custom value",
    }} />);
    const sources = screen.getByRole("region", { name: "Source attributes" });
    expect(within(sources).getByText("crm_customer.customer_name")).toBeVisible();
    expect(within(screen.getByRole("region", { name: "Source objects" })).getByText("Not set")).toBeVisible();
    expect(within(sources).queryByText("Keep this custom field with the logic")).not.toBeInTheDocument();
    expect(container.querySelector(".mapping-logic-expression")?.textContent).toBe(expression);
    expect(container.querySelector("script")).toBeNull();
    expect(Array.from(container.querySelectorAll(".mapping-logic-grid > section:not(.is-source) > h3"), (node) => node.textContent))
      .toEqual(["Transformation", "Steps", "Transformation steps", "Custom field", "Source note", "Unnamed field"]);
    expect(within(screen.getByRole("list", { name: 'Entity logic["steps"]' })).getAllByRole("listitem")
      .map((node) => node.textContent)).toEqual(["Read the source", "Apply the filter"]);
    const transformedSteps = screen.getByRole("list", { name: 'Entity logic["transformation_steps"]' });
    expect(within(transformedSteps).getAllByRole("listitem").map((node) => node.textContent))
      .toEqual(["Step1InstructionNormalize whitespace", "Step2InstructionPreserve accents"]);
    const custom = screen.getByRole("list", { name: 'Entity logic["custom_field"]' });
    expect(within(custom).getAllByRole("listitem").map((node) => node.textContent))
      .toEqual(["false", "0", '\"\"', "Not set", "No fields", "No items"]);
    expect(screen.getByTitle("")).toHaveTextContent("Unnamed field");
  });

  it("renders varying source objects with all columns, preserving missing, null and nested paths", () => {
    render(<MappingLogicDocument path="Mapping" document={{ source_objects: [
      { system_code: "CRM", object_name: "customer", alias: null, enabled: false,
        lookups: [{ key: "first" }, { key: "second", optional: 0 }] },
      { system_code: "ERP", object_name: "account", count: 0, note: "" },
    ], steps: null }} />);
    const table = screen.getByRole("table", { name: 'Mapping["source_objects"]' });
    expect(screen.getByText("Source objects")).toBeVisible();
    const headers = Array.from(table.querySelectorAll(":scope > thead > tr > th"));
    expect(headers.map((node) => node.textContent)).toEqual(["Object name", "Alias", "Enabled", "Lookups", "Count", "Note"]);
    const rows = table.querySelectorAll(":scope > tbody > tr");
    const first = rows[0]!.querySelectorAll(":scope > td");
    const second = rows[1]!.querySelectorAll(":scope > td");
    expect(Array.from(first, (node) => node.textContent).slice(0, 3)).toEqual(["customer", "Not set", "false"]);
    expect(Array.from(second, (node) => node.textContent)).toEqual(["account", "Not provided", "Not provided", "Not provided", "0", '\"\"']);
    const nested = screen.getByRole("table", { name: 'Mapping["source_objects"][0]["lookups"]' });
    expect(within(nested).getAllByRole("row").slice(1).map((node) => node.textContent)).toEqual(["firstNot provided", "second0"]);
    expect(screen.getByRole("region", { name: 'Mapping["source_objects"]' })).toHaveAttribute("tabindex", "0");
  });

  it("keeps generic arrays unchanged unless tabular rendering is requested", () => {
    const value = [{ field: "first" }, { extra: "second" }];
    const { rerender } = render(<MappingDocumentValue value={value} path="Evidence" />);
    expect(screen.getByRole("list", { name: "Evidence" })).toBeVisible();
    expect(screen.queryByRole("table")).not.toBeInTheDocument();
    rerender(<MappingDocumentValue value={value} path="Evidence" tabular />);
    expect(screen.getByRole("table", { name: "Evidence" })).toBeVisible();
    rerender(<MappingDocumentValue value={[{}, { field: "retained" }]} path="Evidence" tabular />);
    expect(screen.getByRole("list", { name: "Evidence" })).toBeVisible();
    expect(screen.getByText("No fields")).toBeVisible();
    expect(screen.getByText("retained")).toBeVisible();
  });

  it("keeps authored empty documents and empty transformation strings explicit", () => {
    const { rerender } = render(<MappingLogicDocument path="Mapping" document={{}} />);
    expect(screen.getByText("No fields")).toBeVisible();
    rerender(<MappingLogicDocument path="Mapping" document={{ transformation: "" }} />);
    expect(screen.getByText('\"\"')).toHaveClass("mapping-logic-expression");
    expect(screen.queryByText("Not authored")).not.toBeInTheDocument();
  });
});
