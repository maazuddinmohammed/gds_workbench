import assert from "node:assert/strict";
import { readFile } from "node:fs/promises";
import { createRequire } from "node:module";
import test from "node:test";

const require = createRequire(import.meta.url);
const { JSDOM } = require("jsdom");

const workbenchRoot = new URL(
  "../../plugins/v2/gds/skills/gds/workbench/",
  import.meta.url,
);

test("connect and refresh render effective dataset counts", async () => {
  const html = await readFile(new URL("index.html", workbenchRoot), "utf8");
  const app = await readFile(new URL("app.js", workbenchRoot), "utf8");
  const dom = new JSDOM(html, { runScripts: "outside-only", url: "file:///workbench/index.html" });
  const { window } = dom;
  const definition = {
    name: "source_object",
    section: "operational",
    row_count: 1,
    canonical_key: ["object_name"],
  };
  const loaded = {
    definition,
    schema: {
      type: "object",
      additionalProperties: false,
      "x-gds-change-set-eligible": true,
      properties: {
        object_name: { type: "string" },
        description: { type: "string" },
      },
      required: ["object_name", "description"],
    },
    baseline: [{ object_name: "Customer", description: "Customer master" }],
    pending: [
      { object_name: "Order", description: "Orders" },
      { object_name: "Product", description: "Products" },
    ],
    effective: [
      { object_name: "Customer", description: "Customer master" },
      { object_name: "Order", description: "Orders" },
      { object_name: "Product", description: "Products" },
    ],
    pendingDigest: "a".repeat(64),
  };
  const emptyArea = { manifest: null, datasets: [], byName: new Map() };
  let savedDraft = null;
  const workspace = {
    handle: { name: "session-01" },
    state: {
      current: "01",
      stale: [],
      tasks: [["01", "metadata", "Edit metadata", "doing"]],
    },
    area: (area) => area === "metadata"
      ? {
          manifest: { snapshot_id: "snapshot-01" },
          datasets: [definition],
          byName: new Map([[definition.name, definition]]),
        }
      : emptyArea,
    loadArea: async () => new Map([[definition.name, loaded]]),
    loadDataset: async () => loaded,
    saveDataset: async (_area, _dataset, text) => {
      savedDraft = JSON.parse(text);
      loaded.pending = savedDraft;
      loaded.pendingDigest = "b".repeat(64);
      return { records: savedDraft, pendingDigest: loaded.pendingDigest };
    },
    changeSetDigest: async () => "c".repeat(64),
    loadValidationReport: async () => null,
    refresh: async () => {
      loaded.pending.push({ object_name: "Invoice", description: "Invoices" });
      loaded.effective.push({ object_name: "Invoice", description: "Invoices" });
      return workspace;
    },
  };
  window.GDSMetadata = { label: "Metadata", reviewGroups: () => [] };
  window.GDSModel = { label: "Model", reviewGroups: () => [] };
  window.GDSCore = {
    stableStringify: JSON.stringify,
    key: (_area, dataset, record) => dataset.canonical_key.map((field) => record[field]),
    overlay: (_area, dataset, baseline, pending) => {
      const records = new Map(
        baseline.map((record) => [JSON.stringify(dataset.canonical_key.map((field) => record[field])), record]),
      );
      for (const record of pending) {
        records.set(JSON.stringify(dataset.canonical_key.map((field) => record[field])), record);
      }
      return [...records.values()];
    },
  };
  window.GDSCommonValidation = { validateSchema: () => [] };
  window.GDSUIState = {
    canEdit: () => true,
    canValidate: () => false,
    requireClean: () => {},
  };
  window.GDSWorkspace = { connect: async () => workspace };
  window.CSS = { escape: (value) => value };
  window.HTMLDialogElement.prototype.showModal = function showModal() {
    this.open = true;
  };
  window.HTMLDialogElement.prototype.close = function close() {
    this.open = false;
    this.dispatchEvent(new window.Event("close"));
  };
  window.eval(app);

  await window.GDSWorkbenchApp.connectDirectoryHandle({ kind: "directory", name: "session-01" });
  assert.equal(
    window.document.querySelector(".dataset-button span:last-child")?.textContent,
    "2 / 1",
  );

  await window.GDSWorkbenchApp.refresh();
  assert.equal(
    window.document.querySelector(".dataset-button span:last-child")?.textContent,
    "3 / 1",
  );

  assert.equal(window.document.querySelectorAll(".data-table tbody tr").length, 1);
  assert.equal(window.document.querySelector(".data-table .text-action")?.textContent, "Add to Change Set");
  window.document.querySelector(".data-table .text-action")?.click();
  await new Promise((resolve) => window.setTimeout(resolve, 0));
  assert.equal(window.GDSWorkbenchApp.state.source, "changeset");
  assert.equal(savedDraft.some((record) => record.object_name === "Customer"), true);

  const customerRow = [...window.document.querySelectorAll(".data-table tbody tr")]
    .find((row) => row.textContent.includes("Customer"));
  customerRow?.querySelector(".text-action")?.click();
  const description = window.document.querySelector("[data-row-field='description']");
  assert.equal(window.document.getElementById("row-editor-dialog")?.open, true);
  description.value = "Customer golden record";
  window.document.getElementById("row-editor-form")?.dispatchEvent(
    new window.Event("submit", { bubbles: true, cancelable: true }),
  );
  await new Promise((resolve) => window.setTimeout(resolve, 0));
  assert.equal(
    savedDraft.find((record) => record.object_name === "Customer")?.description,
    "Customer golden record",
  );
  assert.equal(window.document.getElementById("row-editor-dialog")?.open, false);

  window.document.getElementById("add-row-button")?.click();
  assert.equal(window.document.getElementById("row-editor-dialog")?.open, true);
  assert.equal(window.document.getElementById("row-editor-title")?.textContent, "Add Source Object row");
  window.document.querySelector("[data-row-field='object_name']").value = "Payment";
  window.document.querySelector("[data-row-field='description']").value = "Customer payments";
  window.document.getElementById("row-editor-form")?.dispatchEvent(
    new window.Event("submit", { bubbles: true, cancelable: true }),
  );
  await new Promise((resolve) => window.setTimeout(resolve, 0));
  assert.equal(
    savedDraft.find((record) => record.object_name === "Payment")?.description,
    "Customer payments",
  );
  assert.equal(window.document.getElementById("row-editor-dialog")?.open, false);
});

