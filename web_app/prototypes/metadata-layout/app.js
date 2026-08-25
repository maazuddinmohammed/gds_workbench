// THROWAWAY PROTOTYPE: three Metadata Object/Attribute layouts, selected by ?variant=.
(function () {
  "use strict";

  const variants = [
    { key: "a", label: "A — Stacked grids" },
    { key: "b", label: "B — Object explorer" },
    { key: "c", label: "C — Inline hierarchy" },
  ];

  const catalog = {
    source: [
      object("salesforce", "public", "account", "Table", 5, [
        attribute("account_id", "string", false, true),
        attribute("account_name", "string", true, false),
        attribute("industry", "string", true, false),
        attribute("annual_revenue", "decimal(18,2)", true, false),
        attribute("modified_at", "timestamp", false, false),
      ]),
      object("salesforce", "public", "contact", "Table", 4, [
        attribute("contact_id", "string", false, true),
        attribute("account_id", "string", false, false),
        attribute("email", "string", true, false),
        attribute("modified_at", "timestamp", false, false),
      ]),
      object("netsuite", "finance", "invoice", "Table", 5, [
        attribute("invoice_id", "bigint", false, true),
        attribute("customer_id", "bigint", false, false),
        attribute("invoice_date", "date", false, false),
        attribute("currency_code", "string", false, false),
        attribute("total_amount", "decimal(18,2)", false, false),
      ]),
    ],
    bronze: [
      object("gds_lakehouse", "bronze_crm", "account_raw", "Delta table", 4, [
        attribute("account_id", "string", false, true),
        attribute("payload", "variant", true, false),
        attribute("ingested_at", "timestamp", false, false),
        attribute("batch_id", "bigint", false, false),
      ]),
      object("gds_lakehouse", "bronze_crm", "contact_raw", "Delta table", 4, [
        attribute("contact_id", "string", false, true),
        attribute("payload", "variant", true, false),
        attribute("ingested_at", "timestamp", false, false),
        attribute("batch_id", "bigint", false, false),
      ]),
    ],
    silver: [
      object("gds_lakehouse", "silver_customer", "customer", "Delta table", 5, [
        attribute("customer_key", "bigint", false, true),
        attribute("customer_name", "string", false, false),
        attribute("industry", "string", true, false),
        attribute("effective_from", "timestamp", false, false),
        attribute("effective_to", "timestamp", true, false),
      ]),
      object("gds_lakehouse", "silver_customer", "contact", "Delta table", 4, [
        attribute("contact_key", "bigint", false, true),
        attribute("customer_key", "bigint", false, false),
        attribute("email", "string", true, false),
        attribute("effective_from", "timestamp", false, false),
      ]),
    ],
    gold: [
      object("gds_lakehouse", "gold_finance", "fact_invoice", "Delta table", 5, [
        attribute("invoice_key", "bigint", false, true),
        attribute("customer_key", "bigint", false, false),
        attribute("invoice_date_key", "integer", false, false),
        attribute("currency_key", "integer", false, false),
        attribute("total_amount", "decimal(18,2)", false, false),
      ]),
      object("gds_lakehouse", "gold_finance", "dim_customer", "Delta table", 4, [
        attribute("customer_key", "bigint", false, true),
        attribute("customer_name", "string", false, false),
        attribute("industry", "string", true, false),
        attribute("is_current", "boolean", false, false),
      ]),
    ],
  };

  const state = {
    variant: currentVariant(),
    zone: "source",
    selected: { source: 0, bronze: 0, silver: 0, gold: 0 },
    lock: "unlocked",
  };

  function object(connection, schema, name, type, attributeCount, attributes) {
    return { connection, schema, name, type, attributeCount, attributes, status: "Active" };
  }

  function attribute(name, type, nullable, naturalKey) {
    return { name, type, nullable, naturalKey, status: "Active" };
  }

  function currentVariant() {
    const key = new URLSearchParams(window.location.search).get("variant") || "a";
    return variants.some((variant) => variant.key === key) ? key : "a";
  }

  function selectedObject() {
    return catalog[state.zone][state.selected[state.zone]];
  }

  function shell(content) {
    return `
      <div class="app-shell">
        <header class="topbar">
          <div class="brand"><span class="brand-mark">G</span><strong>GDS</strong><span class="brand-product">Workbench</span></div>
          <div class="tenant-context">
            <div><span class="eyebrow">Active Tenant</span><strong>Northwind Analytics</strong></div>
            <span class="context-divider"></span>
            <span class="gds-connection">GDS Connection · gds_lakehouse_prod</span>
          </div>
          <div class="lock-control">
            <span class="lock-status ${state.lock === "mine" ? "is-owned" : ""}">${state.lock === "mine" ? "Locked by you · 58m" : "Tenant unlocked"}</span>
            <button class="button ${state.lock === "mine" ? "button-quiet" : "button-primary"}" data-action="toggle-lock">${state.lock === "mine" ? "Release" : "Acquire lock"}</button>
          </div>
        </header>
        <aside class="sidebar">
          <span class="nav-label">Workspace</span>
          <nav class="main-nav">
            ${["Home", "Metadata", "Model", "Mapping", "Code generation"].map((item) => `<button class="nav-item ${item === "Metadata" ? "is-active" : ""}">${item}</button>`).join("")}
          </nav>
          <p class="sidebar-note">Prototype only. No database, MCP, uploads, or server mutations.</p>
        </aside>
        <main class="workspace">${content}</main>
      </div>`;
  }

  function heading(subtitle) {
    return `
      <div class="workspace-heading">
        <div>
          <span class="eyebrow">Metadata / Objects</span>
          <h1>Physical catalog</h1>
          <p>${subtitle}</p>
        </div>
        <div class="actions">
          <button class="button" data-action="download">Download Excel</button>
          <button class="button" data-action="import" ${state.lock === "mine" ? "" : "disabled"}>Import Excel</button>
          <button class="button button-primary" data-action="edit" ${state.lock === "mine" ? "" : "disabled"}>Edit dataset</button>
        </div>
      </div>`;
  }

  function zoneTabs(vertical) {
    return `<div class="${vertical ? "vertical-zones" : "zone-tabs"}">${Object.keys(catalog).map((zone) => `
      <button class="zone-tab ${zone === state.zone ? "is-active" : ""}" data-zone="${zone}">${title(zone)}</button>
    `).join("")}</div>`;
  }

  function objectTable() {
    return `
      <table class="data-table">
        <thead><tr><th>Object name</th><th>Schema</th><th>Connection</th><th>Object type</th><th>Attributes</th><th>Status</th></tr></thead>
        <tbody>${catalog[state.zone].map((item, index) => `
          <tr data-object="${index}" class="${index === state.selected[state.zone] ? "is-selected" : ""}">
            <td class="cell-primary">${item.name}</td><td>${item.schema}</td><td>${item.connection}</td><td>${item.type}</td><td>${item.attributeCount}</td><td><span class="status">${item.status}</span></td>
          </tr>`).join("")}</tbody>
      </table>`;
  }

  function attributeTable(attributes) {
    return `
      <table class="data-table">
        <thead><tr><th>Attribute name</th><th>Data type</th><th>Nullable</th><th>Natural key</th><th>Status</th></tr></thead>
        <tbody>${attributes.map((item) => `
          <tr><td class="cell-primary">${item.name}</td><td>${item.type}</td><td>${item.nullable ? "Yes" : "No"}</td><td>${item.naturalKey ? "Yes" : "—"}</td><td><span class="status">${item.status}</span></td></tr>
        `).join("")}</tbody>
      </table>`;
  }

  function variantA() {
    const selected = selectedObject();
    return shell(`
      ${heading("Choose a Zone, then select an Object to inspect its Attributes below.")}
      ${zoneTabs(false)}
      <div class="stacked-grid">
        <section class="grid-section">
          <div class="section-heading"><h2>${title(state.zone)} Objects</h2><span class="count">${catalog[state.zone].length} objects</span></div>
          ${objectTable()}
        </section>
        <section class="grid-section">
          <div class="section-heading"><h2>Attributes</h2><span class="attribute-context">${selected.schema}.${selected.name} · ${selected.attributes.length}</span></div>
          ${attributeTable(selected.attributes)}
        </section>
      </div>`);
  }

  function variantB() {
    const selected = selectedObject();
    return shell(`
      ${heading("Browse Objects on the left; the selected Object's Attributes fill the workspace.")}
      <div class="explorer-layout">
        <aside class="object-explorer">
          ${zoneTabs(true)}
          <input class="explorer-search" type="search" placeholder="Filter ${title(state.zone)} Objects" aria-label="Filter Objects">
          <div class="object-list">${catalog[state.zone].map((item, index) => `
            <button data-object="${index}" class="${index === state.selected[state.zone] ? "is-selected" : ""}"><strong>${item.name}</strong><span>${item.schema} · ${item.attributeCount} attributes</span></button>
          `).join("")}</div>
        </aside>
        <section class="attribute-workspace">
          <div class="object-summary">
            <div><span class="section-kicker">Selected ${title(state.zone)} Object</span><h2>${selected.name}</h2><p>${selected.connection} / ${selected.schema} · ${selected.type}</p></div>
            <span class="status">${selected.status}</span>
          </div>
          ${attributeTable(selected.attributes)}
        </section>
      </div>`);
  }

  function variantC() {
    const selectedIndex = state.selected[state.zone];
    return shell(`
      ${heading("Objects and their Attributes stay in one hierarchy; expand one Object at a time.")}
      ${zoneTabs(false)}
      <div class="section-heading"><h2>${title(state.zone)} Objects</h2><span class="count">Select a row to expand Attributes</span></div>
      <section class="hierarchy">
        <div class="hierarchy-header"><span>Object name</span><span>Schema</span><span>Connection</span><span>Attributes</span><span>Status</span></div>
        ${catalog[state.zone].map((item, index) => `
          <button class="object-row ${index === selectedIndex ? "is-expanded" : ""}" data-object="${index}">
            <span class="cell-primary"><span class="chevron">${index === selectedIndex ? "−" : "+"}</span>${item.name}</span><span>${item.schema}</span><span>${item.connection}</span><span>${item.attributeCount}</span><span class="status">${item.status}</span>
          </button>
          ${index === selectedIndex ? `<div class="inline-attributes">${attributeTable(item.attributes)}</div>` : ""}
        `).join("")}
      </section>`);
  }

  function render() {
    const renderVariant = state.variant === "a" ? variantA : state.variant === "b" ? variantB : variantC;
    document.getElementById("app").innerHTML = renderVariant();
    const variant = variants.find((item) => item.key === state.variant);
    document.getElementById("variant-label").textContent = variant.label;
    document.getElementById("state-readout").textContent = `Tenant: Northwind · Lock: ${state.lock} · Zone: ${state.zone} · Object: ${selectedObject().name}`;
    bindInteractions();
  }

  function bindInteractions() {
    document.querySelectorAll("[data-zone]").forEach((button) => button.addEventListener("click", () => {
      state.zone = button.dataset.zone;
      render();
    }));
    document.querySelectorAll("[data-object]").forEach((row) => row.addEventListener("click", () => {
      state.selected[state.zone] = Number(row.dataset.object);
      render();
    }));
    document.querySelectorAll("[data-action]").forEach((button) => button.addEventListener("click", () => handleAction(button.dataset.action)));
  }

  function handleAction(action) {
    if (action === "toggle-lock") {
      state.lock = state.lock === "mine" ? "unlocked" : "mine";
      showToast(state.lock === "mine" ? "Mock Tenant Lock acquired." : "Mock Tenant Lock released.");
      render();
      return;
    }
    const messages = {
      download: `Would download ${state.zone}_object and ${state.zone}_attribute sheets.`,
      import: "Would open the literal .xlsx import and difference review flow.",
      edit: `Would enter draft editing for ${state.zone} metadata.`,
    };
    showToast(messages[action] || "Prototype action only.");
  }

  function switchVariant(direction) {
    const index = variants.findIndex((variant) => variant.key === state.variant);
    state.variant = variants[(index + direction + variants.length) % variants.length].key;
    const url = new URL(window.location.href);
    url.searchParams.set("variant", state.variant);
    window.history.replaceState({}, "", url);
    render();
  }

  let toastTimer;
  function showToast(message) {
    const toast = document.getElementById("toast");
    toast.textContent = message;
    toast.classList.add("is-visible");
    window.clearTimeout(toastTimer);
    toastTimer = window.setTimeout(() => toast.classList.remove("is-visible"), 2200);
  }

  function title(value) {
    return value.charAt(0).toUpperCase() + value.slice(1);
  }

  document.getElementById("previous-variant").addEventListener("click", () => switchVariant(-1));
  document.getElementById("next-variant").addEventListener("click", () => switchVariant(1));
  window.addEventListener("keydown", (event) => {
    const target = event.target;
    if (target instanceof HTMLElement && (target.matches("input, textarea") || target.isContentEditable)) return;
    if (event.key === "ArrowLeft") switchVariant(-1);
    if (event.key === "ArrowRight") switchVariant(1);
  });

  render();
})();
