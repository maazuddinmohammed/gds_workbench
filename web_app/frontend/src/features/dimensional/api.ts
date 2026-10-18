import type { LogicalTransport } from "../logical/api";
import type { ProjectTargetsTransport } from "../project_targets/api";
import type { ProjectRecordHistoryApi } from "../project_record_review/api";
import type { HttpRequest } from "../../core/http";
import type {
  ModelingCardinality,
  ModelingConfidence,
  ReviewStatus,
} from "../../shared/contracts";
import type { ProjectInputScopeApi } from "../project_input_scope/api";
import type { WorkflowsApi } from "../workflows/api";

export interface DimensionalFilters {
  status?: ReviewStatus;
  locked?: boolean;
  nameExact?: string;
  namePrefix?: string;
}

export interface DimensionalObject {
  dimensional_entity_id: number;
  workflow_run_id: number | null;
  dimensional_entity_schema_name: string;
  dimensional_entity_name: string;
  dimensional_entity_type: "fact" | "dimension" | "bridge";
  dimensional_fact_type:
    | "transaction"
    | "periodic_snapshot"
    | "accumulating_snapshot"
    | "factless"
    | null;
  dimensional_entity_dependency_order: number;
  dimensional_entity_confidence: ModelingConfidence;
  dimensional_entity_status: ReviewStatus;
  dimensional_entity_is_locked: boolean;
  updated_at: string;
}

export interface DimensionalObjectPage {
  project_id: number;
  project_revision: number;
  items: DimensionalObject[];
  next_cursor: string | null;
}

export interface DimensionalSubmodelMembership {
  dimensional_entity_submodel_id: number;
  workflow_run_id: number | null;
  dimensional_submodel_id: number;
  dimensional_submodel_name: string;
  membership_status: ReviewStatus;
  membership_is_locked: boolean;
  created_at: string;
  updated_at: string;
}

export interface DimensionalLogicalEntityReference {
  logical_entity_id: number;
  logical_entity_schema_name: string;
  logical_entity_name: string;
}

export interface DimensionalContextReference {
  context_record_id: string;
  context_group_name: string;
  context_type_name: string;
  context_text: string;
  source_reference: string | null;
  status: ReviewStatus;
}

interface DimensionalObjectSourceBase {
  dimensional_entity_source_mapping_id: number;
  workflow_run_id: number | null;
  source_role: string;
  source_order: number | null;
  rationale: string;
  status: ReviewStatus;
  is_locked: boolean;
  created_at: string;
  updated_at: string;
}

export interface DimensionalLogicalEntitySource extends DimensionalObjectSourceBase {
  support_source_type: "logical_entity";
  source_logical_entity: DimensionalLogicalEntityReference;
}

export interface DimensionalContextSource extends DimensionalObjectSourceBase {
  support_source_type: "context_record";
  context_record: DimensionalContextReference;
}

export type DimensionalObjectSource = DimensionalLogicalEntitySource | DimensionalContextSource;

export interface DimensionalObjectDetail extends DimensionalObject {
  dimensional_entity_definition: string;
  dimensional_entity_grain_definition: string | null;
  created_at: string;
  submodels: DimensionalSubmodelMembership[];
  sources: DimensionalObjectSource[];
}

export interface DimensionalAttributeFilters extends DimensionalFilters {
  dimensionalEntityId?: number;
}

export interface DimensionalAttribute {
  dimensional_attribute_id: number;
  workflow_run_id: number | null;
  dimensional_entity_id: number;
  dimensional_entity_schema_name: string;
  dimensional_entity_name: string;
  dimensional_attribute_name: string;
  dimensional_attribute_data_type: string;
  dimensional_attribute_is_nullable: boolean;
  dimensional_attribute_ordinal_position: number;
  dimensional_attribute_role:
    | "key"
    | "descriptor"
    | "measure"
    | "degenerate_dimension"
    | "bridge_weight"
    | "technical"
    | "audit";
  dimensional_attribute_key_role: "none" | "surrogate" | "business" | "foreign";
  dimensional_attribute_is_grain_component: boolean;
  dimensional_attribute_additivity: "additive" | "semi_additive" | "non_additive" | null;
  dimensional_attribute_default_aggregation: string | null;
  dimensional_attribute_change_behavior: "fixed" | "overwrite" | "historize" | null;
  dimensional_attribute_is_audit_column: boolean;
  dimensional_attribute_confidence: ModelingConfidence;
  dimensional_attribute_status: ReviewStatus;
  dimensional_attribute_is_locked: boolean;
  updated_at: string;
}

