(function (root) {
  "use strict";

  const PAGE_SIZE = 100;
  const app = document.getElementById("workbench-root");
  const dialog = document.getElementById("row-editor-dialog");
  const editorForm = document.getElementById("row-editor-form");
  const editorFields = document.getElementById("row-editor-fields");
  const editorMessage = document.getElementById("row-editor-message");
  const filter = (field, label) => ({ field, label });

  const FILTERS = {
    metadata: {
      project: [filter("project_code", "Project"), filter("is_active", "Active")],
      tenant: [filter("project_code", "Project"), filter("tenant_code", "Tenant"), filter("tenant_visibility", "Visibility")],
      system: [filter("system_code", "System"), filter("system_type_code", "System type"), filter("is_active", "Active")],
      connection: [filter("tenant_code", "Tenant"), filter("system_code", "System"), filter("connection_type_code", "Connection type")],
      system_type: [filter("system_type_name", "System type"), filter("is_active", "Active")],
      connection_type: [filter("connection_type_name", "Connection type"), filter("is_active", "Active")],
      object_type: [filter("object_type_name", "Object type"), filter("is_active", "Active")],
      zone: [filter("zone_name", "Zone"), filter("is_active", "Active")],
      chunk_type: [filter("chunk_type_name", "Chunk type"), filter("is_active", "Active")],
      file_type: [filter("file_type_name", "File type"), filter("is_active", "Active")],
      data_operation: [filter("data_operation_name", "Data operation"), filter("is_active", "Active")],
      process_type: [filter("process_type_name", "Process type"), filter("is_active", "Active")],
      ingestion_object_mapping: [filter("source_system_code", "Source system"), filter("source_object_name", "Source object"), filter("target_object_name", "Target object")],
      ingestion_attribute_mapping: [filter("source_object_name", "Source object"), filter("target_object_name", "Target object"), filter("is_active", "Active")],
      copy_group: [filter("tenant_code", "Tenant"), filter("system_code", "System"), filter("is_active", "Active")],
      member_group: [filter("tenant_code", "Tenant"), filter("system_code", "System"), filter("is_active", "Active")],
      copy_group_control: [filter("copy_group_name", "Copy group"), filter("member_group_name", "Member group")],
      copy: [filter("copy_group_name", "Copy group"), filter("source_object_name", "Source object"), filter("target_object_name", "Target object")],
      process_group: [filter("zone_code", "Zone"), filter("process_group_name", "Process group"), filter("is_active", "Active")],
      process: [filter("process_group_name", "Process group"), filter("object_name", "Target object"), filter("process_type_name", "Process type")],
    },
    model: {
      model_details: [],
      model_input_scope: [filter("system_code", "System"), filter("object_schema", "Object schema"), filter("object_name", "Object")],
      profiling_profile: [filter("system_code", "System"), filter("object_name", "Object"), filter("attribute_name", "Attribute")],
      analysis_result: [filter("from_object_name", "From object"), filter("to_object_name", "To object"), filter("relationship_kind", "Relationship kind")],
      modeling_assertion_document: [filter("modeling_assertion_document_name", "Document"), filter("system_code", "System"), filter("modeling_assertion_document_type", "Document type")],
      modeling_assertion_record: [filter("modeling_assertion_document_name", "Document"), filter("modeling_assertion_record_type", "Record type"), filter("modeling_assertion_record_status", "Status")],
      conceptual_object: [filter("conceptual_object_name", "Concept"), filter("conceptual_object_type", "Concept type"), filter("conceptual_object_status", "Status")],
      conceptual_relationship: [filter("conceptual_relationship_name", "Relationship"), filter("from_conceptual_object_name", "From concept"), filter("to_conceptual_object_name", "To concept")],
      logical_submodel: [filter("logical_submodel_name", "Submodel"), filter("logical_submodel_status", "Status")],
      logical_entity: [filter("logical_entity_name", "Entity"), filter("logical_entity_type", "Entity type"), filter("logical_entity_status", "Status")],
      logical_attribute: [filter("logical_entity_name", "Logical entity"), filter("logical_attribute_data_type", "Data type"), filter("logical_attribute_status", "Status")],
      logical_relationship: [filter("logical_relationship_name", "Relationship"), filter("from_logical_entity_name", "From entity"), filter("to_logical_entity_name", "To entity")],
      dimensional_submodel: [filter("dimensional_submodel_name", "Submodel"), filter("dimensional_submodel_status", "Status")],
      dimensional_entity: [filter("dimensional_entity_name", "Entity"), filter("dimensional_entity_type", "Entity type"), filter("dimensional_entity_status", "Status")],
      dimensional_attribute: [filter("dimensional_entity_name", "Dimensional entity"), filter("dimensional_attribute_role", "Attribute role"), filter("dimensional_attribute_status", "Status")],
      dimensional_relationship: [filter("dimensional_relationship_name", "Relationship"), filter("from_dimensional_entity_name", "From entity"), filter("to_dimensional_entity_name", "To entity")],
      model_object_binding: [filter("modeled_entity_type", "Model layer"), filter("modeled_entity_name", "Modeled entity"), filter("object_schema", "Target schema")],
      model_attribute_binding: [filter("modeled_entity_name", "Modeled entity"), filter("modeled_attribute_name", "Modeled attribute"), filter("model_attribute_binding_status", "Status")],
      mapping_dependency: [filter("modeled_entity_type", "Model layer"), filter("source_system_code", "Source system"), filter("mapping_source_system_dependency_status", "Status")],
      mapping_object: [filter("modeled_entity_name", "Modeled entity"), filter("source_system_code", "Source system"), filter("object_mapping_status", "Status")],
      mapping_attribute: [filter("modeled_entity_name", "Modeled entity"), filter("modeled_attribute_name", "Modeled attribute"), filter("source_system_code", "Source system")],
      generated_code: [filter("modeled_entity_name", "Modeled entity"), filter("artifact_name", "Artifact"), filter("artifact_type", "Artifact type")],
      generated_code_source_system: [filter("modeled_entity_name", "Modeled entity"), filter("artifact_name", "Artifact"), filter("source_system_code", "Source system")],
      validation_group: [filter("validation_group_name", "Validation group"), filter("system_code", "System"), filter("is_active", "Active")],
      validation_check: [filter("validation_group_name", "Validation group"), filter("validation_category_code", "Category"), filter("validation_severity", "Severity")],
    },
  };
  for (const zone of ["source", "bronze", "silver", "gold"]) {
    FILTERS.metadata[`${zone}_object`] = [filter("source_tenant_code", "Source tenant"), filter("object_schema", "Object schema"), filter("object_name", "Object")];
    FILTERS.metadata[`${zone}_attribute`] = [filter("object_name", "Object"), filter("attribute_name", "Attribute"), filter("attribute_data_type", "Data type")];
  }

  const DETAIL_FIELDS = {
    mapping_object: ["mapping_transformation_document"],
    mapping_attribute: ["attribute_mapping_transformation_document"],
    generated_code: ["generated_code_content"],
    validation_check: ["validation_query_sql", "validation_comparison_query_sql"],
  };

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
    validationArea: "metadata",
    validationFilters: { severity: [], dataset: [] },
    detail: null,
    editing: null,
    busy: false,
    message: "Workbench is local-only. Connect one existing GDS session folder.",
    messageError: false,
  };

  function escapeHtml(value) {
    return String(value ?? "")
      .replaceAll("&", "&amp;")
      .replaceAll("<", "&lt;")
      .replaceAll(">", "&gt;")
      .replaceAll('"', "&quot;")
      .replaceAll("'", "&#039;");
  }

  function label(value) {
    return String(value || "")
      .split("_")
      .filter(Boolean)
      .map((word) => word.charAt(0).toUpperCase() + word.slice(1))
      .join(" ");
  }

  function valueText(value) {
    if (value === null || value === undefined || value === "") return "—";
    if (value === true) return "Yes";
    if (value === false) return "No";
    return typeof value === "object" ? JSON.stringify(value) : String(value);
  }

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

  function currentTask(area = state.area) {
    const task = state.workspace?.state?.tasks?.find((item) => item[0] === state.workspace.state.current);
    return task?.[1] === area ? task : null;
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
        state.workspace?.state?.stale?.includes(state.area),
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
      state.workspace?.state?.stale?.includes(area),
    );
  }

  function recordKey(record) {
    return root.GDSCore.stableStringify(
      root.GDSCore.key(state.area, currentDefinition(), record),
    );
  }

  function pendingByKey() {
    return new Map((state.loaded?.pending || []).map((record) => [recordKey(record), record]));
  }

  function filtersForDataset() {
    if (!state.loaded) return [];
    const available = new Set([
      ...Object.keys(state.loaded.schema?.properties || {}),
      ...state.loaded.baseline.flatMap((record) => Object.keys(record)),
      ...state.loaded.pending.flatMap((record) => Object.keys(record)),
    ]);
    return (FILTERS[state.area][state.dataset] || []).filter((item) => available.has(item.field)).slice(0, 3);
  }

  function sourceRows() {
    if (!state.loaded) return [];
    return state.source === "snapshot" ? state.loaded.baseline : state.loaded.pending;
  }

  function filteredRows() {
    return sourceRows().filter((record) => filtersForDataset().every((item) => {
      const selected = state.filters[`${state.area}:${state.dataset}:${item.field}`] || [];
      return !selected.length || selected.includes(valueText(record[item.field]));
    }));
  }

  function pagedRows() {
    const rows = filteredRows();
    const pages = Math.max(1, Math.ceil(rows.length / PAGE_SIZE));
    state.page = Math.min(state.page, pages - 1);
    return { rows: rows.slice(state.page * PAGE_SIZE, (state.page + 1) * PAGE_SIZE), total: rows.length, pages };
  }

  function recordFields(records, includeDetail = false) {
    if (!state.loaded) return [];
    const fields = [];
    const seen = new Set();
    const hidden = new Set(includeDetail ? [] : DETAIL_FIELDS[state.dataset] || []);
    const add = (field) => {
      if (typeof field === "string" && field && !hidden.has(field) && !seen.has(field)) {
        seen.add(field);
        fields.push(field);
      }
    };
    for (const field of state.loaded.definition.canonical_key || []) add(field);
    for (const field of Object.keys(state.loaded.schema?.properties || {})) add(field);
    for (const record of records) for (const field of Object.keys(record || {})) add(field);
    return fields;
  }

  function topBar() {
    const connected = Boolean(state.workspace);
    const task = currentTask();
    const taskState = task ? `${task[0]} · ${new Set(["doing", "review"]).has(task[3]) ? "working" : task[3]}` : "no current task";
    return `<header class="topbar"><div class="brand" aria-label="GDS Workbench"><span class="brand-mark">GDS</span><span class="brand-name">Workbench</span></div><div class="session-line"><span class="eyebrow">Local session</span><strong>${escapeHtml(state.workspace?.handle?.name || "Not connected")}</strong><span class="state-pill">${escapeHtml(connected ? taskState : "idle")}</span></div><div class="top-actions"><button id="connect-button" type="button" class="button button-primary" ${state.busy ? "disabled" : ""}>Connect session</button><button id="refresh-button" type="button" class="button" ${!connected || state.busy ? "disabled" : ""}>Refresh</button><button id="validate-button" type="button" class="button" ${!connected || !canValidate(state.screen === "validation" ? state.validationArea : state.area) || state.busy ? "disabled" : ""}>Validate locally</button><button id="dbml-button" type="button" class="button" ${!connected || !areaSnapshot("model")?.manifest || state.workspace?.state?.stale?.includes("model") || state.busy ? "disabled" : ""}>Generate DBML</button></div></header>`;
  }

  function areaTabs() {
    const active = state.screen === "validation" ? "validation" : state.area;
    const report = state.reports[state.validationArea];
    const snapshot = active === "validation" ? null : areaSnapshot(active);
    const status = active === "validation"
      ? report ? `${label(state.validationArea)} report · ${report.stale ? "stale" : report.valid ? "passed" : `${report.issue_count} issues`}` : "No local validation report yet"
      : snapshot?.manifest
        ? `${label(active)} Snapshot${snapshot.manifest.model_revision == null ? "" : ` · revision ${snapshot.manifest.model_revision}`} · ${[...state.counts.values()].reduce((sum, item) => sum + item.pending, 0)} Change Set records`
        : "Snapshot unavailable";
    return `<nav class="area-tabs" aria-label="Workbench area" role="tablist">${[["metadata", "Metadata"], ["model", "Model"], ["validation", "Validation results"]].map(([value, text]) => `<button type="button" class="area-tab ${active === value ? "is-active" : ""}" data-area="${value}" role="tab" aria-selected="${active === value}" ${!state.workspace || (value !== "validation" && !areaSnapshot(value)?.manifest) ? "disabled" : ""}>${text}${value === "validation" && report?.issue_count ? `<span class="tab-count">${report.issue_count}</span>` : ""}</button>`).join("")}<span class="snapshot-state">${escapeHtml(status)}</span></nav>`;
  }

  function datasetRail() {
    const definitions = areaSnapshot()?.datasets || [];
    let section = null;
    const items = definitions.map((definition) => {
      const heading = definition.section === section ? "" : `<div class="dataset-group">${escapeHtml(definition.section || "Datasets")}</div>`;
      section = definition.section;
      const count = state.counts.get(definition.name) || { baseline: definition.row_count || 0, pending: 0 };
      return `${heading}<button type="button" class="dataset-button ${definition.name === state.dataset ? "is-active" : ""}" data-dataset="${escapeHtml(definition.name)}" aria-current="${definition.name === state.dataset}"><span>${escapeHtml(label(definition.name))}</span><span>${count.pending ? `<b>${count.pending}</b> / ` : ""}${count.baseline}</span></button>`;
    }).join("");
    return `<aside class="dataset-rail" aria-label="Datasets"><div class="rail-heading"><span class="field-label">${label(state.area)} datasets</span><span>${definitions.length}</span></div><div class="dataset-list">${items || '<p class="empty-state-copy">No Snapshot datasets.</p>'}</div></aside>`;
  }

  function filterOptions(field) {
    return [...new Set([...state.loaded.baseline, ...state.loaded.pending].map((record) => valueText(record[field])))].sort((left, right) => left.localeCompare(right));
  }

  function filterMarkup() {
    const filters = filtersForDataset();
    if (!filters.length) return '<span class="no-filters">This sheet has no useful filters.</span>';
    return filters.map((item) => {
      const key = `${state.area}:${state.dataset}:${item.field}`;
      const selected = state.filters[key] || [];
      return `<details class="multi-filter"><summary><span>${escapeHtml(item.label)}</span><b>${selected.length ? `${selected.length} selected` : "All"}</b></summary><div class="multi-filter-menu" role="group" aria-label="${escapeHtml(item.label)}">${filterOptions(item.field).map((value) => `<label><input type="checkbox" data-filter-key="${escapeHtml(key)}" value="${escapeHtml(value)}" ${selected.includes(value) ? "checked" : ""}><span>${escapeHtml(value)}</span></label>`).join("")}<button type="button" class="filter-clear" data-clear-filter="${escapeHtml(key)}" ${selected.length ? "" : "disabled"}>Clear</button></div></details>`;
    }).join("");
  }

  function recordTable(rows) {
    if (!rows.length) return `<div class="empty-state"><strong>No ${state.source === "snapshot" ? "Snapshot" : "Change Set"} rows match these filters.</strong><span>${state.source === "snapshot" ? "Clear a filter or choose another sheet." : "Add a Snapshot row or create a new Change Set record."}</span></div>`;
    const fields = recordFields(rows);
    const keyFields = new Set(state.loaded.definition.canonical_key || []);
    const pending = pendingByKey();
    const detailed = Boolean(DETAIL_FIELDS[state.dataset]);
    return `<table class="data-table" aria-label="${escapeHtml(label(state.dataset))} records"><thead><tr><th class="select-column"><input type="checkbox" data-action="select-all" aria-label="Select all visible rows"></th>${fields.map((field) => `<th class="${keyFields.has(field) ? "is-key" : ""}">${escapeHtml(label(field))}</th>`).join("")}<th class="action-column">Action</th></tr></thead><tbody>${rows.map((record, index) => {
      const key = recordKey(record);
      const draft = pending.get(key);
      const staged = state.source === "snapshot" && Boolean(draft);
      const action = detailed ? "Show details" : state.source === "changeset" || staged ? "Edit draft" : eligible() ? "Add to Change Set" : "View details";
      const selectable = eligible() && (state.source === "changeset" || !staged);
      return `<tr class="${staged ? "is-staged" : ""}"><td class="select-column"><input type="checkbox" data-select-row="${index}" ${state.selected.has(key) ? "checked" : ""} ${selectable ? "" : "disabled"} aria-label="Select row"></td>${fields.map((field) => { const text = valueText(record[field]); return `<td class="${keyFields.has(field) ? "is-key" : ""}" title="${escapeHtml(text)}">${escapeHtml(text)}</td>`; }).join("")}<td class="action-column"><button type="button" class="text-action" data-row-action="${index}">${action}</button>${staged ? '<span class="row-state">In Change Set</span>' : ""}</td></tr>`;
    }).join("")}</tbody></table>`;
  }

  function recordsWorkspace() {
    if (!state.loaded) return `<main class="record-layout">${datasetRail()}<section class="work-area"><div class="empty-state"><strong>Choose a dataset.</strong><span>Snapshot rows remain read-only.</span></div></section></main>`;
    const page = pagedRows();
    const pending = state.loaded.pending.length;
    const selectedRows = page.rows.filter((record) => state.selected.has(recordKey(record)));
    return `<main class="record-layout">${datasetRail()}<section class="work-area"><div class="work-heading"><div><span class="eyebrow">${escapeHtml(state.loaded.definition.section || state.area)}</span><h1>${escapeHtml(label(state.dataset))}</h1><p>${eligible() ? "Edit through the local Change Set. The downloaded Snapshot stays unchanged." : "Read-only Snapshot context for this task."}</p></div><div class="source-tabs" aria-label="Record source"><button type="button" data-source="snapshot" class="${state.source === "snapshot" ? "is-active" : ""}">Snapshot <span>${state.loaded.baseline.length}</span></button><button type="button" data-source="changeset" class="${state.source === "changeset" ? "is-active" : ""}" ${eligible() ? "" : "disabled"}>Change Set <span>${pending}</span></button></div></div><div class="filter-row"><div class="sheet-filters">${filterMarkup()}</div><div class="page-controls"><span>${page.total} visible</span><button type="button" class="icon-button" data-action="previous-page" ${state.page === 0 ? "disabled" : ""} aria-label="Previous page">←</button><span>${page.total ? `${state.page + 1} / ${page.pages}` : "0 / 0"}</span><button type="button" class="icon-button" data-action="next-page" ${state.page >= page.pages - 1 ? "disabled" : ""} aria-label="Next page">→</button></div></div><section class="results-pane"><div class="pane-heading"><div><strong>${state.source === "snapshot" ? "Downloaded Snapshot" : "Local Change Set"}</strong><span>${state.source === "snapshot" ? "Select existing rows to copy them into the Change Set." : "Only new or changed complete records are stored here."}</span></div><div class="pane-actions"><span>${selectedRows.length ? `${selectedRows.length} selected` : ""}</span>${state.source === "snapshot" ? `<button type="button" class="button button-primary" data-action="stage-selected" ${selectedRows.length && eligible() ? "" : "disabled"}>Add selected to Change Set</button>` : `<button type="button" class="button" data-action="remove-selected" ${selectedRows.length ? "" : "disabled"}>Remove selected</button><button id="add-row-button" type="button" class="button button-primary" data-action="add-row" ${eligible() ? "" : "disabled"}>Add row</button>`}</div></div><div class="table-scroll">${recordTable(page.rows)}</div></section><div class="workflow-note"><strong>${state.source === "snapshot" ? "Snapshot stays unchanged." : "The Change Set is sparse."}</strong><span>${state.source === "snapshot" ? "Adding a row copies its complete current values and natural key." : "Save changes writes immediately to the local session; the backend later merges by natural key."}</span></div></section></main>`;
  }

  function detailValue(field, value) {
    const detail = (DETAIL_FIELDS[state.dataset] || []).includes(field);
    if (!detail) return `<dd>${escapeHtml(valueText(value))}</dd>`;
    const content = typeof value === "object" ? JSON.stringify(value, null, 2) : String(value ?? "");
    return `<dd class="detail-document"><pre tabindex="0">${escapeHtml(content)}</pre></dd>`;
  }

  function detailWorkspace() {
    const detail = state.detail;
    if (!detail || !state.loaded) return recordsWorkspace();
    const pending = pendingByKey();
    const draft = pending.get(detail.key);
    const record = detail.source === "changeset" ? draft : state.loaded.baseline.find((item) => recordKey(item) === detail.key);
    if (!record) return recordsWorkspace();
    const fields = recordFields([record], true);
    const titleField = state.loaded.definition.canonical_key?.at(-1) || fields[0];
    return `<main class="record-layout">${datasetRail()}<section class="detail-page"><div class="detail-heading"><div><button type="button" class="back-action" data-action="back-to-ledger">← Back to ${escapeHtml(label(state.dataset))}</button><span class="eyebrow">${detail.source === "changeset" ? "Local Change Set record" : "Snapshot record"}</span><h1>${escapeHtml(valueText(record[titleField]))}</h1><p>${escapeHtml((state.loaded.definition.canonical_key || []).map((field) => valueText(record[field])).join(" · "))}</p></div><div class="detail-actions">${detail.source === "changeset" ? `<button type="button" class="button" data-action="remove-detail-draft">Remove from Change Set</button><button type="button" class="button button-primary" data-action="edit-detail-draft">Edit draft</button>` : draft ? `<button type="button" class="button button-primary" data-action="open-detail-draft">Open Change Set draft</button>` : eligible() ? `<button type="button" class="button button-primary" data-action="stage-detail">Add to Change Set</button>` : '<span class="read-only-note">Read-only Snapshot</span>'}</div></div><div class="detail-body"><dl>${fields.map((field) => `<div class="${(DETAIL_FIELDS[state.dataset] || []).includes(field) ? "is-document" : ""}"><dt>${escapeHtml(label(field))}</dt>${detailValue(field, record[field])}</div>`).join("")}</dl></div></section></main>`;
  }

  function reportButton(area) {
    const report = state.reports[area];
    const status = !report ? "Not run" : report.stale ? "Stale" : report.valid ? "Passed" : `${report.issue_count} issues`;
    const tone = !report ? "" : report.stale ? "is-stale" : report.valid ? "is-valid" : "is-invalid";
    return `<button type="button" class="report-button ${state.validationArea === area ? "is-active" : ""}" data-report="${area}"><span><strong>${label(area)}</strong><small>${report ? `${report.run_by} · ${new Date(report.generated_at).toLocaleString()}` : "No shared report"}</small></span><b class="${tone}">${status}</b></button>`;
  }

  function validationFilter(labelText, field, values) {
    const selected = state.validationFilters[field];
    return `<details class="multi-filter"><summary><span>${labelText}</span><b>${selected.length ? `${selected.length} selected` : "All"}</b></summary><div class="multi-filter-menu">${values.map((value) => `<label><input type="checkbox" data-validation-filter="${field}" value="${escapeHtml(value)}" ${selected.includes(value) ? "checked" : ""}><span>${escapeHtml(value)}</span></label>`).join("")}<button type="button" class="filter-clear" data-clear-validation="${field}" ${selected.length ? "" : "disabled"}>Clear</button></div></details>`;
  }

  function validationWorkspace() {
    const report = state.reports[state.validationArea];
    const issues = report?.issues || [];
    const severities = [...new Set(issues.map((issue) => issue.severity))].sort();
    const datasets = [...new Set(issues.map((issue) => issue.dataset))].sort();
    const visible = issues.map((issue, index) => ({ issue, index })).filter(({ issue }) =>
      (!state.validationFilters.severity.length || state.validationFilters.severity.includes(issue.severity)) &&
      (!state.validationFilters.dataset.length || state.validationFilters.dataset.includes(issue.dataset))
    );
    const summary = report
      ? `<div class="report-summary ${report.stale ? "is-stale" : report.valid ? "is-valid" : "is-invalid"}"><div><span>Status</span><strong>${report.stale ? "Stale—Change Set changed" : report.valid ? "Passed" : `${report.issue_count} corrections`}</strong></div><div><span>Draft digest</span><strong class="mono">${escapeHtml(report.digest)}</strong></div><div><span>Snapshot revision</span><strong>${escapeHtml(report.snapshot.revision ?? "—")}</strong></div><div><span>Run by</span><strong>${escapeHtml(report.run_by)} · ${escapeHtml(new Date(report.generated_at).toLocaleString())}</strong></div></div><div class="report-path"><span>Shared local report</span><code>reports/local-validation/${state.validationArea}.json</code><span>${report.stale ? "Run again before review." : "Matches its recorded draft digest."}</span></div>`
      : '<div class="report-empty"><strong>Validation has not run.</strong><span>Run the same compiled local checks used by the agent.</span></div>';
    const table = visible.length
      ? `<table class="issue-table"><thead><tr><th>Severity</th><th>Check</th><th>Dataset</th><th>Record</th><th>Message</th><th></th></tr></thead><tbody>${visible.map(({ issue, index }) => `<tr><td><span class="severity ${escapeHtml(issue.severity)}">${escapeHtml(issue.severity)}</span></td><td>${escapeHtml(label(issue.code))}</td><td class="mono">${escapeHtml(issue.dataset)}</td><td>${escapeHtml(issue.record ?? "—")}</td><td>${escapeHtml(issue.message)}</td><td><button type="button" class="text-action" data-open-issue="${index}">Open record</button></td></tr>`).join("")}</tbody></table>`
      : `<div class="empty-state"><strong>${report && !report.stale && report.valid ? "No validation issues." : "No issues to display."}</strong><span>${report ? "Adjust the filters or run validation again." : "Choose an area and run local validation."}</span></div>`;
    return `<main class="validation-layout"><aside class="report-rail"><span class="field-label">Local reports</span>${reportButton("model")}${reportButton("metadata")}<p class="report-help">The agent and Workbench write the same digest-bound report. Refresh reads the newest report from the session.</p></aside><section class="validation-workspace"><div class="validation-heading"><div><span class="eyebrow">Compiled ${label(state.validationArea)} graph</span><h1>Local validation</h1><p>Open an affected record, correct its Change Set draft, then run validation again.</p></div><button type="button" class="button button-primary" data-action="run-report" ${canValidate(state.validationArea) && !state.busy ? "" : "disabled"}>Run ${label(state.validationArea)} validation</button></div>${summary}<div class="validation-filter-row">${validationFilter("Severity", "severity", severities)}${validationFilter("Dataset", "dataset", datasets)}<span>${issues.length} total issues</span></div><div class="issue-table-scroll">${table}</div></section></main>`;
  }

  function render() {
    app.innerHTML = `${topBar()}${areaTabs()}${state.screen === "validation" ? validationWorkspace() : state.screen === "detail" ? detailWorkspace() : recordsWorkspace()}<footer class="statusbar"><span id="status-message" role="status" aria-live="polite" class="${state.messageError ? "is-error" : ""}">${escapeHtml(state.message)}</span><span>${state.workspace ? "Local directory connected" : "Chrome or Edge directory access required"}</span></footer>`;
    bindInteractions();
  }

  async function loadReports() {
    if (!state.workspace?.loadValidationReport) return;
    for (const area of ["metadata", "model"]) {
      state.reports[area] = areaSnapshot(area)?.manifest ? await state.workspace.loadValidationReport(area) : null;
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
        if (await handle.requestPermission({ mode: "readwrite" }) !== "granted") throw new Error("Read/write permission to the session folder was not granted.");
      }
      state.workspace = await root.GDSWorkspace.connect(handle);
      await loadReports();
      const area = areaSnapshot("metadata")?.manifest ? "metadata" : "model";
      await switchArea(area);
      setMessage(`Connected to ${state.workspace.handle.name}. All changes remain local.`);
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
      await switchArea(areaSnapshot(area)?.manifest ? area : "metadata", dataset);
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
    setMessage(message);
  }

  async function stageRecords(records) {
    if (!eligible() || !records.length) return;
    const merged = pendingByKey();
    let added = 0;
    for (const record of records) {
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

  function editorProperty(field, sample) {
    const schema = state.loaded?.schema || {};
    const resolve = (value) => typeof value?.$ref === "string" && value.$ref.startsWith("#/$defs/") ? schema.$defs?.[value.$ref.slice(8)] || value : value;
    const property = resolve(schema.properties?.[field] || {});
    const options = (property.oneOf || property.anyOf || []).map(resolve);
    const nullable = property.nullable === true || property.type === "null" || (Array.isArray(property.type) && property.type.includes("null")) || options.some((item) => item?.type === "null" || item?.const === null);
    const selected = options.find((item) => item?.type !== "null" && item?.const !== null) || property;
    const declared = Array.isArray(selected.type) ? selected.type.find((item) => item !== "null") : selected.type;
    const inferred = Array.isArray(sample) ? "array" : sample !== null && typeof sample === "object" ? "object" : typeof sample;
    return {
      schema: { ...property, ...selected },
      type: declared || (inferred === "undefined" ? "string" : inferred),
      nullable,
      fixed: Object.hasOwn(property, "const") || Object.hasOwn(selected, "const"),
      fixedValue: Object.hasOwn(selected, "const") ? selected.const : property.const,
      defaultValue: Object.hasOwn(selected, "default") ? selected.default : property.default,
    };
  }

  function appendEditorField(field, value, index) {
    const details = editorProperty(field, value);
    const initial = value !== undefined ? value : details.fixed ? details.fixedValue : details.defaultValue !== undefined ? details.defaultValue : details.type === "array" ? [] : details.type === "object" ? {} : details.type === "boolean" && !details.nullable ? false : undefined;
    const wrapper = document.createElement("div");
    wrapper.className = `row-editor-field ${(DETAIL_FIELDS[state.dataset] || []).includes(field) ? "is-wide" : ""}`;
    const fieldLabel = document.createElement("label");
    fieldLabel.htmlFor = `row-field-${index}`;
    const text = document.createElement("span");
    text.textContent = label(field);
    const metadata = document.createElement("small");
    const keyField = state.loaded.definition.canonical_key?.includes(field);
    metadata.textContent = [keyField && "Natural key", state.loaded.schema?.required?.includes(field) && "Required", details.fixed && "Fixed", details.type].filter(Boolean).join(" · ");
    fieldLabel.append(text, metadata);
    let control;
    const enumValues = Array.isArray(details.schema.enum) ? details.schema.enum.filter((item) => item !== null) : null;
    if (enumValues || details.type === "boolean") {
      control = document.createElement("select");
      if (details.nullable) {
        const option = document.createElement("option"); option.value = "__null__"; option.textContent = "Null"; control.append(option);
      }
      for (const optionValue of enumValues || [true, false]) {
        const option = document.createElement("option");
        option.value = JSON.stringify(optionValue); option.textContent = valueText(optionValue);
        if (root.GDSCore.stableStringify(optionValue) === root.GDSCore.stableStringify(initial)) option.selected = true;
        control.append(option);
      }
      if (initial === null && details.nullable) control.value = "__null__";
      control.dataset.valueKind = "json";
    } else if (details.type === "object" || details.type === "array" || (DETAIL_FIELDS[state.dataset] || []).includes(field) || (typeof value === "string" && (value.includes("\n") || value.length > 120))) {
      control = document.createElement("textarea");
      control.value = details.type === "object" || details.type === "array" ? initial == null ? "" : JSON.stringify(initial, null, 2) : initial || "";
      control.dataset.valueKind = details.type;
    } else {
      control = document.createElement("input");
      control.type = details.type === "integer" || details.type === "number" ? "number" : details.schema.format === "date" ? "date" : "text";
      control.value = initial == null ? "" : String(initial);
      control.dataset.valueKind = details.type;
    }
    control.id = `row-field-${index}`;
    control.dataset.rowField = field;
    control.disabled = details.fixed || (state.editing.mode === "edit" && keyField);
    wrapper.append(fieldLabel, control);
    if (details.nullable && details.type !== "boolean" && !enumValues) {
      const nullLabel = document.createElement("label");
      nullLabel.className = "null-toggle";
      const checkbox = document.createElement("input");
      checkbox.type = "checkbox"; checkbox.dataset.nullField = field; checkbox.checked = initial === null; checkbox.disabled = control.disabled;
      checkbox.addEventListener("change", () => { control.disabled = checkbox.checked || details.fixed || (state.editing.mode === "edit" && keyField); });
      if (checkbox.checked) control.disabled = true;
      nullLabel.append(checkbox, " Set null");
      wrapper.append(nullLabel);
    }
    editorFields.append(wrapper);
  }

  function openEditor(mode, record) {
    if (!state.loaded || !eligible() || (mode === "edit" && !state.loaded.pending.some((item) => recordKey(item) === recordKey(record)))) return;
    const fields = recordFields([record], true);
    state.editing = { mode, original: record, fields };
    editorFields.replaceChildren();
    editorMessage.textContent = "";
    document.getElementById("row-editor-eyebrow").textContent = mode === "add" ? "New Change Set record" : "Local Change Set record";
    document.getElementById("row-editor-title").textContent = mode === "add" ? `Add ${label(state.dataset)} row` : `Edit ${label(state.dataset)} draft`;
    document.getElementById("row-editor-key").textContent = mode === "add" ? "Complete every required normalized field." : (state.loaded.definition.canonical_key || []).map((field) => valueText(record[field])).join(" · ");
    fields.forEach((field, index) => appendEditorField(field, record[field], index));
    dialog.showModal();
  }

  function editorControl(field, attribute) {
    return [...editorFields.querySelectorAll(`[${attribute}]`)].find((item) => item.dataset[attribute === "data-row-field" ? "rowField" : "nullField"] === field);
  }

  function readEditorRecord() {
    const record = {};
    for (const field of state.editing.fields) {
      const control = editorControl(field, "data-row-field");
      const nullControl = editorControl(field, "data-null-field");
      if (nullControl?.checked || control.value === "__null__") record[field] = null;
      else if (control.dataset.valueKind === "json" || control.dataset.valueKind === "array" || control.dataset.valueKind === "object") record[field] = JSON.parse(control.value);
      else if (control.dataset.valueKind === "integer") {
        const value = Number(control.value); if (!Number.isSafeInteger(value)) throw new Error(`${label(field)} must be an integer.`); record[field] = value;
      } else if (control.dataset.valueKind === "number") {
        const value = Number(control.value); if (!Number.isFinite(value)) throw new Error(`${label(field)} must be a number.`); record[field] = value;
      } else record[field] = control.value;
    }
    return record;
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
    state.detail = DETAIL_FIELDS[state.dataset] ? { source: "changeset", key } : null;
    state.screen = state.detail ? "detail" : "records";
    render();
  }

  function normalizeValidationIssue(issue) {
    const detail = issue.message || issue.target || issue.endpoint || issue.field || issue.code;
    const fields = [];
    if (typeof issue.field === "string" && issue.field) fields.push(issue.field);
    return {
      severity: issue.severity || "error",
      dataset: issue.dataset || state.validationArea,
      record: issue.record ?? null,
      code: issue.code || "validation",
      fields,
      message: String(detail || "Validation failed."),
    };
  }

  async function runValidation(area) {
    try {
      state.busy = true;
      state.validationArea = area;
      render();
      const loaded = await state.workspace.loadArea(area);
      const metadata = area === "model" && areaSnapshot("metadata")?.manifest && !state.workspace.state?.stale?.includes("metadata") ? await state.workspace.loadArea("metadata") : null;
      const raw = areaModule(area).validate(loaded, metadata, {
        tenantCode: area === "model"
          ? areaSnapshot("model")?.catalog?.model?.tenant_code
          : areaSnapshot("metadata")?.manifest?.tenant_code,
        model: areaSnapshot("model")?.catalog?.model ?? null,
      });
      const issues = raw.slice(0, 200).map(normalizeValidationIssue);
      const validation = {
        digest: await state.workspace.changeSetDigest(area),
        valid: raw.length === 0,
        issueCount: raw.length,
        truncated: raw.length > issues.length,
        issues,
      };
      state.reports[area] = state.workspace.saveValidationReport ? await state.workspace.saveValidationReport(area, validation) : {
        schema_version: "1.0", area, run_by: "workbench", generated_at: new Date().toISOString(), digest: validation.digest,
        snapshot: { id: areaSnapshot(area).manifest.snapshot_id, revision: areaSnapshot(area).manifest.model_revision ?? null, manifest_digest: areaSnapshot(area).manifestDigest || "0".repeat(64) },
        valid: validation.valid, issue_count: validation.issueCount, truncated: validation.truncated, issues, stale: false,
      };
      state.screen = "validation";
      setMessage(validation.valid ? `Local ${label(area)} validation passed.` : `Local ${label(area)} validation found ${raw.length} issue${raw.length === 1 ? "" : "s"}.`);
    } catch (error) { showError(error); }
    finally { state.busy = false; render(); }
  }

  async function generateDbml() {
    try {
      state.busy = true;
      render();
      const loaded = await state.workspace.loadArea("model");
      const documents = root.GDSDbml.render(loaded, areaSnapshot("model").catalog.model, { modelType: "full", includeSubmodels: true });
      const result = await state.workspace.saveDbmlDocuments(documents, { modelType: "full", includeSubmodels: true });
      setMessage(`Generated ${result.file_count} local DBML file${result.file_count === 1 ? "" : "s"} in model-dbml.`);
    } catch (error) { showError(error); }
    finally { state.busy = false; render(); }
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
      state.screen = "detail";
    }
    setMessage(`Opened ${label(issue.dataset)} for validation issue ${label(issue.code)}.`);
    render();
  }

  function bindInteractions() {
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
      if (DETAIL_FIELDS[state.dataset] || !eligible()) {
        state.detail = { source: state.source === "snapshot" && draft ? "changeset" : state.source, key: recordKey(draft || record) };
        state.screen = "detail";
        render();
      } else if (state.source === "changeset" || draft) openEditor("edit", draft || record);
      else stageRecords([record]).catch(showError);
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

  editorForm.addEventListener("submit", (event) => {
    event.preventDefault();
    editorMessage.textContent = "";
    document.getElementById("save-row-editor").disabled = true;
    saveEditor().catch((error) => { editorMessage.textContent = error?.message || String(error); }).finally(() => { document.getElementById("save-row-editor").disabled = false; });
  });
  document.getElementById("close-row-editor").addEventListener("click", () => dialog.close());
  document.getElementById("cancel-row-editor").addEventListener("click", () => dialog.close());
  dialog.addEventListener("close", () => { state.editing = null; editorMessage.textContent = ""; });

  root.GDSWorkbenchApp = { connectDirectoryHandle, refresh, selectDataset, switchArea, state };
  render();
})(globalThis);
