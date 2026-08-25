import type { HttpRequest } from "../../core/http";
import type { JsonObject, ReviewStatus } from "../../shared/contracts";

export type { JsonObject, JsonValue } from "../../shared/contracts";

export type ApplicableLayer =
  | "analysis"
  | "conceptual"
  | "logical"
  | "dimensional"
  | "mapping";

export interface AssertionSourceTenant {
  tenant_id: number;
  tenant_code: string;
  tenant_name: string;
}

export interface AssertionSourceSystem {
  system_id: number;
  system_code: string;
  system_name: string;
}

export interface AssertionDocumentFilters {
  sourceSystemId?: number;
  sourceSystemCode?: string;
  active?: boolean;
  namePrefix?: string;
}

export interface AssertionDocument {
  modeling_assertion_document_id: number;
  workflow_run_id: number | null;
  modeling_assertion_document_name: string;
  modeling_assertion_document_type: string | null;
  source_tenant: AssertionSourceTenant | null;
  source_system: AssertionSourceSystem | null;
  is_active: boolean;
  record_count: number;
  active_record_count: number;
  needs_review_record_count: number;
  locked_record_count: number;
  updated_at: string;
}

export interface AssertionDocumentPage {
  model_id: number;
  model_revision: number;
  items: AssertionDocument[];
  next_cursor: string | null;
}

export interface AssertionDocumentDetail extends AssertionDocument {
  modeling_assertion_file_pattern: string | null;
  modeling_assertion_document_description: string | null;
  modeling_assertion_document_metadata: JsonObject;
  agent_run_id: string | null;
  created_at: string;
}

export interface AssertionRecordFilters {
  documentId?: number;
  documentName?: string;
  sourceSystemId?: number;
  sourceSystemCode?: string;
  status?: ReviewStatus;
  locked?: boolean;
  applicableLayer?: ApplicableLayer;
  keyPrefix?: string;
}

export interface AssertionDocumentReference {
  modeling_assertion_document_id: number;
  modeling_assertion_document_name: string;
  modeling_assertion_document_type: string | null;
  source_tenant: AssertionSourceTenant | null;
  source_system: AssertionSourceSystem | null;
  is_active: boolean;
}

export interface AssertionRecord {
  modeling_assertion_record_id: number;
  workflow_run_id: number | null;
  document: AssertionDocumentReference;
  modeling_assertion_record_key: string;
  modeling_assertion_record_type: string;
  modeling_assertion_applicable_layers: ApplicableLayer[];
  modeling_assertion_confidence: "low" | "medium" | "high" | null;
  modeling_assertion_record_status: ReviewStatus;
  modeling_assertion_record_is_locked: boolean;
  updated_at: string;
}

export interface AssertionRecordPage {
  model_id: number;
  model_revision: number;
  items: AssertionRecord[];
  next_cursor: string | null;
}

export interface AssertionRecordDetail extends AssertionRecord {
  modeling_assertion_text: string;
  modeling_assertion_details: JsonObject;
  modeling_assertion_source_location: JsonObject | null;
  agent_run_id: string | null;
  created_at: string;
}

export interface AssertionsApi {
  listAssertionDocuments: (
    tenantId: number,
    modelId: number,
    filters?: AssertionDocumentFilters,
    pageSize?: number,
    cursor?: string,
  ) => Promise<AssertionDocumentPage>;
  readAssertionDocument: (
    tenantId: number,
    modelId: number,
    documentId: number,
  ) => Promise<AssertionDocumentDetail>;
  listAssertionRecords: (
    tenantId: number,
    modelId: number,
    filters?: AssertionRecordFilters,
    pageSize?: number,
    cursor?: string,
  ) => Promise<AssertionRecordPage>;
  readAssertionRecord: (
    tenantId: number,
    modelId: number,
    recordId: number,
  ) => Promise<AssertionRecordDetail>;
}

export function createAssertionsApi(request: HttpRequest): AssertionsApi {
  return {
    listAssertionDocuments: (
      tenantId,
      modelId,
      filters = {},
      pageSize = 200,
      cursor,
    ) => {
      const query = new URLSearchParams();
      if (filters.sourceSystemId) {
        query.set("source_system_id", String(filters.sourceSystemId));
      }
      const sourceSystemCode = normalizeNaturalKeyFilter(filters.sourceSystemCode);
      const namePrefix = normalizeNaturalKeyFilter(filters.namePrefix);
      if (sourceSystemCode) query.set("source_system_code", sourceSystemCode);
      if (filters.active !== undefined) query.set("active", String(filters.active));
      if (namePrefix) query.set("name_prefix", namePrefix);
      query.set("page_size", String(pageSize));
      if (cursor) query.set("cursor", cursor);
      return request<AssertionDocumentPage>(
        `/api/v1/tenants/${tenantId}/models/${modelId}/assertions/documents?${query}`,
      );
    },
    readAssertionDocument: (tenantId, modelId, documentId) =>
      request<AssertionDocumentDetail>(
        `/api/v1/tenants/${tenantId}/models/${modelId}/assertions/documents/${documentId}`,
      ),
    listAssertionRecords: (
      tenantId,
      modelId,
      filters = {},
      pageSize = 200,
      cursor,
    ) => {
      const query = new URLSearchParams();
      if (filters.documentId) query.set("document_id", String(filters.documentId));
      const normalized = {
        document_name: normalizeNaturalKeyFilter(filters.documentName),
        source_system_code: normalizeNaturalKeyFilter(filters.sourceSystemCode),
        key_prefix: normalizeNaturalKeyFilter(filters.keyPrefix),
      };
      if (normalized.document_name) query.set("document_name", normalized.document_name);
      if (filters.sourceSystemId) {
        query.set("source_system_id", String(filters.sourceSystemId));
      }
      if (normalized.source_system_code) {
        query.set("source_system_code", normalized.source_system_code);
      }
      if (filters.status) query.set("status", filters.status);
      if (filters.locked !== undefined) query.set("locked", String(filters.locked));
      if (filters.applicableLayer) query.set("applicable_layer", filters.applicableLayer);
      if (normalized.key_prefix) query.set("key_prefix", normalized.key_prefix);
      query.set("page_size", String(pageSize));
      if (cursor) query.set("cursor", cursor);
      return request<AssertionRecordPage>(
        `/api/v1/tenants/${tenantId}/models/${modelId}/assertions/records?${query}`,
      );
    },
    readAssertionRecord: (tenantId, modelId, recordId) =>
      request<AssertionRecordDetail>(
        `/api/v1/tenants/${tenantId}/models/${modelId}/assertions/records/${recordId}`,
      ),
  };
}

export const assertionsQueryKeys = {
  documents: (tenantId: number, modelId: number, filters: unknown) => (
    ["assertion-documents", tenantId, modelId, filters] as const
  ),
  document: (tenantId: number, modelId: number, documentId: number) => (
    ["assertion-document", tenantId, modelId, documentId] as const
  ),
  records: (tenantId: number, modelId: number, filters: unknown) => (
    ["assertion-records", tenantId, modelId, filters] as const
  ),
  record: (tenantId: number, modelId: number, recordId: number) => (
    ["assertion-record", tenantId, modelId, recordId] as const
  ),
};

function normalizeNaturalKeyFilter(value: string | undefined): string {
  return value?.replace(/^ +| +$/g, "").toLowerCase() ?? "";
}
