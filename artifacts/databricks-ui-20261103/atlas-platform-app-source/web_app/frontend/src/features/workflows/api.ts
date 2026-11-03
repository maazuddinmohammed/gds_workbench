import type { HttpRequest } from "../../core/http";
import type { JsonObject } from "../../shared/contracts";

export type ProjectWorkflow =
  | "profiling"
  | "metadata_enrichment"
  | "analysis"
  | "subject_area"
  | "logical"
  | "dimensional"
  | "mapping"
  | "code_generation"
  | "validation";

export type WorkflowExecutionMode =
  | "one_shot"
  | "tool_assisted";

/**
 * Logical and Dimensional runs build chosen Subject Areas or optimize the whole model;
 * per_table Analysis runs make one one-shot call per selected table.
 */
export type WorkflowOperation = "build" | "optimize" | "per_table";

export type WorkflowRunState =
  | "queued"
  | "running"
  | "completed"
  | "completed_with_repair"
  | "failed"
  | "cancelled";

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
];

export const WORKFLOW_EXECUTION_MODE_NAMES: Record<WorkflowExecutionMode, string> = {
  one_shot: "One shot",
  tool_assisted: "Tool assisted",
};

export function reasoningEffortDisplayName(
  effort: AgentCapabilities["reasoning_efforts"][number],
): string {
  if (effort.code === "default") return "Model default";
  if (effort.code === "none") return "None";
  return effort.name;
}

export interface CreateWorkflowRunCommand {
  expected_project_revision: number;
  project_workflow: ProjectWorkflow;
  workflow_execution_mode: WorkflowExecutionMode | null;
  /** Logical and Dimensional, and per-table Analysis. */
  workflow_operation?: WorkflowOperation;
  /** Build only: the Subject Areas to build, in build order. */
  subject_area_ids?: number[];
  selected_object_ids: number[];
  selected_entity_ids?: number[];
  description_targets?: { object_id: number; attribute_id: number | null; expected_revision: string }[];
  selected_system_codes?: string[];
  requested_batch_id: string | null;
  agent: AgentRunSelection | null;
  prompt_overrides: Record<string, number>;
  modeled_entity_type?: "logical_entity" | "dimensional_entity" | null;
  mapping_operation?: "build" | "extend" | "generate" | null;
  mapping_targets?: { modeled_entity_id: number; source_system_id: number; selected_attribute_ids: number[] }[];
  mapping_coverage_mode?: "selected_targets" | null;
  mapping_source_system_id?: number | null;
  mapping_object_output_template_id?: number | null;
  mapping_attribute_output_template_id?: number | null;
  code_generation_file_layout?: "combined" | "per_system" | null;
  code_generation_coverage_mode?: "selected_targets" | "all_eligible_targets" | null;
}

export type WorkflowRunFilterState = WorkflowRunState | "";

export interface MappingRunOutcome {
  partial_pair_count?: number;
  empty_pair_count?: number;
  completed_pair_count: number;
  preserved_pair_count: number;
  no_source_pair_count: number;
  failed_pair_count: number;
}

export interface MappingRunFailure {
  source_system_id: number;
  system_code: string;
  modeled_entity_id: number;
  entity_schema_name: string;
  entity_name: string;
  message: string;
}

export interface WorkflowRunRecord {
  workflow_run_id: number;
  project_workflow: ProjectWorkflow;
  workflow_execution_mode: WorkflowExecutionMode | null;
  /** Set for Logical and Dimensional runs and per-table Analysis; null otherwise. */
  workflow_operation: WorkflowOperation | null;
  modeled_entity_type: "logical_entity" | "dimensional_entity" | null;
  selected_scope_count: number;
  requested_batch_id: string | null;
  workflow_run_state: WorkflowRunState;
  actor_display_name: string;
  created_at: string;
  started_at: string | null;
  completed_at: string | null;
  mapping_outcome?: MappingRunOutcome | null;
}

export interface WorkflowRunCollection {
  items: WorkflowRunRecord[];
  next_cursor: string | null;
}

