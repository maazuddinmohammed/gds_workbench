import type { HttpRequest } from "../../core/http";
import type { ModelScopeApi } from "../model_scope/api";
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
  model_id: number;
  model_revision: number;
  items: ProfilingObject[];
  next_cursor: string | null;
}

export interface AttributeProfile {
  attribute_id: number;
  attribute_name: string;
  attribute_ordinal_position: number;
  attribute_data_type: string;
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
  model_id: number;
  model_revision: number;
  attribute_profiles: AttributeProfile[];
  profiles_truncated: boolean;
}

export interface CreateProfilingRunCommand {
  expected_model_revision: number;
  model_workflow: "profiling";
  selected_object_ids: number[];
  requested_batch_id: string | null;
}

export type ProfilingRunStart = WorkflowRunStart;

export interface ProfilingTransport {
  listProfilingObjects: (
    tenantId: number,
    modelId: number,
    filters?: ProfilingFilters,
    pageSize?: number,
    cursor?: string,
  ) => Promise<ProfilingObjectPage>;
  readProfilingObject: (
    tenantId: number,
    modelId: number,
    objectId: number,
  ) => Promise<ProfilingObjectDetail>;
  createProfilingRun: (
    tenantId: number,
    modelId: number,
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
  >
  & Pick<ModelScopeApi, "listModelScope">;

export function createProfilingApi(request: HttpRequest): ProfilingTransport {
  return {
    listProfilingObjects: (tenantId, modelId, filters = {}, pageSize = 200, cursor) => {
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
        `/api/v1/tenants/${tenantId}/models/${modelId}/profiling?${query}`,
      );
    },
    readProfilingObject: (tenantId, modelId, objectId) =>
      request<ProfilingObjectDetail>(
        `/api/v1/tenants/${tenantId}/models/${modelId}/profiling/${objectId}`,
      ),
    createProfilingRun: (tenantId, modelId, command, idempotencyKey) =>
      request<WorkflowRunCommandResult>(
        `/api/v1/tenants/${tenantId}/models/${modelId}/runs`,
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
  results: (tenantId: number, modelId: number, filters: unknown) => (
    ["profiling-results", tenantId, modelId, filters] as const
  ),
  result: (tenantId: number, modelId: number, objectId: number | null) => (
    ["profiling-result", tenantId, modelId, objectId] as const
  ),
  runs: (tenantId: number, modelId: number, state?: string) => (
    state === undefined
      ? ["profiling-runs", tenantId, modelId] as const
      : ["profiling-runs", tenantId, modelId, state] as const
  ),
  run: (tenantId: number, modelId: number, runId: number) => (
    ["workflow-run", tenantId, modelId, runId] as const
  ),
  eventFamily: (tenantId: number, modelId: number, runId: number) => (
    ["workflow-run-events", tenantId, modelId, runId] as const
  ),
  events: (
    tenantId: number,
    modelId: number,
    runId: number,
    afterSequence: number,
  ) => [
    ...profilingQueryKeys.eventFamily(tenantId, modelId, runId),
    afterSequence,
  ] as const,
  scope: (tenantId: number, modelId: number) => (
    ["profiling-run-scope", tenantId, modelId] as const
  ),
};

function normalizeNaturalKeyFilter(value: string | undefined): string {
  return value?.replace(/^ +| +$/g, "").toLowerCase() ?? "";
}
