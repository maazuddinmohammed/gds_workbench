import type { HttpRequest } from "../../core/http";

export type ModelWorkflow =
  | "profiling"
  | "analysis"
  | "conceptual"
  | "logical"
  | "dimensional"
  | "mapping"
  | "code_generation";

export type WorkflowExecutionMode =
  | "one_shot"
  | "tool_assisted"
  | "detailed_coverage";

export type WorkflowRunState =
  | "queued"
  | "running"
  | "completed"
  | "completed_with_repair"
  | "failed";

export interface AgentRunSelection {
  sdk_code: string;
  provider_code: string;
  model_code: string;
  reasoning_effort_code: string;
  max_turns: number;
  validation_retry_count: number;
}

export interface AgentCapabilities {
  schema_version: "3.0";
  sdks: { code: string; name: string; provider_codes: string[] }[];
  providers: { code: string; name: string }[];
  models: AgentModelCapability[];
  reasoning_efforts: { code: string; name: string }[];
  max_turns: { minimum: number; default: number; maximum: number };
  validation_retries: { minimum: number; default: number; maximum: number };
}

export interface AgentModelExecutionProfile {
  sdk_code: string;
  execution_mode: WorkflowExecutionMode;
  reasoning_effort_codes: string[];
}

export interface AgentModelCapability {
  code: string;
  name: string;
  provider_code: string;
  deployment_name: string;
  execution_profiles: AgentModelExecutionProfile[];
}

export const WORKFLOW_EXECUTION_MODES: readonly WorkflowExecutionMode[] = [
  "one_shot",
  "tool_assisted",
  "detailed_coverage",
];

export const WORKFLOW_EXECUTION_MODE_NAMES: Record<WorkflowExecutionMode, string> = {
  one_shot: "One shot",
  tool_assisted: "Tool assisted",
  detailed_coverage: "Detailed coverage",
};

export function reasoningEffortDisplayName(
  effort: AgentCapabilities["reasoning_efforts"][number],
): string {
  if (effort.code === "default") return "Provider default (omit setting)";
  if (effort.code === "none") return "None (explicitly disable reasoning)";
  return effort.name;
}

export interface CreateWorkflowRunCommand {
  expected_model_revision: number;
  model_workflow: ModelWorkflow;
  workflow_execution_mode: WorkflowExecutionMode | null;
  selected_object_ids: number[];
  requested_batch_id: string | null;
  agent: AgentRunSelection | null;
  prompt_overrides: Record<string, number>;
  modeled_entity_type?: "logical_entity" | "dimensional_entity" | null;
  mapping_operation?: "build" | "extend" | null;
  mapping_coverage_mode?: "selected_targets" | null;
  mapping_artifact_type?: "sql_file" | "python_file" | "python_notebook" | null;
  mapping_source_system_id?: number | null;
  mapping_object_output_template_id?: number | null;
  mapping_attribute_output_template_id?: number | null;
  code_generation_coverage_mode?: "selected_targets" | "all_eligible_targets" | null;
  sql_generation_guide_version_id?: number | null;
}

export type WorkflowRunFilterState = WorkflowRunState | "";

export interface WorkflowRunRecord {
  workflow_run_id: number;
  model_workflow: ModelWorkflow;
  workflow_execution_mode: WorkflowExecutionMode | null;
  modeled_entity_type: "logical_entity" | "dimensional_entity" | null;
  selected_scope_count: number;
  requested_batch_id: string | null;
  workflow_run_state: WorkflowRunState;
  actor_display_name: string;
  created_at: string;
  started_at: string | null;
  completed_at: string | null;
}

export interface WorkflowRunCollection {
  items: WorkflowRunRecord[];
  next_cursor: string | null;
}

export interface WorkflowRunDetail extends WorkflowRunRecord {
  correlation_id: string;
  agent_sdk_code: string | null;
  agent_provider_code: string | null;
  agent_model_code: string | null;
  reasoning_effort_code: string | null;
  max_turns: number | null;
  validation_retry_count: number | null;
  failure_code: string | null;
  failure_message: string | null;
  model_change_set_id: string | null;
  model_change_set_status:
    | "active"
    | "validated"
    | "applied"
    | "expired"
    | "discarded"
    | "superseded"
    | null;
  draft_revision: number | null;
  candidate_digest: string | null;
  validated_at: string | null;
}

