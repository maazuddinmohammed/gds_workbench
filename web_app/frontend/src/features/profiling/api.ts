import type { HttpRequest } from "../../core/http";
import type { ProjectInputScopeApi } from "../project_input_scope/api";
import type {
  WorkflowRunCommandResult,
  WorkflowRunStart,
  WorkflowsApi,
} from "../workflows/api";

export interface ProfilingFilters {
  objectId?: number;
  sourceTenantCode?: string;
  systemCode?: string;
  objectSchema?: string;
  objectName?: string;
}

export interface ProfilingRouteSearch extends ProfilingFilters {
  returnObjectId?: number;
}

export interface ProfilingObject {
  object_id: number;
  source_tenant_id: number;
  source_tenant_code: string;
  source_tenant_name: string;
  system_id: number;
  system_code: string;
  system_name: string;
  connection_id: number;
  connection_code: string;
  object_schema: string;
  object_name: string;
  profiled_attribute_count: number;
  last_profiled_at: string;
}

export interface ProfilingObjectPage {
  project_id: number;
  project_revision: number;
  items: ProfilingObject[];
  next_cursor: string | null;
}

export interface AttributeProfile {
  attribute_id: number;
  attribute_name: string;
  attribute_ordinal_position: number;
  attribute_data_type: string;
  attribute_inferred_data_type: string | null;
  attribute_description: string | null;
  source_context_digest: string;
  row_count: number;
  non_null_count: number;
  null_count: number;
  blank_count: number | null;
  distinct_count: number | null;
  min_data_length: number | null;
  max_data_length: number | null;
  avg_data_length: string | number | null;
  percent_populated: string | number | null;
  percent_duplicates: string | number | null;
  percent_null: string | number | null;
  percent_blank: string | number | null;
  percent_distinct: string | number | null;
  provenance: {
    agent_run_id: string | null;
    workflow_run_id: number | null;
  };
  created_at: string;
  updated_at: string;
}

export interface ProfilingObjectDetail extends ProfilingObject {
  project_id: number;
  project_revision: number;
  object_description: string | null;
  attribute_profiles: AttributeProfile[];
  profiles_truncated: boolean;
}

export interface CreateProfilingRunCommand {
  expected_project_revision: number;
  project_workflow: "profiling";
  selected_object_ids: number[];
  requested_batch_id: string | null;
}

export type ProfilingRunStart = WorkflowRunStart;

export interface ProfilingTransport {
  listProfilingObjects: (
    tenantId: number,
    projectId: number,
    filters?: ProfilingFilters,
    pageSize?: number,
    cursor?: string,
  ) => Promise<ProfilingObjectPage>;
  readProfilingObject: (
    tenantId: number,
    projectId: number,
    objectId: number,
  ) => Promise<ProfilingObjectDetail>;
  createProfilingRun: (
    tenantId: number,
    projectId: number,
    command: CreateProfilingRunCommand,
    idempotencyKey: string,
  ) => Promise<WorkflowRunCommandResult>;
}

export type ProfilingApi = ProfilingTransport
  & Pick<
    WorkflowsApi,
    | "listWorkflowRuns"
    | "readWorkflowRun"
    | "listWorkflowRunEvents"
    | "executeProfilingRun"
    | "cancelWorkflowRun"
  >
  & Pick<ProjectInputScopeApi, "listProjectInputScope">;

export function createProfilingApi(request: HttpRequest): ProfilingTransport {
  return {
    listProfilingObjects: (tenantId, projectId, filters = {}, pageSize = 200, cursor) => {
      const query = new URLSearchParams();
      if (filters.objectId) query.set("object_id", String(filters.objectId));
      const naturalKeyFilters = {
        source_tenant_code: normalizeNaturalKeyFilter(filters.sourceTenantCode),
        system_code: normalizeNaturalKeyFilter(filters.systemCode),
        object_schema: normalizeNaturalKeyFilter(filters.objectSchema),
        object_name: normalizeNaturalKeyFilter(filters.objectName),
      };
      for (const [key, value] of Object.entries(naturalKeyFilters)) {
        if (value) query.set(key, value);
      }
      query.set("page_size", String(pageSize));
      if (cursor) query.set("cursor", cursor);
      return request<ProfilingObjectPage>(
        `/api/v1/tenants/${tenantId}/projects/${projectId}/profiling?${query}`,
      );
    },
    readProfilingObject: (tenantId, projectId, objectId) =>
      request<ProfilingObjectDetail>(
        `/api/v1/tenants/${tenantId}/projects/${projectId}/profiling/${objectId}`,
      ),
    createProfilingRun: (tenantId, projectId, command, idempotencyKey) =>
      request<WorkflowRunCommandResult>(
        `/api/v1/tenants/${tenantId}/projects/${projectId}/runs`,
        {
          method: "POST",
          headers: {
            "content-type": "application/json",
            "Idempotency-Key": idempotencyKey,
          },
          body: JSON.stringify(command),
        },
      ),
  };
}

export const profilingQueryKeys = {
  results: (tenantId: number, projectId: number, filters: unknown) => (
    ["profiling-results", tenantId, projectId, filters] as const
  ),
  result: (tenantId: number, projectId: number, objectId: number | null) => (
    ["profiling-result", tenantId, projectId, objectId] as const
  ),
  runs: (tenantId: number, projectId: number, state?: string) => (
    state === undefined
      ? ["profiling-runs", tenantId, projectId] as const
      : ["profiling-runs", tenantId, projectId, state] as const
  ),
  run: (tenantId: number, projectId: number, runId: number) => (
    ["workflow-run", tenantId, projectId, runId] as const
  ),
  eventFamily: (tenantId: number, projectId: number, runId: number) => (
    ["workflow-run-events", tenantId, projectId, runId] as const
  ),
  events: (
    tenantId: number,
    projectId: number,
    runId: number,
    afterSequence: number,
  ) => [
    ...profilingQueryKeys.eventFamily(tenantId, projectId, runId),
    afterSequence,
  ] as const,
  scope: (tenantId: number, projectId: number) => (
    ["profiling-run-scope", tenantId, projectId] as const
  ),
};

export function validateProfilingRouteSearch(
  search: Record<string, unknown>,
): ProfilingRouteSearch {
  const positiveInteger = (value: unknown): number | undefined => {
    if (typeof value !== "number" && typeof value !== "string") return undefined;
    const parsed = Number(value);
    return Number.isSafeInteger(parsed) && parsed > 0 ? parsed : undefined;
  };
  const boundedString = (value: unknown): string | undefined => (
    typeof value === "string" && value.trim() && value.length <= 400 ? value : undefined
  );
  const result: ProfilingRouteSearch = {};
  const objectId = positiveInteger(search.objectId);
  const sourceTenantCode = boundedString(search.sourceTenantCode);
  const systemCode = boundedString(search.systemCode);
  const objectSchema = boundedString(search.objectSchema);
  const objectName = boundedString(search.objectName);
  const returnObjectId = positiveInteger(search.returnObjectId);
  if (objectId !== undefined) result.objectId = objectId;
  if (sourceTenantCode !== undefined) result.sourceTenantCode = sourceTenantCode;
  if (systemCode !== undefined) result.systemCode = systemCode;
  if (objectSchema !== undefined) result.objectSchema = objectSchema;
  if (objectName !== undefined) result.objectName = objectName;
  if (returnObjectId !== undefined) result.returnObjectId = returnObjectId;
  return result;
}

function normalizeNaturalKeyFilter(value: string | undefined): string {
  return value?.replace(/^ +| +$/g, "").toLowerCase() ?? "";
}
