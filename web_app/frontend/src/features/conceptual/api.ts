import type { HttpRequest } from "../../core/http";
import type {
  ModelingCardinality,
  ModelingConfidence,
  ReviewStatus,
} from "../../shared/contracts";
import type { ModelInputScopeApi } from "../model_input_scope/api";
import type { WorkflowsApi } from "../workflows/api";

export type ConceptualStatus = ReviewStatus;
export type ConceptualConfidence = ModelingConfidence;
export type ConceptualCardinality = ModelingCardinality;

export interface ConceptualFilters {
  status?: ConceptualStatus;
  locked?: boolean;
  nameExact?: string;
  namePrefix?: string;
}

export interface ConceptualObject {
  conceptual_object_id: number;
  workflow_run_id: number | null;
  conceptual_object_name: string;
  conceptual_object_type: string;
  conceptual_object_confidence: ConceptualConfidence;
  conceptual_object_status: ConceptualStatus;
  conceptual_object_is_locked: boolean;
  updated_at: string;
}

export interface ConceptualObjectPage {
  model_id: number;
  model_revision: number;
  items: ConceptualObject[];
  next_cursor: string | null;
}

export interface ConceptualRelationship {
  conceptual_relationship_id: number;
  workflow_run_id: number | null;
  from_conceptual_object_id: number;
  from_conceptual_object_name: string;
  to_conceptual_object_id: number;
  to_conceptual_object_name: string;
  conceptual_relationship_name: string;
  conceptual_relationship_type: string;
  conceptual_relationship_cardinality: ConceptualCardinality;
  conceptual_relationship_confidence: ConceptualConfidence;
  conceptual_relationship_status: ConceptualStatus;
  conceptual_relationship_is_locked: boolean;
  updated_at: string;
}

export interface ConceptualRelationshipPage {
  model_id: number;
  model_revision: number;
  items: ConceptualRelationship[];
  next_cursor: string | null;
}

export interface ConceptualPhysicalObjectReference {
  object_id: number;
  tenant_code: string;
  system_code: string;
  connection_code: string;
  object_schema: string;
  object_name: string;
}

export interface ConceptualAssertionReference {
  modeling_assertion_record_id: number;
  modeling_assertion_record_key: string;
  modeling_assertion_document_name: string;
  modeling_assertion_record_type: string;
  modeling_assertion_text: string;
  modeling_assertion_confidence: ConceptualConfidence | null;
  modeling_assertion_record_status: ConceptualStatus;
}

interface ConceptualSupportBase {
  conceptual_support_id: number;
  workflow_run_id: number | null;
  support_role: string | null;
  support_reason: string;
  support_reason_detail: string | null;
  support_confidence: ConceptualConfidence;
  support_status: ConceptualStatus;
  support_is_locked: boolean;
  created_at: string;
  updated_at: string;
}

export interface ConceptualPhysicalSupport extends ConceptualSupportBase {
  support_source_type: "object";
  source_object: ConceptualPhysicalObjectReference;
}

export interface ConceptualAssertionSupport extends ConceptualSupportBase {
  support_source_type: "assertion";
  assertion_record: ConceptualAssertionReference;
}

export type ConceptualSupport = ConceptualPhysicalSupport | ConceptualAssertionSupport;

export interface ConceptualObjectDetail extends ConceptualObject {
  conceptual_object_definition: string;
  conceptual_object_grain: string;
  conceptual_object_aliases: string[];
  created_at: string;
  supports: ConceptualSupport[];
}

export interface ConceptualRelationshipDetail extends ConceptualRelationship {
  conceptual_relationship_definition: string;
  conceptual_relationship_basis: string;
  conceptual_relationship_cardinality_basis: string;
  created_at: string;
  supports: ConceptualSupport[];
}

