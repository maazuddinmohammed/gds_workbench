import type { MappingEntityType } from "../mapping/api";
import type { ProjectRecordReviewApi } from "../project_record_review/api";
import type { HttpRequest } from "../../core/http";
import { readArchiveDownload, type ArchiveDownload, type LayerArchiveRequest } from "../../shared/archiveDownload";
import type { ProjectsApi } from "../projects/api";
import type { WorkflowsApi } from "../workflows/api";

export interface ValidationEligibleSystem {
  system_id: number;
  system_code: string;
  system_name: string;
  scope_target_count: number;
  mapping_target_count: number;
  current_code_target_count: number;
  has_applied_validation: boolean;
}

export interface ValidationEligibleSystemCollection {
  project_id: number;
  project_revision: number;
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
  is_locked: boolean;
}

export interface ValidationValidationGroup {
  validation_group_id: number;
  modeled_entity_type: MappingEntityType | null;
  system_id: number;
  system_code: string;
  validation_group_name: string;
  validation_group_description: string | null;
  mapping_context_is_current: boolean;
  code_context_is_current: boolean;
  validation_group_is_current: boolean;
  is_active: boolean;
  is_locked: boolean;
  checks: ValidationValidationCheck[];
}

export interface ValidationLedger {
  project_id: number;
  project_revision: number;
  groups: ValidationValidationGroup[];
}

export interface ValidationTransport {
  exportAllValidations: (
    tenantId: number,
    projectId: number,
    command: LayerArchiveRequest,
  ) => Promise<ArchiveDownload>;
  listValidationEligibleSystems: (
    tenantId: number,
    projectId: number,
    entityType?: MappingEntityType,
  ) => Promise<ValidationEligibleSystemCollection>;
  readValidationLedger: (
    tenantId: number,
    projectId: number,
    entityType?: MappingEntityType,
  ) => Promise<ValidationLedger>;
}

export type ValidationApi = ValidationTransport & ProjectRecordReviewApi
  & Pick<ProjectsApi, "listProjects">
  & Pick<
    WorkflowsApi,
    | "applyWorkflowDraft"
  | "cancelWorkflowRun"
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
    exportAllValidations: (tenantId, projectId, command) => request(
      `/api/v1/tenants/${tenantId}/projects/${projectId}/validation/downloads/all.zip`,
      { method: "POST", headers: { accept: "application/zip", "content-type": "application/json" }, body: JSON.stringify(command) },
      readArchiveDownload,
    ),
    listValidationEligibleSystems: (tenantId, projectId, entityType) => request<ValidationEligibleSystemCollection>(
      `/api/v1/tenants/${tenantId}/projects/${projectId}/validation/systems${entityType ? `?entity_type=${entityType}` : ""}`,
    ),
    readValidationLedger: (tenantId, projectId, entityType) => request<ValidationLedger>(
      `/api/v1/tenants/${tenantId}/projects/${projectId}/validation/ledger${entityType ? `?entity_type=${entityType}` : ""}`,
    ),
  };
}

export const validationQueryKeys = {
  systems: (tenantId: number, projectId: number, entityType?: MappingEntityType) => ["validation-systems", tenantId, projectId, entityType] as const,
  ledger: (tenantId: number, projectId: number, entityType?: MappingEntityType) => ["validation-ledger", tenantId, projectId, entityType] as const,
};
