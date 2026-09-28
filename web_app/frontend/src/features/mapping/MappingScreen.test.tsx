import { withRecordReview } from "../../test/modelRecordReview";
import { render, screen, waitFor, within } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { createMemoryHistory } from "@tanstack/react-router";
import { describe, expect, it, vi } from "vitest";

import { createApiClient } from "../../api";
import { WorkbenchApp, createWorkbenchRouter } from "../../app";

describe("Mapping journey", () => {
  it.each(["logical", "dimensional"] as const)("shows one Entity transformation above Attributes only after Show details in the %s layer", async (layer) => {
    const base = mappingFetchStub();
    const entityType = layer === "logical" ? "logical_entity" : "dimensional_entity";
    const fetcher = vi.fn<typeof fetch>(async (input, init) => {
      const response = await base(input, init);
      const url = String(input);
      if (!/\/mapping\/(objects|attributes)(?:\?|\/)/.test(url)) return response;
      const body = await response.json();
      for (const row of Array.isArray(body.items) ? body.items : [body]) {
        row.target = url.includes("/mapping/attributes")
          ? { ...row.target, entity: { ...row.target.entity, entity_type: entityType } }
          : { ...row.target, entity_type: entityType };
        if (url.endsWith("/mapping/objects/81")) row.mapping_document = {
          source_objects: [{ object_name: "crm_customer" }], ...row.mapping_document,
        };
      }
      return jsonResponse(body);
    });
    const router = createWorkbenchRouter({ api: createApiClient(fetcher),
      history: createMemoryHistory({ initialEntries: [`/tenants/7/mapping/models/18?layer=${layer}`] }) });
    render(<WorkbenchApp router={router} />);
    const user = userEvent.setup();
    const grid = await screen.findByRole("table", { name: "Object Mappings" });
    expect(within(grid).queryByRole("columnheader", { name: "Entity transformation" })).not.toBeInTheDocument();
    expect(screen.queryByRole("heading", { name: "Entity transformation" })).not.toBeInTheDocument();
    expect(fetcher.mock.calls.some(([input]) => /\/mapping\/objects\/\d+$/.test(String(input)))).toBe(false);
    expect(within(grid).queryByText("Standard Object Mapping")).not.toBeInTheDocument();
    expect(within(grid).queryByRole("columnheader", { name: "Attributes" })).not.toBeInTheDocument();
    expect(screen.queryByRole("button", { name: /Show Attributes|Show Attribute mappings/ })).not.toBeInTheDocument();
    expect(screen.queryByRole("table", { name: "Attribute Mappings" })).not.toBeInTheDocument();
    expect(fetcher.mock.calls.some(([input]) => String(input).includes("/mapping/attributes"))).toBe(false);
    await user.click(screen.getByRole("link", { name: "Open Object Mapping 81" }));
    const attributes = await screen.findByRole("table", { name: "Attribute Mappings" });
    const transformation = screen.getByRole("region", { name: "Entity transformation" });
    expect(screen.getAllByRole("heading", { name: "Entity transformation" })).toHaveLength(1);
    expect(transformation).toBeVisible();
    expect(within(transformation).getByText("customer_raw.is_deleted = false")).toBeVisible();
    expect(within(transformation).getByText("customer_address_raw")).toBeVisible();
    const sources = within(transformation).getByRole("region", { name: "Sources" });
    expect(within(transformation).getByText("customer_raw.is_deleted = false")
      .compareDocumentPosition(sources) & Node.DOCUMENT_POSITION_FOLLOWING).toBeTruthy();
    expect(transformation.compareDocumentPosition(attributes) & Node.DOCUMENT_POSITION_FOLLOWING).toBeTruthy();
    expect(screen.queryByText("Object transformation", { exact: true })).not.toBeInTheDocument();
    expect(await within(attributes).findByText("crm_customer.customer_name")).toBeVisible();
    expect(within(attributes).getByText("Normalize whitespace")).toBeVisible();
    expect(within(attributes).getByRole("columnheader", { name: "Source attributes" })).toBeVisible();
    expect(within(attributes).getByRole("columnheader", { name: "Transformation steps" })).toBeVisible();
    expect(router.state.location.pathname).toBe("/tenants/7/mapping/models/18/objects/81");
    expect(router.state.location.search).toEqual({ layer });
    expect(within(attributes).queryByRole("link", { name: /Open Attribute Mapping/ })).not.toBeInTheDocument();
    expect(within(attributes).getByLabelText("Record info for customer_name")).toBeVisible();
    await user.click(screen.getByRole("link", { name: "Back to Object mappings" }));
    expect(await screen.findByRole("table", { name: "Object Mappings" })).toBeVisible();
    expect(screen.queryByRole("table", { name: "Attribute Mappings" })).not.toBeInTheDocument();
    expect(router.state.location.pathname).toBe("/tenants/7/mapping/models/18");
    expect(router.state.location.search).toEqual({ layer });
  });

  it("refreshes Entity and Attribute transformations on details without reading them again on the ledger", async () => {
    let refreshed = false;
    const base = mappingFetchStub();
    const fetcher = vi.fn<typeof fetch>(async (input, init) => {
      const url = String(input);
      const updated = refreshed ? "2026-08-25T10:00:00Z" : mappingObject.updated_at;
      if (url.endsWith("/mapping/objects/81")) return jsonResponse({ ...mappingObjectDetail,
        updated_at: updated, mapping_document: { steps: [refreshed ? "Use current source" : "Use original source"] } });
      if (url.endsWith("/mapping/attributes/91")) return jsonResponse({ ...mappingAttributeDetail,
        updated_at: updated, mapping_document: { transformation: refreshed ? "TRIM(current_name)" : "TRIM(original_name)" } });
      const response = await base(input, init);
      if (/\/mapping\/(objects|attributes)\?/.test(url)) {
        const page = await response.json();
        return jsonResponse({ ...page, items: page.items.map((row: object) => ({ ...row, updated_at: updated })) });
      }
      return response;
    });
    render(<WorkbenchApp router={createWorkbenchRouter({ api: createApiClient(fetcher),
      history: createMemoryHistory({ initialEntries: ["/tenants/7/mapping/models/18"] }) })} />);
    const user = userEvent.setup();
    await user.click(await screen.findByRole("link", { name: "Open Object Mapping 81" }));
    expect(await screen.findByText("Use original source")).toBeVisible();
    expect(await screen.findByText("TRIM(original_name)")).toBeVisible();
    refreshed = true;
    await user.click(screen.getByRole("button", { name: "Refresh Attributes" }));
    expect(await screen.findByText("TRIM(current_name)")).toBeVisible();
    expect(await screen.findByText("Use current source")).toBeVisible();
    expect(screen.queryByText("TRIM(original_name)")).not.toBeInTheDocument();
    await user.click(screen.getByRole("link", { name: "Back to Object mappings" }));
    await screen.findByRole("table", { name: "Object Mappings" });
    expect(screen.queryByText("Use current source")).not.toBeInTheDocument();
    expect(fetcher.mock.calls.filter(([input]) => String(input).endsWith("/mapping/objects/81"))).toHaveLength(2);
    expect(fetcher.mock.calls.filter(([input]) => String(input).endsWith("/mapping/attributes/91"))).toHaveLength(2);
    const ledgerReads = fetcher.mock.calls.filter(([input]) => String(input).includes("/mapping/objects?")).length;
    await user.click(screen.getByRole("button", { name: "Refresh" }));
    await waitFor(() => expect(fetcher.mock.calls.filter(([input]) => String(input).includes("/mapping/objects?"))).toHaveLength(ledgerReads + 2));
    expect(fetcher.mock.calls.filter(([input]) => String(input).endsWith("/mapping/objects/81"))).toHaveLength(2);
    expect(screen.queryByRole("table", { name: "Attribute Mappings" })).not.toBeInTheDocument();
    expect(fetcher.mock.calls.filter(([input]) => String(input).endsWith("/mapping/attributes/91"))).toHaveLength(2);
  });

  it("withholds changed Attribute transformations until Refresh reconciles their rows", async () => {
    let refreshed = false;
    const base = mappingFetchStub();
    const fetcher = vi.fn<typeof fetch>(async (input, init) => {
      const url = String(input);
      const updated = "2026-08-25T10:00:00Z";
      if (url.endsWith("/mapping/attributes/91")) return jsonResponse({ ...mappingAttributeDetail,
        updated_at: updated, mapping_document: { transformation: "Current safe attribute transformation" } });
      if (refreshed && url.includes("/mapping/attributes?")) return jsonResponse({
        model_id: 18, model_revision: 18, next_cursor: null, items: [{ ...mappingAttribute, updated_at: updated }],
      });
      return base(input, init);
    });
    render(<WorkbenchApp router={createWorkbenchRouter({ api: createApiClient(fetcher),
      history: createMemoryHistory({ initialEntries: ["/tenants/7/mapping/models/18/objects/81"] }) })} />);
    expect(await screen.findByRole("alert")).toHaveTextContent("Mapping changed. Refresh");
    expect(screen.queryByText("Current safe attribute transformation")).not.toBeInTheDocument();
    refreshed = true;
    await userEvent.setup().click(screen.getByRole("button", { name: "Refresh Attributes" }));
    expect(await screen.findByText("Current safe attribute transformation")).toBeVisible();
  });

  it("keeps a failed Attribute transformation local to its cell and retries the safe read", async () => {
    let attempts = 0;
    const base = mappingFetchStub();
    const fetcher = vi.fn<typeof fetch>(async (input, init) => {
      if (String(input).endsWith("/mapping/attributes/91") && attempts++ === 0) {
        return jsonResponse({ error: { code: "unavailable", message: "DO NOT DISPLAY RAW ERROR" } }, 503);
      }
      return base(input, init);
    });
    render(<WorkbenchApp router={createWorkbenchRouter({ api: createApiClient(fetcher),
      history: createMemoryHistory({ initialEntries: ["/tenants/7/mapping/models/18/objects/81"] }) })} />);
    expect(await screen.findByRole("alert")).toHaveTextContent("Transformation could not be loaded.");
    expect(screen.getByRole("table", { name: "Attribute Mappings" })).toBeVisible();
    expect(screen.queryByText("DO NOT DISPLAY RAW ERROR")).not.toBeInTheDocument();
    await userEvent.setup().click(screen.getByRole("button", { name: "Retry transformation" }));
    expect(await screen.findByText("Normalize whitespace")).toBeVisible();
  });

  it("pivots the union of Attribute fields while preserving absent, null, empty, and unauthored values", async () => {
    const documents = [
      { source_attributes: ["crm_customer.customer_name"], target_attribute_name: "customer_name",
        transformation: "TRIM(customer_name)", nullable_rule: null, enabled: false, weight: 0, blank_text: "" },
      { transformation: "LOWER(email)", target_attribute_name: "email_alias", custom_rule: "Validate address" },
      null,
      {},
    ];
    const details = ["customer_name", "email", "customer_id", "region"].map((attribute_name, index) => ({
      ...mappingAttributeDetail,
      mapping_attribute_id: 91 + index,
      target: { ...mappingAttribute.target, attribute_id: 702 + index, attribute_name, ordinal_position: 2 + index },
      mapping_document: documents[index],
    }));
    const base = mappingFetchStub();
    const fetcher = vi.fn<typeof fetch>(async (input, init) => {
      const url = String(input);
      if (url.includes("/mapping/attributes?")) return jsonResponse({
        model_id: 18, model_revision: 18, items: details, next_cursor: null,
      });
      const detail = details.find((item) => url.endsWith(`/mapping/attributes/${item.mapping_attribute_id}`));
      return detail ? jsonResponse(detail) : base(input, init);
    });
    render(<WorkbenchApp router={createWorkbenchRouter({ api: createApiClient(fetcher),
      history: createMemoryHistory({ initialEntries: ["/tenants/7/mapping/models/18/objects/81"] }),
    })} />);
    const table = await screen.findByRole("table", { name: "Attribute Mappings" });
    await within(table).findByRole("columnheader", { name: "Custom rule" });
    const headerRow = within(table).getAllByRole("row")[0];
    if (!headerRow) throw new Error("Attribute Mappings must have a header row.");
    const headers = within(headerRow).getAllByRole("columnheader").map((header) => header.textContent);
    expect(headers.slice(1)).toEqual([
      "Target Attribute", "Transformation", "Source attributes", "Target attribute name", "Nullable rule", "Enabled",
      "Weight", "Blank text", "Custom rule", "Status", "Record info",
    ]);
    const nameRow = within(table).getByRole("checkbox", { name: "Select Mapping Attributes 91" }).closest("tr")!;
    const emailRow = within(table).getByRole("checkbox", { name: "Select Mapping Attributes 92" }).closest("tr")!;
    const nameNullable = nameRow.cells[headers.indexOf("Nullable rule")];
    const emailNullable = emailRow.cells[headers.indexOf("Nullable rule")];
    if (!nameNullable || !emailNullable) throw new Error("Both rows must have a Nullable rule cell.");
    expect(within(nameNullable).getByText("Not set")).toBeVisible();
    expect(within(emailNullable).getByText("Not provided")).toBeVisible();
    expect(within(nameRow).getByText("false")).toBeVisible();
    expect(within(nameRow).getByText("0")).toBeVisible();
    expect(within(nameRow).getByText('""')).toBeVisible();
    expect(within(emailRow).getByText("email_alias")).toBeVisible();
    expect(within(emailRow).getByText("Validate address")).toBeVisible();
    const unauthoredRow = within(table).getByRole("checkbox", { name: "Select Mapping Attributes 93" }).closest("tr")!;
    const emptyRow = within(table).getByRole("checkbox", { name: "Select Mapping Attributes 94" }).closest("tr")!;
    expect(within(unauthoredRow).getByText("Not authored")).toBeVisible();
    expect(within(emptyRow).getByText("No fields")).toBeVisible();
    expect(within(table).queryByRole("link")).not.toBeInTheDocument();
  });

  it("keeps the legacy Mapping Model picker addressable", async () => {
    const fetcher = mappingFetchStub();
    render(<WorkbenchApp router={createWorkbenchRouter({
      api: createApiClient(fetcher),
      history: createMemoryHistory({ initialEntries: ["/tenants/7/mapping"] }),
    })} />);

    expect(await screen.findByRole("table", { name: "Models for Mapping" })).toBeVisible();
    expect(screen.getByRole("link", { name: "Open Customer 360 Mapping" })).toBeVisible();
  });

  it("opens a Model directly into server-filtered Entity mappings", async () => {
    const fetcher = mappingFetchStub();
    const user = userEvent.setup();
    render(<WorkbenchApp router={createWorkbenchRouter({
      api: createApiClient(fetcher),
      history: createMemoryHistory({ initialEntries: ["/tenants/7/mapping/models/18"] }),
    })} />);

    expect(await screen.findByRole("table", { name: "Object Mappings" })).toBeVisible();
    expect(screen.getByRole("navigation", { name: "Model sections" })).toBeVisible();
    expect(screen.queryByRole("button", { name: "Dependencies" })).not.toBeInTheDocument();
    expect(screen.queryByRole("button", { name: "Add System dependency" })).not.toBeInTheDocument();
    expect(fetcher.mock.calls.some(([input]) => String(input).includes("/mapping/dependencies"))).toBe(false);
    expect(within(screen.getByRole("navigation", { name: "Model sections" })).getByRole("link", { name: "Overview" })).toBeVisible();

    expect(within(screen.getByRole("navigation", { name: "Mapping layer" })).getByRole("link", { name: "Logical" })).toHaveAttribute("aria-current", "page");
    expect(screen.queryByLabelText("Entity type")).not.toBeInTheDocument();
    await user.selectOptions(screen.getByLabelText("Source System code"), "CRM");
    await user.selectOptions(screen.getByLabelText("Mapping status"), "inactive");
    await user.selectOptions(screen.getByLabelText("Mapping lock"), "false");
    await user.click(screen.getByRole("button", { name: "Apply Mapping filters" }));

    expect(fetcher).toHaveBeenCalledWith(
      "/api/v1/tenants/7/models/18/mapping/objects?entity_type=logical_entity&source_system_code=crm&status=inactive&locked=false&page_size=200",
      expect.objectContaining({ credentials: "same-origin" }),
    );
  });

  it("reviews Entity logic and inline Attribute records without leaving the spreadsheet", async () => {
    const fetcher = mappingFetchStub();
    const user = userEvent.setup();
    render(<WorkbenchApp router={createWorkbenchRouter({
      api: createApiClient(fetcher),
      history: createMemoryHistory({ initialEntries: ["/tenants/7/mapping/models/18"] }),
    })} />);

    await screen.findByRole("table", { name: "Object Mappings" });
    expect(await screen.findByRole("table", { name: "Object Mappings" })).toBeVisible();
    const mappings = within(screen.getByRole("table", { name: "Object Mappings" }));
    expect(mappings.getAllByRole("columnheader").slice(1, 4).map((header) => header.textContent)).toEqual(["System", "Schema", "Entity name"]);
    expect(mappings.getByRole("cell", { name: "silver_nwa" })).toBeVisible();
    expect(mappings.getByRole("cell", { name: "customer" })).toBeVisible();
    expect(mappings.getByRole("cell", { name: "CRM" })).toBeVisible();
    expect(screen.getByRole("region", { name: "Object Mappings spreadsheet" })).toHaveAttribute("tabindex", "0");
    await user.click(screen.getByRole("link", { name: "Open Object Mapping 81" }));

    const objectHeading = await screen.findByRole("heading", { name: "customer", level: 1 });
    expect(objectHeading).toHaveFocus();
    const identity = within(objectHeading.closest("header")!);
    expect(identity.getByText("System")).toBeVisible();
    expect(identity.getByText("CRM")).toBeVisible();
    expect(identity.getByText("Schema")).toBeVisible();
    expect(identity.getByText("silver_nwa")).toBeVisible();
    expect(screen.queryByRole("heading", { name: "Mapping context" })).not.toBeInTheDocument();
    const attributes = await screen.findByRole("table", { name: "Attribute Mappings" });
    expect(attributes).toBeVisible();
    await within(attributes).findByRole("columnheader", { name: "Source attributes" });
    const headerRow = within(attributes).getAllByRole("row")[0];
    if (!headerRow) throw new Error("Attribute Mappings must have a header row.");
    const headers = within(headerRow).getAllByRole("columnheader").slice(1).map((header) => header.textContent);
    expect(headers[0]).toBe("Target Attribute");
    expect(headers.slice(1, -2)).toEqual(expect.arrayContaining(["Source attributes", "Transformation steps"]));
    expect(headers.slice(-2)).toEqual(["Status", "Record info"]);
    expect(headers).toHaveLength(5);
    const recordInfoToggle = within(attributes).getByLabelText("Record info for customer_name");
    const attributeRow = recordInfoToggle.closest("tr")!;
    const targetCell = attributeRow.cells[1];
    const statusCell = attributeRow.cells[attributeRow.cells.length - 2];
    if (!targetCell || !statusCell) throw new Error("Attribute Mappings must have target and status cells.");
    expect(within(targetCell).getByText("customer_name")).toBeVisible();
    expect(within(targetCell).getByText("string")).toBeVisible();
    expect(within(statusCell).getByText("Active")).toBeVisible();
    expect(within(statusCell).getByText("Open")).toBeVisible();
    expect(screen.getByRole("heading", { name: "Attribute transformations" })).toBeVisible();
    expect(fetcher).toHaveBeenCalledWith(
      "/api/v1/tenants/7/models/18/mapping/attributes?mapping_object_id=81&page_size=200",
      expect.objectContaining({ credentials: "same-origin" }),
    );
    expect(screen.queryByRole("button", { name: "Attribute mappings" })).not.toBeInTheDocument();
    expect(screen.getByRole("heading", { name: "Entity transformation" })).toBeVisible();
    expect(screen.getByText("Join strategy")).toBeVisible();
    expect(screen.getByRole("table", { name: 'Entity transformation["join_strategy"]["joins"]' })).toHaveTextContent("customer_address_raw");
    expect(screen.getByText("customer_raw")).toBeVisible();
    expect(screen.queryByText(JSON.stringify(mappingObjectDetail.mapping_document))).not.toBeInTheDocument();
    const mappingDetails = screen.getByText("Mapping details").closest("details")!;
    expect(mappingDetails).not.toHaveAttribute("open");
    expect(within(mappingDetails).getByText("Standard Object Mapping")).not.toBeVisible();
    expect(attributes.compareDocumentPosition(mappingDetails) & Node.DOCUMENT_POSITION_FOLLOWING).toBeTruthy();
    await user.click(within(mappingDetails).getByText("Mapping details"));
    expect(within(mappingDetails).getByText("Standard Object Mapping")).toBeVisible();
    expect(within(mappingDetails).getByText("mapping.object.standard")).toBeVisible();
    expect(within(mappingDetails).getByText("Entity order")).toBeVisible();
    expect(within(mappingDetails).getByText("Updated")).toBeVisible();
    expect(within(mappingDetails).getByText("Created")).toBeVisible();

    expect(within(attributes).queryByRole("link")).not.toBeInTheDocument();
    const recordInfo = recordInfoToggle.closest("details")!;
    expect(recordInfo).not.toHaveAttribute("open");
    expect(within(recordInfo).getByText("Standard Attribute Mapping")).not.toBeVisible();
    await user.click(recordInfoToggle);
    expect(recordInfo).toHaveAttribute("open");
    expect(within(recordInfo).getByText("91")).toBeVisible();
    expect(within(recordInfo).getByText("2")).toBeVisible();
    expect(within(recordInfo).getByText("Created")).toBeVisible();
    expect(within(recordInfo).getByText("Updated")).toBeVisible();
    expect(within(recordInfo).getByText("Standard Attribute Mapping")).toBeVisible();
    expect(within(recordInfo).getByText("mapping.attribute.standard")).toBeVisible();
    const originalDocument = within(recordInfo).getByText("Original document").closest("details")!;
    expect(originalDocument).not.toHaveAttribute("open");
    await user.click(within(recordInfo).getByText("Original document"));
    expect(within(originalDocument).getByText(JSON.stringify(mappingAttributeDetail.mapping_document, null, 2), {
      normalizer: (text) => text,
    })).toBeVisible();
    expect(screen.getByRole("heading", { name: "customer", level: 1 })).toBeVisible();
    await user.click(screen.getByRole("link", { name: "Back to Object mappings" }));
    expect(await screen.findByRole("table", { name: "Object Mappings" })).toBeVisible();
  });

  it("keeps legacy Attribute Mapping URLs addressable with focused return navigation", async () => {
    render(<WorkbenchApp router={createWorkbenchRouter({ api: createApiClient(mappingFetchStub()),
      history: createMemoryHistory({ initialEntries: ["/tenants/7/mapping/models/18/attributes/91"] }),
    })} />);
    const user = userEvent.setup();
    const heading = await screen.findByRole("heading", { name: "silver_nwa.customer.customer_name", level: 1 });
    expect(heading).toHaveFocus();
    expect(screen.getByText("crm_customer.customer_name")).toBeVisible();
    expect(screen.getByText("Normalize whitespace")).toBeVisible();
    expect(screen.getAllByRole("heading", { level: 2 }).map((item) => item.textContent)).toEqual([
      "Mapping context", "Transformation document", "Parent Object Mapping",
    ]);
    expect(screen.getAllByText("mapping.attribute.standard")).toHaveLength(1);
    expect(screen.queryByText("c".repeat(64))).not.toBeInTheDocument();
    await user.click(screen.getByText("Source and template details"));
    expect(screen.getByText("Created")).toBeVisible();
    expect(screen.getByText("Updated")).toBeVisible();
    await user.click(screen.getByRole("link", { name: "Back to Object Mapping" }));
    expect(await screen.findByRole("heading", { name: "customer", level: 1 })).toHaveFocus();
    expect(await screen.findByRole("table", { name: "Attribute Mappings" })).toBeVisible();
  });

  it("follows opaque Mapping cursors and refreshes the active ledger", async () => {
    const fetcher = mappingFetchStub({ hasNextPage: true });
    const user = userEvent.setup();
    render(<WorkbenchApp router={createWorkbenchRouter({
      api: createApiClient(fetcher),
      history: createMemoryHistory({ initialEntries: ["/tenants/7/mapping/models/18"] }),
    })} />);

    await screen.findByRole("table", { name: "Object Mappings" });
    const objectCallsBeforeRefresh = fetcher.mock.calls.filter(([input]) => (
      String(input).includes("/mapping/objects?")
    )).length;
    await user.click(screen.getByRole("button", { name: "Refresh" }));
    expect(fetcher.mock.calls.filter(([input]) => (
      String(input).includes("/mapping/objects?")
    ))).toHaveLength(objectCallsBeforeRefresh + 3);

    await screen.findByRole("table", { name: "Object Mappings" });
    await user.click(screen.getByRole("button", { name: "Load more Object Mappings" }));
    expect(fetcher).toHaveBeenCalledWith(
      "/api/v1/tenants/7/models/18/mapping/objects?entity_type=logical_entity&page_size=200&cursor=objects-next",
      expect.objectContaining({ credentials: "same-origin" }),
    );
    expect(await screen.findByRole("cell", { name: "contact" })).toBeVisible();
  });

  it("keeps Attribute filters, pagination, and refresh within the parent Object", async () => {
    const fetcher = mappingFetchStub({ hasNextPage: true });
    const user = userEvent.setup();
    render(<WorkbenchApp router={createWorkbenchRouter({
      api: createApiClient(fetcher),
      history: createMemoryHistory({ initialEntries: ["/tenants/7/mapping/models/18/objects/81"] }),
    })} />);
    await screen.findByRole("table", { name: "Attribute Mappings" });
    expect(screen.queryByLabelText("Entity type")).not.toBeInTheDocument();
    const filtersToggle = screen.getByRole("button", { name: "Filters" });
    expect(filtersToggle).toHaveAttribute("aria-expanded", "false");
    expect(screen.getByLabelText("Mapping status")).not.toBeVisible();
    expect(screen.getByLabelText("Mapping lock")).not.toBeVisible();
    await user.click(filtersToggle);
    expect(filtersToggle).toHaveAttribute("aria-expanded", "true");
    expect(screen.getByLabelText("Mapping status")).toBeVisible();
    expect(screen.getByLabelText("Mapping lock")).toBeVisible();
    await user.click(screen.getByRole("checkbox", { name: "Select Mapping Attributes 91" }));
    await user.selectOptions(screen.getByLabelText("Mapping status"), "inactive");
    await user.click(screen.getByRole("button", { name: "Apply Mapping filters" }));
    expect(await screen.findByRole("checkbox", { name: "Select Mapping Attributes 91" })).not.toBeChecked();
    expect(filtersToggle).toHaveAccessibleName("Filters · 1");
    await user.click(filtersToggle);
    expect(filtersToggle).toHaveAttribute("aria-expanded", "false");
    expect(screen.getByLabelText("Mapping status")).not.toBeVisible();
    await user.click(screen.getByRole("button", { name: "Load more Attribute Mappings" }));
    expect(await screen.findByRole("checkbox", { name: "Select Mapping Attributes 92" })).toBeVisible();
    expect(fetcher).toHaveBeenCalledWith(
      "/api/v1/tenants/7/models/18/mapping/attributes?status=inactive&mapping_object_id=81&page_size=200&cursor=attributes-next",
      expect.objectContaining({ credentials: "same-origin" }),
    );
    await user.click(filtersToggle);
    expect(screen.getByLabelText("Mapping status")).toHaveValue("inactive");
    await user.click(screen.getByRole("button", { name: "Clear" }));
    expect(filtersToggle).toHaveAccessibleName("Filters");
    await user.click(await screen.findByRole("checkbox", { name: "Select Mapping Attributes 91" }));
    await user.click(screen.getByRole("button", { name: "Refresh Attributes" }));
    expect(await screen.findByRole("checkbox", { name: "Select Mapping Attributes 91" })).not.toBeChecked();
    const calls = fetcher.mock.calls.filter(([input]) => String(input).includes("/mapping/attributes?"));
    expect(calls.length).toBeGreaterThan(3);
    expect(calls.every(([input]) => String(input).includes("mapping_object_id=81"))).toBe(true);
  });

  it.each([
    [{ empty: true }, "No Attribute Mappings match these filters."],
    [{ denied: true }, "You do not have permission to view Attribute Mappings."],
    [{ error: true }, "Attribute Mappings could not be loaded."],
    [{ modelRevision: 19 }, "The Model changed while Attribute Mappings were loading. Refresh to reconcile revisions."],
  ] as const)("keeps nested Attribute states explicit: %s", async (options, message) => {
    render(<WorkbenchApp router={createWorkbenchRouter({
      api: createApiClient(mappingFetchStub(options)),
      history: createMemoryHistory({ initialEntries: ["/tenants/7/mapping/models/18/objects/81"] }),
    })} />);
    expect(await screen.findByText(message)).toBeVisible();
    expect(screen.getByRole("button", { name: "Lock selected", hidden: true })).toBeDisabled();
    expect(screen.getByRole("link", { name: "Back to Object mappings" })).toBeVisible();
  });

  it.each(["attributes", "dependencies"])("opens old %s bookmarks at Entity mappings", async (view) => {
    render(<WorkbenchApp router={createWorkbenchRouter({
      api: createApiClient(mappingFetchStub()),
      history: createMemoryHistory({ initialEntries: [`/tenants/7/mapping/models/18?view=${view}`] }),
    })} />);
    expect(await screen.findByRole("table", { name: "Object Mappings" })).toBeVisible();
    expect(screen.queryByRole("button", { name: "Attribute mappings" })).not.toBeInTheDocument();
  });

  it("keeps Mapping empty, safe-error, denied, and revision states explicit", async () => {
    const empty = render(<WorkbenchApp router={createWorkbenchRouter({
      api: createApiClient(mappingFetchStub({ empty: true })),
      history: createMemoryHistory({ initialEntries: ["/tenants/7/mapping/models/18"] }),
    })} />);
    expect(await screen.findByText("No Object Mappings match these filters.")).toBeVisible();
    empty.unmount();

    const mismatch = render(<WorkbenchApp router={createWorkbenchRouter({
      api: createApiClient(mappingFetchStub({ modelRevision: 19 })),
      history: createMemoryHistory({ initialEntries: ["/tenants/7/mapping/models/18"] }),
    })} />);
    expect(await screen.findByRole("alert")).toHaveTextContent(
      "The Model changed while Object Mappings were loading.",
    );
    mismatch.unmount();

    const denied = render(<WorkbenchApp router={createWorkbenchRouter({
      api: createApiClient(mappingFetchStub({ denied: true })),
      history: createMemoryHistory({ initialEntries: ["/tenants/7/mapping/models/18"] }),
    })} />);
    expect(await screen.findByRole("alert")).toHaveTextContent(
      "You do not have permission to view Object Mappings.",
    );
    denied.unmount();

    render(<WorkbenchApp router={createWorkbenchRouter({
      api: createApiClient(mappingFetchStub({ error: true })),
      history: createMemoryHistory({ initialEntries: ["/tenants/7/mapping/models/18"] }),
    })} />);
    expect(await screen.findByRole("alert")).toHaveTextContent(
      "Object Mappings could not be loaded.",
    );
  });

  it("requires App permission and Tenant Lock, then explicitly creates and executes one target", async () => {
    const unlocked = render(<WorkbenchApp router={createWorkbenchRouter({
      api: createApiClient(mappingFetchStub({ hasLock: false })),
      history: createMemoryHistory({ initialEntries: ["/tenants/7/mapping/models/18"] }),
    })} />);
    await screen.findByRole("table", { name: "Object Mappings" });
    expect(screen.getByRole("button", { name: "Generate mappings" })).toBeDisabled();
    expect(screen.getByText("Tenant Lock required to run")).toBeVisible();
    unlocked.unmount();

    const denied = render(<WorkbenchApp router={createWorkbenchRouter({
      api: createApiClient(mappingFetchStub({ role: "developer" })),
      history: createMemoryHistory({ initialEntries: ["/tenants/7/mapping/models/18"] }),
    })} />);
    await screen.findByRole("table", { name: "Object Mappings" });
    expect(screen.getByRole("button", { name: "Generate mappings" })).toBeDisabled();
    expect(screen.getByText("Architect permission required to run")).toBeVisible();
    denied.unmount();

    const fetcher = mappingFetchStub();
    const user = userEvent.setup();
    render(<WorkbenchApp router={createWorkbenchRouter({
      api: createApiClient(fetcher),
      history: createMemoryHistory({ initialEntries: ["/tenants/7/mapping/models/18"] }),
    })} />);
    await screen.findByRole("table", { name: "Object Mappings" });
    await user.click(await screen.findByRole("button", { name: "Generate mappings" }));
    await user.click(screen.getByText("Advanced settings"));
    expect(await screen.findByRole("heading", { name: "Generate mappings" })).toBeVisible();
    const executionMode = screen.getByLabelText("Execution mode");
    expect(within(executionMode).getAllByRole("option").map((option) => (
      (option as HTMLOptionElement).value
    ))).toEqual(["", "tool_assisted"]);
    expect(executionMode).toHaveValue("tool_assisted");
    expect(screen.getByLabelText("Object Mapping Output Template")).toHaveValue("");
    expect(screen.getByLabelText("Attribute Mapping Output Template")).toHaveValue("");
    expect(screen.getAllByRole("option", { name: "Use global default" })).toHaveLength(2);
    expect(screen.getByText("mapping_object_default")).toBeVisible();
    expect(screen.getByText("mapping_attribute_default")).toBeVisible();
    expect(screen.getByRole("option", {
      name: "Standard Object Mapping · Schema valid",
    })).toBeInTheDocument();
    expect(screen.getByRole("option", {
      name: "Broken Object Mapping · Schema invalid",
    })).toBeDisabled();
    await user.selectOptions(screen.getByLabelText("Source System"), "2");
    await user.selectOptions(screen.getByLabelText("Object Mapping Output Template"), "801");
    await user.selectOptions(screen.getByLabelText("Attribute Mapping Output Template"), "802");
    await user.click(within(screen.getByRole("dialog")).getByRole("button", { name: "Generate mappings" }));

    const createCall = fetcher.mock.calls.find(([input, init]) => (
      String(input) === "/api/v1/tenants/7/models/18/runs" && init?.method === "POST"
    ));
    expect(createCall).toBeDefined();
    expect(JSON.parse(String(createCall?.[1]?.body))).toEqual({
      expected_model_revision: 18,
      model_workflow: "mapping",
      workflow_execution_mode: "tool_assisted",
      selected_object_ids: [],
      selected_entity_ids: [701],
      modeled_entity_type: "logical_entity",
      requested_batch_id: null,
      agent: {
        sdk_code: "openai_agents_sdk",
        provider_code: "microsoft_foundry",
        model_code: "foundry-primary",
        reasoning_effort_code: "medium",
        max_turns: 8,
        validation_retry_count: 1,
      },
      prompt_overrides: {},
      mapping_operation: "generate",
      mapping_coverage_mode: "selected_targets",
      mapping_targets: [{ modeled_entity_id: 701, source_system_id: 2, selected_attribute_ids: [702] }],
      mapping_object_output_template_id: 801,
      mapping_attribute_output_template_id: 802,
    });
    expect(fetcher).toHaveBeenCalledWith(
      "/api/v1/tenants/7/models/18/mapping/runs/1150/execute",
      expect.objectContaining({
        method: "POST",
        body: JSON.stringify({ execution_mode: "tool_assisted", expected_model_revision: 18 }),
      }),
    );
  });

  it.each(["network", "server"] as const)("retries an ambiguous Mapping %s create with the original command and key", async (failure) => {
    const success = mappingFetchStub();
    let attempts = 0;
    const fetcher = vi.fn<typeof fetch>(async (input, init) => {
      if (String(input) === "/api/v1/tenants/7/models/18/runs" && init?.method === "POST" && ++attempts === 1) {
        if (failure === "network") throw new TypeError("Synthetic network failure");
        return jsonResponse({ error: { code: "unavailable" } }, 503);
      }
      return success(input, init);
    });
    const user = userEvent.setup();
    render(<WorkbenchApp router={createWorkbenchRouter({
      api: createApiClient(fetcher),
      history: createMemoryHistory({ initialEntries: ["/tenants/7/mapping/models/18"] }),
    })} />);
    await screen.findByRole("table", { name: "Object Mappings" });
    await user.click(await screen.findByRole("button", { name: "Generate mappings" }));
    await user.click(screen.getByText("Advanced settings"));
    await screen.findByRole("heading", { name: "Generate mappings" });
    await user.selectOptions(screen.getByLabelText("Source System"), "2");
    const submit = await within(screen.getByRole("dialog")).findByRole("button", { name: "Generate mappings" });
    await waitFor(() => expect(submit).toBeEnabled());
    for (const label of ["Agent SDK", "Provider", "Maximum turns", "Validation retries"]) {
      expect(screen.queryByLabelText(label)).not.toBeInTheDocument();
    }
    await user.click(submit);
    await screen.findByRole("alert");
    expect(screen.getByLabelText("Model")).toBeEnabled();
    await user.click(submit);
    await waitFor(() => expect(screen.queryByRole("dialog")).not.toBeInTheDocument());
    const creates = fetcher.mock.calls.filter(([input, init]) =>
      String(input) === "/api/v1/tenants/7/models/18/runs" && init?.method === "POST");
    expect(creates).toHaveLength(2);
    expect(creates[1]?.[1]?.body).toBe(creates[0]?.[1]?.body);
    const firstKey = new Headers(creates[0]?.[1]?.headers).get("Idempotency-Key");
    expect(firstKey).toMatch(/^[a-f0-9-]{36}$/);
    expect(new Headers(creates[1]?.[1]?.headers).get("Idempotency-Key")).toBe(firstKey);
  });

  it("retries a conflicted Mapping start without creating another run", async () => {
    const fetcher = mappingFetchStub({ executeConflictOnce: true });
    const user = userEvent.setup();
    render(<WorkbenchApp router={createWorkbenchRouter({
      api: createApiClient(fetcher),
      history: createMemoryHistory({ initialEntries: ["/tenants/7/mapping/models/18"] }),
    })} />);
    await screen.findByRole("table", { name: "Object Mappings" });

    await screen.findByRole("table", { name: "Object Mappings" });
    await user.click(await screen.findByRole("button", { name: "Generate mappings" }));
    await user.click(screen.getByText("Advanced settings"));
    await screen.findByRole("heading", { name: "Generate mappings" });
    await user.selectOptions(screen.getByLabelText("Source System"), "2");
    const createAndRun = within(screen.getByRole("dialog")).getByRole("button", { name: "Generate mappings" });
    await waitFor(() => expect(createAndRun).toBeEnabled());
    await user.click(createAndRun);

    expect(await screen.findByRole("alert")).toHaveTextContent(
      "Another Workflow Run is already active for this Tenant. "
      + "This run remains queued; retry after the active run finishes.",
    );
    await user.click(screen.getByRole("button", { name: "Retry start" }));

    await waitFor(() => {
      expect(fetcher.mock.calls.filter(([input, init]) => (
        String(input) === "/api/v1/tenants/7/models/18/runs" && init?.method === "POST"
      ))).toHaveLength(1);
      expect(fetcher.mock.calls.filter(([input, init]) => (
        String(input) === "/api/v1/tenants/7/models/18/mapping/runs/1150/execute"
        && init?.method === "POST"
      ))).toHaveLength(2);
    });
  });

  it("cannot dismiss Mapping configuration while create/start is pending", async () => {
    let releaseExecute: (() => void) | undefined;
    const executeGate = new Promise<void>((resolve) => {
      releaseExecute = resolve;
    });
    const fetcher = mappingFetchStub({ executeGate });
    const user = userEvent.setup();
    render(<WorkbenchApp router={createWorkbenchRouter({
      api: createApiClient(fetcher),
      history: createMemoryHistory({ initialEntries: ["/tenants/7/mapping/models/18"] }),
    })} />);
    await screen.findByRole("table", { name: "Object Mappings" });

    await screen.findByRole("table", { name: "Object Mappings" });
    await user.click(await screen.findByRole("button", { name: "Generate mappings" }));
    await user.click(screen.getByText("Advanced settings"));
    await user.selectOptions(screen.getByLabelText("Source System"), "2");
    const submit = within(screen.getByRole("dialog")).getByRole("button", { name: "Generate mappings" });
    await waitFor(() => expect(submit).toBeEnabled());
    await user.click(submit);

    await waitFor(() => expect(screen.getByRole("button", {
      name: "Close Generate mappings",
    })).toBeDisabled());
    expect(screen.getByRole("button", { name: "Cancel" })).toBeDisabled();
    expect(screen.getByLabelText("Object Mapping Output Template")).toBeDisabled();
    expect(screen.getByLabelText("Attribute Mapping Output Template")).toBeDisabled();
    await user.keyboard("{Escape}");
    expect(screen.getByRole("dialog", { name: "Generate mappings" })).toBeVisible();

    releaseExecute?.();
    await waitFor(() => expect(screen.queryByRole(
      "dialog",
      { name: "Generate mappings" },
    )).not.toBeInTheDocument());
  });

  it.each([
    { layer: "logical_entity", customObject: false, templatesUnavailable: false },
    { layer: "dimensional_entity", customObject: false, templatesUnavailable: false },
    { layer: "logical_entity", customObject: true, templatesUnavailable: false },
    { layer: "logical_entity", customObject: false, templatesUnavailable: true },
  ])("uses server-resolved global defaults with independent overrides: $layer, custom=$customObject, unavailable=$templatesUnavailable", async ({ layer, customObject, templatesUnavailable }) => {
    const fetcher = mappingFetchStub({ templatesUnavailable });
    const user = userEvent.setup();
    render(<WorkbenchApp router={createWorkbenchRouter({
      api: createApiClient(fetcher),
      history: createMemoryHistory({ initialEntries: ["/tenants/7/mapping/models/18"] }),
    })} />);

    await screen.findByRole("table", { name: "Object Mappings" });
    if (layer === "dimensional_entity") await user.click(within(screen.getByRole("navigation", { name: "Mapping layer" })).getByRole("link", { name: "Dimensional" }));
    await user.click(await screen.findByRole("button", { name: "Generate mappings" }));
    await user.click(screen.getByText("Advanced settings"));
    const dialog = await screen.findByRole("dialog", { name: "Generate mappings" });
    if (templatesUnavailable) {
      expect(await within(dialog).findByText("Custom templates could not be loaded. Global defaults remain available.")).toHaveTextContent(
        "Custom templates could not be loaded. Global defaults remain available.",
      );
    } else {
      await screen.findByRole("option", { name: "Standard Attribute Mapping · Schema valid" });
    }
    expect(within(dialog).queryByLabelText("Layer")).not.toBeInTheDocument();
    expect(fetcher.mock.calls.some(([input]) => String(input).includes(`/mapping/generation-targets?entity_type=${layer}`))).toBe(true);
    await within(dialog).findByRole("checkbox", { name: "Generate silver_nwa.customer from CRM" });
    await user.selectOptions(screen.getByLabelText("Source System"), "2");
    if (customObject) {
      await user.selectOptions(screen.getByLabelText("Object Mapping Output Template"), "801");
    }
    expect(within(screen.getByLabelText("Attribute Mapping Output Template")).getByRole("option", { name: "Use global default" })).toHaveProperty("selected", true);
    await waitFor(() => expect(within(screen.getByRole("dialog")).getByRole("button", { name: "Generate mappings" })).toBeEnabled());
    await user.click(within(screen.getByRole("dialog")).getByRole("button", { name: "Generate mappings" }));

    const createCall = fetcher.mock.calls.find(([input, init]) => (
      String(input) === "/api/v1/tenants/7/models/18/runs" && init?.method === "POST"
    ));
    expect(JSON.parse(String(createCall?.[1]?.body))).toEqual(expect.objectContaining({
      mapping_object_output_template_id: customObject ? 801 : null,
      mapping_attribute_output_template_id: null,
    }));
  });
});

