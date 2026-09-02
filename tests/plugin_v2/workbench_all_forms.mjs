import assert from "node:assert/strict";
import { readFile } from "node:fs/promises";
import { createRequire } from "node:module";

const require = createRequire(import.meta.url);
const { JSDOM } = require("jsdom");
const repositoryRoot = new URL("../../", import.meta.url);
const workbenchRoot = new URL("plugins/v2/gds/skills/gds/workbench/", repositoryRoot);
const html = await readFile(new URL("index.html", workbenchRoot), "utf8");
const app = await readFile(new URL("app.js", workbenchRoot), "utf8");
const datasets = JSON.parse(await readFile(process.argv[2], "utf8"));

for (const fixture of datasets) {
  const dom = new JSDOM(html, {
    runScripts: "outside-only",
    url: "file:///workbench/index.html",
  });
  const { window } = dom;
  const definition = {
    name: fixture.name,
    section: fixture.section,
    row_count: 0,
    canonical_key: fixture.canonical_key,
  };
  const loaded = {
    definition,
    schema: fixture.schema,
    baseline: [],
    pending: [],
    effective: [],
    pendingDigest: null,
  };
  const area = {
    manifest: { snapshot_id: `${fixture.area}-snapshot` },
    datasets: [definition],
    byName: new Map([[fixture.name, definition]]),
  };
  const emptyArea = { manifest: null, datasets: [], byName: new Map() };
  const workspace = {
    handle: { name: `${fixture.area}-session` },
    state: {
      current: "01",
      stale: [],
      tasks: [["01", fixture.area, `Edit ${fixture.area}`, "doing"]],
    },
    area: (name) => name === fixture.area ? area : emptyArea,
    loadArea: async () => new Map([[fixture.name, loaded]]),
    loadDataset: async () => loaded,
    loadValidationReport: async () => null,
    saveDataset: async (_area, _dataset, text) => {
      loaded.pending = JSON.parse(text);
      loaded.effective = [...loaded.pending];
      loaded.pendingDigest = "a".repeat(64);
      return { records: loaded.pending, pendingDigest: loaded.pendingDigest };
    },
  };
  window.GDSMetadata = { label: "Metadata", reviewGroups: () => [] };
  window.GDSModel = { label: "Model", reviewGroups: () => [] };
  window.GDSCore = {
    stableStringify: JSON.stringify,
    key: (_area, dataset, record) => dataset.canonical_key.map((field) => record[field]),
    overlay: (_area, _dataset, baseline, pending) => [...baseline, ...pending],
  };
  window.GDSCommonValidation = { validateSchema: () => [] };
  window.GDSUIState = {
    canEdit: () => fixture.change_set_eligible,
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

  await window.GDSWorkbenchApp.connectDirectoryHandle({ name: workspace.handle.name });
  window.document.querySelector(".dataset-button")?.click();
  await new Promise((resolve) => window.setTimeout(resolve, 0));
  const changeSetButton = window.document.querySelector('[data-source="changeset"]');
  assert.ok(
    changeSetButton,
    `${fixture.area}/${fixture.name}: Change Set source exists; ${window.GDSWorkbenchApp.state.message}`,
  );
  assert.equal(
    changeSetButton.disabled,
    !fixture.change_set_eligible,
    `${fixture.area}/${fixture.name}: Change Set eligibility`,
  );
  if (!fixture.change_set_eligible) {
    assert.equal(window.document.getElementById("add-row-button"), null);
    continue;
  }
  changeSetButton.click();
  const addButton = window.document.getElementById("add-row-button");
  assert.equal(addButton.disabled, false, `${fixture.area}/${fixture.name}: Add row eligibility`);

  addButton.click();
  assert.equal(
    window.document.getElementById("row-editor-dialog")?.open,
    true,
    `${fixture.area}/${fixture.name}: dialog opens`,
  );
  const controls = [...window.document.querySelectorAll("[data-row-field]")];
  const propertyNames = Object.keys(fixture.schema.properties || {});
  assert.deepEqual(
    controls.map((control) => control.dataset.rowField).sort(),
    propertyNames.sort(),
    `${fixture.area}/${fixture.name}: every schema field has a form control`,
  );
  for (const field of fixture.schema.required || []) {
    assert.ok(
      controls.some((control) => control.dataset.rowField === field),
      `${fixture.area}/${fixture.name}.${field}: required field is present`,
    );
  }
  for (const [field, property] of Object.entries(fixture.schema.properties || {})) {
    if (!Object.hasOwn(property, "const")) continue;
    const control = controls.find((item) => item.dataset.rowField === field);
    const controlValue = control.dataset.valueKind === "json"
      ? JSON.parse(control.value)
      : control.value;
    assert.deepEqual(
      controlValue,
      property.const,
      `${fixture.area}/${fixture.name}.${field}: fixed value is prefilled`,
    );
    assert.equal(
      control.disabled,
      true,
      `${fixture.area}/${fixture.name}.${field}: fixed value is locked`,
    );
  }

  for (const control of controls) {
    if (control.disabled) continue;
    if (control.tagName === "SELECT") {
      if (control.value === "__null__" && control.options.length > 1) {
        control.selectedIndex = 1;
      }
    } else if (control.dataset.valueKind === "integer") {
      control.value = "1";
    } else if (control.dataset.valueKind === "number") {
      control.value = "1.5";
    } else if (control.dataset.valueKind === "array") {
      control.value = "[]";
    } else if (control.dataset.valueKind === "object") {
      control.value = "{}";
    } else if (control.type === "date") {
      control.value = "2026-01-01";
    } else {
      control.value = "sample";
    }
  }
  window.document.getElementById("row-editor-form")?.dispatchEvent(
    new window.Event("submit", { bubbles: true, cancelable: true }),
  );
  await new Promise((resolve) => window.setTimeout(resolve, 0));
  assert.equal(
    window.document.getElementById("row-editor-dialog")?.open,
    false,
    `${fixture.area}/${fixture.name}: completed form stages a row`,
  );
  const staged = loaded.pending;
  assert.equal(staged.length, 1, `${fixture.area}/${fixture.name}: one row is staged`);
  for (const field of propertyNames) {
    assert.ok(
      Object.hasOwn(staged[0], field),
      `${fixture.area}/${fixture.name}.${field}: staged row retains every field`,
    );
  }
}

process.stdout.write(`Checked Add row forms for ${datasets.length} dataset schemas.\n`);
