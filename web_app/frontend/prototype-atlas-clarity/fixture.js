// THROWAWAY prototype fixture: synthetic retail records shaped like Atlas data.
// No production imports, API calls, persistence or real customer data.

const P = (nullPct, distinctPct) => ({ nullPct, distinctPct });

// One modeled Attribute. `map` holds one [source column, transformation logic] pair per System.
function a(name, type, flags, definition, map = {}, profile = null) {
  return {
    name, type, definition, map, profile,
    nk: Boolean(flags.nk), sk: Boolean(flags.sk), fk: flags.fk ?? null,
    pii: Boolean(flags.pii), nullable: Boolean(flags.nullable), src: flags.src ?? [],
  };
}

const copy = "Copy the source value.";

export const tenant = { name: "Demo Retail", role: "Architect", user: "Jordan Lee", initials: "JL" };
export const lock = { heldByMe: true, minutesLeft: 38 };

export const project = {
  name: "Customer Orders 360",
  description: "Conformed customers, orders and billing in Silver, with a Gold sales mart.",
  revision: 14,
  logicalSchema: "silver_retail",
  dimensionalSchema: "gold_sales",
  scd: "Type 2 / Type 2",
  updated: "Today, 9:42 AM",
  updatedBy: "Jordan Lee",
};

export const systems = [
  { code: "CRM", name: "Customer CRM" },
  { code: "ERP", name: "Order ERP" },
  { code: "ECOM", name: "Web store" },
];

export const subjectAreas = [
  { id: "customer", name: "Customer", description: "People and businesses who buy, with addresses and online sessions.",
    objects: ["bronze_crm.customer", "bronze_crm.customer_address", "bronze_crm.country", "bronze_crm.loyalty_account", "bronze_ecom.web_session"] },
  { id: "sales", name: "Sales", description: "Orders from stores, phone and the web store, with their lines.",
    objects: ["bronze_erp.sales_order", "bronze_erp.sales_order_line", "bronze_ecom.web_order", "bronze_ecom.cart_item", "bronze_erp.currency", "bronze_crm.customer", "bronze_erp.product"] },
  { id: "billing", name: "Billing", description: "Invoices raised for orders and the payments that settle them.",
    objects: ["bronze_erp.invoice", "bronze_erp.payment", "bronze_erp.currency", "bronze_erp.sales_order"] },
  { id: "product", name: "Product", description: "What is sold and how it is categorized.",
    objects: ["bronze_erp.product", "bronze_erp.product_category"] },
];

export const inputObjects = [
  ["CRM", "bronze_crm.customer", 125000], ["CRM", "bronze_crm.customer_address", 183402],
  ["CRM", "bronze_crm.country", 249], ["CRM", "bronze_crm.loyalty_account", 61220],
  ["ERP", "bronze_erp.sales_order", 842310], ["ERP", "bronze_erp.sales_order_line", 2915004],
  ["ERP", "bronze_erp.product", 8412], ["ERP", "bronze_erp.product_category", 146],
  ["ERP", "bronze_erp.invoice", 801977], ["ERP", "bronze_erp.payment", 790105],
  ["ERP", "bronze_erp.currency", 32], ["ECOM", "bronze_ecom.web_order", 311560],
  ["ECOM", "bronze_ecom.web_session", 4220918], ["ECOM", "bronze_ecom.cart_item", 1048331],
].map(([system, name, rows]) => ({ system, name, rows }));