export interface ConceptualTransport {
  listConceptualObjects: (
    tenantId: number,
    modelId: number,
    filters?: ConceptualFilters,
    pageSize?: number,
    cursor?: string,
  ) => Promise<ConceptualObjectPage>;
  readConceptualObject: (
    tenantId: number,
    modelId: number,
    conceptualObjectId: number,
  ) => Promise<ConceptualObjectDetail>;
  listConceptualRelationships: (
    tenantId: number,
    modelId: number,
    filters?: ConceptualFilters,
    pageSize?: number,
    cursor?: string,
  ) => Promise<ConceptualRelationshipPage>;
  readConceptualRelationship: (
    tenantId: number,
    modelId: number,
    conceptualRelationshipId: number,
  ) => Promise<ConceptualRelationshipDetail>;
}

export type ConceptualApi = ConceptualTransport
  & Pick<
    WorkflowsApi,
    | "applyWorkflowDraft"
    | "createWorkflowRun"
    | "executeConceptualRun"
    | "listWorkflowRunEvents"
    | "listWorkflowRuns"
    | "readAgentCapabilities"
    | "readWorkflowDraftReview"
    | "readWorkflowRun"
  >
  & Pick<ModelInputScopeApi, "listModelInputScope">;

export function createConceptualApi(request: HttpRequest): ConceptualTransport {
  return {
    listConceptualObjects: (tenantId, modelId, filters = {}, pageSize = 200, cursor) =>
      request<ConceptualObjectPage>(
        conceptualCollectionPath(tenantId, modelId, "objects", filters, pageSize, cursor),
      ),
    readConceptualObject: (tenantId, modelId, conceptualObjectId) =>
      request<ConceptualObjectDetail>(
        `/api/v1/tenants/${tenantId}/models/${modelId}/conceptual/objects/${conceptualObjectId}`,
      ),
    listConceptualRelationships: (tenantId, modelId, filters = {}, pageSize = 200, cursor) =>
      request<ConceptualRelationshipPage>(
        conceptualCollectionPath(
          tenantId,
          modelId,
          "relationships",
          filters,
          pageSize,
          cursor,
        ),
      ),
    readConceptualRelationship: (tenantId, modelId, conceptualRelationshipId) =>
      request<ConceptualRelationshipDetail>(
        `/api/v1/tenants/${tenantId}/models/${modelId}/conceptual/relationships/${conceptualRelationshipId}`,
      ),
  };
}

export const conceptualQueryKeys = {
  objects: (tenantId: number, modelId: number, filters: unknown) => (
    ["conceptual-objects", tenantId, modelId, filters] as const
  ),
  object: (tenantId: number, modelId: number, objectId: number) => (
    ["conceptual-object", tenantId, modelId, objectId] as const
  ),
  relationships: (tenantId: number, modelId: number, filters: unknown) => (
    ["conceptual-relationships", tenantId, modelId, filters] as const
  ),
  relationship: (tenantId: number, modelId: number, relationshipId: number) => (
    ["conceptual-relationship", tenantId, modelId, relationshipId] as const
  ),
};

function conceptualCollectionPath(
  tenantId: number,
  modelId: number,
  collection: "objects" | "relationships",
  filters: ConceptualFilters,
  pageSize: number,
  cursor: string | undefined,
): string {
  const query = new URLSearchParams();
  if (filters.status) query.set("status", filters.status);
  if (filters.locked !== undefined) query.set("locked", String(filters.locked));
  const nameExact = normalizeNaturalKeyFilter(filters.nameExact);
  const namePrefix = normalizeNaturalKeyFilter(filters.namePrefix);
  if (nameExact) query.set("name_exact", nameExact);
  if (namePrefix) query.set("name_prefix", namePrefix);
  query.set("page_size", String(pageSize));
  if (cursor) query.set("cursor", cursor);
  return `/api/v1/tenants/${tenantId}/models/${modelId}/conceptual/${collection}?${query}`;
}

function normalizeNaturalKeyFilter(value: string | undefined): string {
  return value?.replace(/^ +| +$/g, "").toLowerCase() ?? "";
}
