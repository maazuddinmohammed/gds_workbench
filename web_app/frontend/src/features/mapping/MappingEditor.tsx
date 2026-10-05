import { useId, useRef, useState } from "react";
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { ApiError } from "../../core/http";
import { trapDialogFocus, useDialogFocus } from "../../shared/dialog";
import type { MappingApi } from "./api";
import type { MappingEditorData, ModelRecordEditorApi } from "../model_record_review/api";
import "./mapping-ledger.css";

type Document = Record<string, unknown> | null;
const tableFields = ["source_tables", "source_objects", "source_logical_entities", "source_dimensional_entities"];
const columnFields = ["source_columns", "source_attributes", "source_logical_attributes", "source_dimensional_attributes"];
function references(document: Document, fields: string[]): Record<string, unknown>[] {
  return fields.flatMap((field) => Array.isArray(document?.[field]) ? document[field] as unknown[] : [])
    .filter((value): value is Record<string, unknown> => value !== null && typeof value === "object" && !Array.isArray(value));
}
function sourceKey(reference: Record<string, unknown>, column = false): string {
  const kind = reference.entity_type ?? (reference.logical_entity_name ? "logical_entity" : reference.dimensional_entity_name ? "dimensional_entity" : null);
  const parts = kind ? [kind, reference.entity_schema_name ?? reference.logical_entity_schema_name ?? reference.dimensional_entity_schema_name,
    reference.entity_name ?? reference.logical_entity_name ?? reference.dimensional_entity_name]
    : [reference.tenant_code, reference.system_code, reference.connection_code, reference.object_schema, reference.object_name];
  if (column) parts.push(reference.attribute_name ?? reference.logical_attribute_name ?? reference.dimensional_attribute_name);
  return JSON.stringify(parts.map((part) => typeof part === "string" ? part.trim().toLowerCase() : null));
}
function editorError(error: unknown): string {
  if (error instanceof ApiError) {
    if (error.code === "model_locked") return "The Model is locked. A human must unlock it before saving. Your edits are preserved.";
    if (error.code === "record_locked") return "A Mapping or modeled record is locked. Review its locks before saving.";
    if (error.code === "model_revision_conflict") return "The Model changed. Your edits are preserved; close and refresh before retrying.";
    if (error.code === "invalid_request") return "Check source table and column selections, document size, and protected records. Every source column must belong to a selected table.";
    if (["tenant_locked", "tenant_lock_required", "authorization_denied"].includes(error.code)) return "Architect permission and the Tenant Lock are required.";
  }
  return "The save could not be confirmed. Retry the same save before making further edits.";
}

export function MappingEditor({ api, tenantId, modelId, mappingObjectId, modelRevision, hasTenantLock, mode }: {
  api: Pick<MappingApi, "readModelRecordEditor" | "saveModelRecord">;
  tenantId: number; modelId: number; mappingObjectId: number; modelRevision: number;
  hasTenantLock: boolean; mode: "object" | "attribute";
}) {
  const [open, setOpen] = useState(false);
  const [openedRevision, setOpenedRevision] = useState(modelRevision);
  const trigger = useRef<HTMLButtonElement>(null);
  const client = useQueryClient();
  const title = mode === "object" ? "Edit Object Mapping" : "Edit Attribute Mapping";
  const query = useQuery({
    queryKey: ["mapping-editor", tenantId, modelId, mappingObjectId, openedRevision],
    queryFn: () => api.readModelRecordEditor(tenantId, modelId, { dataset: "mapping_object", record_id: mappingObjectId, expected_model_revision: openedRevision }),
    enabled: open, retry: false,
  });
  const close = () => { setOpen(false); requestAnimationFrame(() => trigger.current?.focus()); };
  return <div className="mapping-editor-entry">
    <button ref={trigger} type="button" className="button button-secondary button-small" disabled={!hasTenantLock || open}
      title={!hasTenantLock ? "Architect permission and Tenant Lock required" : undefined}
      onClick={() => { setOpenedRevision(modelRevision); setOpen(true); }}>{title}</button>
    {open && query.isPending ? <p aria-busy="true">Loading Mapping editor…</p> : null}
    {open && query.isError ? <><p role="alert">{editorError(query.error)}</p><button type="button" className="text-action" onClick={close}>Close editor</button></> : null}
    {open && query.data?.mapping ? <MappingEditForm key={`${mode}:${mappingObjectId}:${query.data.model_revision}`}
      data={query.data.mapping} isLocked={query.data.is_locked} stale={query.data.model_revision !== modelRevision}
      mode={mode} title={title} hasTenantLock={hasTenantLock} onClose={close}
      save={(changes, key) => api.saveModelRecord(tenantId, modelId, {
        dataset: "mapping_object", record_id: mappingObjectId, expected_model_revision: query.data!.model_revision, changes,
      }, key)} onSaved={async () => {
        close();
        await client.invalidateQueries({ predicate: (item) => item.queryKey[1] === tenantId });
      }} /> : null}
  </div>;
}