export const entities = [
  {
    id: 1, name: "Country", type: "reference", order: 0, areas: ["customer"], locked: false, updated: "Oct 23, 4:20 PM",
    definition: "A country or territory used by customer and address records.",
    grain: "One row per ISO 3166 country code.",
    sources: [{ object: "bronze_crm.country", system: "CRM", rationale: "The CRM country list supplies the codes and names used across customer records." }],
    systems: ["CRM"],
    objectLogic: { CRM: { filter: "", sample: "SELECT iso_code, country_name\nFROM bronze_crm.country" } },
    attrs: [
      a("Country Code", "CHAR(2)", { nk: true }, "ISO 3166-1 alpha-2 code.", { CRM: ["bronze_crm.country.iso_code", "Copy the source value in upper case."] }, P(0, 100)),
      a("Country Name", "VARCHAR(100)", {}, "English short name of the country.", { CRM: ["bronze_crm.country.country_name", copy] }, P(0, 100)),
    ],
    sql: { file: "silver_country.sql", state: "current" }, checks: 1, feeds: ["dim_customer"], context: [],
  },
  {
    id: 2, name: "Currency", type: "reference", order: 0, areas: ["sales", "billing"], locked: true, updated: "Oct 23, 4:20 PM",
    definition: "A currency in which orders, invoices and payments are recorded.",
    grain: "One row per ISO 4217 currency code.",
    sources: [{ object: "bronze_erp.currency", system: "ERP", rationale: "ERP currency table is the only list of transaction currencies." }],
    systems: ["ERP"],
    objectLogic: { ERP: { filter: "", sample: "SELECT currency_cd, description, decimals\nFROM bronze_erp.currency" } },
    attrs: [
      a("Currency Code", "CHAR(3)", { nk: true }, "ISO 4217 currency code.", { ERP: ["bronze_erp.currency.currency_cd", copy] }, P(0, 100)),
      a("Currency Name", "VARCHAR(60)", {}, "Display name of the currency.", { ERP: ["bronze_erp.currency.description", copy] }, P(0, 100)),
      a("Minor Units", "SMALLINT", {}, "Number of decimal places used for amounts.", { ERP: ["bronze_erp.currency.decimals", copy] }, P(0, 9.4)),
    ],
    sql: { file: "silver_currency.sql", state: "current" }, checks: 1, feeds: ["dim_currency"], context: [],
  },
  {
    id: 3, name: "Product Category", type: "reference", order: 0, areas: ["product"], locked: false, updated: "Oct 23, 4:20 PM",
    definition: "A grouping of products used for merchandising and reporting. Categories can nest.",
    grain: "One row per category.",
    sources: [{ object: "bronze_erp.product_category", system: "ERP", rationale: "ERP category hierarchy, including parent links." }],
    systems: ["ERP"],
    objectLogic: { ERP: { filter: "Only active categories (is_active = 'Y').", sample: "SELECT category_id, name, parent_id\nFROM bronze_erp.product_category\nWHERE is_active = 'Y'" } },
    attrs: [
      a("Category ID", "INT", { nk: true }, "ERP category identifier.", { ERP: ["bronze_erp.product_category.category_id", copy] }, P(0, 100)),
      a("Category Name", "VARCHAR(120)", {}, "Name shown to merchandisers.", { ERP: ["bronze_erp.product_category.name", copy] }, P(0, 98.6)),
      a("Parent Category ID", "INT", { fk: "Product Category", nullable: true }, "The broader category this one belongs to; blank for top-level categories.", { ERP: ["bronze_erp.product_category.parent_id", copy] }, P(8.9, 15.1)),
    ],
    sql: { file: "silver_product_category.sql", state: "current" }, checks: 1, feeds: ["dim_product"], context: [],
  },
  {
    id: 4, name: "Customer", type: "core", order: 1, areas: ["customer", "sales"], locked: true, updated: "Today, 8:29 AM",
    definition: "A person or business that has placed, or may place, orders with the retailer.",
    grain: "One row per CRM customer.",
    sources: [{ object: "bronze_crm.customer", system: "CRM", rationale: "The CRM customer master is the system of record for customer identity." }],
    systems: ["CRM"],
    objectLogic: { CRM: { filter: "Exclude deleted customers (is_deleted = TRUE).", sample: "SELECT customer_id, customer_name, email,\n       segment_cd, country_cd, created_at\nFROM bronze_crm.customer\nWHERE is_deleted = FALSE" } },
    attrs: [
      a("Customer ID", "BIGINT", { nk: true }, "CRM identifier for the customer.", { CRM: ["bronze_crm.customer.customer_id", copy] }, P(0, 100)),
      a("Customer Name", "VARCHAR(200)", {}, "Display name of the person or business.", { CRM: ["bronze_crm.customer.customer_name", copy] }, P(0.14, 96.2)),
      a("Email Address", "VARCHAR(320)", { pii: true, nullable: true }, "Primary contact email.", { CRM: ["bronze_crm.customer.email", "Trim and lower-case the source value."] }, P(8.2, 91.0)),
      a("Segment Code", "VARCHAR(20)", { nullable: true }, "Marketing segment, such as RETAIL or TRADE.", { CRM: ["bronze_crm.customer.segment_cd", copy] }, P(31.4, 0.004)),
      a("Country Code", "CHAR(2)", { fk: "Country" }, "Country of the customer's billing address.", { CRM: ["bronze_crm.customer.country_cd", copy] }, P(0.6, 0.15)),
      a("Customer Since", "DATE", {}, "Date the customer record was created in the CRM.", { CRM: ["bronze_crm.customer.created_at", "CAST(created_at AS DATE)"] }, P(0, 2.9)),
    ],
    sql: { file: "silver_customer.sql", state: "current" }, checks: 3, feeds: ["dim_customer"], context: ["CR-08"],
  },
  {
    id: 5, name: "Product", type: "core", order: 1, areas: ["product", "sales"], locked: false, updated: "Oct 23, 4:20 PM",
    definition: "An item the retailer sells, identified by its ERP product number.",
    grain: "One row per ERP product.",
    sources: [{ object: "bronze_erp.product", system: "ERP", rationale: "ERP product master holds identity, price and category." }],
    systems: ["ERP"],
    objectLogic: { ERP: { filter: "", sample: "SELECT product_id, sku, product_name,\n       category_id, list_price, status_cd\nFROM bronze_erp.product" } },
    attrs: [
      a("Product ID", "BIGINT", { nk: true }, "ERP product number.", { ERP: ["bronze_erp.product.product_id", copy] }, P(0, 100)),
      a("SKU", "VARCHAR(40)", {}, "Stock keeping unit printed on packaging.", { ERP: ["bronze_erp.product.sku", copy] }, P(0, 99.9)),
      a("Product Name", "VARCHAR(200)", {}, "Name shown to customers.", { ERP: ["bronze_erp.product.product_name", copy] }, P(0, 97.3)),
      a("Category ID", "INT", { fk: "Product Category" }, "Lowest category the product belongs to.", { ERP: ["bronze_erp.product.category_id", copy] }, P(0.4, 1.7)),
      a("List Price", "DECIMAL(18,2)", {}, "Current catalogue price before discounts.", { ERP: ["bronze_erp.product.list_price", copy] }, P(1.2, 22.4)),
      a("Is Discontinued", "BOOLEAN", {}, "True when the product can no longer be ordered.", { ERP: ["bronze_erp.product.status_cd", "CASE WHEN status_cd = 'D' THEN TRUE ELSE FALSE END"] }, P(0, 0.02)),
    ],
    sql: { file: "silver_product.sql", state: "current" }, checks: 2, feeds: ["dim_product"], context: [],
  },
  {
    id: 6, name: "Customer Address", type: "history", order: 2, areas: ["customer"], locked: false, updated: "Oct 23, 4:20 PM",
    definition: "A postal address used by a customer, kept as dated versions.",
    grain: "One row per address version per customer.",
    sources: [{ object: "bronze_crm.customer_address", system: "CRM", rationale: "CRM keeps every address change with an effective date." }],
    systems: ["CRM"],
    objectLogic: { CRM: { filter: "", sample: "SELECT address_id, customer_id, address_line_1,\n       city, postal_code, country_cd, effective_date\nFROM bronze_crm.customer_address" } },
    attrs: [
      a("Address ID", "BIGINT", { nk: true }, "CRM address identifier.", { CRM: ["bronze_crm.customer_address.address_id", copy] }, P(0, 100)),
      a("Customer ID", "BIGINT", { fk: "Customer" }, "Customer who uses the address.", { CRM: ["bronze_crm.customer_address.customer_id", copy] }, P(0, 68.2)),
      a("Address Line 1", "VARCHAR(200)", { pii: true }, "Street and number.", { CRM: ["bronze_crm.customer_address.address_line_1", copy] }, P(0.3, 88.0)),
      a("City", "VARCHAR(100)", {}, "City or town.", { CRM: ["bronze_crm.customer_address.city", copy] }, P(0.2, 2.1)),
      a("Postal Code", "VARCHAR(20)", { pii: true }, "Postal or ZIP code.", { CRM: ["bronze_crm.customer_address.postal_code", copy] }, P(1.1, 9.6)),
      a("Country Code", "CHAR(2)", { fk: "Country" }, "Country of the address.", { CRM: ["bronze_crm.customer_address.country_cd", copy] }, P(0, 0.1)),
      a("Valid From", "DATE", {}, "Date this address version became effective.", { CRM: ["bronze_crm.customer_address.effective_date", copy] }, P(0, 1.9)),
    ],
    sql: { file: "silver_customer_address.sql", state: "current" }, checks: 1, feeds: ["dim_customer"], context: ["CR-08"],
  },
  {
    id: 7, name: "Sales Order", type: "transaction", order: 2, areas: ["sales", "billing"], locked: false, updated: "Today, 8:29 AM",
    definition: "A customer's request to buy products, placed in a store, by phone or on the web store.",
    grain: "One row per submitted order, from the ERP or the web store.",
    sources: [
      { object: "bronze_erp.sales_order", system: "ERP", rationale: "Store and phone orders are recorded in the ERP." },
      { object: "bronze_ecom.web_order", system: "ECOM", rationale: "Web store orders; combined with ERP orders as required by CR-01." },
    ],
    systems: ["ERP", "ECOM"],
    objectLogic: {
      ERP: { filter: "Exclude draft orders (status_cd = 'DRAFT').", sample: "SELECT order_id, customer_id, order_date,\n       status_cd, currency_cd, total_amount\nFROM bronze_erp.sales_order\nWHERE status_cd <> 'DRAFT'" },
      ECOM: { filter: "Exclude abandoned checkouts (state = 'ABANDONED').", sample: "SELECT web_order_id, customer_ref, placed_at,\n       state, currency, grand_total\nFROM bronze_ecom.web_order\nWHERE state <> 'ABANDONED'" },
    },
    attrs: [
      a("Order ID", "BIGINT", { nk: true }, "Order number, unique across ERP and web store orders.", {
        ERP: ["bronze_erp.sales_order.order_id", copy],
        ECOM: ["bronze_ecom.web_order.web_order_id", "9000000000 + web_order_id, so web orders never collide with ERP numbers."],
      }, P(0, 100)),
      a("Customer ID", "BIGINT", { fk: "Customer" }, "Customer who placed the order.", {
        ERP: ["bronze_erp.sales_order.customer_id", copy],
        ECOM: ["bronze_ecom.web_order.customer_ref", "Look up the CRM customer by customer_ref."],
      }, P(0, 14.8)),
      a("Order Date", "DATE", {}, "Date the order was submitted.", {
        ERP: ["bronze_erp.sales_order.order_date", copy],
        ECOM: ["bronze_ecom.web_order.placed_at", "CAST(placed_at AS DATE)"],
      }, P(0, 0.4)),
      a("Channel Code", "VARCHAR(10)", {}, "Where the order was placed: STORE, PHONE or WEB.", {
        ECOM: ["(constant)", "'WEB'"],
      }, null),
      a("Order Status", "VARCHAR(20)", {}, "Lifecycle status, such as OPEN, SHIPPED or CANCELLED.", {
        ERP: ["bronze_erp.sales_order.status_cd", "Map ERP status codes to the shared status list."],
        ECOM: ["bronze_ecom.web_order.state", "Map web store states to the shared status list."],
      }, P(0, 0.001)),
      a("Currency Code", "CHAR(3)", { fk: "Currency" }, "Currency of the order amounts.", {
        ERP: ["bronze_erp.sales_order.currency_cd", copy],
        ECOM: ["bronze_ecom.web_order.currency", "Upper-case the source value."],
      }, P(0, 0.002)),
      a("Order Total", "DECIMAL(18,2)", {}, "Total order value in the order currency, after discounts.", {
        ERP: ["bronze_erp.sales_order.total_amount", copy],
        ECOM: ["bronze_ecom.web_order.grand_total", copy],
      }, P(0, 31.0)),
    ],
    sql: { file: "silver_sales_order.sql", state: "stale", note: "Mapping changed after this file was generated." },
    checks: 4, feeds: ["fact_order_line", "dim_channel"], context: ["CR-01", "CR-02", "CR-03"],
  },
  {
    id: 8, name: "Web Session", type: "event", order: 2, areas: ["customer"], locked: false, updated: "Oct 23, 4:20 PM",
    definition: "A visit to the web store, whether or not the visitor signed in.",
    grain: "One row per web store session.",
    sources: [{ object: "bronze_ecom.web_session", system: "ECOM", rationale: "Web store session log; links to customers when they sign in." }],
    systems: ["ECOM"],
    objectLogic: {},
    attrs: [
      a("Session ID", "VARCHAR(64)", { nk: true, src: ["bronze_ecom.web_session.session_id"] }, "Web store session token.", {}, P(0, 100)),
      a("Customer ID", "BIGINT", { fk: "Customer", nullable: true, src: ["bronze_ecom.web_session.customer_id"] }, "Signed-in customer; blank for anonymous sessions.", {}, P(64.1, 1.2)),
      a("Started At", "TIMESTAMP", { src: ["bronze_ecom.web_session.started_at"] }, "When the session began.", {}, P(0, 99.2)),
      a("Device Type", "VARCHAR(20)", { src: ["bronze_ecom.web_session.device"] }, "Desktop, tablet or phone.", {}, P(0.3, 0.0001)),
      a("Landing Page", "VARCHAR(500)", { src: ["bronze_ecom.web_session.landing_url"] }, "First page viewed in the session.", {}, P(2.0, 0.8)),
    ],
    sql: { file: null, state: "none" }, checks: 0, feeds: ["fact_web_session"], context: [],
  },
  {
    id: 9, name: "Sales Order Line", type: "transaction", order: 3, areas: ["sales"], locked: false, updated: "Today, 8:29 AM",
    definition: "One product and quantity requested on a sales order.",
    grain: "One row per order line.",
    sources: [
      { object: "bronze_erp.sales_order_line", system: "ERP", rationale: "ERP order lines." },
      { object: "bronze_ecom.cart_item", system: "ECOM", rationale: "Cart items of placed web orders become order lines." },
    ],
    systems: ["ERP", "ECOM"],
    objectLogic: {
      ERP: { filter: "", sample: "SELECT order_id, line_no, product_id, qty,\n       unit_price, discount_amt\nFROM bronze_erp.sales_order_line" },
      ECOM: { filter: "Only items of placed orders (order_state <> 'ABANDONED').", sample: "SELECT ci.web_order_id, ci.position, p.product_id,\n       ci.quantity, ci.price\nFROM bronze_ecom.cart_item ci\nJOIN bronze_erp.product p ON p.sku = ci.sku\nWHERE ci.order_state <> 'ABANDONED'" },
    },
    attrs: [
      a("Order ID", "BIGINT", { nk: true, fk: "Sales Order" }, "Order the line belongs to.", {
        ERP: ["bronze_erp.sales_order_line.order_id", copy],
        ECOM: ["bronze_ecom.cart_item.web_order_id", "9000000000 + web_order_id"],
      }, P(0, 28.9)),
      a("Line Number", "INT", { nk: true }, "Position of the line on the order.", {
        ERP: ["bronze_erp.sales_order_line.line_no", copy],
        ECOM: ["bronze_ecom.cart_item.position", copy],
      }, P(0, 0.001)),
      a("Product ID", "BIGINT", { fk: "Product" }, "Product ordered.", {
        ERP: ["bronze_erp.sales_order_line.product_id", copy],
        ECOM: ["bronze_ecom.cart_item.sku", "Look up product_id by SKU."],
      }, P(0, 0.29)),
      a("Quantity", "INT", {}, "Units ordered.", {
        ERP: ["bronze_erp.sales_order_line.qty", copy],
        ECOM: ["bronze_ecom.cart_item.quantity", copy],
      }, P(0, 0.002)),
      a("Unit Price", "DECIMAL(18,2)", {}, "Price per unit in the order currency.", {
        ERP: ["bronze_erp.sales_order_line.unit_price", copy],
        ECOM: ["bronze_ecom.cart_item.price", copy],
      }, P(0, 0.8)),
      a("Discount Amount", "DECIMAL(18,2)", { nullable: true }, "Discount applied to the line.", {
        ERP: ["bronze_erp.sales_order_line.discount_amt", "COALESCE(discount_amt, 0)"],
      }, P(71.3, 0.4)),
      a("Line Amount", "DECIMAL(18,2)", {}, "Quantity × Unit Price − Discount Amount.", {
        ERP: ["(derived)", "qty * unit_price - COALESCE(discount_amt, 0)"],
        ECOM: ["(derived)", "quantity * price"],
      }, null),
    ],
    sql: { file: "silver_sales_order_line.sql", state: "placeholders", note: "Discount Amount is a typed-null placeholder for web store lines." },
    checks: 3, feeds: ["fact_order_line"], context: ["CR-01"],
  },
  {
    id: 10, name: "Invoice", type: "transaction", order: 3, areas: ["billing"], locked: false, updated: "Today, 8:29 AM",
    definition: "A bill raised for an order, stating the amount due and when.",
    grain: "One row per ERP invoice.",
    sources: [{ object: "bronze_erp.invoice", system: "ERP", rationale: "ERP invoices reference the order they bill." }],
    systems: ["ERP"],
    objectLogic: { ERP: { filter: "", sample: "SELECT invoice_id, order_id, invoice_date,\n       due_date, amount, status_cd\nFROM bronze_erp.invoice" } },
    attrs: [
      a("Invoice ID", "BIGINT", { nk: true }, "ERP invoice number.", { ERP: ["bronze_erp.invoice.invoice_id", copy] }, P(0, 100)),
      a("Order ID", "BIGINT", { fk: "Sales Order" }, "Order the invoice bills.", { ERP: ["bronze_erp.invoice.order_id", copy] }, P(0, 99.6)),
      a("Invoice Date", "DATE", {}, "Date the invoice was raised.", { ERP: ["bronze_erp.invoice.invoice_date", copy] }, P(0, 0.4)),
      a("Due Date", "DATE", {}, "Date payment is due.", { ERP: ["bronze_erp.invoice.due_date", copy] }, P(0, 0.4)),
      a("Invoice Amount", "DECIMAL(18,2)", {}, "Amount billed, in the order currency.", { ERP: ["bronze_erp.invoice.amount", copy] }, P(0, 30.2)),
      a("Invoice Status", "VARCHAR(20)", {}, "OPEN, PAID, PART_PAID or VOID.", { ERP: ["bronze_erp.invoice.status_cd", "Map ERP status codes to the shared status list."] }, P(0, 0.001)),
    ],
    sql: { file: "silver_invoice.sql", state: "stale", note: "Mapping changed after this file was generated." },
    checks: 3, feeds: ["fact_invoice"], context: ["CR-04"],
  },
  {
    id: 11, name: "Payment", type: "event", order: 4, areas: ["billing"], locked: false, updated: "Oct 23, 4:20 PM",
    definition: "Money received against an invoice. An invoice can be settled by several payments.",
    grain: "One row per payment received.",
    sources: [{ object: "bronze_erp.payment", system: "ERP", rationale: "ERP payment ledger, one row per receipt." }],
    systems: ["ERP"],
    objectLogic: {},
    attrs: [
      a("Payment ID", "BIGINT", { nk: true, src: ["bronze_erp.payment.payment_id"] }, "ERP payment reference.", {}, P(0, 100)),
      a("Invoice ID", "BIGINT", { fk: "Invoice", src: ["bronze_erp.payment.invoice_id"] }, "Invoice the payment settles.", {}, P(0, 92.4)),
      a("Paid At", "TIMESTAMP", { src: ["bronze_erp.payment.paid_at"] }, "When the payment was received.", {}, P(0, 98.7)),
      a("Payment Amount", "DECIMAL(18,2)", { src: ["bronze_erp.payment.amount"] }, "Amount received, in the invoice currency.", {}, P(0, 28.8)),
      a("Payment Method", "VARCHAR(20)", { src: ["bronze_erp.payment.method_cd"] }, "CARD, TRANSFER or CASH.", {}, P(0.1, 0.0004)),
    ],
    sql: { file: null, state: "none" }, checks: 0, feeds: ["fact_invoice"], context: ["CR-05"],
  },
];

