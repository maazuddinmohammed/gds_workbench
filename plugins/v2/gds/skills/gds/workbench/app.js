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
      "results-view",
      "json-view",
      "results-table",
      "results-head",
      "results-body",
      "results-empty",
      "add-row-button",
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
      "row-editor-dialog",
      "row-editor-form",
      "row-editor-eyebrow",
      "row-editor-title",
      "row-editor-key",
      "row-editor-fields",
      "row-editor-message",
      "close-row-editor",
      "cancel-row-editor",
      "save-row-editor",
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
    datasetCounts: new Map(),
    view: "results",
    editing: null,
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

  function canEditCurrent() {
    const stale = Boolean(state.workspace?.state.stale?.includes(state.area));
    return root.GDSUIState.canEdit(
      currentTask(),
      state.area,
      state.loaded,
      stale,
      state.dataset,
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
    const editable = canEditCurrent();
    const hasSnapshot = Boolean(connected && state.workspace.area(state.area).manifest);
    elements["connect-button"].disabled = state.dirty;
    elements["refresh-button"].disabled = !connected || state.dirty;
    elements["dataset-search"].disabled = !connected;
    elements["record-filter"].disabled = !state.loaded;
    elements["pending-editor"].disabled = !editable;
    elements["add-row-button"].disabled = !editable || state.preview !== "effective";
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
    for (const button of document.querySelectorAll("[data-view]")) {
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
      const effectiveCount = state.datasetCounts.get(dataset.name);
      count.textContent = String(effectiveCount ?? dataset.row_count);
      count.title =
        effectiveCount == null
          ? `${dataset.row_count} Snapshot rows`
          : `${effectiveCount} effective rows · ${dataset.row_count} Snapshot rows`;
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

  function fieldLabel(field) {
    return field
      .split("_")
      .filter(Boolean)
      .map((word) => word[0].toUpperCase() + word.slice(1))
      .join(" ");
  }

  function recordFields(records) {
    if (!state.loaded) return [];
    const fields = [];
    const seen = new Set();
    const add = (field) => {
      if (typeof field === "string" && field && !seen.has(field)) {
        seen.add(field);
        fields.push(field);
      }
    };
    for (const field of state.loaded.definition.canonical_key || []) add(field);
    for (const field of Object.keys(state.loaded.schema?.properties || {})) add(field);
    for (const record of records) {
      for (const field of Object.keys(record || {})) add(field);
    }
    return fields;
  }

  function valueText(value) {
    if (value === null || value === undefined || value === "") return "—";
    if (value === true) return "Yes";
    if (value === false) return "No";
    if (typeof value === "object") return JSON.stringify(value);
    return String(value);
  }

  function pendingKeys() {
    if (!state.loaded) return new Set();
    return new Set(
      state.loaded.pending.map((record) =>
        root.GDSCore.stableStringify(
          root.GDSCore.key(state.area, state.loaded.definition, record),
        ),
      ),
    );
  }

  function renderResults(records) {
    elements["results-head"].replaceChildren();
    elements["results-body"].replaceChildren();
    const fields = recordFields(records);
    const empty = records.length === 0;
    elements["results-table"].hidden = empty;
    elements["results-empty"].hidden = !empty;
    elements["results-empty"].textContent = state.loaded
      ? "No records match the current filter."
      : "Choose a dataset to see normalized results.";
    if (empty) return;

    const keyFields = new Set(state.loaded.definition.canonical_key || []);
    const staged = pendingKeys();
    const heading = document.createElement("tr");
    for (const field of fields) {
      const cell = document.createElement("th");
      cell.scope = "col";
      cell.textContent = fieldLabel(field);
      if (keyFields.has(field)) cell.className = "is-key";
      heading.append(cell);
    }
    const actionHeading = document.createElement("th");
    actionHeading.scope = "col";
    actionHeading.textContent = "";
    heading.append(actionHeading);
    elements["results-head"].append(heading);

    for (const record of records) {
      const row = document.createElement("tr");
      const rowKey = root.GDSCore.stableStringify(
        root.GDSCore.key(state.area, state.loaded.definition, record),
      );
      if (staged.has(rowKey)) row.className = "is-staged";
      row.tabIndex = 0;
      for (const field of fields) {
        const cell = document.createElement("td");
        const text = valueText(record[field]);
        cell.textContent = text;
        cell.title = text;
        if (keyFields.has(field)) cell.className = "is-key";
        row.append(cell);
      }
      const action = document.createElement("td");
      action.className = "row-action";
      const button = document.createElement("button");
      button.type = "button";
      button.className = "text-action";
      button.textContent = canEditCurrent() && state.preview === "effective" ? "Edit" : "View";
      button.addEventListener("click", () => openRowEditor("edit", record));
      action.append(button);
      row.append(action);
      row.addEventListener("dblclick", () => openRowEditor("edit", record));
      row.addEventListener("keydown", (event) => {
        if (event.key === "Enter") openRowEditor("edit", record);
      });
      elements["results-body"].append(row);
    }
  }

  function renderRecords() {
    const view = recordView();
    elements["record-preview"].textContent = JSON.stringify(view.visible, null, 2);
    renderResults(view.visible);
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

  function setView(view) {
    state.view = view === "json" ? "json" : "results";
    const showResults = state.view === "results";
    elements["results-view"].hidden = !showResults;
    elements["results-view"].classList.toggle("is-hidden", !showResults);
    elements["json-view"].hidden = showResults;
    elements["json-view"].classList.toggle("is-hidden", showResults);
    document.querySelectorAll("[data-view]").forEach((button) => {
      const active = button.dataset.view === state.view;
      button.classList.toggle("is-active", active);
      button.setAttribute("aria-selected", active ? "true" : "false");
    });
  }

  function syncDraftPreview() {
    if (!state.loaded) return false;
    try {
      const pending = JSON.parse(elements["pending-editor"].value);
      if (!Array.isArray(pending)) return false;
      const effective = root.GDSCore.overlay(
        state.area,
        state.loaded.definition,
        state.loaded.baseline,
        pending,
      );
      state.loaded.pending = pending;
      state.loaded.effective = effective;
      state.loaded.overlayError = null;
      state.datasetCounts.set(state.dataset, effective.length);
      renderDatasets();
      renderRecords();
      return true;
    } catch (_error) {
      return false;
    }
  }

  function editorProperty(field, sample) {
    const rootSchema = state.loaded?.schema || {};
    let property = rootSchema.properties?.[field] || {};
    const resolve = (value) => {
      if (typeof value?.$ref !== "string" || !value.$ref.startsWith("#/$defs/")) return value;
      return rootSchema.$defs?.[value.$ref.slice(8)] || value;
    };
    property = resolve(property);
    const options = property.oneOf || property.anyOf || [];
    const resolvedOptions = options.map(resolve);
    const nullable =
      property.nullable === true ||
      property.type === "null" ||
      (Array.isArray(property.type) && property.type.includes("null")) ||
      resolvedOptions.some((option) => option?.type === "null" || option?.const === null);
    const selected =
      resolvedOptions.find((option) => option?.type !== "null" && option?.const !== null) ||
      property;
    const declaredType = Array.isArray(selected.type)
      ? selected.type.find((type) => type !== "null")
      : selected.type;
    const inferredType = Array.isArray(sample)
      ? "array"
      : sample !== null && typeof sample === "object"
        ? "object"
        : typeof sample;
    return {
      schema: { ...property, ...selected },
      type: declaredType || (inferredType === "undefined" ? "string" : inferredType),
      nullable,
      fixed: Object.hasOwn(property, "const") || Object.hasOwn(selected, "const"),
      fixedValue: Object.hasOwn(selected, "const") ? selected.const : property.const,
      defaultValue: Object.hasOwn(selected, "default") ? selected.default : property.default,
    };
  }

  function appendEditorField(field, value, mode, editable, index) {
    const details = editorProperty(field, value);
    const initialValue =
      value !== undefined
        ? value
        : details.fixed
          ? details.fixedValue
          : details.defaultValue !== undefined
            ? details.defaultValue
            : details.type === "array"
              ? []
              : details.type === "object"
                ? {}
                : details.type === "boolean" && !details.nullable
                  ? false
                  : undefined;
    const wrapper = document.createElement("div");
    wrapper.className = "row-editor-field";
    const label = document.createElement("label");
    label.htmlFor = `row-field-${index}`;
    const labelText = document.createElement("span");
    labelText.textContent = fieldLabel(field);
    const metadata = document.createElement("small");
    const keyField = state.loaded.definition.canonical_key?.includes(field);
    const required = state.loaded.schema?.required?.includes(field);
    metadata.textContent = [
      keyField && "Natural key",
      required && "Required",
      details.fixed && "Fixed",
      details.type,
    ]
      .filter(Boolean)
      .join(" · ");
    label.append(labelText, metadata);

    let control;
    const enumValues = Array.isArray(details.schema.enum)
      ? details.schema.enum.filter((option) => option !== null)
      : null;
    if (enumValues || details.type === "boolean") {
      control = document.createElement("select");
      if (details.nullable) {
        const option = document.createElement("option");
        option.value = "__null__";
        option.textContent = "Null";
        control.append(option);
      }
      const values = enumValues || [true, false];
      for (const optionValue of values) {
        const option = document.createElement("option");
        option.value = JSON.stringify(optionValue);
        option.textContent = valueText(optionValue);
        if (
          root.GDSCore.stableStringify(optionValue) ===
          root.GDSCore.stableStringify(initialValue)
        ) {
          option.selected = true;
        }
        control.append(option);
      }
      if (initialValue === null && details.nullable) control.value = "__null__";
      control.dataset.valueKind = "json";
    } else if (
      details.type === "object" ||
      details.type === "array" ||
      (typeof value === "string" && (value.includes("\n") || value.length > 120))
    ) {
      control = document.createElement("textarea");
      control.value =
        details.type === "object" || details.type === "array"
          ? initialValue == null
            ? ""
            : JSON.stringify(initialValue, null, 2)
          : initialValue || "";
      control.dataset.valueKind = details.type;
    } else {
      control = document.createElement("input");
      control.type = details.type === "integer" || details.type === "number" ? "number" : "text";
      control.value = initialValue == null ? "" : String(initialValue);
      control.dataset.valueKind = details.type;
      if (details.schema.format === "date") control.type = "date";
    }
    control.id = `row-field-${index}`;
    control.dataset.rowField = field;
    control.disabled = !editable || details.fixed || (mode === "edit" && keyField);
    wrapper.append(label, control);

    if (details.nullable && details.type !== "boolean" && !enumValues) {
      const nullLabel = document.createElement("label");
      nullLabel.className = "null-toggle";
      const nullControl = document.createElement("input");
      nullControl.type = "checkbox";
      nullControl.dataset.nullField = field;
      nullControl.checked = initialValue === null;
      nullControl.disabled = !editable || details.fixed || (mode === "edit" && keyField);
      nullControl.addEventListener("change", () => {
        control.disabled =
          nullControl.checked || !editable || details.fixed || (mode === "edit" && keyField);
      });
      if (nullControl.checked) control.disabled = true;
      nullLabel.append(nullControl, " Set null");
      wrapper.append(nullLabel);
    }
    elements["row-editor-fields"].append(wrapper);
  }

  function openRowEditor(mode, record) {
    if (!state.loaded) return;
    const editable = canEditCurrent() && state.preview === "effective";
    if (mode === "add" && !editable) return;
    const fields = recordFields([record]);
    state.editing = { mode, original: record, fields, editable };
    elements["row-editor-fields"].replaceChildren();
    elements["row-editor-message"].textContent = "";
    elements["row-editor-eyebrow"].textContent =
      mode === "add" ? "New local record" : state.preview === "snapshot" ? "Snapshot record" : "Effective record";
    elements["row-editor-title"].textContent =
      mode === "add" ? `Add ${fieldLabel(state.dataset)} row` : `${fieldLabel(state.dataset)} details`;
    elements["row-editor-key"].textContent =
      mode === "add"
        ? "Complete every required normalized field."
        : (state.loaded.definition.canonical_key || [])
            .map((field) => valueText(record[field]))
            .join(" · ");
    elements["save-row-editor"].hidden = !editable;
    elements["cancel-row-editor"].textContent = editable ? "Cancel" : "Close";
    fields.forEach((field, index) => appendEditorField(field, record[field], mode, editable, index));
    elements["row-editor-dialog"].showModal();
  }

  function readEditorRecord() {
    const record = {};
    for (const field of state.editing.fields) {
      const control = elements["row-editor-fields"].querySelector(
        `[data-row-field="${CSS.escape(field)}"]`,
      );
      const nullControl = elements["row-editor-fields"].querySelector(
        `[data-null-field="${CSS.escape(field)}"]`,
      );
      if (nullControl?.checked || control.value === "__null__") {
        record[field] = null;
      } else if (control.dataset.valueKind === "json") {
        record[field] = JSON.parse(control.value);
      } else if (control.dataset.valueKind === "integer") {
        const value = Number(control.value);
        if (!Number.isSafeInteger(value)) throw new Error(`${fieldLabel(field)} must be an integer.`);
        record[field] = value;
      } else if (control.dataset.valueKind === "number") {
        const value = Number(control.value);
        if (!Number.isFinite(value)) throw new Error(`${fieldLabel(field)} must be a number.`);
        record[field] = value;
      } else if (control.dataset.valueKind === "array" || control.dataset.valueKind === "object") {
        record[field] = JSON.parse(control.value);
      } else {
        record[field] = control.value;
      }
    }
    return record;
  }

  function stageEditorRecord() {
    try {
      const record = readEditorRecord();
      const issues = root.GDSCommonValidation?.validateSchema(record, state.loaded.schema) || [];
      if (issues.length) throw new Error(issues.slice(0, 3).join(" "));
      const key = root.GDSCore.stableStringify(
        root.GDSCore.key(state.area, state.loaded.definition, record),
      );
      if (state.editing.mode === "edit") {
        const originalKey = root.GDSCore.stableStringify(
          root.GDSCore.key(state.area, state.loaded.definition, state.editing.original),
        );
        if (originalKey !== key) throw new Error("Natural key fields cannot be renamed.");
      }
      const pending = JSON.parse(elements["pending-editor"].value);
      if (!Array.isArray(pending)) throw new Error("Local editor must contain a JSON array.");
      const merged = new Map(
        pending.map((item) => [
          root.GDSCore.stableStringify(
            root.GDSCore.key(state.area, state.loaded.definition, item),
          ),
          item,
        ]),
      );
      merged.set(key, record);
      elements["pending-editor"].value = JSON.stringify([...merged.values()], null, 2);
      state.dirty = true;
      if (!syncDraftPreview()) throw new Error("The updated local draft could not be previewed.");
      clearValidation();
      enableControls();
      elements["row-editor-dialog"].close();
      setStatus("Updated the unsaved local draft. Select Save dataset to write it to disk.");
    } catch (error) {
      elements["row-editor-message"].textContent = error?.message || String(error);
    }
  }

  function clearValidation() {
    state.validation = null;
    elements["validation-summary"].className = "validation-summary is-neutral";
    elements["validation-summary"].textContent = "Validation has not run for this digest.";
    elements["issue-list"].replaceChildren();
    elements["accept-button"].disabled = true;
    elements["override-button"].disabled = true;
  }

  async function refreshDatasetCounts() {
    if (!state.workspace?.area(state.area).manifest) {
      state.datasetCounts = new Map();
      return;
    }
    const loaded = await state.workspace.loadArea(state.area);
    state.datasetCounts = new Map(
      [...loaded].map(([name, dataset]) => [name, dataset.effective.length]),
    );
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
    state.datasetCounts = new Map();
    state.view = "results";
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
    await refreshDatasetCounts();
    setView("results");
    renderRecords();
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
      syncDraftPreview();
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
      state.datasetCounts.set(state.dataset, state.loaded.effective.length);
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
      state.datasetCounts.set(state.dataset, state.loaded.effective.length);
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
  elements["add-row-button"].addEventListener("click", () => openRowEditor("add", {}));
  elements["copy-visible"].addEventListener("click", copyVisible);
  elements["discard-button"].addEventListener("click", discard);
  elements["save-button"].addEventListener("click", save);
  elements["validate-button"].addEventListener("click", validate);
  elements["pending-editor"].addEventListener("input", () => {
    state.dirty = true;
    clearValidation();
    const previewed = syncDraftPreview();
    enableControls();
    setStatus(
      previewed
        ? "Unsaved draft. Save or discard it before validation or navigation."
        : "Unsaved JSON is incomplete or invalid; Results retain the last valid preview.",
      !previewed,
    );
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
      enableControls();
    });
  });
  document.querySelectorAll("[data-view]").forEach((button) => {
    button.addEventListener("click", () => setView(button.dataset.view));
  });
  elements["row-editor-form"].addEventListener("submit", (event) => {
    event.preventDefault();
    stageEditorRecord();
  });
  elements["close-row-editor"].addEventListener("click", () =>
    elements["row-editor-dialog"].close(),
  );
  elements["cancel-row-editor"].addEventListener("click", () =>
    elements["row-editor-dialog"].close(),
  );
  elements["row-editor-dialog"].addEventListener("close", () => {
    state.editing = null;
    elements["row-editor-message"].textContent = "";
  });

  root.GDSWorkbenchApp = { connectDirectoryHandle, refresh, state };
  enableControls();
})(globalThis);