export interface WorkflowCostEstimate {
  status: "unavailable" | "unpriced" | "partial" | "estimated";
  currency: "USD";
  amount: string | null;
  priced_request_count: number;
  unpriced_request_count: number;
  pricing_bases: string[];
  unpriced_reasons: Record<
    | "pricing_not_configured"
    | "outside_pricing_window"
    | "context_limit_exceeded"
    | "missing_usage"
    | "unsupported_token_types",
    number
  >;
}

export interface WorkflowTokenUsage {
  cost_estimate: WorkflowCostEstimate;
  status: "unavailable" | "recording" | "complete" | "partial";
  request_count: number;
  reported_request_count: number;
  pending_request_count: number;
  missing_usage_request_count: number;
  input_tokens: number | null;
  output_tokens: number | null;
  total_tokens: number | null;
  cached_input_tokens: number | null;
  cache_write_input_tokens: number | null;
  reasoning_output_tokens: number | null;
  history_incomplete: boolean;
}

export interface WorkflowRunDetail extends WorkflowRunRecord {
  mapping_failures?: MappingRunFailure[];
  mapping_failures_truncated?: boolean;
  token_usage: WorkflowTokenUsage;
  correlation_id: string;
  agent_sdk_code: string | null;
  agent_provider_code: string | null;
  agent_model_code: string | null;
  reasoning_effort_code: string | null;
  max_turns: number | null;
  validation_retry_count: number | null;
  failure_code: string | null;
  failure_message: string | null;
  project_change_set_id: string | null;
  project_change_set_status:
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
  execution_status?: "waiting_for_worker" | "executing" | null;
  model_request_started_at?: string | null;
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
  project_revision: number;
}

export interface ApplyWorkflowDraftResult {
  schema_version: "1.0";
  project_id: number;
  workflow_run_id: number;
  project_change_set_id: string;
  replayed: boolean;
  draft_revision: number;
  candidate_digest: string;
  action_count: number;
  project_revision: number;
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
  project_id: number;
  project_change_set_id: string;
  status: "active" | "validated" | "applied" | "expired" | "discarded" | "superseded";
  draft_revision: number;
  candidate_digest: string | null;
  validation_outcome: {
    schema_version: "1.0";
    valid: boolean;
    phase: string;
    staged_record_count: number;
    error_count: number;
    error_groups?: { dataset: string; code: string; count: number }[];
    errors?: {
      code: string;
      dataset: string;
      record_number: number | null;
      fields: string[];
      message: string;
    }[];
    errors_truncated?: boolean;
    action_review: WorkflowDraftActionReview[];
  } | null;
  dataset_counts: { dataset: string; record_count: number }[];
  dataset: string | null;
  records: JsonObject[] | null;
  created_at: string;
  last_activity_at: string;
  expires_at: string;
  validated_at: string | null;
  applied_at: string | null;
  terminal_at: string | null;
}

export interface WorkflowRunCancellationResult {
  changed: boolean;
  workflow_run_id: number;
  workflow_run_state: "cancelled";
  completed_at: string;
}