// Child Attribute -> why the relationship exists.
export const relationshipBasis = {
  "Sales Order.Customer ID": "Analysis F-1 (Supported): every ERP order customer_id exists in the CRM customer list.",
  "Sales Order Line.Order ID": "Analysis F-2 (Supported): every order line belongs to an existing order.",
  "Sales Order Line.Product ID": "Analysis F-3 (Supported): 12 of 8,302 product values are missing; reviewed as acceptable.",
  "Invoice.Order ID": "Analysis F-4 (Inconclusive) and Context CR-04: an invoice belongs to exactly one order.",
  "Payment.Invoice ID": "Analysis F-5 (Supported) and Context CR-05: an invoice can have many payments.",
  "Product.Category ID": "Analysis F-6 (Supported): every product category exists.",
  "Web Session.Customer ID": "Analysis F-7 (Supported): signed-in sessions match CRM customers; 64% are anonymous.",
};

export const analysisFindings = [
  { id: "F-1", from: "bronze_erp.sales_order.customer_id", to: "bronze_crm.customer.customer_id", inferred: "Many to one",
    result: "supported", observed: "Many to one", aCount: 842310, bCount: 125000, aMissing: 0, aDistinct: 106796, bUnused: 18204, bDistinct: 125000,
    basis: "sales_order.customer_id values follow the CRM customer number format and every value appears in customer.customer_id.", locked: true },
  { id: "F-2", from: "bronze_erp.sales_order_line.order_id", to: "bronze_erp.sales_order.order_id", inferred: "Many to one",
    result: "supported", observed: "Many to one", aCount: 2915004, bCount: 842310, aMissing: 0, aDistinct: 841288, bUnused: 1022, bDistinct: 842310,
    basis: "Order lines carry the parent order number; the column name and values match sales_order.order_id.", locked: true },
  { id: "F-3", from: "bronze_erp.sales_order_line.product_id", to: "bronze_erp.product.product_id", inferred: "Many to one",
    result: "supported", observed: "Many to one", aCount: 2915004, bCount: 8412, aMissing: 12, aDistinct: 8302, bUnused: 122, bDistinct: 8412,
    basis: "Lines reference products by ERP product number.", locked: false },
  { id: "F-4", from: "bronze_erp.invoice.order_id", to: "bronze_erp.sales_order.order_id", inferred: "Many to one",
    result: "inconclusive", observed: "Many to one", aCount: 801977, bCount: 842310, aMissing: 10402, aDistinct: 798511, bUnused: 54201, bDistinct: 842310,
    basis: "Invoices name the order they bill. Orders created before the ERP migration are not in sales_order.", locked: false },
  { id: "F-5", from: "bronze_erp.payment.invoice_id", to: "bronze_erp.invoice.invoice_id", inferred: "Many to one",
    result: "supported", observed: "Many to one", aCount: 790105, bCount: 801977, aMissing: 0, aDistinct: 741020, bUnused: 60957, bDistinct: 801977,
    basis: "Payments are recorded against invoice numbers; several payments can settle one invoice.", locked: false },
  { id: "F-6", from: "bronze_erp.product.category_id", to: "bronze_erp.product_category.category_id", inferred: "Many to one",
    result: "supported", observed: "Many to one", aCount: 8412, bCount: 146, aMissing: 0, aDistinct: 139, bUnused: 7, bDistinct: 146,
    basis: "Products are assigned to their lowest-level category.", locked: false },
  { id: "F-7", from: "bronze_ecom.web_session.customer_id", to: "bronze_crm.customer.customer_id", inferred: "Many to one",
    result: "supported", observed: "Many to one", aCount: 4220918, bCount: 125000, aMissing: 0, aDistinct: 50644, bUnused: 74356, bDistinct: 125000,
    basis: "Signed-in sessions store the CRM customer number. Blank values are anonymous sessions and are not counted.", locked: false },
  { id: "F-8", from: "bronze_ecom.web_order.customer_ref", to: "bronze_crm.customer.customer_id", inferred: "One to one",
    result: "inconclusive", observed: "Many to one", aCount: 311560, bCount: 125000, aMissing: 3112, aDistinct: 47003, bUnused: 81109, bDistinct: 125000,
    basis: "customer_ref looks like the CRM customer number. The inference expected one web order per customer; measured counts show many.", locked: false },
  { id: "F-9", from: "bronze_ecom.cart_item.sku", to: "bronze_erp.product.sku", inferred: "Many to one",
    result: "unsupported", observed: null, aCount: 1048331, bCount: 8412, aMissing: 2241, aDistinct: 5896, bUnused: 4757, bDistinct: 8412,
    basis: "Cart items carry a SKU that could identify the product.", locked: false },
];

