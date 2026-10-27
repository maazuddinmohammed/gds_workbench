// THROWAWAY sample API for the Subject Area cards prototype. Response shapes copied from the
// disposable local stack on 2026-10-26; all values are invented. Read-only: writes are refused.

const updated = "2026-10-26T13:42:00Z";
const revision = 14;

const systems = {
  CRM: { system_id: 1, system_code: "CRM", system_name: "Customer CRM" },
  ERP: { system_id: 2, system_code: "ERP", system_name: "Order ERP" },
  ECOM: { system_id: 3, system_code: "ECOM", system_name: "Web store" },
} as const;
type SystemCode = keyof typeof systems;

// [object id, System, schema, name, Attribute count, description]
const objectRows: [number, SystemCode, string, string, number, string][] = [
  [1, "CRM", "bronze_crm", "customer", 14, "Customer master records from the CRM."],
  [2, "CRM", "bronze_crm", "customer_address", 9, "Every customer address change, with an effective date."],
  [3, "CRM", "bronze_crm", "country", 3, "Country codes and names."],
  [4, "CRM", "bronze_crm", "loyalty_account", 8, "Loyalty programme membership and tier."],
  [5, "CRM", "bronze_crm", "campaign", 9, "Marketing campaigns and their channels."],
  [6, "CRM", "bronze_crm", "campaign_response", 6, "Customer responses to campaigns."],
  [7, "ERP", "bronze_erp", "sales_order", 16, "Store and phone orders."],
  [8, "ERP", "bronze_erp", "sales_order_line", 12, "Order lines with product and quantity."],
  [9, "ERP", "bronze_erp", "product", 11, "Product master with list price."],
  [10, "ERP", "bronze_erp", "product_category", 4, "Product category hierarchy."],
  [11, "ERP", "bronze_erp", "invoice", 10, "Invoices raised for orders."],
  [12, "ERP", "bronze_erp", "payment", 8, "Payments received against invoices."],
  [13, "ERP", "bronze_erp", "currency", 3, "Transaction currencies."],
  [14, "ERP", "bronze_erp", "shipment", 11, "Shipments sent to customers."],
  [15, "ERP", "bronze_erp", "warehouse", 6, "Warehouses that ship orders."],
  [16, "ECOM", "bronze_ecom", "web_order", 13, "Orders placed on the web store."],
  [17, "ECOM", "bronze_ecom", "web_session", 7, "Web store sessions."],
  [18, "ECOM", "bronze_ecom", "cart_item", 9, "Items in web store carts."],
];
const objects = objectRows.map(([id, system, schema, name, columns, description]) => ({ id, system, schema, name, columns, description }));
const objectById = new Map(objects.map((object) => [object.id, object]));

// [area id, name, definition, active, locked, object ids]
const areaRows: [number, string, string, boolean, boolean, number[]][] = [
  [1, "Customer", "People and businesses who buy from us, with their addresses and loyalty status.", true, false, [1, 2, 3, 4]],
  [2, "Sales", "Orders placed in stores, by phone and on the web store, with their lines.", true, false, [7, 8, 16, 18, 13, 1, 9]],
  [3, "Billing", "Invoices raised for orders and the payments that settle them.", true, true, [11, 12, 13, 7]],
  [4, "Product", "What we sell and how it is grouped for merchandising.", true, false, [9, 10]],
  [5, "Fulfilment", "How orders leave the warehouse and reach the customer.", true, false, [14, 15, 7]],
  [6, "Marketing", "Campaigns we run and how customers respond to them.", true, false, [5, 6, 1, 17]],
  [7, "Returns", "Customer returns and refunds. Retired; now covered by Billing.", false, false, [7, 12]],
];
const areas = areaRows.map(([id, name, definition, active, locked, objectIds]) => ({ id, name, definition, active, locked, objectIds }));
const activeAreas = areas.filter((area) => area.active);

type Attribute = [name: string, type: string, naturalKey?: boolean, nullable?: boolean];
interface ModelEntity {
  id: number; name: string; type: string; order: number; definition: string; grain: string;
  sources: number[]; attributes: Attribute[]; locked?: boolean;
}

