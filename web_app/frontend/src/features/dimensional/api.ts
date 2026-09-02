import type { HttpRequest } from "../../core/http";
import type {
  ModelingCardinality,
  ModelingConfidence,
  ReviewStatus,
} from "../../shared/contracts";
import type { ModelInputScopeApi } from "../model_input_scope/api";
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
  model_id: number;
  model_revision: number;
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

export interface DimensionalPhysicalObjectReference {
  object_id: number;
  tenant_code: string;
  system_code: string;
  connection_code: string;
  object_schema: string;
  object_name: string;
}

export interface DimensionalAssertionReference {
  modeling_assertion_record_id: number;
  modeling_assertion_record_key: string;
  modeling_assertion_document_name: string;
  modeling_assertion_record_type: string;
  modeling_assertion_text: string;
  modeling_assertion_confidence: ModelingConfidence | null;
  modeling_assertion_record_status: ReviewStatus;
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

export interface DimensionalPhysicalObjectSource extends DimensionalObjectSourceBase {
  support_source_type: "object";
  source_object: DimensionalPhysicalObjectReference;
}

export interface DimensionalAssertionSource extends DimensionalObjectSourceBase {
  support_source_type: "assertion";
  assertion_record: DimensionalAssertionReference;
}

export type DimensionalObjectSource = DimensionalPhysicalObjectSource | DimensionalAssertionSource;

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
  model_id: number;
  model_revision: number;
  items: DimensionalAttribute[];
  next_cursor: string | null;
}

export interface DimensionalPhysicalAttributeReference extends DimensionalPhysicalObjectReference {
  attribute_id: number;
  attribute_name: string;
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

export interface DimensionalPhysicalAttributeSource extends DimensionalAttributeSourceBase {
  dimensional_entity_source_mapping_id: number;
  support_source_type: "attribute";
  source_attribute: DimensionalPhysicalAttributeReference;
}

export interface DimensionalAttributeAssertionSource extends DimensionalAttributeSourceBase {
  support_source_type: "assertion";
  assertion_record: DimensionalAssertionReference;
}

export type DimensionalAttributeSource =
  | DimensionalPhysicalAttributeSource
  | DimensionalAttributeAssertionSource;

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
  from_dimensional_entity_name: string;
  from_dimensional_attribute_id: number;
  from_dimensional_attribute_name: string;
  to_dimensional_entity_id: number;
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
  model_id: number;
  model_revision: number;
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
    modelId: number,
    filters?: DimensionalFilters,
    pageSize?: number,
    cursor?: string,
  ) => Promise<DimensionalObjectPage>;
  readDimensionalObject: (
    tenantId: number,
    modelId: number,
    dimensionalEntityId: number,
  ) => Promise<DimensionalObjectDetail>;
  listDimensionalAttributes: (
    tenantId: number,
    modelId: number,
    filters?: DimensionalAttributeFilters,
    pageSize?: number,
    cursor?: string,
  ) => Promise<DimensionalAttributePage>;
  readDimensionalAttribute: (
    tenantId: number,
    modelId: number,
    dimensionalAttributeId: number,
  ) => Promise<DimensionalAttributeDetail>;
  listDimensionalRelationships: (
    tenantId: number,
    modelId: number,
    filters?: DimensionalRelationshipFilters,
    pageSize?: number,
    cursor?: string,
  ) => Promise<DimensionalRelationshipPage>;
  readDimensionalRelationship: (
    tenantId: number,
    modelId: number,
    dimensionalRelationshipId: number,
  ) => Promise<DimensionalRelationshipDetail>;
}

export type DimensionalApi = DimensionalTransport
  & Pick<
    WorkflowsApi,
    | "applyWorkflowDraft"
    | "createWorkflowRun"
    | "executeDimensionalRun"
    | "listWorkflowRunEvents"
    | "listWorkflowRuns"
    | "readAgentCapabilities"
    | "readWorkflowDraftReview"
    | "readWorkflowRun"
  >
  & Pick<ModelInputScopeApi, "listModelInputScope">;

export function createDimensionalApi(request: HttpRequest): DimensionalTransport {
  return {
    listDimensionalObjects: (tenantId, modelId, filters = {}, pageSize = 200, cursor) =>
      request<DimensionalObjectPage>(
        dimensionalCollectionPath(tenantId, modelId, "objects", filters, pageSize, cursor),
      ),
    readDimensionalObject: (tenantId, modelId, dimensionalEntityId) =>
      request<DimensionalObjectDetail>(
        `/api/v1/tenants/${tenantId}/models/${modelId}/dimensional/objects/${dimensionalEntityId}`,
      ),
    listDimensionalAttributes: (tenantId, modelId, filters = {}, pageSize = 200, cursor) =>
      request<DimensionalAttributePage>(
        dimensionalCollectionPath(tenantId, modelId, "attributes", filters, pageSize, cursor),
      ),
    readDimensionalAttribute: (tenantId, modelId, dimensionalAttributeId) =>
      request<DimensionalAttributeDetail>(
        `/api/v1/tenants/${tenantId}/models/${modelId}/dimensional/attributes/${dimensionalAttributeId}`,
      ),
    listDimensionalRelationships: (tenantId, modelId, filters = {}, pageSize = 200, cursor) =>
      request<DimensionalRelationshipPage>(
        dimensionalCollectionPath(tenantId, modelId, "relationships", filters, pageSize, cursor),
      ),
    readDimensionalRelationship: (tenantId, modelId, dimensionalRelationshipId) =>
      request<DimensionalRelationshipDetail>(
        `/api/v1/tenants/${tenantId}/models/${modelId}/dimensional/relationships/${dimensionalRelationshipId}`,
      ),
  };
}

export const dimensionalQueryKeys = {
  objects: (tenantId: number, modelId: number, filters: unknown) => (
    ["dimensional-objects", tenantId, modelId, filters] as const
  ),
  object: (tenantId: number, modelId: number, entityId: number) => (
    ["dimensional-object", tenantId, modelId, entityId] as const
  ),
  attributes: (tenantId: number, modelId: number, filters: unknown) => (
    ["dimensional-attributes", tenantId, modelId, filters] as const
  ),
  attribute: (tenantId: number, modelId: number, attributeId: number) => (
    ["dimensional-attribute", tenantId, modelId, attributeId] as const
  ),
  relationships: (tenantId: number, modelId: number, filters: unknown) => (
    ["dimensional-relationships", tenantId, modelId, filters] as const
  ),
  relationship: (tenantId: number, modelId: number, relationshipId: number) => (
    ["dimensional-relationship", tenantId, modelId, relationshipId] as const
  ),
};

function dimensionalCollectionPath(
  tenantId: number,
  modelId: number,
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
  return `/api/v1/tenants/${tenantId}/models/${modelId}/dimensional/${collection}?${query}`;
}

function normalizeNaturalKeyFilter(value: string | undefined): string {
  return value?.replace(/^ +| +$/g, "").toLowerCase() ?? "";
}
