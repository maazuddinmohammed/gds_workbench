import type { HttpRequest } from "../../core/http";
import type { JsonObject } from "../../shared/contracts";
import type { ProjectWorkflow, WorkflowRunState } from "../workflows/api";

export type { ProjectWorkflow, WorkflowRunState } from "../workflows/api";

export type ProjectStatus = "active" | "archived";

export interface ProjectLedgerRecord {
  project_id: number;
  project_name: string;
  project_description: string | null;
  project_revision: number;
  is_locked?: boolean;
  project_input_scope_object_count: number;
  latest_workflow: ProjectWorkflow | null;
  latest_run_status: string | null;
  updated_at: string;
}

export interface ProjectCollection {
  items: ProjectLedgerRecord[];
  next_cursor: string | null;
}

export interface ProjectSchemaDefinition { schema_name: string; description: string | null; }
export type ProjectEntityScdType = "type_1" | "type_2";

export interface ProjectDetail {
  project_id: number;
  tenant_id: number;
  project_name: string;
  project_description: string | null;
  project_revision: number;
  is_locked?: boolean;
  project_input_scope_object_count: number;
  logical_schemas: ProjectSchemaDefinition[];
  dimensional_schemas: ProjectSchemaDefinition[];
  silver_model_naming_instructions: string | null;
  silver_model_audit_columns_template: unknown;
  logical_entity_scd_type?: ProjectEntityScdType | null;
  dimensional_entity_scd_type?: ProjectEntityScdType | null;
  logical_coverage_threshold_percent: number;
  dimensional_coverage_threshold_percent: number;
  logical_enforce_coverage_threshold: boolean;
  dimensional_enforce_coverage_threshold: boolean;
  gold_model_naming_instructions: string | null;
  gold_model_technical_columns_template: unknown;
  gold_model_audit_columns_template: unknown;
  default_agent_sdk_code: string | null;
  default_agent_provider_code: string | null;
  default_agent_model_code: string | null;
  default_reasoning_effort_code: string | null;
  default_max_turns: number | null;
  default_validation_retry_count: number | null;
  default_mapping_source_system_id?: number | null;
  is_active: boolean;
  updated_at: string;
}

export type LedgerWorkflow =
  | "scope"
  | "profiling"
  | "analysis"
  | "context"
  | "conceptual"
  | "logical"
  | "dimensional";

export type WorkflowLedgerState =
  | "empty"
  | "ready"
  | "not_started"
  | "queued"
  | "running"
  | "results_available"
  | "completed_no_results"
  | "failed"
  | "cancelled";

export type QualityWarningCode =
  | "scope_empty"
  | "profiling_results_unavailable"
  | "logical_results_unavailable";

export interface WorkflowLedgerEntry {
  workflow: LedgerWorkflow;
  result_count: number;
  locked_count: number;
  latest_run_id: number | null;
  latest_run_state: WorkflowRunState | null;
  latest_run_created_at: string | null;
  state: WorkflowLedgerState;
  quality_warning_codes: QualityWarningCode[];
}

export interface ProjectWorkflowOverview {
  project_id: number;
  project_revision: number;
  items: WorkflowLedgerEntry[];
  section_states?: ProjectSectionState[];
}

export interface ProjectSectionState {
  section: "overview" | "settings" | "scope" | "metadata-enrichment" | "profiling"
    | "context" | "analysis" | "conceptual" | "logical" | "dimensional" | "mapping"
    | "code-generation" | "validation";
  state: "available" | "ready" | "empty" | "not_run" | "queued" | "running"
    | "completed" | "failed" | "cancelled" | "results_available";
}

export interface CreateProjectCommand {
  project_name: string;
  project_description: string | null;
  logical_schemas: ProjectSchemaDefinition[];
  dimensional_schemas: ProjectSchemaDefinition[];
  silver_model_naming_instructions: string | null;
  silver_model_audit_columns_template: JsonObject | null;
  logical_entity_scd_type: ProjectEntityScdType | null;
  dimensional_entity_scd_type?: ProjectEntityScdType | null;
  logical_coverage_threshold_percent?: number | null;
  dimensional_coverage_threshold_percent?: number | null;
  logical_enforce_coverage_threshold?: boolean;
  dimensional_enforce_coverage_threshold?: boolean;
  gold_model_naming_instructions: string | null;
  gold_model_technical_columns_template: JsonObject | null;
  gold_model_audit_columns_template: JsonObject | null;
  default_agent_sdk_code: string | null;
  default_agent_provider_code: string | null;
  default_agent_model_code: string | null;
  default_reasoning_effort_code: string | null;
  default_max_turns: number | null;
  default_validation_retry_count: number | null;
  default_mapping_source_system_id?: number | null;
}

export interface ProjectCommandResult {
  project_id: number;
  tenant_id: number;
  project_revision: number;
  is_active: boolean;
  updated_at: string;
}

export interface UpdateProjectCommand extends CreateProjectCommand {
  expected_project_revision: number;
}

export interface ProjectsApi {
  setProjectLock: (tenantId: number, projectId: number, command: { expected_project_revision: number; is_locked: boolean }) => Promise<ProjectCommandResult>;
  readProjectTemplates: (tenantId: number) => Promise<Record<string, string | JsonObject>>;
  createProject: (tenantId: number, command: CreateProjectCommand) => Promise<ProjectCommandResult>;
  updateProject: (tenantId: number, projectId: number, command: UpdateProjectCommand) => Promise<ProjectCommandResult>;
  listProjects: (
    tenantId: number,
    status: ProjectStatus,
    pageSize?: number,
    cursor?: string,
  ) => Promise<ProjectCollection>;
  readProject: (tenantId: number, projectId: number) => Promise<ProjectDetail>;
  readProjectOverview: (
    tenantId: number,
    projectId: number,
  ) => Promise<ProjectWorkflowOverview>;
}

export function createProjectsApi(request: HttpRequest): ProjectsApi {
  return {
    setProjectLock: (tenantId, projectId, command) => request(`/api/v1/tenants/${tenantId}/projects/${projectId}/lock`, {
      method: "PUT", headers: { "content-type": "application/json" }, body: JSON.stringify(command),
    }),
    readProjectTemplates: (tenantId) => request(`/api/v1/tenants/${tenantId}/projects/templates`),
    createProject: (tenantId, command) => request<ProjectCommandResult>(`/api/v1/tenants/${tenantId}/projects`, {
      method: "POST",
      headers: { "content-type": "application/json" },
      body: JSON.stringify(command),
    }),
    updateProject: (tenantId, projectId, command) => request<ProjectCommandResult>(`/api/v1/tenants/${tenantId}/projects/${projectId}`, {
      method: "PUT",
      headers: { "content-type": "application/json" },
      body: JSON.stringify(command),
    }),
    listProjects: (tenantId, status, pageSize = 200, cursor) => {
      const query = new URLSearchParams({ status, page_size: String(pageSize) });
      if (cursor) query.set("cursor", cursor);
      return request<ProjectCollection>(`/api/v1/tenants/${tenantId}/projects?${query}`);
    },
    readProject: (tenantId, projectId) =>
      request<ProjectDetail>(`/api/v1/tenants/${tenantId}/projects/${projectId}`),
    readProjectOverview: (tenantId, projectId) =>
      request<ProjectWorkflowOverview>(
        `/api/v1/tenants/${tenantId}/projects/${projectId}/overview`,
      ),
  };
}
