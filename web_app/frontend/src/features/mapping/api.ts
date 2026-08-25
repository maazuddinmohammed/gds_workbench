import type { HttpRequest } from "../../core/http";
import type { JsonObject, ReviewStatus } from "../../shared/contracts";
import type { ModelsApi } from "../models/api";
import type { ModelScopeApi, ModelScopeObject } from "../model_scope/api";
import type { WorkflowsApi } from "../workflows/api";

export type MappingEntityType = "logical_entity" | "dimensional_entity";
export type MappingStatus = ReviewStatus;

export interface MappingFilters {
  entityType?: MappingEntityType;
  sourceSystemId?: number;
  sourceSystemCode?: string;
  status?: MappingStatus;
  locked?: boolean;
}

export type OutputTemplateTargetType = "mapping_object" | "mapping_attribute";

export interface OutputTemplateSummary {
  output_template_id: number;
  output_template_code: string;
  output_template_name: string;
  output_template_description: string | null;
  output_template_target_type: OutputTemplateTargetType;
  output_template_schema_digest: string;
  output_template_schema_digest_is_valid: boolean;
  is_active: boolean;
  field_count: number;
}

export interface OutputTemplatePage {
  tenant_id: number;
  items: OutputTemplateSummary[];
  next_cursor: string | null;
}

export interface MappingSourceSystem {
  system_id: number;
  system_code: string;
  system_name: string;
}

export interface MappingPhysicalObject {
  object_id: number;
  tenant_id: number;
  tenant_code: string;
  tenant_name: string;
  system_id: number;
  system_code: string;
  system_name: string;
  connection_id: number;
  connection_code: string;
  object_schema: string;
  object_name: string;
  zone_code: string;
}

export interface MappingModeledEntity {
  entity_type: MappingEntityType;
  entity_id: number;
  entity_name: string;
}

export interface MappingPhysicalAttribute {
  object: MappingPhysicalObject;
  attribute_id: number;
  attribute_name: string;
  attribute_ordinal_position: number;
  attribute_data_type: string;
}

export interface MappingModeledAttribute {
  entity: MappingModeledEntity;
  attribute_id: number;
  attribute_name: string;
}

export interface MappingDependency {
  mapping_source_system_dependency_id: number;
  workflow_run_id: number | null;
  entity_type: MappingEntityType;
  source_system: MappingSourceSystem;
  dependency_order: number;
  status: MappingStatus;
  is_locked: boolean;
  updated_at: string;
}

export interface MappingDependencyPage {
  model_id: number;
  model_revision: number;
  items: MappingDependency[];
  next_cursor: string | null;
}

export interface MappingObject {
  mapping_object_id: number;
  workflow_run_id: number | null;
  target: MappingPhysicalObject;
  source: MappingModeledEntity;
  source_system: MappingSourceSystem;
  dependency_order: number;
  artifact_type: "sql_file" | "python_file" | "python_notebook" | null;
  status: MappingStatus;
  is_locked: boolean;
  updated_at: string;
}

export interface MappingObjectPage {
  model_id: number;
  model_revision: number;
  items: MappingObject[];
  next_cursor: string | null;
}

export interface MappingProfileProvenance {
  profile_key: string;
  profile_version: string;
  profile_schema_digest: string;
  package_digest: string;
}

export interface MappingOutputTemplateProvenance {
  output_template_id: number;
  output_template_code: string;
  output_template_name: string;
  output_template_target_type: OutputTemplateTargetType;
  output_template_schema_digest: string;
  is_active: boolean;
}

export interface MappingObjectDetail extends MappingObject {
  artifact_generation_instructions: string | null;
  mapping_profile: MappingProfileProvenance | null;
  mapping_package_document: JsonObject | null;
  mapping_document_format: "free_form" | "structured" | null;
  mapping_document: JsonObject | null;
  output_template: MappingOutputTemplateProvenance | null;
  created_at: string;
}

export interface MappingAttribute {
  mapping_attribute_id: number;
  workflow_run_id: number | null;
  mapping_object_id: number;
  target: MappingPhysicalAttribute;
  source: MappingModeledAttribute;
  source_system: MappingSourceSystem;
  status: MappingStatus;
  is_locked: boolean;
  updated_at: string;
}

export interface MappingAttributePage {
  model_id: number;
  model_revision: number;
  items: MappingAttribute[];
  next_cursor: string | null;
}

