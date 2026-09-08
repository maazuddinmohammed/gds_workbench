import { useEffect, useRef, useState, type ReactNode } from "react";
import { useInfiniteQuery, useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { Link } from "@tanstack/react-router";
import { ApiError } from "../../core/http";
import type { ModelDetail } from "../models/api";
import { ModelRecordHistory } from "../model_record_review/ModelRecordHistory";
import { ModelRecordReview } from "../model_record_review/ModelRecordReview";
import type { AttributeAssignment, BindingCommand, BindingPreview, GenerateBindingCommand, ModelTargetsApi, RegisteredTarget, TargetBindingRow, TargetLayer } from "./api";
import { targetError } from "./api";

type ApplyCommand = BindingCommand & { assignments: AttributeAssignment[]; expected_plan_digest: string };

export function ModelTargetsScreen({ api, tenantId, model, hasTenantLock, layer }: {
  api: ModelTargetsApi; tenantId: number; model: ModelDetail; hasTenantLock: boolean; layer: TargetLayer;
}) {
  return <div className="model-targets-page page-enter">
    <header className="workflow-commandbar"><h1>Target Binding</h1><nav className="target-layer-switch" aria-label="Target layer">
      {(["logical", "dimensional"] as const).map((value) => <Link key={value} to="/tenants/$tenantId/models/$modelId/targets"
        params={{ tenantId: String(tenantId), modelId: String(model.model_id) }} search={{ layer: value }}
        className={layer === value ? "is-active" : ""} aria-current={layer === value ? "page" : undefined}>{value === "logical" ? "Logical" : "Dimensional"}</Link>)}
    </nav></header>
    <TargetWorkspace key={`${tenantId}:${model.model_id}:${layer}`} api={api} tenantId={tenantId} model={model} hasTenantLock={hasTenantLock} layer={layer} />
  </div>;
}

function TargetWorkspace({ api, tenantId, model, hasTenantLock, layer }: {
  api: ModelTargetsApi; tenantId: number; model: ModelDetail; hasTenantLock: boolean; layer: TargetLayer;
}) {
  const client = useQueryClient(), modelId = model.model_id, zone = layer === "logical" ? "Silver" : "Gold";
  const [selected, setSelected] = useState<Set<number>>(new Set());
  const [attributeSelected, setAttributeSelected] = useState<Set<number>>(new Set());
  const [entity, setEntity] = useState<TargetBindingRow | null>(null);
  const [searchEntity, setSearchEntity] = useState<TargetBindingRow | null>(null);
  const [generate, setGenerate] = useState(false);
  const [attributeSearch, setAttributeSearch] = useState<number | null>(null);
  const [attributeQuery, setAttributeQuery] = useState("");
  const [preview, setPreview] = useState<BindingPreview | null>(null);
  const [assignments, setAssignments] = useState<AttributeAssignment[]>([]);
  const [edited, setEdited] = useState(false), [page, setPage] = useState(0), [notice, setNotice] = useState("");
  const [historyOpen, setHistoryOpen] = useState(false);
  const [historyKind, setHistoryKind] = useState<"model_object_binding" | "model_attribute_binding">("model_object_binding");
  const submission = useRef<{ command: ApplyCommand; key: string } | null>(null);
  const heading = useRef<HTMLHeadingElement>(null), returnEntity = useRef<number | null>(null);
  const options = useQuery({ queryKey: ["model-target-options", tenantId, modelId], queryFn: () => api.readTargetOptions(tenantId, modelId) });
  const bindings = useInfiniteQuery({ queryKey: ["model-target-bindings", tenantId, modelId, layer], initialPageParam: 0,
    queryFn: ({ pageParam }) => api.listTargetBindings(tenantId, modelId, layer, pageParam), getNextPageParam: (result) => result.next_after ?? undefined });
  const rows = bindings.data?.pages.flatMap((result) => result.items) ?? [];
  const stale = options.data?.model_revision !== model.model_revision || bindings.data?.pages.some((result) => result.model_revision !== model.model_revision);
  const ready = !stale && !!options.data?.placement && !options.isFetching && !options.isError && !bindings.isFetching && !bindings.isError;
  const refresh = async () => {
    setPreview(null); setEntity(null); setSelected(new Set()); setAttributeSelected(new Set()); setAssignments([]); setEdited(false);
    await Promise.all(["model", "model-target-options", "model-target-bindings", "model-record-history", "registered-model-targets"]
      .map((key) => client.invalidateQueries({ queryKey: [key, tenantId, modelId] })));
  };
  const previewMutation = useMutation({ mutationFn: (command: BindingCommand) => api.previewModelBinding(tenantId, modelId, command),
    onSuccess: (result) => { setPreview(result); setEdited(false); setPage(0); setAttributeSelected(new Set());
      setAssignments(result.assignments.flatMap((item) => item.attribute_id === null ? [] : [{ modeled_attribute_id: item.modeled_attribute_id, attribute_id: item.attribute_id }])); } });
  const applyMutation = useMutation({ mutationFn: (request: { command: ApplyCommand; key: string }) => api.applyModelBinding(tenantId, modelId, request.command, request.key),
    onSuccess: async (receipt) => { submission.current = null; await refresh(); setNotice(`${receipt.action_count} binding records updated.`); },
    onError: (error) => { if (error instanceof ApiError && error.status < 500 && error.status !== 408) submission.current = null; } });
  const uncertain = applyMutation.isError && submission.current !== null;
  const busy = previewMutation.isPending || applyMutation.isPending || uncertain;
  useEffect(() => {
    if (entity) { returnEntity.current = entity.entity_id; heading.current?.focus(); }
    else if (returnEntity.current !== null) document.getElementById(`binding-entity-${returnEntity.current}`)?.focus();
  }, [entity]);
  const open = (row: TargetBindingRow, targetId: number) => {
    setNotice(""); setSearchEntity(null); setEntity(row); setPreview(null); setAssignments([]); setEdited(false); applyMutation.reset();
    previewMutation.mutate({ layer, entity_id: row.entity_id, object_id: targetId, expected_model_revision: model.model_revision });
  };
  const review = (regenerate = false) => {
    if (!entity || !preview) return;
    applyMutation.reset(); previewMutation.mutate({ layer, entity_id: entity.entity_id, object_id: preview.target.object_id,
      expected_model_revision: model.model_revision, ...(regenerate ? {} : { assignments }) });
  };
  const assignmentIds = new Map(assignments.map((item) => [item.modeled_attribute_id, item.attribute_id]));
  const visibleAttributes = preview?.assignments.slice(page * 50, (page + 1) * 50) ?? [];
  const activeBindingIds = rows.flatMap((item) => item.binding_id === null ? [] : [item.binding_id]);
  const attributeBindingIds = visibleAttributes.flatMap((item) => item.binding_id == null ? [] : [item.binding_id]);
  const select = (ids: number[], chosen: Set<number>, update: (value: Set<number>) => void, label: string) => <input type="checkbox" aria-label={label} disabled={busy || !ready || !ids.length}
    checked={ids.length > 0 && ids.every((id) => chosen.has(id))} onChange={(event) => { const next = new Set(chosen); for (const id of ids) { if (event.target.checked) next.add(id); else next.delete(id); } update(next); }} />;

  return <>
    <div className="target-context-bar"><span>{options.data?.placement ? `${options.data.placement.system_code} · ${options.data.placement.connection_code}` : "GDS Connection not configured"}</span>
      <div className="target-review-actions"><button className="button button-secondary button-small" type="button" disabled={busy} onClick={() => { applyMutation.reset(); previewMutation.reset(); void refresh(); }}>Refresh</button>
        {!entity ? <button className="button button-primary button-small" type="button" disabled={!ready || busy || !hasTenantLock} onClick={() => setGenerate(true)}>Generate</button> : null}</div>
    </div>
    {!hasTenantLock ? <p className="lock-context">Tenant Lock required to change Bindings.</p> : null}
    {options.isPending || bindings.isPending ? <p aria-busy="true">Loading Bindings…</p> : null}
    {options.isError || bindings.isError ? <p role="alert">Could not load Bindings. Refresh to retry.</p> : null}
    {options.data && stale ? <p role="alert">The Model changed. Refresh before changing Bindings.</p> : null}
    {!entity ? <>
      <ModelRecordReview api={api} tenantId={tenantId} modelId={modelId} modelRevision={model.model_revision} dataset="model_object_binding" selectedIds={selected}
        hasTenantLock={hasTenantLock} disabled={busy || !ready} actions={["lock", "unlock"]} onApplied={refresh} />
      <div className="workflow-table-scroll table-scroll binding-ledger"><table className="target-table" aria-label={`${layer === "logical" ? "Logical" : "Dimensional"} target Entities`}><thead><tr>
        <th className="selection-cell">{select(activeBindingIds, selected, setSelected, "Select all visible Object Bindings")}</th><th>Entity</th><th>{zone} schema</th><th>{zone} Object</th><th>Lock</th><th>Actions</th><th><span className="sr-only">Details</span></th>
      </tr></thead><tbody>{rows.map((row) => <tr key={row.entity_id}>
        <td className="selection-cell">{select(row.binding_id === null ? [] : [row.binding_id], selected, setSelected, `Select Binding for ${row.entity_name}`)}</td>
        <th scope="row">{row.entity_name}</th><td>{row.object_schema ?? "—"}</td><td>{row.object_name ?? "—"}</td><td>{row.binding_id === null ? "—" : row.is_locked ? "Locked" : "Open"}</td>
        <td><button type="button" className="text-action" disabled={!ready || busy || row.is_locked || !hasTenantLock} aria-label={`Search target for ${row.entity_name}`} onClick={() => setSearchEntity(row)}>Search</button></td>
        <td><button type="button" className="text-action" id={`binding-entity-${row.entity_id}`} disabled={!ready || busy || row.object_id === null || !hasTenantLock} aria-label={`Show details for ${row.entity_name}`} onClick={() => { if (row.object_id) open(row, row.object_id); }}>Show details</button></td>
      </tr>)}</tbody></table></div>
      {!bindings.isPending && !rows.length ? <p className="empty-state">No active Entities. Apply the {layer === "logical" ? "Logical" : "Dimensional"} design first.</p> : null}
      {bindings.hasNextPage ? <button className="button button-secondary button-small" type="button" disabled={busy || bindings.isFetching} onClick={() => void bindings.fetchNextPage()}>Load more Entities</button> : null}
      <div className="target-list-footer"><Link className="text-action" to="/tenants/$tenantId/metadata" params={{ tenantId: String(tenantId) }}>Metadata registration</Link><Link className="button button-secondary button-small" to="/tenants/$tenantId/mapping/models/$modelId" params={{ tenantId: String(tenantId), modelId: String(modelId) }}>Open Mapping</Link></div>
    </> : <section className="target-binding-detail" aria-labelledby="bind-targets-heading">
      <button className="text-action target-back" type="button" disabled={busy} onClick={() => { setEntity(null); setPreview(null); setAttributeSelected(new Set()); }}>← Back to target Objects</button>
      <header className="target-binding-identity"><h2 id="bind-targets-heading" ref={heading} tabIndex={-1}>{entity.entity_name}</h2><div><small>{zone} target</small><strong>{preview ? `${preview.target.object_schema}.${preview.target.object_name}` : "Loading…"}</strong></div></header>
      {previewMutation.isPending ? <p aria-busy="true">Checking Attribute bindings…</p> : null}
      {previewMutation.isError ? <p role="alert">{targetError(previewMutation.error)}</p> : null}
      {preview ? <>
        <div className="binding-attribute-toolbar"><ModelRecordReview api={api} tenantId={tenantId} modelId={modelId} modelRevision={model.model_revision} dataset="model_attribute_binding" selectedIds={attributeSelected}
          hasTenantLock={hasTenantLock} disabled={busy || !ready || !!preview.is_locked || edited} actions={["lock", "unlock"]} onApplied={refresh} />
          <button type="button" className="button button-secondary button-small" disabled={busy || !ready || !hasTenantLock || preview.is_locked} onClick={() => review(true)}>Generate Attribute bindings</button></div>
        <div className="workflow-table-scroll table-scroll binding-ledger"><table className="target-table" aria-label="Attribute assignments"><thead><tr><th className="selection-cell">{select(attributeBindingIds, attributeSelected, setAttributeSelected, "Select all visible Attribute Bindings")}</th><th>Modeled Attribute</th><th>Storage type</th><th>Registered Attribute</th><th>Lock</th><th>Actions</th></tr></thead><tbody>
          {visibleAttributes.map((row) => <tr key={row.modeled_attribute_id}><td className="selection-cell">{select(row.binding_id == null ? [] : [row.binding_id], attributeSelected, setAttributeSelected, `Select Binding for ${row.modeled_attribute_name}`)}</td><th scope="row">{row.modeled_attribute_name}</th><td>{row.modeled_data_type}</td>
            <td>{preview.target_attributes.find((item) => item.attribute_id === assignmentIds.get(row.modeled_attribute_id))?.attribute_name ?? "—"}</td><td>{row.is_locked ? "Locked" : row.binding_id ? "Open" : "—"}</td>
            <td><button type="button" className="text-action" aria-label={`Search Attribute for ${row.modeled_attribute_name}`} disabled={busy || !ready || !hasTenantLock || row.is_locked || preview.is_locked} onClick={() => { setAttributeSearch(row.modeled_attribute_id); setAttributeQuery(""); }}>Search</button></td></tr>)}
        </tbody></table></div>
        {preview.assignments.length > 50 ? <div className="target-review-actions"><button className="button button-secondary button-small" disabled={busy || page === 0} onClick={() => { setAttributeSelected(new Set()); setPage(page - 1); }}>Previous Attributes</button><span>{page * 50 + 1}–{Math.min((page + 1) * 50, preview.assignments.length)} of {preview.assignments.length}</span><button className="button button-secondary button-small" disabled={busy || (page + 1) * 50 >= preview.assignments.length} onClick={() => { setAttributeSelected(new Set()); setPage(page + 1); }}>Next Attributes</button></div> : null}
        {edited ? <p role="status">Assignments changed.</p> : preview.issues.length ? <div role="alert"><ul>{preview.issues.map((issue, index) => <li key={index}>{issue}</li>)}</ul></div> : <p role="status">{preview.action_count ? "Ready to apply." : "Already bound."}</p>}
        <div className="target-review-actions">{edited || previewMutation.isError ? <button type="button" className="button button-secondary" disabled={busy || !ready || !hasTenantLock} onClick={() => review()}>Review Attribute assignments</button> : null}
          <button type="button" className="button button-accent" disabled={busy || edited || !ready || !hasTenantLock || !preview.can_apply || !preview.action_count || preview.model_revision !== model.model_revision || previewMutation.isError || applyMutation.isError} onClick={() => {
            submission.current = { key: crypto.randomUUID(), command: { layer, entity_id: entity.entity_id, object_id: preview.target.object_id, expected_model_revision: preview.model_revision, assignments, expected_plan_digest: preview.plan_digest } };
            applyMutation.mutate(submission.current);
          }}>{applyMutation.isPending ? "Applying…" : "Apply Bindings"}</button></div>
      </> : null}
      {applyMutation.isError ? <div role="alert"><p>{uncertain ? "Apply was not confirmed. Retry the same submission before changing selections." : targetError(applyMutation.error)}</p>{uncertain ? <button type="button" className="button button-secondary" onClick={() => { if (submission.current) applyMutation.mutate(submission.current); }}>Retry same apply</button> : null}</div> : null}
    </section>}
    {notice ? <p role="status">{notice}</p> : null}
    {!entity ? <details className="target-step" onToggle={(event) => setHistoryOpen(event.currentTarget.open)}><summary>Binding history</summary>{historyOpen ? <><label>Binding records<select value={historyKind} onChange={(event) => setHistoryKind(event.target.value as typeof historyKind)}><option value="model_object_binding">Object Bindings</option><option value="model_attribute_binding">Attribute Bindings</option></select></label><ModelRecordHistory key={historyKind} api={api} tenantId={tenantId} modelId={modelId} modelRevision={model.model_revision} dataset={historyKind} label="Bindings" hasTenantLock={hasTenantLock} /></> : null}</details> : null}
    {searchEntity ? <TargetSearch api={api} tenantId={tenantId} modelId={modelId} layer={layer} schemas={options.data?.schemas.filter((item) => item.layer === layer).map((item) => item.object_schema) ?? []} name={searchEntity.entity_name} onClose={() => setSearchEntity(null)} onSelect={(target) => open(searchEntity, target.object_id)} /> : null}
    {generate ? <GenerateBindings api={api} tenantId={tenantId} model={model} layer={layer} schemas={options.data?.schemas.filter((item) => item.layer === layer).map((item) => item.object_schema) ?? []} hasTenantLock={hasTenantLock} onClose={() => setGenerate(false)} onApplied={async (count) => { setGenerate(false); await refresh(); setNotice(`${count} binding records updated.`); }} /> : null}
    {attributeSearch !== null && preview ? <BindingDialog title="Find target Attribute" onClose={() => setAttributeSearch(null)}><label>Attribute name<input type="search" value={attributeQuery} onChange={(event) => setAttributeQuery(event.target.value)} /></label><div className="binding-search-results">
      {preview.target_attributes.filter((item) => item.attribute_name.toLowerCase().includes(attributeQuery.trim().toLowerCase())).map((item) => <button key={item.attribute_id} type="button" className="binding-search-result" disabled={assignments.some((assigned) => assigned.attribute_id === item.attribute_id && assigned.modeled_attribute_id !== attributeSearch)} onClick={() => { setAssignments((current) => [...current.filter((assigned) => assigned.modeled_attribute_id !== attributeSearch), { modeled_attribute_id: attributeSearch, attribute_id: item.attribute_id }]); setEdited(true); applyMutation.reset(); setAttributeSearch(null); }}><strong>{item.attribute_name}</strong><span>{item.data_type}</span></button>)}
    </div></BindingDialog> : null}
  </>;
}

function BindingDialog({ title, children, onClose, busy = false }: { title: string; children: ReactNode; onClose: () => void; busy?: boolean }) {
  const ref = useRef<HTMLElement>(null), close = useRef<HTMLButtonElement>(null);
  useEffect(() => { const previous = document.activeElement as HTMLElement | null; close.current?.focus(); return () => previous?.focus(); }, []);
  return <div className="dialog-scrim"><section className="run-configuration-dialog binding-dialog" ref={ref} role="dialog" aria-modal="true" aria-label={title} onKeyDown={(event) => {
    if (event.key === "Escape" && !busy) { event.stopPropagation(); onClose(); }
    if (event.key === "Tab") { const elements = Array.from(ref.current?.querySelectorAll<HTMLElement>('button:not(:disabled), input:not(:disabled), select:not(:disabled), summary') ?? []); const first = elements[0], last = elements.at(-1);
      if (event.shiftKey && document.activeElement === first) { event.preventDefault(); last?.focus(); } else if (!event.shiftKey && document.activeElement === last) { event.preventDefault(); first?.focus(); } }
  }}><header className="drawer-header"><h2>{title}</h2><button className="panel-close" ref={close} type="button" disabled={busy} aria-label={`Close ${title}`} onClick={onClose}>×</button></header><div className="binding-dialog-body">{children}</div></section></div>;
}

function TargetSearch({ api, tenantId, modelId, layer, schemas, name, onClose, onSelect }: { api: ModelTargetsApi; tenantId: number; modelId: number; layer: TargetLayer; schemas: string[]; name: string; onClose: () => void; onSelect: (target: RegisteredTarget) => void }) {
  const [schema, setSchema] = useState(""), [search, setSearch] = useState(name), [query, setQuery] = useState(name);
  const targets = useInfiniteQuery({ queryKey: ["registered-model-targets", tenantId, modelId, layer, schema, query], initialPageParam: 0,
    queryFn: ({ pageParam }) => api.listRegisteredTargets(tenantId, modelId, layer, query, pageParam, schema), getNextPageParam: (result) => result.next_after ?? undefined, enabled: schemas.includes(schema) });
  return <BindingDialog title={`Find target for ${name}`} onClose={onClose}><form className="binding-search-form" onSubmit={(event) => { event.preventDefault(); if (query === search.trim()) void targets.refetch(); else setQuery(search.trim()); }}>
    <label>{layer === "logical" ? "Silver" : "Gold"} schema<input type="search" list="binding-search-schemas" value={schema} onChange={(event) => setSchema(event.target.value)} /><datalist id="binding-search-schemas">{schemas.map((value) => <option key={value} value={value} />)}</datalist></label>
    <label>Object name<input type="search" value={search} onChange={(event) => setSearch(event.target.value)} /></label><button type="submit" className="button button-secondary button-small" disabled={!schemas.includes(schema)}>Search</button></form>
    {targets.isFetching ? <p aria-busy="true">Finding targets…</p> : null}{targets.isError ? <p role="alert">Could not load registered targets.</p> : null}
    <div className="binding-search-results">{!targets.isError && targets.data?.pages.flatMap((page) => page.items).map((target) => <button className="binding-search-result" type="button" key={target.object_id} aria-label={`Select ${target.object_schema}.${target.object_name}`} onClick={() => onSelect(target)}><span>{target.object_schema}</span><strong>{target.object_name}</strong></button>)}</div>
    {targets.isSuccess && !targets.data.pages.some((page) => page.items.length) ? <p>No registered targets match.</p> : null}
    {targets.hasNextPage ? <button className="button button-secondary button-small" type="button" disabled={targets.isFetching} onClick={() => void targets.fetchNextPage()}>Load more targets</button> : null}
  </BindingDialog>;
}

function GenerateBindings({ api, tenantId, model, layer, schemas, hasTenantLock, onClose, onApplied }: { api: ModelTargetsApi; tenantId: number; model: ModelDetail; layer: TargetLayer; schemas: string[]; hasTenantLock: boolean; onClose: () => void; onApplied: (count: number) => Promise<void> }) {
  const [schema, setSchema] = useState("");
  const request = useRef<{ command: GenerateBindingCommand & { expected_plan_digest: string }; key: string } | null>(null);
  const generate = useMutation({ mutationFn: () => api.generateBindings(tenantId, model.model_id, { layer, expected_model_revision: model.model_revision, object_schema: schema.trim() }) });
  const apply = useMutation({ mutationFn: (attempt: NonNullable<typeof request.current>) => api.applyGeneratedBindings(tenantId, model.model_id, attempt.command, attempt.key),
    onSuccess: async (receipt) => { request.current = null; await onApplied(receipt.action_count); },
    onError: (error) => { if (error instanceof ApiError && error.status < 500 && error.status !== 408) request.current = null; } });
  const uncertain = apply.isError && request.current !== null, busy = generate.isPending || apply.isPending || uncertain;
  const result = generate.data;
  return <BindingDialog title="Generate Bindings" onClose={onClose} busy={busy}><form className="binding-search-form" onSubmit={(event) => { event.preventDefault(); if (!busy && hasTenantLock && schemas.includes(schema.trim())) { apply.reset(); generate.mutate(); } }}>
    <label>{layer === "logical" ? "Silver" : "Gold"} schema<input type="search" list="generate-binding-schemas" value={schema} disabled={busy} onChange={(event) => { setSchema(event.target.value); generate.reset(); apply.reset(); }} /><datalist id="generate-binding-schemas">{schemas.map((value) => <option key={value} value={value} />)}</datalist></label>
    <button className="button button-primary button-small" type="submit" disabled={busy || !hasTenantLock || !schemas.includes(schema.trim())}>{generate.isPending ? "Matching…" : "Generate"}</button></form>
    {generate.isError ? <p role="alert">{targetError(generate.error)}</p> : null}
    {result ? <><div className="workflow-table-scroll table-scroll binding-ledger"><table aria-label="Generated Bindings"><thead><tr><th>Entity</th><th>Registered Object</th><th>Match</th></tr></thead><tbody>{result.matches.map((match) => <tr key={match.entity_id}><th scope="row">{match.entity_name}</th><td>{match.object_name ?? "—"}</td><td>{match.status}{match.issues.length ? <details><summary>Details</summary><ul>{match.issues.map((issue, index) => <li key={index}>{issue}</li>)}</ul></details> : null}</td></tr>)}</tbody></table></div>
      {result.issues.length ? <p role="alert">{result.issues.join(" ")}</p> : null}<p>{result.action_count ? `${result.action_count} binding records ready.` : "No new Bindings to apply."}</p>
      <button className="button button-accent" type="button" disabled={busy || !hasTenantLock || !result.can_apply || result.model_revision !== model.model_revision || generate.isError || apply.isError} onClick={() => { request.current = { key: crypto.randomUUID(), command: { layer, expected_model_revision: result.model_revision, object_schema: result.object_schema, expected_plan_digest: result.plan_digest } }; apply.mutate(request.current); }}>Apply generated Bindings</button></> : null}
    {apply.isError ? <div role="alert"><p>{uncertain ? "Apply was not confirmed. Retry the same submission." : targetError(apply.error)}</p>{uncertain ? <button type="button" className="button button-secondary" onClick={() => { if (request.current) apply.mutate(request.current); }}>Retry same apply</button> : null}</div> : null}
  </BindingDialog>;
}
