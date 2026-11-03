import type { ProjectTargetsTransport } from "../project_targets/api";
import type { ProjectRecordReviewApi } from "../project_record_review/api";
import type { HttpRequest } from "../../core/http";
import type { ReviewStatus } from "../../shared/contracts";
import type { ProjectInputScopeApi } from "../project_input_scope/api";
import type { SubjectAreaTransport } from "../subject_areas/api";
import type { WorkflowsApi } from "../workflows/api";
import type { ModelSubjectAreaPage } from "../../shared/contracts";

export interface LogicalFilters {
  active?: boolean;
  locked?: boolean;
  nameExact?: string;
  namePrefix?: string;
}

export interface LogicalEntityFilters extends LogicalFilters {
  /** Entities with an active Object source among the area's active Objects. */
  subjectAreaId?: number;
}

export interface LogicalEntity {
  logical_entity_id: number;
  workflow_run_id: number | null;
  logical_entity_schema_name: string;
  logical_entity_name: string;
  /** Reference code such as core, reference or transaction. */
  logical_entity_type: string;
  logical_entity_dependency_order: number;
  logical_entity_is_active: boolean;
  logical_entity_is_locked: boolean;
  updated_at: string;
}

export interface LogicalEntityPage {
  project_id: number;
  project_revision: number;
  items: LogicalEntity[];
  next_cursor: string | null;
}

export interface LogicalPhysicalObjectReference {
  object_id: number;
  tenant_code: string;
  system_code: string;
  connection_code: string;
  object_schema: string;
  object_name: string;
}

export interface LogicalContextReference {
  context_record_id: string;
  context_group_name: string;
  context_type_name: string;
  context_text: string;
  source_reference: string | null;
  status: ReviewStatus;
}

interface LogicalEntitySourceBase {
  logical_entity_source_mapping_id: number;
  workflow_run_id: number | null;
  rationale: string | null;
  is_active: boolean;
  is_locked: boolean;
  created_at: string;
  updated_at: string;
}

export interface LogicalObjectSource extends LogicalEntitySourceBase {
  support_source_type: "object";
  source_object: LogicalPhysicalObjectReference;
}

export interface LogicalContextSource extends LogicalEntitySourceBase {
  support_source_type: "context_record";
  context_record: LogicalContextReference;
}

export type LogicalEntitySource = LogicalObjectSource | LogicalContextSource;

export interface LogicalEntityDetail extends LogicalEntity {
  logical_entity_definition: string;
  logical_entity_grain: string;
  created_at: string;
  /** Read-only: the active Subject Areas that contain the Entity's active Object sources. */
  subject_areas: { subject_area_id: number; subject_area_name: string }[];
  sources: LogicalEntitySource[];
}

export interface LogicalAttributeFilters extends LogicalFilters {
  logicalEntityId?: number;
}

export interface LogicalAttribute {
  logical_attribute_id: number;
  workflow_run_id: number | null;
  logical_entity_id: number;
  logical_entity_schema_name: string;
  logical_entity_name: string;
  logical_attribute_name: string;
  logical_attribute_data_type: string;
  logical_attribute_is_nullable: boolean;
  logical_attribute_is_natural_key: boolean;
  logical_attribute_is_surrogate_key: boolean;
  logical_attribute_ordinal_position: number;
  logical_attribute_is_audit_column: boolean;
  logical_attribute_is_active: boolean;
  logical_attribute_is_locked: boolean;
  updated_at: string;
}

export interface LogicalAttributePage {
  project_id: number;
  project_revision: number;
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
  rationale: string | null;
  is_active: boolean;
  is_locked: boolean;
  created_at: string;
  updated_at: string;
}

export interface LogicalAttributePhysicalSource extends LogicalAttributeSourceBase {
  logical_entity_source_mapping_id: number;
  support_source_type: "attribute";
  source_attribute: LogicalPhysicalAttributeReference;
}

