import type { ProjectTargetsTransport } from "../project_targets/api";
import type { ProjectRecordReviewApi } from "../project_record_review/api";
import type { HttpRequest } from "../../core/http";
import type {
  ModelingCardinality,
  ReviewStatus,
} from "../../shared/contracts";
import type { ProjectInputScopeApi } from "../project_input_scope/api";
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
  logical_entity_schema_name: string;
  logical_entity_name: string;
  logical_entity_type: string;
  logical_entity_dependency_order: number;
  logical_entity_status: ReviewStatus;
  logical_entity_is_locked: boolean;
  updated_at: string;
}

export interface LogicalEntityPage {
  project_id: number;
  project_revision: number;
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

export interface LogicalContextSource extends LogicalEntitySourceBase {
  support_source_type: "context_record";
  context_record: LogicalContextReference;
}

export type LogicalEntitySource = LogicalObjectSource | LogicalContextSource;

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
  logical_entity_schema_name: string;
  logical_entity_name: string;
  logical_attribute_name: string;
  logical_attribute_data_type: string;
  logical_attribute_is_nullable: boolean;
  logical_attribute_is_natural_key: boolean;
  logical_attribute_is_surrogate_key: boolean;
  logical_attribute_ordinal_position: number;
  logical_attribute_is_audit_column: boolean;
  logical_attribute_status: ReviewStatus;
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
  logical_relationship_name: string;
  logical_relationship_cardinality: ModelingCardinality;
  logical_relationship_status: ReviewStatus;
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
  project_id: number;
  project_revision: number;
  items: LogicalSubmodel[];
  next_cursor: string | null;
}

export interface LogicalSubmodelEntityMembership {
  logical_entity_submodel_id: number;
  workflow_run_id: number | null;
  logical_entity_id: number;
  logical_entity_schema_name: string;
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
  listLogicalSubmodels: (
    tenantId: number,
    projectId: number,
    filters?: LogicalFilters,
    pageSize?: number,
    cursor?: string,
  ) => Promise<LogicalSubmodelPage>;
  readLogicalSubmodel: (
    tenantId: number,
    projectId: number,
    logicalSubmodelId: number,
  ) => Promise<LogicalSubmodelDetail>;
}

export type LogicalApi = LogicalTransport & Pick<ProjectTargetsTransport, "readTargetOptions" | "exportProjectTargets" | "exportProjectDdl"> & ProjectRecordReviewApi
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
    listLogicalSubmodels: (tenantId, projectId, filters = {}, pageSize = 200, cursor) =>
      request<LogicalSubmodelPage>(
        logicalCollectionPath(tenantId, projectId, "submodels", filters, pageSize, cursor),
      ),
    readLogicalSubmodel: (tenantId, projectId, logicalSubmodelId) =>
      request<LogicalSubmodelDetail>(
        `/api/v1/tenants/${tenantId}/projects/${projectId}/logical/submodels/${logicalSubmodelId}`,
      ),
  };
}

export const logicalQueryKeys = {
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
  submodels: (tenantId: number, projectId: number, filters: unknown) => (
    ["logical-submodels", tenantId, projectId, filters] as const
  ),
  submodel: (tenantId: number, projectId: number, submodelId: number) => (
    ["logical-submodel", tenantId, projectId, submodelId] as const
  ),
  submodelOptions: (tenantId: number, projectId: number) => (
    ["logical-submodel-options", tenantId, projectId] as const
  ),
};

export async function loadAllLogicalSubmodels(
  api: Pick<LogicalTransport, "listLogicalSubmodels">,
  tenantId: number,
  projectId: number,
): Promise<{ projectRevision: number; items: LogicalSubmodel[] }> {
  const items: LogicalSubmodel[] = [];
  const seenCursors = new Set<string>();
  let cursor: string | undefined;
  let projectRevision: number | null = null;

  for (let page = 0; page < 250; page += 1) {
    const response = await api.listLogicalSubmodels(tenantId, projectId, {}, 200, cursor);
    if (projectRevision !== null && projectRevision !== response.project_revision) {
      throw new Error("Project revision changed while loading Logical Submodels");
    }
    projectRevision = response.project_revision;
    items.push(...response.items);
    if (!response.next_cursor) return { projectRevision, items };
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
  projectId: number,
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
  return `/api/v1/tenants/${tenantId}/projects/${projectId}/logical/${collection}?${query}`;
}

function normalizeNaturalKeyFilter(value: string | undefined): string {
  return value?.replace(/^ +| +$/g, "").toLowerCase() ?? "";
}
