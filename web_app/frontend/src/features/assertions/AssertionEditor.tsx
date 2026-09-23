import { useRef, useState, type FormEvent } from "react";
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { ApiError } from "../../core/http";
import { trapDialogFocus, useDialogFocus } from "../../shared/dialog";
import { assertionsQueryKeys, type AssertionDocument, type AssertionDocumentReference, type AssertionRecord, type AssertionRecordDetail, type AssertionsApi, type SaveAssertionCommand } from "./api";

const documentTypes = [
  ["kpi_requirements", "KPI requirements"], ["reporting_requirements", "Reporting requirements"],
  ["business_rules", "Business rules"], ["domain_context", "Domain context"],
  ["policy", "Policy"], ["design_notes", "Design notes"],
] as const;
const assertionTypes = [
  ["business_rule", "Business rule"], ["definition", "Definition"], ["relationship", "Relationship"],
  ["identity_rule", "Identity rule"], ["design_convention", "Design convention"],
  ["data_quality_rule", "Data quality rule"], ["reporting_requirement", "Reporting requirement"],
  ["kpi_definition", "KPI definition"],
] as const;

export function AssertionEditor({ api, tenantId, modelId, modelRevision, hasTenantLock, document, record, onClose, onSaved }: {
  api: AssertionsApi; tenantId: number; modelId: number; modelRevision: number; hasTenantLock: boolean;
  document?: AssertionDocumentReference; record?: AssertionRecordDetail; onClose: () => void; onSaved: () => Promise<void>;
}) {
  const closeButton = useRef<HTMLButtonElement>(null);
  const queryClient = useQueryClient();
  const parent = record?.document ?? document;
  const [revision] = useState(modelRevision);
  const [key, setKey] = useState(() => crypto.randomUUID());
  const [documentMode, setDocumentMode] = useState("new");
  const [documentId, setDocumentId] = useState("");
  const [documentName, setDocumentName] = useState("");
  const [scope, setScope] = useState("");
  const [action, setAction] = useState(record ? "edit" : "add");
  const [recordId, setRecordId] = useState("");
  const documents = useQuery({
    queryKey: ["assertion-document-choices", tenantId, modelId],
    enabled: !parent,
    queryFn: async () => {
      const items: AssertionDocument[] = [];
      const cursors = new Set<string>();
      let cursor: string | undefined;
      do {
        const page = await api.listAssertionDocuments(tenantId, modelId, {}, 200, cursor);
        items.push(...page.items);
        cursor = page.next_cursor ?? undefined;
        if (cursor && cursors.has(cursor)) throw new Error("Document pagination did not advance.");
        if (cursor) cursors.add(cursor);
      } while (cursor);
      return items;
    },
  });
  const selectedDocument = parent ?? (documentMode === "existing" ? documents.data?.find((item) => String(item.modeling_assertion_document_id) === documentId) : undefined);
  const editing = action === "edit";
  const records = useQuery({
    queryKey: ["assertion-record-choices", tenantId, modelId, selectedDocument?.modeling_assertion_document_id],
    enabled: !record && editing && Boolean(selectedDocument),
    queryFn: async () => {
      const items: AssertionRecord[] = [];
      const cursors = new Set<string>();
      let cursor: string | undefined;
      do {
        const page = await api.listAssertionRecords(tenantId, modelId, { documentId: selectedDocument!.modeling_assertion_document_id }, 200, cursor);
        items.push(...page.items);
        cursor = page.next_cursor ?? undefined;
        if (cursor && cursors.has(cursor)) throw new Error("Assertion pagination did not advance.");
        if (cursor) cursors.add(cursor);
      } while (cursor);
      return items;
    },
  });
  const detail = useQuery({
    queryKey: assertionsQueryKeys.record(tenantId, modelId, Number(recordId)),
    enabled: !record && editing && Boolean(recordId),
    queryFn: () => api.readAssertionRecord(tenantId, modelId, Number(recordId)),
  });
  const selectedRecord = record ?? (editing && !detail.isFetching ? detail.data : undefined);
  const systems = useQuery({
    queryKey: ["assertion-source-systems", tenantId],
    enabled: !parent && documentMode === "new",
    queryFn: async () => {
      const codes = new Set<string>();
      const cursors = new Set<string>();
      let cursor: string | undefined;
      do {
        const page = await api.listMetadataRows(tenantId, "system", {}, 200, cursor);
        for (const row of page.items) if (row.is_active === true && typeof row.system_code === "string") codes.add(row.system_code);
        cursor = page.next_cursor ?? undefined;
        if (cursor && cursors.has(cursor)) throw new Error("System pagination did not advance.");
        if (cursor) cursors.add(cursor);
      } while (cursor);
      return [...codes].sort((a, b) => a.localeCompare(b));
    },
  });
  const mutation = useMutation({
    mutationFn: (command: SaveAssertionCommand) => api.saveAssertion(tenantId, modelId, command, key),
    retry: false,
    onSuccess: async () => {
      await queryClient.invalidateQueries({ predicate: ({ queryKey }) => typeof queryKey[0] === "string" && queryKey[0].startsWith("assertion-") && queryKey[1] === tenantId && queryKey[2] === modelId });
      await onSaved();
      onClose();
    },
  });
  useDialogFocus(closeButton);
  const uncertain = mutation.isError && (!(mutation.error instanceof ApiError) || mutation.error.status >= 500 || mutation.error.status === 408);
  const stale = revision !== modelRevision;
  const frozen = !hasTenantLock || (stale && !uncertain) || mutation.isPending || uncertain;
  const duplicateDocument = !parent && documentMode === "new" && documents.data?.some((item) => item.modeling_assertion_document_name.normalize("NFC").trim().toLowerCase() === documentName.normalize("NFC").trim().toLowerCase());
  const imported = selectedRecord && selectedRecord.modeling_assertion_source_location?.entry_method !== "manual" && selectedRecord.document.modeling_assertion_document_type !== "manual_input";
  const unavailable = (!parent && !documents.isSuccess) || (!parent && documentMode === "existing" && !selectedDocument) || selectedDocument?.is_active === false || duplicateDocument;
  const recordBlocked = editing && (!selectedRecord || detail.isError || selectedRecord.modeling_assertion_record_is_locked || imported);
  const effectiveScope = selectedDocument ? selectedDocument.source_system?.system_code ?? "" : scope;
  const disabled = !hasTenantLock || mutation.isPending || (!uncertain && (stale || unavailable || recordBlocked));
  function submit(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    if (disabled) return;
    if (uncertain && mutation.variables) { mutation.mutate(mutation.variables); return; }
    const data = new FormData(event.currentTarget);
    const notes = String(data.get("notes") ?? "").trim();
    mutation.mutate({
      expected_model_revision: revision,
      ...(selectedRecord ? { record_id: selectedRecord.modeling_assertion_record_id } : {}),
      document_name: selectedDocument?.modeling_assertion_document_name ?? documentName.trim(),
      document_type: selectedDocument ? selectedDocument.modeling_assertion_document_type : String(data.get("document_type") ?? "").trim() || null,
      record_key: selectedRecord?.modeling_assertion_record_key ?? String(data.get("key")).trim(),
      record_type: String(data.get("type")).trim(),
      text: String(data.get("text")).trim(),
      source_system_code: effectiveScope || null,
      source_reference: String(data.get("reference")).trim() || null,
      details: notes ? { notes } : {},
    });
  }
  return <div className="dialog-scrim" role="presentation">
    <section className="run-configuration-dialog assertion-editor" role="dialog" aria-modal="true" aria-labelledby="assertion-editor-heading"
      onKeyDown={(event) => { trapDialogFocus(event); if (event.key === "Escape" && !mutation.isPending && !uncertain) onClose(); }}>
      <header className="drawer-header"><h2 id="assertion-editor-heading">{editing ? "Edit Assertion" : "Add Assertion"}</h2>
        <button ref={closeButton} className="panel-close" type="button" aria-label="Close Assertion editor" disabled={mutation.isPending || uncertain} onClick={onClose}>×</button>
      </header>
      <form onSubmit={submit} onChange={() => { if (!uncertain) { setKey(crypto.randomUUID()); mutation.reset(); } }}>
        <fieldset className="assertion-editor-fields" disabled={frozen}>
          <legend className="sr-only">Document</legend>
          {!parent ? <label><span>Document</span><select value={documentMode} onChange={(event) => { setDocumentMode(event.target.value); setAction("add"); setRecordId(""); }}>
            <option value="new">New document</option><option value="existing">Existing document</option>
          </select></label> : null}
          {!parent && documentMode === "existing" ? <label><span>Existing document</span><select required value={documentId} onChange={(event) => { setDocumentId(event.target.value); setRecordId(""); }}>
            <option value="">{documents.isPending ? "Loading documents…" : "Choose a document"}</option>
            {documents.data?.map((item) => <option key={item.modeling_assertion_document_id} value={item.modeling_assertion_document_id} disabled={!item.is_active}>{item.modeling_assertion_document_name}{item.is_active ? "" : " (inactive)"}</option>)}
          </select></label> : <label><span>Document name</span><input required maxLength={255} readOnly={Boolean(parent)} value={parent?.modeling_assertion_document_name ?? documentName} onChange={(event) => setDocumentName(event.target.value)} placeholder="Customer domain notes" /></label>}
          {duplicateDocument ? <p role="alert">This document already exists. Choose Existing document to add or edit its assertions.</p> : null}
          {(selectedDocument || documentMode === "new") ? <div className="agent-run-grid agent-run-grid-two">
            {selectedDocument ? <label><span>Document type</span><input readOnly value={selectedDocument.modeling_assertion_document_type ?? "Not classified"} /></label> : <TypeField name="document_type" label="Document type" options={documentTypes} />}
            <label><span>Document scope</span><select aria-label="Document scope" aria-describedby="assertion-scope-help" disabled={Boolean(selectedDocument)} value={effectiveScope} onChange={(event) => setScope(event.target.value)}>
              <option value="">Entire Model</option>
              {effectiveScope && !systems.data?.includes(effectiveScope) ? <option value={effectiveScope}>{effectiveScope}</option> : null}
              {systems.data?.map((code) => <option key={code} value={code}>{code}</option>)}
            </select><small id="assertion-scope-help">{selectedDocument ? "All records share this document’s scope." : "Which source context these assertions describe."}</small></label>
          </div> : null}
          {systems.isError && !selectedDocument && documentMode === "new" ? <p role="alert">Systems could not be loaded. <button type="button" className="text-action" onClick={() => void systems.refetch()}>Retry</button></p> : null}
          {selectedDocument && !record ? <label><span>Assertion action</span><select value={action} onChange={(event) => { setAction(event.target.value); setRecordId(""); }}>
            <option value="add">Add new assertion</option><option value="edit">Edit existing assertion</option>
          </select></label> : null}
          {editing && !record ? <label><span>Existing assertion key</span><select required value={recordId} onChange={(event) => setRecordId(event.target.value)}>
            <option value="">{records.isPending ? "Loading assertions…" : "Choose an assertion"}</option>
            {records.data?.map((item) => <option key={item.modeling_assertion_record_id} value={item.modeling_assertion_record_id} disabled={item.modeling_assertion_record_is_locked}>{item.modeling_assertion_record_key}{item.modeling_assertion_record_is_locked ? " (locked)" : ""}</option>)}
          </select></label> : null}
        </fieldset>
        {editing && !record && records.isError ? <p role="alert">Assertions could not be loaded. <button type="button" className="text-action" onClick={() => void records.refetch()}>Retry</button></p> : null}
        {editing && !record && records.isSuccess && records.data.length === 0 ? <p className="field-help">This document has no assertions. Choose Add new assertion.</p> : null}
        {editing && recordId && detail.isFetching ? <p role="status">Loading assertion…</p> : null}
        {editing && !record && detail.isError ? <p role="alert">Assertion details could not be loaded. <button type="button" className="text-action" onClick={() => void detail.refetch()}>Retry</button></p> : null}
        {selectedRecord?.modeling_assertion_record_is_locked ? <p role="alert">Unlock this Assertion from its details page before editing.</p> : null}
        {imported ? <p role="alert">This assertion was imported. Update it through its source import, or add a new manual assertion.</p> : null}
        {(!editing || selectedRecord) ? <fieldset key={`${selectedDocument?.modeling_assertion_document_id ?? documentMode}:${selectedRecord?.modeling_assertion_record_id ?? "new"}`} className="assertion-editor-fields assertion-content-fields" disabled={frozen || Boolean(unavailable) || Boolean(recordBlocked)}>
          <legend className="sr-only">Assertion content</legend>
          <p className="field-help">A document contains multiple assertions. Each key identifies one assertion and must be unique within this Model.</p>
          <div className="agent-run-grid agent-run-grid-two">
            <label><span>Assertion key</span><input name="key" aria-label="Assertion key" aria-describedby="assertion-key-help" required maxLength={100} pattern="[A-Za-z][A-Za-z0-9_.\-]*" readOnly={editing} defaultValue={selectedRecord?.modeling_assertion_record_key} placeholder="customer_identity" /><small id="assertion-key-help">{editing ? "The key stays the same when you edit." : "Start with a letter; use letters, numbers, dots, underscores or hyphens."}</small></label>
            <TypeField name="type" label="Assertion type" required options={assertionTypes} initialValue={selectedRecord?.modeling_assertion_record_type ?? "business_rule"} />
          </div>
          <label><span>Assertion</span><textarea name="text" required rows={4} defaultValue={selectedRecord?.modeling_assertion_text} placeholder="Describe the fact, rule, definition, or requirement the workflows should consider." /></label>
          <label><span>Additional context (optional)</span><textarea name="notes" rows={3} defaultValue={typeof selectedRecord?.modeling_assertion_details.notes === "string" ? selectedRecord.modeling_assertion_details.notes : ""} placeholder="Examples, exceptions, definitions, formulas, or other useful context." /></label>
          <label><span>Reference (optional)</span><input name="reference" defaultValue={typeof selectedRecord?.modeling_assertion_source_location?.reference === "string" ? selectedRecord.modeling_assertion_source_location.reference : ""} placeholder="Document section, page, or meeting reference" /></label>
        </fieldset> : null}
        <p className="field-help">Active assertions are available to all downstream workflows. Each agent uses what is relevant to its task and reports missing evidence or conflicts.</p>
        {!parent && documents.isError ? <p role="alert">Documents could not be loaded. <button type="button" className="text-action" onClick={() => void documents.refetch()}>Retry</button></p> : null}
        {selectedDocument?.is_active === false ? <p role="alert">This document is inactive. Choose an active document.</p> : null}
        {stale && !uncertain ? <p role="alert">The Model changed. Close and reopen this form before saving.</p> : null}
        {!hasTenantLock ? <p role="alert">Tenant Lock required to save.</p> : null}
        {mutation.isError ? <p role="alert" className="inline-error">{mutation.error instanceof ApiError ? mutation.error.message : "The save could not be confirmed."}{uncertain ? " Retry to confirm the original save." : ""}</p> : null}
        <footer className="dialog-actions"><button className="button button-secondary" type="button" disabled={mutation.isPending || uncertain} onClick={onClose}>Cancel</button>
          <button className="button button-primary" type="submit" disabled={Boolean(disabled)}>{mutation.isPending ? "Saving…" : uncertain ? "Retry save" : "Save Assertion"}</button>
        </footer>
      </form>
    </section>
  </div>;
}

function TypeField({ name, label, options, initialValue = "", required = false }: {
  name: string; label: string; options: readonly (readonly [string, string])[]; initialValue?: string; required?: boolean;
}) {
  const [choice, setChoice] = useState(initialValue && !options.some(([value]) => value === initialValue) ? "custom" : initialValue);
  return <div className="assertion-type-field">
    <label><span>{label}{required ? "" : " (optional)"}</span><select name={choice === "custom" ? undefined : name} required={required} value={choice} onChange={(event) => setChoice(event.target.value)}>
      {!required ? <option value="">Not classified</option> : null}
      {options.map(([value, title]) => <option key={value} value={value}>{title}</option>)}
      <option value="custom">Custom type</option>
    </select></label>
    {choice === "custom" ? <label><span>Custom {label.toLowerCase()}</span><input name={name} required maxLength={100} defaultValue={initialValue && !options.some(([value]) => value === initialValue) ? initialValue : ""} /></label> : null}
  </div>;
}
