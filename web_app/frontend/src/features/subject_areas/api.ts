import type { HttpRequest } from "../../core/http";
import type { ReviewStatus } from "../../shared/contracts";
import type { ProjectInputScopeApi } from "../project_input_scope/api";
import type { ProjectRecordReviewApi } from "../project_record_review/api";
import type { WorkflowsApi } from "../workflows/api";

export interface SubjectAreaSummary {
  subject_area_id: number;
  workflow_run_id: number | null;
  subject_area_name: string;
  subject_area_definition: string;
  subject_area_status: ReviewStatus;
  subject_area_is_locked: boolean;
  table_count: number;
  column_count: number;
  updated_at: string;
}

export interface SubjectAreaPage {
  project_id: number;
  project_revision: number;
  max_subject_area_columns: number;
  scope_table_count: number;
  unassigned_table_count: number;
  items: SubjectAreaSummary[];
}

export interface SubjectAreaMembership {
  subject_area_id: number;
  subject_area_name: string;
  subject_area_table_id: number;
  subject_area_table_is_locked: boolean;
}

/** One active Bronze Input Scope table with the active areas it belongs to. */
export interface ScopeTable {
  object_id: number;
  tenant_code: string;
  system_code: string;
  connection_code: string;
  object_schema: string;
  object_name: string;
  object_description: string | null;
  zone_code: string;
  column_count: number;
  areas: SubjectAreaMembership[];
}

export interface ScopeTablePage {
  project_id: number;
  project_revision: number;
  items: ScopeTable[];
}

export interface SubjectAreaDetail extends SubjectAreaSummary {
  project_id: number;
  project_revision: number;
  max_subject_area_columns: number;
  tables: ScopeTable[];
}

/** One human change: create (name + definition), rename, define, add or remove tables. */
export interface SaveSubjectAreaCommand {
  expected_project_revision: number;
  subject_area_id?: number;
  subject_area_name?: string;
  subject_area_definition?: string;
  add_object_ids?: number[];
  remove_object_ids?: number[];
}

export interface SaveSubjectAreaResult {
  project_id: number;
  project_change_set_id: string;
  project_revision: number;
  action_count: number;
}

export interface SubjectAreaTransport {
  listSubjectAreas: (tenantId: number, projectId: number) => Promise<SubjectAreaPage>;
  listSubjectAreaScopeTables: (tenantId: number, projectId: number) => Promise<ScopeTablePage>;
  readSubjectArea: (
    tenantId: number,
    projectId: number,
    subjectAreaId: number,
  ) => Promise<SubjectAreaDetail>;
  saveSubjectArea: (
    tenantId: number,
    projectId: number,
    command: SaveSubjectAreaCommand,
    idempotencyKey: string,
  ) => Promise<SaveSubjectAreaResult>;
}

export type SubjectAreaApi = SubjectAreaTransport
  & ProjectRecordReviewApi
  & Pick<
    WorkflowsApi,
    | "applyWorkflowDraft"
    | "cancelWorkflowRun"
    | "createWorkflowRun"
    | "executeSubjectAreaRun"
    | "listWorkflowRunEvents"
    | "listWorkflowRuns"
    | "readAgentCapabilities"
    | "readWorkflowDraftReview"
    | "readWorkflowRun"
  >
  & Pick<ProjectInputScopeApi, "listProjectInputScope">;

export function createSubjectAreaApi(request: HttpRequest): SubjectAreaTransport {
  const base = (tenantId: number, projectId: number) => (
    `/api/v1/tenants/${tenantId}/projects/${projectId}/subject-areas`
  );
  return {
    listSubjectAreas: (tenantId, projectId) => request<SubjectAreaPage>(base(tenantId, projectId)),
    listSubjectAreaScopeTables: (tenantId, projectId) => request<ScopeTablePage>(
      `${base(tenantId, projectId)}/tables`,
    ),
    readSubjectArea: (tenantId, projectId, subjectAreaId) => request<SubjectAreaDetail>(
      `${base(tenantId, projectId)}/${subjectAreaId}`,
    ),
    saveSubjectArea: (tenantId, projectId, command, idempotencyKey) => request<SaveSubjectAreaResult>(
      `/api/v1/tenants/${tenantId}/projects/${projectId}/change-sets/review/subject-area`,
      {
        method: "POST",
        headers: { "content-type": "application/json", "Idempotency-Key": idempotencyKey },
        body: JSON.stringify(command),
      },
    ),
  };
}

export const subjectAreaQueryKeys = {
  all: (tenantId: number, projectId: number) => ["subject-areas", tenantId, projectId] as const,
  areas: (tenantId: number, projectId: number) => ["subject-areas", tenantId, projectId, "areas"] as const,
  tables: (tenantId: number, projectId: number) => ["subject-areas", tenantId, projectId, "tables"] as const,
  area: (tenantId: number, projectId: number, subjectAreaId: number) => (
    ["subject-areas", tenantId, projectId, "area", subjectAreaId] as const
  ),
};

export function tableLabel(table: Pick<ScopeTable, "object_schema" | "object_name">): string {
  return `${table.object_schema}.${table.object_name}`;
}
