import { ApiError, type HttpRequest } from "../../core/http";
import { METADATA_XLSX_MEDIA_TYPE } from "../metadata/api";

export type TargetLayer = "logical" | "dimensional";
export interface TargetOptions {
  model_id: number;
  model_revision: number;
  placement: { tenant_code: string; system_code: string; connection_code: string; source_tenant_code: string } | null;
}
export interface ModelTargetsTransport {
  readTargetOptions: (tenantId: number, modelId: number) => Promise<TargetOptions>;
  exportModelTargets: (tenantId: number, modelId: number, command: { layer: TargetLayer; entity_ids?: number[]; expected_model_revision: number; object_type_code?: string }) => Promise<{ blob: Blob; filename: string }>;
}

export function createModelTargetsApi(request: HttpRequest): ModelTargetsTransport {
  const path = (tenantId: number, modelId: number) => `/api/v1/tenants/${tenantId}/models/${modelId}`;
  return {
    readTargetOptions: (tenantId, modelId) => request(`${path(tenantId, modelId)}/model-targets/options`),
    exportModelTargets: (tenantId, modelId, command) => request(`${path(tenantId, modelId)}/model-targets/export`, {
      method: "POST", headers: { "content-type": "application/json", accept: METADATA_XLSX_MEDIA_TYPE }, body: JSON.stringify(command),
    }, async (response) => {
      if (response.headers.get("content-type")?.split(";", 1)[0]?.trim().toLowerCase() !== METADATA_XLSX_MEDIA_TYPE) throw new ApiError(502, "invalid_response", null);
      const filename = /(?:^|;)\s*filename="([A-Za-z0-9._-]{1,180}\.xlsx)"\s*(?:;|$)/i.exec(response.headers.get("content-disposition") ?? "")?.[1];
      return { blob: await response.blob(), filename: filename ?? `gds_${command.layer}_registration.xlsx` };
    }),
  };
}

export function targetError(error: unknown): string {
  if (error instanceof ApiError) {
    if (error.code === "model_revision_conflict" || error.code === "review_conflict") return "The Model or target changed. Refresh and preview again.";
    if (error.code === "tenant_lock_required" || error.code === "tenant_locked") return "Acquire the Tenant Lock, then retry.";
    if (error.code === "tenant_workflow_conflict") return "Wait for the active Tenant workflow to finish, then refresh.";
    if (error.code === "authorization_denied") return "Your role cannot perform this action.";
    if (error.code === "invalid_request") return "Check the active Entities, schema, and GDS Connection. Exports support up to 200 Entities and 5,000 Attributes.";
  }
  return "The request could not be confirmed. Retry the same action or refresh before changing selections.";
}