function mappingFetchStub(options: {
  hasNextPage?: boolean;
  empty?: boolean;
  denied?: boolean;
  error?: boolean;
  modelRevision?: number;
  hasLock?: boolean;
  role?: string;
  executeConflictOnce?: boolean;
  executeGate?: Promise<void>;
  templatesUnavailable?: boolean;
  generationTargets?: Array<Record<string, unknown>>;
} = {}) {
  let executeAttempts = 0;
  return vi.fn<typeof fetch>(async (input) => {
    const url = String(input);
    if (url === "/api/v1/tenants/7/home") return jsonResponse({
      ...tenantHome,
      tenant: { ...tenantHome.tenant, effective_role: options.role ?? "tenant_admin" },
      lock: {
        ...tenantHome.lock,
        is_locked: options.hasLock ?? true,
        owned_by_current_principal: options.hasLock ?? true,
      },
    });
    if (url === "/api/v1/tenants/7/models?status=active&page_size=200") {
      return jsonResponse({ items: [modelLedger], next_cursor: null });
    }
    if (url === "/api/v1/tenants/7/models/18") return jsonResponse(modelDetail);
    if (url.startsWith("/api/v1/tenants/7/models/18/mapping/generation-targets?")) {
      return jsonResponse({ model_id: 18, model_revision: 18, next_cursor: null, items: options.generationTargets ?? [{
        ...mappingTarget, source_system: sourceSystem, entity_name: "customer",
        mapping_object_id: 81, object_order: 0, is_locked: false, has_sources: true,
        attributes: [{ attribute_id: 702, attribute_name: "customer_name", modeled_attribute_name: "CustomerName", ordinal_position: 1, is_locked: false, is_authored: true }],
      }] });
    }
    if (url.startsWith("/api/v1/tenants/7/models/18/mapping/objects?")) {
      if (options.denied) return jsonResponse({ error: { code: "authorization_denied" } }, 403);
      if (options.error) return jsonResponse({ error: { code: "unavailable" } }, 503);
      const nextPage = url.includes("cursor=objects-next");
      return jsonResponse({
        model_id: 18,
        model_revision: options.modelRevision ?? 18,
        items: options.empty ? [] : [{
          ...mappingObject,
          ...(nextPage ? { mapping_object_id: 82, target: { ...mappingObject.target, entity_name: "contact" } } : {}),
        }],
        next_cursor: options.hasNextPage && !nextPage ? "objects-next" : null,
      });
    }
    if (url === "/api/v1/tenants/7/models/18/mapping/objects/81") return jsonResponse(mappingObjectDetail);
    if (url.startsWith("/api/v1/tenants/7/models/18/mapping/attributes?")) {
      if (options.denied) return jsonResponse({ error: { code: "authorization_denied" } }, 403);
      if (options.error) return jsonResponse({ error: { code: "unavailable" } }, 503);
      const nextPage = url.includes("cursor=attributes-next");
      const parentId = new URL(url, "http://localhost").searchParams.get("mapping_object_id");
      return jsonResponse({
        model_id: 18,
        model_revision: options.modelRevision ?? 18,
        items: options.empty || parentId !== "81" ? [] : [{
          ...mappingAttribute,
          ...(nextPage ? { mapping_attribute_id: 92, target: { ...mappingAttribute.target, attribute_name: "email" } } : {}),
        }],
        next_cursor: options.hasNextPage && !nextPage ? "attributes-next" : null,
      });
    }
    if (url === "/api/v1/tenants/7/models/18/mapping/attributes/91") return jsonResponse(mappingAttributeDetail);
    if (url === "/api/v1/tenants/7/output-templates?target_type=mapping_object&active=true&page_size=200") {
      if (options.templatesUnavailable) return jsonResponse({ error: { code: "unavailable" } }, 503);
      return jsonResponse({
        tenant_id: 7,
        items: [objectOutputTemplate, {
          ...objectOutputTemplate,
          output_template_id: 803,
          output_template_code: "mapping.object.broken",
          output_template_name: "Broken Object Mapping",
          output_template_schema_digest_is_valid: false,
        }],
        next_cursor: null,
      });
    }
    if (url === "/api/v1/tenants/7/output-templates?target_type=mapping_attribute&active=true&page_size=200") {
      if (options.templatesUnavailable) return jsonResponse({ error: { code: "unavailable" } }, 503);
      return jsonResponse({ tenant_id: 7, items: [attributeOutputTemplate], next_cursor: null });
    }
    if (url === "/api/v1/config/agent-capabilities") return jsonResponse(agentCapabilities);
    if (url === "/api/v1/tenants/7/models/18/runs?workflow=mapping&page_size=5") {
      return jsonResponse({ items: [], next_cursor: null });
    }
    if (url === "/api/v1/tenants/7/models/18/runs") {
      return jsonResponse({
        created: true,
        workflow_run_id: 1150,
        workflow_run_state: "queued",
        correlation_id: "mapping-run-1150",
        prompt_snapshot_count: 5,
        created_at: "2026-08-24T11:00:00Z",
      }, 201);
    }
    if (url === "/api/v1/tenants/7/models/18/mapping/runs/1150/execute") {
      executeAttempts += 1;
      await options.executeGate;
      if (options.executeConflictOnce && executeAttempts === 1) {
        return jsonResponse({ error: { code: "tenant_workflow_conflict" } }, 409);
      }
      return jsonResponse({
        changed: true,
        workflow_run_id: 1150,
        workflow_run_state: "running",
        model_revision: 18,
      }, 202);
    }
    return new Response(null, { status: 404 });
  });
}

