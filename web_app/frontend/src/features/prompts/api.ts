import type { HttpRequest } from "../../core/http";
import type { ModelWorkflow, WorkflowExecutionMode } from "../workflows/api";

export type PromptOwnershipScope = "global" | "tenant";
export type PromptVersionStatus = "draft" | "published" | "retired";

export interface PromptStageVariable {
  name: string;
  resolver_key: string;
  data_type: "text" | "integer" | "number" | "boolean" | "json";
  is_required: boolean;
  description: string;
  example: unknown;
  order: number;
}

export interface PromptStage {
  workflow_stage_id: number;
  model_workflow: ModelWorkflow;
  workflow_execution_mode: WorkflowExecutionMode | null;
  workflow_stage_code: string;
  workflow_stage_name: string;
  workflow_stage_description: string | null;
  workflow_stage_order: number;
  allowed_variables: PromptStageVariable[];
}

export interface PromptStageCatalog {
  tenant_id: number;
  items: PromptStage[];
}

export interface PromptTemplateFilters {
  workflow?: ModelWorkflow;
  mode?: WorkflowExecutionMode;
  stageCode?: string;
  status?: PromptVersionStatus;
}

export interface PromptTemplateSummary {
  prompt_template_id: number;
  workflow_stage_id: number;
  model_workflow: ModelWorkflow;
  workflow_execution_mode: WorkflowExecutionMode | null;
  workflow_stage_code: string;
  workflow_stage_name: string;
  prompt_template_ownership_scope: PromptOwnershipScope;
  owner_tenant_id: number | null;
  prompt_template_code: string;
  prompt_template_name: string;
  prompt_template_description: string | null;
  is_active: boolean;
  latest_version_id: number | null;
  latest_version_number: number | null;
  latest_version_status: PromptVersionStatus | null;
  latest_version_digest: string | null;
  latest_version_updated_at: string | null;
  updated_at: string;
}

export interface PromptTemplatePage {
  tenant_id: number;
  items: PromptTemplateSummary[];
  next_cursor: string | null;
}

export interface PromptTemplateVersion {
  prompt_template_version_id: number;
  prompt_template_id: number;
  workflow_stage_id: number;
  prompt_template_version_number: number;
  system_prompt_template: string;
  instruction_prompt_template: string;
  tool_instruction_prompt_template: string | null;
  prompt_template_digest: string;
  prompt_template_version_status: PromptVersionStatus;
  published_at: string | null;
  retired_at: string | null;
  created_at: string;
  updated_at: string;
}

export interface PromptTemplateDetail {
  tenant_id: number;
  template: PromptTemplateSummary;
  allowed_variables: PromptStageVariable[];
  versions: PromptTemplateVersion[];
}

export interface PromptTemplateHeader {
  prompt_template_id: number;
  workflow_stage_id: number;
  prompt_template_ownership_scope: PromptOwnershipScope;
  owner_tenant_id: number | null;
  prompt_template_code: string;
  prompt_template_name: string;
  prompt_template_description: string | null;
  is_active: boolean;
  created_at: string;
  updated_at: string;
}

export interface CreatePromptTemplateCommand {
  workflow_stage_id: number;
  prompt_template_ownership_scope: PromptOwnershipScope;
  prompt_template_code: string;
  prompt_template_name: string;
  prompt_template_description: string | null;
  is_active: boolean;
}

export interface UpdatePromptTemplateCommand {
  prompt_template_name: string;
  prompt_template_description: string | null;
  is_active: boolean;
  expected_updated_at: string;
}

export interface SavePromptDraftCommand {
  expected_prompt_template_version_id: number | null;
  expected_updated_at: string | null;
  system_prompt_template: string;
  instruction_prompt_template: string;
  tool_instruction_prompt_template: string | null;
}

export interface PromptAssignmentTarget {
  prompt_assignment_id: number;
  prompt_assignment_scope: "global_default" | "model_default";
  prompt_template_version_id: number;
  prompt_template_version_number: number;
  prompt_template_digest: string;
  prompt_template_id: number;
  prompt_template_ownership_scope: PromptOwnershipScope;
  owner_tenant_id: number | null;
  prompt_template_code: string;
  prompt_template_name: string;
  assigned_at: string;
}

export interface ModelPromptAssignmentState {
  workflow_stage_id: number;
  model_workflow: ModelWorkflow;
  workflow_execution_mode: WorkflowExecutionMode | null;
  workflow_stage_code: string;
  workflow_stage_name: string;
  workflow_stage_order: number;
  model_assignment: PromptAssignmentTarget | null;
  global_assignment: PromptAssignmentTarget | null;
  effective_source: "global_default" | "model_default" | "none";
  effective_assignment: PromptAssignmentTarget | null;
}

