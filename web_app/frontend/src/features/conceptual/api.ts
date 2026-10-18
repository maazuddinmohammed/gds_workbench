import type { ProjectTargetsTransport } from "../project_targets/api";
import type { HttpRequest } from "../../core/http";
import type {
  ModelingCardinality,
  ReviewStatus,
} from "../../shared/contracts";
import type { ProjectInputScopeApi } from "../project_input_scope/api";
import type { WorkflowsApi } from "../workflows/api";
import type { ProjectRecordReviewApi } from "../project_record_review/api";

export type ConceptualStatus = ReviewStatus;
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
  conceptual_object_status: ConceptualStatus;
  conceptual_object_is_locked: boolean;
  updated_at: string;
}

export interface ConceptualObjectPage {
  project_id: number;
  project_revision: number;
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
  conceptual_relationship_status: ConceptualStatus;
  conceptual_relationship_is_locked: boolean;
  updated_at: string;
}

export interface ConceptualRelationshipPage {
  project_id: number;
  project_revision: number;
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

export interface ConceptualContextReference {
  context_record_id: string;
  context_group_name: string;
  context_type_name: string;
  context_text: string;
  source_reference: string | null;
  status: ConceptualStatus;
}

interface ConceptualSupportBase {
  conceptual_support_id: number;
  workflow_run_id: number | null;
  support_role: string | null;
  support_reason: string;
  support_reason_detail: string | null;
  support_status: ConceptualStatus;
  support_is_locked: boolean;
  created_at: string;
  updated_at: string;
}

export interface ConceptualPhysicalSupport extends ConceptualSupportBase {
  support_source_type: "object";
  source_object: ConceptualPhysicalObjectReference;
}

export interface ConceptualContextSupport extends ConceptualSupportBase {
  support_source_type: "context_record";
  context_record: ConceptualContextReference;
}

export type ConceptualSupport = ConceptualPhysicalSupport | ConceptualContextSupport;

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
    projectId: number,
    filters?: ConceptualFilters,
    pageSize?: number,
    cursor?: string,
  ) => Promise<ConceptualObjectPage>;
  readConceptualObject: (
    tenantId: number,
    projectId: number,
    conceptualObjectId: number,
  ) => Promise<ConceptualObjectDetail>;
  listConceptualRelationships: (
    tenantId: number,
    projectId: number,
    filters?: ConceptualFilters,
    pageSize?: number,
    cursor?: string,
  ) => Promise<ConceptualRelationshipPage>;
  readConceptualRelationship: (
    tenantId: number,
    projectId: number,
    conceptualRelationshipId: number,
  ) => Promise<ConceptualRelationshipDetail>;
}

export type ConceptualApi = Pick<ProjectTargetsTransport, "exportProjectDdl"> & ConceptualTransport
  & ProjectRecordReviewApi
  & Pick<
    WorkflowsApi,
    | "applyWorkflowDraft"
  | "cancelWorkflowRun"
    | "createWorkflowRun"
    | "executeConceptualRun"
    | "listWorkflowRunEvents"
    | "listWorkflowRuns"
    | "readAgentCapabilities"
    | "readWorkflowDraftReview"
    | "readWorkflowRun"
  >
  & Pick<ProjectInputScopeApi, "listProjectInputScope">;

export function createConceptualApi(request: HttpRequest): ConceptualTransport {
  return {
    listConceptualObjects: (tenantId, projectId, filters = {}, pageSize = 200, cursor) =>
      request<ConceptualObjectPage>(
        conceptualCollectionPath(tenantId, projectId, "objects", filters, pageSize, cursor),
      ),
    readConceptualObject: (tenantId, projectId, conceptualObjectId) =>
      request<ConceptualObjectDetail>(
        `/api/v1/tenants/${tenantId}/projects/${projectId}/conceptual/objects/${conceptualObjectId}`,
      ),
    listConceptualRelationships: (tenantId, projectId, filters = {}, pageSize = 200, cursor) =>
      request<ConceptualRelationshipPage>(
        conceptualCollectionPath(
          tenantId,
          projectId,
          "relationships",
          filters,
          pageSize,
          cursor,
        ),
      ),
    readConceptualRelationship: (tenantId, projectId, conceptualRelationshipId) =>
      request<ConceptualRelationshipDetail>(
        `/api/v1/tenants/${tenantId}/projects/${projectId}/conceptual/relationships/${conceptualRelationshipId}`,
      ),
  };
}

export const conceptualQueryKeys = {
  objects: (tenantId: number, projectId: number, filters: unknown) => (
    ["conceptual-objects", tenantId, projectId, filters] as const
  ),
  object: (tenantId: number, projectId: number, objectId: number) => (
    ["conceptual-object", tenantId, projectId, objectId] as const
  ),
  relationships: (tenantId: number, projectId: number, filters: unknown) => (
    ["conceptual-relationships", tenantId, projectId, filters] as const
  ),
  relationship: (tenantId: number, projectId: number, relationshipId: number) => (
    ["conceptual-relationship", tenantId, projectId, relationshipId] as const
  ),
};

function conceptualCollectionPath(
  tenantId: number,
  projectId: number,
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
  return `/api/v1/tenants/${tenantId}/projects/${projectId}/conceptual/${collection}?${query}`;
}

function normalizeNaturalKeyFilter(value: string | undefined): string {
  return value?.replace(/^ +| +$/g, "").toLowerCase() ?? "";
}
