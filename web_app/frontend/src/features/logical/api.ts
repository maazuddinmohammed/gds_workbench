import type { HttpRequest } from "../../core/http";
import type {
  ModelingCardinality,
  ModelingConfidence,
  ReviewStatus,
} from "../../shared/contracts";
import type { ModelScopeApi } from "../model_scope/api";
import type { WorkflowsApi } from "../workflows/api";

export interface LogicalFilters {
  status?: ReviewStatus;
  locked?: boolean;
  nameExact?: string;
  namePrefix?: string;
}

export interface LogicalEntityFilters extends LogicalFilters {
  logicalSubmodelId?: number;
}

export interface LogicalEntity {
  logical_entity_id: number;
  workflow_run_id: number | null;
  logical_entity_name: string;
  logical_entity_type: string;
  logical_entity_dependency_order: number;
  logical_entity_confidence: ModelingConfidence;
  logical_entity_status: ReviewStatus;
  logical_entity_is_locked: boolean;
  updated_at: string;
}

export interface LogicalEntityPage {
  model_id: number;
  model_revision: number;
  items: LogicalEntity[];
  next_cursor: string | null;
}

export interface LogicalSubmodelMembership {
  logical_entity_submodel_id: number;
  workflow_run_id: number | null;
  logical_submodel_id: number;
  logical_submodel_name: string;
  membership_status: ReviewStatus;
  membership_is_locked: boolean;
  created_at: string;
  updated_at: string;
}

export interface LogicalPhysicalObjectReference {
  object_id: number;
  tenant_code: string;
  system_code: string;
  connection_code: string;
  object_schema: string;
  object_name: string;
}

export interface LogicalAssertionReference {
  modeling_assertion_record_id: number;
  modeling_assertion_record_key: string;
  modeling_assertion_document_name: string;
  modeling_assertion_record_type: string;
  modeling_assertion_text: string;
  modeling_assertion_confidence: ModelingConfidence | null;
  modeling_assertion_record_status: ReviewStatus;
}

interface LogicalEntitySourceBase {
  logical_entity_source_mapping_id: number;
  workflow_run_id: number | null;
  source_order: number | null;
  rationale: string;
  status: ReviewStatus;
  is_locked: boolean;
  created_at: string;
  updated_at: string;
}

export interface LogicalObjectSource extends LogicalEntitySourceBase {
  support_source_type: "object";
  source_object: LogicalPhysicalObjectReference;
}

export interface LogicalAssertionSource extends LogicalEntitySourceBase {
  support_source_type: "assertion";
  assertion_record: LogicalAssertionReference;
}

export type LogicalEntitySource = LogicalObjectSource | LogicalAssertionSource;

export interface LogicalEntityDetail extends LogicalEntity {
  logical_entity_definition: string;
  logical_entity_type_detail: string | null;
  logical_entity_grain: string;
  created_at: string;
  submodels: LogicalSubmodelMembership[];
  sources: LogicalEntitySource[];
}

export interface LogicalAttributeFilters extends LogicalFilters {
  logicalEntityId?: number;
}

export interface LogicalAttribute {
  logical_attribute_id: number;
  workflow_run_id: number | null;
  logical_entity_id: number;
  logical_entity_name: string;
  logical_attribute_name: string;
  logical_attribute_data_type: string;
  logical_attribute_is_nullable: boolean;
  logical_attribute_is_primary_key: boolean;
  logical_attribute_is_natural_key: boolean;
  logical_attribute_is_surrogate_key: boolean;
  logical_attribute_ordinal_position: number;
  logical_attribute_is_audit_column: boolean;
  logical_attribute_status: ReviewStatus;
  logical_attribute_is_locked: boolean;
  updated_at: string;
}

export interface LogicalAttributePage {
  model_id: number;
  model_revision: number;
  items: LogicalAttribute[];
  next_cursor: string | null;
}

export interface LogicalPhysicalAttributeReference extends LogicalPhysicalObjectReference {
  attribute_id: number;
  attribute_name: string;
}

interface LogicalAttributeSourceBase {
  logical_attribute_source_mapping_id: number;
  workflow_run_id: number | null;
  source_order: number | null;
  rationale: string;
  status: ReviewStatus;
  is_locked: boolean;
  created_at: string;
  updated_at: string;
}

export interface LogicalAttributePhysicalSource extends LogicalAttributeSourceBase {
  logical_entity_source_mapping_id: number;
  support_source_type: "attribute";
  source_attribute: LogicalPhysicalAttributeReference;
}

export interface LogicalAttributeAssertionSource extends LogicalAttributeSourceBase {
  support_source_type: "assertion";
  assertion_record: LogicalAssertionReference;
}

export type LogicalAttributeSource =
  | LogicalAttributePhysicalSource
  | LogicalAttributeAssertionSource;