const logicalEntities: ModelEntity[] = [
  { id: 1, name: "Country", type: "reference", order: 0, sources: [3], definition: "A country or territory used by customer and address records.", grain: "One row per ISO country code.",
    attributes: [["Country Code", "CHAR(2)", true], ["Country Name", "VARCHAR(100)"]] },
  { id: 2, name: "Currency", type: "reference", order: 0, sources: [13], locked: true, definition: "A currency in which orders, invoices and payments are recorded.", grain: "One row per ISO currency code.",
    attributes: [["Currency Code", "CHAR(3)", true], ["Currency Name", "VARCHAR(60)"], ["Minor Units", "SMALLINT"]] },
  { id: 3, name: "Product Category", type: "reference", order: 0, sources: [10], definition: "A grouping of products used for merchandising. Categories can nest.", grain: "One row per category.",
    attributes: [["Category ID", "INT", true], ["Category Name", "VARCHAR(120)"], ["Parent Category ID", "INT", false, true]] },
  { id: 4, name: "Warehouse", type: "reference", order: 0, sources: [15], definition: "A site that stores stock and ships orders.", grain: "One row per warehouse.",
    attributes: [["Warehouse ID", "INT", true], ["Warehouse Name", "VARCHAR(120)"], ["Country Code", "CHAR(2)"]] },
  { id: 5, name: "Customer", type: "core", order: 1, sources: [1], locked: true, definition: "A person or business that has placed, or may place, orders with the retailer.", grain: "One row per CRM customer.",
    attributes: [["Customer ID", "BIGINT", true], ["Customer Name", "VARCHAR(200)"], ["Email Address", "VARCHAR(320)", false, true], ["Segment Code", "VARCHAR(20)", false, true], ["Country Code", "CHAR(2)"], ["Customer Since", "DATE"]] },
  { id: 6, name: "Product", type: "core", order: 1, sources: [9], definition: "An item the retailer sells, identified by its ERP product number.", grain: "One row per ERP product.",
    attributes: [["Product ID", "BIGINT", true], ["SKU", "VARCHAR(40)"], ["Product Name", "VARCHAR(200)"], ["Category ID", "INT"], ["List Price", "DECIMAL(18,2)"], ["Is Discontinued", "BOOLEAN"]] },
  { id: 7, name: "Loyalty Account", type: "core", order: 2, sources: [4], definition: "A customer's membership in the loyalty programme.", grain: "One row per loyalty account.",
    attributes: [["Loyalty Account ID", "BIGINT", true], ["Customer ID", "BIGINT"], ["Tier Code", "VARCHAR(20)"], ["Points Balance", "INT"], ["Joined Date", "DATE"]] },
  { id: 8, name: "Campaign", type: "core", order: 0, sources: [5], definition: "A marketing campaign with a channel and run dates.", grain: "One row per campaign.",
    attributes: [["Campaign ID", "BIGINT", true], ["Campaign Name", "VARCHAR(200)"], ["Channel Code", "VARCHAR(20)"], ["Start Date", "DATE"], ["End Date", "DATE", false, true]] },
  { id: 9, name: "Customer Address", type: "history", order: 2, sources: [2], definition: "A postal address used by a customer, kept as dated versions.", grain: "One row per address version per customer.",
    attributes: [["Address ID", "BIGINT", true], ["Customer ID", "BIGINT"], ["Address Line 1", "VARCHAR(200)"], ["City", "VARCHAR(100)"], ["Postal Code", "VARCHAR(20)"], ["Country Code", "CHAR(2)"], ["Valid From", "DATE"]] },
  { id: 10, name: "Sales Order", type: "transaction", order: 2, sources: [7, 16], definition: "A customer's request to buy products, placed in a store, by phone or on the web store.", grain: "One row per submitted order.",
    attributes: [["Order ID", "BIGINT", true], ["Customer ID", "BIGINT"], ["Order Date", "DATE"], ["Channel Code", "VARCHAR(10)"], ["Order Status", "VARCHAR(20)"], ["Currency Code", "CHAR(3)"], ["Order Total", "DECIMAL(18,2)"]] },
  { id: 11, name: "Web Session", type: "event", order: 2, sources: [17], definition: "A visit to the web store, whether or not the visitor signed in.", grain: "One row per web store session.",
    attributes: [["Session ID", "VARCHAR(64)", true], ["Customer ID", "BIGINT", false, true], ["Started At", "TIMESTAMP"], ["Device Type", "VARCHAR(20)"], ["Landing Page", "VARCHAR(500)"]] },
  { id: 12, name: "Sales Order Line", type: "transaction", order: 3, sources: [8, 18], definition: "One product and quantity requested on a sales order.", grain: "One row per order line.",
    attributes: [["Order ID", "BIGINT", true], ["Line Number", "INT", true], ["Product ID", "BIGINT"], ["Quantity", "INT"], ["Unit Price", "DECIMAL(18,2)"], ["Discount Amount", "DECIMAL(18,2)", false, true], ["Line Amount", "DECIMAL(18,2)"]] },
  { id: 13, name: "Invoice", type: "transaction", order: 3, sources: [11], definition: "A bill raised for an order, stating the amount due and when.", grain: "One row per ERP invoice.",
    attributes: [["Invoice ID", "BIGINT", true], ["Order ID", "BIGINT"], ["Invoice Date", "DATE"], ["Due Date", "DATE"], ["Invoice Amount", "DECIMAL(18,2)"], ["Invoice Status", "VARCHAR(20)"]] },
  { id: 14, name: "Payment", type: "event", order: 4, sources: [12], definition: "Money received against an invoice. An invoice can be settled by several payments.", grain: "One row per payment received.",
    attributes: [["Payment ID", "BIGINT", true], ["Invoice ID", "BIGINT"], ["Paid At", "TIMESTAMP"], ["Payment Amount", "DECIMAL(18,2)"], ["Payment Method", "VARCHAR(20)"]] },
  { id: 15, name: "Shipment", type: "event", order: 3, sources: [14], definition: "A parcel sent from a warehouse for an order.", grain: "One row per shipment.",
    attributes: [["Shipment ID", "BIGINT", true], ["Order ID", "BIGINT"], ["Warehouse ID", "INT"], ["Shipped At", "TIMESTAMP"], ["Delivered At", "TIMESTAMP", false, true], ["Carrier Code", "VARCHAR(20)"]] },
  { id: 16, name: "Campaign Response", type: "event", order: 2, sources: [6], definition: "A customer's response to a campaign, such as a click or a purchase.", grain: "One row per response.",
    attributes: [["Response ID", "BIGINT", true], ["Campaign ID", "BIGINT"], ["Customer ID", "BIGINT"], ["Responded At", "TIMESTAMP"], ["Response Type", "VARCHAR(20)"]] },
];
const logicalById = new Map(logicalEntities.map((entity) => [entity.id, entity]));