export interface WorkflowRunEvent {
  sequence: number;
  attempt: number;
  stage: string;
  status: "started" | "running" | "completed" | "warning" | "failed" | "blocked";
  message: string;
  current: number | null;
  total: number | null;
  percent: string | number | null;
  finding_count: number;
  created_at: string;
}

export interface WorkflowRunEventCollection {
  items: WorkflowRunEvent[];
  next_after_sequence: number;
}

export interface WorkflowRunCommandResult {
  created: boolean;
  workflow_run_id: number;
  workflow_run_state: WorkflowRunState;
  correlation_id: string;
  prompt_snapshot_count: number;
  created_at: string;
}

export interface WorkflowRunStart {
  changed: boolean;
  workflow_run_id: number;
  workflow_run_state: WorkflowRunState;
  model_revision: number;
}

export interface ApplyWorkflowDraftResult {
  schema_version: "1.0";
  model_id: number;
  workflow_run_id: number;
  model_change_set_id: string;
  replayed: boolean;
  draft_revision: number;
  candidate_digest: string;
  action_count: number;
  model_revision: number;
  applied_at: string;
}

export interface WorkflowDraftActionReview {
  dataset: string;
  insert_count: number;
  update_count: number;
  deactivate_count: number;
  reactivate_count: number;
  no_change_count: number;
}

export interface WorkflowDraftReview {
  schema_version: "1.0";
  model_id: number;
  model_change_set_id: string;
  status: "active" | "validated" | "applied" | "expired" | "discarded" | "superseded";
  draft_revision: number;
  candidate_digest: string | null;
  validation_outcome: {
    schema_version: "1.0";
    valid: boolean;
    phase: string;
    staged_record_count: number;
    error_count: number;
    action_review: WorkflowDraftActionReview[];
  } | null;
  dataset_counts: { dataset: string; record_count: number }[];
  dataset: null;
  records: null;
  created_at: string;
  last_activity_at: string;
  expires_at: string;
  validated_at: string | null;
  applied_at: string | null;
  terminal_at: string | null;
}

export interface WorkflowsApi {
  readAgentCapabilities: () => Promise<AgentCapabilities>;
  listWorkflowRuns: (
    tenantId: number,
    modelId: number,
    workflow: ModelWorkflow,
    state?: WorkflowRunFilterState,
    pageSize?: number,
    cursor?: string,
  ) => Promise<WorkflowRunCollection>;
  readWorkflowRun: (
    tenantId: number,
    modelId: number,
    workflowRunId: number,
  ) => Promise<WorkflowRunDetail>;
  listWorkflowRunEvents: (
    tenantId: number,
    modelId: number,
    workflowRunId: number,
    afterSequence?: number,
  ) => Promise<WorkflowRunEventCollection>;
  createWorkflowRun: (
    tenantId: number,
    modelId: number,
    command: CreateWorkflowRunCommand,
    idempotencyKey: string,
  ) => Promise<WorkflowRunCommandResult>;
  applyWorkflowDraft: (
    tenantId: number,
    modelId: number,
    workflowRunId: number,
    expectedModelRevision: number,
    expectedDraftRevision: number,
    expectedCandidateDigest: string,
    idempotencyKey: string,
  ) => Promise<ApplyWorkflowDraftResult>;
  readWorkflowDraftReview: (
    tenantId: number,
    modelId: number,
    modelChangeSetId: string,
  ) => Promise<WorkflowDraftReview>;
  executeProfilingRun: (
    tenantId: number,
    modelId: number,
    workflowRunId: number,
    expectedModelRevision: number,
  ) => Promise<WorkflowRunStart>;
  executeAnalysisInferenceRun: (
    tenantId: number,
    modelId: number,
    workflowRunId: number,
    executionMode: WorkflowExecutionMode,
    expectedModelRevision: number,
  ) => Promise<WorkflowRunStart>;
  executeAnalysisValidationRun: (
    tenantId: number,
    modelId: number,
    workflowRunId: number,
    expectedModelRevision: number,
  ) => Promise<WorkflowRunStart>;
  executeConceptualRun: (
    tenantId: number,
    modelId: number,
    workflowRunId: number,
    executionMode: WorkflowExecutionMode,
    expectedModelRevision: number,
  ) => Promise<WorkflowRunStart>;
  executeLogicalRun: (
    tenantId: number,
    modelId: number,
    workflowRunId: number,
    executionMode: WorkflowExecutionMode,
    expectedModelRevision: number,
  ) => Promise<WorkflowRunStart>;
  executeDimensionalRun: (
    tenantId: number,
    modelId: number,
    workflowRunId: number,
    executionMode: WorkflowExecutionMode,
    expectedModelRevision: number,
  ) => Promise<WorkflowRunStart>;
  executeMappingRun: (
    tenantId: number,
    modelId: number,
    workflowRunId: number,
    executionMode: WorkflowExecutionMode,
    expectedModelRevision: number,
  ) => Promise<WorkflowRunStart>;
  executeCodeGenerationRun: (
    tenantId: number,
    modelId: number,
    workflowRunId: number,
    expectedModelRevision: number,
  ) => Promise<WorkflowRunStart>;
}