export const contextRecords = {
  "CR-01": { group: "Order handling requirements", kind: "Requirement", text: "Web store and ERP orders must be combined into one Sales Order record." },
  "CR-02": { group: "Order handling requirements", kind: "Requirement", text: "Cancelled orders stay in history with status CANCELLED." },
  "CR-03": { group: "Order handling requirements", kind: "Requirement", text: "Order totals are stored in the order currency; reporting converts later." },
  "CR-04": { group: "Billing conventions", kind: "Convention", text: "An invoice belongs to exactly one order." },
  "CR-05": { group: "Billing conventions", kind: "Convention", text: "Partial payments are allowed; an invoice can have many payments." },
  "CR-08": { group: "Customer data rules", kind: "Decision", text: "Email and street address are PII and must be masked outside Silver." },
};

export const dimensionalEntities = [
  { name: "dim_customer", kind: "Dimension", note: "SCD Type 2", attrs: 9, from: ["Customer", "Customer Address", "Country"] },
  { name: "dim_product", kind: "Dimension", note: "", attrs: 7, from: ["Product", "Product Category"] },
  { name: "dim_date", kind: "Dimension", note: "Calendar", attrs: 8, from: [] },
  { name: "dim_channel", kind: "Dimension", note: "", attrs: 3, from: ["Sales Order"] },
  { name: "dim_currency", kind: "Dimension", note: "", attrs: 3, from: ["Currency"] },
  { name: "fact_order_line", kind: "Fact", note: "Transaction", attrs: 10, from: ["Sales Order Line", "Sales Order"] },
  { name: "fact_invoice", kind: "Fact", note: "Accumulating snapshot", attrs: 9, from: ["Invoice", "Payment"] },
  { name: "fact_web_session", kind: "Fact", note: "Factless", attrs: 5, from: ["Web Session"] },
];

