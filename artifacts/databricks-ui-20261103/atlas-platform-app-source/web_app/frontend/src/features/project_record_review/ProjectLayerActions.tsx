import { useState } from "react";
import { useQueryClient } from "@tanstack/react-query";
import type { ProjectRecordReviewApi, ProjectReviewCommand } from "./api";
import { ReviewDialog } from "./ProjectRecordReview";

export function ProjectLayerActions({ api, tenantId, projectId, projectRevision, hasTenantLock, canDelete = false, layer, onApplied }: {
  api: ProjectRecordReviewApi; tenantId: number; projectId: number; projectRevision: number; hasTenantLock: boolean; canDelete?: boolean;
  layer: "subject_area" | "logical" | "dimensional"; onApplied: () => void;
}) {
  const [command, setCommand] = useState<ProjectReviewCommand | null>(null);
  const client = useQueryClient();
  return <>
    {canDelete ? <button className="button button-secondary button-small project-delete-action" type="button" disabled={!hasTenantLock}
      title={hasTenantLock ? undefined : "Tenant Lock required"}
      onClick={() => setCommand({ dataset: layer === "subject_area" ? "subject_area" : `${layer}_entity`,
        record_ids: [], layer, action: "delete", expected_project_revision: projectRevision })}>
      {layer === "subject_area" ? "Delete all Subject Areas" : `Clear ${layer} layer`}</button> : null}
    {command ? <ReviewDialog key={`${command.dataset}:${command.action}:${command.record_ids.join()}`} api={api}
      tenantId={tenantId} projectId={projectId} projectRevision={projectRevision} hasTenantLock={hasTenantLock}
      command={command} onReview={setCommand} onClose={() => setCommand(null)}
      onApplied={async () => { setCommand(null); onApplied(); await client.invalidateQueries({ predicate: (query) => query.queryKey[1] === tenantId }); }} /> : null}
  </>;
}
