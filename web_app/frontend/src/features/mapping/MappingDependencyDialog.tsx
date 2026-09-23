import { useRef, useState, type FormEvent } from "react";
import { useMutation, useQuery } from "@tanstack/react-query";
import { ApiError } from "../../core/http";
import { trapDialogFocus, useDialogFocus } from "../../shared/dialog";
import { type MappingApi, type MappingDependency, type MappingEntityType, type SaveMappingDependencyCommand } from "./api";

export function MappingDependencyDialog({ api, tenantId, modelId, modelRevision, entityType, dependency, onClose, onSaved }: {
  api: MappingApi; tenantId: number; modelId: number; modelRevision: number;
  entityType: MappingEntityType;
  dependency: MappingDependency | null; onClose: () => void; onSaved: () => Promise<void>;
}) {
  const firstInput = useRef<HTMLButtonElement>(null);
  const [key, setKey] = useState(() => crypto.randomUUID());
  const registeredSystems = useQuery({
    queryKey: ["mapping-source-systems", tenantId],
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
    enabled: !dependency,
  });
  const systems = dependency ? [dependency.source_system.system_code] : registeredSystems.data ?? [];
  const systemsUnavailable = !dependency && (registeredSystems.isPending || registeredSystems.isError || !systems.length);
  const mutation = useMutation({
    mutationFn: (command: SaveMappingDependencyCommand) => api.saveMappingDependency(tenantId, modelId, command, key),
    retry: false,
    onSuccess: async () => { await onSaved(); onClose(); },
  });
  useDialogFocus(firstInput);
  function submit(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    if (mutation.isPending || systemsUnavailable) return;
    const data = new FormData(event.currentTarget);
    mutation.mutate({
      expected_model_revision: modelRevision,
      entity_type: dependency?.entity_type ?? entityType,
      source_system_code: dependency?.source_system.system_code ?? String(data.get("system")).trim(),
      dependency_order: Number(data.get("order")),
    });
  }
  return <div className="dialog-scrim" role="presentation">
    <section className="run-configuration-dialog" role="dialog" aria-modal="true" aria-labelledby="dependency-heading"
      onKeyDown={(event) => { trapDialogFocus(event); if (event.key === "Escape" && !mutation.isPending) onClose(); }}>
      <header className="drawer-header"><h2 id="dependency-heading">{dependency ? "Edit System order" : "Add System dependency"}</h2>
        <button ref={firstInput} className="panel-close" type="button" aria-label="Close System dependency" disabled={mutation.isPending} onClick={onClose}>×</button>
      </header>
      <form onSubmit={submit} onChange={() => { setKey(crypto.randomUUID()); mutation.reset(); }}>
        <fieldset className="agent-run-grid" disabled={mutation.isPending}>
          <legend className="sr-only">System dependency</legend>
          <label><span>Layer</span><select name="layer" value={dependency?.entity_type ?? entityType} disabled>
            <option value="logical_entity">Logical → Silver</option><option value="dimensional_entity">Dimensional → Gold</option>
          </select></label>
          <label><span>Source System code</span><select name="system" required defaultValue={dependency?.source_system.system_code ?? ""} disabled={Boolean(dependency) || systemsUnavailable}>
            {!dependency ? <option value="">Choose a System</option> : null}
            {systems.map((code) => <option key={code} value={code}>{code}</option>)}
          </select></label>
          <label><span>Dependency order</span><input name="order" type="number" min={0} step={1} required defaultValue={dependency?.dependency_order ?? 0} /></label>
        </fieldset>
        {!dependency && registeredSystems.isPending ? <p className="field-help" aria-busy="true">Loading Systems…</p>
          : !dependency && registeredSystems.isError ? <p className="inline-error" role="alert">Systems could not be loaded. Close and retry.</p>
          : !systems.length ? <p className="field-help">No source Systems are available for this layer.</p> : null}
        <p className="field-help">Lower orders run first. Systems at the same order have no ordering preference. Existing Mapping and lock rules are checked before saving.</p>
        {mutation.isError ? <p className="inline-error" role="alert">{mutation.error instanceof ApiError ? mutation.error.message : "The dependency could not be saved. Retry with the same values."}</p> : null}
        <footer className="dialog-actions"><button className="button button-secondary" type="button" disabled={mutation.isPending} onClick={onClose}>Cancel</button>
          <button className="button button-primary" type="submit" disabled={mutation.isPending || systemsUnavailable}>{mutation.isPending ? "Saving…" : "Save dependency"}</button>
        </footer>
      </form>
    </section>
  </div>;
}
