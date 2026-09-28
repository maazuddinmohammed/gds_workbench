import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { act, render, screen, waitFor, within } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { describe, expect, it, vi } from "vitest";
import type { MappingApi, MappingAttribute, MappingAttributeDetail } from "./api";
import {
  createMappingDetailReader,
  MappingTransformationValue,
  useMappingAttributeDocuments,
} from "./MappingAttributeDocuments";

const item: MappingAttribute = {
  mapping_attribute_id: 91, mapping_object_id: 81, workflow_run_id: null,
  target: {
    entity: { entity_type: "logical_entity", entity_id: 701, entity_schema_name: "silver", entity_name: "customer" },
    attribute_id: 702, attribute_name: "customer_name", ordinal_position: 2, data_type: "string",
  },
  source_system: { system_id: 2, system_code: "CRM", system_name: "Customer system" },
  status: "active", is_locked: false, updated_at: "2026-09-01T00:00:00Z",
};

const detail: MappingAttributeDetail = {
  ...item, mapping_attribute_id: 91, status: "active", updated_at: "2026-09-01T00:00:00Z",
  mapping_document: null, output_template: null, created_at: "2026-09-01T00:00:00Z",
  parent_object_mapping: { mapping_object_id: 81, dependency_order: 0, status: "active", is_locked: false },
};

function client() {
  return new QueryClient({ defaultOptions: { queries: { retry: false, staleTime: Infinity } } });
}

function Documents({ api, items, enabled = true }: {
  api: Pick<MappingApi, "readMappingAttribute">;
  items: MappingAttribute[];
  enabled?: boolean;
}) {
  const { documents, fields } = useMappingAttributeDocuments({ api, tenantId: 7, modelId: 18, items, enabled });
  return <>
    <output data-testid="fields">{JSON.stringify(fields)}</output>
    {items.map((row) => <output key={row.target.attribute_id} data-testid={`document-${row.mapping_attribute_id}`}>
      {row.mapping_attribute_id === null ? "not mapped" : documents.get(row.mapping_attribute_id)?.state}
    </output>)}
  </>;
}