function MappingEditForm({ data, isLocked, stale, hasTenantLock, mode, title, save, onSaved, onClose }: {
  data: MappingEditorData; isLocked: boolean; stale: boolean; hasTenantLock: boolean;
  mode: "object" | "attribute"; title: string;
  save: (changes: Record<string, unknown>, key: string) => ReturnType<ModelRecordEditorApi["saveModelRecord"]>;
  onSaved: () => Promise<void>; onClose: () => void;
}) {
  const headingId = useId();
  const closeButton = useRef<HTMLButtonElement>(null);
  useDialogFocus(closeButton);
  const [object, setObject] = useState<Document>(data.object_document);
  const [attributes, setAttributes] = useState(() => Object.fromEntries(data.attributes.map((item) => [item.name, item.document])));
  const [active, setActive] = useState(mode === "attribute" ? data.attributes[0]?.name ?? "" : "");
  const [search, setSearch] = useState("");
  const [pickerOpen, setPickerOpen] = useState(false);
  const [message, setMessage] = useState("");
  const [discard, setDiscard] = useState(false);
  const [rawDrafts, setRawDrafts] = useState<Record<string, string>>({});
  const [jsonFields, setJsonFields] = useState<Record<string, Record<string, string>>>({});
  const attempt = useRef<{ changes: Record<string, unknown>; key: string } | null>(null);
  const mutation = useMutation({
    mutationFn: (request: NonNullable<typeof attempt.current>) => save(request.changes, request.key),
    retry: false, onSuccess: onSaved,
    onError: (error) => { if (error instanceof ApiError && error.status < 500 && error.status !== 408) attempt.current = null; },
  });
  const attributeMode = mode === "attribute";
  const uncertain = mutation.isError && attempt.current !== null;
  const disabled = stale || isLocked || !hasTenantLock || mutation.isPending || uncertain;
  // Attribute editing only reads the saved Object document; it cannot draft table changes.
  const selectedTables = new Set(references(attributeMode ? data.object_document : object, tableFields).map((ref) => sourceKey(ref)));
  const target = data.attributes.find((item) => item.name === active);
  const document = attributeMode ? attributes[active] ?? null : object;
  const structured = attributeMode ? target?.structured : data.structured;
  const protectedDocument = disabled || (attributeMode ? !target || target.is_locked : data.object_is_locked);
  const selectedRefs = references(document, attributeMode ? columnFields : tableFields);
  const dirty = JSON.stringify(object) !== JSON.stringify(data.object_document)
    || data.attributes.some((item) => JSON.stringify(attributes[item.name]) !== JSON.stringify(item.document))
    || Object.keys(rawDrafts).length > 0 || Object.keys(jsonFields).length > 0;
  const updateDocument = (next: Document) => attributeMode ? setAttributes((current) => ({ ...current, [active]: next })) : setObject(next);
  const toggleSource = (reference: Record<string, unknown>) => {
    const key = sourceKey(reference, attributeMode);
    const removing = selectedRefs.some((ref) => sourceKey(ref, attributeMode) === key);
    if (!attributeMode && removing && data.attributes.some((item) => references(item.document, columnFields).some((ref) => sourceKey(ref) === key))) {
      setMessage("Remove this table’s source columns from Attribute Mapping and save before removing the table."); return;
    }
    setMessage("");
    const next = { ...document };
    (attributeMode ? columnFields : tableFields).forEach((field) => delete next[field]);
    next[attributeMode ? "source_columns" : "source_tables"] = removing
      ? selectedRefs.filter((ref) => sourceKey(ref, attributeMode) !== key) : [...selectedRefs, reference];
    updateDocument(next);
  };
  const choices = data.source_tables.filter((table) => !attributeMode || selectedTables.has(sourceKey(table.reference)))
    .flatMap((table) => attributeMode
      ? table.columns.map((column) => ({ reference: column.reference, label: `${table.label} · ${column.name}`, help: column.data_type }))
      : [{ reference: table.reference, label: table.label, help: `${table.columns.length} columns` }]);
  const filteredChoices = choices.filter((item) => item.label.toLowerCase().includes(search.trim().toLowerCase()));
  const selectedLabel = (reference: Record<string, unknown>) => choices.find((item) => sourceKey(item.reference, attributeMode) === sourceKey(reference, attributeMode))?.label
    ?? [reference.object_schema ?? reference.entity_schema_name, reference.object_name ?? reference.entity_name, attributeMode ? reference.attribute_name : null].filter(Boolean).join(".");
  function submit(event: React.FormEvent) {
    event.preventDefault(); setMessage("");
    if (stale || isLocked || !hasTenantLock || mutation.isPending) return;
    if (uncertain && attempt.current) { mutation.mutate(attempt.current); return; }
    try {
      const nextDocument = (key: string, current: Document): Document => {
        const next = Object.hasOwn(rawDrafts, key) ? parseDocument(rawDrafts[key]!) : current;
        const fields = Object.entries(jsonFields[key] ?? {});
        return fields.length ? { ...next, ...Object.fromEntries(fields.map(([field, raw]) => [field, raw.trim() ? JSON.parse(raw) : null])) } : next;
      };
      const changes = attributeMode ? {
        attribute_mappings: data.attributes.map((item) => ({ item, next: nextDocument(item.name, attributes[item.name] ?? null) }))
          .filter(({ item, next }) => JSON.stringify(next) !== JSON.stringify(item.document))
          .map(({ item, next }) => ({ modeled_attribute_name: item.name, attribute_mapping_transformation_document: next })),
      } : { object_mapping: { object_dependency_order: data.dependency_order, mapping_transformation_document: nextDocument("", object) } };
      attempt.current = { changes, key: crypto.randomUUID() }; mutation.mutate(attempt.current);
    } catch { setMessage("Check the JSON fields. Custom documents must be a JSON object or null."); }
  }
  const requestClose = () => { if (!mutation.isPending && !uncertain) { if (dirty) setDiscard(true); else onClose(); } };
  const sourceTitle = attributeMode ? "source columns" : "source tables";
  return <div className="dialog-scrim" role="presentation"><section
    className="run-configuration-dialog model-record-review-dialog mapping-edit-dialog" role="dialog" aria-modal="true" aria-labelledby={headingId}
    onKeyDown={(event) => { if (event.key === "Escape") { event.stopPropagation(); requestClose(); } trapDialogFocus(event); }}>
    <header className="drawer-header"><h2 id={headingId}>{title}</h2>
      <button ref={closeButton} type="button" className="panel-close" aria-label="Close Mapping editor" disabled={mutation.isPending || uncertain} onClick={requestClose}>×</button></header>
    <form className="model-record-review-body mapping-edit-panel model-record-editor" onSubmit={submit} aria-label="Mapping editor" aria-busy={mutation.isPending}>
    {attributeMode ? <label>Target attribute<select value={active} disabled={mutation.isPending || uncertain} onChange={(event) => { setActive(event.target.value); setSearch(""); setMessage(""); }}>
      {!data.attributes.length ? <option value="">No active attributes</option> : null}
      {data.attributes.map((item) => <option key={item.name} value={item.name}>{item.name} · {item.data_type}{item.is_locked ? " · Locked" : ""}</option>)}
    </select></label> : null}
    {protectedDocument ? <p className="field-help">{stale ? "Model revision changed. Close and refresh before editing." : uncertain ? "Retry the pending save to confirm its outcome." : "This Mapping is read-only. Locked Attributes also protect their Object Mapping."}</p> : null}
    <fieldset disabled={Boolean(protectedDocument)}>
      {structured ? <>
        <section className="mapping-source-picker" aria-label={attributeMode ? "Selected source columns" : "Selected source tables"}>
          <header><span>{selectedRefs.length} {selectedRefs.length === 1 ? sourceTitle.slice(0, -1) : sourceTitle} selected</span><button type="button" className="text-action"
            aria-expanded={pickerOpen} aria-controls={`${headingId}-sources`} onClick={() => setPickerOpen(!pickerOpen)}>
            {pickerOpen ? "Hide" : "Choose"} {sourceTitle}</button></header>
          {selectedRefs.length ? <ul className="mapping-selected-sources">{selectedRefs.map((reference, index) => <li key={`${sourceKey(reference, attributeMode)}:${index}`}>
            <span>{selectedLabel(reference)}</span><button type="button" className="text-action" aria-label={`Remove ${selectedLabel(reference)}`} onClick={() => toggleSource(reference)}>Remove</button>
          </li>)}</ul> : <p className="field-help">{attributeMode ? "Choose columns from the saved Object Mapping." : "Choose the tables this Object Mapping reads."}</p>}
          <div id={`${headingId}-sources`} hidden={!pickerOpen}>
            <label>Search {sourceTitle}<input type="search" value={search} onChange={(event) => setSearch(event.target.value)} /></label>
            <div className="mapping-source-options" role="group" aria-label={attributeMode ? "Source columns" : "Source tables"}>
              {filteredChoices.map((item) => <label className="mapping-source-choice" key={sourceKey(item.reference, attributeMode)}>
                <input type="checkbox" checked={selectedRefs.some((ref) => sourceKey(ref, attributeMode) === sourceKey(item.reference, attributeMode))}
                  onChange={() => toggleSource(item.reference)} /><span>{item.label}<small>{item.help}</small></span></label>)}
              {!filteredChoices.length ? <p className="field-help">{attributeMode && !selectedTables.size ? "Save source tables in Object Mapping first." : search ? "No matching sources." : "No eligible sources are available."}</p> : null}
            </div>
          </div>
        </section>
        {(attributeMode ? ["transformation_logic", "default_record"] : ["filter_criteria", "sample_query"]).map((field) => {
          const json = document?.[field] != null && typeof document[field] !== "string";
          return <label key={field}>{field.replaceAll("_", " ").replace(/^./, (letter) => letter.toUpperCase())}
            <textarea rows={field === "sample_query" ? 6 : field === "transformation_logic" ? 5 : 3} spellCheck={false}
              value={json ? jsonFields[active]?.[field] ?? JSON.stringify(document?.[field], null, 2) : String(document?.[field] ?? "")}
              onChange={(event) => json ? setJsonFields((current) => ({ ...current, [active]: { ...current[active], [field]: event.target.value } }))
                : updateDocument({ ...document, [field]: event.target.value || null })} />
            {json ? <small className="field-help">This saved value uses JSON. Keep valid JSON to preserve its structure.</small> : null}
          </label>;
        })}
      </> : target || !attributeMode ? <label>Custom transformation document<textarea rows={14} spellCheck={false}
        value={rawDrafts[active] ?? JSON.stringify(document, null, 2)}
        onChange={(event) => setRawDrafts((current) => ({ ...current, [active]: event.target.value }))} />
        <small className="field-help">This custom template uses its own fields. Edit its JSON without changing the template.</small></label> : null}
    </fieldset>
    {message ? <p role="alert">{message}</p> : null}
    {mutation.isError ? <p role="alert">{editorError(mutation.error)}</p> : null}
    <footer className="workflow-command-actions">
      <button type="submit" className="button button-primary" disabled={stale || isLocked || !hasTenantLock || mutation.isPending || (!dirty && !uncertain)}>{mutation.isPending ? "Saving…" : uncertain ? "Retry same save" : attributeMode ? "Save Attribute Mapping" : "Save Object Mapping"}</button>
      <button type="button" className="button button-secondary" disabled={mutation.isPending || uncertain} onClick={requestClose}>Cancel</button>
    </footer>
    {discard ? <div role="alert"><p>Discard unsaved Mapping edits?</p><button type="button" className="button button-secondary" onClick={() => setDiscard(false)}>Keep editing</button><button type="button" className="button button-secondary" onClick={onClose}>Discard edits</button></div> : null}
  </form></section></div>;
}

function parseDocument(raw: string): Document {
  const value: unknown = JSON.parse(raw);
  if (value !== null && (typeof value !== "object" || Array.isArray(value))) throw new Error("Invalid document");
  return value as Document;
}