export interface WorkflowsApi {
  cancelWorkflowRun: (
    tenantId: number, projectId: number, workflowRunId: number,
  ) => Promise<WorkflowRunCancellationResult>;
  readAgentCapabilities: () => Promise<AgentCapabilities>;
  listWorkflowRuns: (
    tenantId: number,
    projectId: number,
    workflow: ProjectWorkflow,
    state?: WorkflowRunFilterState,
    pageSize?: number,
    cursor?: string,
  ) => Promise<WorkflowRunCollection>;
  readWorkflowRun: (
    tenantId: number,
    projectId: number,
    workflowRunId: number,
  ) => Promise<WorkflowRunDetail>;
  listWorkflowRunEvents: (
    tenantId: number,
    projectId: number,
    workflowRunId: number,
    afterSequence?: number,
  ) => Promise<WorkflowRunEventCollection>;
  createWorkflowRun: (
    tenantId: number,
    projectId: number,
    command: CreateWorkflowRunCommand,
    idempotencyKey: string,
  ) => Promise<WorkflowRunCommandResult>;
  applyWorkflowDraft: (
    tenantId: number,
    projectId: number,
    workflowRunId: number,
    expectedProjectRevision: number,
    expectedDraftRevision: number,
    expectedCandidateDigest: string,
    idempotencyKey: string,
  ) => Promise<ApplyWorkflowDraftResult>;
  readWorkflowDraftReview: (
    tenantId: number,
    projectId: number,
    projectChangeSetId: string,
    dataset?: string,
  ) => Promise<WorkflowDraftReview>;
  executeProfilingRun: (
    tenantId: number,
    projectId: number,
    workflowRunId: number,
    expectedProjectRevision: number,
  ) => Promise<WorkflowRunStart>;
  executeAnalysisInferenceRun: (
    tenantId: number,
    projectId: number,
    workflowRunId: number,
    executionMode: WorkflowExecutionMode,
    expectedProjectRevision: number,
  ) => Promise<WorkflowRunStart>;
  executeAnalysisValidationRun: (
    tenantId: number,
    projectId: number,
    workflowRunId: number,
    expectedProjectRevision: number,
  ) => Promise<WorkflowRunStart>;
  executeSubjectAreaRun: (
    tenantId: number,
    projectId: number,
    workflowRunId: number,
    executionMode: WorkflowExecutionMode,
    expectedProjectRevision: number,
  ) => Promise<WorkflowRunStart>;
  executeLogicalRun: (
    tenantId: number,
    projectId: number,
    workflowRunId: number,
    executionMode: WorkflowExecutionMode,
    expectedProjectRevision: number,
  ) => Promise<WorkflowRunStart>;
  executeDimensionalRun: (
    tenantId: number,
    projectId: number,
    workflowRunId: number,
    executionMode: WorkflowExecutionMode,
    expectedProjectRevision: number,
  ) => Promise<WorkflowRunStart>;
  executeMappingRun: (
    tenantId: number,
    projectId: number,
    workflowRunId: number,
    executionMode: WorkflowExecutionMode,
    expectedProjectRevision: number,
  ) => Promise<WorkflowRunStart>;
  executeCodeGenerationRun: (
    tenantId: number,
    projectId: number,
    workflowRunId: number,
    expectedProjectRevision: number,
  ) => Promise<WorkflowRunStart>;
  executeValidationRun: (
    tenantId: number,
    projectId: number,
    workflowRunId: number,
    expectedProjectRevision: number,
  ) => Promise<WorkflowRunStart>;
}

