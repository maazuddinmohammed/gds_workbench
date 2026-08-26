import type { HttpRequest } from "../../core/http";
import type { ReviewStatus } from "../../shared/contracts";
import type { ModelScopeApi } from "../model_scope/api";
import type { WorkflowsApi } from "../workflows/api";

export type AnalysisValidationState = "validated" | "unvalidated";
export type AnalysisValidationResult = "supported" | "inconclusive" | "unsupported";

export interface AnalysisFilters {
  objectId?: number;
  validationState?: AnalysisValidationState;
  status?: ReviewStatus;
  locked?: boolean;
  showInactive?: boolean;
}

export interface AnalysisEndpoint {
  object_id: number;
  attribute_id: number;
  source_tenant_id: number;
  source_tenant_code: string;
  source_tenant_name: string;
  system_id: number;
  system_code: string;
  system_name: string;
  connection_id: number;
  connection_code: string;
  object_schema: string;
  object_name: string;
  attribute_name: string;
  attribute_data_type: string;
}

export interface AnalysisFinding {
  analysis_result_id: number;
  from_endpoint: AnalysisEndpoint;
  to_endpoint: AnalysisEndpoint;
  relationship_kind: string;
  relationship_confidence: "low" | "medium" | "high";
  validation_state: AnalysisValidationState;
  validation_result: AnalysisValidationResult | null;
  status: ReviewStatus;
  is_locked: boolean;
  updated_at: string;
}

export interface AnalysisFindingPage {
  model_id: number;
  model_revision: number;
  items: AnalysisFinding[];
  next_cursor: string | null;
}

export interface AnalysisEvidence {
  validation_policy_version: string;
  validation_policy_digest: string;
  result: AnalysisValidationResult;
  source_non_null_count: number;
  source_distinct_count: number;
  target_non_null_count: number;
  target_distinct_count: number;
  source_missing_target_count: number;
  unused_target_count: number;
  duplicate_target_key_count: number;
}

export interface AnalysisFindingDetail extends AnalysisFinding {
  relationship_basis: string;
  relationship_basis_truncated: boolean;
  evidence: AnalysisEvidence | null;
  provenance: {
    agent_run_id: string | null;
    inference_workflow_run_id: number | null;
    validation_workflow_run_id: number | null;
  };
  created_at: string;
}

export interface AnalysisTransport {
  listAnalysisFindings: (
    tenantId: number,
    modelId: number,
    filters?: AnalysisFilters,
    pageSize?: number,
    cursor?: string,
  ) => Promise<AnalysisFindingPage>;
  readAnalysisFinding: (
    tenantId: number,
    modelId: number,
    analysisResultId: number,
  ) => Promise<AnalysisFindingDetail>;
}

export type AnalysisApi = AnalysisTransport
  & Pick<
    WorkflowsApi,
    | "applyWorkflowDraft"
    | "createWorkflowRun"
    | "executeAnalysisInferenceRun"
    | "executeAnalysisValidationRun"
    | "listWorkflowRunEvents"
    | "listWorkflowRuns"
    | "readAgentCapabilities"
    | "readWorkflowDraftReview"
    | "readWorkflowRun"
  >
  & Pick<ModelScopeApi, "listModelScope">;

export function createAnalysisApi(request: HttpRequest): AnalysisTransport {
  return {
    listAnalysisFindings: (tenantId, modelId, filters = {}, pageSize = 200, cursor) => {
      const query = new URLSearchParams();
      if (filters.objectId) query.set("object_id", String(filters.objectId));
      if (filters.validationState) query.set("validation_state", filters.validationState);
      if (filters.status) query.set("status", filters.status);
      if (filters.locked !== undefined) query.set("locked", String(filters.locked));
      if (filters.showInactive) query.set("show_inactive", "true");
      query.set("page_size", String(pageSize));
      if (cursor) query.set("cursor", cursor);
      return request<AnalysisFindingPage>(
        `/api/v1/tenants/${tenantId}/models/${modelId}/analysis?${query}`,
      );
    },
    readAnalysisFinding: (tenantId, modelId, analysisResultId) =>
      request<AnalysisFindingDetail>(
        `/api/v1/tenants/${tenantId}/models/${modelId}/analysis/${analysisResultId}`,
      ),
  };
}

export const analysisQueryKeys = {
  findings: (tenantId: number, modelId: number, filters: unknown) => (
    ["analysis-findings", tenantId, modelId, filters] as const
  ),
  finding: (tenantId: number, modelId: number, findingId: number) => (
    ["analysis-finding", tenantId, modelId, findingId] as const
  ),
  runs: (tenantId: number, modelId: number, state: string) => (
    ["analysis-runs", tenantId, modelId, state] as const
  ),
  endpointOptions: (tenantId: number, modelId: number) => (
    ["analysis-endpoint-options", tenantId, modelId] as const
  ),
};
