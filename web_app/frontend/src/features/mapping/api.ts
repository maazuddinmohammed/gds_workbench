import type { ModelRecordReviewApi } from "../model_record_review/api";
import type { HttpRequest } from "../../core/http";
import type { JsonObject, ReviewStatus } from "../../shared/contracts";
import type { ModelsApi } from "../models/api";
import type { WorkflowsApi } from "../workflows/api";

export type MappingEntityType = "logical_entity" | "dimensional_entity";
export type MappingStatus = ReviewStatus;

export interface MappingFilters {
  mappingObjectId?: number;
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

export interface MappingModeledEntity {
  entity_type: MappingEntityType;
  entity_id: number;
  entity_schema_name: string;
  entity_name: string;
}

export interface MappingModeledAttribute {
  entity: MappingModeledEntity;
  attribute_id: number;
  attribute_name: string;
  ordinal_position: number;
  data_type: string;
}

export interface MappingGenerationTarget extends MappingModeledEntity {
  source_system: MappingSourceSystem;
  entity_name: string;
  mapping_object_id: number | null;
  object_order: number;
  is_locked: boolean;
  has_sources: boolean;
  attributes: { attribute_id: number; attribute_name: string; modeled_attribute_name: string; ordinal_position: number; is_locked: boolean; is_authored: boolean }[];
}

export interface MappingGenerationPage {
  model_id: number; model_revision: number; items: MappingGenerationTarget[]; next_cursor: string | null;
}

export interface MappingObject {
  mapping_object_id: number;
  workflow_run_id: number | null;
  target: MappingModeledEntity;
  source_system: MappingSourceSystem;
  dependency_order: number;
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

export interface MappingOutputTemplateProvenance {
  output_template_id: number;
  output_template_code: string;
  output_template_name: string;
  output_template_target_type: OutputTemplateTargetType;
  output_template_schema_digest: string;
  is_active: boolean;
}

export interface MappingObjectDetail extends MappingObject {
  mapping_document: JsonObject | null;
  output_template: MappingOutputTemplateProvenance | null;
  created_at: string;
}

export interface MappingAttribute {
  mapping_attribute_id: number;
  workflow_run_id: number | null;
  mapping_object_id: number;
  target: MappingModeledAttribute;
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
  status: MappingStatus;
  is_locked: boolean;
}

export interface MappingAttributeDetail extends MappingAttribute {
  parent_object_mapping: MappingParentObjectReference;
  mapping_document: JsonObject | null;
  output_template: MappingOutputTemplateProvenance | null;
  created_at: string;
}

export interface MappingTransport {
  listMappingGenerationTargets: (tenantId: number, modelId: number, entityType: MappingEntityType, pageSize?: number, cursor?: string) => Promise<MappingGenerationPage>;
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

export type MappingApi = MappingTransport & ModelRecordReviewApi
  & Pick<ModelsApi, "listModels">
  & Pick<
    WorkflowsApi,
    | "applyWorkflowDraft"
    | "createWorkflowRun"
    | "executeMappingRun"
    | "listWorkflowRunEvents"
    | "listWorkflowRuns"
    | "readAgentCapabilities"
    | "readWorkflowDraftReview"
    | "readWorkflowRun"
  >;

export function createMappingApi(request: HttpRequest): MappingTransport {
  return {
    listMappingGenerationTargets: (tenantId, modelId, entityType, pageSize = 200, cursor) => {
      const query = new URLSearchParams({
        entity_type: entityType,
        page_size: String(pageSize),
      });
      if (cursor) query.set("cursor", cursor);
      return request<MappingGenerationPage>(
        `/api/v1/tenants/${tenantId}/models/${modelId}/mapping/generation-targets?${query}`,
      );
    },
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
  runTargets: (tenantId: number, modelId: number, entityType: MappingEntityType) => (
    ["mapping-run-targets", tenantId, modelId, entityType] as const
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

  for (;;) {
    const response = await api.listOutputTemplates(tenantId, targetType, 200, cursor);
    items.push(...response.items);
    if (!response.next_cursor) return items;
    if (seenCursors.has(response.next_cursor)) {
      throw new Error("Output Template cursor repeated");
    }
    seenCursors.add(response.next_cursor);
    cursor = response.next_cursor;
  }
}

export async function loadMappingGenerationTargets(
  api: Pick<MappingTransport, "listMappingGenerationTargets">,
  tenantId: number,
  modelId: number,
  entityType: MappingEntityType,
): Promise<{ modelRevision: number; items: MappingGenerationTarget[] }> {
  const items: MappingGenerationTarget[] = [];
  const seenCursors = new Set<string>();
  let cursor: string | undefined;
  let modelRevision: number | null = null;

  for (;;) {
    const response = await api.listMappingGenerationTargets(tenantId, modelId, entityType, 200, cursor);
    if (modelRevision !== null && response.model_revision !== modelRevision) {
      throw new Error("Mapping target revision changed while loading");
    }
    modelRevision = response.model_revision;
    items.push(...response.items);
    if (!response.next_cursor) return { modelRevision, items };
    if (seenCursors.has(response.next_cursor)) {
      throw new Error("Mapping target cursor repeated");
    }
    seenCursors.add(response.next_cursor);
    cursor = response.next_cursor;
  }
}

function mappingCollectionPath(
  tenantId: number,
  modelId: number,
  collection: "objects" | "attributes",
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
  if (filters.mappingObjectId !== undefined) query.set("mapping_object_id", String(filters.mappingObjectId));
  query.set("page_size", String(pageSize));
  if (cursor) query.set("cursor", cursor);
  return `/api/v1/tenants/${tenantId}/models/${modelId}/mapping/${collection}?${query}`;
}

function normalizeNaturalKeyFilter(value: string | undefined): string {
  return value?.replace(/^ +| +$/g, "").toLowerCase() ?? "";
}