export function createWorkflowsApi(request: HttpRequest): WorkflowsApi {
  return {
    readAgentCapabilities: () =>
      request<AgentCapabilities>("/api/v1/config/agent-capabilities"),
    listWorkflowRuns: (
      tenantId,
      modelId,
      workflow,
      state = "",
      pageSize = 200,
      cursor,
    ) => {
      const query = new URLSearchParams({ workflow, page_size: String(pageSize) });
      if (state) query.set("state", state);
      if (cursor) query.set("cursor", cursor);
      return request<WorkflowRunCollection>(
        `/api/v1/tenants/${tenantId}/models/${modelId}/runs?${query}`,
      );
    },
    readWorkflowRun: (tenantId, modelId, workflowRunId) =>
      request<WorkflowRunDetail>(
        `/api/v1/tenants/${tenantId}/models/${modelId}/runs/${workflowRunId}`,
      ),
    listWorkflowRunEvents: (tenantId, modelId, workflowRunId, afterSequence = 0) =>
      request<WorkflowRunEventCollection>(
        `/api/v1/tenants/${tenantId}/models/${modelId}/runs/${workflowRunId}/events`
        + `?after_sequence=${afterSequence}&page_size=200`,
      ),
    createWorkflowRun: (tenantId, modelId, command, idempotencyKey) =>
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
    applyWorkflowDraft: (
      tenantId,
      modelId,
      workflowRunId,
      expectedModelRevision,
      expectedDraftRevision,
      expectedCandidateDigest,
      idempotencyKey,
    ) => request<ApplyWorkflowDraftResult>(
      `/api/v1/tenants/${tenantId}/models/${modelId}/runs/${workflowRunId}/draft/apply`,
      {
        method: "POST",
        headers: {
          "content-type": "application/json",
          "Idempotency-Key": idempotencyKey,
        },
        body: JSON.stringify({
          expected_model_revision: expectedModelRevision,
          expected_draft_revision: expectedDraftRevision,
          expected_candidate_digest: expectedCandidateDigest,
        }),
      },
    ),
    readWorkflowDraftReview: (tenantId, modelId, modelChangeSetId) =>
      request<WorkflowDraftReview>(
        `/api/v1/tenants/${tenantId}/models/${modelId}/change-sets/${modelChangeSetId}`,
      ),
    executeProfilingRun: (
      tenantId,
      modelId,
      workflowRunId,
      expectedModelRevision,
    ) => request<WorkflowRunStart>(
      `/api/v1/tenants/${tenantId}/models/${modelId}/profiling/runs/${workflowRunId}/execute`,
      {
        method: "POST",
        headers: { "content-type": "application/json" },
        body: JSON.stringify({ expected_model_revision: expectedModelRevision }),
      },
    ),
    executeAnalysisInferenceRun: (
      tenantId,
      modelId,
      workflowRunId,
      executionMode,
      expectedModelRevision,
    ) => request<WorkflowRunStart>(
      `/api/v1/tenants/${tenantId}/models/${modelId}/analysis/inference-runs/${workflowRunId}/execute`,
      {
        method: "POST",
        headers: { "content-type": "application/json" },
        body: JSON.stringify({
          execution_mode: executionMode,
          expected_model_revision: expectedModelRevision,
        }),
      },
    ),
    executeAnalysisValidationRun: (
      tenantId,
      modelId,
      workflowRunId,
      expectedModelRevision,
    ) => request<WorkflowRunStart>(
      `/api/v1/tenants/${tenantId}/models/${modelId}/analysis/validation-runs/${workflowRunId}/execute`,
      {
        method: "POST",
        headers: { "content-type": "application/json" },
        body: JSON.stringify({ expected_model_revision: expectedModelRevision }),
      },
    ),
    executeConceptualRun: (
      tenantId,
      modelId,
      workflowRunId,
      executionMode,
      expectedModelRevision,
    ) => request<WorkflowRunStart>(
      `/api/v1/tenants/${tenantId}/models/${modelId}/conceptual/runs/${workflowRunId}/execute`,
      {
        method: "POST",
        headers: { "content-type": "application/json" },
        body: JSON.stringify({
          execution_mode: executionMode,
          expected_model_revision: expectedModelRevision,
        }),
      },
    ),
    executeLogicalRun: (
      tenantId,
      modelId,
      workflowRunId,
      executionMode,
      expectedModelRevision,
    ) => request<WorkflowRunStart>(
      `/api/v1/tenants/${tenantId}/models/${modelId}/logical/runs/${workflowRunId}/execute`,
      {
        method: "POST",
        headers: { "content-type": "application/json" },
        body: JSON.stringify({
          execution_mode: executionMode,
          expected_model_revision: expectedModelRevision,
        }),
      },
    ),
    executeDimensionalRun: (
      tenantId,
      modelId,
      workflowRunId,
      executionMode,
      expectedModelRevision,
    ) => request<WorkflowRunStart>(
      `/api/v1/tenants/${tenantId}/models/${modelId}/dimensional/runs/${workflowRunId}/execute`,
      {
        method: "POST",
        headers: { "content-type": "application/json" },
        body: JSON.stringify({
          execution_mode: executionMode,
          expected_model_revision: expectedModelRevision,
        }),
      },
    ),
    executeMappingRun: (
      tenantId,
      modelId,
      workflowRunId,
      executionMode,
      expectedModelRevision,
    ) => request<WorkflowRunStart>(
      `/api/v1/tenants/${tenantId}/models/${modelId}/mapping/runs/${workflowRunId}/execute`,
      {
        method: "POST",
        headers: { "content-type": "application/json" },
        body: JSON.stringify({
          execution_mode: executionMode,
          expected_model_revision: expectedModelRevision,
        }),
      },
    ),
    executeCodeGenerationRun: (
      tenantId,
      modelId,
      workflowRunId,
      expectedModelRevision,
    ) => request<WorkflowRunStart>(
      `/api/v1/tenants/${tenantId}/models/${modelId}/code-generation/runs/${workflowRunId}/execute`,
      {
        method: "POST",
        headers: { "content-type": "application/json" },
        body: JSON.stringify({ expected_model_revision: expectedModelRevision }),
      },
    ),
  };
}

