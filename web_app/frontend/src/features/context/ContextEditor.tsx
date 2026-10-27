import { useRef, useState, type FormEvent } from "react";
import { useMutation, useQuery } from "@tanstack/react-query";
import { ApiError } from "../../core/http";
import { trapDialogFocus, useDialogFocus } from "../../shared/dialog";
import { loadContextSystems, contextQueryKeys, type ContextApi, type ContextGroupDetail, type ContextGroupReference, type ContextRecordDetail, type ContextWorkflow, type SaveContextGroupCommand, type SaveContextRecordCommand } from "./api";

// In workflow order, as the Project ribbon names them.
const WORKFLOW_NAMES: [ContextWorkflow, string][] = [
  ["analysis", "Analysis"], ["subject_area", "Subject Areas"], ["logical", "Logical"], ["dimensional", "Dimensional"],
  ["mapping", "Mapping"], ["code_generation", "Code generation"], ["validation", "Validation"],
];

type EditorProps = {
  api: ContextApi; tenantId: number; projectId: number; projectRevision: number; hasTenantLock: boolean;
  authoringDisabledReason?: string | undefined;
  onClose: () => void; onSaved: () => Promise<void>;
} & ({ kind: "group"; group?: ContextGroupDetail } | { kind: "record"; group: ContextGroupReference; record?: ContextRecordDetail });

