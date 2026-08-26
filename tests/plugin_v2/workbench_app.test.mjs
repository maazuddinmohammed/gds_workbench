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
    "3",
  );

  await window.GDSWorkbenchApp.refresh();
  assert.equal(
    window.document.querySelector(".dataset-button span:last-child")?.textContent,
    "4",
  );

  window.document.querySelector(".dataset-button")?.click();
  await new Promise((resolve) => window.setTimeout(resolve, 0));
  assert.equal(window.document.querySelectorAll("#results-body tr").length, 4);
  assert.equal(window.document.querySelector("[data-view='results']")?.className, "is-active");

  window.document.querySelector("#results-body .text-action")?.click();
  const description = window.document.querySelector("[data-row-field='description']");
  assert.equal(window.document.getElementById("row-editor-dialog")?.open, true);
  description.value = "Customer golden record";
  window.document.getElementById("row-editor-form")?.dispatchEvent(
    new window.Event("submit", { bubbles: true, cancelable: true }),
  );
  assert.equal(window.GDSWorkbenchApp.state.dirty, true);
  assert.match(window.document.getElementById("pending-editor")?.value, /Customer golden record/);

  window.document.getElementById("save-button")?.click();
  await new Promise((resolve) => window.setTimeout(resolve, 0));
  assert.equal(
    savedDraft.find((record) => record.object_name === "Customer")?.description,
    "Customer golden record",
  );
  assert.equal(window.GDSWorkbenchApp.state.dirty, false);

  window.document.getElementById("add-row-button")?.click();
  assert.equal(window.document.getElementById("row-editor-dialog")?.open, true);
  assert.equal(window.document.getElementById("row-editor-title")?.textContent, "Add Source Object row");
  window.document.querySelector("[data-row-field='object_name']").value = "Payment";
  window.document.querySelector("[data-row-field='description']").value = "Customer payments";
  window.document.getElementById("row-editor-form")?.dispatchEvent(
    new window.Event("submit", { bubbles: true, cancelable: true }),
  );
  assert.equal(window.GDSWorkbenchApp.state.dirty, true);
  assert.match(window.document.getElementById("pending-editor")?.value, /Customer payments/);

  window.document.getElementById("save-button")?.click();
  await new Promise((resolve) => window.setTimeout(resolve, 0));
  assert.equal(
    savedDraft.find((record) => record.object_name === "Payment")?.description,
    "Customer payments",
  );
  assert.equal(window.GDSWorkbenchApp.state.dirty, false);
});