// Dimensional sources are Logical Entity ids.
const dimensionalEntities: (ModelEntity & { factType: string | null })[] = [
  { id: 1, name: "Dim Customer", type: "dimension", factType: null, order: 0, sources: [5, 9, 1, 7], definition: "Customers with their current address, country and loyalty tier.", grain: "One row per customer version.",
    attributes: [["Customer Key", "BIGINT"], ["Customer ID", "BIGINT", true], ["Customer Name", "VARCHAR(200)"], ["Segment Code", "VARCHAR(20)"], ["Country Name", "VARCHAR(100)"], ["Loyalty Tier", "VARCHAR(20)"]] },
  { id: 2, name: "Dim Product", type: "dimension", factType: null, order: 0, sources: [6, 3], definition: "Products with their category path.", grain: "One row per product.",
    attributes: [["Product Key", "BIGINT"], ["Product ID", "BIGINT", true], ["Product Name", "VARCHAR(200)"], ["Category Name", "VARCHAR(120)"], ["List Price", "DECIMAL(18,2)"]] },
  { id: 3, name: "Dim Date", type: "dimension", factType: null, order: 0, sources: [], definition: "Calendar dates for reporting.", grain: "One row per calendar date.",
    attributes: [["Date Key", "INT"], ["Calendar Date", "DATE", true], ["Month Name", "VARCHAR(20)"], ["Year Number", "SMALLINT"]] },
  { id: 4, name: "Dim Currency", type: "dimension", factType: null, order: 0, sources: [2], definition: "Currencies used on orders and invoices.", grain: "One row per currency.",
    attributes: [["Currency Key", "BIGINT"], ["Currency Code", "CHAR(3)", true], ["Currency Name", "VARCHAR(60)"]] },
  { id: 5, name: "Dim Warehouse", type: "dimension", factType: null, order: 0, sources: [4], definition: "Warehouses that ship orders.", grain: "One row per warehouse.",
    attributes: [["Warehouse Key", "BIGINT"], ["Warehouse ID", "INT", true], ["Warehouse Name", "VARCHAR(120)"]] },
  { id: 6, name: "Dim Campaign", type: "dimension", factType: null, order: 0, sources: [8], definition: "Campaigns and their channels.", grain: "One row per campaign.",
    attributes: [["Campaign Key", "BIGINT"], ["Campaign ID", "BIGINT", true], ["Campaign Name", "VARCHAR(200)"], ["Channel Code", "VARCHAR(20)"]] },
  { id: 7, name: "Fact Order Line", type: "fact", factType: "transaction", order: 1, sources: [12, 10], definition: "Quantities and amounts for each order line.", grain: "One row per order line.",
    attributes: [["Order ID", "BIGINT"], ["Line Number", "INT"], ["Customer Key", "BIGINT"], ["Product Key", "BIGINT"], ["Order Date Key", "INT"], ["Quantity", "INT"], ["Line Amount", "DECIMAL(18,2)"]] },
  { id: 8, name: "Fact Invoice", type: "fact", factType: "accumulating_snapshot", order: 1, sources: [13, 14], definition: "Each invoice from issue to final payment.", grain: "One row per invoice.",
    attributes: [["Invoice ID", "BIGINT"], ["Customer Key", "BIGINT"], ["Invoice Date Key", "INT"], ["Paid Date Key", "INT"], ["Invoice Amount", "DECIMAL(18,2)"], ["Paid Amount", "DECIMAL(18,2)"]] },
  { id: 9, name: "Fact Shipment", type: "fact", factType: "transaction", order: 1, sources: [15], definition: "Shipments with their dispatch and delivery dates.", grain: "One row per shipment.",
    attributes: [["Shipment ID", "BIGINT"], ["Warehouse Key", "BIGINT"], ["Shipped Date Key", "INT"], ["Delivered Date Key", "INT"]] },
  { id: 10, name: "Fact Campaign Response", type: "fact", factType: "factless", order: 1, sources: [16, 8], definition: "Which customers responded to which campaigns.", grain: "One row per response.",
    attributes: [["Response ID", "BIGINT"], ["Campaign Key", "BIGINT"], ["Customer Key", "BIGINT"], ["Response Date Key", "INT"]] },
];