const tenantHome = {
  tenant: {
    tenant_id: 7,
    tenant_code: "NWA",
    tenant_name: "Northwind Analytics",
    tenant_description: null,
    tenant_visibility: "private",
    effective_role: "tenant_admin",
  },
  lock: {
    is_locked: true,
    owner_display_name: "Maaz",
    owned_by_current_principal: true,
    purpose: "Mapping review",
    acquired_at: "2026-08-24T10:00:00Z",
    expires_at: "2026-08-24T12:00:00Z",
  },
  lock_actions: { can_acquire: false, can_renew: true, can_release: true, can_override: false },
  systems: [],
};

const modelLedger = {
  model_id: 18,
  model_name: "Customer 360",
  model_description: "Cross-system customer domain",
  model_revision: 18,
  model_input_scope_object_count: 25,
  latest_workflow: "mapping",
  latest_run_status: "completed",
  updated_at: "2026-08-24T10:00:00Z",
};

const modelDetail = {
  ...modelLedger,
  tenant_id: 7,
  logical_schemas: [], dimensional_schemas: [], silver_model_naming_instructions: null,
  silver_model_audit_columns_template: null,
  gold_model_naming_instructions: null,
  gold_model_technical_columns_template: null,
  gold_model_audit_columns_template: null,
  default_agent_sdk_code: "openai_agents",
  default_agent_provider_code: "databricks",
  default_agent_model_code: "databricks-primary",
  default_reasoning_effort_code: "medium",
  default_max_turns: 8,
  default_validation_retry_count: 1,
  is_active: true,
};