interface WorkflowScopeObject {
  object_id: number;
  system_id: number;
  system_code: string;
  source_tenant_code: string;
  object_name: string;
  is_dimensional_source_eligible: boolean;
}

interface WorkflowScopePage<TScope extends WorkflowScopeObject> {
  model_revision: number;
  items: TScope[];
  next_cursor: string | null;
}

interface WorkflowScopeReader<TScope extends WorkflowScopeObject = WorkflowScopeObject> {
  listModelScope: (
    tenantId: number,
    modelId: number,
    filters: { zone: "bronze" | "silver" },
    pageSize: number,
    cursor?: string,
  ) => Promise<WorkflowScopePage<TScope>>;
}

export type WorkflowCreationApi = Pick<
  WorkflowsApi,
  "createWorkflowRun" | "readAgentCapabilities"
> & WorkflowScopeReader;

export type WorkflowRunMonitorApi = Pick<
  WorkflowsApi,
  | "applyWorkflowDraft"
  | "listWorkflowRunEvents"
  | "listWorkflowRuns"
  | "readWorkflowDraftReview"
  | "readWorkflowRun"
>;

export const workflowRunQueryKeys = {
  recent: (tenantId: number, modelId: number, workflow: ModelWorkflow) => (
    ["workflow-runs", tenantId, modelId, workflow] as const
  ),
  detail: (tenantId: number, modelId: number, workflowRunId: number) => (
    ["workflow-run", tenantId, modelId, workflowRunId] as const
  ),
  events: (tenantId: number, modelId: number, workflowRunId: number) => (
    ["workflow-run-events", tenantId, modelId, workflowRunId] as const
  ),
  draftReview: (tenantId: number, modelId: number, modelChangeSetId: string) => (
    ["workflow-draft-review", tenantId, modelId, modelChangeSetId] as const
  ),
};