export function ContextEditor(props: EditorProps) {
  const { api, tenantId, projectId, projectRevision, hasTenantLock, onClose, onSaved } = props;
  const group = props.group;
  const record = props.kind === "record" ? props.record : undefined;
  const editing = props.kind === "group" ? Boolean(group) : Boolean(record);
  const title = `${editing ? "Edit" : props.kind === "group" ? "Create" : "Add"} ${props.kind === "group" ? "context group" : "context record"}`;
  const closeButton = useRef<HTMLButtonElement>(null);
  const [revision] = useState(projectRevision);
  const [typeId, setTypeId] = useState(String(group?.context_type.context_type_id ?? ""));
  const [systemId, setSystemId] = useState(String(group?.source_system?.system_id ?? ""));
  const [recordId] = useState(() => record?.context_record_id ?? crypto.randomUUID());
  const [requestKey, setRequestKey] = useState(() => crypto.randomUUID());
  const [dirty, setDirty] = useState(false);
  const [discard, setDiscard] = useState(false);
  const types = useQuery({
    queryKey: contextQueryKeys.types(tenantId, projectId),
    queryFn: () => api.listContextTypes(tenantId, projectId),
    enabled: props.kind === "group",
  });
  const systems = useQuery({
    queryKey: contextQueryKeys.systems(tenantId, projectId),
    enabled: props.kind === "group",
    queryFn: () => loadContextSystems(api, tenantId, projectId),
  });
  const mutation = useMutation({
    mutationFn: (command: SaveContextGroupCommand | SaveContextRecordCommand) => "context_record_id" in command
      ? api.saveContextRecord(tenantId, projectId, command, requestKey)
      : api.saveContextGroup(tenantId, projectId, command, requestKey),
    retry: false,
    onSuccess: async () => {
      await onSaved();
      onClose();
    },
  });
  useDialogFocus(closeButton);
  const uncertain = mutation.isError && (!(mutation.error instanceof ApiError) || mutation.error.status >= 500 || mutation.error.status === 408);
  const stale = revision !== projectRevision;
  const busy = mutation.isPending || uncertain;
  const groupProtected = props.kind === "group" && (props.group?.locked_record_count ?? 0) > 0;
  const blocked = !hasTenantLock || groupProtected || (props.kind === "record" && (!group?.is_active || record?.is_locked));
  const unavailable = props.kind === "group" && (!types.isSuccess || !types.data.items.length || !systems.isSuccess);
  const selectedType = types.data?.items.find((type) => String(type.context_type_id) === typeId);
  const typeWorkflows = WORKFLOW_NAMES.filter(([code]) => selectedType?.context_type_workflows?.includes(code)).map(([, name]) => name);
  const typeDescription = [selectedType?.context_type_description, typeWorkflows.length ? `Used in ${typeWorkflows.join(", ")}.` : null]
    .filter(Boolean).join(" ");
  const disabled = Boolean(blocked || mutation.isPending || (!uncertain && (stale || unavailable)));
  function requestClose() {
    if (busy) return;
    if (dirty) setDiscard(true);
    else onClose();
  }
  function submit(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    if (disabled) return;
    if (uncertain && mutation.variables) { mutation.mutate(mutation.variables); return; }
    const data = new FormData(event.currentTarget);
    if (props.kind === "group") {
      mutation.mutate({
        action: editing ? "edit" : "create", expected_project_revision: revision,
        ...(group ? { context_group_id: group.context_group_id } : {}),
        context_group_name: String(data.get("name") ?? "").trim(),
        context_type_id: Number(data.get("type")),
        context_group_description: String(data.get("description") ?? "").trim() || null,
        source_system_id: data.get("system") ? Number(data.get("system")) : null,
        is_active: editing ? data.has("active") : true,
      });
    } else {
      mutation.mutate({
        action: editing ? "edit" : "create", expected_project_revision: revision,
        context_record_id: recordId, context_group_id: props.group.context_group_id,
        context_text: String(data.get("text") ?? "").trim(),
        source_reference: String(data.get("reference") ?? "").trim() || null,
      });
    }
  }
  return <div className="dialog-scrim" role="presentation">
    <section className="run-configuration-dialog context-editor" role="dialog" aria-modal="true" aria-labelledby="context-editor-heading"
      onKeyDown={(event) => { trapDialogFocus(event); if (event.key === "Escape") requestClose(); }}>
      <header className="drawer-header"><h2 id="context-editor-heading">{title}</h2>
        <button ref={closeButton} className="panel-close" type="button" aria-label="Close context editor" disabled={busy} onClick={requestClose}>×</button>
      </header>
      <form onSubmit={submit} onChange={() => { if (!uncertain) { setDirty(true); setDiscard(false); setRequestKey(crypto.randomUUID()); mutation.reset(); } }}>
        <fieldset className="context-editor-fields" disabled={Boolean(blocked || busy || stale)}>
          <legend className="sr-only">{props.kind === "group" ? "Group details" : "Record content"}</legend>
          {props.kind === "group" ? <>
            <label><span>Context Group Name</span><input name="name" required maxLength={255} readOnly={editing} defaultValue={group?.context_group_name} /></label>
            <label><span>Context type</span><select name="type" required value={typeId} onChange={(event) => setTypeId(event.target.value)} disabled={!types.isSuccess} aria-describedby={typeDescription ? "context-type-description" : undefined}>
              <option value="">{types.isPending ? "Loading types…" : "Choose a type"}</option>
              {types.data?.items.map((type) => <option key={type.context_type_id} value={type.context_type_id}>{type.context_type_name}</option>)}
            </select></label>
            {typeDescription ? <p className="field-help" id="context-type-description">{typeDescription}</p> : null}
            <label><span>Context Group Description (optional)</span><textarea name="description" rows={3} maxLength={2000} defaultValue={props.group?.context_group_description ?? ""} /></label>
            <label><span>Source System (optional)</span><select name="system" value={systemId} onChange={(event) => setSystemId(event.target.value)} disabled={!systems.isSuccess}>
              <option value="">Entire Project</option>
              {group?.source_system && !systems.data?.some((system) => system.system_id === group.source_system?.system_id) ? <option value={group.source_system.system_id}>{group.source_system.system_code} (saved)</option> : null}
              {systems.data?.map((system) => <option key={system.system_id} value={system.system_id}>{system.system_code}</option>)}
            </select></label>
            {editing ? <label className="checkbox-label"><input name="active" type="checkbox" defaultChecked={group?.is_active} />Active group</label> : null}
          </> : <>
            <p className="field-help">{props.group.context_group_name} · {props.group.context_type.context_type_name}</p>
            <label><span>Context Record Text</span><textarea name="text" required rows={7} maxLength={262144} defaultValue={record?.context_text} placeholder="Describe the requirement, rule, or information agents should consider." /></label>
            <label><span>Source reference (optional)</span><textarea name="reference" rows={2} maxLength={65536} defaultValue={record?.source_reference ?? ""} placeholder="Document section, page, link, or meeting reference" /></label>
          </>}
        </fieldset>
        {props.kind === "group" && types.isError ? <p role="alert">Context types could not be loaded. <button type="button" className="text-action" onClick={() => void types.refetch()}>Retry types</button></p> : null}
        {props.kind === "group" && types.isSuccess && !types.data.items.length ? <p role="alert">No Context types are available. Refresh before creating a group.</p> : null}
        {props.kind === "group" && systems.isError ? <p role="alert">Source Systems could not be loaded. <button type="button" className="text-action" onClick={() => void systems.refetch()}>Retry Systems</button></p> : null}
        {props.kind === "record" && !props.group.is_active ? <p role="alert">Activate this group before editing its records.</p> : null}
        {record?.is_locked ? <p role="alert">Unlock this record before editing.</p> : null}
        {groupProtected ? <p role="alert">Unlock this group's records before changing its settings.</p> : null}
        {stale && !uncertain ? <p role="alert">The Project changed. Close and reopen this form before saving.</p> : null}
        {!hasTenantLock ? <p role="alert">{props.authoringDisabledReason ?? "Tenant Lock required to save."}</p> : null}
        {mutation.isError ? <p role="alert" className="inline-error">{mutation.error instanceof ApiError ? mutation.error.message : "The save could not be confirmed."}{uncertain ? " Retry to confirm the original save." : ""}</p> : null}
        {discard ? <div role="alert"><p>Discard unsaved context edits?</p><button type="button" className="button button-secondary" onClick={() => setDiscard(false)}>Keep editing</button><button type="button" className="button button-secondary" onClick={onClose}>Discard edits</button></div> : null}
        <footer className="dialog-actions"><button className="button button-secondary" type="button" disabled={busy} onClick={requestClose}>Cancel</button>
          <button className="button button-primary" type="submit" disabled={disabled}>{mutation.isPending ? "Saving…" : uncertain ? "Retry save" : props.kind === "group" ? "Save group" : "Save record"}</button>
        </footer>
      </form>
    </section>
  </div>;
}