const sourceSystem = { system_id: 2, system_code: "CRM", system_name: "Customer CRM" };

const mappingTarget = {
  entity_type: "logical_entity", entity_id: 701,
  entity_schema_name: "silver_nwa", entity_name: "customer",
};

const mappingObject = {
  mapping_object_id: 81,
  workflow_run_id: 1048,
  target: mappingTarget,
  source_system: { system_id: 2, system_code: "CRM", system_name: "Customer CRM" },
  dependency_order: 10,
  status: "active",
  is_locked: true,
  updated_at: "2026-08-24T10:00:00Z",
};

const mappingObjectDetail = {
  ...mappingObject,
  mapping_document: {
    transformation_kind: "derived",
    join_strategy: {
      base_object: "customer_raw",
      joins: [{ object_name: "customer_address_raw", join_type: "left" }],
    },
    filter_criteria: ["customer_raw.is_deleted = false"],
  },
  output_template: {
    output_template_id: 31,
    output_template_code: "mapping.object.standard",
    output_template_name: "Standard Object Mapping",
    output_template_target_type: "mapping_object",
    output_template_schema_digest: "c".repeat(64),
    is_active: true,
  },
  created_at: "2026-08-24T09:00:00Z",
};

const mappingAttribute = {
  mapping_attribute_id: 91,
  workflow_run_id: 1048,
  mapping_object_id: 81,
  target: {
    entity: mappingTarget,
    attribute_id: 702,
    attribute_name: "customer_name",
    ordinal_position: 2,
    data_type: "string",
  },
  source_system: { system_id: 2, system_code: "CRM", system_name: "Customer CRM" },
  status: "active",
  is_locked: false,
  updated_at: "2026-08-24T10:00:00Z",
};