export interface ModelPromptAssignments {
  tenant_id: number;
  model_id: number;
  items: ModelPromptAssignmentState[];
}

export interface SetModelPromptAssignmentCommand {
  prompt_template_version_id: number | null;
  expected_prompt_assignment_id: number | null;
}

export interface PromptsApi {
  listPromptStages: (tenantId: number) => Promise<PromptStageCatalog>;
  listPromptTemplates: (
    tenantId: number,
    filters?: PromptTemplateFilters,
    pageSize?: number,
    cursor?: string,
  ) => Promise<PromptTemplatePage>;
  readPromptTemplate: (
    tenantId: number,
    promptTemplateId: number,
  ) => Promise<PromptTemplateDetail>;
  createPromptTemplate: (
    tenantId: number,
    command: CreatePromptTemplateCommand,
  ) => Promise<PromptTemplateHeader>;
  updatePromptTemplate: (
    tenantId: number,
    promptTemplateId: number,
    command: UpdatePromptTemplateCommand,
  ) => Promise<PromptTemplateHeader>;
  savePromptDraft: (
    tenantId: number,
    promptTemplateId: number,
    command: SavePromptDraftCommand,
  ) => Promise<PromptTemplateVersion>;
  publishPromptVersion: (
    tenantId: number,
    promptTemplateId: number,
    promptTemplateVersionId: number,
  ) => Promise<PromptTemplateVersion>;
  retirePromptVersion: (
    tenantId: number,
    promptTemplateId: number,
    promptTemplateVersionId: number,
  ) => Promise<PromptTemplateVersion>;
  listModelPromptAssignments: (
    tenantId: number,
    modelId: number,
  ) => Promise<ModelPromptAssignments>;
  setModelPromptAssignment: (
    tenantId: number,
    modelId: number,
    workflowStageId: number,
    command: SetModelPromptAssignmentCommand,
  ) => Promise<ModelPromptAssignmentState>;
}

export function createPromptsApi(request: HttpRequest): PromptsApi {
  return {
    listPromptStages: (tenantId) =>
      request<PromptStageCatalog>(`/api/v1/tenants/${tenantId}/prompts/stages`),
    listPromptTemplates: (tenantId, filters = {}, pageSize = 50, cursor) =>
      request<PromptTemplatePage>(
        promptTemplatesPath(tenantId, filters, pageSize, cursor),
      ),
    readPromptTemplate: (tenantId, promptTemplateId) =>
      request<PromptTemplateDetail>(
        `/api/v1/tenants/${tenantId}/prompts/templates/${promptTemplateId}`,
      ),
    createPromptTemplate: (tenantId, command) =>
      request<PromptTemplateHeader>(`/api/v1/tenants/${tenantId}/prompts/templates`, {
        method: "POST",
        headers: { "content-type": "application/json" },
        body: JSON.stringify(command),
      }),
    updatePromptTemplate: (tenantId, promptTemplateId, command) =>
      request<PromptTemplateHeader>(
        `/api/v1/tenants/${tenantId}/prompts/templates/${promptTemplateId}`,
        {
          method: "PUT",
          headers: { "content-type": "application/json" },
          body: JSON.stringify(command),
        },
      ),
    savePromptDraft: (tenantId, promptTemplateId, command) =>
      request<PromptTemplateVersion>(
        `/api/v1/tenants/${tenantId}/prompts/templates/${promptTemplateId}/draft`,
        {
          method: "PUT",
          headers: { "content-type": "application/json" },
          body: JSON.stringify(command),
        },
      ),
    publishPromptVersion: (tenantId, promptTemplateId, promptTemplateVersionId) =>
      request<PromptTemplateVersion>(
        `/api/v1/tenants/${tenantId}/prompts/templates/${promptTemplateId}/versions/${promptTemplateVersionId}/publish`,
        { method: "POST" },
      ),
    retirePromptVersion: (tenantId, promptTemplateId, promptTemplateVersionId) =>
      request<PromptTemplateVersion>(
        `/api/v1/tenants/${tenantId}/prompts/templates/${promptTemplateId}/versions/${promptTemplateVersionId}/retire`,
        { method: "POST" },
      ),
    listModelPromptAssignments: (tenantId, modelId) =>
      request<ModelPromptAssignments>(
        `/api/v1/tenants/${tenantId}/prompts/models/${modelId}/assignments`,
      ),
    setModelPromptAssignment: (tenantId, modelId, workflowStageId, command) =>
      request<ModelPromptAssignmentState>(
        `/api/v1/tenants/${tenantId}/prompts/models/${modelId}/assignments/${workflowStageId}`,
        {
          method: "PUT",
          headers: { "content-type": "application/json" },
          body: JSON.stringify(command),
        },
      ),
  };
}

