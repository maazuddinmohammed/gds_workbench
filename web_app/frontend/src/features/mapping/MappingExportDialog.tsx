import { useRef, useState } from "react";
import { useMutation } from "@tanstack/react-query";
import { ApiError } from "../../core/http";
import { trapDialogFocus, useDialogFocus } from "../../shared/dialog";
import type { ModelDetail } from "../models/api";
import type { MappingApi, MappingEntityType } from "./api";

export function MappingExportDialog({ api, tenantId, model, entityType, systemCodes, initialSystem, loading, unavailable, onClose }: {
  api: Pick<MappingApi, "exportMapping">; tenantId: number; model: ModelDetail; entityType: MappingEntityType;
  systemCodes: string[]; initialSystem?: string | undefined; loading: boolean; unavailable: boolean; onClose: () => void;
}) {
  const close = useRef<HTMLButtonElement>(null);
  useDialogFocus(close);
  const [revision] = useState(model.model_revision);
  const [system, setSystem] = useState(initialSystem ?? (systemCodes.length === 1 ? systemCodes[0]! : ""));
  const stale = revision !== model.model_revision;
  const download = useMutation({
    mutationFn: () => api.exportMapping(tenantId, model.model_id, revision, entityType, system),
    onSuccess: ({ blob, filename }) => {
      const url = URL.createObjectURL(blob);
      const link = document.createElement("a");
      link.href = url; link.download = filename; document.body.append(link); link.click(); link.remove(); URL.revokeObjectURL(url);
    },
  });
  return <div className="dialog-scrim" role="presentation">
    <section role="dialog" aria-modal="true" aria-labelledby="mapping-export-title" className="run-configuration-dialog" onKeyDown={(event) => {
      if (event.key === "Escape" && !download.isPending) { event.stopPropagation(); onClose(); }
      trapDialogFocus(event);
    }}>
      <header className="drawer-header"><h2 id="mapping-export-title">Export {entityType === "logical_entity" ? "Logical" : "Dimensional"} mappings</h2>
        <button ref={close} type="button" className="button button-secondary button-small" disabled={download.isPending} onClick={onClose}>Close</button>
      </header>
      <form className="target-export-form" onSubmit={(event) => { event.preventDefault(); if (system && !stale && !unavailable) download.mutate(); }}>
        <p>One workbook per System, one sheet per Entity. Includes all active saved mappings in this layer.</p>
        <label><span>System</span><select required value={system} disabled={loading || unavailable || download.isPending} onChange={(event) => { setSystem(event.target.value); download.reset(); }}>
          <option value="">Choose System</option>{systemCodes.map((code) => <option key={code} value={code}>{code}</option>)}
        </select></label>
        {loading ? <p aria-busy="true">Loading Systems…</p> : unavailable ? <p role="alert">Systems could not be loaded. Close and refresh.</p> : null}
        {stale ? <p role="alert">Model changed. Close and refresh before exporting.</p> : null}
        {download.isError ? <p role="alert">{download.error instanceof ApiError && download.error.status === 409 ? "Model changed. Close and refresh before exporting." : download.error instanceof ApiError && download.error.status === 403 ? "You do not have permission to export these mappings." : download.error instanceof ApiError && download.error.code === "invalid_request" ? "No workbook available. This System needs active mappings using standard templates within workbook limits." : "Mapping export could not be prepared. Close and refresh to try again."}</p> : null}
        {download.isSuccess ? <p role="status">Workbook downloaded.</p> : null}
        <button className="button button-primary" type="submit" disabled={!system || loading || unavailable || stale || download.isPending}>{download.isPending ? "Exporting…" : "Download XLSX"}</button>
      </form>
    </section>
  </div>;
}
