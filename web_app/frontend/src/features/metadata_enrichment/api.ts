import { createModelInputScopeApi, type ModelInputScopeApi } from "../model_input_scope/api";
export interface ReviewEnrichmentResult {
  review_event_id: number;
  action_count: number;
  records: Array<{ record_id: number; review_revision: string; is_active: boolean; is_locked: boolean }>;
}
import type { HttpRequest } from "../../core/http";
import type { WorkflowRunStart, WorkflowRunState } from "../workflows/api";

export type EnrichmentField = "object_description" | "attribute_description" | "attribute_inferred_data_type" | "is_natural_key" | "is_primary_key" | "is_nullable" | "is_pii";
export type EnrichmentStatus = "applied" | "existing" | "locked" | "inactive" | "changed" | "unavailable" | "inconclusive";
export type EnrichmentEvidence = "agent_key_inference" | "agent_description" | "source_comment" | "registered_type" | "source_schema" | "bronze_schema" | "source_sample" | "bronze_sample" | "none";

export interface MetadataEnrichmentResult {
  result_id: number;
  object_id: number;
  attribute_id: number | null;
  object_schema: string | null;
  object_name: string | null;
  attribute_name: string | null;
  storage_type: string | null;
  field_name: EnrichmentField;
  status: EnrichmentStatus;
  evidence_method: EnrichmentEvidence;
  applied_value: string | null;
  sample_count: number;
}

export interface MetadataEnrichmentResultPage {
  tenant_id: number;
  model_id: number;
  model_revision: number;
  workflow_run_id: number;
  workflow_run_state: WorkflowRunState;
  total_count: number;
  result_count: number;
  warning_count: number;
  counts: Partial<Record<EnrichmentStatus, number>>;
  applied_field_counts: Record<EnrichmentField, number>;
  results: MetadataEnrichmentResult[];
  limit: number;
  offset: number;
  next_offset: number | null;
}

export interface EnrichmentEditFields {
  attribute_inferred_data_type: string | null;
  is_natural_key: boolean | null;
  is_primary_key: boolean | null;
  is_nullable: boolean | null;
  is_pii: boolean | null;
}
export interface ReviewEnrichmentCommand {
  record_type: "object" | "attribute";
  action: "edit" | "lock" | "unlock";
  records: Array<{ record_id: number; expected_revision: string; description?: string | null } & Partial<EnrichmentEditFields>>;
}

export interface MetadataEnrichmentTransport {
  listEnrichmentObjects: ModelInputScopeApi["listModelInputScope"];
  readEnrichmentObject: ModelInputScopeApi["readModelInputScopeObject"];
  reviewEnrichment: (tenantId: number, modelId: number, modelRevision: number, command: ReviewEnrichmentCommand, key: string) => Promise<ReviewEnrichmentResult>;
  exportEnrichment: (tenantId: number, modelId: number) => Promise<{ blob: Blob; filename: string }>;
  executeMetadataEnrichmentRun: (tenantId: number, modelId: number, runId: number,
    expectedModelRevision: number) => Promise<WorkflowRunStart>;
  readMetadataEnrichmentResults: (tenantId: number, modelId: number, runId: number,
    limit?: number, offset?: number) => Promise<MetadataEnrichmentResultPage>;
}

export const enrichmentResultKey = (tenantId: number, modelId: number, runId: number) => (
  ["metadata-enrichment-results", tenantId, modelId, runId] as const
);

export function createMetadataEnrichmentApi(request: HttpRequest): MetadataEnrichmentTransport {
  const scope = createModelInputScopeApi((path, init, reader) => request(path.replace("/input-scope", "/metadata-enrichment/objects"), init, reader));
  return {
    listEnrichmentObjects: scope.listModelInputScope,
    readEnrichmentObject: scope.readModelInputScopeObject,
    reviewEnrichment: (tenantId, modelId, expectedModelRevision, command, key) => request(
      `/api/v1/tenants/${tenantId}/models/${modelId}/metadata-enrichment/review`,
      { method: "POST", headers: { "content-type": "application/json", "Idempotency-Key": key },
        body: JSON.stringify({ ...command, expected_model_revision: expectedModelRevision }) },
    ),
    exportEnrichment: (tenantId, modelId) => request(
      `/api/v1/tenants/${tenantId}/models/${modelId}/metadata-enrichment/export`,
      { headers: { accept: "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet" } },
      async (response) => ({ blob: await response.blob(), filename: /filename="([^"\r\n]+)"/.exec(response.headers.get("content-disposition") ?? "")?.[1] ?? "Model_Enrichment.xlsx" }),
    ),
    executeMetadataEnrichmentRun: (tenantId, modelId, runId, expectedModelRevision) => request(
      `/api/v1/tenants/${tenantId}/models/${modelId}/metadata-enrichment/runs/${runId}/execute`,
      { method: "POST", headers: { "content-type": "application/json" }, body: JSON.stringify({
        execution_mode: "one_shot", expected_model_revision: expectedModelRevision,
      }) },
    ),
    readMetadataEnrichmentResults: (tenantId, modelId, runId, limit = 100, offset = 0) => request(
      `/api/v1/tenants/${tenantId}/models/${modelId}/runs/${runId}/metadata-enrichment?limit=${limit}&offset=${offset}`,
    ),
  };
}
