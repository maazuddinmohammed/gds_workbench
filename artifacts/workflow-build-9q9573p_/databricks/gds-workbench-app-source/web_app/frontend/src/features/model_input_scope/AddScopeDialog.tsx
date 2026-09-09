import { useEffect, useRef, useState } from "react";
import { useInfiniteQuery, useMutation, useQuery } from "@tanstack/react-query";
import { ApiError } from "../../core/http";
import type { AddScopeCommand, ModelInputScopeApi, ScopeCandidateFilters, ZoneCode } from "./api";

export function AddScopeDialog({ api, tenantId, modelId, modelRevision, hasTenantLock, onClose, onAdded }: {
  api: ModelInputScopeApi; tenantId: number; modelId: number; modelRevision: number;
  hasTenantLock: boolean; onClose: () => void; onAdded: () => Promise<void>;
}) {
  const [placement, setPlacement] = useState(0);
  const [system, setSystem] = useState("");
  const [zone, setZone] = useState<ZoneCode | "">("");
  const [name, setName] = useState("");
  const [search, setSearch] = useState<ScopeCandidateFilters | null>(null);
  const [selected, setSelected] = useState(new Set<number>());
  const [revision] = useState(modelRevision);
  const dialog = useRef<HTMLElement>(null);
  const firstInput = useRef<HTMLSelectElement>(null);
  const attempt = useRef<{ command: AddScopeCommand; key: string } | null>(null);
  const options = useQuery({ queryKey: ["scope-search-options", tenantId, modelId], queryFn: () => api.readScopeSearchOptions(tenantId, modelId) });
  const candidates = useInfiniteQuery({
    queryKey: ["scope-candidates", tenantId, modelId, search], enabled: search !== null,
    queryFn: ({ pageParam }) => api.listScopeCandidates(tenantId, modelId, search!, pageParam),
    initialPageParam: undefined as string | undefined,
    getNextPageParam: (page) => page.next_cursor ?? undefined,
  });
  const add = useMutation({
    mutationFn: (submission: NonNullable<typeof attempt.current>) => api.addScopeObjects(tenantId, modelId, submission.command, submission.key),
    onSuccess: async () => { attempt.current = null; await onAdded(); onClose(); },
    onError: (error) => { if (error instanceof ApiError && error.status < 500 && error.status !== 408) attempt.current = null; },
  });
  const uncertain = add.isError && attempt.current !== null;
  const busy = add.isPending || uncertain;
  const locations = options.data?.locations ?? [];
  const tenants = [...new Map(locations.map((item) => [item.tenant_id, item])).values()];
  const systems = [...new Map(locations.filter((item) => item.tenant_id === placement).map((item) => [item.system_code, item])).values()];
  const zones = [...new Set(locations.filter((item) => item.tenant_id === placement && item.system_code === system).map((item) => item.zone_code))];
  const rows = candidates.data?.pages.flatMap((page) => page.items) ?? [];
  const stale = revision !== modelRevision || (options.data && options.data.model_revision !== revision)
    || candidates.data?.pages.some((page) => page.model_revision !== revision);
  useEffect(() => {
    const previous = document.activeElement;
    firstInput.current?.focus();
    return () => { if (previous instanceof HTMLElement && previous.isConnected) previous.focus(); };
  }, []);
  function resetSearch() { setSearch(null); add.reset(); }
  return <div className="dialog-scrim" role="presentation">
    <section ref={dialog} className="run-configuration-dialog scope-add-dialog" role="dialog" aria-modal="true" aria-labelledby="scope-add-title" tabIndex={-1}
      onKeyDown={(event) => {
        if (event.key === "Escape" && !busy) onClose();
        if (event.key !== "Tab") return;
        const focusable = [...(dialog.current?.querySelectorAll<HTMLElement>("button:not(:disabled), input:not(:disabled), select:not(:disabled)") ?? [])];
        if (event.shiftKey && (document.activeElement === focusable[0] || document.activeElement === dialog.current)) { event.preventDefault(); focusable.at(-1)?.focus(); }
        else if (!event.shiftKey && document.activeElement === focusable.at(-1)) { event.preventDefault(); focusable[0]?.focus(); }
      }}>
      <header className="drawer-header"><h2 id="scope-add-title">Add Objects</h2><button type="button" className="button button-secondary button-small" disabled={busy} onClick={onClose}>Close</button></header>
      <form className="scope-add-filters" onSubmit={(event) => { event.preventDefault(); if (placement && system && zone) setSearch({ tenantId: placement, systemCode: system, zone, objectName: name }); }}>
        <label>Tenant<select ref={firstInput} value={placement || ""} disabled={busy} onChange={(event) => { setPlacement(Number(event.target.value)); setSystem(""); setZone(""); resetSearch(); }}><option value="">Choose Tenant</option>{tenants.map((item) => <option key={item.tenant_id} value={item.tenant_id}>{item.tenant_name} ({item.tenant_code})</option>)}</select></label>
        <label>System<select value={system} disabled={!placement || busy} onChange={(event) => { setSystem(event.target.value); setZone(""); resetSearch(); }}><option value="">Choose System</option>{systems.map((item) => <option key={item.system_code} value={item.system_code}>{item.system_name} ({item.system_code})</option>)}</select></label>
        <label>Zone<select value={zone} disabled={!system || busy} onChange={(event) => { setZone(event.target.value as ZoneCode | ""); resetSearch(); }}><option value="">Choose Zone</option>{zones.map((item) => <option key={item} value={item}>{item === "source" ? "Source" : "Bronze"}</option>)}</select></label>
        <label>Schema or Object name<input value={name} maxLength={400} disabled={busy} onChange={(event) => setName(event.target.value)} placeholder="Search Objects" /></label>
        <button className="button button-secondary" type="submit" disabled={busy || !placement || !system || !zone || candidates.isFetching}>Find Objects</button>
      </form>
      {options.isPending ? <p aria-busy="true">Loading available locations…</p> : options.isError ? <p role="alert">Could not load locations. Close and retry.</p> : !locations.length ? <p className="empty-state">Register Source or Bronze Objects in Metadata first.</p> : null}
      {search ? candidates.isPending ? <p aria-busy="true">Finding Objects…</p> : candidates.isError ? <p role="alert">Could not find Objects. Retry the search.</p> : <>
        <div className="workflow-table-scroll"><table aria-label="Objects to add"><thead><tr><th><span className="sr-only">Select</span></th><th>Object</th><th>Schema</th><th>Attributes</th><th>Scope</th></tr></thead><tbody>{rows.map((row) => <tr key={row.object_id}>
          <td><input type="checkbox" aria-label={`Add ${row.object_schema}.${row.object_name}`} disabled={row.is_in_active_scope || busy} checked={row.is_in_active_scope || selected.has(row.object_id)} onChange={(event) => setSelected((current) => { const next = new Set(current); if (event.target.checked) next.add(row.object_id); else next.delete(row.object_id); return next; })} /></td>
          <th scope="row">{row.object_name}</th><td>{row.object_schema}</td><td>{row.attribute_count}</td><td>{row.is_in_active_scope ? "Already added" : "Available"}</td>
        </tr>)}</tbody></table></div>
        {!rows.length ? <p className="empty-state">No Objects match this search.</p> : null}
        {candidates.hasNextPage ? <button type="button" className="button button-secondary button-small" disabled={busy || candidates.isFetching} onClick={() => void candidates.fetchNextPage()}>Load more Objects</button> : null}
      </> : null}
      {stale ? <p role="alert">The Model changed. Close and refresh before adding Objects.</p> : null}
      {!hasTenantLock ? <p role="alert">Acquire the Tenant Lock before adding Objects.</p> : null}
      {selected.size > 200 ? <p role="alert">Add at most 200 Objects at a time.</p> : null}
      {add.isError ? <p role="alert">{uncertain ? "Addition was not confirmed. Retry this submission." : add.error instanceof ApiError && add.error.code === "model_revision_conflict" ? "The Model changed. Close and refresh." : "Could not add Objects. Check the Tenant Lock, Scope locks, and Source/Bronze eligibility."}</p> : null}
      <footer className="scope-add-actions"><span>{selected.size} selected</span><button className="button button-primary" type="button" disabled={add.isPending || (!uncertain && (!hasTenantLock || Boolean(stale) || selected.size === 0 || selected.size > 200))} onClick={() => {
        if (!attempt.current) attempt.current = { command: { object_ids: [...selected].sort((a, b) => a - b), expected_model_revision: revision }, key: crypto.randomUUID() };
        add.mutate(attempt.current);
      }}>{add.isPending ? "Adding…" : uncertain ? "Retry addition" : "Add selected Objects"}</button></footer>
    </section>
  </div>;
}
