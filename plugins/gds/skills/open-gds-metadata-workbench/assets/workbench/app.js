(function () {
  "use strict";

  const logic = window.GdsWorkbenchLogic;
  const PAGE_SIZE = 50;
  const EXPECTED_IGNORE = "*\n!.gitignore\n";
  const state = {
    profile: null,
    gdsHandle: null,
    snapshotHandle: null,
    changeSetHandle: null,
    datasetsHandle: null,
    manifest: null,
    catalog: null,
    memberIndex: new Map(),
    datasets: [],
    datasetByName: new Map(),
    schemaCache: new Map(),
    snapshotSearchCache: new Map(),
    snapshotTextCache: new Map(),
    snapshotCache: new Map(),
    changeCache: new Map(),
    pendingCounts: new Map(),
    activeDataset: null,
    view: "snapshot",
    selectedIndex: null,
    selectedRecord: null,
    selectedIndexes: new Set(),
    query: "",
    datasetQuery: "",
    page: 1,
    formMode: null,
    formIndex: null,
    formBaseline: null,
    formOriginalRecord: null,
    referenceSuggestions: new Map(),
    localControl: null,
    createdChangeSet: false,
    handoffText: "",
    modelStageText: "",
    busy: false
  };

  const $ = (selector, parent = document) => parent.querySelector(selector);
  const elements = {
    welcome: $("#welcome"), appShell: $("#appShell"), connectButton: $("#connectButton"),
    welcomeConnectButton: $("#welcomeConnectButton"), reloadButton: $("#reloadButton"),
    connectionSummary: $("#connectionSummary"), browserNote: $("#browserNote"),
    datasetTotal: $("#datasetTotal"), datasetSearch: $("#datasetSearch"), datasetNav: $("#datasetNav"),
    datasetContext: $("#datasetContext"), datasetTitle: $("#datasetTitle"), datasetDescription: $("#datasetDescription"),
    snapshotTab: $("#snapshotTab"), changeSetTab: $("#changeSetTab"), stateBanner: $("#stateBanner"),
    rowSearch: $("#rowSearch"), rowSummary: $("#rowSummary"), schemaButton: $("#schemaButton"),
    newRowButton: $("#newRowButton"), saveButton: $("#saveButton"), tableFrame: $("#tableFrame"),
    loadingState: $("#loadingState"), dataTable: $("#dataTable"), pageLabel: $("#pageLabel"),
    previousPage: $("#previousPage"), nextPage: $("#nextPage"), inspector: $("#inspector"),
    recordDialog: $("#recordDialog"), recordForm: $("#recordForm"), dialogKicker: $("#dialogKicker"),
    dialogTitle: $("#dialogTitle"), formErrors: $("#formErrors"), fieldGrid: $("#fieldGrid"),
    recordSubmitButton: $("#recordSubmitButton"), diffPreview: $("#diffPreview"),
    selectionActions: $("#selectionActions"), selectionSummary: $("#selectionSummary"),
    selectPageButton: $("#selectPageButton"), clearSelectionButton: $("#clearSelectionButton"),
    bulkEditButton: $("#bulkCopyButton"), bulkDeactivateButton: $("#bulkDeactivateButton"),
    reviewStrip: $("#reviewStrip"), reviewTitle: $("#reviewTitle"), reviewSummary: $("#reviewSummary"),
    reviewButton: $("#reviewButton"), reviewDialog: $("#reviewDialog"), reviewContent: $("#reviewContent"),
    copyHandoffButton: $("#copyHandoffButton"), schemaDialog: $("#schemaDialog"),
    schemaDialogTitle: $("#schemaDialogTitle"), schemaContent: $("#schemaContent"), toastRegion: $("#toastRegion"),
    snapshotKindSelect: $("#snapshotKindSelect"),
    exportModelSnapshotButton: $("#exportModelSnapshotButton")
  };

  if (!elements.exportModelSnapshotButton) {
    const button = document.createElement("button");
    button.className = "button quiet";
    button.id = "exportModelSnapshotButton";
    button.type = "button";
    button.textContent = "Export proposed model JSON";
    button.hidden = true;
    elements.saveButton.before(button);
    elements.exportModelSnapshotButton = button;
  }

  function toast(title, message, kind = "") {
    const node = document.createElement("div");
    node.className = `toast ${kind}`.trim();
    const heading = document.createElement("strong");
    const copy = document.createElement("span");
    heading.textContent = title;
    copy.textContent = message;
    node.append(heading, copy);
    elements.toastRegion.appendChild(node);
    window.setTimeout(() => node.remove(), 6500);
  }

  function setBusy(busy, message = "Working…") {
    state.busy = busy;
    elements.connectButton.disabled = busy;
    elements.welcomeConnectButton.disabled = busy;
    elements.reloadButton.disabled = busy;
    elements.exportModelSnapshotButton.disabled = busy;
    if (busy && !elements.appShell.hidden) {
      elements.loadingState.hidden = false;
      elements.loadingState.textContent = message;
      elements.dataTable.hidden = true;
    }
  }

  async function getHandleAt(rootHandle, path, kind, create = false) {
    const parts = logic.safePathParts(path);
    let current = rootHandle;
    for (let index = 0; index < parts.length - 1; index++) {
      current = await current.getDirectoryHandle(parts[index], { create: false });
    }
    const name = parts[parts.length - 1];
    return kind === "directory"
      ? current.getDirectoryHandle(name, { create })
      : current.getFileHandle(name, { create });
  }

  async function tryDirectory(rootHandle, name) {
    try { return await rootHandle.getDirectoryHandle(name, { create: false }); }
    catch (error) { if (error.name === "NotFoundError") return null; throw error; }
  }

  async function tryFile(rootHandle, name) {
    try { return await rootHandle.getFileHandle(name, { create: false }); }
    catch (error) { if (error.name === "NotFoundError") return null; throw error; }
  }

  async function writeFileText(fileHandle, text) {
    const writable = await fileHandle.createWritable();
    try {
      await writable.write(text);
      await writable.close();
    } catch (error) {
      try { await writable.abort(); } catch (_abortError) { /* Preserve the original write error. */ }
      throw error;
    }
  }

  async function ensureIgnoredWorkspace(gdsHandle) {
    const ignoreHandle = await tryFile(gdsHandle, ".gitignore");
    if (!ignoreHandle) {
      const created = await gdsHandle.getFileHandle(".gitignore", { create: true });
      await writeFileText(created, EXPECTED_IGNORE);
      return;
    }
    const current = (await (await ignoreHandle.getFile()).text()).replace(/\r\n/g, "\n");
    if (current !== EXPECTED_IGNORE) throw new Error("GDS/.gitignore has unexpected content. Run the plugin workspace initializer before continuing.");
  }

  async function resolveGdsHandle(selected) {
    if (selected.name === "GDS") return selected;
    const existing = await tryDirectory(selected, "GDS");
    if (existing) return existing;
    throw new Error(`No GDS folder exists inside “${selected.name}”. Create it with the plugin workspace helper, then reconnect.`);
  }

  async function sha256(buffer) {
    if (!window.crypto?.subtle) throw new Error("This browser cannot verify Snapshot hashes. Use current Chrome or Edge.");
    const digest = await window.crypto.subtle.digest("SHA-256", buffer);
    return Array.from(new Uint8Array(digest), (value) => value.toString(16).padStart(2, "0")).join("");
  }

  async function readVerifiedSnapshotFile(snapshotHandle, memberIndex, path) {
    const record = memberIndex.get(path);
    if (!record) throw new Error(`Snapshot manifest does not authorize ${path}.`);
    const handle = await getHandleAt(snapshotHandle, path, "file");
    const file = await handle.getFile();
    if (Number.isInteger(record.size_bytes) && file.size !== record.size_bytes) throw new Error(`${path} does not match its Snapshot size.`);
    const buffer = await file.arrayBuffer();
    if (typeof record.sha256 !== "string" || await sha256(buffer) !== record.sha256) throw new Error(`${path} does not match its Snapshot SHA-256.`);
    return new TextDecoder("utf-8", { fatal: true }).decode(buffer);
  }

  async function readSnapshotFile(path) {
    return readVerifiedSnapshotFile(state.snapshotHandle, state.memberIndex, path);
  }

  function validateManifest(manifest, expectedKind = null) {
    if (!logic.isObject(manifest)) throw new Error("Snapshot manifest is invalid.");
    const profile = logic.profileForManifest(manifest);
    if (expectedKind && profile.kind !== expectedKind) throw new Error(`The ${profile.snapshotDirectory} manifest has the wrong Snapshot kind.`);
    if (manifest.database_ids_included !== false) throw new Error("Snapshot must be ID-free.");
    if (typeof manifest.snapshot_id !== "string") throw new Error("Snapshot identity is incomplete.");
    if (profile.kind === "metadata" && (typeof manifest.tenant_code !== "string" || !manifest.tenant_code.trim())) throw new Error("Metadata Snapshot identity is incomplete.");
    if (profile.kind === "model" && (!Number.isInteger(manifest.model_id) || manifest.model_id <= 0 || typeof manifest.model_name !== "string" || !manifest.model_name.trim() || !Number.isInteger(manifest.model_revision) || manifest.model_revision <= 0)) {
      throw new Error("Model Snapshot identity is incomplete.");
    }
    if (!Array.isArray(manifest.members)) throw new Error("Snapshot manifest has no member inventory.");
    const paths = new Set();
    for (const member of manifest.members) {
      if (!logic.isObject(member) || typeof member.path !== "string" || typeof member.sha256 !== "string" || !Number.isInteger(member.size_bytes)) throw new Error("Snapshot manifest contains an invalid member.");
      logic.safePathParts(member.path);
      if (paths.has(member.path)) throw new Error("Snapshot manifest contains a duplicate member path.");
      paths.add(member.path);
    }
    return profile;
  }

  function humanize(value) {
    return String(value || "").replace(/_/g, " ").replace(/\b\w/g, (letter) => letter.toLocaleUpperCase("en-US"));
  }

  function flattenCatalog(catalog, profile, manifest) {
    if (!logic.isObject(catalog) || catalog.schema_version !== "2.0" || catalog.snapshot_kind !== profile.kind || catalog.database_ids_included !== false) {
      throw new Error(`catalog.json is not a supported ID-free ${humanize(profile.kind)} Catalog.`);
    }
    if (!Array.isArray(catalog.sections)) throw new Error("catalog.json has no sections.");
    if (profile.kind === "model" && (catalog.model?.model_id !== manifest.model_id || catalog.model?.model_name !== manifest.model_name || catalog.model?.model_revision !== manifest.model_revision)) {
      throw new Error("Model Catalog identity does not match its manifest.");
    }
    const result = [];
    const seen = new Set();
    for (const section of catalog.sections) {
      if (!logic.isObject(section) || typeof section.name !== "string" || !Array.isArray(section.datasets)) throw new Error("catalog.json contains an invalid section.");
      for (const dataset of section.datasets) {
        if (!logic.isObject(dataset) || typeof dataset.name !== "string" || seen.has(dataset.name)) throw new Error("catalog.json contains an invalid or duplicate dataset.");
        [dataset.schema_file, dataset.rows_file].forEach(logic.safePathParts);
        if (dataset.search_file !== undefined) logic.safePathParts(dataset.search_file);
        seen.add(dataset.name);
        result.push({
          ...dataset,
          label: dataset.label || humanize(dataset.name),
          search_file: dataset.search_file || dataset.rows_file,
          search_fields: Array.isArray(dataset.search_fields) ? dataset.search_fields : Array.isArray(dataset.canonical_key) ? dataset.canonical_key : [],
          search_result_complete: dataset.search_result_complete !== false,
          section: section.name,
          sectionLabel: section.label || humanize(section.name)
        });
      }
    }
    if (profile.kind === "model") {
      const names = new Set(result.map((dataset) => dataset.name));
      const missing = logic.MODEL_DATASETS.filter((name) => !names.has(name));
      const unknown = result.filter((dataset) => !logic.MODEL_DATASETS.includes(dataset.name)).map((dataset) => dataset.name);
      if (missing.length || unknown.length || result.length !== logic.MODEL_DATASETS.length) {
        throw new Error("Model Catalog must contain exactly the 19 supported Model Change Set datasets.");
      }
    }
    return result;
  }

  function profileDatasetNames(profile) {
    return profile.kind === "model" ? logic.MODEL_DATASETS : logic.METADATA_DATASETS;
  }

  function workspaceIdentity(manifest) {
    return state.profile?.kind === "model"
      ? `${manifest.model_name} · model revision ${manifest.model_revision}`
      : manifest.tenant_code;
  }

  async function inspectExistingChangeSet(gdsHandle, manifest, profile, confirmReuse = true) {
    const changeSetHandle = await tryDirectory(gdsHandle, profile.changeSetDirectory);
    if (!changeSetHandle) {
      return {
        changeSetHandle: null,
        datasetsHandle: null,
        localControl: logic.createLocalState(manifest),
        pendingCounts: new Map()
      };
    }
    if (confirmReuse && !window.confirm(`An existing GDS/${profile.changeSetDirectory} folder was found. Open and continue that local draft?`)) {
      throw new Error(`Rename or remove the existing GDS/${profile.changeSetDirectory} folder, then reconnect to start a different draft.`);
    }
    const stateHandle = await tryFile(changeSetHandle, profile.controlFile);
    if (!stateHandle) throw new Error(`Existing ${profile.changeSetDirectory}/${profile.controlFile} is missing. Rename or remove that folder before continuing.`);
    const local = logic.parseJson(await (await stateHandle.getFile()).text(), `${profile.changeSetDirectory}/${profile.controlFile}`);
    const identityMatches = profile.kind === "model"
      ? local?.model?.model_id === manifest.model_id && local?.model?.model_name === manifest.model_name && local?.model?.model_revision === manifest.model_revision
      : local?.tenant?.tenant_code === manifest.tenant_code;
    if (local?.format_version !== "1.0" || !identityMatches || local?.snapshot?.snapshot_id !== manifest.snapshot_id || local?.snapshot?.path !== `../${profile.snapshotDirectory}`) {
      throw new Error(`Existing ${humanize(profile.kind)} Change Set belongs to another Snapshot.`);
    }
    if (!["local", "active", "validated"].includes(local?.server_change_set?.status)) throw new Error("Existing Change Set control state is invalid.");
    if (!logic.isObject(local.datasets)) throw new Error("Existing Change Set dataset state is invalid.");
    const datasetsHandle = await tryDirectory(changeSetHandle, "datasets");
    if (!datasetsHandle) throw new Error(`Existing ${profile.changeSetDirectory}/datasets is missing. Rename or remove that folder before continuing.`);
    const pendingCounts = new Map();
    const eligible = new Set(profileDatasetNames(profile));
    for await (const [name, handle] of datasetsHandle.entries()) {
      if (handle.kind !== "file" || !name.endsWith(".json")) throw new Error("Change Set datasets may contain only JSON files.");
      const dataset = name.slice(0, -5);
      if (!eligible.has(dataset)) throw new Error(`Change Set contains an ineligible dataset: ${dataset}.`);
      const file = await handle.getFile();
      const rows = logic.parseRows(await file.text(), `${profile.changeSetDirectory}/datasets/${name}`);
      pendingCounts.set(dataset, rows.length);
    }
    return { changeSetHandle, datasetsHandle, localControl: local, pendingCounts };
  }

  async function ensureWritableDraft() {
    if (state.changeSetHandle && state.datasetsHandle) return;
    const permission = await state.gdsHandle.requestPermission?.({ mode: "readwrite" });
    if (permission !== "granted") throw new Error("Write access to GDS was not granted. No local files were changed.");
    await ensureIgnoredWorkspace(state.gdsHandle);
    const changeSetHandle = state.profile.kind === "metadata"
      ? await state.gdsHandle.getDirectoryHandle("change-set", { create: true })
      : await state.gdsHandle.getDirectoryHandle(state.profile.changeSetDirectory, { create: true });
    const datasetsHandle = await changeSetHandle.getDirectoryHandle("datasets", { create: true });
    let controlHandle = await tryFile(changeSetHandle, state.profile.controlFile);
    if (!controlHandle) {
      controlHandle = await changeSetHandle.getFileHandle(state.profile.controlFile, { create: true });
      await writeFileText(controlHandle, JSON.stringify(state.localControl, null, 2) + "\n");
      state.createdChangeSet = true;
    }
    state.changeSetHandle = changeSetHandle;
    state.datasetsHandle = datasetsHandle;
    showConnectedWorkspace();
    updateReviewStrip();
  }

  async function connectWorkspace(options = {}) {
    const suppliedHandle = options.directoryHandle || null;
    const suppliedKind = ["metadata", "model"].includes(options.snapshotKind) ? options.snapshotKind : null;
    if (!suppliedHandle && !("showDirectoryPicker" in window)) {
      toast("Browser not supported", "Open this utility in current Chrome or Edge.", "error");
      return;
    }
    if (hasDirtyChanges() && !window.confirm("Discard unsaved Workbench edits and choose another workspace?")) return;
    setBusy(true, "Connecting to GDS…");
    try {
      const selected = suppliedHandle || await window.showDirectoryPicker({ id: "gds-metadata-workbench", mode: "read" });
      const gdsHandle = await resolveGdsHandle(selected);
      const requestedKind = suppliedKind || (["metadata", "model"].includes(elements.snapshotKindSelect?.value) ? elements.snapshotKindSelect.value : null);
      const available = new Map();
      for (const [kind, profile] of Object.entries(logic.PROFILES)) {
        const handle = await tryDirectory(gdsHandle, profile.snapshotDirectory);
        if (handle) available.set(kind, { profile, handle });
      }
      if (!available.size) throw new Error("GDS/metadata-snapshot or GDS/model-snapshot is required. Add an extracted Snapshot and reconnect.");
      let selectedSnapshot = requestedKind ? available.get(requestedKind) : null;
      if (requestedKind && !selectedSnapshot) throw new Error(`GDS/${logic.PROFILES[requestedKind].snapshotDirectory} is missing.`);
      if (!selectedSnapshot && available.size === 1) selectedSnapshot = [...available.values()][0];
      if (!selectedSnapshot) {
        const answer = window.prompt("Both Metadata and Model Snapshots were found. Type metadata or model.", "metadata");
        if (answer === null) throw new DOMException("Workspace choice cancelled.", "AbortError");
        selectedSnapshot = available.get(answer.trim().toLocaleLowerCase("en-US"));
        if (!selectedSnapshot) throw new Error("Choose exactly metadata or model.");
      }
      const { profile: expectedProfile, handle: snapshotHandle } = selectedSnapshot;
      const manifestHandle = await tryFile(snapshotHandle, "manifest.json");
      if (!manifestHandle) throw new Error(`${expectedProfile.snapshotDirectory}/manifest.json is missing.`);
      const manifest = logic.parseJson(await (await manifestHandle.getFile()).text(), "manifest.json");
      const profile = validateManifest(manifest, expectedProfile.kind);
      const memberIndex = new Map(manifest.members.map((member) => [member.path, member]));
      const catalogPath = manifest.catalog?.path;
      if (catalogPath !== "catalog.json") throw new Error("Snapshot catalog path is invalid.");
      const catalog = logic.parseJson(
        await readVerifiedSnapshotFile(snapshotHandle, memberIndex, catalogPath),
        "catalog.json"
      );
      const datasets = flattenCatalog(catalog, profile, manifest);
      const local = await inspectExistingChangeSet(gdsHandle, manifest, profile);

      state.profile = profile;
      state.gdsHandle = gdsHandle;
      state.snapshotHandle = snapshotHandle;
      state.changeSetHandle = local.changeSetHandle;
      state.datasetsHandle = local.datasetsHandle;
      state.manifest = manifest;
      state.memberIndex = memberIndex;
      state.catalog = catalog;
      state.datasets = datasets;
      state.datasetByName = new Map(datasets.map((dataset) => [dataset.name, dataset]));
      state.localControl = local.localControl;
      state.schemaCache.clear(); state.snapshotSearchCache.clear();
      state.snapshotTextCache.clear(); state.snapshotCache.clear(); state.changeCache.clear();
      state.pendingCounts = local.pendingCounts;
      state.createdChangeSet = false;
      state.modelStageText = "";
      state.activeDataset = null; state.view = "snapshot"; state.selectedIndex = null;
      state.selectedRecord = null; state.selectedIndexes.clear(); state.query = ""; state.page = 1;
      elements.rowSearch.value = "";
      showConnectedWorkspace();
      renderDatasetNav();
      const first = state.datasetByName.get(profile.kind === "model" ? "conceptual_object" : "source_object") || datasets[0];
      if (first) await selectDataset(first.name);
      toast("GDS workspace ready", `${workspaceIdentity(manifest)} · ${datasets.length} datasets · Snapshot verified on demand.`, "success");
      if (state.createdChangeSet) toast("Local Change Set created", "This draft is local only until an approved Tenant Lock and server Change Set bind it.", "warning");
    } catch (error) {
      if (error.name !== "AbortError") toast("Could not open GDS workspace", error.message, "error");
    } finally { setBusy(false); }
  }

  function showConnectedWorkspace() {
    elements.welcome.hidden = true;
    elements.appShell.hidden = false;
    elements.reloadButton.hidden = false;
    elements.connectionSummary.classList.add("connected");
    const server = state.localControl.server_change_set;
    const binding = !state.changeSetHandle
      ? "no local draft"
      : server.status === "local" ? "local draft" : `${server.status} · revision ${server.draft_revision}`;
    $("span:last-child", elements.connectionSummary).textContent = `${workspaceIdentity(state.manifest)} · ${binding}`;
    elements.connectButton.textContent = "Change workspace";
    elements.datasetTotal.textContent = String(state.datasets.length);
    elements.exportModelSnapshotButton.hidden = state.profile.kind !== "model";
  }

  function renderDatasetNav() {
    elements.datasetNav.replaceChildren();
    const query = state.datasetQuery.trim().toLocaleLowerCase("en-US");
    const sectionNames = [...new Set(state.datasets.map((dataset) => dataset.section))];
    for (const sectionName of sectionNames) {
      const datasets = state.datasets.filter((dataset) => dataset.section === sectionName && (!query || `${dataset.name} ${dataset.label}`.toLocaleLowerCase("en-US").includes(query)));
      if (!datasets.length) continue;
      const section = document.createElement("section");
      section.className = "nav-section";
      const title = document.createElement("div");
      title.className = "nav-section-title";
      title.textContent = datasets[0].sectionLabel;
      section.appendChild(title);
      datasets.forEach((dataset) => {
        const button = document.createElement("button");
        button.className = `dataset-link${state.activeDataset === dataset.name ? " active" : ""}`;
        button.type = "button";
        button.dataset.dataset = dataset.name;
        const label = document.createElement("span");
        label.textContent = dataset.label || dataset.name;
        const count = document.createElement("span");
        const pending = state.pendingCounts.get(dataset.name);
        count.className = pending === undefined ? "dataset-count" : "pending-count";
        count.textContent = pending === undefined ? String(dataset.row_count ?? 0) : String(pending);
        count.title = pending === undefined ? "Snapshot rows" : "Local Change Set records";
        button.append(label, count);
        button.addEventListener("click", () => selectDataset(dataset.name));
        section.appendChild(button);
      });
      elements.datasetNav.appendChild(section);
    }
  }

  async function loadSchema(datasetName) {
    if (state.schemaCache.has(datasetName)) return state.schemaCache.get(datasetName);
    const dataset = state.datasetByName.get(datasetName);
    const schema = logic.parseJson(await readSnapshotFile(dataset.schema_file), dataset.schema_file);
    logic.validateSchema(schema, datasetName, false);
    state.schemaCache.set(datasetName, schema);
    return schema;
  }

  async function loadSnapshotSearchRows(datasetName) {
    if (state.snapshotSearchCache.has(datasetName)) return state.snapshotSearchCache.get(datasetName);
    const dataset = state.datasetByName.get(datasetName);
    const text = await readSnapshotFile(dataset.search_file);
    const rows = logic.parseRows(text, dataset.search_file);
    if (Number.isInteger(dataset.row_count) && rows.length !== dataset.row_count) throw new Error(`${datasetName} row count does not match the Catalog.`);
    if (rows.some((row) => (dataset.search_fields || []).some((field) => !Object.prototype.hasOwnProperty.call(row, field)))) {
      throw new Error(`${datasetName} lookup does not contain every declared search field.`);
    }
    if (dataset.search_result_complete === false && rows.some((row) => !Number.isInteger(row.line) || row.line < 1)) {
      throw new Error(`${datasetName} lookup contains an invalid row line.`);
    }
    if (dataset.search_file === dataset.rows_file) state.snapshotTextCache.set(datasetName, text);
    state.snapshotSearchCache.set(datasetName, rows);
    return rows;
  }

  async function snapshotRowsText(datasetName) {
    if (state.snapshotTextCache.has(datasetName)) return state.snapshotTextCache.get(datasetName);
    const dataset = state.datasetByName.get(datasetName);
    const text = dataset.search_file === dataset.rows_file
      ? await readSnapshotFile(dataset.search_file)
      : await readSnapshotFile(dataset.rows_file);
    state.snapshotTextCache.set(datasetName, text);
    return text;
  }

  async function loadSnapshotRecord(datasetName, searchIndex) {
    const dataset = state.datasetByName.get(datasetName);
    const searchRows = await loadSnapshotSearchRows(datasetName);
    const searchRecord = searchRows[searchIndex];
    if (!searchRecord) return null;
    let record = searchRecord;
    if (dataset.search_result_complete === false) {
      const lines = (await snapshotRowsText(datasetName)).split(/\r?\n/);
      const raw = lines[searchRecord.line - 1];
      if (!raw) throw new Error(`${datasetName} row line is outside the verified rows file.`);
      record = logic.parseJson(raw, `${dataset.rows_file} line ${searchRecord.line}`);
    }
    const schema = await loadSchema(datasetName);
    const errors = logic.validateRecord(record, schema);
    if (errors.length) throw new Error(`${datasetName} row does not match its verified schema.`);
    return record;
  }

  async function loadSnapshotRows(datasetName) {
    if (state.snapshotCache.has(datasetName)) return state.snapshotCache.get(datasetName);
    const dataset = state.datasetByName.get(datasetName);
    const text = await snapshotRowsText(datasetName);
    const rows = logic.parseRows(text, dataset.rows_file);
    if (Number.isInteger(dataset.row_count) && rows.length !== dataset.row_count) throw new Error(`${datasetName} row count does not match the Catalog.`);
    state.snapshotCache.set(datasetName, rows);
    return rows;
  }

  async function loadChangeRows(datasetName) {
    if (state.changeCache.has(datasetName)) return state.changeCache.get(datasetName);
    const handle = state.datasetsHandle
      ? await tryFile(state.datasetsHandle, `${datasetName}.json`)
      : null;
    let sourceText = null;
    let rows = [];
    if (handle) {
      sourceText = await (await handle.getFile()).text();
      rows = logic.parseRows(sourceText, `${state.profile.changeSetDirectory}/datasets/${datasetName}.json`);
    }
    const schema = await loadSchema(datasetName);
    const errors = logic.validateDataset(rows, schema);
    const entry = { rows, sourceText, fileHandle: handle, dirty: false, errors };
    state.changeCache.set(datasetName, entry);
    if (handle) state.pendingCounts.set(datasetName, rows.length);
    return entry;
  }

  function hasDirtyChanges() {
    return [...state.changeCache.values()].some((entry) => entry.dirty);
  }

  async function selectDataset(datasetName) {
    if (!state.datasetByName.has(datasetName)) return;
    setBusy(true, `Loading ${datasetName}…`);
    try {
      state.activeDataset = datasetName;
      state.selectedIndex = null;
      state.selectedRecord = null;
      state.selectedIndexes.clear();
      state.page = 1;
      const dataset = state.datasetByName.get(datasetName);
      const schema = await loadSchema(datasetName);
      await loadSnapshotSearchRows(datasetName);
      if (!isChangeEligible(dataset, schema) && state.view === "change-set") state.view = "snapshot";
      if (state.view === "change-set") {
        await loadSnapshotRows(datasetName);
        await loadChangeRows(datasetName);
      }
      elements.datasetContext.textContent = `${dataset.sectionLabel} · ${schema["x-gds-record-type"] || schema.title || "record"}`;
      elements.datasetTitle.textContent = dataset.label || dataset.name;
      elements.datasetDescription.textContent = schema.description || dataset.name;
      elements.changeSetTab.disabled = !isChangeEligible(dataset, schema);
      renderDatasetNav();
      renderWorkspace();
    } catch (error) {
      toast("Dataset could not be loaded", error.message, "error");
      elements.loadingState.textContent = error.message;
    } finally { setBusy(false); }
  }

  async function switchView(view) {
    if (!state.activeDataset || state.busy || view === state.view) return;
    const dataset = state.datasetByName.get(state.activeDataset);
    const schema = state.schemaCache.get(state.activeDataset);
    if (view === "change-set" && !isChangeEligible(dataset, schema)) return;
    setBusy(true, "Loading local Change Set…");
    try {
      if (view === "change-set") {
        await loadSnapshotRows(state.activeDataset);
        await loadChangeRows(state.activeDataset);
      }
      state.view = view;
      state.selectedIndex = null;
      state.selectedRecord = null;
      state.selectedIndexes.clear();
      state.page = 1;
      renderWorkspace();
    } catch (error) { toast("Could not switch view", error.message, "error"); }
    finally { setBusy(false); }
  }

  function currentRows() {
    if (!state.activeDataset) return [];
    return state.view === "snapshot"
      ? state.snapshotSearchCache.get(state.activeDataset) || []
      : state.changeCache.get(state.activeDataset)?.rows || [];
  }

  function filteredRows() {
    const query = state.query.trim().toLocaleLowerCase("en-US");
    return currentRows().map((row, index) => ({ row, index })).filter(({ row }) => !query || Object.values(row).some((value) => displayValue(value).toLocaleLowerCase("en-US").includes(query)));
  }

  function displayValue(value) {
    if (value === null || value === undefined) return "null";
    if (typeof value === "object") return JSON.stringify(value);
    return String(value);
  }

  function isChangeEligible(dataset, schema) {
    if (!dataset || !schema || schema["x-gds-change-set-eligible"] !== true) return false;
    const supported = state.profile.kind === "model" ? logic.MODEL_DATASETS : logic.METADATA_DATASETS;
    return supported.includes(dataset.name) && (state.profile.kind === "model" || dataset.section === "operational");
  }

  function modelStatusField(schema) {
    if (Object.prototype.hasOwnProperty.call(schema?.properties || {}, "is_active")) return "is_active";
    return Object.keys(schema?.properties || {}).find((field) => field.endsWith("_status")) || null;
  }

  function renderWorkspace() {
    document.body.dataset.view = state.view;
    document.body.dataset.snapshotKind = state.profile.kind;
    elements.snapshotTab.classList.toggle("active", state.view === "snapshot");
    elements.changeSetTab.classList.toggle("active", state.view === "change-set");
    elements.snapshotTab.setAttribute("aria-pressed", String(state.view === "snapshot"));
    elements.changeSetTab.setAttribute("aria-pressed", String(state.view === "change-set"));
    if (state.view === "snapshot") {
      elements.stateBanner.className = "state-banner snapshot-banner";
      elements.stateBanner.replaceChildren(textNode("strong", "Immutable Snapshot"), textNode("span", "Rows are verified against the Snapshot manifest and cannot be edited here."));
      elements.newRowButton.hidden = true;
      elements.saveButton.hidden = true;
    } else {
      const control = state.localControl.server_change_set;
      const status = control.status === "local" ? "Not bound to a server Change Set" : `Bound to revision ${control.draft_revision}`;
      elements.stateBanner.className = "state-banner change-banner";
      elements.stateBanner.replaceChildren(textNode("strong", "Editable local Change Set"), textNode("span", `${status}. Saving here never Stages or Applies ${state.profile.kind === "model" ? "the model" : "metadata"}.`));
      elements.newRowButton.hidden = false;
      elements.saveButton.hidden = false;
    }
    updateSaveButton();
    renderTable();
    renderInspector();
  }

  function textNode(tag, text) {
    const node = document.createElement(tag);
    node.textContent = text;
    return node;
  }

  function renderTable() {
    const dataset = state.datasetByName.get(state.activeDataset);
    const schema = state.schemaCache.get(state.activeDataset);
    if (!dataset || !schema) return;
    const rows = filteredRows();
    const pages = Math.max(1, Math.ceil(rows.length / PAGE_SIZE));
    if (state.page > pages) state.page = pages;
    const pageRows = rows.slice((state.page - 1) * PAGE_SIZE, state.page * PAGE_SIZE);
    const searchable = Array.isArray(dataset.search_fields) && dataset.search_fields.length
      ? dataset.search_fields
      : logic.canonicalColumns(schema);
    const columns = state.view === "snapshot"
      ? (searchable.length ? searchable : Object.keys(schema.properties || {}))
      : Object.keys(schema.properties || {});
    const keyColumns = new Set(logic.canonicalColumns(schema));
    const headRow = document.createElement("tr");
    const selectionHeading = document.createElement("th");
    selectionHeading.className = "selection-column";
    selectionHeading.textContent = "Select";
    headRow.appendChild(selectionHeading);
    const numberHeading = document.createElement("th");
    numberHeading.textContent = "#";
    numberHeading.className = "row-number";
    headRow.appendChild(numberHeading);
    columns.forEach((column) => {
      const heading = document.createElement("th");
      heading.textContent = column;
      if (keyColumns.has(column)) heading.className = "key-heading";
      headRow.appendChild(heading);
    });
    $("thead", elements.dataTable).replaceChildren(headRow);
    const body = $("tbody", elements.dataTable);
    body.replaceChildren();
    pageRows.forEach(({ row, index }) => {
      const tr = document.createElement("tr");
      if (state.selectedIndex === index) tr.classList.add("selected");
      tr.tabIndex = 0;
      const selectionCell = document.createElement("td");
      selectionCell.className = "selection-column";
      const checkbox = document.createElement("input");
      checkbox.type = "checkbox";
      checkbox.checked = state.selectedIndexes.has(index);
      checkbox.setAttribute("aria-label", `Select row ${index + 1}`);
      checkbox.addEventListener("click", (event) => event.stopPropagation());
      checkbox.addEventListener("change", () => {
        if (checkbox.checked) state.selectedIndexes.add(index);
        else state.selectedIndexes.delete(index);
        renderSelectionActions(pageRows);
      });
      selectionCell.appendChild(checkbox);
      tr.appendChild(selectionCell);
      const number = document.createElement("td");
      number.className = "row-number";
      number.textContent = String(index + 1);
      tr.appendChild(number);
      columns.forEach((column) => {
        const cell = document.createElement("td");
        const value = row[column];
        cell.textContent = displayValue(value);
        cell.title = displayValue(value);
        if (value === null || value === undefined) cell.className = "null-value";
        if (value === true) cell.className = "boolean-true";
        if (value === false) cell.className = "boolean-false";
        tr.appendChild(cell);
      });
      const select = async () => {
        state.selectedIndex = index;
        state.selectedRecord = state.view === "snapshot" ? null : row;
        renderTable();
        renderInspector();
        if (state.view === "snapshot") {
          try {
            const selectedDataset = state.activeDataset;
            const record = await loadSnapshotRecord(selectedDataset, index);
            if (state.activeDataset === selectedDataset && state.selectedIndex === index) {
              state.selectedRecord = record;
              renderInspector();
            }
          } catch (error) {
            toast("Could not load full record", error.message, "error");
          }
        }
      };
      tr.addEventListener("click", () => { void select(); });
      tr.addEventListener("keydown", (event) => { if (event.key === "Enter" || event.key === " ") { event.preventDefault(); void select(); } });
      body.appendChild(tr);
    });
    elements.loadingState.hidden = pageRows.length > 0;
    elements.loadingState.textContent = state.view === "change-set" ? "No local records for this dataset." : "No Snapshot rows match this search.";
    elements.dataTable.hidden = pageRows.length === 0;
    elements.rowSummary.textContent = `${rows.length.toLocaleString()} of ${currentRows().length.toLocaleString()} rows`;
    elements.pageLabel.textContent = `Page ${state.page} of ${pages}`;
    elements.previousPage.disabled = state.page <= 1;
    elements.nextPage.disabled = state.page >= pages;
    renderSelectionActions(pageRows);
  }

  function inspectorEmpty() {
    const wrapper = document.createElement("div");
    wrapper.className = "inspector-empty";
    wrapper.append(textNode("span", "⌁"), textNode("strong", "Select a row"), textNode("p", "Inspect its canonical identity and move eligible records into the Change Set."));
    wrapper.firstChild.className = "inspector-glyph";
    return wrapper;
  }

  function renderSelectionActions(pageRows = []) {
    const dataset = state.datasetByName.get(state.activeDataset);
    const schema = state.schemaCache.get(state.activeDataset);
    const eligibleDataset = isChangeEligible(dataset, schema);
    elements.selectionActions.hidden = !eligibleDataset;
    if (!eligibleDataset) return;
    for (const index of [...state.selectedIndexes]) {
      if (!currentRows()[index]) state.selectedIndexes.delete(index);
    }
    const count = state.selectedIndexes.size;
    elements.selectionSummary.textContent = count
      ? `${count.toLocaleString()} row${count === 1 ? "" : "s"} selected`
      : "Select rows for a bulk change";
    elements.selectPageButton.textContent = pageRows.length && pageRows.every(({ index }) => state.selectedIndexes.has(index))
      ? "Unselect page"
      : "Select page";
    elements.clearSelectionButton.disabled = count === 0;
    elements.bulkEditButton.hidden = count === 0;
    elements.bulkEditButton.textContent = `Edit one field (${count})`;
    elements.bulkDeactivateButton.hidden = count === 0 || !modelStatusField(schema);
    elements.bulkDeactivateButton.textContent = `Deactivate (${count})`;
  }

  function pageRowIndexes() {
    const rows = filteredRows();
    return rows.slice((state.page - 1) * PAGE_SIZE, state.page * PAGE_SIZE).map(({ index }) => index);
  }

  function togglePageSelection() {
    const indexes = pageRowIndexes();
    const allSelected = indexes.length > 0 && indexes.every((index) => state.selectedIndexes.has(index));
    indexes.forEach((index) => {
      if (allSelected) state.selectedIndexes.delete(index);
      else state.selectedIndexes.add(index);
    });
    renderTable();
  }

  async function selectedFullRecords() {
    const indexes = [...state.selectedIndexes].sort((left, right) => left - right);
    if (state.view === "change-set") {
      return indexes.map((index) => currentRows()[index]).filter(Boolean).map(logic.clone);
    }
    const records = [];
    for (const index of indexes) {
      const record = await loadSnapshotRecord(state.activeDataset, index);
      if (record) records.push(logic.clone(record));
    }
    return records;
  }

  async function applyBulkField(field, value) {
    const schema = await loadSchema(state.activeDataset);
    if (!Object.prototype.hasOwnProperty.call(schema.properties || {}, field)) throw new Error(`${field} is not a dataset field.`);
    if (logic.canonicalColumns(schema).includes(field)) throw new Error("Canonical-key fields cannot be bulk edited.");
    if (Object.prototype.hasOwnProperty.call(schema.properties[field], "const")) throw new Error(`${field} is fixed by this dataset.`);
    const selected = await selectedFullRecords();
    if (!selected.length) throw new Error("Select at least one row.");
    const entry = await loadChangeRows(state.activeDataset);
    const proposed = selected.flatMap((baseline) => {
      const pending = entry.rows.find((record) => sameNaturalKey(record, baseline, schema));
      const base = pending ? logic.clone(pending) : baseline;
      if (JSON.stringify(base[field]) === JSON.stringify(value)) return [];
      return [{ ...base, [field]: logic.clone(value) }];
    });
    if (!proposed.length) throw new Error("The selected records already have that value.");
    const result = logic.mergeRecords(entry.rows, proposed, schema, state.activeDataset);
    if (result.errors.length) throw new Error(result.errors[0].message || "Bulk change does not match the dataset schema.");
    await ensureWritableDraft();
    entry.rows = result.rows;
    entry.errors = [];
    entry.dirty = true;
    state.pendingCounts.set(state.activeDataset, entry.rows.length);
    state.selectedIndexes.clear();
    renderDatasetNav();
    renderWorkspace();
    toast("Bulk change prepared", `${proposed.length} ${state.activeDataset} record${proposed.length === 1 ? "" : "s"} updated locally. Save when ready.`, "success");
  }

  async function editSelectedField() {
    const schema = state.schemaCache.get(state.activeDataset);
    const blocked = new Set(logic.canonicalColumns(schema));
    const fields = Object.entries(schema.properties || {})
      .filter(([name, property]) => !blocked.has(name) && !Object.prototype.hasOwnProperty.call(property, "const"))
      .map(([name]) => name);
    const field = window.prompt(`Field to update:\n${fields.join(", ")}`);
    if (field === null) return;
    if (!fields.includes(field)) {
      toast("Bulk edit stopped", "Choose one exact editable field name from the list.", "error");
      return;
    }
    const raw = window.prompt(`JSON value for ${field} (strings need quotes; null is allowed only when the schema allows it):`);
    if (raw === null) return;
    try {
      const value = logic.parseJson(raw, field);
      if (!window.confirm(`Set ${field}=${displayValue(value)} on ${state.selectedIndexes.size} selected record${state.selectedIndexes.size === 1 ? "" : "s"}?`)) return;
      await applyBulkField(field, value);
    } catch (error) {
      toast("Bulk edit stopped", error.message, "error");
    }
  }

  async function deactivateSelectedRecords() {
    const count = state.selectedIndexes.size;
    const schema = state.schemaCache.get(state.activeDataset);
    const field = modelStatusField(schema);
    if (!field) return;
    const value = field === "is_active" ? false : "inactive";
    if (!count || !window.confirm(`Set ${field}=${displayValue(value)} for ${count} selected record${count === 1 ? "" : "s"}?`)) return;
    try { await applyBulkField(field, value); }
    catch (error) { toast("Bulk deactivation stopped", error.message, "error"); }
  }

  function renderInspector() {
    elements.inspector.replaceChildren();
    const record = state.selectedIndex === null ? null : state.selectedRecord;
    const schema = state.schemaCache.get(state.activeDataset);
    const dataset = state.datasetByName.get(state.activeDataset);
    if (!record || !schema || !dataset) { elements.inspector.appendChild(inspectorEmpty()); return; }

    const identity = document.createElement("section");
    identity.className = "inspector-section";
    const canonical = logic.canonicalColumns(schema);
    identity.appendChild(labelNode(canonical.length ? "Canonical key" : "Singleton dataset"));
    const keys = document.createElement("dl");
    keys.className = "key-list";
    canonical.forEach((field) => {
      const group = document.createElement("div");
      group.append(textNode("dt", field), textNode("dd", displayValue(record[field])));
      keys.appendChild(group);
    });
    identity.appendChild(keys);
    elements.inspector.appendChild(identity);

    const action = document.createElement("section");
    action.className = "inspector-section";
    action.appendChild(labelNode(state.view === "snapshot" ? "Move to Change Set" : "Local draft action"));
    const actionArea = document.createElement("div");
    actionArea.className = "inspector-actions";
    if (state.view === "snapshot") {
      if (isChangeEligible(dataset, schema)) {
        const add = actionButton("Create change", "button change-action", openSelectedSnapshotChange);
        actionArea.append(add, paragraph("Edit a proposed copy beside the immutable current record."));
      } else {
        actionArea.append(paragraph("This record is available for context only. It cannot enter this Change Set."));
      }
    } else {
      const base = state.snapshotCache.get(state.activeDataset) || [];
      const classification = textNode("span", logic.classifyRecord(record, base, schema).replace("_", " "));
      classification.className = "action-tag";
        actionArea.append(classification, actionButton("Edit proposed record", "button change-action", () => { void openRecordDialog("edit", state.selectedIndex); }), actionButton("Remove from local draft", "button quiet", removeSelectedLocalRecord));
    }
    action.appendChild(actionArea);
    elements.inspector.appendChild(action);

    const relations = document.createElement("section");
    relations.className = "inspector-section";
    relations.appendChild(labelNode("References"));
    const references = schema["x-gds-references"] || [];
    if (!references.length) relations.appendChild(paragraph("No parent references declared."));
    references.forEach((reference) => {
      const node = document.createElement("p");
      node.className = "relation";
      node.append(textNode("strong", reference.target_record_type), textNode("span", `${reference.columns.join(" + ")} → ${reference.target_columns.join(" + ")}${reference.nullable ? " · optional" : ""}`));
      relations.appendChild(node);
    });
    elements.inspector.appendChild(relations);
  }

  function labelNode(text) { const node = textNode("div", text); node.className = "inspector-label"; return node; }
  function paragraph(text) { const node = textNode("p", text); node.className = "inspector-copy"; return node; }
  function actionButton(text, className, handler) { const node = textNode("button", text); node.type = "button"; node.className = className; node.addEventListener("click", handler); return node; }

  function sameNaturalKey(left, right, schema) {
    return logic.canonicalColumns(schema).every((field) =>
      logic.normalizeKeyValue(field, left?.[field], schema) ===
      logic.normalizeKeyValue(field, right?.[field], schema)
    );
  }

  async function openSelectedSnapshotChange() {
    const baseline = state.selectedRecord;
    if (!baseline) return;
    try {
      const entry = await loadChangeRows(state.activeDataset);
      const schema = await loadSchema(state.activeDataset);
      const pendingIndex = entry.rows.findIndex((record) => sameNaturalKey(record, baseline, schema));
      await openRecordDialog("snapshot-edit", pendingIndex, baseline);
    } catch (error) {
      toast("Could not prepare change", error.message, "error");
    }
  }

  function removeSelectedLocalRecord() {
    const entry = state.changeCache.get(state.activeDataset);
    const record = entry?.rows[state.selectedIndex];
    if (!record || !window.confirm(`Remove this record from the local draft? This does not delete the applied ${state.profile.kind}.`)) return;
    try {
      const schema = state.schemaCache.get(state.activeDataset);
      const key = Object.fromEntries(logic.canonicalColumns(schema).map((field) => [field, record[field]]));
      entry.rows = logic.removeRecord(entry.rows, key, schema, state.activeDataset);
      entry.errors = logic.validateDataset(entry.rows, schema);
      entry.dirty = true;
      state.pendingCounts.set(state.activeDataset, entry.rows.length);
      state.selectedIndex = null;
      renderDatasetNav(); renderWorkspace();
      toast("Removed from local draft", `The applied ${state.profile.kind} was not changed.`, "success");
    } catch (error) { toast("Could not remove record", error.message, "error"); }
  }

  function propertyTypes(property) {
    const candidates = Array.isArray(property.anyOf) ? property.anyOf : [property];
    return candidates.map((candidate) => candidate.type).filter(Boolean);
  }

  function propertyChoices(property) {
    const choices = [];
    const candidates = Array.isArray(property.anyOf) ? property.anyOf : [property];
    for (const candidate of candidates) {
      if (Object.prototype.hasOwnProperty.call(candidate || {}, "const")) choices.push(candidate.const);
      else if (Array.isArray(candidate?.enum)) choices.push(...candidate.enum);
    }
    return choices;
  }

  function suggestedRecord(schema) {
    const result = {};
    for (const [field, property] of Object.entries(schema.properties || {})) {
      const types = propertyTypes(property);
      if (Object.prototype.hasOwnProperty.call(property, "const")) result[field] = logic.clone(property.const);
      else if (Object.prototype.hasOwnProperty.call(property, "default")) result[field] = logic.clone(property.default);
      else if (types.includes("null")) result[field] = null;
      else if (propertyChoices(property).length) result[field] = logic.clone(propertyChoices(property)[0]);
      else if (types.includes("boolean")) result[field] = field === "is_active";
      else if (types.includes("integer") || types.includes("number")) result[field] = 0;
      else if (types.includes("array")) result[field] = [];
      else if (types.includes("object")) result[field] = {};
      else result[field] = "";
    }
    return result;
  }

  async function loadReferenceSuggestions(schema) {
    const suggestions = new Map();
    for (const reference of schema["x-gds-references"] || []) {
      const parents = state.datasets.filter((dataset) => dataset.record_type === reference.target_record_type);
      for (const parent of parents) {
        const rows = await loadSnapshotSearchRows(parent.name);
        reference.columns.forEach((field, columnIndex) => {
          const targetField = reference.target_columns[columnIndex];
          const values = suggestions.get(field) || new Set();
          for (const row of rows) {
            if (row[targetField] !== undefined && row[targetField] !== null && values.size < 500) values.add(String(row[targetField]));
          }
          suggestions.set(field, values);
        });
      }
    }
    return new Map([...suggestions].map(([field, values]) => [field, [...values].sort()]));
  }

  async function openRecordDialog(mode, index = null, suppliedBaseline = null) {
    const schema = state.schemaCache.get(state.activeDataset);
    const entry = state.changeCache.get(state.activeDataset);
    if (!schema || !entry) return;
    state.formMode = mode; state.formIndex = index;
    let record;
    if (mode === "snapshot-edit") {
      state.formBaseline = logic.clone(suppliedBaseline);
      record = index === null || index < 0
        ? logic.clone(suppliedBaseline)
        : logic.clone(entry.rows[index]);
    } else if (mode === "edit") {
      record = logic.clone(entry.rows[index]);
      const snapshotRows = state.snapshotCache.get(state.activeDataset) || [];
      state.formBaseline = logic.clone(
        snapshotRows.find((candidate) => sameNaturalKey(candidate, record, schema)) || null
      );
    } else {
      record = suggestedRecord(schema);
      state.formBaseline = null;
    }
    state.formOriginalRecord = logic.clone(record);
    try { state.referenceSuggestions = await loadReferenceSuggestions(schema); }
    catch (error) {
      state.referenceSuggestions = new Map();
      toast("Reference suggestions unavailable", error.message, "warning");
    }
    elements.dialogKicker.textContent = state.activeDataset;
    elements.dialogTitle.textContent = mode === "add" ? "Add new record" : "Review proposed change";
    elements.recordSubmitButton.textContent = mode === "add" ? "Add to Change Set" : "Save proposed change";
    elements.formErrors.hidden = true;
    elements.formErrors.textContent = "";
    elements.fieldGrid.replaceChildren();
    const keyFields = new Set(logic.canonicalColumns(schema));
    Object.entries(schema.properties || {}).forEach(([field, property]) => elements.fieldGrid.appendChild(
      buildField(
        field,
        property,
        record[field],
        (schema.required || []).includes(field),
        mode !== "add" && keyFields.has(field)
      )
    ));
    renderFormDiff(record, schema);
    elements.recordDialog.showModal();
  }

  function buildField(name, property, value, required, keyLocked) {
    const wrapper = document.createElement("div");
    const types = propertyTypes(property);
    const wide = types.some((type) => ["object", "array"].includes(type)) || /description|transformation|expression/i.test(name);
    wrapper.className = `field${wide ? " wide" : ""}`;
    wrapper.dataset.fieldWrapper = name;
    const label = document.createElement("label");
    label.className = "field-label";
    label.htmlFor = `field-${name}`;
    const title = document.createElement("span");
    title.textContent = `${property.title || name}${required ? " *" : ""}`;
    if (required) title.className = "required-mark";
    const type = document.createElement("code");
    type.textContent = types.join(" | ") || "value";
    label.append(title, type);
    let control;
    const declaredChoices = propertyChoices(property);
    if (declaredChoices.length || Object.prototype.hasOwnProperty.call(property, "const") || (types.includes("boolean") && types.every((item) => item === "boolean" || item === "null"))) {
      control = document.createElement("select");
      const choices = Object.prototype.hasOwnProperty.call(property, "const") ? [property.const] : declaredChoices.length ? declaredChoices : [true, false];
      if (types.includes("null")) control.appendChild(optionNode("__GDS_NULL__", "null", value === null));
      choices.forEach((choice) => control.appendChild(optionNode(JSON.stringify(choice), String(choice), value === choice)));
    } else if (types.some((item) => item === "object" || item === "array")) {
      control = document.createElement("textarea");
      control.value = value === null ? "null" : JSON.stringify(value, null, 2);
      control.spellcheck = false;
    } else {
      control = document.createElement(wide ? "textarea" : "input");
      if (control.tagName === "INPUT") control.type = types.includes("integer") || types.includes("number") ? "number" : "text";
      if (control.tagName === "INPUT" && types.includes("integer")) control.step = "1";
      control.value = value === null ? "" : String(value ?? "");
      control.dataset.nullable = String(types.includes("null"));
    }
    control.dataset.field = name;
    control.dataset.types = types.join(",");
    control.dataset.nullable = String(types.includes("null"));
    control.id = `field-${name}`;
    if (Object.prototype.hasOwnProperty.call(property, "const") || keyLocked) control.disabled = true;
    const help = document.createElement("span");
    help.className = "field-help";
    help.textContent = keyLocked
      ? "Canonical-key field; create a new record to use another value."
      : property.description || (Object.prototype.hasOwnProperty.call(property, "const") ? "Fixed by this dataset." : required ? "Required field." : "Optional field.");
    wrapper.append(label, control);
    const suggestions = state.referenceSuggestions.get(name) || [];
    if (suggestions.length && control.tagName === "INPUT" && control.type === "text") {
      const list = document.createElement("datalist");
      list.id = `suggestions-${name}`;
      suggestions.forEach((suggestion) => list.appendChild(optionNode(suggestion, suggestion, false)));
      control.setAttribute("list", list.id);
      wrapper.appendChild(list);
    }
    if (types.includes("null") && control.tagName !== "SELECT" && !types.some((typeName) => typeName === "object" || typeName === "array")) {
      const nullChoice = document.createElement("label");
      nullChoice.className = "null-choice";
      const checkbox = document.createElement("input");
      checkbox.type = "checkbox";
      checkbox.checked = value === null;
      checkbox.disabled = keyLocked || Object.prototype.hasOwnProperty.call(property, "const");
      const applyNullState = () => {
        control.dataset.nullSelected = String(checkbox.checked);
        control.disabled = checkbox.checked || keyLocked || Object.prototype.hasOwnProperty.call(property, "const");
      };
      checkbox.addEventListener("change", applyNullState);
      applyNullState();
      nullChoice.append(checkbox, document.createTextNode("Use null"));
      wrapper.appendChild(nullChoice);
    }
    wrapper.appendChild(help);
    return wrapper;
  }

  function optionNode(value, label, selected) { const option = document.createElement("option"); option.value = value; option.textContent = label; option.selected = selected; return option; }

  function readFormRecord(schema) {
    const record = {};
    for (const control of elements.fieldGrid.querySelectorAll("[data-field]")) {
      const name = control.dataset.field;
      const property = schema.properties[name];
      const types = propertyTypes(property);
      if (Object.prototype.hasOwnProperty.call(property, "const")) { record[name] = logic.clone(property.const); continue; }
      if (control.dataset.nullSelected === "true") {
        record[name] = null;
      } else if (control.tagName === "SELECT") {
        record[name] = control.value === "__GDS_NULL__" ? null : JSON.parse(control.value);
      } else if (types.some((type) => type === "object" || type === "array")) {
        record[name] = logic.parseJson(control.value, name);
      } else if (types.includes("integer")) {
        record[name] = Number(control.value);
      } else if (types.includes("number")) {
        record[name] = Number(control.value);
      } else {
        record[name] = control.value;
      }
    }
    return record;
  }

  function renderFormDiff(record, schema) {
    const diff = logic.diffRecord(record, state.formBaseline, schema);
    elements.diffPreview.replaceChildren();
    const summary = document.createElement("strong");
    summary.textContent = diff.action === "no_change"
      ? "No values changed yet."
      : diff.action === "insert"
        ? "New record"
        : `${diff.action.replace("_", " ")} · ${diff.changes.length} changed field${diff.changes.length === 1 ? "" : "s"}`;
    elements.diffPreview.appendChild(summary);
    diff.changes.slice(0, 12).forEach((change) => {
      const line = document.createElement("div");
      line.append(
        textNode("code", change.field),
        document.createTextNode(`  ${displayValue(change.before)} → ${displayValue(change.after)}`)
      );
      elements.diffPreview.appendChild(line);
    });
    if (diff.changes.length > 12) elements.diffPreview.appendChild(paragraph(`${diff.changes.length - 12} more changed fields`));
    elements.recordSubmitButton.disabled = state.formMode !== "add" && diff.action === "no_change";
    return diff;
  }

  function showFormErrors(errors) {
    elements.formErrors.hidden = errors.length === 0;
    elements.formErrors.textContent = errors.length
      ? `${errors.length} issue${errors.length === 1 ? "" : "s"}: ${errors.slice(0, 3).map((error) => error.message).join(" ")}`
      : "";
    elements.fieldGrid.querySelectorAll("[data-field-wrapper]").forEach((wrapper) => {
      const field = wrapper.dataset.fieldWrapper;
      const error = errors.find((issue) => issue.field === field || issue.field === `$.${field}` || issue.field?.startsWith(`${field}.`) || issue.field?.startsWith(`${field}[`) || issue.field?.startsWith(`$.${field}.`) || issue.field?.startsWith(`$.${field}[`));
      wrapper.classList.toggle("invalid", Boolean(error));
      if (error) $(".field-help", wrapper).textContent = error.message;
    });
  }

  async function submitRecordForm(event) {
    event.preventDefault();
    if (event.submitter !== elements.recordSubmitButton) { elements.recordDialog.close(); return; }
    const schema = state.schemaCache.get(state.activeDataset);
    const entry = state.changeCache.get(state.activeDataset);
    try {
      const record = readFormRecord(schema);
      if (state.formMode !== "add" && !sameNaturalKey(record, state.formOriginalRecord, schema)) {
        showFormErrors([{ field: "$", message: "Canonical-key fields cannot change during an update. Add a new record instead." }]);
        return;
      }
      const diff = renderFormDiff(record, schema);
      if (diff.action === "no_change") {
        showFormErrors([{ field: "$", message: "Nothing changed. Close this dialog or remove the existing pending record." }]);
        return;
      }
      if (state.formMode === "add") {
        const snapshotRows = state.snapshotCache.get(state.activeDataset) || [];
        if (snapshotRows.some((candidate) => sameNaturalKey(candidate, record, schema))) {
          showFormErrors([{ field: "$", message: "That natural key already exists in the Snapshot. Select it there and choose Create change." }]);
          return;
        }
      }
      let result;
      if (state.formMode === "edit") {
        const next = logic.clone(entry.rows);
        next[state.formIndex] = record;
        const errors = logic.validateDataset(next, schema);
        result = errors.length ? { action: "rejected", errors } : { action: "updated", rows: next, index: state.formIndex, errors: [] };
      } else {
        result = logic.mergeRecord(entry.rows, record, schema, state.activeDataset);
      }
      if (result.errors.length) { showFormErrors(result.errors); return; }
      await ensureWritableDraft();
      entry.rows = result.rows; entry.errors = logic.validateDataset(entry.rows, schema); entry.dirty = true;
      state.pendingCounts.set(state.activeDataset, entry.rows.length);
      state.selectedIndex = result.index;
      state.selectedRecord = entry.rows[result.index];
      elements.recordDialog.close();
      renderDatasetNav(); renderWorkspace();
      toast("Local record updated", `${state.activeDataset} · ${result.action} · save when ready.`, "success");
    } catch (error) {
      showFormErrors([{ field: "$", message: error.message }]);
      elements.formErrors.textContent = error.message;
    }
  }

  function updateSaveButton() {
    const dirty = [...state.changeCache.values()].filter((entry) => entry.dirty).length;
    elements.saveButton.disabled = dirty === 0;
    elements.saveButton.textContent = dirty ? `Save Change Set (${dirty})` : "Save Change Set";
    updateReviewStrip();
  }

  function localDatasetNames() {
    const loaded = [...state.changeCache.entries()]
      .filter(([, entry]) => entry.fileHandle || entry.dirty)
      .map(([name]) => name);
    return [...new Set([...state.pendingCounts.keys(), ...loaded])].sort();
  }

  function updateReviewStrip() {
    if (!state.manifest) return;
    const names = localDatasetNames();
    const dirtyCount = [...state.changeCache.values()].filter((entry) => entry.dirty).length;
    const recordCount = names.reduce((total, name) => total + (state.pendingCounts.get(name) || 0), 0);
    if (!state.changeSetHandle && !names.length) {
      elements.reviewTitle.textContent = "No local draft";
      elements.reviewSummary.textContent = "Browse the verified Snapshot. A draft is created only after your first accepted edit.";
      elements.reviewButton.disabled = true;
      return;
    }
    elements.reviewTitle.textContent = dirtyCount ? `${dirtyCount} unsaved dataset${dirtyCount === 1 ? "" : "s"}` : "Local draft saved";
    elements.reviewSummary.textContent = `${names.length} dataset${names.length === 1 ? "" : "s"} · ${recordCount.toLocaleString()} record${recordCount === 1 ? "" : "s"} · not Staged`;
    elements.reviewButton.disabled = names.length === 0;
  }

  async function saveChanges() {
    const dirtyEntries = [...state.changeCache.entries()].filter(([, entry]) => entry.dirty);
    if (!dirtyEntries.length || state.busy) return;
    setBusy(true, "Saving local Change Set…");
    try {
      await ensureWritableDraft();
      const plan = [];
      for (const [datasetName, entry] of dirtyEntries) {
        const schema = await loadSchema(datasetName);
        const errors = logic.validateDataset(entry.rows, schema);
        if (errors.length) throw new Error(`${datasetName} has ${errors.length} schema or uniqueness issues.`);
        const serialized = logic.serializeDataset(entry.rows);
        if (entry.fileHandle) {
          const current = await (await entry.fileHandle.getFile()).text();
          if (entry.sourceText !== current) throw new Error(`${datasetName}.json changed outside the Workbench. Reload files before saving.`);
        } else {
          const appeared = await tryFile(state.datasetsHandle, `${datasetName}.json`);
          if (appeared) throw new Error(`${datasetName}.json was created outside the Workbench. Reload files before saving.`);
        }
        plan.push({ datasetName, entry, content: serialized.content });
      }

      const saved = [];
      for (const item of plan) {
        try {
          const handle = item.entry.fileHandle || await state.datasetsHandle.getFileHandle(`${item.datasetName}.json`, { create: true });
          await writeFileText(handle, item.content);
          item.entry.fileHandle = handle;
          item.entry.sourceText = item.content;
          item.entry.dirty = false;
          item.entry.errors = [];
          saved.push(item.datasetName);
        } catch (_error) {
          const prefix = saved.length ? `${saved.join(", ")} saved; ` : "No dataset saved; ";
          throw new Error(`${prefix}${item.datasetName} failed. Reload files before retrying.`);
        }
      }
      updateSaveButton(); renderDatasetNav(); updateReviewStrip();
      toast("Local Change Set saved", `${dirtyEntries.length} dataset file${dirtyEntries.length === 1 ? "" : "s"} written. Nothing was Staged or Applied.`, "success");
    } catch (error) { toast("Save stopped", error.message, "error"); }
    finally { setBusy(false); renderWorkspace(); }
  }

  async function buildLocalReview() {
    const datasets = [];
    const totals = { insert: 0, update: 0, deactivate: 0, reactivate: 0, no_change: 0 };
    for (const name of localDatasetNames()) {
      const entry = await loadChangeRows(name);
      const schema = await loadSchema(name);
      const snapshotRows = await loadSnapshotRows(name);
      const errors = logic.validateDataset(entry.rows, schema);
      let bytes = 0;
      let digest = null;
      try {
        const serialized = logic.serializeDataset(entry.rows);
        bytes = serialized.bytes;
        digest = await sha256(new TextEncoder().encode(serialized.content));
      } catch (error) {
        errors.push({ field: "$", message: error.message });
      }
      const actions = { insert: 0, update: 0, deactivate: 0, reactivate: 0, no_change: 0 };
      entry.rows.forEach((record) => {
        const action = logic.classifyRecord(record, snapshotRows, schema);
        actions[action] += 1;
        totals[action] += 1;
      });
      datasets.push({ name, recordCount: entry.rows.length, dirty: entry.dirty, errors, bytes, digest, actions });
    }
    return { datasets, totals };
  }

  function receiptText(review) {
    const server = state.localControl.server_change_set;
    const isModel = state.profile.kind === "model";
    const serverId = server[state.profile.serverIdField] || "unbound";
    const lines = [
      `GDS local ${isModel ? "Model" : "Metadata"} Change Set handoff`,
      isModel
        ? `Model: ${state.manifest.model_name} (ID ${state.manifest.model_id}; baseline revision ${state.manifest.model_revision})`
        : `Tenant: ${state.manifest.tenant_code}`,
      `Snapshot ID: ${state.manifest.snapshot_id}`,
      `Server Change Set: ${serverId}`,
      `Draft revision: ${server.draft_revision ?? "unbound"}`,
      "Status: local files saved; not Staged, not server-validated, not Applied",
      "Datasets:"
    ];
    review.datasets.forEach((dataset) => {
      lines.push(
        `- ${dataset.name}: ${dataset.recordCount} records; insert ${dataset.actions.insert}; update ${dataset.actions.update}; deactivate ${dataset.actions.deactivate}; reactivate ${dataset.actions.reactivate}; sha256 ${dataset.digest}`
      );
    });
    lines.push(isModel
      ? "Next: use the governed model workflow for Tenant Lock, server Model Change Set, Stage, validation, authoritative action review, and separate Apply approval."
      : "Next: use the manage-gds-metadata workflow for lock, server Change Set, Stage, validation, authoritative action review, and separate Apply approval.");
    return lines.join("\n");
  }

  async function pendingModelDatasets() {
    const pending = new Map();
    for (const name of localDatasetNames()) {
      pending.set(name, logic.clone((await loadChangeRows(name)).rows));
    }
    return pending;
  }

  function appendModelStagePreview(pending) {
    const documentValue = logic.modelStageDocument(state.manifest, state.localControl, pending);
    state.modelStageText = logic.serializeJsonDocument(documentValue).content;
    const bound = documentValue.model_change_set_id !== null && documentValue.expected_draft_revision !== null;
    const details = document.createElement("details");
    details.className = "schema-block";
    const summary = document.createElement("summary");
    summary.textContent = bound ? "Preview bound Model Stage JSON" : "Preview local Model Stage template";
    const explanation = paragraph(!bound
      ? "This is an unbound local payload. Bind a server Model Change Set and revision before Stage."
      : `Bound to server draft revision ${documentValue.expected_draft_revision}. Server validation remains authoritative.`);
    const previewLimit = 200000;
    const preview = codeBlock(state.modelStageText.length > previewLimit
      ? `${state.modelStageText.slice(0, previewLimit)}\n… preview truncated; copy to inspect the complete local payload.`
      : state.modelStageText);
    const copy = actionButton(bound ? "Copy bound Stage JSON" : "Copy local Stage template", "button quiet small", () => {
      void copyText(state.modelStageText, bound ? "Stage JSON copied" : "Stage template copied", `${bound ? "The bound" : "The unbound"} local Model Stage payload was copied. It was not Staged.`);
    });
    details.append(summary, explanation, preview, copy);
    elements.reviewContent.appendChild(details);
  }

  async function openReview() {
    if (!localDatasetNames().length) return;
    elements.reviewButton.disabled = true;
    try {
      const review = await buildLocalReview();
      elements.reviewContent.replaceChildren();
      const errorCount = review.datasets.reduce((total, dataset) => total + dataset.errors.length, 0);
      const dirtyCount = review.datasets.filter((dataset) => dataset.dirty).length;
      const effectiveCount = review.totals.insert + review.totals.update + review.totals.deactivate + review.totals.reactivate;
      const overview = document.createElement("p");
      overview.className = "review-overview";
      overview.textContent = `${review.datasets.length} dataset${review.datasets.length === 1 ? "" : "s"} · ${effectiveCount} effective local change${effectiveCount === 1 ? "" : "s"} · not Staged`;
      elements.reviewContent.appendChild(overview);
      review.datasets.forEach((dataset) => {
        const node = document.createElement("section");
        node.className = "review-dataset";
        node.append(
          textNode("strong", dataset.name),
          textNode("span", `${dataset.recordCount} records · ${dataset.bytes.toLocaleString()} bytes${dataset.dirty ? " · unsaved" : " · saved"}`),
          textNode("span", `insert ${dataset.actions.insert} · update ${dataset.actions.update} · deactivate ${dataset.actions.deactivate} · reactivate ${dataset.actions.reactivate} · no change ${dataset.actions.no_change}`),
          textNode("span", dataset.errors.length ? `${dataset.errors.length} validation issue${dataset.errors.length === 1 ? "" : "s"}` : `sha256 ${dataset.digest}`)
        );
        elements.reviewContent.appendChild(node);
      });
      if (state.profile.kind === "model") appendModelStagePreview(await pendingModelDatasets());
      const ready = dirtyCount === 0 && errorCount === 0 && review.totals.no_change === 0 && effectiveCount > 0;
      if (!ready) {
        const warning = document.createElement("p");
        warning.className = "review-warning";
        warning.textContent = dirtyCount
          ? "Save every dataset before handoff."
          : errorCount
            ? "Fix every local validation issue before handoff."
            : review.totals.no_change
              ? "Remove unchanged pending records before handoff."
              : `No effective ${state.profile.kind} change is present.`;
        elements.reviewContent.appendChild(warning);
      }
      state.handoffText = ready ? receiptText(review) : "";
      elements.copyHandoffButton.disabled = !ready;
      elements.reviewDialog.showModal();
    } catch (error) {
      toast("Review could not be built", error.message, "error");
    } finally {
      updateReviewStrip();
    }
  }

  async function copyHandoff() {
    if (!state.handoffText) return;
    await copyText(state.handoffText, "Handoff copied", "Only counts, hashes, IDs, and workflow status were copied; row values were excluded.");
  }

  async function copyText(value, title, successMessage) {
    if (!value) return;
    try {
      await navigator.clipboard.writeText(value);
      toast(title, successMessage, "success");
    } catch (_error) {
      toast("Copy unavailable", "Copy the review manually from this local dialog.", "error");
    }
  }

  async function proposedModelDatasets() {
    const datasets = new Map();
    for (const name of logic.MODEL_DATASETS) {
      if (!state.datasetByName.has(name)) throw new Error(`Model Snapshot Catalog is missing ${name}.`);
      const schema = await loadSchema(name);
      const baseline = await loadSnapshotRows(name);
      const hasPending = state.pendingCounts.has(name) || state.changeCache.get(name)?.dirty || state.changeCache.get(name)?.fileHandle;
      const rows = hasPending
        ? logic.overlayDataset(baseline, (await loadChangeRows(name)).rows, schema)
        : logic.clone(baseline);
      const errors = logic.validateDataset(rows, schema);
      if (errors.length) throw new Error(`${name}: ${errors[0].message}`);
      datasets.set(name, rows);
    }
    return datasets;
  }

  async function exportProposedModelSnapshot() {
    if (state.profile?.kind !== "model" || state.busy) return;
    const includesUnsaved = hasDirtyChanges();
    const warning = includesUnsaved
      ? "Create a proposed Model Snapshot JSON from the verified baseline plus saved and unsaved local edits? It is not an authoritative server Snapshot."
      : "Create a proposed Model Snapshot JSON from the verified baseline plus the local Change Set? It is not an authoritative server Snapshot.";
    if (!window.confirm(warning)) return;
    if (!("showSaveFilePicker" in window)) {
      toast("Export unavailable", "Current Chrome or Edge is required to save proposed Model Snapshot JSON.", "error");
      return;
    }
    setBusy(true, "Building proposed Model Snapshot JSON…");
    try {
      const snapshot = logic.modelSnapshotFromDatasets(state.manifest, await proposedModelDatasets());
      logic.modelSnapshotToDatasets(snapshot);
      const serialized = logic.serializeJsonDocument(snapshot);
      const slug = state.manifest.model_name.toLocaleLowerCase("en-US").replace(/[^a-z0-9]+/g, "-").replace(/^-+|-+$/g, "") || "model";
      const handle = await window.showSaveFilePicker({
        suggestedName: `${slug}-proposed-model-snapshot.json`,
        types: [{ description: "JSON document", accept: { "application/json": [".json"] } }]
      });
      await writeFileText(handle, serialized.content);
      toast("Proposed Model Snapshot saved", `${serialized.bytes.toLocaleString()} bytes written locally. Nothing was Staged, validated, or Applied.`, "success");
    } catch (error) {
      if (error.name !== "AbortError") toast("Model Snapshot export stopped", error.message, "error");
    } finally {
      setBusy(false);
      renderWorkspace();
    }
  }

  function showSchema() {
    const schema = state.schemaCache.get(state.activeDataset);
    if (!schema) return;
    elements.schemaDialogTitle.textContent = schema.title || state.activeDataset;
    elements.schemaContent.replaceChildren();
    const overview = schemaSection("Record contract", schema.description || `ID-free GDS ${humanize(state.profile.kind)} record.`);
    overview.appendChild(codeBlock(`Dataset: ${schema["x-gds-dataset"]}\nRecord type: ${schema["x-gds-record-type"]}\nChange Set eligible: ${schema["x-gds-change-set-eligible"]}`));
    elements.schemaContent.appendChild(overview);
    const canonical = logic.canonicalColumns(schema);
    elements.schemaContent.appendChild(schemaSection("Canonical key", canonical.length ? canonical.join(" + ") : "Singleton dataset"));
    const uniques = (schema["x-gds-unique-constraints"] || []).map((group) => group.join(" + ")).join("\n");
    elements.schemaContent.appendChild(schemaSection("Unique constraints", uniques || "None declared"));
    const references = (schema["x-gds-references"] || []).map((reference) => `${reference.columns.join(" + ")} → ${reference.target_record_type} (${reference.target_columns.join(" + ")})${reference.nullable ? " [optional]" : ""}`).join("\n");
    elements.schemaContent.appendChild(schemaSection("References", references || "None declared"));
    const fields = Object.entries(schema.properties || {}).map(([name, property]) => `${name} · ${propertyTypes(property).join(" | ")}${(schema.required || []).includes(name) ? " · required" : ""}${Object.prototype.hasOwnProperty.call(property, "const") ? ` · fixed ${JSON.stringify(property.const)}` : ""}`).join("\n");
    const fieldsSection = schemaSection("Fields", `${Object.keys(schema.properties || {}).length} fields`);
    fieldsSection.appendChild(codeBlock(fields));
    elements.schemaContent.appendChild(fieldsSection);
    elements.schemaDialog.showModal();
  }

  function schemaSection(title, text) { const node = document.createElement("section"); node.className = "schema-block"; node.append(textNode("h3", title), textNode("p", text)); return node; }
  function codeBlock(text) { const node = textNode("pre", text); node.className = "schema-code"; return node; }

  async function reloadFiles() {
    if (hasDirtyChanges() && !window.confirm("Discard unsaved Workbench edits and reload files from disk?")) return;
    const active = state.activeDataset;
    const view = state.view;
    state.schemaCache.clear(); state.snapshotSearchCache.clear();
    state.snapshotTextCache.clear(); state.snapshotCache.clear();
    state.changeCache.clear(); state.pendingCounts.clear(); state.createdChangeSet = false;
    setBusy(true, "Reloading GDS files…");
    try {
      const local = await inspectExistingChangeSet(state.gdsHandle, state.manifest, state.profile, false);
      state.changeSetHandle = local.changeSetHandle;
      state.datasetsHandle = local.datasetsHandle;
      state.localControl = local.localControl;
      state.pendingCounts = local.pendingCounts;
      state.view = view;
      renderDatasetNav();
      if (active) await selectDataset(active);
      toast("Files reloaded", "Snapshot and Change Set caches now match disk.", "success");
    } catch (error) { toast("Reload failed", error.message, "error"); }
    finally { setBusy(false); }
  }

  elements.connectButton.addEventListener("click", () => {
    if (state.manifest && elements.snapshotKindSelect) elements.snapshotKindSelect.value = "auto";
    void connectWorkspace();
  });
  elements.welcomeConnectButton.addEventListener("click", () => { void connectWorkspace(); });
  elements.reloadButton.addEventListener("click", reloadFiles);
  elements.snapshotTab.addEventListener("click", () => switchView("snapshot"));
  elements.changeSetTab.addEventListener("click", () => switchView("change-set"));
  elements.datasetSearch.addEventListener("input", () => { state.datasetQuery = elements.datasetSearch.value; renderDatasetNav(); });
  elements.rowSearch.addEventListener("input", () => { state.query = elements.rowSearch.value; state.page = 1; state.selectedIndex = null; state.selectedRecord = null; renderTable(); renderInspector(); });
  elements.previousPage.addEventListener("click", () => { if (state.page > 1) { state.page--; renderTable(); } });
  elements.nextPage.addEventListener("click", () => { state.page++; renderTable(); });
  elements.selectPageButton.addEventListener("click", togglePageSelection);
  elements.clearSelectionButton.addEventListener("click", () => { state.selectedIndexes.clear(); renderTable(); });
  elements.bulkEditButton.addEventListener("click", () => { void editSelectedField(); });
  elements.bulkDeactivateButton.addEventListener("click", () => { void deactivateSelectedRecords(); });
  elements.newRowButton.addEventListener("click", () => { void openRecordDialog("add"); });
  elements.saveButton.addEventListener("click", saveChanges);
  elements.exportModelSnapshotButton.addEventListener("click", () => { void exportProposedModelSnapshot(); });
  elements.reviewButton.addEventListener("click", () => { void openReview(); });
  elements.copyHandoffButton.addEventListener("click", () => { void copyHandoff(); });
  elements.schemaButton.addEventListener("click", showSchema);
  elements.recordForm.addEventListener("submit", submitRecordForm);
  elements.fieldGrid.addEventListener("input", () => {
    const schema = state.schemaCache.get(state.activeDataset);
    if (!schema || !elements.recordDialog.open) return;
    try { renderFormDiff(readFormRecord(schema), schema); }
    catch (_error) { elements.recordSubmitButton.disabled = true; }
  });
  elements.recordDialog.querySelectorAll("[data-dialog-close]").forEach((button) => {
    button.addEventListener("click", () => elements.recordDialog.close());
  });
  window.addEventListener("beforeunload", (event) => {
    if ([...state.changeCache.values()].some((entry) => entry.dirty)) { event.preventDefault(); event.returnValue = ""; }
  });

  if (!("showDirectoryPicker" in window)) {
    elements.browserNote.textContent = "Direct editing is unavailable in this browser. Open this file in current Chrome or Edge.";
    elements.browserNote.classList.add("unsupported");
  }

  const publicApi = Object.freeze({
    getState: () => state,
    connectWorkspace,
    connectDirectoryHandle: (directoryHandle, snapshotKind) => connectWorkspace({ directoryHandle, snapshotKind }),
    selectDataset,
    switchView,
    exportProposedModelSnapshot
  });
  window.GdsWorkbench = publicApi;
  window.GdsMetadataWorkbench = publicApi;
})();
