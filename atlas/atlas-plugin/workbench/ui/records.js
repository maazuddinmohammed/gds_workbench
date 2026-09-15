(function (root) {
  "use strict";
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


  function create(context) {
    const { state, PAGE_SIZE, areaSnapshot, recordKey, pendingByKey, eligible, recordReadOnlyReason } = context;
    const { escapeHtml, label, valueText } = root.AtlasText;
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
    if (includeDetail) return fields;
    const chosen = state.columns?.[`${state.area}:${state.dataset}`];
    const name = fields.find(field => field === `${state.dataset}_name`) || fields.find(field => ["attribute_name", "object_name", "modeled_attribute_name", "modeled_entity_name"].includes(field)) || fields[0];
    const priority = [name, ...(state.loaded.definition.canonical_key || []), ...fields.filter(field => /(_data_type|_description|_definition|_is_nullable|_role|_status)$/.test(field) || ["is_active", "is_locked"].includes(field))];
    const defaults = [...new Set(priority)].slice(0, Math.max(8, (state.loaded.definition.canonical_key || []).length + 1));
    const selected = chosen || defaults;
    return [...new Set([name, ...(state.loaded.definition.canonical_key || []), ...selected])].filter(field => fields.includes(field));
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
    if (!rows.length) return `<div class="empty-state"><strong>No ${state.source === "snapshot" ? "Snapshot" : "Change Set"} records match.</strong><span>Clear a filter, choose a dataset or create a local record.</span></div>`;
    const fields = recordFields(rows), keyFields = new Set(state.loaded.definition.canonical_key || []), pending = pendingByKey();
    const actions = new Map(root.GDSCore.reviewActions(state.area, state.loaded.definition, state.loaded.baseline, state.loaded.pending).map(item => [recordKey(item.record), item.action]));
    return `<table class="data-table" aria-label="${escapeHtml(label(state.dataset))} records"><thead><tr><th class="select-column"><input type="checkbox" data-action="select-all" aria-label="Select all visible records"></th>${fields.map((field, index) => `<th class="${index === 0 ? "identity-column" : ""}" scope="col"><div class="column-label">${escapeHtml(label(field))}<button type="button" class="column-resizer" data-resize-column="${escapeHtml(field)}" aria-label="Resize ${escapeHtml(label(field))}" title="Drag or use arrow keys to resize"></button></div></th>`).join("")}<th scope="col">Local change</th><th class="action-column" scope="col">Actions</th></tr></thead><tbody>${rows.map((record, index) => {
      const key = recordKey(record), draft = pending.get(key), change = actions.get(key), selected = state.detail?.key === key;
      return `<tr class="${selected ? "is-selected" : draft ? "has-draft" : ""}"><td class="select-column"><input type="checkbox" data-select-row="${index}" ${state.selected.has(key) ? "checked" : ""} ${eligible() && !recordReadOnlyReason(record) && (state.source === "changeset" || !draft) ? "" : "disabled"} aria-label="Select ${escapeHtml(valueText(record[fields[0]]))}"></td>${fields.map((field, fieldIndex) => {
        const value = record[field];
        const isLong = typeof value === "object" && value !== null || (DETAIL_FIELDS[state.dataset] || []).includes(field);
        const text = isLong ? Array.isArray(value) ? `${value.length} items · Show details` : typeof value === "object" ? `${Object.keys(value).length} fields · Show details` : `${String(value).split("\n").length} lines · Show details` : valueText(value);
        return `<td class="${fieldIndex === 0 ? "identity-column" : ""} ${keyFields.has(field) ? "is-key" : ""} ${/description|definition/.test(field) ? "wrap-value" : ""}">${escapeHtml(text)}</td>`;
      }).join("")}<td><span class="change-label">${change ? escapeHtml(label(change)) : "—"}</span></td><td class="action-column"><button type="button" class="text-action" data-row-action="${index}">Show details</button></td></tr>`;
    }).join("")}</tbody></table>`;
  }

  function columnsMenu() {
    const all = recordFields([...state.loaded.baseline, ...state.loaded.pending], true);
    const visible = new Set(recordFields([...state.loaded.baseline, ...state.loaded.pending]));
    const keys = new Set(state.loaded.definition.canonical_key || []);
    return `<details class="multi-filter columns-menu"><summary>Columns</summary><div class="multi-filter-menu" role="group" aria-label="Visible columns">${all.map(field => `<label><input type="checkbox" data-column="${escapeHtml(field)}" ${visible.has(field) ? "checked" : ""} ${keys.has(field) ? "disabled" : ""}><span>${escapeHtml(label(field))}${keys.has(field) ? " · identity" : ""}</span></label>`).join("")}</div></details>`;
  }

  function recordsWorkspace() {
    if (!state.loaded) return `<main class="record-layout ${state.detail ? "has-details" : ""}">${datasetRail()}<section class="work-area"><div class="empty-state"><strong>Choose a dataset.</strong><span>Snapshot rows remain read-only.</span></div></section>${state.detail ? detailWorkspace() : ""}</main>`;
    const page = pagedRows();
    const pending = state.loaded.pending.length;
    const selectedRows = page.rows.filter((record) => state.selected.has(recordKey(record)));
    return `<main class="record-layout ${state.detail ? "has-details" : ""}">${datasetRail()}<section class="work-area"><div class="work-heading"><div><span class="eyebrow">${escapeHtml(state.loaded.definition.section || state.area)}</span><h1>${escapeHtml(label(state.dataset))}</h1><p>${eligible() ? "Edit through the local Change Set. The downloaded Snapshot stays unchanged." : "Read-only Snapshot context for this task."}</p></div><div class="source-tabs" aria-label="Record source"><button type="button" data-source="snapshot" class="${state.source === "snapshot" ? "is-active" : ""}">Snapshot <span>${state.loaded.baseline.length}</span></button><button type="button" data-source="changeset" class="${state.source === "changeset" ? "is-active" : ""}" >Change Set <span>${pending}</span></button></div></div><div class="filter-row"><div class="sheet-filters">${filterMarkup()}${columnsMenu()}</div><div class="page-controls"><span>${page.total} visible</span><button type="button" class="icon-button" data-action="previous-page" ${state.page === 0 ? "disabled" : ""} aria-label="Previous page">←</button><span>${page.total ? `${state.page + 1} / ${page.pages}` : "0 / 0"}</span><button type="button" class="icon-button" data-action="next-page" ${state.page >= page.pages - 1 ? "disabled" : ""} aria-label="Next page">→</button></div></div><section class="results-pane"><div class="pane-heading"><div><strong>${state.source === "snapshot" ? "Downloaded Snapshot" : "Local Change Set"}</strong><span>${state.source === "snapshot" ? "Select existing rows to copy them into the Change Set." : "Only new or changed complete records are stored here."}</span></div><div class="pane-actions"><span>${selectedRows.length ? `${selectedRows.length} selected` : ""}</span>${state.source === "snapshot" ? `<button type="button" class="button button-primary" data-action="stage-selected" ${selectedRows.length && eligible() ? "" : "disabled"}>Add selected to Change Set</button>` : `<button type="button" class="button" data-action="remove-selected" ${selectedRows.length ? "" : "disabled"}>Remove selected</button><button id="add-row-button" type="button" class="button button-primary" data-action="add-row" ${eligible() ? "" : "disabled"}>Add row</button>`}</div></div><div class="table-scroll">${recordTable(page.rows)}</div></section><div class="workflow-note"><strong>${state.source === "snapshot" ? "Snapshot stays unchanged." : "The Change Set is sparse."}</strong><span>${state.source === "snapshot" ? "Adding a row copies its complete current values and natural key." : "Save changes writes immediately to the local session; the backend later merges by natural key."}</span></div></section>${state.detail ? detailWorkspace() : ""}</main>`;
  }

  function detailValue(field, value) {
    const detail = (DETAIL_FIELDS[state.dataset] || []).includes(field);
    if (!detail) return `<dd>${escapeHtml(valueText(value))}</dd>`;
    const content = typeof value === "object" ? JSON.stringify(value, null, 2) : String(value ?? "");
    return `<dd class="detail-document"><pre tabindex="0">${escapeHtml(content)}</pre></dd>`;
  }

  function detailWorkspace() {
    const detail = state.detail;
    if (!detail || !state.loaded) return "";
    const baseline = state.loaded.baseline.find(item => recordKey(item) === detail.key);
    const draft = pendingByKey().get(detail.key);
    const record = draft || baseline;
    if (!record) return "";
    const fields = recordFields([record, ...(baseline ? [baseline] : [])], true);
    const titleField = fields.find(field => field === `${state.dataset}_name`) || state.loaded.definition.canonical_key?.at(-1) || fields[0];
    const changed = field => root.GDSCore.stableStringify(baseline?.[field]) !== root.GDSCore.stableStringify(record[field]);
    const reason = recordReadOnlyReason(record), locked = Boolean(reason);
    return `<aside class="comparison-panel" aria-label="Snapshot and proposed values"><div class="comparison-heading"><div><span class="eyebrow">${draft ? "Local proposal" : "Snapshot record"}</span><h2 tabindex="-1">${escapeHtml(valueText(record[titleField]))}</h2></div><button type="button" class="icon-button" data-action="back-to-ledger" aria-label="Close record details">×</button></div><div class="detail-actions">${draft ? `<button type="button" class="button" data-action="remove-detail-draft">Remove local change</button><button type="button" class="button button-primary" data-action="edit-detail-draft" ${eligible() && !locked ? "" : "disabled"}>Edit draft</button>` : eligible() && !locked ? `<button type="button" class="button button-primary" data-action="stage-detail">Add to Change Set</button>` : `<span class="read-only-note">${locked ? escapeHtml(reason) : "Read-only Snapshot"}</span>`}</div><div class="comparison-scroll">${fields.map(field => `<section class="comparison-field ${draft && changed(field) ? "is-changed" : ""}"><h3>${escapeHtml(label(field))}</h3><code class="technical-name">${escapeHtml(field)}</code><div class="compare-values"><div><span>Snapshot</span>${detailValue(field, baseline?.[field])}</div><div><span>${draft ? "Proposed" : "Current"}</span>${detailValue(field, record[field])}</div></div></section>`).join("")}</div></aside>`;
  }

    return { filtersForDataset, sourceRows, filteredRows, pagedRows, recordFields, datasetRail, filterOptions, filterMarkup, recordTable, recordsWorkspace, detailValue, detailWorkspace, DETAIL_FIELDS };
  }
  root.AtlasRecords = { create };
})(globalThis);