// Model records belong to the active areas that contain any of their source Objects.
const logicalAreaIds = (entity: ModelEntity) => activeAreas
  .filter((area) => entity.sources.some((objectId) => area.objectIds.includes(objectId)))
  .map((area) => area.id);
const dimensionalAreaIds = (entity: ModelEntity) => [...new Set(entity.sources.flatMap((id) => logicalAreaIds(logicalById.get(id)!)))]
  .sort((left, right) => left - right);
const areaRefs = (ids: number[]) => ids.map((id) => ({ subject_area_id: id, subject_area_name: areas.find((area) => area.id === id)!.name }));
const byOrder = (left: ModelEntity, right: ModelEntity) => left.order - right.order || left.name.localeCompare(right.name);

function objectRecord(id: number) {
  const object = objectById.get(id)!;
  return {
    object_id: object.id, tenant_code: "DEMO_RETAIL", system_code: object.system, connection_code: `${object.system}_GDS`,
    object_schema: object.schema, object_name: object.name, object_description: object.description, zone_code: "bronze",
    column_count: object.columns,
    areas: areas.filter((area) => area.objectIds.includes(id))
      .map((area) => ({ subject_area_id: area.id, subject_area_name: area.name, subject_area_table_id: area.id * 100 + id, subject_area_table_is_locked: false })),
  };
}