export const runs = [
  { id: 214, workflow: "Dimensional", operation: "Build", state: "running", when: "Today, 10:02 AM", detail: "Area 2 of 4 · Sales", actor: "Jordan Lee" },
  { id: 213, workflow: "Logical", operation: "Optimize", state: "completed", when: "Today, 8:15 AM", duration: "14m 02s", detail: "3 merges · 5 renames · 1.24M tokens", actor: "Jordan Lee" },
  { id: 212, workflow: "Mapping", operation: "Logical", state: "failed", when: "Yesterday, 5:40 PM", duration: "6m 11s", detail: "Repair attempts exhausted · stage 2, attempt 3", actor: "Sam Patel" },
  { id: 211, workflow: "Mapping", operation: "Logical", state: "completed", when: "Yesterday, 3:05 PM", duration: "22m 40s", detail: "9 entities · 59 attribute mappings", actor: "Sam Patel" },
  { id: 210, workflow: "Logical", operation: "Build", state: "completed", when: "Oct 23, 4:20 PM", duration: "41m 18s", detail: "4 areas · 11 entities", actor: "Jordan Lee" },
  { id: 209, workflow: "Analysis", operation: "Run", state: "completed", when: "Oct 22, 2:10 PM", duration: "9m 51s", detail: "9 findings", actor: "Jordan Lee" },
  { id: 208, workflow: "Profiling", operation: "Run", state: "completed", when: "Oct 22, 1:30 PM", duration: "3m 12s", detail: "14 Objects · 131 columns", actor: "Jordan Lee" },
];

