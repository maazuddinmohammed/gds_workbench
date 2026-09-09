import type { ModelRecordHistoryApi } from "../model_record_review/api";
import { ApiError, type HttpRequest } from "../../core/http";
import { METADATA_XLSX_MEDIA_TYPE } from "../metadata/api";

export type TargetLayer = "logical" | "dimensional";
export interface TargetOptions {
  model_id: number;
  model_revision: number;
  placement: { tenant_code: string; system_code: string; connection_code: string; source_tenant_code: string } | null;
  object_types: { code: string; name: string }[];
  schemas: { layer: TargetLayer; object_schema: string }[];
}
export interface RegisteredTarget {
  object_id: number;
  object_schema: string;
  object_name: string;
  connection_code: string;
  matching_entity_ids?: number[];
  bound_entity_ids?: number[];
}
export interface AttributeAssignment { modeled_attribute_id: number; attribute_id: number }
export interface BindingCommand {
  layer: TargetLayer;
  entity_id: number;
  object_id: number;
  expected_model_revision: number;
  assignments?: AttributeAssignment[];
}
export interface BindingPreview {
  binding_id?: number | null;
  is_locked?: boolean;
  model_id: number;
  model_revision: number;
  entity_name: string;
  target: RegisteredTarget;
  assignments: { binding_id?: number | null; is_locked?: boolean; modeled_attribute_id: number; modeled_attribute_name: string; modeled_data_type: string; attribute_id: number | null }[];
  target_attributes: { attribute_id: number; attribute_name: string; data_type: string }[];
  can_apply: boolean;
  action_count: number;
  issues: string[];
  plan_digest: string;
}
export interface BindingReceipt { model_id: number; model_revision: number; model_change_set_id: string; action_count: number }
export interface TargetBindingRow {
  entity_id: number; entity_name: string; binding_id: number | null; object_id: number | null;
  object_schema: string | null; object_name: string | null; is_locked: boolean;
}
export interface GenerateBindingCommand { layer: TargetLayer; expected_model_revision: number; object_schema: string; expected_plan_digest?: string }
export interface GeneratedBindingsPreview {
  model_id: number; model_revision: number; object_schema: string;
  matches: { entity_id: number; entity_name: string; object_id: number | null; object_name: string | null;
    status: "matched" | "unmatched" | "ambiguous" | "locked" | "existing" | "incompatible"; issues: string[] }[];
  can_apply: boolean; action_count: number; plan_digest: string; issues: string[];
}
export interface ModelTargetsTransport {
  listTargetBindings: (tenantId: number, modelId: number, layer: TargetLayer, after?: number) => Promise<{ model_id: number; model_revision: number; items: TargetBindingRow[]; next_after: number | null }>;
  generateBindings: (tenantId: number, modelId: number, command: GenerateBindingCommand) => Promise<GeneratedBindingsPreview>;
  applyGeneratedBindings: (tenantId: number, modelId: number, command: GenerateBindingCommand & { expected_plan_digest: string }, key: string) => Promise<BindingReceipt>;
  readTargetOptions: (tenantId: number, modelId: number) => Promise<TargetOptions>;
  listRegisteredTargets: (tenantId: number, modelId: number, layer: TargetLayer, search: string, after?: number, objectSchema?: string) => Promise<{ items: RegisteredTarget[]; next_after: number | null }>;
  exportModelTargets: (tenantId: number, modelId: number, command: { layer: TargetLayer; entity_ids?: number[]; expected_model_revision: number; object_schema: string; object_type_code?: string }) => Promise<{ blob: Blob; filename: string }>;
  previewModelBinding: (tenantId: number, modelId: number, command: BindingCommand) => Promise<BindingPreview>;
  applyModelBinding: (tenantId: number, modelId: number, command: BindingCommand & { assignments: AttributeAssignment[]; expected_plan_digest: string }, key: string) => Promise<BindingReceipt>;
}
export type ModelTargetsApi = ModelTargetsTransport & ModelRecordHistoryApi;

export function createModelTargetsApi(request: HttpRequest): ModelTargetsTransport {
  const path = (tenantId: number, modelId: number) => `/api/v1/tenants/${tenantId}/models/${modelId}`;
  return {
    listTargetBindings: (tenantId, modelId, layer, after = 0) => request(`${path(tenantId, modelId)}/model-targets/bindings?${new URLSearchParams({ layer, after: String(after) })}`),
    generateBindings: (tenantId, modelId, command) => request(`${path(tenantId, modelId)}/change-sets/bindings/generate/preview`, { method: "POST", headers: { "content-type": "application/json" }, body: JSON.stringify(command) }),
    applyGeneratedBindings: (tenantId, modelId, command, key) => request(`${path(tenantId, modelId)}/change-sets/bindings/generate/apply`, { method: "POST", headers: { "content-type": "application/json", "Idempotency-Key": key }, body: JSON.stringify(command) }),
    readTargetOptions: (tenantId, modelId) => request(`${path(tenantId, modelId)}/model-targets/options`),
    listRegisteredTargets: (tenantId, modelId, layer, search, after = 0, objectSchema) => request(`${path(tenantId, modelId)}/model-targets?${new URLSearchParams({ layer, search, after: String(after), ...(objectSchema ? { object_schema: objectSchema } : {}) })}`),
    exportModelTargets: (tenantId, modelId, command) => request(`${path(tenantId, modelId)}/model-targets/export`, {
      method: "POST", headers: { "content-type": "application/json", accept: METADATA_XLSX_MEDIA_TYPE }, body: JSON.stringify(command),
    }, async (response) => {
      if (response.headers.get("content-type")?.split(";", 1)[0]?.trim().toLowerCase() !== METADATA_XLSX_MEDIA_TYPE) throw new ApiError(502, "invalid_response", null);
      const filename = /(?:^|;)\s*filename="([A-Za-z0-9._-]{1,180}\.xlsx)"\s*(?:;|$)/i.exec(response.headers.get("content-disposition") ?? "")?.[1];
      return { blob: await response.blob(), filename: filename ?? `gds_${command.layer}_registration.xlsx` };
    }),
    previewModelBinding: (tenantId, modelId, command) => request(`${path(tenantId, modelId)}/change-sets/bindings/preview`, { method: "POST", headers: { "content-type": "application/json" }, body: JSON.stringify(command) }),
    applyModelBinding: (tenantId, modelId, command, key) => request(`${path(tenantId, modelId)}/change-sets/bindings/apply`, { method: "POST", headers: { "content-type": "application/json", "Idempotency-Key": key }, body: JSON.stringify(command) }),
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