function areaSummary(area: (typeof areas)[number]) {
  const shared = area.objectIds.filter((id) => activeAreas.some((other) => other.id !== area.id && other.objectIds.includes(id)));
  return {
    subject_area_id: area.id, workflow_run_id: null, subject_area_name: area.name, subject_area_definition: area.definition,
    subject_area_is_active: area.active, subject_area_is_locked: area.locked, table_count: area.objectIds.length,
    column_count: area.objectIds.reduce((sum, id) => sum + objectById.get(id)!.columns, 0),
    shared_table_count: shared.length, updated_at: updated,
  };
}

function modelAreas(layer: "logical" | "dimensional") {
  const records = layer === "logical" ? logicalEntities : dimensionalEntities;
  const areaIds = layer === "logical" ? logicalAreaIds : dimensionalAreaIds;
  return {
    project_id: 1, project_revision: revision,
    items: activeAreas.map((area) => {
      const members = records.filter((entity) => areaIds(entity).includes(area.id));
      return {
        subject_area_id: area.id, subject_area_name: area.name, subject_area_definition: area.definition,
        table_count: area.objectIds.length, entity_count: members.length,
      };
    }),
  };
}

function logicalSummary(entity: ModelEntity) {
  return {
    logical_entity_id: entity.id, workflow_run_id: null, logical_entity_schema_name: "silver_retail",
    logical_entity_name: entity.name, logical_entity_type: entity.type, logical_entity_dependency_order: entity.order,
    logical_entity_is_active: true, logical_entity_is_locked: Boolean(entity.locked), updated_at: updated,
  };
}

function dimensionalSummary(entity: (typeof dimensionalEntities)[number]) {
  return {
    dimensional_entity_id: entity.id, workflow_run_id: null, dimensional_entity_schema_name: "gold_sales",
    dimensional_entity_name: entity.name, dimensional_entity_type: entity.type, dimensional_fact_type: entity.factType,
    dimensional_entity_dependency_order: entity.order, dimensional_entity_is_active: true,
    dimensional_entity_is_locked: Boolean(entity.locked), updated_at: updated,
  };
}

function attributes(layer: "logical" | "dimensional", entity: ModelEntity) {
  const schema = layer === "logical" ? "silver_retail" : "gold_sales";
  return entity.attributes.map(([name, type, naturalKey = false, nullable = false], index) => ({
    [`${layer}_attribute_id`]: entity.id * 100 + index + 1, workflow_run_id: null,
    [`${layer}_entity_id`]: entity.id, [`${layer}_entity_schema_name`]: schema, [`${layer}_entity_name`]: entity.name,
    [`${layer}_attribute_name`]: name, [`${layer}_attribute_data_type`]: type,
    [`${layer}_attribute_is_nullable`]: nullable, [`${layer}_attribute_is_natural_key`]: naturalKey,
    [`${layer}_attribute_is_surrogate_key`]: layer === "dimensional" && name.endsWith(" Key") && index === 0,
    [`${layer}_attribute_ordinal_position`]: index + 1, [`${layer}_attribute_is_audit_column`]: false,
    [`${layer}_attribute_is_active`]: true, [`${layer}_attribute_is_locked`]: false, updated_at: updated,
  }));
}

function page(items: unknown[]) {
  return { project_id: 1, project_revision: revision, items, next_cursor: null };
}

