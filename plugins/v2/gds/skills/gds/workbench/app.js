(function (root) {
  "use strict";

  const PAGE_SIZE = 50;
  const elements = Object.fromEntries(
    [
      "session-name",
      "task-state",
      "connect-button",
      "refresh-button",
      "snapshot-state",
      "dataset-search",
      "dataset-list",
      "dataset-section",
      "dataset-title",
      "previous-page",
      "next-page",
      "all-groups",
      "page-label",
      "record-filter",
      "preview-label",
      "preview-count",
      "record-preview",
      "pending-digest",
      "pending-editor",
      "copy-visible",
      "discard-button",
      "save-button",
      "validate-button",
      "validation-summary",
      "issue-list",
      "accept-button",
      "override-button",
      "status-message",
      "connection-capability",
      "override-dialog",
      "override-reason",
      "confirm-override",
    ].map((id) => [id, document.getElementById(id)]),
  );

  const state = {
    workspace: null,
    area: "metadata",
    dataset: null,
    loaded: null,
    page: 0,
    preview: "effective",
    allGroups: false,
    validation: null,
    dirty: false,
  };

  function areaModule() {
    return state.area === "metadata" ? root.GDSMetadata : root.GDSModel;
  }

  function setStatus(message, isError) {
    elements["status-message"].textContent = message;
    elements["status-message"].style.color = isError ? "#ffb9b2" : "";
  }

  function showError(error) {
    setStatus(error?.message || String(error), true);
  }

  function currentTask() {
    return state.workspace?.state.tasks.find(
      (task) => task[0] === state.workspace.state.current,
    );
  }

  function updateSessionHeader() {
    if (!state.workspace) return;
    elements["session-name"].textContent = state.workspace.handle.name;
    const task = currentTask();
    elements["task-state"].textContent = task ? `${task[0]} · ${task[3]}` : "no current task";
    const stale = state.workspace.state.stale || [];
    const area = state.workspace.area(state.area);
    const revision = area.manifest?.model_revision;
    elements["snapshot-state"].textContent = stale.includes(state.area)
      ? `${areaModule().label} Snapshot is stale`
      : area.manifest
        ? `${areaModule().label} Snapshot${revision == null ? "" : ` · revision ${revision}`}`
        : `${areaModule().label} Snapshot missing`;
  }

  function enableControls() {
    const connected = Boolean(state.workspace);
    const task = currentTask();
    const stale = Boolean(state.workspace?.state.stale?.includes(state.area));
    const editable = root.GDSUIState.canEdit(
      task,
      state.area,
      state.loaded,
      stale,
      state.dataset,
    );
    const hasSnapshot = Boolean(connected && state.workspace.area(state.area).manifest);
    elements["connect-button"].disabled = state.dirty;
    elements["refresh-button"].disabled = !connected || state.dirty;
    elements["dataset-search"].disabled = !connected;
    elements["record-filter"].disabled = !state.loaded;
    elements["pending-editor"].disabled = !editable;
    elements["copy-visible"].disabled = !editable;
    elements["discard-button"].disabled = !editable || !state.dirty;
    elements["save-button"].disabled = !editable || !state.dirty;
    elements["validate-button"].disabled = !root.GDSUIState.canValidate(
      task,
      state.area,
      hasSnapshot,
      state.dirty,
      stale,
    );
    for (const button of document.querySelectorAll(".area-tab")) {
      button.disabled =
        !connected || state.dirty || !state.workspace.area(button.dataset.area).manifest;
    }
    for (const button of document.querySelectorAll("[data-preview]")) {
      button.disabled = !state.loaded;
    }
  }

  function renderDatasets() {
    elements["dataset-list"].replaceChildren();
    if (!state.workspace) return;
    const filter = elements["dataset-search"].value.trim().toLowerCase();
    const definitions = state.workspace
      .area(state.area)
      .datasets.filter((dataset) => dataset.name.toLowerCase().includes(filter));
    let section = null;
    for (const dataset of definitions) {
      if (dataset.section !== section) {
        section = dataset.section;
        const heading = document.createElement("div");
        heading.className = "dataset-group";
        heading.textContent = section || "Datasets";
        elements["dataset-list"].append(heading);
      }
      const button = document.createElement("button");
      button.className = `dataset-button${dataset.name === state.dataset ? " is-active" : ""}`;
      button.type = "button";
      const name = document.createElement("span");
      name.textContent = dataset.name;
      const count = document.createElement("span");
      count.textContent = String(dataset.row_count);
      button.append(name, count);
      button.disabled = state.dirty;
      button.setAttribute("aria-current", dataset.name === state.dataset ? "true" : "false");
      button.addEventListener("click", () => selectDataset(dataset.name));
      elements["dataset-list"].append(button);
    }
    if (!definitions.length) {
      const empty = document.createElement("p");
      empty.className = "empty-copy";
      empty.textContent = "No matching datasets.";
      elements["dataset-list"].append(empty);
    }
  }

  function filteredRecords() {
    if (!state.loaded) return [];
    const source = state.preview === "snapshot" ? state.loaded.baseline : state.loaded.effective;
    const filter = elements["record-filter"].value.trim().toLowerCase();
    return filter
      ? source.filter((record) => JSON.stringify(record).toLowerCase().includes(filter))
      : source;
  }

  function recordView() {
    const records = filteredRecords();
    const groups = areaModule().reviewGroups?.(state.loaded?.definition, records) || [];
    if (groups.length && !state.allGroups) {
      state.page = Math.min(state.page, groups.length - 1);
      return {
        visible: groups[state.page].records,
        count: records.length,
        label: `${state.page + 1} / ${groups.length} · ${groups[state.page].label}`,
        previousDisabled: state.page === 0,
        nextDisabled: state.page >= groups.length - 1,
        groups,
      };
    }
    if (groups.length) {
      state.page = 0;
      return {
        visible: records,
        count: records.length,
        label: `All · ${groups.length} target${groups.length === 1 ? "" : "s"}`,
        previousDisabled: true,
        nextDisabled: true,
        groups,
      };
    }
    const pages = Math.max(1, Math.ceil(records.length / PAGE_SIZE));
    state.page = Math.min(state.page, pages - 1);
    return {
      visible: records.slice(state.page * PAGE_SIZE, (state.page + 1) * PAGE_SIZE),
      count: records.length,
      label: records.length ? `${state.page + 1} / ${pages}` : "0 / 0",
      previousDisabled: state.page === 0,
      nextDisabled: state.page >= pages - 1,
      groups,
    };
  }

  function renderRecords() {
    const view = recordView();
    elements["record-preview"].textContent = JSON.stringify(view.visible, null, 2);
    elements["preview-count"].textContent = `${view.count} record${view.count === 1 ? "" : "s"}`;
    elements["page-label"].textContent = view.label;
    elements["previous-page"].disabled = view.previousDisabled;
    elements["next-page"].disabled = view.nextDisabled;
    elements["all-groups"].disabled = view.groups.length === 0;
    elements["all-groups"].textContent = state.allGroups ? "One" : "All";
    elements["all-groups"].setAttribute("aria-pressed", state.allGroups ? "true" : "false");
    elements["preview-label"].textContent =
      state.preview === "snapshot" ? "Snapshot records" : "Effective records";
  }

  function clearValidation() {
    state.validation = null;
    elements["validation-summary"].className = "validation-summary is-neutral";
    elements["validation-summary"].textContent = "Validation has not run for this digest.";
    elements["issue-list"].replaceChildren();
    elements["accept-button"].disabled = true;
    elements["override-button"].disabled = true;
  }

  async function selectDataset(name) {
    try {
      root.GDSUIState.requireClean(state.dirty, "opening another dataset");
      state.dataset = name;
      state.page = 0;
      state.allGroups = false;
      state.loaded = await state.workspace.loadDataset(state.area, name);
      elements["dataset-section"].textContent = state.loaded.definition.section || state.area;
      elements["dataset-title"].textContent = name;
      elements["pending-editor"].value = JSON.stringify(state.loaded.pending, null, 2);
      elements["pending-digest"].textContent = state.loaded.pendingDigest || "not created";
      elements["pending-digest"].title = state.loaded.pendingDigest || "";
      state.dirty = false;
      renderDatasets();
      renderRecords();
      clearValidation();
      enableControls();
      setStatus(`Loaded ${name}. Snapshot remains read-only.`);
    } catch (error) {
      showError(error);
    }
  }

  async function switchArea(area) {
    try {
      root.GDSUIState.requireClean(state.dirty, "switching areas");
    } catch (error) {
      showError(error);
      return;
    }
    if (!state.workspace?.area(area).manifest) return;
    state.area = area;
    state.dataset = null;
    state.loaded = null;
    state.page = 0;
    state.allGroups = false;
    state.preview = "effective";
    state.dirty = false;
    document.querySelectorAll(".area-tab").forEach((button) => {
      button.classList.toggle("is-active", button.dataset.area === area);
      button.setAttribute("aria-selected", button.dataset.area === area ? "true" : "false");
    });
    document.querySelectorAll("[data-preview]").forEach((button) => {
      button.classList.toggle("is-active", button.dataset.preview === "effective");
      button.setAttribute(
        "aria-pressed",
        button.dataset.preview === "effective" ? "true" : "false",
      );
    });
    elements["dataset-title"].textContent = `Choose a ${area} dataset`;
    elements["dataset-section"].textContent = areaModule().label;
    elements["pending-editor"].value = "[]";
    elements["record-preview"].textContent = "[]";
    clearValidation();
    renderDatasets();
    updateSessionHeader();
    enableControls();
  }

  async function connectDirectoryHandle(handle) {
    try {
      root.GDSUIState.requireClean(state.dirty, "connecting another session");
      if (handle.queryPermission && (await handle.queryPermission({ mode: "readwrite" })) !== "granted") {
        if ((await handle.requestPermission({ mode: "readwrite" })) !== "granted") {
          throw new Error("Read/write permission to the session folder was not granted.");
        }
      }
      state.workspace = await root.GDSWorkspace.connect(handle);
      const firstArea = state.workspace.area("metadata").manifest
        ? "metadata"
        : state.workspace.area("model").manifest
          ? "model"
          : "metadata";
      await switchArea(firstArea);
      elements["connection-capability"].textContent = "Local directory connected";
      setStatus("Connected. Workbench cannot contact the GDS server.");
    } catch (error) {
      showError(error);
    }
  }

  async function connectFromPicker() {
    if (!root.showDirectoryPicker) {
      showError(new Error("This browser cannot open local directories. Use current Chrome or Edge."));
      return;
    }
    try {
      await connectDirectoryHandle(await root.showDirectoryPicker({ mode: "readwrite" }));
    } catch (error) {
      if (error?.name !== "AbortError") showError(error);
    }
  }

  async function refresh() {
    if (!state.workspace) return;
    const area = state.area;
    const dataset = state.dataset;
    try {
      root.GDSUIState.requireClean(state.dirty, "refreshing");
      await state.workspace.refresh();
      await switchArea(state.workspace.area(area).manifest ? area : "metadata");
      if (dataset && state.workspace.area(state.area).byName.has(dataset)) await selectDataset(dataset);
      setStatus("Refreshed session, Snapshot contracts, and local Change Sets from disk.");
    } catch (error) {
      showError(error);
    }
  }

  function copyVisible() {
    try {
      const pending = JSON.parse(elements["pending-editor"].value);
      if (!Array.isArray(pending)) throw new Error("Local editor must contain a JSON array.");
      const visible = recordView().visible;
      const definition = state.loaded.definition;
      const merged = new Map();
      for (const record of pending) {
        merged.set(root.GDSCore.stableStringify(root.GDSCore.key(state.area, definition, record)), record);
      }
      for (const record of visible) {
        merged.set(root.GDSCore.stableStringify(root.GDSCore.key(state.area, definition, record)), record);
      }
      elements["pending-editor"].value = JSON.stringify([...merged.values()], null, 2);
      clearValidation();
      state.dirty = true;
      renderDatasets();
      enableControls();
      setStatus(`Copied ${visible.length} visible record(s) into the unsaved local draft.`);
    } catch (error) {
      showError(error);
    }
  }

  async function save() {
    try {
      const saved = await state.workspace.saveDataset(
        state.area,
        state.dataset,
        elements["pending-editor"].value,
        state.loaded.pendingDigest,
      );
      state.loaded = await state.workspace.loadDataset(state.area, state.dataset);
      elements["pending-editor"].value = JSON.stringify(state.loaded.pending, null, 2);
      elements["pending-digest"].textContent = saved.pendingDigest;
      elements["pending-digest"].title = saved.pendingDigest;
      state.dirty = false;
      renderRecords();
      renderDatasets();
      clearValidation();
      updateSessionHeader();
      enableControls();
      setStatus("Saved one local dataset atomically. Task returned to review.");
    } catch (error) {
      showError(error);
    }
  }

  async function discard() {
    if (!state.loaded || !state.dataset) return;
    try {
      state.loaded = await state.workspace.loadDataset(state.area, state.dataset);
      elements["pending-editor"].value = JSON.stringify(state.loaded.pending, null, 2);
      elements["pending-digest"].textContent = state.loaded.pendingDigest || "not created";
      elements["pending-digest"].title = state.loaded.pendingDigest || "";
      state.dirty = false;
      renderRecords();
      renderDatasets();
      clearValidation();
      enableControls();
      setStatus("Discarded unsaved editor changes. Local files were not changed.");
    } catch (error) {
      showError(error);
    }
  }

  function issueText(issue) {
    return issue.message || issue.target || issue.endpoint || issue.field || issue.code;
  }

  function renderValidation(validation) {
    elements["validation-summary"].className = `validation-summary ${
      validation.valid ? "is-valid" : "is-invalid"
    }`;
    elements["validation-summary"].textContent = validation.valid
      ? `Local checks passed for digest ${validation.digest.slice(0, 12)}…`
      : `${validation.issues.length} issue(s) for digest ${validation.digest.slice(0, 12)}…`;
    elements["issue-list"].replaceChildren();
    for (const issue of validation.issues.slice(0, 200)) {
      const item = document.createElement("li");
      const code = document.createElement("span");
      code.className = "issue-code";
      code.textContent = issue.code || "validation";
      const message = document.createElement("span");
      message.textContent = issueText(issue);
      const location = document.createElement("span");
      location.className = "issue-location";
      location.textContent = [issue.dataset, issue.record && `record ${issue.record}`]
        .filter(Boolean)
        .join(" · ");
      item.append(code, message, document.createElement("br"), location);
      elements["issue-list"].append(item);
    }
    const review = currentTask()?.[3] === "review";
    elements["accept-button"].disabled = !validation.valid || !review;
    elements["override-button"].disabled = validation.valid || !review;
  }

  async function validate() {
    try {
      root.GDSUIState.requireClean(state.dirty, "validation");
      setStatus(`Validating the effective ${state.area} graph locally…`);
      const loaded = await state.workspace.loadArea(state.area);
      const issues = areaModule().validate(loaded);
      const digest = await state.workspace.changeSetDigest(state.area);
      const snapshot = state.workspace.area(state.area);
      state.validation = {
        area: state.area,
        digest,
        snapshot_id: snapshot.manifest.snapshot_id,
        snapshot_revision: snapshot.manifest.model_revision ?? null,
        snapshot_digest: snapshot.manifestDigest,
        issues,
        valid: issues.length === 0,
      };
      renderValidation(state.validation);
      setStatus(
        state.validation.valid
          ? "Local validation passed. Human acceptance is still required."
          : "Local validation found issues. Nothing was changed.",
      );
    } catch (error) {
      showError(error);
    }
  }

  async function accept(reason) {
    if (!state.validation || state.validation.area !== state.area) return;
    try {
      const result = await state.workspace.accept(
        state.area,
        state.validation.digest,
        state.validation,
        reason,
      );
      updateSessionHeader();
      elements["accept-button"].disabled = true;
      elements["override-button"].disabled = true;
      setStatus(`Local digest accepted as ${result.state}. Server validation remains required.`);
    } catch (error) {
      showError(error);
    }
  }

  elements["connect-button"].addEventListener("click", connectFromPicker);
  elements["refresh-button"].addEventListener("click", refresh);
  elements["dataset-search"].addEventListener("input", renderDatasets);
  elements["record-filter"].addEventListener("input", () => {
    state.page = 0;
    renderRecords();
  });
  elements["previous-page"].addEventListener("click", () => {
    state.page -= 1;
    renderRecords();
  });
  elements["next-page"].addEventListener("click", () => {
    state.page += 1;
    renderRecords();
  });
  elements["all-groups"].addEventListener("click", () => {
    state.allGroups = !state.allGroups;
    state.page = 0;
    renderRecords();
  });
  elements["copy-visible"].addEventListener("click", copyVisible);
  elements["discard-button"].addEventListener("click", discard);
  elements["save-button"].addEventListener("click", save);
  elements["validate-button"].addEventListener("click", validate);
  elements["pending-editor"].addEventListener("input", () => {
    state.dirty = true;
    clearValidation();
    renderDatasets();
    enableControls();
    setStatus("Unsaved draft. Save or discard it before validation or navigation.");
  });
  elements["accept-button"].addEventListener("click", () => accept(null));
  elements["override-button"].addEventListener("click", () => {
    elements["override-reason"].value = "";
    elements["override-dialog"].showModal();
  });
  elements["override-dialog"].addEventListener("close", () => {
    if (elements["override-dialog"].returnValue === "confirm") {
      accept(elements["override-reason"].value);
    }
  });
  document.querySelectorAll(".area-tab").forEach((button) => {
    button.addEventListener("click", () => switchArea(button.dataset.area));
  });
  document.querySelectorAll("[data-preview]").forEach((button) => {
    button.addEventListener("click", () => {
      state.preview = button.dataset.preview;
      state.page = 0;
      document.querySelectorAll("[data-preview]").forEach((item) => {
        item.classList.toggle("is-active", item === button);
        item.setAttribute("aria-pressed", item === button ? "true" : "false");
      });
      renderRecords();
    });
  });

  root.GDSWorkbenchApp = { connectDirectoryHandle, refresh, state };
  enableControls();
})(globalThis);
