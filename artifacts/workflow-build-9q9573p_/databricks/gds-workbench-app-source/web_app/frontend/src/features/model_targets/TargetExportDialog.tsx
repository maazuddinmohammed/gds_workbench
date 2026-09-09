import { useEffect, useRef, useState } from "react";
import { useMutation, useQuery } from "@tanstack/react-query";
import type { ModelTargetsTransport, TargetLayer } from "./api";
import { targetError } from "./api";

type ExportProps = {
  api: Pick<ModelTargetsTransport, "readTargetOptions" | "exportModelTargets">;
  tenantId: number; modelId: number; modelRevision: number;
  layer: TargetLayer; entityIds?: number[] | undefined;
};

export function TargetExportButton(props: ExportProps) {
  const [open, setOpen] = useState(false);
  return <><button className="button button-secondary button-small" type="button" onClick={() => setOpen(true)}>Export</button>
    {open ? <TargetExportDialog {...props} onClose={() => setOpen(false)} /> : null}</>;
}

export function TargetExportDialog({ api, tenantId, modelId, modelRevision, layer, entityIds, onClose }: ExportProps & { onClose: () => void }) {
  const options = useQuery({ queryKey: ["model-target-options", tenantId, modelId], queryFn: () => api.readTargetOptions(tenantId, modelId) });
  const [schema, setSchema] = useState("");
  const [exportRevision] = useState(modelRevision);
  const dialog = useRef<HTMLElement>(null);
  const schemaInput = useRef<HTMLInputElement>(null);
  const zone = layer === "logical" ? "Silver" : "Gold";
  const download = useMutation({
    mutationFn: () => api.exportModelTargets(tenantId, modelId, {
      layer, ...(entityIds ? { entity_ids: entityIds } : {}), expected_model_revision: exportRevision,
      object_schema: schema.trim(),
    }),
    onSuccess: (result) => {
      const url = URL.createObjectURL(result.blob);
      const link = document.createElement("a");
      link.href = url; link.download = result.filename; document.body.append(link); link.click(); link.remove();
      URL.revokeObjectURL(url);
    },
  });
  useEffect(() => {
    const previous = document.activeElement;
    schemaInput.current?.focus();
    return () => { if (previous instanceof HTMLElement && previous.isConnected) previous.focus(); };
  }, []);
  const stale = exportRevision !== modelRevision || (options.data !== undefined && exportRevision !== options.data.model_revision);
  return <div className="dialog-scrim" role="presentation">
    <section ref={dialog} role="dialog" aria-modal="true" aria-labelledby="target-export-heading" className="run-configuration-dialog" tabIndex={-1}
      onKeyDown={(event) => {
        if (event.key === "Escape" && !download.isPending) onClose();
        if (event.key !== "Tab") return;
        const elements = [...(dialog.current?.querySelectorAll<HTMLElement>("button, input, select, a[href]") ?? [])].filter((element) => !(element instanceof HTMLButtonElement || element instanceof HTMLInputElement || element instanceof HTMLSelectElement) || !element.disabled);
        if (event.shiftKey && (document.activeElement === elements[0] || document.activeElement === dialog.current)) { event.preventDefault(); elements.at(-1)?.focus(); }
        else if (!event.shiftKey && document.activeElement === elements.at(-1)) { event.preventDefault(); elements[0]?.focus(); }
      }}>
      <header className="drawer-header"><div><h2 id="target-export-heading">Export {zone} metadata</h2></div>
        <button className="button button-secondary button-small" type="button" disabled={download.isPending} onClick={onClose}>Close</button>
      </header>
      <form className="target-export-form" onSubmit={(event) => { event.preventDefault(); if (!stale) download.mutate(); }}>
        <p>{entityIds ? `${entityIds.length} selected ${entityIds.length === 1 ? "Entity" : "Entities"}` : "All active Entities"} · Objects and Attributes workbook.</p>
        <label>Target schema<input ref={schemaInput} required maxLength={400} value={schema} disabled={download.isPending} onChange={(event) => { setSchema(event.target.value); download.reset(); }} /></label>
        <p className="field-help">Upload this workbook in Metadata, then bind the registered {zone} Objects in Target Binding.</p>
        {options.isPending ? <p aria-busy="true">Checking target connection…</p> : options.isError ? <p role="alert">Could not load export settings. Close and retry.</p> : !options.data?.placement ? <p role="alert">Configure this Tenant’s GDS Connection before export.</p> : null}
        {stale ? <p role="alert">Model revision changed. Close and refresh before export.</p> : null}
        {download.isError ? <p role="alert">{targetError(download.error)}</p> : null}
        {download.isSuccess ? <p role="status">Workbook downloaded. Continue with Metadata registration.</p> : null}
        <button className="button button-primary" type="submit" disabled={download.isPending || stale || !schema.trim() || !options.data?.placement || options.isFetching || options.isError || (entityIds !== undefined && entityIds.length > 200)}>{download.isPending ? "Preparing workbook…" : "Download XLSX"}</button>
      </form>
    </section>
  </div>;
}