function home() {
  const now = Date.now();
  return {
    tenant: { tenant_id: 1, tenant_code: "DEMO_RETAIL", tenant_name: "Demo Retail", tenant_description: "Sample Tenant for prototypes", tenant_visibility: "private", effective_role: "architect" },
    lock: { is_locked: true, owner_display_name: "Jordan Lee", owned_by_current_principal: true, purpose: "Subject Area review",
      acquired_at: new Date(now - 20 * 60_000).toISOString(), expires_at: new Date(now + 40 * 60_000).toISOString() },
    lock_actions: { can_acquire: false, can_renew: true, can_release: true, can_override: false },
    systems: Object.values(systems).map((system) => ({
      ...system, system_type_name: "Database", connection_count: 1,
      registered_object_count: objects.filter((object) => object.system === system.system_code).length,
      active_project_count: 1, last_metadata_update_time: updated,
    })),
  };
}

const project = {
  project_id: 1, tenant_id: 1, project_name: "Customer Orders 360",
  project_description: "Conformed customers, orders and billing in Silver, with a Gold sales mart.",
  project_revision: revision, is_locked: false, project_input_scope_object_count: objects.length,
  logical_schemas: [{ schema_name: "silver_retail", description: "Conformed entities" }],
  dimensional_schemas: [{ schema_name: "gold_sales", description: "Sales mart" }],
  logical_entity_scd_type: "type_2", dimensional_entity_scd_type: "type_2",
  logical_coverage_threshold_percent: 70, dimensional_coverage_threshold_percent: 60,
  logical_enforce_coverage_threshold: false, dimensional_enforce_coverage_threshold: false,
  silver_model_naming_instructions: "Use snake_case names and preserve stable business identifiers.",
  silver_model_audit_columns_template: null,
  gold_model_naming_instructions: "Use dim_ and fact_ prefixes with explicit grain.",
  gold_model_technical_columns_template: null, gold_model_audit_columns_template: null,
  default_agent_sdk_code: null, default_agent_provider_code: null, default_agent_model_code: null,
  default_reasoning_effort_code: null, default_max_turns: null, default_validation_retry_count: null,
  is_active: true, updated_at: updated,
};

const overview = {
  project_id: 1, project_revision: revision,
  items: [
    ["scope", objects.length, "ready"], ["profiling", 18, "results_available"], ["analysis", 9, "results_available"],
    ["context", 11, "results_available"], ["subject_area", activeAreas.length, "results_available"],
    ["logical", logicalEntities.length, "results_available"], ["dimensional", dimensionalEntities.length, "results_available"],
  ].map(([workflow, count, state]) => ({
    workflow, result_count: count, locked_count: 0, latest_run_id: null, latest_run_state: null,
    latest_run_created_at: null, state, quality_warning_codes: [],
  })),
  section_states: [
    ["overview", "available"], ["settings", "available"], ["scope", "ready"], ["metadata-enrichment", "completed"],
    ["profiling", "results_available"], ["context", "results_available"], ["analysis", "results_available"],
    ["subject-area", "results_available"], ["logical", "results_available"], ["dimensional", "results_available"],
    ["mapping", "results_available"], ["code-generation", "results_available"], ["validation", "results_available"],
  ].map(([section, state]) => ({ section, state })),
};