const mappingAttributeDetail = {
  ...mappingAttribute,
  parent_object_mapping: {
    mapping_object_id: 81,
    dependency_order: 10,
    status: "active",
    is_locked: true,
  },
  mapping_document: {
    target_attribute_name: "customer_name",
    source_attributes: ["crm_customer.customer_name"],
    transformation_steps: [{ step: 1, instruction: "Normalize whitespace" }],
  },
  output_template: {
    ...mappingObjectDetail.output_template,
    output_template_id: 32,
    output_template_code: "mapping.attribute.standard",
    output_template_name: "Standard Attribute Mapping",
    output_template_target_type: "mapping_attribute",
  },
  created_at: "2026-08-24T09:05:00Z",
};

const agentCapabilities = {
  schema_version: "3.0",
  sdks: [{ code: "openai_agents_sdk", name: "OpenAI Agents", provider_codes: ["microsoft_foundry"] }],
  providers: [{ code: "microsoft_foundry", name: "Microsoft Foundry" }],
  models: [{
    code: "foundry-primary",
    name: "GPT-5.6",
    provider_code: "microsoft_foundry",
    deployment_name: "foundry-primary",
    execution_profiles: ["tool_assisted"].map((execution_mode) => ({
      sdk_code: "openai_agents_sdk",
      execution_mode,
      reasoning_effort_codes: ["medium"],
    })),
  }],
  reasoning_efforts: [{ code: "medium", name: "Medium" }],
  max_turns: { minimum: 1, default: 8, maximum: 50 },
  validation_retries: { minimum: 0, default: 1, maximum: 5 },
};