export interface MappingParentObjectReference {
  mapping_object_id: number;
  dependency_order: number;
  artifact_type: "sql_file" | "python_file" | "python_notebook" | null;
  mapping_profile: MappingProfileProvenance | null;
  status: MappingStatus;
  is_locked: boolean;
}

export interface MappingAttributeDetail extends MappingAttribute {
  parent_object_mapping: MappingParentObjectReference;
  mapping_document_format: "free_form" | "structured" | null;
  mapping_document: JsonObject | null;
  output_template: MappingOutputTemplateProvenance | null;
  created_at: string;
}

export interface MappingTransport {
  listMappingDependencies: (
    tenantId: number,
    modelId: number,
    filters?: MappingFilters,
    pageSize?: number,
    cursor?: string,
  ) => Promise<MappingDependencyPage>;
  listMappingObjects: (
    tenantId: number,
    modelId: number,
    filters?: MappingFilters,
    pageSize?: number,
    cursor?: string,
  ) => Promise<MappingObjectPage>;
  readMappingObject: (
    tenantId: number,
    modelId: number,
    mappingObjectId: number,
  ) => Promise<MappingObjectDetail>;
  listMappingAttributes: (
    tenantId: number,
    modelId: number,
    filters?: MappingFilters,
    pageSize?: number,
    cursor?: string,
  ) => Promise<MappingAttributePage>;
  readMappingAttribute: (
    tenantId: number,
    modelId: number,
    mappingAttributeId: number,
  ) => Promise<MappingAttributeDetail>;
  listOutputTemplates: (
    tenantId: number,
    targetType: OutputTemplateTargetType,
    pageSize?: number,
    cursor?: string,
  ) => Promise<OutputTemplatePage>;
}

export type MappingApi = MappingTransport
  & Pick<ModelsApi, "listModels">
  & Pick<ModelScopeApi, "listModelScope">
  & Pick<
    WorkflowsApi,
    "readAgentCapabilities" | "createWorkflowRun" | "executeMappingRun"
  >;

export function createMappingApi(request: HttpRequest): MappingTransport {
  return {
    listMappingDependencies: (tenantId, modelId, filters = {}, pageSize = 200, cursor) =>
      request<MappingDependencyPage>(
        mappingCollectionPath(tenantId, modelId, "dependencies", filters, pageSize, cursor),
      ),
    listMappingObjects: (tenantId, modelId, filters = {}, pageSize = 200, cursor) =>
      request<MappingObjectPage>(
        mappingCollectionPath(tenantId, modelId, "objects", filters, pageSize, cursor),
      ),
    readMappingObject: (tenantId, modelId, mappingObjectId) =>
      request<MappingObjectDetail>(
        `/api/v1/tenants/${tenantId}/models/${modelId}/mapping/objects/${mappingObjectId}`,
      ),
    listMappingAttributes: (tenantId, modelId, filters = {}, pageSize = 200, cursor) =>
      request<MappingAttributePage>(
        mappingCollectionPath(tenantId, modelId, "attributes", filters, pageSize, cursor),
      ),
    readMappingAttribute: (tenantId, modelId, mappingAttributeId) =>
      request<MappingAttributeDetail>(
        `/api/v1/tenants/${tenantId}/models/${modelId}/mapping/attributes/${mappingAttributeId}`,
      ),
    listOutputTemplates: (tenantId, targetType, pageSize = 200, cursor) => {
      const query = new URLSearchParams({
        target_type: targetType,
        active: "true",
        page_size: String(pageSize),
      });
      if (cursor) query.set("cursor", cursor);
      return request<OutputTemplatePage>(
        `/api/v1/tenants/${tenantId}/output-templates?${query}`,
      );
    },
  };
}

