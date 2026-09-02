import type { HttpRequest } from "../../core/http";
import type { ModelsApi } from "../models/api";
import type { WorkflowsApi } from "../workflows/api";

export interface ValidationEligibleSystem {
  system_id: number;
  system_code: string;
  system_name: string;
  mapping_target_count: number;
  current_code_target_count: number;
  has_applied_validation: boolean;
}

export interface ValidationEligibleSystemCollection {
  model_id: number;
  model_revision: number;
  items: ValidationEligibleSystem[];
  is_truncated: boolean;
}

export type ValidationValidationSeverity = "blocking" | "warning" | "informational";

export interface ValidationValidationCheck {
  validation_check_id: number;
  validation_check_name: string;
  validation_check_description: string | null;
  validation_category_code: string;
  validation_severity: ValidationValidationSeverity;
  validation_query_sql: string;
  validation_comparison_query_sql: string | null;
  validation_result_data_type: string | null;
  validation_comparison_operator: string;
  validation_comparison_value_type: string;
  validation_comparison_value: unknown;
  is_active: boolean;
}

export interface ValidationValidationGroup {
  validation_group_id: number;
  system_id: number;
  system_code: string;
  validation_group_name: string;
  validation_group_description: string | null;
  mapping_context_is_current: boolean;
  code_context_is_current: boolean;
  validation_group_is_current: boolean;
  is_active: boolean;
  checks: ValidationValidationCheck[];
}

export interface ValidationLedger {
  model_id: number;
  model_revision: number;
  groups: ValidationValidationGroup[];
}

export interface ValidationTransport {
  listValidationEligibleSystems: (
    tenantId: number,
    modelId: number,
  ) => Promise<ValidationEligibleSystemCollection>;
  readValidationLedger: (
    tenantId: number,
    modelId: number,
  ) => Promise<ValidationLedger>;
}

export type ValidationApi = ValidationTransport
  & Pick<ModelsApi, "listModels">
  & Pick<
    WorkflowsApi,
    | "applyWorkflowDraft"
    | "createWorkflowRun"
    | "executeValidationRun"
    | "listWorkflowRunEvents"
    | "listWorkflowRuns"
    | "readAgentCapabilities"
    | "readWorkflowDraftReview"
    | "readWorkflowRun"
  >;

export function createValidationApi(request: HttpRequest): ValidationTransport {
  return {
    listValidationEligibleSystems: (tenantId, modelId) => request<ValidationEligibleSystemCollection>(
      `/api/v1/tenants/${tenantId}/models/${modelId}/validation/systems`,
    ),
    readValidationLedger: (tenantId, modelId) => request<ValidationLedger>(
      `/api/v1/tenants/${tenantId}/models/${modelId}/validation/ledger`,
    ),
  };
}

export const validationQueryKeys = {
  models: (tenantId: number) => ["validation-models", tenantId] as const,
  systems: (tenantId: number, modelId: number) => ["validation-systems", tenantId, modelId] as const,
  ledger: (tenantId: number, modelId: number) => ["validation-ledger", tenantId, modelId] as const,
};
