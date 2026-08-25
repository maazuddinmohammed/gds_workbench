import type { HttpRequest } from "../../core/http";
import type { ModelWorkflow, WorkflowRunState } from "../workflows/api";

export type { ModelWorkflow, WorkflowRunState } from "../workflows/api";

export type ModelStatus = "active" | "archived";

export interface ModelLedgerRecord {
  model_id: number;
  model_name: string;
  model_description: string | null;
  model_revision: number;
  model_scope_object_count: number;
  latest_workflow: ModelWorkflow | null;
  latest_run_status: string | null;
  updated_at: string;
}

export interface ModelCollection {
  items: ModelLedgerRecord[];
  next_cursor: string | null;
}

export interface ModelDetail {
  model_id: number;
  tenant_id: number;
  model_name: string;
  model_description: string | null;
  model_revision: number;
  model_scope_object_count: number;
  silver_model_naming_instructions: string | null;
  silver_model_audit_columns_template: unknown;
  gold_model_naming_instructions: string | null;
  gold_model_technical_columns_template: unknown;
  gold_model_audit_columns_template: unknown;
  default_agent_sdk_code: string | null;
  default_agent_provider_code: string | null;
  default_agent_model_code: string | null;
  default_reasoning_effort_code: string | null;
  default_max_turns: number | null;
  default_validation_retry_count: number | null;
  is_active: boolean;
  updated_at: string;
}

export type LedgerWorkflow =
  | "scope"
  | "profiling"
  | "analysis"
  | "assertions"
  | "conceptual"
  | "logical"
  | "dimensional";

export type WorkflowLedgerState =
  | "empty"
  | "ready"
  | "not_started"
  | "queued"
  | "running"
  | "results_available"
  | "needs_review"
  | "completed_no_results"
  | "failed";

export type QualityWarningCode =
  | "scope_empty"
  | "profiling_results_unavailable"
  | "conceptual_results_unavailable"
  | "logical_results_unavailable";

export interface WorkflowLedgerEntry {
  workflow: LedgerWorkflow;
  result_count: number;
  needs_review_count: number;
  locked_count: number;
  latest_run_id: number | null;
  latest_run_state: WorkflowRunState | null;
  latest_run_created_at: string | null;
  state: WorkflowLedgerState;
  quality_warning_codes: QualityWarningCode[];
}

export interface ModelWorkflowOverview {
  model_id: number;
  model_revision: number;
  items: WorkflowLedgerEntry[];
}

export interface ModelsApi {
  listModels: (
    tenantId: number,
    status: ModelStatus,
    pageSize?: number,
    cursor?: string,
  ) => Promise<ModelCollection>;
  readModel: (tenantId: number, modelId: number) => Promise<ModelDetail>;
  readModelOverview: (
    tenantId: number,
    modelId: number,
  ) => Promise<ModelWorkflowOverview>;
}

export function createModelsApi(request: HttpRequest): ModelsApi {
  return {
    listModels: (tenantId, status, pageSize = 200, cursor) => {
      const query = new URLSearchParams({ status, page_size: String(pageSize) });
      if (cursor) query.set("cursor", cursor);
      return request<ModelCollection>(`/api/v1/tenants/${tenantId}/models?${query}`);
    },
    readModel: (tenantId, modelId) =>
      request<ModelDetail>(`/api/v1/tenants/${tenantId}/models/${modelId}`),
    readModelOverview: (tenantId, modelId) =>
      request<ModelWorkflowOverview>(
        `/api/v1/tenants/${tenantId}/models/${modelId}/overview`,
      ),
  };
}
