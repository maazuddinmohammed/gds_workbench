import type { HttpRequest } from "../../core/http";

export type ZoneCode = "source" | "bronze" | "silver" | "gold";

export interface ModelScopeFilters {
  zone?: string;
  systemCode?: string;
  sourceTenantCode?: string;
  objectName?: string;
}

export interface ModelScopeObject {
  model_scope_id: number;
  object_id: number;
  connection_id: number;
  system_id: number;
  system_code: string;
  system_name: string;
  source_tenant_id: number;
  source_tenant_code: string;
  source_tenant_name: string;
  object_schema: string;
  object_name: string;
  zone_code: ZoneCode;
  batch_attribute_name: string | null;
  attribute_count: number;
  is_bronze_source_eligible: boolean;
  is_dimensional_source_eligible: boolean;
  is_logical_mapping_target_eligible: boolean;
  is_dimensional_mapping_target_eligible: boolean;
  created_at: string;
  updated_at: string;
}

export interface ObjectAttribute {
  attribute_id: number;
  attribute_name: string;
  attribute_ordinal_position: number;
  attribute_description: string | null;
  attribute_data_type: string;
  attribute_nullability: boolean;
  is_surrogate_key: boolean;
  is_natural_key: boolean;
  is_meta_data: boolean;
  is_masking_required: boolean;
  is_mapped: boolean;
  is_purge: boolean;
  is_active: boolean;
}

export interface ModelScopePage {
  model_id: number;
  model_revision: number;
  items: ModelScopeObject[];
  next_cursor: string | null;
}

export interface ModelScopeDetail extends ModelScopeObject {
  attributes: ObjectAttribute[];
}

export interface ModelScopeApi {
  listModelScope: (
    tenantId: number,
    modelId: number,
    filters?: ModelScopeFilters,
    pageSize?: number,
    cursor?: string,
  ) => Promise<ModelScopePage>;
  readModelScopeObject: (
    tenantId: number,
    modelId: number,
    objectId: number,
  ) => Promise<ModelScopeDetail>;
}

export function createModelScopeApi(request: HttpRequest): ModelScopeApi {
  return {
    listModelScope: (tenantId, modelId, filters = {}, pageSize = 200, cursor) => {
      const query = new URLSearchParams();
      const normalizedFilters = {
        zone: normalizeNaturalKeyFilter(filters.zone),
        system_code: normalizeNaturalKeyFilter(filters.systemCode),
        source_tenant_code: normalizeNaturalKeyFilter(filters.sourceTenantCode),
        object_name: normalizeNaturalKeyFilter(filters.objectName),
      };
      for (const [key, value] of Object.entries(normalizedFilters)) {
        if (value) query.set(key, value);
      }
      query.set("page_size", String(pageSize));
      if (cursor) query.set("cursor", cursor);
      return request<ModelScopePage>(
        `/api/v1/tenants/${tenantId}/models/${modelId}/scope?${query}`,
      );
    },
    readModelScopeObject: (tenantId, modelId, objectId) =>
      request<ModelScopeDetail>(
        `/api/v1/tenants/${tenantId}/models/${modelId}/scope/${objectId}`,
      ),
  };
}

function normalizeNaturalKeyFilter(value: string | undefined): string {
  return value?.replace(/^ +| +$/g, "").toLowerCase() ?? "";
}