export interface DimensionalAttributePage {
  project_id: number;
  project_revision: number;
  items: DimensionalAttribute[];
  next_cursor: string | null;
}

export interface DimensionalLogicalAttributeReference extends DimensionalLogicalEntityReference {
  logical_attribute_id: number;
  logical_attribute_name: string;
}

interface DimensionalAttributeSourceBase {
  dimensional_attribute_source_mapping_id: number;
  workflow_run_id: number | null;
  source_order: number | null;
  rationale: string;
  status: ReviewStatus;
  is_locked: boolean;
  created_at: string;
  updated_at: string;
}

export interface DimensionalLogicalAttributeSource extends DimensionalAttributeSourceBase {
  dimensional_entity_source_mapping_id: number;
  support_source_type: "logical_attribute";
  source_logical_attribute: DimensionalLogicalAttributeReference;
}

export interface DimensionalAttributeContextSource extends DimensionalAttributeSourceBase {
  support_source_type: "context_record";
  context_record: DimensionalContextReference;
}

export type DimensionalAttributeSource =
  | DimensionalLogicalAttributeSource
  | DimensionalAttributeContextSource;

export interface DimensionalAttributeDetail extends DimensionalAttribute {
  dimensional_attribute_definition: string;
  dimensional_attribute_aggregation_basis: string | null;
  created_at: string;
  sources: DimensionalAttributeSource[];
}

export interface DimensionalRelationshipFilters extends DimensionalFilters {
  dimensionalEntityId?: number;
}

export interface DimensionalRelationship {
  dimensional_relationship_id: number;
  workflow_run_id: number | null;
  from_dimensional_entity_id: number;
  from_dimensional_entity_schema_name: string;
  from_dimensional_entity_name: string;
  from_dimensional_attribute_id: number;
  from_dimensional_attribute_name: string;
  to_dimensional_entity_id: number;
  to_dimensional_entity_schema_name: string;
  to_dimensional_entity_name: string;
  to_dimensional_attribute_id: number;
  to_dimensional_attribute_name: string;
  dimensional_relationship_name: string;
  dimensional_relationship_kind: string;
  dimensional_relationship_cardinality: ModelingCardinality;
  dimensional_relationship_is_optional: boolean;
  dimensional_relationship_role_name: string | null;
  dimensional_relationship_confidence: ModelingConfidence;
  dimensional_relationship_status: ReviewStatus;
  dimensional_relationship_is_locked: boolean;
  updated_at: string;
}

export interface DimensionalRelationshipPage {
  project_id: number;
  project_revision: number;
  items: DimensionalRelationship[];
  next_cursor: string | null;
}

export interface DimensionalRelationshipDetail extends DimensionalRelationship {
  dimensional_relationship_definition: string;
  dimensional_relationship_basis: string;
  dimensional_relationship_cardinality_basis: string;
  created_at: string;
}

export interface DimensionalTransport {
  listDimensionalObjects: (
    tenantId: number,
    projectId: number,
    filters?: DimensionalFilters,
    pageSize?: number,
    cursor?: string,
  ) => Promise<DimensionalObjectPage>;
  readDimensionalObject: (
    tenantId: number,
    projectId: number,
    dimensionalEntityId: number,
  ) => Promise<DimensionalObjectDetail>;
  listDimensionalAttributes: (
    tenantId: number,
    projectId: number,
    filters?: DimensionalAttributeFilters,
    pageSize?: number,
    cursor?: string,
  ) => Promise<DimensionalAttributePage>;
  readDimensionalAttribute: (
    tenantId: number,
    projectId: number,
    dimensionalAttributeId: number,
  ) => Promise<DimensionalAttributeDetail>;
  listDimensionalRelationships: (
    tenantId: number,
    projectId: number,
    filters?: DimensionalRelationshipFilters,
    pageSize?: number,
    cursor?: string,
  ) => Promise<DimensionalRelationshipPage>;
  readDimensionalRelationship: (
    tenantId: number,
    projectId: number,
    dimensionalRelationshipId: number,
  ) => Promise<DimensionalRelationshipDetail>;
}