test("mapping documents stay out of the ledger and open on a dedicated detail page", async () => {
  const html = await readFile(new URL("index.html", workbenchRoot), "utf8");
  const app = await readFile(new URL("app.js", workbenchRoot), "utf8");
  const dom = new JSDOM(html, { runScripts: "outside-only", url: "file:///workbench/index.html" });
  const { window } = dom;
  const definition = {
    name: "mapping_object",
    section: "mapping",
    row_count: 1,
    canonical_key: ["modeled_entity_name", "source_system_code"],
  };
  const mappingDocument = { steps: [{ sql: "select * from bronze.Customer" }] };
  const loaded = {
    definition,
    schema: {
      type: "object",
      additionalProperties: false,
      "x-gds-change-set-eligible": true,
      properties: {
        modeled_entity_name: { type: "string" },
        source_system_code: { type: "string" },
        mapping_transformation_document: { type: "object" },
      },
      required: ["modeled_entity_name", "source_system_code", "mapping_transformation_document"],
    },
    baseline: [{
      modeled_entity_name: "Customer",
      source_system_code: "CRM",
      mapping_transformation_document: mappingDocument,
    }],
    pending: [],
    effective: [],
    pendingDigest: null,
  };
  const modelArea = {
    manifest: { snapshot_id: "model-01", model_revision: 3 },
    catalog: { model: { model_id: 41, model_name: "Customer", model_revision: 3 } },
    datasets: [definition],
    byName: new Map([[definition.name, definition]]),
  };
  let savedReport = null;
  const workspace = {
    handle: { name: "session-01" },
    state: { current: "01", stale: [], tasks: [["01", "model", "Map logical", "doing"]] },
    area: (area) => area === "model" ? modelArea : { manifest: null, datasets: [], byName: new Map() },
    loadArea: async () => new Map([[definition.name, loaded]]),
    loadDataset: async () => loaded,
    loadValidationReport: async () => null,
    changeSetDigest: async () => "c".repeat(64),
    saveValidationReport: async (_area, report) => {
      savedReport = report;
      return {
        schema_version: "1.0",
        area: "model",
        run_by: "workbench",
        generated_at: "2026-09-02T12:00:00.000Z",
        digest: report.digest,
        snapshot: { id: "model-01", revision: 3, manifest_digest: "e".repeat(64) },
        valid: report.valid,
        issue_count: report.issueCount,
        truncated: report.truncated,
        issues: report.issues,
        stale: false,
      };
    },
    saveDataset: async (_area, _dataset, text) => {
      loaded.pending = JSON.parse(text);
      loaded.effective = [...loaded.pending];
      loaded.pendingDigest = "d".repeat(64);
      return { records: loaded.pending, pendingDigest: loaded.pendingDigest };
    },
  };
  window.GDSMetadata = { label: "Metadata", validate: () => [] };
  window.GDSModel = { label: "Model", validate: () => [{ code: "mapping_check", dataset: "mapping_object", record: 1, message: "Review mapping." }] };
  window.GDSCore = {
    stableStringify: JSON.stringify,
    key: (_area, dataset, record) => dataset.canonical_key.map((field) => record[field]),
  };
  window.GDSCommonValidation = { validateSchema: () => [] };
  window.GDSUIState = { canEdit: () => true, canValidate: () => true };
  window.GDSWorkspace = { connect: async () => workspace };
  window.GDSDbml = { render: () => [] };
  window.HTMLDialogElement.prototype.showModal = function showModal() { this.open = true; };
  window.HTMLDialogElement.prototype.close = function close() {
    this.open = false;
    this.dispatchEvent(new window.Event("close"));
  };
  window.eval(app);

  await window.GDSWorkbenchApp.connectDirectoryHandle({ kind: "directory", name: "session-01" });
  assert.equal(window.document.querySelector(".data-table")?.textContent.includes("bronze.Customer"), false);
  assert.equal(window.document.querySelector(".data-table .text-action")?.textContent, "Show details");

  window.document.querySelector(".data-table .text-action")?.click();
  assert.match(window.document.querySelector(".detail-document pre")?.textContent || "", /bronze\.Customer/);
  window.document.querySelector('[data-action="stage-detail"]')?.click();
  await new Promise((resolve) => window.setTimeout(resolve, 0));
  assert.equal(loaded.pending.length, 1);
  assert.equal(window.document.querySelector('[data-action="open-detail-draft"]')?.textContent, "Open Change Set draft");
  window.document.querySelector('[data-action="open-detail-draft"]')?.click();
  assert.equal(window.document.querySelector('[data-action="edit-detail-draft"]')?.textContent, "Edit draft");

  window.document.getElementById("validate-button")?.click();
  await new Promise((resolve) => window.setTimeout(resolve, 0));
  assert.equal(savedReport.issueCount, 1);
  assert.equal(window.GDSWorkbenchApp.state.screen, "validation");
  assert.equal(window.document.querySelector(".issue-table")?.textContent.includes("Review mapping."), true);
  assert.equal(window.document.querySelector("[data-open-issue]")?.textContent, "Open record");
});
