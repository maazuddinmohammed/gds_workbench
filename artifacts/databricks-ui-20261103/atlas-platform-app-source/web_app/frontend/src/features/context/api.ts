import type { ProjectRecordReviewApi } from "../project_record_review/api";
import type { HttpRequest } from "../../core/http";
import type { ReviewStatus } from "../../shared/contracts";

export type ContextWorkflow = "analysis" | "subject_area" | "logical" | "dimensional" | "mapping" | "code_generation" | "validation";
export interface ContextType {
  context_type_id: number;
  context_type_name: string;
  context_type_description: string | null;
  /** Workflows whose prompts receive this Type's records; only the type list carries it. */
  context_type_workflows?: ContextWorkflow[];
}
export interface ContextSourceSystem { system_id: number; system_code: string; system_name: string }
export interface ContextGroupReference {
  context_group_id: number;
  context_group_name: string;
  context_type: ContextType;
  source_system: ContextSourceSystem | null;
  is_active: boolean;
}
export interface ContextGroup extends ContextGroupReference {
  record_count: number;
  active_record_count: number;
  locked_record_count: number;
  updated_at: string;
}
export interface ContextGroupDetail extends ContextGroup {
  context_group_description: string | null;
  created_at: string;
}
export interface ContextRecord {
  context_record_id: string;
  group: ContextGroupReference;
  context_text_preview: string;
  text_truncated: boolean;
  source_reference_preview: string | null;
  source_reference_truncated: boolean;
  status: ReviewStatus;
  is_locked: boolean;
  updated_at: string;
}
export interface ContextRecordDetail extends ContextRecord {
  context_text: string;
  source_reference: string | null;
  created_at: string;
}
export interface ContextGroupFilters {
  contextTypeId?: number;
  sourceSystemId?: number;
  active?: boolean;
  namePrefix?: string;
}
export interface ContextRecordFilters {
  groupId?: number;
  contextTypeId?: number;
  sourceSystemId?: number;
  status?: ReviewStatus;
  locked?: boolean;
  textSearch?: string;
}
export interface ContextGroupPage {
  project_id: number; project_revision: number; items: ContextGroup[]; next_cursor: string | null;
}
export interface ContextRecordPage {
  project_id: number; project_revision: number; items: ContextRecord[]; next_cursor: string | null;
}
export interface SaveContextGroupCommand {
  action: "create" | "edit";
  expected_project_revision: number;
  context_group_id?: number;
  context_group_name: string;
  context_type_id: number;
  context_group_description: string | null;
  source_system_id: number | null;
  is_active: boolean;
}
export interface SaveContextRecordCommand {
  action: "create" | "edit";
  expected_project_revision: number;
  context_record_id: string;
  context_group_id: number;
  context_text: string;
  source_reference: string | null;
}
interface ContextSaveResult {
  project_id: number; project_revision: number; project_change_set_id: string; action_count: number;
}
export interface ContextApi extends ProjectRecordReviewApi {
  listContextTypes: (tenantId: number, projectId: number) => Promise<{ items: ContextType[] }>;
  listContextSourceSystems: (tenantId: number, projectId: number, pageSize?: number, cursor?: string) => Promise<{ items: ContextSourceSystem[]; next_cursor: string | null }>;
  listContextGroups: (tenantId: number, projectId: number, filters?: ContextGroupFilters, pageSize?: number, cursor?: string) => Promise<ContextGroupPage>;
  readContextGroup: (tenantId: number, projectId: number, groupId: number) => Promise<ContextGroupDetail>;
  listContextRecords: (tenantId: number, projectId: number, filters?: ContextRecordFilters, pageSize?: number, cursor?: string) => Promise<ContextRecordPage>;
  readContextRecord: (tenantId: number, projectId: number, recordId: string) => Promise<ContextRecordDetail>;
  saveContextGroup: (tenantId: number, projectId: number, command: SaveContextGroupCommand, idempotencyKey: string) => Promise<ContextSaveResult>;
  saveContextRecord: (tenantId: number, projectId: number, command: SaveContextRecordCommand, idempotencyKey: string) => Promise<ContextSaveResult>;
}
export function createContextApi(request: HttpRequest): Omit<ContextApi, keyof ProjectRecordReviewApi> {
  return {
    listContextTypes: (tenantId, projectId) => request(`/api/v1/tenants/${tenantId}/projects/${projectId}/context/types`),
    listContextSourceSystems: (tenantId, projectId, pageSize = 200, cursor) => {
      const query = new URLSearchParams({ page_size: String(pageSize) });
      if (cursor) query.set("cursor", cursor);
      return request(`/api/v1/tenants/${tenantId}/projects/${projectId}/context/source-systems?${query}`);
    },
    listContextGroups: (tenantId, projectId, filters = {}, pageSize = 200, cursor) => {
      const query = new URLSearchParams();
      if (filters.contextTypeId) query.set("context_type_id", String(filters.contextTypeId));
      if (filters.sourceSystemId) query.set("source_system_id", String(filters.sourceSystemId));
      if (filters.active !== undefined) query.set("active", String(filters.active));
      const prefix = filters.namePrefix?.replace(/^ +| +$/g, "").toLowerCase();
      if (prefix) query.set("name_prefix", prefix);
      query.set("page_size", String(pageSize));
      if (cursor) query.set("cursor", cursor);
      return request(`/api/v1/tenants/${tenantId}/projects/${projectId}/context/groups?${query}`);
    },
    readContextGroup: (tenantId, projectId, groupId) => request(`/api/v1/tenants/${tenantId}/projects/${projectId}/context/groups/${groupId}`),
    listContextRecords: (tenantId, projectId, filters = {}, pageSize = 200, cursor) => {
      const query = new URLSearchParams();
      if (filters.groupId) query.set("group_id", String(filters.groupId));
      if (filters.contextTypeId) query.set("context_type_id", String(filters.contextTypeId));
      if (filters.sourceSystemId) query.set("source_system_id", String(filters.sourceSystemId));
      if (filters.status) query.set("status", filters.status);
      if (filters.locked !== undefined) query.set("locked", String(filters.locked));
      const search = filters.textSearch?.trim();
      if (search) query.set("text_search", search);
      query.set("page_size", String(pageSize));
      if (cursor) query.set("cursor", cursor);
      return request(`/api/v1/tenants/${tenantId}/projects/${projectId}/context/records?${query}`);
    },
    readContextRecord: (tenantId, projectId, recordId) => request(`/api/v1/tenants/${tenantId}/projects/${projectId}/context/records/${encodeURIComponent(recordId)}`),
    saveContextGroup: (tenantId, projectId, command, key) => request(`/api/v1/tenants/${tenantId}/projects/${projectId}/change-sets/context-groups`, {
      method: "POST", headers: { "content-type": "application/json", "Idempotency-Key": key }, body: JSON.stringify(command),
    }),
    saveContextRecord: (tenantId, projectId, command, key) => request(`/api/v1/tenants/${tenantId}/projects/${projectId}/change-sets/context-records`, {
      method: "POST", headers: { "content-type": "application/json", "Idempotency-Key": key }, body: JSON.stringify(command),
    }),
  };
}
export const contextQueryKeys = {
  types: (tenantId: number, projectId: number) => ["context-types", tenantId, projectId] as const,
  systems: (tenantId: number, projectId: number) => ["context-source-systems", tenantId, projectId] as const,
  groups: (tenantId: number, projectId: number, filters: unknown) => ["context-groups", tenantId, projectId, filters] as const,
  group: (tenantId: number, projectId: number, groupId: number) => ["context-group", tenantId, projectId, groupId] as const,
  records: (tenantId: number, projectId: number, filters: unknown) => ["context-records", tenantId, projectId, filters] as const,
  record: (tenantId: number, projectId: number, recordId: string) => ["context-record", tenantId, projectId, recordId] as const,
};

export async function loadContextSystems(api: Pick<ContextApi, "listContextSourceSystems">, tenantId: number, projectId: number): Promise<ContextSourceSystem[]> {
  const choices = new Map<number, ContextSourceSystem>();
  const cursors = new Set<string>();
  let cursor: string | undefined;
  for (let pageNumber = 0; pageNumber < 250; pageNumber += 1) {
    const page = await api.listContextSourceSystems(tenantId, projectId, 200, cursor);
    for (const row of page.items) choices.set(row.system_id, row);
    cursor = page.next_cursor ?? undefined;
    if (!cursor) return [...choices.values()].sort((a, b) => a.system_code.localeCompare(b.system_code));
    if (cursors.has(cursor)) throw new Error("System pagination did not advance.");
    cursors.add(cursor);
  }
  throw new Error("System choices exceed the supported selection limit.");
}