export type DimensionalApi = Pick<LogicalTransport, "listLogicalEntities"> & DimensionalTransport & Pick<ProjectTargetsTransport, "readTargetOptions" | "exportProjectTargets" | "exportProjectDdl"> & ProjectRecordHistoryApi
  & Pick<
    WorkflowsApi,
    | "applyWorkflowDraft"
  | "cancelWorkflowRun"
    | "createWorkflowRun"
    | "executeDimensionalRun"
    | "listWorkflowRunEvents"
    | "listWorkflowRuns"
    | "readAgentCapabilities"
    | "readWorkflowDraftReview"
    | "readWorkflowRun"
  >
  & Pick<ProjectInputScopeApi, "listProjectInputScope">;

export function createDimensionalApi(request: HttpRequest): DimensionalTransport {
  return {
    listDimensionalObjects: (tenantId, projectId, filters = {}, pageSize = 200, cursor) =>
      request<DimensionalObjectPage>(
        dimensionalCollectionPath(tenantId, projectId, "objects", filters, pageSize, cursor),
      ),
    readDimensionalObject: (tenantId, projectId, dimensionalEntityId) =>
      request<DimensionalObjectDetail>(
        `/api/v1/tenants/${tenantId}/projects/${projectId}/dimensional/objects/${dimensionalEntityId}`,
      ),
    listDimensionalAttributes: (tenantId, projectId, filters = {}, pageSize = 200, cursor) =>
      request<DimensionalAttributePage>(
        dimensionalCollectionPath(tenantId, projectId, "attributes", filters, pageSize, cursor),
      ),
    readDimensionalAttribute: (tenantId, projectId, dimensionalAttributeId) =>
      request<DimensionalAttributeDetail>(
        `/api/v1/tenants/${tenantId}/projects/${projectId}/dimensional/attributes/${dimensionalAttributeId}`,
      ),
    listDimensionalRelationships: (tenantId, projectId, filters = {}, pageSize = 200, cursor) =>
      request<DimensionalRelationshipPage>(
        dimensionalCollectionPath(tenantId, projectId, "relationships", filters, pageSize, cursor),
      ),
    readDimensionalRelationship: (tenantId, projectId, dimensionalRelationshipId) =>
      request<DimensionalRelationshipDetail>(
        `/api/v1/tenants/${tenantId}/projects/${projectId}/dimensional/relationships/${dimensionalRelationshipId}`,
      ),
  };
}

export const dimensionalQueryKeys = {
  objects: (tenantId: number, projectId: number, filters: unknown) => (
    ["dimensional-objects", tenantId, projectId, filters] as const
  ),
  object: (tenantId: number, projectId: number, entityId: number) => (
    ["dimensional-object", tenantId, projectId, entityId] as const
  ),
  attributes: (tenantId: number, projectId: number, filters: unknown) => (
    ["dimensional-attributes", tenantId, projectId, filters] as const
  ),
  attribute: (tenantId: number, projectId: number, attributeId: number) => (
    ["dimensional-attribute", tenantId, projectId, attributeId] as const
  ),
  relationships: (tenantId: number, projectId: number, filters: unknown) => (
    ["dimensional-relationships", tenantId, projectId, filters] as const
  ),
  relationship: (tenantId: number, projectId: number, relationshipId: number) => (
    ["dimensional-relationship", tenantId, projectId, relationshipId] as const
  ),
};

function dimensionalCollectionPath(
  tenantId: number,
  projectId: number,
  collection: "objects" | "attributes" | "relationships",
  filters: DimensionalFilters | DimensionalAttributeFilters | DimensionalRelationshipFilters,
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
  if ("dimensionalEntityId" in filters && filters.dimensionalEntityId) {
    query.set("dimensional_entity_id", String(filters.dimensionalEntityId));
  }
  query.set("page_size", String(pageSize));
  if (cursor) query.set("cursor", cursor);
  return `/api/v1/tenants/${tenantId}/projects/${projectId}/dimensional/${collection}?${query}`;
}

function normalizeNaturalKeyFilter(value: string | undefined): string {
  return value?.replace(/^ +| +$/g, "").toLowerCase() ?? "";
}