export interface LogicalAttributeContextSource extends LogicalAttributeSourceBase {
  support_source_type: "context_record";
  context_record: LogicalContextReference;
}

export type LogicalAttributeSource =
  | LogicalAttributePhysicalSource
  | LogicalAttributeContextSource;

export interface LogicalAttributeDetail extends LogicalAttribute {
  logical_attribute_definition: string;
  created_at: string;
  sources: LogicalAttributeSource[];
}

export interface LogicalRelationshipFilters extends LogicalFilters {
  logicalEntityId?: number;
}

/**
 * Child to parent: the From Entity's foreign-key Attribute points at the To (parent)
 * Entity's key Attribute.
 */
export interface LogicalRelationship {
  logical_relationship_id: number;
  workflow_run_id: number | null;
  from_logical_entity_id: number;
  from_logical_entity_schema_name: string;
  from_logical_entity_name: string;
  from_logical_attribute_id: number;
  from_logical_attribute_name: string;
  to_logical_entity_id: number;
  to_logical_entity_schema_name: string;
  to_logical_entity_name: string;
  to_logical_attribute_id: number;
  to_logical_attribute_name: string;
  logical_relationship_cardinality: "many_to_one" | "one_to_one";
  logical_relationship_is_active: boolean;
  logical_relationship_is_locked: boolean;
  updated_at: string;
}

export interface LogicalRelationshipPage {
  project_id: number;
  project_revision: number;
  items: LogicalRelationship[];
  next_cursor: string | null;
}

export interface LogicalRelationshipDetail extends LogicalRelationship {
  logical_relationship_basis: string;
  created_at: string;
}

export interface LogicalTransport {
  listLogicalSubjectAreas: (tenantId: number, projectId: number) => Promise<ModelSubjectAreaPage>;
  listLogicalEntities: (
    tenantId: number,
    projectId: number,
    filters?: LogicalEntityFilters,
    pageSize?: number,
    cursor?: string,
  ) => Promise<LogicalEntityPage>;
  readLogicalEntity: (
    tenantId: number,
    projectId: number,
    logicalEntityId: number,
  ) => Promise<LogicalEntityDetail>;
  listLogicalAttributes: (
    tenantId: number,
    projectId: number,
    filters?: LogicalAttributeFilters,
    pageSize?: number,
    cursor?: string,
  ) => Promise<LogicalAttributePage>;
  readLogicalAttribute: (
    tenantId: number,
    projectId: number,
    logicalAttributeId: number,
  ) => Promise<LogicalAttributeDetail>;
  listLogicalRelationships: (
    tenantId: number,
    projectId: number,
    filters?: LogicalRelationshipFilters,
    pageSize?: number,
    cursor?: string,
  ) => Promise<LogicalRelationshipPage>;
  readLogicalRelationship: (
    tenantId: number,
    projectId: number,
    logicalRelationshipId: number,
  ) => Promise<LogicalRelationshipDetail>;
}

export type LogicalApi = LogicalTransport & Pick<ProjectTargetsTransport, "readTargetOptions" | "exportProjectTargets" | "exportProjectDdl"> & ProjectRecordReviewApi
  & Pick<SubjectAreaTransport, "listSubjectAreas">
  & Pick<
    WorkflowsApi,
    | "applyWorkflowDraft"
    | "cancelWorkflowRun"
    | "createWorkflowRun"
    | "executeLogicalRun"
    | "listWorkflowRunEvents"
    | "listWorkflowRuns"
    | "readAgentCapabilities"
    | "readWorkflowDraftReview"
    | "readWorkflowRun"
  >
  & Pick<ProjectInputScopeApi, "listProjectInputScope">;