const objectOutputTemplate = {
  output_template_id: 801,
  output_template_code: "mapping.object.standard",
  output_template_name: "Standard Object Mapping",
  output_template_description: "Structured Object Mapping output.",
  output_template_target_type: "mapping_object",
  output_template_schema_digest: "c".repeat(64),
  output_template_schema_digest_is_valid: true,
  is_active: true,
  field_count: 5,
};

const attributeOutputTemplate = {
  ...objectOutputTemplate,
  output_template_id: 802,
  output_template_code: "mapping.attribute.standard",
  output_template_name: "Standard Attribute Mapping",
  output_template_description: "Structured Attribute Mapping output.",
  output_template_target_type: "mapping_attribute",
  output_template_schema_digest: "d".repeat(64),
  field_count: 4,
};

function jsonResponse(value: unknown, status = 200): Response {
  return new Response(JSON.stringify(value), {
    status,
    headers: { "content-type": "application/json" },
  });
}


it.each([["Object mappings", "mapping_object", 81], ["Attribute mappings", "mapping_attribute", 91]] as const)("reviews selected %s through the governed endpoint", async (view, dataset, recordId) => {
  const { fetcher, commands } = withRecordReview(mappingFetchStub());
  render(<WorkbenchApp router={createWorkbenchRouter({ api: createApiClient(fetcher),
    history: createMemoryHistory({ initialEntries: ["/tenants/7/mapping/models/18"] }),
  })} />);
  const user = userEvent.setup();
  await screen.findByRole("table", { name: "Object Mappings" });
  if (view === "Attribute mappings") {
    await user.click(await screen.findByRole("link", { name: "Open Object Mapping 81" }));
  }
  const selection = await screen.findByRole("checkbox", { name: new RegExp(`^Select Mapping .* ${recordId}$`) });
  await user.click(selection);
  expect(screen.getByRole("checkbox", { name: new RegExp(`^Select Mapping .* ${recordId}$`) })).toBeChecked();
  expect(screen.getByRole("checkbox", { name: new RegExp(`^Select Mapping .* ${recordId}$`) })).toHaveFocus();
  await waitFor(() => expect(screen.getByRole("button", { name: "Lock selected" })).toBeEnabled());
  await user.click(screen.getByRole("button", { name: "Lock selected" }));
  const apply = await screen.findByRole("button", { name: "Apply this change" });
  expect(commands[0]).toEqual({ dataset, record_ids: [recordId], action: "lock", expected_model_revision: 18 });
  await user.click(apply);
  expect(commands[1]).toEqual({ ...commands[0], expected_plan_digest: "c".repeat(64) });
  const refreshName = view === "Attribute mappings" ? "Refresh Attributes" : "Refresh";
  await waitFor(() => expect(screen.getByRole("button", { name: refreshName })).toHaveFocus());
  expect(screen.getByRole("button", { name: refreshName })).toBeVisible();
  expect(screen.getByRole("checkbox", { name: new RegExp(`^Select Mapping .* ${recordId}$`) })).not.toBeChecked();
});