function respond(url: URL): unknown {
  const path = url.pathname.replace(/^\/api\/v1\/tenants\/1/, "");
  const query = url.searchParams;
  const areaFilter = query.has("subject_area_id") ? Number(query.get("subject_area_id")) : null;
  let match: RegExpMatchArray | null;
  if (path === "/home") return home();
  if (path === "/projects/1") return project;
  if (path === "/projects/1/overview") return overview;
  if (path === "/projects/1/subject-areas") {
    return { project_id: 1, project_revision: revision, scope_table_count: objects.length, unassigned_table_count: 0, items: areas.map(areaSummary) };
  }
  if (path === "/projects/1/subject-areas/tables") return { project_id: 1, project_revision: revision, items: objects.map((object) => objectRecord(object.id)) };
  if ((match = path.match(/^\/projects\/1\/subject-areas\/(\d+)$/))) {
    const area = areas.find((item) => item.id === Number(match![1]));
    return area ? { ...areaSummary(area), project_id: 1, project_revision: revision, tables: area.objectIds.map(objectRecord) } : undefined;
  }
  if (path === "/projects/1/logical/subject-areas") return modelAreas("logical");
  if (path === "/projects/1/dimensional/subject-areas") return modelAreas("dimensional");
  if (path === "/projects/1/logical/entities") {
    return page(logicalEntities.filter((entity) => areaFilter === null || logicalAreaIds(entity).includes(areaFilter)).sort(byOrder).map(logicalSummary));
  }
  if (path === "/projects/1/dimensional/objects") {
    return page(dimensionalEntities.filter((entity) => areaFilter === null || dimensionalAreaIds(entity).includes(areaFilter)).sort(byOrder).map(dimensionalSummary));
  }
  if ((match = path.match(/^\/projects\/1\/logical\/entities\/(\d+)$/))) {
    const entity = logicalById.get(Number(match[1]));
    return entity ? {
      ...logicalSummary(entity), logical_entity_definition: entity.definition, logical_entity_grain: entity.grain, created_at: updated,
      subject_areas: areaRefs(logicalAreaIds(entity)),
      sources: entity.sources.map((objectId, index) => {
        const object = objectRecord(objectId);
        return {
          logical_entity_source_mapping_id: entity.id * 10 + index, workflow_run_id: null,
          rationale: `${object.object_name} supplies ${entity.name} records.`, is_active: true, is_locked: false,
          created_at: updated, updated_at: updated, support_source_type: "object",
          source_object: { object_id: objectId, tenant_code: object.tenant_code, system_code: object.system_code,
            connection_code: object.connection_code, object_schema: object.object_schema, object_name: object.object_name },
        };
      }),
    } : undefined;
  }
  if ((match = path.match(/^\/projects\/1\/dimensional\/objects\/(\d+)$/))) {
    const entity = dimensionalEntities.find((item) => item.id === Number(match![1]));
    return entity ? {
      ...dimensionalSummary(entity), dimensional_entity_definition: entity.definition,
      dimensional_entity_grain_definition: entity.grain, created_at: updated,
      subject_areas: areaRefs(dimensionalAreaIds(entity)),
      sources: entity.sources.map((logicalId, index) => ({
        dimensional_entity_source_mapping_id: entity.id * 10 + index, workflow_run_id: null,
        rationale: `Silver ${logicalById.get(logicalId)!.name} supplies this ${entity.type}.`, is_active: true, is_locked: false,
        created_at: updated, updated_at: updated, support_source_type: "logical_entity",
        source_logical_entity: { logical_entity_id: logicalId, logical_entity_schema_name: "silver_retail", logical_entity_name: logicalById.get(logicalId)!.name },
      })),
    } : undefined;
  }
  if (path === "/projects/1/logical/attributes") {
    const entity = logicalById.get(Number(query.get("logical_entity_id")));
    return page(entity ? attributes("logical", entity) : []);
  }
  if (path === "/projects/1/dimensional/attributes") {
    const entity = dimensionalEntities.find((item) => item.id === Number(query.get("dimensional_entity_id")));
    return page(entity ? attributes("dimensional", entity) : []);
  }
  // Other lists (runs, relationships, other sections) answer empty so their screens still render.
  if (query.has("page_size") || path.endsWith("/runs")) return page([]);
  return undefined;
}

function json(body: unknown, status = 200) {
  return new Response(JSON.stringify(body), { status, headers: { "content-type": "application/json" } });
}

export const sampleFetch: typeof fetch = async (input, init) => {
  const url = new URL(typeof input === "string" ? input : input instanceof URL ? input.href : input.url, window.location.origin);
  if ((init?.method ?? "GET").toUpperCase() !== "GET") return json({ code: "prototype_read_only" }, 409);
  const body = respond(url);
  return body === undefined ? json({ code: "not_in_prototype" }, 404) : json(body);
};
