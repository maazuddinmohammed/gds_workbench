(function (root) {
  "use strict";
  function create({ state, dialog, editorFields, editorMessage, eligible, recordKey, recordFields, DETAIL_FIELDS, recordReadOnlyReason }) {
    const { label, valueText } = root.AtlasText;
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
    if (!state.loaded || !eligible() || (mode === "edit" && recordReadOnlyReason(record)) || (mode === "edit" && !state.loaded.pending.some((item) => recordKey(item) === recordKey(record)))) return;
    const fields = recordFields([record], true);
    state.editing = { mode, original: record, fields };
    editorFields.replaceChildren();
    editorMessage.textContent = "";
    document.getElementById("row-editor-eyebrow").textContent = mode === "add" ? "New Change Set record" : "Local Change Set record";
    document.getElementById("row-editor-title").textContent = mode === "add" ? `Add ${label(state.dataset)} row` : `Edit ${label(state.dataset)} draft`;
    document.getElementById("row-editor-key").textContent = mode === "add" ? "Complete every required normalized field." : (state.loaded.definition.canonical_key || []).map((field) => valueText(record[field])).join(" · ");
    fields.forEach((field, index) => appendEditorField(field, record[field], index));
    state.editing.initial = formValue();
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
    function formValue() {
      return JSON.stringify([...editorFields.querySelectorAll("input, select, textarea")].map(input => [input.id, input.value, input.checked, input.disabled]));
    }
    function dirty() { return Boolean(state.editing && state.editing.initial !== formValue()); }
    return { openEditor, readEditorRecord, dirty };
  }
  root.AtlasEditor = { create };
})(globalThis);