it("selects Objects with their unlocked Attributes and preserves explicit exclusions", async () => {
  const source = sourceSystem;
  const target = { ...mappingTarget, source_system: source, entity_name: "customer",
    object_order: 0, has_sources: true, is_locked: false,
    attributes: [
      { attribute_id: 702, attribute_name: "customer_name", modeled_attribute_name: "Name", ordinal_position: 1, is_locked: false, is_authored: true },
      { attribute_id: 703, attribute_name: "email", modeled_attribute_name: "Email", ordinal_position: 2, is_locked: false, is_authored: true },
      { attribute_id: 704, attribute_name: "customer_id", modeled_attribute_name: "ID", ordinal_position: 3, is_locked: true, is_authored: true },
    ],
  };
  const fetcher = mappingFetchStub({ generationTargets: [target,
    { ...target, entity_id: 705, entity_name: "orders", is_locked: true },
  ] });
  const user = userEvent.setup();
  render(<WorkbenchApp router={createWorkbenchRouter({ api: createApiClient(fetcher),
    history: createMemoryHistory({ initialEntries: ["/tenants/7/mapping/models/18"] }),
  })} />);
  await screen.findByRole("table", { name: "Object Mappings" });
  await user.click(await screen.findByRole("button", { name: "Generate mappings" }));
  const dialog = within(await screen.findByRole("dialog"));
  expect(await dialog.findByRole("checkbox", { name: "Generate silver_nwa.customer from CRM" })).toBeChecked();
  expect(dialog.getByRole("checkbox", { name: "Generate silver_nwa.orders from CRM" })).toBeDisabled();
  await user.click(dialog.getByRole("button", { name: "Choose Attributes for customer from CRM" }));
  expect(dialog.getByRole("checkbox", { name: "Generate customer.customer_id from CRM" })).toBeDisabled();
  await user.click(dialog.getByRole("checkbox", { name: "Generate customer.email from CRM" }));
  expect(dialog.getByText("1 Entity–System mappings · 1 Attributes to generate")).toBeVisible();
  expect(dialog.getByText(/2 Attributes preserved/)).toBeVisible();
  await user.click(dialog.getByRole("button", { name: "Generate mappings" }));
  await waitFor(() => expect(screen.queryByRole("dialog")).not.toBeInTheDocument());
  const call = fetcher.mock.calls.find(([input, init]) => String(input).endsWith("/models/18/runs") && init?.method === "POST");
  expect(JSON.parse(String(call?.[1]?.body)).mapping_targets).toEqual([
    { modeled_entity_id: 701, source_system_id: 2, selected_attribute_ids: [702] },
  ]);
});

it("assesses every input System even without saved Entity source links", async () => {
  const target = { ...mappingTarget, entity_name: "customer",
    object_order: 0, has_sources: false, is_locked: false,
    attributes: [{ attribute_id: 702, attribute_name: "customer_name", modeled_attribute_name: "Name",
      ordinal_position: 1, is_locked: false, is_authored: false }],
  };
  const fetcher = mappingFetchStub({ generationTargets: ["CRM", "ERP", "BILLING"].map((system_code, index) => ({
    ...target, source_system: { system_id: index + 2, system_code, system_name: system_code },
  })) });
  const user = userEvent.setup();
  render(<WorkbenchApp router={createWorkbenchRouter({ api: createApiClient(fetcher),
    history: createMemoryHistory({ initialEntries: ["/tenants/7/mapping/models/18?layer=logical&view=objects"] }),
  })} />);
  await user.click(await screen.findByRole("button", { name: "Generate mappings" }));
  const dialog = within(await screen.findByRole("dialog"));
  for (const system of ["CRM", "ERP", "BILLING"]) {
    expect(await dialog.findByRole("checkbox", { name: `Generate silver_nwa.customer from ${system}` })).toBeChecked();
  }
  expect(dialog.queryByText("No eligible sources")).not.toBeInTheDocument();
  await user.click(dialog.getByRole("button", { name: "Generate mappings" }));
  await waitFor(() => expect(screen.queryByRole("dialog")).not.toBeInTheDocument());
  const call = fetcher.mock.calls.find(([input, init]) => String(input).endsWith("/models/18/runs") && init?.method === "POST");
  expect(JSON.parse(String(call?.[1]?.body)).mapping_targets).toEqual([2, 3, 4].map((source_system_id) => ({
    modeled_entity_id: 701, source_system_id, selected_attribute_ids: [702],
  })));
});

it("keeps layer filters and detail navigation scoped to Dimensional", async () => {
  const base = mappingFetchStub();
  const fetcher = vi.fn<typeof fetch>(async (input, init) => String(input).endsWith("/mapping/objects/81")
    ? jsonResponse({ ...mappingObjectDetail, target: { ...mappingObjectDetail.target, entity_type: "dimensional_entity" } })
    : base(input, init));
  const user = userEvent.setup();
  const router = createWorkbenchRouter({ api: createApiClient(fetcher),
    history: createMemoryHistory({ initialEntries: ["/tenants/7/mapping/models/18"] }) });
  render(<WorkbenchApp router={router} />);
  await user.click(await screen.findByRole("checkbox", { name: "Select Mapping Objects 81" }));
  await user.click(within(screen.getByRole("navigation", { name: "Mapping layer" })).getByRole("link", { name: "Dimensional" }));
  expect(await screen.findByRole("checkbox", { name: "Select Mapping Objects 81" })).not.toBeChecked();
  expect(within(screen.getByRole("navigation", { name: "Mapping layer" })).getByRole("link", { name: "Dimensional" })).toHaveAttribute("aria-current", "page");
  expect(fetcher).toHaveBeenCalledWith(
    "/api/v1/tenants/7/models/18/mapping/objects?entity_type=dimensional_entity&page_size=200", expect.anything(),
  );
  expect(screen.queryByRole("link", { name: "Review target bindings" })).not.toBeInTheDocument();
  await user.click(await screen.findByRole("link", { name: "Open Object Mapping 81" }));
  await user.click(await screen.findByRole("link", { name: "Back to Object mappings" }));
  expect(await screen.findByRole("table", { name: "Object Mappings" })).toBeVisible();
  expect(within(screen.getByRole("navigation", { name: "Mapping layer" })).getByRole("link", { name: "Dimensional" })).toHaveAttribute("aria-current", "page");
  expect(fetcher).toHaveBeenCalledWith(
    "/api/v1/tenants/7/models/18/mapping/objects?entity_type=dimensional_entity&page_size=200", expect.anything(),
  );
});

