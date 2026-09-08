import type { HttpRequest } from "../../core/http";
import type { ReviewStatus } from "../../shared/contracts";

export type ModelReviewDataset =
  | "conceptual_object" | "conceptual_relationship"
  | "logical_submodel" | "logical_entity" | "logical_attribute" | "logical_relationship"
  | "dimensional_submodel" | "dimensional_entity" | "dimensional_attribute" | "dimensional_relationship"
  | "model_object_binding" | "model_attribute_binding" | "mapping_dependency" | "mapping_object" | "mapping_attribute"
  | "generated_code" | "generated_code_source_system" | "validation_group" | "validation_check";
export type ModelReviewAction = "lock" | "unlock" | "deactivate" | "reactivate";

export interface ModelReviewCommand {
  dataset: ModelReviewDataset;
  record_ids: number[];
  action: ModelReviewAction;
  expected_model_revision: number;
  expected_plan_digest?: string;
}

export interface ModelReviewPreview {
  model_id: number;
  model_revision: number;
  plan_digest: string;
  can_apply: boolean;
  action_count: number;
  additional_change_count: number;
  total_record_count: number;
  items: {
    dataset: ModelReviewDataset;
    record_id: number;
    label: string;
    selected: boolean;
    reason: string;
    is_locked: boolean;
    desired_locked: boolean;
    status: ReviewStatus;
    desired_status: ReviewStatus;
    changed: boolean;
  }[];
  issues: { code: string; dataset: string; message: string }[];
  issue_count: number;
  page: number;
  next_page: number | null;
}

export interface ModelRecordReviewApi {
  previewModelRecordReview: (
    tenantId: number, modelId: number, command: ModelReviewCommand, page?: number,
  ) => Promise<ModelReviewPreview>;
  applyModelRecordReview: (
    tenantId: number, modelId: number, command: ModelReviewCommand, idempotencyKey: string,
  ) => Promise<{
    model_id: number; model_revision: number; model_change_set_id: string; action_count: number;
  }>;
}

export interface ModelRecordHistoryPage {
  model_id: number; model_revision: number; dataset: ModelReviewDataset;
  items: { record_id: number; label: string; is_locked: boolean; status: ReviewStatus }[];
  next_page: number | null;
}

export interface ModelRecordHistoryApi extends ModelRecordReviewApi {
  listModelReviewRecords: (tenantId: number, modelId: number, dataset: ModelReviewDataset,
    modelRevision: number, page?: number) => Promise<ModelRecordHistoryPage>;
}

export function createModelRecordReviewApi(request: HttpRequest): ModelRecordHistoryApi {
  return {
    listModelReviewRecords: (tenantId, modelId, dataset, modelRevision, page = 1) => request(
      `/api/v1/tenants/${tenantId}/models/${modelId}/change-sets/review/records?dataset=${dataset}&expected_model_revision=${modelRevision}&page=${page}`,
    ),
    previewModelRecordReview: (tenantId, modelId, command, page = 1) => request(
      `/api/v1/tenants/${tenantId}/models/${modelId}/change-sets/review/preview?page=${page}`,
      { method: "POST", headers: { "content-type": "application/json" }, body: JSON.stringify(command) },
    ),
    applyModelRecordReview: (tenantId, modelId, command, idempotencyKey) => request(
      `/api/v1/tenants/${tenantId}/models/${modelId}/change-sets/review`,
      {
        method: "POST",
        headers: { "content-type": "application/json", "Idempotency-Key": idempotencyKey },
        body: JSON.stringify(command),
      },
    ),
  };
}