// Stage summaries a backend overview endpoint would need to return. Counts are illustrative.
export const stages = [
  { id: "overview", label: "Overview", group: null },
  { id: "settings", label: "Settings", group: "Setup", state: "neutral" },
  { id: "scope", label: "Input scope", group: "Setup", state: "neutral", count: "14" },
  { id: "context", label: "Context", group: "Setup", state: "neutral", count: "11" },
  { id: "profiling", label: "Profiling", group: "Evidence", state: "complete", status: "Completed" },
  { id: "enrichment", label: "Enrichment", group: "Evidence", state: "complete", status: "Completed" },
  { id: "analysis", label: "Analysis", group: "Evidence", state: "attention", status: "3 to review", count: "3" },
  { id: "subject-areas", label: "Subject Areas", group: "Model", state: "complete", status: "Completed", count: "4" },
  { id: "logical", label: "Logical", group: "Model", state: "complete", status: "Results available", count: "11" },
  { id: "dimensional", label: "Dimensional", group: "Model", state: "running", status: "Running" },
  { id: "mapping", label: "Mapping", group: "Deliver", state: "attention", status: "Incomplete", count: "9/11" },
  { id: "code", label: "Code generation", short: "Code", group: "Deliver", state: "attention", status: "2 stale", count: "2" },
  { id: "validation", label: "Validation", group: "Deliver", state: "complete", status: "Results available", count: "14" },
];