export function createLogicalApi(request: HttpRequest): LogicalTransport {
  return {
    listLogicalSubjectAreas: (tenantId, projectId) => request<ModelSubjectAreaPage>(
      `/api/v1/tenants/${tenantId}/projects/${projectId}/logical/subject-areas`,
    ),
    listLogicalEntities: (tenantId, projectId, filters = {}, pageSize = 200, cursor) =>
      request<LogicalEntityPage>(
        logicalCollectionPath(tenantId, projectId, "entities", filters, pageSize, cursor),
      ),
    readLogicalEntity: (tenantId, projectId, logicalEntityId) =>
      request<LogicalEntityDetail>(
        `/api/v1/tenants/${tenantId}/projects/${projectId}/logical/entities/${logicalEntityId}`,
      ),
    listLogicalAttributes: (tenantId, projectId, filters = {}, pageSize = 200, cursor) =>
      request<LogicalAttributePage>(
        logicalCollectionPath(tenantId, projectId, "attributes", filters, pageSize, cursor),
      ),
    readLogicalAttribute: (tenantId, projectId, logicalAttributeId) =>
      request<LogicalAttributeDetail>(
        `/api/v1/tenants/${tenantId}/projects/${projectId}/logical/attributes/${logicalAttributeId}`,
      ),
    listLogicalRelationships: (tenantId, projectId, filters = {}, pageSize = 200, cursor) =>
      request<LogicalRelationshipPage>(
        logicalCollectionPath(tenantId, projectId, "relationships", filters, pageSize, cursor),
      ),
    readLogicalRelationship: (tenantId, projectId, logicalRelationshipId) =>
      request<LogicalRelationshipDetail>(
        `/api/v1/tenants/${tenantId}/projects/${projectId}/logical/relationships/${logicalRelationshipId}`,
      ),
  };
}

export const logicalQueryKeys = {
  subjectAreas: (tenantId: number, projectId: number) => (
    ["logical-subject-areas", tenantId, projectId] as const
  ),
  entities: (tenantId: number, projectId: number, filters: unknown) => (
    ["logical-entities", tenantId, projectId, filters] as const
  ),
  entity: (tenantId: number, projectId: number, entityId: number) => (
    ["logical-entity", tenantId, projectId, entityId] as const
  ),
  attributes: (tenantId: number, projectId: number, filters: unknown) => (
    ["logical-attributes", tenantId, projectId, filters] as const
  ),
  attribute: (tenantId: number, projectId: number, attributeId: number) => (
    ["logical-attribute", tenantId, projectId, attributeId] as const
  ),
  relationships: (tenantId: number, projectId: number, filters: unknown) => (
    ["logical-relationships", tenantId, projectId, filters] as const
  ),
  relationship: (tenantId: number, projectId: number, relationshipId: number) => (
    ["logical-relationship", tenantId, projectId, relationshipId] as const
  ),
};

function logicalCollectionPath(
  tenantId: number,
  projectId: number,
  collection: "entities" | "attributes" | "relationships",
  filters: LogicalEntityFilters | LogicalAttributeFilters | LogicalRelationshipFilters,
  pageSize: number,
  cursor: string | undefined,
): string {
  const query = new URLSearchParams();
  if (filters.active !== undefined) query.set("active", String(filters.active));
  if (filters.locked !== undefined) query.set("locked", String(filters.locked));
  const nameExact = normalizeNaturalKeyFilter(filters.nameExact);
  const namePrefix = normalizeNaturalKeyFilter(filters.namePrefix);
  if (nameExact) query.set("name_exact", nameExact);
  if (namePrefix) query.set("name_prefix", namePrefix);
  if ("logicalEntityId" in filters && filters.logicalEntityId) {
    query.set("logical_entity_id", String(filters.logicalEntityId));
  }
  if ("subjectAreaId" in filters && filters.subjectAreaId) {
    query.set("subject_area_id", String(filters.subjectAreaId));
  }
  query.set("page_size", String(pageSize));
  if (cursor) query.set("cursor", cursor);
  return `/api/v1/tenants/${tenantId}/projects/${projectId}/logical/${collection}?${query}`;
}

function normalizeNaturalKeyFilter(value: string | undefined): string {
  return value?.replace(/^ +| +$/g, "").toLowerCase() ?? "";
}