it("retains the Dimensional layer across Mapping, Code generation, and Validation Model tabs", async () => {
  const base = mappingFetchStub();
  const fetcher = vi.fn<typeof fetch>(async (input, init) => {
    const url = String(input);
    if (url.includes("/code-generation/targets?") || url.includes("/validation/systems?")) {
      return jsonResponse({ model_id: 18, model_revision: 18, items: [], next_cursor: null, is_truncated: false });
    }
    if (url.includes("/validation/ledger?")) return jsonResponse({ model_id: 18, model_revision: 18, groups: [] });
    if (url.includes("/runs?")) return jsonResponse({ items: [], next_cursor: null });
    return base(input, init);
  });
  const user = userEvent.setup();
  const router = createWorkbenchRouter({ api: createApiClient(fetcher),
    history: createMemoryHistory({ initialEntries: ["/tenants/7/mapping/models/18?layer=dimensional"] }) });
  render(<WorkbenchApp router={router} />);
  await screen.findByRole("table", { name: "Object Mappings" });
  for (const [tab, heading, path, layerNav] of [
    ["Code generation", "Code generation", "code-generation", "Code generation layer"],
    ["Validation", "Validation", "validation", "Validation layer"],
    ["Mapping", "Mapping", "mapping", "Mapping layer"],
  ] as const) {
    await user.click(within(screen.getByRole("navigation", { name: "Model sections" })).getByRole("link", { name: tab }));
    await screen.findByRole("heading", { name: heading, level: 1 });
    expect(router.state.location.pathname).toBe(`/tenants/7/${path}/models/18`);
    expect(router.state.location.search).toEqual({ layer: "dimensional" });
    expect(within(screen.getByRole("navigation", { name: layerNav })).getByRole("link", { name: "Dimensional" })).toHaveAttribute("aria-current", "page");
    expect(within(screen.getByRole("navigation", { name: "Model sections" })).getByRole("link", { name: tab })).toHaveAttribute("aria-current", "page");
  }
  const workflowDataCalls = fetcher.mock.calls.map(([input]) => String(input)).filter((url) =>
    /\/(?:code-generation\/targets|validation\/(?:systems|ledger)|mapping\/objects)\?/.test(url));
  expect(workflowDataCalls).toHaveLength(5);
  expect(workflowDataCalls.every((url) => url.includes("entity_type=dimensional_entity"))).toBe(true);
});

it("retains Object and Attribute choices across scope modes, detail navigation and search", async () => {
  const target = { ...mappingTarget, source_system: sourceSystem, entity_name: "customer",
    mapping_object_id: 81, object_order: 0, has_sources: true, is_locked: false,
    attributes: [
      { attribute_id: 702, attribute_name: "customer_name", modeled_attribute_name: "Name", ordinal_position: 1, is_locked: false, is_authored: true },
      { attribute_id: 703, attribute_name: "customer_id", modeled_attribute_name: "ID", ordinal_position: 2, is_locked: true, is_authored: true },
    ],
  };
  const fetcher = mappingFetchStub({ generationTargets: [target,
    { ...target, entity_id: 705, entity_name: "orders", attributes: [
      { attribute_id: 802, attribute_name: "order_id", modeled_attribute_name: "OrderID", ordinal_position: 1, is_locked: false, is_authored: true },
    ] },
    { ...target, entity_id: 706, entity_name: "locked", is_locked: true },
  ] });
  const user = userEvent.setup();
  render(<WorkbenchApp router={createWorkbenchRouter({ api: createApiClient(fetcher),
    history: createMemoryHistory({ initialEntries: ["/tenants/7/mapping/models/18?view=objects"] }),
  })} />);
  await user.click(await screen.findByRole("button", { name: "Generate mappings" }));
  const dialog = within(await screen.findByRole("dialog"));
  const controls = dialog.getAllByRole("combobox");
  expect(controls.slice(0, 3)).toEqual([
    dialog.getByLabelText("Execution mode"), dialog.getByLabelText("Model"), dialog.getByLabelText("Reasoning effort"),
  ]);
  await dialog.findByRole("checkbox", { name: "Generate silver_nwa.customer from CRM" });
  await user.click(dialog.getByRole("radio", { name: "Selected Entities" }));
  await user.click(dialog.getByRole("button", { name: "Clear Entity selection" }));
  expect(dialog.getByRole("button", { name: "Generate mappings" })).toBeDisabled();
  await user.click(dialog.getByRole("checkbox", { name: "Generate silver_nwa.customer from CRM" }));
  const chooseCustomer = dialog.getByRole("button", { name: "Choose Attributes for customer from CRM" });
  await user.click(chooseCustomer);
  expect(dialog.getByRole("heading", { name: "customer" })).toHaveFocus();
  await user.click(dialog.getByRole("button", { name: "Clear Attribute selection" }));
  expect(dialog.getByRole("checkbox", { name: "Generate customer.customer_name from CRM" })).not.toBeChecked();
  await user.click(dialog.getByRole("button", { name: "Select all unlocked Attributes" }));
  expect(dialog.getByRole("checkbox", { name: "Generate customer.customer_name from CRM" })).toBeChecked();
  expect(dialog.getByRole("checkbox", { name: "Generate customer.customer_id from CRM" })).toBeDisabled();
  expect(dialog.getByRole("checkbox", { name: "Generate customer.customer_id from CRM" })).not.toBeChecked();
  await user.click(dialog.getByRole("button", { name: "Back to Entities" }));
  expect(dialog.getByRole("button", { name: "Choose Attributes for customer from CRM" })).toHaveFocus();
  await user.click(dialog.getByRole("radio", { name: "All unlocked Entities" }));
  expect(dialog.getByRole("checkbox", { name: "Generate silver_nwa.orders from CRM" })).toBeChecked();
  await user.click(dialog.getByRole("radio", { name: "Selected Entities" }));
  expect(dialog.getByRole("checkbox", { name: "Generate silver_nwa.orders from CRM" })).not.toBeChecked();
  await user.type(dialog.getByRole("searchbox", { name: "Find Entities" }), "orders");
  expect(dialog.getByText("1 Entity–System mappings · 1 Attributes to generate")).toBeVisible();
  await user.click(dialog.getByRole("button", { name: "Select all shown Entities" }));
  await user.click(dialog.getByRole("button", { name: "Generate mappings" }));
  await waitFor(() => expect(screen.queryByRole("dialog")).not.toBeInTheDocument());
  const call = fetcher.mock.calls.find(([input, init]) => String(input).endsWith("/models/18/runs") && init?.method === "POST");
  expect(JSON.parse(String(call?.[1]?.body)).mapping_targets).toEqual([
    { modeled_entity_id: 701, source_system_id: 2, selected_attribute_ids: [702] },
    { modeled_entity_id: 705, source_system_id: 2, selected_attribute_ids: [802] },
  ]);
});

it("selects unlocked Attributes across every page and rejects excluded missing mappings", async () => {
  const fetcher = mappingFetchStub({ generationTargets: [{
    ...mappingTarget, source_system: sourceSystem, entity_name: "customer", mapping_object_id: 81,
    object_order: 0, has_sources: true, is_locked: false,
    attributes: Array.from({ length: 52 }, (_, index) => ({ attribute_id: 800 + index,
      attribute_name: `field_${index}`, modeled_attribute_name: `Field${index}`,
      ordinal_position: index + 1, is_locked: index === 0, is_authored: index !== 51 })),
  }] });
  const user = userEvent.setup();
  render(<WorkbenchApp router={createWorkbenchRouter({ api: createApiClient(fetcher),
    history: createMemoryHistory({ initialEntries: ["/tenants/7/mapping/models/18?view=objects"] }),
  })} />);
  await user.click(await screen.findByRole("button", { name: "Generate mappings" }));
  const dialog = within(await screen.findByRole("dialog"));
  await user.click(await dialog.findByRole("button", { name: "Choose Attributes for customer from CRM" }));
  await user.click(dialog.getByRole("button", { name: "Clear Attribute selection" }));
  expect(dialog.getByRole("button", { name: "Generate mappings" })).toBeDisabled();
  expect(dialog.getByRole("alert")).toHaveTextContent("missing Attributes excluded");
  await user.click(dialog.getByRole("button", { name: "Next Attributes" }));
  expect(dialog.getByRole("checkbox", { name: "Generate customer.field_51 from CRM" })).not.toBeChecked();
  await user.click(dialog.getByRole("button", { name: "Select all unlocked Attributes" }));
  expect(dialog.getByRole("checkbox", { name: "Generate customer.field_51 from CRM" })).toBeChecked();
  await user.click(dialog.getByRole("button", { name: "Generate mappings" }));
  await waitFor(() => expect(screen.queryByRole("dialog")).not.toBeInTheDocument());
  const call = fetcher.mock.calls.find(([input, init]) => String(input).endsWith("/models/18/runs") && init?.method === "POST");
  expect(JSON.parse(String(call?.[1]?.body)).mapping_targets[0].selected_attribute_ids).toEqual(
    Array.from({ length: 51 }, (_, index) => 801 + index),
  );
});