export interface LogicalAttributeDetail extends LogicalAttribute {
  logical_attribute_definition: string;
  created_at: string;
  sources: LogicalAttributeSource[];
}

export interface LogicalRelationshipFilters extends LogicalFilters {
  logicalEntityId?: number;
}

export interface LogicalRelationship {
  logical_relationship_id: number;
  workflow_run_id: number | null;
  from_logical_entity_id: number;
  from_logical_entity_name: string;
  from_logical_attribute_id: number;
  from_logical_attribute_name: string;
  to_logical_entity_id: number;
  to_logical_entity_name: string;
  to_logical_attribute_id: number;
  to_logical_attribute_name: string;
  logical_relationship_name: string;
  logical_relationship_cardinality: ModelingCardinality;
  logical_relationship_confidence: ModelingConfidence;
  logical_relationship_status: ReviewStatus;
  logical_relationship_is_locked: boolean;
  updated_at: string;
}

export interface LogicalRelationshipPage {
  model_id: number;
  model_revision: number;
  items: LogicalRelationship[];
  next_cursor: string | null;
}

export interface LogicalRelationshipDetail extends LogicalRelationship {
  logical_relationship_definition: string;
  logical_relationship_basis: string;
  logical_relationship_cardinality_basis: string;
  created_at: string;
}

export interface LogicalSubmodel {
  logical_submodel_id: number;
  workflow_run_id: number | null;
  logical_submodel_name: string;
  logical_submodel_status: ReviewStatus;
  logical_submodel_is_locked: boolean;
  entity_count: number;
  updated_at: string;
}

export interface LogicalSubmodelPage {
  model_id: number;
  model_revision: number;
  items: LogicalSubmodel[];
  next_cursor: string | null;
}

export interface LogicalSubmodelEntityMembership {
  logical_entity_submodel_id: number;
  workflow_run_id: number | null;
  logical_entity_id: number;
  logical_entity_name: string;
  logical_entity_type: string;
  logical_entity_status: ReviewStatus;
  membership_status: ReviewStatus;
  membership_is_locked: boolean;
  created_at: string;
  updated_at: string;
}

export interface LogicalSubmodelDetail extends LogicalSubmodel {
  logical_submodel_definition: string;
  created_at: string;
  entities: LogicalSubmodelEntityMembership[];
}

export interface LogicalTransport {
  listLogicalEntities: (
    tenantId: number,
    modelId: number,
    filters?: LogicalEntityFilters,
    pageSize?: number,
    cursor?: string,
  ) => Promise<LogicalEntityPage>;
  readLogicalEntity: (
    tenantId: number,
    modelId: number,
    logicalEntityId: number,
  ) => Promise<LogicalEntityDetail>;
  listLogicalAttributes: (
    tenantId: number,
    modelId: number,
    filters?: LogicalAttributeFilters,
    pageSize?: number,
    cursor?: string,
  ) => Promise<LogicalAttributePage>;
  readLogicalAttribute: (
    tenantId: number,
    modelId: number,
    logicalAttributeId: number,
  ) => Promise<LogicalAttributeDetail>;
  listLogicalRelationships: (
    tenantId: number,
    modelId: number,
    filters?: LogicalRelationshipFilters,
    pageSize?: number,
    cursor?: string,
  ) => Promise<LogicalRelationshipPage>;
  readLogicalRelationship: (
    tenantId: number,
    modelId: number,
    logicalRelationshipId: number,
  ) => Promise<LogicalRelationshipDetail>;
  listLogicalSubmodels: (
    tenantId: number,
    modelId: number,
    filters?: LogicalFilters,
    pageSize?: number,
    cursor?: string,
  ) => Promise<LogicalSubmodelPage>;
  readLogicalSubmodel: (
    tenantId: number,
    modelId: number,
    logicalSubmodelId: number,
  ) => Promise<LogicalSubmodelDetail>;
}

export type LogicalApi = LogicalTransport
  & Pick<
    WorkflowsApi,
    "createWorkflowRun" | "executeLogicalRun" | "readAgentCapabilities"
  >
  & Pick<ModelScopeApi, "listModelScope">;

