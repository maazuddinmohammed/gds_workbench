import { useState } from "react";
import { useQueryClient } from "@tanstack/react-query";
import type { ModelRecordReviewApi, ModelReviewCommand } from "./api";
import { ReviewDialog } from "./ModelRecordReview";

export function ModelLayerActions({ api, tenantId, modelId, modelRevision, hasTenantLock, canDelete = false, layer, onApplied }: {
  api: ModelRecordReviewApi; tenantId: number; modelId: number; modelRevision: number; hasTenantLock: boolean; canDelete?: boolean;
  layer: "conceptual" | "logical" | "dimensional"; onApplied: () => void;
}) {
  const [command, setCommand] = useState<ModelReviewCommand | null>(null);
  const client = useQueryClient();
  return <>
    {canDelete ? <button className="button button-secondary button-small model-delete-action" type="button" disabled={!hasTenantLock}
      title={hasTenantLock ? undefined : "Tenant Lock required"}
      onClick={() => setCommand({ dataset: layer === "conceptual" ? "conceptual_object" : `${layer}_entity`,
        record_ids: [], layer, action: "delete", expected_model_revision: modelRevision })}>Clear {layer} layer</button> : null}
    {command ? <ReviewDialog key={`${command.dataset}:${command.action}:${command.record_ids.join()}`} api={api}
      tenantId={tenantId} modelId={modelId} modelRevision={modelRevision} hasTenantLock={hasTenantLock}
      command={command} onReview={setCommand} onClose={() => setCommand(null)}
      onApplied={async () => { setCommand(null); onApplied(); await client.invalidateQueries({ predicate: (query) => query.queryKey[1] === tenantId }); }} /> : null}
  </>;
}