export const workflowCreationQueryKeys = {
  capabilities: ["agent-capabilities"] as const,
  bronzeScope: (tenantId: number, modelId: number) => (
    ["workflow-run-bronze-scope", tenantId, modelId] as const
  ),
  dimensionalScope: (tenantId: number, modelId: number) => (
    ["workflow-run-dimensional-scope", tenantId, modelId] as const
  ),
};

export async function loadAllBronzeScope<TScope extends WorkflowScopeObject>(
  api: WorkflowScopeReader<TScope>,
  tenantId: number,
  modelId: number,
): Promise<{ modelRevision: number; items: TScope[] }> {
  const items: TScope[] = [];
  const seenCursors = new Set<string>();
  let cursor: string | undefined;
  let modelRevision: number | null = null;

  for (let page = 0; page < 250; page += 1) {
    const response = await api.listModelScope(
      tenantId,
      modelId,
      { zone: "bronze" },
      200,
      cursor,
    );
    if (modelRevision !== null && modelRevision !== response.model_revision) {
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
  throw new Error("Active Bronze Scope exceeds the supported bounded selection");
}

export async function loadAllDimensionalScope<TScope extends WorkflowScopeObject>(
  api: WorkflowScopeReader<TScope>,
  tenantId: number,
  modelId: number,
): Promise<{ modelRevision: number; items: TScope[] }> {
  const items: TScope[] = [];
  const seenCursors = new Set<string>();
  let cursor: string | undefined;
  let modelRevision: number | null = null;

  for (let page = 0; page < 250; page += 1) {
    const response = await api.listModelScope(
      tenantId,
      modelId,
      { zone: "silver" },
      200,
      cursor,
    );
    if (modelRevision !== null && modelRevision !== response.model_revision) {
      throw new Error("Model Scope revision changed while loading");
    }
    modelRevision = response.model_revision;
    items.push(...response.items.filter((item) => item.is_dimensional_source_eligible));
    if (!response.next_cursor) return { modelRevision, items };
    if (seenCursors.has(response.next_cursor)) {
      throw new Error("Model Scope cursor repeated");
    }
    seenCursors.add(response.next_cursor);
    cursor = response.next_cursor;
  }
  throw new Error("Active Silver Scope exceeds the supported bounded selection");
}

export function resolveDefaultAgent(
  capabilities: AgentCapabilities,
  effectiveExecutionMode: WorkflowExecutionMode,
  defaults: {
    sdkCode: string | null;
    providerCode: string | null;
    modelCode: string | null;
    reasoningEffortCode: string | null;
    maxTurns: number | null;
    validationRetryCount: number | null;
  },
): CreateWorkflowRunCommand["agent"] {
  for (const sdk of preferCode(capabilities.sdks, defaults.sdkCode)) {
    const providers = preferCode(capabilities.providers, defaults.providerCode)
      .filter((provider) => sdk.provider_codes.includes(provider.code));
    for (const provider of providers) {
      const models = preferCode(capabilities.models, defaults.modelCode)
        .filter((model) => model.provider_code === provider.code);
      for (const model of models) {
        const profile = findAgentExecutionProfile(
          model,
          sdk.code,
          effectiveExecutionMode,
        );
        if (!profile) continue;
        const reasoningEffortCode = profile.reasoning_effort_codes.includes(
          defaults.reasoningEffortCode ?? "",
        )
          ? defaults.reasoningEffortCode
          : profile.reasoning_effort_codes[0];
        if (!reasoningEffortCode) continue;
        return {
          sdk_code: sdk.code,
          provider_code: provider.code,
          model_code: model.code,
          reasoning_effort_code: reasoningEffortCode,
          max_turns: defaults.maxTurns ?? capabilities.max_turns.default,
          validation_retry_count: defaults.validationRetryCount
            ?? capabilities.validation_retries.default,
        };
      }
    }
  }
  return null;
}

export function listCompatibleExecutionModes(
  capabilities: AgentCapabilities,
  sdkCode: string,
  providerCode: string,
): WorkflowExecutionMode[] {
  const sdk = capabilities.sdks.find((item) => item.code === sdkCode);
  if (!sdk?.provider_codes.includes(providerCode)) return [];
  const available = new Set(capabilities.models
    .filter((model) => model.provider_code === providerCode)
    .flatMap((model) => model.execution_profiles
      .filter((profile) => profile.sdk_code === sdkCode)
      .map((profile) => profile.execution_mode)));
  return WORKFLOW_EXECUTION_MODES.filter((mode) => available.has(mode));
}

export function resolveAgentProfileSelection(
  capabilities: AgentCapabilities,
  preferredExecutionMode: WorkflowExecutionMode,
  selection: {
    sdkCode: string | null;
    providerCode: string | null;
    modelCode: string | null;
    reasoningEffortCode: string | null;
  },
): {
  executionMode: WorkflowExecutionMode;
  sdkCode: string;
  providerCode: string;
  modelCode: string;
  reasoningEffortCode: string;
} | null {
  for (const sdk of preferCode(capabilities.sdks, selection.sdkCode)) {
    const providers = preferCode(capabilities.providers, selection.providerCode)
      .filter((provider) => (
        sdk.provider_codes.includes(provider.code)
        && capabilities.models.some((model) => (
          model.provider_code === provider.code
          && model.execution_profiles.some((profile) => profile.sdk_code === sdk.code)
        ))
      ));
    for (const provider of providers) {
      const compatibleModes = listCompatibleExecutionModes(
        capabilities,
        sdk.code,
        provider.code,
      );
      const modes = preferExecutionMode(compatibleModes, preferredExecutionMode);
      for (const executionMode of modes) {
        const models = preferCode(capabilities.models, selection.modelCode)
          .filter((model) => (
            model.provider_code === provider.code
            && findAgentExecutionProfile(model, sdk.code, executionMode) !== undefined
          ));
        for (const model of models) {
          const profile = findAgentExecutionProfile(model, sdk.code, executionMode);
          const reasoningEfforts = profile?.reasoning_effort_codes.filter((code) => (
            capabilities.reasoning_efforts.some((effort) => effort.code === code)
          )) ?? [];
          const reasoningEffortCode = reasoningEfforts.includes(
            selection.reasoningEffortCode ?? "",
          )
            ? selection.reasoningEffortCode
            : reasoningEfforts[0];
          if (!reasoningEffortCode) continue;
          return {
            executionMode,
            sdkCode: sdk.code,
            providerCode: provider.code,
            modelCode: model.code,
            reasoningEffortCode,
          };
        }
      }
    }
  }
  return null;
}

export function findAgentExecutionProfile(
  model: AgentModelCapability,
  sdkCode: string,
  executionMode: WorkflowExecutionMode,
): AgentModelExecutionProfile | undefined {
  return model.execution_profiles.find((profile) => (
    profile.sdk_code === sdkCode && profile.execution_mode === executionMode
  ));
}

function preferCode<T extends { code: string }>(items: T[], code: string | null): T[] {
  const preferred = items.find((item) => item.code === code);
  return preferred
    ? [preferred, ...items.filter((item) => item.code !== preferred.code)]
    : items;
}

function preferExecutionMode(
  modes: WorkflowExecutionMode[],
  preferred: WorkflowExecutionMode,
): WorkflowExecutionMode[] {
  if (modes.includes(preferred)) {
    return [preferred, ...modes.filter((mode) => mode !== preferred)];
  }
  if (modes.includes("tool_assisted")) {
    return ["tool_assisted", ...modes.filter((mode) => mode !== "tool_assisted")];
  }
  return modes;
}