export function createWorkflowsApi(request: HttpRequest): WorkflowsApi {
  return {
    cancelWorkflowRun: (tenantId, projectId, workflowRunId) =>
      request<WorkflowRunCancellationResult>(
        `/api/v1/tenants/${tenantId}/projects/${projectId}/runs/${workflowRunId}/cancel`,
        { method: "POST" },
      ),
    readAgentCapabilities: () =>
      request<AgentCapabilities>("/api/v1/config/agent-capabilities"),
    listWorkflowRuns: (
      tenantId,
      projectId,
      workflow,
      state = "",
      pageSize = 200,
      cursor,
    ) => {
      const query = new URLSearchParams({ workflow, page_size: String(pageSize) });
      if (state) query.set("state", state);
      if (cursor) query.set("cursor", cursor);
      return request<WorkflowRunCollection>(
        `/api/v1/tenants/${tenantId}/projects/${projectId}/runs?${query}`,
      );
    },
    readWorkflowRun: (tenantId, projectId, workflowRunId) =>
      request<WorkflowRunDetail>(
        `/api/v1/tenants/${tenantId}/projects/${projectId}/runs/${workflowRunId}`,
      ),
    listWorkflowRunEvents: (tenantId, projectId, workflowRunId, afterSequence = 0) =>
      request<WorkflowRunEventCollection>(
        `/api/v1/tenants/${tenantId}/projects/${projectId}/runs/${workflowRunId}/events`
        + `?after_sequence=${afterSequence}&page_size=200`,
      ),
    createWorkflowRun: (tenantId, projectId, command, idempotencyKey) =>
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
    applyWorkflowDraft: (
      tenantId,
      projectId,
      workflowRunId,
      expectedProjectRevision,
      expectedDraftRevision,
      expectedCandidateDigest,
      idempotencyKey,
    ) => request<ApplyWorkflowDraftResult>(
      `/api/v1/tenants/${tenantId}/projects/${projectId}/runs/${workflowRunId}/draft/apply`,
      {
        method: "POST",
        headers: {
          "content-type": "application/json",
          "Idempotency-Key": idempotencyKey,
        },
        body: JSON.stringify({
          expected_project_revision: expectedProjectRevision,
          expected_draft_revision: expectedDraftRevision,
          expected_candidate_digest: expectedCandidateDigest,
        }),
      },
    ),
    readWorkflowDraftReview: (tenantId, projectId, projectChangeSetId, dataset) =>
      request<WorkflowDraftReview>(
        `/api/v1/tenants/${tenantId}/projects/${projectId}/change-sets/${projectChangeSetId}`
        + (dataset ? `?${new URLSearchParams({ dataset })}` : ""),
      ),
    executeProfilingRun: (
      tenantId,
      projectId,
      workflowRunId,
      expectedProjectRevision,
    ) => request<WorkflowRunStart>(
      `/api/v1/tenants/${tenantId}/projects/${projectId}/profiling/runs/${workflowRunId}/execute`,
      {
        method: "POST",
        headers: { "content-type": "application/json" },
        body: JSON.stringify({ expected_project_revision: expectedProjectRevision }),
      },
    ),
    executeAnalysisInferenceRun: (
      tenantId,
      projectId,
      workflowRunId,
      executionMode,
      expectedProjectRevision,
    ) => request<WorkflowRunStart>(
      `/api/v1/tenants/${tenantId}/projects/${projectId}/analysis/inference-runs/${workflowRunId}/execute`,
      {
        method: "POST",
        headers: { "content-type": "application/json" },
        body: JSON.stringify({
          execution_mode: executionMode,
          expected_project_revision: expectedProjectRevision,
        }),
      },
    ),
    executeAnalysisValidationRun: (
      tenantId,
      projectId,
      workflowRunId,
      expectedProjectRevision,
    ) => request<WorkflowRunStart>(
      `/api/v1/tenants/${tenantId}/projects/${projectId}/analysis/validation-runs/${workflowRunId}/execute`,
      {
        method: "POST",
        headers: { "content-type": "application/json" },
        body: JSON.stringify({ expected_project_revision: expectedProjectRevision }),
      },
    ),
    executeSubjectAreaRun: (
      tenantId,
      projectId,
      workflowRunId,
      executionMode,
      expectedProjectRevision,
    ) => request<WorkflowRunStart>(
      `/api/v1/tenants/${tenantId}/projects/${projectId}/subject-areas/runs/${workflowRunId}/execute`,
      {
        method: "POST",
        headers: { "content-type": "application/json" },
        body: JSON.stringify({
          execution_mode: executionMode,
          expected_project_revision: expectedProjectRevision,
        }),
      },
    ),
    executeLogicalRun: (
      tenantId,
      projectId,
      workflowRunId,
      executionMode,
      expectedProjectRevision,
    ) => request<WorkflowRunStart>(
      `/api/v1/tenants/${tenantId}/projects/${projectId}/logical/runs/${workflowRunId}/execute`,
      {
        method: "POST",
        headers: { "content-type": "application/json" },
        body: JSON.stringify({
          execution_mode: executionMode,
          expected_project_revision: expectedProjectRevision,
        }),
      },
    ),
    executeDimensionalRun: (
      tenantId,
      projectId,
      workflowRunId,
      executionMode,
      expectedProjectRevision,
    ) => request<WorkflowRunStart>(
      `/api/v1/tenants/${tenantId}/projects/${projectId}/dimensional/runs/${workflowRunId}/execute`,
      {
        method: "POST",
        headers: { "content-type": "application/json" },
        body: JSON.stringify({
          execution_mode: executionMode,
          expected_project_revision: expectedProjectRevision,
        }),
      },
    ),
    executeMappingRun: (
      tenantId,
      projectId,
      workflowRunId,
      executionMode,
      expectedProjectRevision,
    ) => request<WorkflowRunStart>(
      `/api/v1/tenants/${tenantId}/projects/${projectId}/mapping/runs/${workflowRunId}/execute`,
      {
        method: "POST",
        headers: { "content-type": "application/json" },
        body: JSON.stringify({
          execution_mode: executionMode,
          expected_project_revision: expectedProjectRevision,
        }),
      },
    ),
    executeCodeGenerationRun: (
      tenantId,
      projectId,
      workflowRunId,
      expectedProjectRevision,
    ) => request<WorkflowRunStart>(
      `/api/v1/tenants/${tenantId}/projects/${projectId}/code-generation/runs/${workflowRunId}/execute`,
      {
        method: "POST",
        headers: { "content-type": "application/json" },
        body: JSON.stringify({ expected_project_revision: expectedProjectRevision }),
      },
    ),
    executeValidationRun: (
      tenantId,
      projectId,
      workflowRunId,
      expectedProjectRevision,
    ) => request<WorkflowRunStart>(
      `/api/v1/tenants/${tenantId}/projects/${projectId}/validation/runs/${workflowRunId}/execute`,
      {
        method: "POST",
        headers: { "content-type": "application/json" },
        body: JSON.stringify({ expected_project_revision: expectedProjectRevision }),
      },
    ),
  };
}

