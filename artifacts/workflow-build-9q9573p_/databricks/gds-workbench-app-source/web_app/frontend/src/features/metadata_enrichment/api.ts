import type { HttpRequest } from "../../core/http";
import type { WorkflowRunStart, WorkflowRunState } from "../workflows/api";

export type EnrichmentField = "object_description" | "attribute_description" | "attribute_inferred_data_type";
export type EnrichmentStatus = "applied" | "existing" | "locked" | "inactive" | "changed" | "unavailable" | "inconclusive";
export type EnrichmentEvidence = "agent_description" | "source_comment" | "registered_type" | "source_schema" | "bronze_schema" | "source_sample" | "bronze_sample" | "none";

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

export interface MetadataEnrichmentTransport {
  executeMetadataEnrichmentRun: (tenantId: number, modelId: number, runId: number,
    expectedModelRevision: number) => Promise<WorkflowRunStart>;
  readMetadataEnrichmentResults: (tenantId: number, modelId: number, runId: number,
    limit?: number, offset?: number) => Promise<MetadataEnrichmentResultPage>;
}

export const enrichmentResultKey = (tenantId: number, modelId: number, runId: number) => (
  ["metadata-enrichment-results", tenantId, modelId, runId] as const
);

export function createMetadataEnrichmentApi(request: HttpRequest): MetadataEnrichmentTransport {
  return {
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