describe("Mapping Attribute documents", () => {
  it("renders exact custom values safely and expands long values in place", async () => {
    const expression = "SELECT '<script>literal</script>' AS name;\n".repeat(12);
    const { container } = render(<MappingTransformationValue label="Custom rule for customer_name"
      value={{ custom_rule: expression, values: [false, 0, "", null, {}] }} />);
    const region = screen.getByRole("region", { name: "Custom rule for customer_name" });
    expect(within(region).getByText("Custom rule")).toBeVisible();
    expect(region.textContent).toContain(expression);
    for (const scalar of ["false", "0", '\"\"', "Not set", "No fields"]) {
      expect(within(region).getByText(scalar)).toBeVisible();
    }
    expect(region).toHaveAttribute("tabindex", "0");
    expect(container.querySelector("script")).toBeNull();
    const expand = screen.getByRole("button", { name: "Expand transformation" });
    await userEvent.setup().click(expand);
    expect(expand).toHaveAttribute("aria-expanded", "true");
    expect(region).toHaveClass("is-expanded");
    await userEvent.setup().click(expand);
    expect(expand).toHaveAttribute("aria-expanded", "false");
    expect(region).not.toHaveClass("is-expanded");
  });

  it("shows source records as a table but preserves ordered transformation steps", () => {
    render(<>
      <MappingTransformationValue label="Source records" value={[
        { schema: "raw", name: "customer", nullable: null },
        { schema: "raw", name: "address", is_primary: false },
      ]} />
      <MappingTransformationValue label="Ordered steps" ordered value={[
        { instruction: "Trim whitespace" }, { instruction: "Uppercase the name" },
      ]} />
    </>);
    const table = screen.getByRole("table", { name: "Source records" });
    expect(within(table).getAllByRole("columnheader").map((column) => column.textContent))
      .toEqual(["Schema", "Name", "Nullable", "Is primary"]);
    expect(within(table).getByText("Not set")).toBeVisible();
    expect(within(table).getByText("false")).toBeVisible();
    expect(within(table).getAllByText("Not provided")).toHaveLength(2);
    const steps = screen.getByRole("list", { name: "Ordered steps" });
    expect(within(steps).getAllByRole("listitem").map((step) => step.textContent))
      .toEqual(["InstructionTrim whitespace", "InstructionUppercase the name"]);
    expect(screen.queryByRole("table", { name: "Ordered steps" })).not.toBeInTheDocument();
  });

  it.each([
    { updated_at: "2026-09-02T00:00:00Z" },
    { source_system: { ...item.source_system, system_id: 3 } },
    { target: { ...item.target, attribute_name: "other_name" } },
  ])("withholds mismatched document values and fields (%j)", async (changed) => {
    const api = { readMappingAttribute: vi.fn<MappingApi["readMappingAttribute"]>().mockResolvedValue({
      ...detail, ...changed, mapping_document: { stale_custom_rule: "Do not show this value" },
    }) };
    render(<QueryClientProvider client={client()}><Documents api={api} items={[item]} /></QueryClientProvider>);
    await waitFor(() => expect(screen.getByTestId("document-91")).toHaveTextContent("changed"));
    expect(screen.getByTestId("fields")).toHaveTextContent("[]");
    expect(screen.queryByText("Do not show this value")).not.toBeInTheDocument();
  });

  it("unions fields from loaded rows and reuses the shared detail cache", async () => {
    const next: MappingAttribute = { ...item, mapping_attribute_id: 92,
      target: { ...item.target, attribute_id: 703, attribute_name: "customer_code", ordinal_position: 3 } };
    const api = { readMappingAttribute: vi.fn<MappingApi["readMappingAttribute"]>().mockImplementation(async (_tenant, _model, id) => ({
      ...detail, target: (id === 91 ? item : next).target, mapping_attribute_id: id,
      mapping_document: id === 91 ? { transformation: "TRIM(name)", custom_check: false }
        : { transformation: "code", source_attributes: ["raw.customer.code"] },
    })) };
    const queryClient = client();
    const { rerender } = render(<QueryClientProvider client={queryClient}>
      <Documents api={api} items={[item]} />
    </QueryClientProvider>);
    await waitFor(() => expect(screen.getByTestId("document-91")).toHaveTextContent("ready"));
    expect(JSON.parse(screen.getByTestId("fields").textContent ?? "[]")).toEqual(expect.arrayContaining(["transformation", "custom_check"]));
    rerender(<QueryClientProvider client={queryClient}><Documents api={api} items={[item, next]} /></QueryClientProvider>);
    await waitFor(() => expect(screen.getByTestId("document-92")).toHaveTextContent("ready"));
    const fields = JSON.parse(screen.getByTestId("fields").textContent ?? "[]") as string[];
    expect(fields).toHaveLength(3);
    expect(fields).toEqual(expect.arrayContaining(["transformation", "custom_check", "source_attributes"]));
    expect(api.readMappingAttribute).toHaveBeenCalledTimes(2);
  });

  it("does not read documents while the ledger is unavailable", async () => {
    const api = { readMappingAttribute: vi.fn<MappingApi["readMappingAttribute"]>().mockResolvedValue(detail) };
    const queryClient = client();
    const { rerender } = render(<QueryClientProvider client={queryClient}>
      <Documents api={api} items={[item]} enabled={false} />
    </QueryClientProvider>);
    expect(api.readMappingAttribute).not.toHaveBeenCalled();
    rerender(<QueryClientProvider client={queryClient}><Documents api={api} items={[item]} /></QueryClientProvider>);
    await waitFor(() => expect(api.readMappingAttribute).toHaveBeenCalledTimes(1));
  });

  it("limits simultaneous detail reads and releases a slot after failure", async () => {
    const read = createMappingDetailReader();
    const gates = Array.from({ length: 6 }, () => {
      let resolve!: () => void;
      let reject!: () => void;
      const promise = new Promise<void>((yes, no) => { resolve = yes; reject = () => no(new Error("Unavailable")); });
      return { promise, resolve, reject };
    });
    const started: number[] = [];
    const tasks = gates.map((gate, index) => read(async () => {
      started.push(index);
      await gate.promise;
      return index;
    }));
    const completed = Promise.allSettled(tasks);
    expect(started).toEqual([0, 1, 2, 3]);
    gates[0]!.reject();
    await waitFor(() => expect(started).toEqual([0, 1, 2, 3, 4]));
    gates[1]!.resolve();
    await waitFor(() => expect(started).toEqual([0, 1, 2, 3, 4, 5]));
    gates.slice(2).forEach((gate) => gate.resolve());
    expect((await completed).map((result) => result.status)).toEqual([
      "rejected", "fulfilled", "fulfilled", "fulfilled", "fulfilled", "fulfilled",
    ]);
  });

  it("skips queued reads when the ledger unmounts", async () => {
    const releases: (() => void)[] = [];
    const api = { readMappingAttribute: vi.fn<MappingApi["readMappingAttribute"]>()
      .mockImplementation(async (_tenant, _model, id) => {
        await new Promise<void>((resolve) => releases.push(resolve));
        return { ...detail, mapping_attribute_id: id };
      }) };
    const queryClient = client();
    const { unmount } = render(<QueryClientProvider client={queryClient}>
      <Documents api={api} items={Array.from({ length: 6 }, (_, index) => ({ ...item, mapping_attribute_id: index + 91 }))} />
    </QueryClientProvider>);
    await waitFor(() => expect(api.readMappingAttribute).toHaveBeenCalledTimes(4));
    unmount();
    await act(async () => { releases.forEach((release) => release()); });
    expect(api.readMappingAttribute).toHaveBeenCalledTimes(4);
    queryClient.clear();
  });
});
