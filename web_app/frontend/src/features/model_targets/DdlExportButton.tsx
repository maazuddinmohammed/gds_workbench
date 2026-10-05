import { useMutation } from "@tanstack/react-query";
import { ApiError } from "../../core/http";
import type { ModelTargetsTransport, TargetLayer } from "./api";
import { targetError } from "./api";

export function DdlExportButton({ api, tenantId, modelId, modelRevision, layer, entityIds }: {
  api: Pick<ModelTargetsTransport, "exportModelDdl">;
  tenantId: number; modelId: number; modelRevision: number;
  layer: TargetLayer | "conceptual"; entityIds?: number[] | undefined;
}) {
  const download = useMutation({
    mutationFn: () => api.exportModelDdl(tenantId, modelId, {
      layer, expected_model_revision: modelRevision, ...(entityIds ? { entity_ids: entityIds } : {}),
    }),
    onSuccess: ({ blob, filename }) => {
      const url = URL.createObjectURL(blob);
      const link = document.createElement("a");
      link.href = url; link.download = filename; document.body.append(link); link.click(); link.remove();
      URL.revokeObjectURL(url);
    },
  });
  return <>
    <button type="button" className="button button-secondary button-small"
      disabled={download.isPending || (entityIds?.length ?? 0) > 200}
      title={layer === "conceptual" ? "Databricks table skeletons with an artificial ConceptID column" : "Download Databricks Delta table definitions"}
      onClick={() => download.mutate()}>{download.isPending ? "Exporting…" : "Export DDL"}</button>
    {download.isError ? <p role="alert">{download.error instanceof ApiError && download.error.code === "invalid_request"
      ? "Check Databricks-compatible names and column types. Schema/table names must fit 255 characters without spaces, dots, or slashes. Select up to 200 active Entities and 5,000 Attributes."
      : targetError(download.error)}</p> : null}
  </>;
}