export function createLogicalApi(request: HttpRequest): LogicalTransport {
  return {
    listLogicalEntities: (tenantId, modelId, filters = {}, pageSize = 200, cursor) =>
      request<LogicalEntityPage>(
        logicalCollectionPath(tenantId, modelId, "entities", filters, pageSize, cursor),
      ),
    readLogicalEntity: (tenantId, modelId, logicalEntityId) =>
      request<LogicalEntityDetail>(
        `/api/v1/tenants/${tenantId}/models/${modelId}/logical/entities/${logicalEntityId}`,
      ),
    listLogicalAttributes: (tenantId, modelId, filters = {}, pageSize = 200, cursor) =>
      request<LogicalAttributePage>(
        logicalCollectionPath(tenantId, modelId, "attributes", filters, pageSize, cursor),
      ),
    readLogicalAttribute: (tenantId, modelId, logicalAttributeId) =>
      request<LogicalAttributeDetail>(
        `/api/v1/tenants/${tenantId}/models/${modelId}/logical/attributes/${logicalAttributeId}`,
      ),
    listLogicalRelationships: (tenantId, modelId, filters = {}, pageSize = 200, cursor) =>
      request<LogicalRelationshipPage>(
        logicalCollectionPath(tenantId, modelId, "relationships", filters, pageSize, cursor),
      ),
    readLogicalRelationship: (tenantId, modelId, logicalRelationshipId) =>
      request<LogicalRelationshipDetail>(
        `/api/v1/tenants/${tenantId}/models/${modelId}/logical/relationships/${logicalRelationshipId}`,
      ),
    listLogicalSubmodels: (tenantId, modelId, filters = {}, pageSize = 200, cursor) =>
      request<LogicalSubmodelPage>(
        logicalCollectionPath(tenantId, modelId, "submodels", filters, pageSize, cursor),
      ),
    readLogicalSubmodel: (tenantId, modelId, logicalSubmodelId) =>
      request<LogicalSubmodelDetail>(
        `/api/v1/tenants/${tenantId}/models/${modelId}/logical/submodels/${logicalSubmodelId}`,
      ),
  };
}

export const logicalQueryKeys = {
  entities: (tenantId: number, modelId: number, filters: unknown) => (
    ["logical-entities", tenantId, modelId, filters] as const
  ),
  entity: (tenantId: number, modelId: number, entityId: number) => (
    ["logical-entity", tenantId, modelId, entityId] as const
  ),
  attributes: (tenantId: number, modelId: number, filters: unknown) => (
    ["logical-attributes", tenantId, modelId, filters] as const
  ),
  attribute: (tenantId: number, modelId: number, attributeId: number) => (
    ["logical-attribute", tenantId, modelId, attributeId] as const
  ),
  relationships: (tenantId: number, modelId: number, filters: unknown) => (
    ["logical-relationships", tenantId, modelId, filters] as const
  ),
  relationship: (tenantId: number, modelId: number, relationshipId: number) => (
    ["logical-relationship", tenantId, modelId, relationshipId] as const
  ),
  submodels: (tenantId: number, modelId: number, filters: unknown) => (
    ["logical-submodels", tenantId, modelId, filters] as const
  ),
  submodel: (tenantId: number, modelId: number, submodelId: number) => (
    ["logical-submodel", tenantId, modelId, submodelId] as const
  ),
  submodelOptions: (tenantId: number, modelId: number) => (
    ["logical-submodel-options", tenantId, modelId] as const
  ),
};

export async function loadAllLogicalSubmodels(
  api: Pick<LogicalTransport, "listLogicalSubmodels">,
  tenantId: number,
  modelId: number,
): Promise<{ modelRevision: number; items: LogicalSubmodel[] }> {
  const items: LogicalSubmodel[] = [];
  const seenCursors = new Set<string>();
  let cursor: string | undefined;
  let modelRevision: number | null = null;

  for (let page = 0; page < 250; page += 1) {
    const response = await api.listLogicalSubmodels(tenantId, modelId, {}, 200, cursor);
    if (modelRevision !== null && modelRevision !== response.model_revision) {
      throw new Error("Model revision changed while loading Logical Submodels");
    }
    modelRevision = response.model_revision;
    items.push(...response.items);
    if (!response.next_cursor) return { modelRevision, items };
    if (seenCursors.has(response.next_cursor)) {
      throw new Error("Logical Submodel cursor repeated");
    }
    seenCursors.add(response.next_cursor);
    cursor = response.next_cursor;
  }
  throw new Error("Logical Submodels exceed the supported bounded filter selection");
}

function logicalCollectionPath(
  tenantId: number,
  modelId: number,
  collection: "entities" | "attributes" | "relationships" | "submodels",
  filters: LogicalFilters | LogicalEntityFilters | LogicalAttributeFilters | LogicalRelationshipFilters,
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
  if ("logicalEntityId" in filters && filters.logicalEntityId) {
    query.set("logical_entity_id", String(filters.logicalEntityId));
  }
  if ("logicalSubmodelId" in filters && filters.logicalSubmodelId) {
    query.set("logical_submodel_id", String(filters.logicalSubmodelId));
  }
  query.set("page_size", String(pageSize));
  if (cursor) query.set("cursor", cursor);
  return `/api/v1/tenants/${tenantId}/models/${modelId}/logical/${collection}?${query}`;
}

function normalizeNaturalKeyFilter(value: string | undefined): string {
  return value?.replace(/^ +| +$/g, "").toLowerCase() ?? "";
}