export interface WorkflowScopeObject {
  connection_id?: number;
  attribute_count?: number;
  object_schema?: string;
  source_tenant_id?: number;
  is_locked?: boolean;
  review_revision?: string | null;
  object_id: number;
  system_id: number;
  system_code: string;
  source_tenant_code: string;
  object_name: string;
  zone_code?: "source" | "bronze" | "silver";
}

interface WorkflowScopePage<TScope extends WorkflowScopeObject> {
  project_revision: number;
  items: TScope[];
  next_cursor: string | null;
}

interface WorkflowScopeReader<TScope extends WorkflowScopeObject = WorkflowScopeObject> {
  listProjectInputScope: (
    tenantId: number,
    projectId: number,
    filters: { zone?: "bronze" },
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
  | "cancelWorkflowRun"
  | "listWorkflowRunEvents"
  | "listWorkflowRuns"
  | "readWorkflowDraftReview"
  | "readWorkflowRun"
>;

export const workflowRunQueryKeys = {
  recent: (tenantId: number, projectId: number, workflow: ProjectWorkflow) => (
    ["workflow-runs", tenantId, projectId, workflow] as const
  ),
  detail: (tenantId: number, projectId: number, workflowRunId: number) => (
    ["workflow-run", tenantId, projectId, workflowRunId] as const
  ),
  events: (tenantId: number, projectId: number, workflowRunId: number) => (
    ["workflow-run-events", tenantId, projectId, workflowRunId] as const
  ),
  draftReview: (tenantId: number, projectId: number, projectChangeSetId: string) => (
    ["workflow-draft-review", tenantId, projectId, projectChangeSetId] as const
  ),
};

export const workflowCreationQueryKeys = {
  capabilities: ["agent-capabilities"] as const,
  bronzeScope: (tenantId: number, projectId: number) => (
    ["workflow-run-bronze-scope", tenantId, projectId] as const
  ),
  enrichmentScope: (tenantId: number, projectId: number) => (
    ["workflow-run-enrichment-scope", tenantId, projectId] as const
  ),
};

export async function loadWorkflowScope<TScope extends WorkflowScopeObject>(
  api: WorkflowScopeReader<TScope>,
  tenantId: number,
  projectId: number,
  scope: "bronze" | "enrichment",
): Promise<{ projectRevision: number; items: TScope[] }> {
  const items: TScope[] = [];
  const seenCursors = new Set<string>();
  let cursor: string | undefined;
  let projectRevision: number | null = null;

  for (let page = 0; page < 250; page += 1) {
    const response = await api.listProjectInputScope(
      tenantId,
      projectId,
      scope === "enrichment" ? {} : { zone: "bronze" },
      200,
      cursor,
    );
    if (projectRevision !== null && projectRevision !== response.project_revision) {
      throw new Error("Project Input Scope revision changed while loading");
    }
    projectRevision = response.project_revision;
    if (scope === "enrichment"
      && response.items.some((item) => item.zone_code !== "source" && item.zone_code !== "bronze")) {
      throw new Error("Enrichment requires Source and Bronze Project Input Scope");
    }
    items.push(...response.items);
    if (!response.next_cursor) return { projectRevision, items };
    if (seenCursors.has(response.next_cursor)) {
      throw new Error("Project Input Scope cursor repeated");
    }
    seenCursors.add(response.next_cursor);
    cursor = response.next_cursor;
  }
  const zoneName = scope === "enrichment" ? "Source and Bronze" : "Bronze";
  throw new Error(`Active ${zoneName} Scope exceeds the supported bounded selection`);
}

export function resolveDefaultAgent(
  capabilities: AgentCapabilities,
  effectiveExecutionMode: WorkflowExecutionMode,
  defaults: {
    modelCode: string | null;
    reasoningEffortCode: string | null;
    maxTurns: number | null;
    validationRetryCount: number | null;
  },
): CreateWorkflowRunCommand["agent"] {
  const resolved = resolveAgentProfileSelection(
    capabilities, effectiveExecutionMode, defaults, [effectiveExecutionMode],
  );
  if (!resolved) return null;
  const turns = defaults.maxTurns;
  const retries = defaults.validationRetryCount;
  return {
    sdk_code: "openai_agents_sdk",
    provider_code: "microsoft_foundry",
    model_code: resolved.modelCode,
    reasoning_effort_code: resolved.reasoningEffortCode,
    max_turns: turns !== null && Number.isInteger(turns)
      && turns >= capabilities.max_turns.minimum && turns <= capabilities.max_turns.maximum
      ? turns : capabilities.max_turns.default,
    validation_retry_count: retries !== null && Number.isInteger(retries)
      && retries >= capabilities.validation_retries.minimum
      && retries <= capabilities.validation_retries.maximum
      ? retries : capabilities.validation_retries.default,
  };
}

export function listCompatibleExecutionModes(
  capabilities: AgentCapabilities,
): WorkflowExecutionMode[] {
  const sdk = capabilities.sdks.find((item) => item.code === "openai_agents_sdk");
  if (!sdk?.provider_codes.includes("microsoft_foundry")
    || !capabilities.providers.some((item) => item.code === "microsoft_foundry")) return [];
  const available = new Set(capabilities.models
    .filter((model) => model.provider_code === "microsoft_foundry")
    .flatMap((model) => model.execution_profiles
      .filter((profile) => profile.sdk_code === "openai_agents_sdk"
        && profile.reasoning_effort_codes.some((code) =>
          capabilities.reasoning_efforts.some((effort) => effort.code === code)))
      .map((profile) => profile.execution_mode)));
  return WORKFLOW_EXECUTION_MODES.filter((mode) => available.has(mode));
}

export function resolveAgentProfileSelection(
  capabilities: AgentCapabilities,
  preferredExecutionMode: WorkflowExecutionMode,
  selection: {
    modelCode: string | null;
    reasoningEffortCode: string | null;
  },
  allowedExecutionModes: readonly WorkflowExecutionMode[] = WORKFLOW_EXECUTION_MODES,
): {
  executionMode: WorkflowExecutionMode;
  modelCode: string;
  reasoningEffortCode: string;
} | null {
  const modes = preferExecutionMode(
    listCompatibleExecutionModes(capabilities).filter((mode) => allowedExecutionModes.includes(mode)),
    preferredExecutionMode,
  );
  for (const executionMode of modes) {
    for (const model of preferCode(capabilities.models, selection.modelCode)) {
      const profile = findAgentExecutionProfile(model, executionMode);
      const efforts = profile?.reasoning_effort_codes.filter((code) => (
        capabilities.reasoning_efforts.some((effort) => effort.code === code)
      )) ?? [];
      const reasoningEffortCode = efforts.includes(selection.reasoningEffortCode ?? "")
        ? selection.reasoningEffortCode : efforts[0];
      if (!reasoningEffortCode) continue;
      return { executionMode, modelCode: model.code, reasoningEffortCode };
    }
  }
  return null;
}

export function findAgentExecutionProfile(
  model: AgentModelCapability,
  executionMode: WorkflowExecutionMode,
): AgentModelExecutionProfile | undefined {
  if (model.provider_code !== "microsoft_foundry") return undefined;
  return model.execution_profiles.find((profile) => (
    profile.sdk_code === "openai_agents_sdk" && profile.execution_mode === executionMode
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
