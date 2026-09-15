(function (root) {
  "use strict";

  const PAGE_SIZE = 100;
  const { escapeHtml, label, valueText } = root.AtlasText;
  const app = document.getElementById("workbench-root");
  const dialog = document.getElementById("row-editor-dialog");
  const editorForm = document.getElementById("row-editor-form");
  const editorFields = document.getElementById("row-editor-fields");
  const editorMessage = document.getElementById("row-editor-message");
  const state = {
    workspace: null,
    area: "metadata",
    screen: "records",
    dataset: null,
    loaded: null,
    source: "snapshot",
    page: 0,
    selected: new Set(),
    filters: {},
    counts: new Map(),
    reports: { metadata: null, model: null },
    operations: { metadata: null, model: null },
    validationArea: "metadata",
    validationFilters: { severity: [], dataset: [] },
    detail: null,
    columns: {},
    parentBaseline: null,
    dbml: null,
    editing: null,
    busy: false,
    message: "Workbench is local-only. Open an initialized Atlas working directory.",
    messageError: false,
  };




  function setMessage(message, isError = false) {
    state.message = message;
    state.messageError = isError;
  }

  function showError(error) {
    setMessage(error?.message || String(error), true);
    render();
  }

  function areaModule(area = state.area) {
    return area === "metadata" ? root.GDSMetadata : root.GDSModel;
  }

  function currentTask() {
    return state.workspace?.task || null;
  }

  function areaSnapshot(area = state.area) {
    return state.workspace?.area(area);
  }

  function currentDefinition() {
    return state.loaded?.definition || null;
  }

  function eligible() {
    return Boolean(
      state.loaded?.schema?.["x-gds-change-set-eligible"] === true &&
      root.GDSUIState.canEdit(
        currentTask(),
        state.area,
        state.loaded,
        state.workspace?.isStale(state.area),
        state.dataset,
      ),
    );
  }

  function canValidate(area = state.area) {
    return root.GDSUIState.canValidate(
      currentTask(area),
      area,
      Boolean(areaSnapshot(area)?.manifest),
      false,
      state.workspace?.isStale(area),
    );
  }

  function recordKey(record) {
    return root.GDSCore.stableStringify(
      root.GDSCore.key(state.area, currentDefinition(), record),
    );
  }

  function recordReadOnlyReason(record) {
    const key = recordKey(record);
    const original = state.loaded?.baseline.find(item => recordKey(item) === key);
    if (Object.entries(original || {}).some(([field, value]) => value === true && (field === "is_locked" || field.endsWith("_is_locked")))) return "Locked record · changes prohibited";
    if (state.area === "metadata" && state.parentBaseline) {
      const { definition, baseline } = state.parentBaseline;
      const parentKey = root.GDSCore.stableStringify(root.GDSCore.key("metadata", definition, record));
      if (baseline.some(parent => parent.is_locked && root.GDSCore.stableStringify(root.GDSCore.key("metadata", definition, parent)) === parentKey)) return "Parent Object is locked · Attribute changes prohibited";
    }
    return null;
  }

  function pendingByKey() {
    return new Map((state.loaded?.pending || []).map((record) => [recordKey(record), record]));
  }






  function topBar() {
    const connected = Boolean(state.workspace), context = state.workspace?.state, task = currentTask();
    const owners = context ? Object.values(context.metadata_owners || { [context.tenant.id]: { ...context.tenant, root: "." } }) : [];
    return `<header class="topbar"><div class="brand" aria-label="atlas Workbench"><span class="brand-mark">a</span><span class="brand-name">atlas <small>Workbench</small></span></div><div class="session-line"><span class="eyebrow">Working directory</span><strong>${escapeHtml(state.workspace?.handle?.name || "Not connected")}</strong>${context ? `<span>${escapeHtml(context.tenant.code)}${context.model ? ` · ${escapeHtml(context.model.name)}` : ""}</span><span class="context-detail">${escapeHtml(context.sql?.policy || "SQL policy unset")}${context.sql?.environment ? ` · ${escapeHtml(context.sql.environment)}` : ""}</span>` : ""}</div><div class="top-actions"><button id="connect-button" type="button" class="button" ${state.busy ? "disabled" : ""}>Open working directory</button><button id="refresh-button" type="button" class="button" ${!connected || state.busy ? "disabled" : ""}>Reload local files</button><button id="validate-button" type="button" class="button button-primary" ${!connected || !canValidate(state.screen === "validation" ? state.validationArea : state.area) || state.busy ? "disabled" : ""}>Validate locally</button><button id="dbml-button" type="button" class="button" ${!connected || !areaSnapshot("model")?.manifest || state.workspace?.isStale("model") || state.busy ? "disabled" : ""}>Generate DBML</button></div></header>${context ? `<div class="workspace-context"><span>${task ? escapeHtml(task.outcome) : "No active task · initialize work through Atlas"}</span>${owners.length > 1 ? `<label>Metadata owner <select id="metadata-owner">${owners.map(owner => `<option value="${owner.id}" ${String(owner.id) === state.workspace.ownerId ? "selected" : ""}>${escapeHtml(owner.code)}</option>`).join("")}</select></label>` : ""}<span>Remote freshness unknown</span></div>` : ""}`;
  }

  function areaTabs() {
    const active = state.screen === "validation" ? "validation" : state.area;
    const report = state.reports[state.validationArea];
    const snapshot = active === "validation" ? null : areaSnapshot(active);
    const operation = state.operations[active === "validation" ? state.validationArea : active];
    const status = active === "validation"
      ? report ? `${label(state.validationArea)} report · ${report.stale ? "stale" : report.valid ? "passed" : `${report.issue_count} issues`}` : "No local validation report yet"
      : snapshot?.manifest
        ? `${label(active)} Snapshot${snapshot.manifest.model_revision == null ? "" : ` · revision ${snapshot.manifest.model_revision}`} · ${[...state.counts.values()].reduce((sum, item) => sum + item.pending, 0)} Change Set records`
        : "Snapshot unavailable";
    return `<nav class="area-tabs" aria-label="Workbench area" role="tablist">${[["metadata", "Metadata"], ["model", "Model"], ["validation", "Validation results"]].map(([value, text]) => `<button type="button" class="area-tab ${active === value ? "is-active" : ""}" data-area="${value}" role="tab" aria-selected="${active === value}" ${!state.workspace || (value !== "validation" && !areaSnapshot(value)?.manifest) ? "disabled" : ""}>${text}${value === "validation" && report?.issue_count ? `<span class="tab-count">${report.issue_count}</span>` : ""}</button>`).join("")}<span class="snapshot-state">${escapeHtml(status)}</span></nav>${operation ? `<div class="operation-state ${operation.uncertain ? "is-error" : ""}" role="status">${escapeHtml(operation.status)}${operation.revision == null ? "" : ` · revision ${operation.revision}`}${operation.historical ? " · historical batch; current saved inputs differ" : ""}</div>` : ""}`;
  }











  function render() {
    app.innerHTML = `${topBar()}${areaTabs()}${state.screen === "validation" ? validationWorkspace() : state.screen === "dbml" ? dbmlWorkspace() : recordsWorkspace()}<footer class="statusbar"><span id="status-message" role="status" aria-live="polite" class="${state.messageError ? "is-error" : ""}">${escapeHtml(state.message)}</span><span>${state.workspace ? "Local directory connected" : "Chrome or Edge directory access required"}</span></footer>`;
    bindInteractions();
  }

  async function loadReports() {
    if (!state.workspace?.loadValidationReport) return;
    for (const area of ["metadata", "model"]) {
      state.reports[area] = areaSnapshot(area)?.manifest ? await state.workspace.loadValidationReport(area) : null;
      state.operations[area] = await state.workspace.loadOperation(area);
    }
  }

  async function refreshCounts(area = state.area) {
    if (!areaSnapshot(area)?.manifest) { state.counts = new Map(); return; }
    const loaded = await state.workspace.loadArea(area);
    state.counts = new Map([...loaded].map(([name, item]) => [name, {
      baseline: item.baseline.length,
      pending: item.pending.length,
      effective: item.effective.length,
    }]));
  }

  async function selectDataset(name) {
    state.dataset = name;
    state.loaded = await state.workspace.loadDataset(state.area, name);
    state.parentBaseline = null;
    const parent = state.area === "metadata" && name.endsWith("_attribute") ? name.replace(/_attribute$/, "_object") : null;
    if (parent && areaSnapshot().byName.has(parent)) state.parentBaseline = await state.workspace.loadDataset("metadata", parent);
    state.source = "snapshot";
    state.page = 0;
    state.selected.clear();
    state.detail = null;
    state.screen = "records";
    setMessage(`Loaded ${label(name)}. Snapshot remains read-only.`);
    render();
  }

  async function switchArea(area, preferredDataset = null) {
    if (!areaSnapshot(area)?.manifest) return;
    state.area = area;
    state.validationArea = area;
    state.screen = "records";
    state.loaded = null;
    state.dataset = null;
    state.source = "snapshot";
    state.selected.clear();
    await refreshCounts(area);
    const definitions = areaSnapshot(area).datasets;
    const next = definitions.some((item) => item.name === preferredDataset) ? preferredDataset : definitions[0]?.name;
    if (next) await selectDataset(next);
    else render();
  }

  async function connectDirectoryHandle(handle) {
    try {
      state.busy = true;
      render();
      if (handle.queryPermission && await handle.queryPermission({ mode: "readwrite" }) !== "granted") {
        if (await handle.requestPermission({ mode: "readwrite" }) !== "granted") throw new Error("Read/write permission to the working directory was not granted.");
      }
      state.workspace = await root.GDSWorkspace.connect(handle);
      await loadReports();
      const area = areaSnapshot("metadata")?.manifest ? "metadata" : "model";
      await switchArea(area);
      setMessage(state.workspace.areaErrors.size ? [...state.workspace.areaErrors.values()].join(" ") : `Opened ${state.workspace.handle.name}. All changes remain local.`, state.workspace.areaErrors.size > 0);
    } catch (error) {
      state.workspace = null;
      showError(error);
    } finally {
      state.busy = false;
      render();
    }
  }

  async function connectFromPicker() {
    if (!root.showDirectoryPicker) return showError(new Error("This browser cannot open local directories. Use current Chrome or Edge."));
    try { await connectDirectoryHandle(await root.showDirectoryPicker({ mode: "readwrite" })); }
    catch (error) { if (error?.name !== "AbortError") showError(error); }
  }

  async function refresh() {
    if (!state.workspace) return;
    const area = state.area;
    const dataset = state.dataset;
    try {
      state.busy = true;
      render();
      await state.workspace.refresh();
      await loadReports();
      await switchArea(areaSnapshot(area)?.manifest ? area : areaSnapshot("metadata")?.manifest ? "metadata" : "model", dataset);
      setMessage("Refreshed Snapshot, Change Set, and shared local validation reports from disk.");
    } catch (error) { showError(error); }
    finally { state.busy = false; render(); }
  }

  async function persistPending(records, message) {
    const expectedDigest = state.loaded.pendingDigest;
    await state.workspace.saveDataset(state.area, state.dataset, JSON.stringify(records, null, 2), expectedDigest);
    state.loaded = await state.workspace.loadDataset(state.area, state.dataset);
    state.counts.set(state.dataset, {
      baseline: state.loaded.baseline.length,
      pending: state.loaded.pending.length,
      effective: state.loaded.effective.length,
    });
    if (state.reports[state.area]) state.reports[state.area] = { ...state.reports[state.area], stale: true };
    if (state.operations[state.area]) state.operations[state.area].historical = true;
    setMessage(message);
  }

  async function stageRecords(records) {
    if (!eligible() || !records.length) return;
    const merged = pendingByKey();
    let added = 0;
    for (const record of records) {
      if (recordReadOnlyReason(record)) continue;
      const key = recordKey(record);
      if (!merged.has(key)) { merged.set(key, JSON.parse(JSON.stringify(record))); added++; }
    }
    if (!added) { setMessage("Every selected row is already in the Change Set."); return render(); }
    await persistPending([...merged.values()], `Added ${added} complete record${added === 1 ? "" : "s"} to the local Change Set.`);
    state.source = "changeset";
    state.selected.clear();
    state.page = 0;
    render();
  }

  async function removeDrafts(records) {
    if (!eligible() || !records.length) return;
    const removed = new Set(records.map((record) => recordKey(record)));
    await persistPending(state.loaded.pending.filter((record) => !removed.has(recordKey(record))), `Removed ${removed.size} record${removed.size === 1 ? "" : "s"} from the local Change Set.`);
    state.selected.clear();
    state.detail = null;
    render();
  }






  async function saveEditor() {
    const record = readEditorRecord();
    const issues = root.GDSCommonValidation?.validateSchema(record, state.loaded.schema) || [];
    if (issues.length) throw new Error(issues.slice(0, 3).join(" "));
    const key = recordKey(record);
    if (state.editing.mode === "edit" && key !== recordKey(state.editing.original)) throw new Error("Natural key fields cannot be renamed.");
    const merged = pendingByKey();
    merged.set(key, record);
    await persistPending([...merged.values()], `Saved ${label(state.dataset)} in the local Change Set.`);
    dialog.close();
    state.source = "changeset";
    state.detail = { source: "changeset", key };
    state.screen = "records";
    render();
  }

  async function validateSaved(area, includeQuality = true) {
    const binding = await state.workspace.captureInputs(area);
    const loaded = await state.workspace.loadArea(area);
    const metadataContext = area === "model" ? await state.workspace.loadModelMetadata() : null;
    const metadata = metadataContext?.loaded || null;
    if (metadataContext) for (const input of metadataContext.inputs) {
      if (!binding.inputs.some(existing => existing.manifest_path === input.manifest_path)) binding.inputs.push(input);
    }
    const evidence = area === "model" && includeQuality ? await state.workspace.loadQualityEvidence() : { decisions: null, noteFiles: new Map(), files: [] };
    const validation = root.AtlasValidation.run(area, loaded, metadata, {
      tenantCode: state.workspace.owner(area).code, model: areaSnapshot("model")?.catalog?.model || null,
      includeQuality, decisions: evidence.decisions, noteFiles: evidence.noteFiles, missingMetadataOwners: metadataContext?.missing || [],
    });
    await state.workspace.assertInputsUnchanged(binding);
    await state.workspace.assertEvidenceUnchanged(evidence.files);
    return { loaded, validation: { ...validation, digest: binding.inputs.find(item => item.area === area).draft_digest, binding, evidenceFiles: evidence.files } };
  }

  async function runValidation(area) {
    try {
      state.busy = true; state.validationArea = area; render();
      const { validation } = await validateSaved(area);
      state.reports[area] = await state.workspace.saveValidationReport(area, validation);
      state.screen = "validation";
      setMessage(validation.valid ? `Local ${label(area)} checks passed. Business meaning and server validation remain separate.` : `Local ${label(area)} validation found ${validation.issueCount} findings.`);
    } catch (error) { showError(error); }
    finally { state.busy = false; render(); }
  }

  async function generateDbml() {
    try {
      state.busy = true; render();
      const { loaded, validation } = await validateSaved("model", false);
      if (!validation.valid) {
        state.validationArea = "model"; state.reports.model = await state.workspace.saveValidationReport("model", validation);
        state.screen = "validation";
        throw new Error("Correct the blocking Model findings before generating DBML.");
      }
      const documents = root.GDSDbml.render(loaded, areaSnapshot("model").catalog.model, { modelType: "full", includeSubmodels: true });
      const result = await state.workspace.saveDbmlDocuments(documents, { modelType: "full", includeSubmodels: true, binding: validation.binding });
      state.dbml = { documents, result, selected: documents[0].path };
      state.screen = "dbml";
      setMessage(`Generated ${result.file_count} DBML files from Snapshot + local changes.`);
    } catch (error) { state.dbml = null; showError(error); }
    finally { state.busy = false; render(); }
  }

  function dbmlWorkspace() {
    const preview = state.dbml;
    if (!preview) return recordsWorkspace();
    const current = preview.documents.find(item => item.path === preview.selected);
    return `<main class="dbml-workspace"><div class="work-heading"><div><span class="eyebrow">Snapshot + local changes</span><h1>DBML preview</h1><p>Saved in model-dbml. Regenerate after changing saved inputs.</p></div><button type="button" class="button" data-action="back-to-ledger">Back to records</button></div><div class="dbml-toolbar"><label>Generated file <select id="dbml-file">${preview.documents.map(item => `<option value="${escapeHtml(item.path)}" ${item.path === preview.selected ? "selected" : ""}>${escapeHtml(item.path)}</option>`).join("")}</select></label><button type="button" id="copy-dbml" class="button">Copy</button><button type="button" id="download-dbml" class="button">Download</button></div><pre class="dbml-text" tabindex="0">${escapeHtml(current.content)}</pre></main>`;
  }

  async function openValidationIssue(index) {
    const issue = state.reports[state.validationArea]?.issues?.[index];
    if (!issue || !areaSnapshot(state.validationArea)?.byName?.has(issue.dataset)) return;
    await switchArea(state.validationArea, issue.dataset);
    const pending = state.loaded.pending;
    const recordIndex = Number.isSafeInteger(issue.record) && issue.record > 0 ? issue.record - 1 : 0;
    const record = pending[recordIndex] || state.loaded.effective[recordIndex] || state.loaded.baseline[recordIndex];
    if (record) {
      const key = recordKey(record);
      const isPending = pending.some((item) => recordKey(item) === key);
      state.detail = { source: isPending ? "changeset" : "snapshot", key };
      state.screen = "records";
    }
    setMessage(`Opened ${label(issue.dataset)} for validation issue ${label(issue.code)}.`);
    render();
  }

  function bindInteractions() {
    document.getElementById("dbml-file")?.addEventListener("change", event => { state.dbml.selected = event.target.value; render(); });
    document.getElementById("copy-dbml")?.addEventListener("click", async () => {
      try { await navigator.clipboard.writeText(state.dbml.documents.find(item => item.path === state.dbml.selected).content); setMessage("DBML copied."); render(); }
      catch { showError(new Error("Clipboard access unavailable. Select the DBML text or use Download.")); }
    });
    document.getElementById("download-dbml")?.addEventListener("click", () => {
      const current = state.dbml.documents.find(item => item.path === state.dbml.selected);
      const url = URL.createObjectURL(new Blob([current.content], {type: "text/plain;charset=utf-8"}));
      const link = document.createElement("a"); link.href = url; link.download = current.path; link.click(); URL.revokeObjectURL(url);
    });
    document.getElementById("metadata-owner")?.addEventListener("change", async event => {
      try { await state.workspace.selectOwner(event.target.value); await loadReports(); await switchArea("metadata"); }
      catch (error) { showError(error); }
    });
    app.querySelectorAll("[data-column]").forEach(input => input.addEventListener("change", () => {
      const selected = new Set(recordFields([...state.loaded.baseline, ...state.loaded.pending]));
      if (input.checked) selected.add(input.dataset.column); else selected.delete(input.dataset.column);
      state.columns[`${state.area}:${state.dataset}`] = [...selected]; render();
    }));
    app.querySelectorAll("[data-resize-column]").forEach(handle => {
      const header = handle.closest("th");
      handle.addEventListener("keydown", event => {
        if (!["ArrowLeft", "ArrowRight"].includes(event.key)) return;
        event.preventDefault(); header.style.minWidth = `${Math.max(100, header.getBoundingClientRect().width + (event.key === "ArrowRight" ? 24 : -24))}px`;
      });
      handle.addEventListener("pointerdown", event => {
        const start = event.clientX, width = header.getBoundingClientRect().width;
        handle.setPointerCapture(event.pointerId);
        const move = event => { header.style.minWidth = `${Math.max(100, width + event.clientX - start)}px`; };
        handle.addEventListener("pointermove", move);
        handle.addEventListener("pointerup", () => handle.removeEventListener("pointermove", move), { once: true });
      });
    });
    document.getElementById("connect-button")?.addEventListener("click", connectFromPicker);
    document.getElementById("refresh-button")?.addEventListener("click", refresh);
    document.getElementById("validate-button")?.addEventListener("click", () => runValidation(state.screen === "validation" ? state.validationArea : state.area));
    document.getElementById("dbml-button")?.addEventListener("click", generateDbml);
    app.querySelectorAll("[data-area]").forEach((button) => button.addEventListener("click", async () => {
      if (button.dataset.area === "validation") { state.screen = "validation"; render(); }
      else await switchArea(button.dataset.area);
    }));
    app.querySelectorAll("[data-dataset]").forEach((button) => button.addEventListener("click", () => selectDataset(button.dataset.dataset).catch(showError)));
    app.querySelectorAll("[data-source]").forEach((button) => button.addEventListener("click", () => { state.source = button.dataset.source; state.page = 0; state.selected.clear(); render(); }));
    app.querySelectorAll("[data-filter-key]").forEach((input) => input.addEventListener("change", () => {
      const selected = new Set(state.filters[input.dataset.filterKey] || []);
      if (input.checked) selected.add(input.value); else selected.delete(input.value);
      state.filters[input.dataset.filterKey] = [...selected]; state.page = 0; state.selected.clear(); render();
    }));
    app.querySelectorAll("[data-clear-filter]").forEach((button) => button.addEventListener("click", () => { state.filters[button.dataset.clearFilter] = []; state.page = 0; state.selected.clear(); render(); }));
    app.querySelectorAll("[data-select-row]").forEach((input) => input.addEventListener("change", () => {
      const record = pagedRows().rows[Number(input.dataset.selectRow)];
      const key = recordKey(record); if (input.checked) state.selected.add(key); else state.selected.delete(key); render();
    }));
    app.querySelectorAll("[data-row-action]").forEach((button) => button.addEventListener("click", () => {
      const record = pagedRows().rows[Number(button.dataset.rowAction)];
      const draft = pendingByKey().get(recordKey(record));
      state.detail = { source: state.source === "snapshot" && draft ? "changeset" : state.source, key: recordKey(draft || record) };
      state.screen = "records";
      render();
      app.querySelector(".comparison-heading h2")?.focus();
    }));
    app.querySelectorAll("[data-report]").forEach((button) => button.addEventListener("click", () => { state.validationArea = button.dataset.report; state.validationFilters = { severity: [], dataset: [] }; render(); }));
    app.querySelectorAll("[data-validation-filter]").forEach((input) => input.addEventListener("change", () => {
      const selected = new Set(state.validationFilters[input.dataset.validationFilter]);
      if (input.checked) selected.add(input.value); else selected.delete(input.value);
      state.validationFilters[input.dataset.validationFilter] = [...selected]; render();
    }));
    app.querySelectorAll("[data-clear-validation]").forEach((button) => button.addEventListener("click", () => { state.validationFilters[button.dataset.clearValidation] = []; render(); }));
    app.querySelectorAll("[data-open-issue]").forEach((button) => button.addEventListener("click", () => openValidationIssue(Number(button.dataset.openIssue)).catch(showError)));
    app.querySelectorAll("[data-action]").forEach((button) => button.addEventListener("click", () => {
      const action = button.dataset.action;
      const pageRows = state.loaded ? pagedRows().rows : [];
      const selected = pageRows.filter((record) => state.selected.has(recordKey(record)));
      if (action === "select-all") {
        const candidates = pageRows.filter((record) => state.source === "changeset" || !pendingByKey().has(recordKey(record)));
        const all = candidates.length && candidates.every((record) => state.selected.has(recordKey(record)));
        candidates.forEach((record) => all ? state.selected.delete(recordKey(record)) : state.selected.add(recordKey(record)));
        render();
      }
      if (action === "previous-page") { state.page--; state.selected.clear(); render(); }
      if (action === "next-page") { state.page++; state.selected.clear(); render(); }
      if (action === "stage-selected") stageRecords(selected).catch(showError);
      if (action === "remove-selected") removeDrafts(selected).catch(showError);
      if (action === "add-row") openEditor("add", {});
      if (action === "back-to-ledger") { state.screen = "records"; state.detail = null; render(); }
      if (action === "stage-detail") stageRecords([state.loaded.baseline.find((record) => recordKey(record) === state.detail.key)]).catch(showError);
      if (action === "open-detail-draft") { state.detail = { source: "changeset", key: state.detail.key }; render(); }
      if (action === "edit-detail-draft") { const record = pendingByKey().get(state.detail.key); if (record) openEditor("edit", record); }
      if (action === "remove-detail-draft") { const record = pendingByKey().get(state.detail.key); if (record) removeDrafts([record]).catch(showError); }
      if (action === "run-report") runValidation(state.validationArea);
    }));
  }

  const { filtersForDataset, pagedRows, recordFields, recordsWorkspace, detailWorkspace, DETAIL_FIELDS } = root.AtlasRecords.create({ state, PAGE_SIZE, areaSnapshot, recordKey, pendingByKey, eligible, recordReadOnlyReason });
  const { validationWorkspace } = root.AtlasValidationUI.create({ state, canValidate });
  const { openEditor, readEditorRecord, dirty } = root.AtlasEditor.create({ state, dialog, editorFields, editorMessage, eligible, recordKey, recordFields, DETAIL_FIELDS, recordReadOnlyReason });

  editorForm.addEventListener("submit", (event) => {
    event.preventDefault();
    editorMessage.textContent = "";
    document.getElementById("save-row-editor").disabled = true;
    saveEditor().catch((error) => { editorMessage.textContent = error?.message || String(error); }).finally(() => { document.getElementById("save-row-editor").disabled = false; });
  });
  function requestEditorClose() {
    if (!dirty()) return dialog.close();
    document.getElementById("unsaved-dialog").showModal();
  }
  document.getElementById("close-row-editor").addEventListener("click", requestEditorClose);
  document.getElementById("cancel-row-editor").addEventListener("click", requestEditorClose);
  dialog.addEventListener("cancel", event => { event.preventDefault(); requestEditorClose(); });
  document.getElementById("unsaved-cancel").addEventListener("click", () => document.getElementById("unsaved-dialog").close());
  document.getElementById("unsaved-discard").addEventListener("click", () => { document.getElementById("unsaved-dialog").close(); dialog.close(); });
  document.getElementById("unsaved-save").addEventListener("click", async () => {
    document.getElementById("unsaved-dialog").close();
    try { await saveEditor(); } catch (error) { editorMessage.textContent = error.message; }
  });
  root.addEventListener("beforeunload", event => { if (dirty()) { event.preventDefault(); event.returnValue = ""; } });
  dialog.addEventListener("close", () => { state.editing = null; editorMessage.textContent = ""; });

  root.GDSWorkbenchApp = root.AtlasWorkbenchApp = { connectDirectoryHandle, refresh, selectDataset, switchArea, runValidation, generateDbml, state };
  render();
})(globalThis);