export const mappingQueryKeys = {
  models: (tenantId: number) => ["mapping-models", tenantId] as const,
  dependencies: (tenantId: number, modelId: number, filters: unknown) => (
    ["mapping-dependencies", tenantId, modelId, filters] as const
  ),
  objects: (tenantId: number, modelId: number, filters: unknown) => (
    ["mapping-objects", tenantId, modelId, filters] as const
  ),
  object: (tenantId: number, modelId: number, mappingObjectId: number) => (
    ["mapping-object", tenantId, modelId, mappingObjectId] as const
  ),
  attributes: (tenantId: number, modelId: number, filters: unknown) => (
    ["mapping-attributes", tenantId, modelId, filters] as const
  ),
  attribute: (tenantId: number, modelId: number, mappingAttributeId: number) => (
    ["mapping-attribute", tenantId, modelId, mappingAttributeId] as const
  ),
  runScope: (tenantId: number, modelId: number) => (
    ["mapping-run-scope", tenantId, modelId] as const
  ),
  outputTemplates: (tenantId: number, modelId: number) => (
    ["mapping-output-templates", tenantId, modelId] as const
  ),
};

export interface ActiveMappingOutputTemplates {
  mappingObjects: OutputTemplateSummary[];
  mappingAttributes: OutputTemplateSummary[];
}

export async function loadActiveMappingOutputTemplates(
  api: Pick<MappingTransport, "listOutputTemplates">,
  tenantId: number,
): Promise<ActiveMappingOutputTemplates> {
  const [mappingObjects, mappingAttributes] = await Promise.all([
    loadOutputTemplatesForTargetType(api, tenantId, "mapping_object"),
    loadOutputTemplatesForTargetType(api, tenantId, "mapping_attribute"),
  ]);
  return { mappingObjects, mappingAttributes };
}

async function loadOutputTemplatesForTargetType(
  api: Pick<MappingTransport, "listOutputTemplates">,
  tenantId: number,
  targetType: OutputTemplateTargetType,
): Promise<OutputTemplateSummary[]> {
  const items: OutputTemplateSummary[] = [];
  const seenCursors = new Set<string>();
  let cursor: string | undefined;

  for (let page = 0; page < 5; page += 1) {
    const response = await api.listOutputTemplates(tenantId, targetType, 200, cursor);
    items.push(...response.items);
    if (!response.next_cursor) return items;
    if (seenCursors.has(response.next_cursor)) {
      throw new Error("Output Template cursor repeated");
    }
    if (page === 4) {
      throw new Error("Output Template selection exceeds the supported bound");
    }
    seenCursors.add(response.next_cursor);
    cursor = response.next_cursor;
  }
  throw new Error("Output Template selection exceeds the supported bound");
}

export async function loadAllMappingScope(
  api: Pick<ModelScopeApi, "listModelScope">,
  tenantId: number,
  modelId: number,
): Promise<{ modelRevision: number; items: ModelScopeObject[] }> {
  const items: ModelScopeObject[] = [];
  const seenCursors = new Set<string>();
  let cursor: string | undefined;
  let modelRevision: number | null = null;

  for (let page = 0; page < 250; page += 1) {
    const response = await api.listModelScope(tenantId, modelId, {}, 200, cursor);
    if (modelRevision !== null && response.model_revision !== modelRevision) {
      throw new Error("Model Scope revision changed while loading");
    }
    modelRevision = response.model_revision;
    items.push(...response.items);
    if (!response.next_cursor) return { modelRevision, items };
    if (seenCursors.has(response.next_cursor)) {
      throw new Error("Model Scope cursor repeated");
    }
    seenCursors.add(response.next_cursor);
    cursor = response.next_cursor;
  }
  throw new Error("Active Scope exceeds the supported bounded Mapping selection");
}

function mappingCollectionPath(
  tenantId: number,
  modelId: number,
  collection: "dependencies" | "objects" | "attributes",
  filters: MappingFilters,
  pageSize: number,
  cursor: string | undefined,
): string {
  const query = new URLSearchParams();
  if (filters.entityType) query.set("entity_type", filters.entityType);
  if (filters.sourceSystemId) query.set("source_system_id", String(filters.sourceSystemId));
  const sourceSystemCode = normalizeNaturalKeyFilter(filters.sourceSystemCode);
  if (sourceSystemCode) query.set("source_system_code", sourceSystemCode);
  if (filters.status) query.set("status", filters.status);
  if (filters.locked !== undefined) query.set("locked", String(filters.locked));
  query.set("page_size", String(pageSize));
  if (cursor) query.set("cursor", cursor);
  return `/api/v1/tenants/${tenantId}/models/${modelId}/mapping/${collection}?${query}`;
}

function normalizeNaturalKeyFilter(value: string | undefined): string {
  return value?.replace(/^ +| +$/g, "").toLowerCase() ?? "";
}