export interface AssignablePromptVersion {
  promptTemplateId: number;
  promptTemplateVersionId: number;
  promptTemplateName: string;
  promptTemplateCode: string;
  versionNumber: number;
  digest: string;
}

export const promptQueryKeys = {
  stages: (tenantId: number) => ["prompt-stages", tenantId] as const,
  templates: (
    tenantId: number,
    filters: PromptTemplateFilters,
    cursor: string | undefined,
  ) => ["prompt-templates", tenantId, filters, cursor] as const,
  template: (tenantId: number, promptTemplateId: number) => (
    ["prompt-template", tenantId, promptTemplateId] as const
  ),
  modelAssignments: (tenantId: number, modelId: number) => (
    ["model-prompt-assignments", tenantId, modelId] as const
  ),
  assignableVersions: (tenantId: number, workflowStageId: number) => (
    ["assignable-prompt-versions", tenantId, workflowStageId] as const
  ),
};

export async function loadAssignableTenantPromptVersions(
  api: PromptsApi,
  tenantId: number,
  workflowStageId: number,
  workflowStageCode: string,
): Promise<AssignablePromptVersion[]> {
  const templateIds: number[] = [];
  const seenCursors = new Set<string>();
  let cursor: string | undefined;

  for (let pageNumber = 0; pageNumber < 5; pageNumber += 1) {
    const page = await api.listPromptTemplates(
      tenantId,
      { stageCode: workflowStageCode },
      200,
      cursor,
    );
    for (const template of page.items) {
      if (
        template.workflow_stage_id === workflowStageId
        && template.prompt_template_ownership_scope === "tenant"
        && template.owner_tenant_id === tenantId
        && template.is_active
      ) {
        templateIds.push(template.prompt_template_id);
      }
    }
    if (!page.next_cursor) break;
    if (seenCursors.has(page.next_cursor)) {
      throw new Error("Prompt Template cursor repeated");
    }
    if (pageNumber === 4) {
      throw new Error("Prompt Template selection exceeds the supported bound");
    }
    seenCursors.add(page.next_cursor);
    cursor = page.next_cursor;
  }

  const versions: AssignablePromptVersion[] = [];
  for (let offset = 0; offset < templateIds.length; offset += 8) {
    const batch = templateIds.slice(offset, offset + 8);
    const details = await Promise.all(
      batch.map((promptTemplateId) => api.readPromptTemplate(tenantId, promptTemplateId)),
    );
    for (const detail of details) {
      for (const version of detail.versions) {
        if (
          version.workflow_stage_id === workflowStageId
          && version.prompt_template_version_status === "published"
        ) {
          versions.push({
            promptTemplateId: detail.template.prompt_template_id,
            promptTemplateVersionId: version.prompt_template_version_id,
            promptTemplateName: detail.template.prompt_template_name,
            promptTemplateCode: detail.template.prompt_template_code,
            versionNumber: version.prompt_template_version_number,
            digest: version.prompt_template_digest,
          });
        }
      }
    }
  }

  return versions.sort((left, right) => (
    left.promptTemplateName.localeCompare(right.promptTemplateName)
    || right.versionNumber - left.versionNumber
    || left.promptTemplateVersionId - right.promptTemplateVersionId
  ));
}

function promptTemplatesPath(
  tenantId: number,
  filters: PromptTemplateFilters,
  pageSize: number,
  cursor: string | undefined,
): string {
  const query = new URLSearchParams();
  if (filters.workflow) query.set("workflow", filters.workflow);
  if (filters.mode) query.set("mode", filters.mode);
  const stageCode = normalizeNaturalKeyFilter(filters.stageCode);
  if (stageCode) query.set("stage_code", stageCode);
  if (filters.status) query.set("status", filters.status);
  query.set("page_size", String(pageSize));
  if (cursor) query.set("cursor", cursor);
  return `/api/v1/tenants/${tenantId}/prompts/templates?${query}`;
}

function normalizeNaturalKeyFilter(value: string | undefined): string {
  return value?.replace(/^ +| +$/g, "").toLowerCase() ?? "";
}
