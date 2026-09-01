import type { HttpRequest } from "../../core/http";
import type { ModelsApi } from "../models/api";
import type { WorkflowsApi } from "../workflows/api";

export interface QAEligibleSystem {
  system_id: number;
  system_code: string;
  system_name: string;
  mapping_target_count: number;
  current_code_target_count: number;
  has_applied_qa: boolean;
}

export interface QAEligibleSystemCollection {
  model_id: number;
  model_revision: number;
  items: QAEligibleSystem[];
  is_truncated: boolean;
}

export type QAValidationSeverity = "blocking" | "warning" | "informational";

export interface QAValidationCheck {
  validation_check_id: number;
  validation_check_name: string;
  validation_check_description: string | null;
  validation_category_code: string;
  validation_severity: QAValidationSeverity;
  validation_query_sql: string;
  validation_comparison_query_sql: string | null;
  validation_result_data_type: string | null;
  validation_comparison_operator: string;
  validation_comparison_value_type: string;
  validation_comparison_value: unknown;
  is_active: boolean;
}

export interface QAValidationGroup {
  validation_group_id: number;
  system_id: number;
  system_code: string;
  validation_group_name: string;
  validation_group_description: string | null;
  mapping_context_digest: string;
  code_context_digest: string | null;
  current_mapping_context_digest: string | null;
  current_code_context_digest: string | null;
  mapping_context_is_current: boolean;
  code_context_is_current: boolean;
  validation_group_is_current: boolean;
  is_active: boolean;
  checks: QAValidationCheck[];
}

export interface QALedger {
  model_id: number;
  model_revision: number;
  groups: QAValidationGroup[];
}

export interface QATransport {
  listQAEligibleSystems: (
    tenantId: number,
    modelId: number,
  ) => Promise<QAEligibleSystemCollection>;
  readQALedger: (
    tenantId: number,
    modelId: number,
  ) => Promise<QALedger>;
}

export type QAApi = QATransport
  & Pick<ModelsApi, "listModels">
  & Pick<
    WorkflowsApi,
    | "applyWorkflowDraft"
    | "createWorkflowRun"
    | "executeQARun"
    | "listWorkflowRunEvents"
    | "listWorkflowRuns"
    | "readAgentCapabilities"
    | "readWorkflowDraftReview"
    | "readWorkflowRun"
  >;

export function createQAApi(request: HttpRequest): QATransport {
  return {
    listQAEligibleSystems: (tenantId, modelId) => request<QAEligibleSystemCollection>(
      `/api/v1/tenants/${tenantId}/models/${modelId}/qa/systems`,
    ),
    readQALedger: (tenantId, modelId) => request<QALedger>(
      `/api/v1/tenants/${tenantId}/models/${modelId}/qa/ledger`,
    ),
  };
}

export const qaQueryKeys = {
  models: (tenantId: number) => ["qa-models", tenantId] as const,
  systems: (tenantId: number, modelId: number) => ["qa-systems", tenantId, modelId] as const,
  ledger: (tenantId: number, modelId: number) => ["qa-ledger", tenantId, modelId] as const,
};
