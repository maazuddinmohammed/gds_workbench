import type { HttpRequest } from "../../core/http";
import type { ReviewStatus } from "../../shared/contracts";

export type ProjectReviewDataset =
  | "context_record"
  | "subject_area" | "subject_area_table"
  | "logical_entity" | "logical_attribute" | "logical_relationship"
  | "dimensional_entity" | "dimensional_attribute" | "dimensional_relationship"
  | "mapping_object" | "mapping_attribute"
  | "generated_code" | "generated_code_source_system" | "validation_group" | "validation_check";
export type ProjectReviewAction = "lock" | "unlock" | "deactivate" | "reactivate" | "delete";

export interface ProjectReviewCommand {
  dataset: ProjectReviewDataset;
  record_ids: (number | string)[];
  action: ProjectReviewAction;
  expected_project_revision: number;
  expected_plan_digest?: string;
  layer?: "subject_area" | "logical" | "dimensional";
}

export interface ProjectReviewPreview {
  project_id: number;
  project_revision: number;
  plan_digest: string;
  can_apply: boolean;
  action_count: number;
  additional_change_count: number;
  total_record_count: number;
  changes_by_dataset?: Record<string, number>;
  warnings?: string[];
  items: {
    dataset: string;
    record_id: number | string;
    label: string;
    selected: boolean;
    reason: string;
    is_locked: boolean;
    desired_locked: boolean;
    status: ReviewStatus;
    desired_status: ReviewStatus | "deleted";
    can_unlock?: boolean;
    changed: boolean;
  }[];
  issues: { code: string; dataset: string; message: string }[];
  issue_count: number;
  page: number;
  next_page: number | null;
}

export interface ProjectRecordReviewApi {
  previewProjectRecordReview: (
    tenantId: number, projectId: number, command: ProjectReviewCommand, page?: number,
  ) => Promise<ProjectReviewPreview>;
  applyProjectRecordReview: (
    tenantId: number, projectId: number, command: ProjectReviewCommand, idempotencyKey: string,
  ) => Promise<{
    project_id: number; project_revision: number; project_change_set_id: string; action_count: number;
  }>;
}

export interface ProjectRecordHistoryPage {
  project_id: number; project_revision: number; dataset: ProjectReviewDataset;
  items: { record_id: number | string; label: string; is_locked: boolean; status: ReviewStatus }[];
  next_page: number | null;
}

export interface ProjectRecordHistoryApi extends ProjectRecordReviewApi {
  listProjectReviewRecords: (tenantId: number, projectId: number, dataset: ProjectReviewDataset,
    projectRevision: number, page?: number, entityType?: "logical_entity" | "dimensional_entity") => Promise<ProjectRecordHistoryPage>;
}

export type EditableDataset = Extract<ProjectReviewDataset, `logical_${string}` | `dimensional_${string}`> | "mapping_object";
export interface ProjectRecordEditorRequest {
  dataset: EditableDataset; record_id: number; expected_project_revision: number;
  mapping_target?: { entity_type: "logical_entity" | "dimensional_entity"; entity_id: number; source_system_id: number };
}
export interface ProjectRecordEditor {
  mapping?: MappingEditorData | null;
  project_revision: number; label: string; is_locked: boolean;
  fields: { name: string; label: string; kind: "text" | "multiline" | "number" | "boolean" | "choice" | "lines";
    value: string | number | boolean | string[] | null; required: boolean; options: string[];
    minimum: number | null; maximum_length: number | null;
  }[];
}

export interface MappingSourceChoice {
  reference: Record<string, string>; label: string;
  columns: { name: string; data_type: string; reference: Record<string, string> }[];
}
export interface MappingEditorData {
  object_document: Record<string, unknown> | null; dependency_order: number;
  object_is_locked: boolean; structured: boolean;
  attributes: { name: string; data_type: string; ordinal: number; is_locked: boolean;
    document: Record<string, unknown> | null; structured: boolean }[];
  source_tables: MappingSourceChoice[];
}
export interface ProjectRecordEditorApi extends ProjectRecordHistoryApi {
  readProjectRecordEditor: (tenantId: number, projectId: number, command: ProjectRecordEditorRequest) => Promise<ProjectRecordEditor>;
  saveProjectRecord: (tenantId: number, projectId: number, command: ProjectRecordEditorRequest & { changes: Record<string, unknown> }, key: string) => Promise<{ project_revision: number }>;
}

export function createProjectRecordReviewApi(request: HttpRequest): ProjectRecordEditorApi {
  return {
    readProjectRecordEditor: (tenantId, projectId, command) => request(
      `/api/v1/tenants/${tenantId}/projects/${projectId}/change-sets/review/editor`,
      { method: "POST", headers: { "content-type": "application/json" }, body: JSON.stringify(command) },
    ),
    saveProjectRecord: (tenantId, projectId, command, key) => request(
      `/api/v1/tenants/${tenantId}/projects/${projectId}/change-sets/review/edit`,
      { method: "POST", headers: { "content-type": "application/json", "Idempotency-Key": key }, body: JSON.stringify(command) },
    ),
    listProjectReviewRecords: (tenantId, projectId, dataset, projectRevision, page = 1, entityType) => request(
      `/api/v1/tenants/${tenantId}/projects/${projectId}/change-sets/review/records?dataset=${dataset}&expected_project_revision=${projectRevision}&page=${page}${entityType ? `&entity_type=${entityType}` : ""}`,
    ),
    previewProjectRecordReview: (tenantId, projectId, command, page = 1) => request(
      `/api/v1/tenants/${tenantId}/projects/${projectId}/change-sets/review/preview?page=${page}`,
      { method: "POST", headers: { "content-type": "application/json" }, body: JSON.stringify(command) },
    ),
    applyProjectRecordReview: (tenantId, projectId, command, idempotencyKey) => request(
      `/api/v1/tenants/${tenantId}/projects/${projectId}/change-sets/review`,
      {
        method: "POST",
        headers: { "content-type": "application/json", "Idempotency-Key": idempotencyKey },
        body: JSON.stringify(command),
      },
    ),
  };
}
