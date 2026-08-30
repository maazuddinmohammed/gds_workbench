import { useEffect, useRef, useState } from "react";
import { useForm, useStore } from "@tanstack/react-form";
import { useMutation, useQuery } from "@tanstack/react-query";

import type { ModelDetail } from "../models/api";
import type { CreateWorkflowRunCommand } from "./api";
import {
  findAgentExecutionProfile,
  listCompatibleExecutionModes,
  loadAllBronzeScope,
  loadAllDimensionalScope,
  reasoningEffortDisplayName,
  resolveAgentProfileSelection,
  WORKFLOW_EXECUTION_MODE_NAMES,
  workflowCreationQueryKeys,
  type WorkflowCreationApi,
} from "./api";
import {
  isTenantWorkflowConflict,
  TENANT_WORKFLOW_CONFLICT_MESSAGE,
} from "./presentation";

type AnalysisRunKind = "inference" | "validation";
type AgenticWorkflow = "analysis" | "conceptual" | "logical" | "dimensional";
type WorkflowExecutionMode = NonNullable<CreateWorkflowRunCommand["workflow_execution_mode"]>;
type PendingWorkflowStart =
  | {
    workflowRunId: number;
    runKind: "inference";
    executionMode: WorkflowExecutionMode;
  }
  | {
    workflowRunId: number;
    runKind: "validation";
  };
type WorkflowRunSubmission =
  | { kind: "create"; command: CreateWorkflowRunCommand }
  | ({ kind: "retry" } & PendingWorkflowStart);

export function WorkflowRunDialog({
  api,
  tenantId,
  model,
  kind,
  workflow = "analysis",
  executeCreated,
  executeValidationCreated,
  onClose,
  onCreated,
}: {
  api: WorkflowCreationApi;
  tenantId: number;
  model: ModelDetail;
  kind: AnalysisRunKind;
  workflow?: AgenticWorkflow;
  executeCreated?: (
    workflowRunId: number,
    executionMode: WorkflowExecutionMode,
  ) => Promise<void>;
  executeValidationCreated?: (workflowRunId: number) => Promise<void>;
  onClose: () => void;
  onCreated: (workflowRunId: number) => Promise<void>;
}) {
  const closeButton = useRef<HTMLButtonElement>(null);
  const [pendingStart, setPendingStart] = useState<PendingWorkflowStart | null>(null);
  const isDimensional = workflow === "dimensional";
  const authoringWorkflowName = workflow === "conceptual"
    ? "Conceptual"
    : workflow === "logical"
      ? "Logical"
      : "Dimensional";
  const workflowName = workflow === "analysis" ? "Analysis" : authoringWorkflowName;
  const scopeZoneName = isDimensional ? "Silver" : "Bronze";
  const scopeQuery = useQuery({
    queryKey: isDimensional
      ? workflowCreationQueryKeys.dimensionalScope(tenantId, model.model_id)
      : workflowCreationQueryKeys.bronzeScope(tenantId, model.model_id),
    queryFn: () => isDimensional
      ? loadAllDimensionalScope(api, tenantId, model.model_id)
      : loadAllBronzeScope(api, tenantId, model.model_id),
  });
  const capabilitiesQuery = useQuery({
    queryKey: workflowCreationQueryKeys.capabilities,
    queryFn: api.readAgentCapabilities,
    enabled: kind === "inference",
  });
  const form = useForm({
    defaultValues: {
      scopeMode: "all" as "all" | "selected",
      selectedObjectIds: [] as number[],
      executionMode: "tool_assisted" as "one_shot" | "tool_assisted" | "detailed_coverage",
      requestedBatchId: "",
      sdkCode: model.default_agent_sdk_code ?? "",
      providerCode: model.default_agent_provider_code ?? "",
      modelCode: model.default_agent_model_code ?? "",
      reasoningEffortCode: model.default_reasoning_effort_code ?? "",
      maxTurns: model.default_max_turns ? String(model.default_max_turns) : "",
      validationRetryCount: model.default_validation_retry_count === null
        ? ""
        : String(model.default_validation_retry_count),
    },
    onSubmit: ({ value }) => {
      if (pendingStart) {
        runMutation.mutate({ kind: "retry", ...pendingStart });
        return;
      }
      const selectedObjectIds = value.scopeMode === "all"
        ? (scopeQuery.data?.items.map((item) => item.object_id) ?? [])
        : value.selectedObjectIds;
      runMutation.mutate({
        kind: "create",
        command: {
          expected_model_revision: model.model_revision,
          model_workflow: workflow,
          workflow_execution_mode: kind === "inference" ? value.executionMode : null,
          selected_object_ids: selectedObjectIds,
          requested_batch_id: value.requestedBatchId.trim() || null,
          agent: kind === "inference" ? {
            sdk_code: value.sdkCode,
            provider_code: value.providerCode,
            model_code: value.modelCode,
            reasoning_effort_code: value.reasoningEffortCode,
            max_turns: Number(value.maxTurns),
            validation_retry_count: Number(value.validationRetryCount),
          } : null,
          prompt_overrides: {},
        },
      });
    },
  });
  const scopeMode = useStore(form.store, (state) => state.values.scopeMode);
  const selectedObjectIds = useStore(form.store, (state) => state.values.selectedObjectIds);
  const executionMode = useStore(form.store, (state) => state.values.executionMode);
  const requestedBatchId = useStore(form.store, (state) => state.values.requestedBatchId);
  const sdkCode = useStore(form.store, (state) => state.values.sdkCode);
  const providerCode = useStore(form.store, (state) => state.values.providerCode);
  const modelCode = useStore(form.store, (state) => state.values.modelCode);
  const reasoningEffortCode = useStore(form.store, (state) => state.values.reasoningEffortCode);
  const maxTurns = useStore(form.store, (state) => state.values.maxTurns);
  const validationRetryCount = useStore(
    form.store,
    (state) => state.values.validationRetryCount,
  );
  const effectiveObjects = scopeMode === "all"
    ? (scopeQuery.data?.items ?? [])
    : (scopeQuery.data?.items.filter((item) => selectedObjectIds.includes(item.object_id)) ?? []);
  const batchSystems = new Set(effectiveObjects.map((item) => item.system_id));
  const batchIsIncoherent = Boolean(requestedBatchId.trim()) && batchSystems.size > 1;
  const revisionChanged = scopeQuery.data?.modelRevision !== undefined
    && scopeQuery.data.modelRevision !== model.model_revision;
  const runMutation = useMutation({
    mutationFn: async (submission: WorkflowRunSubmission) => {
      if (submission.kind === "retry") {
        if (submission.runKind === "validation") {
          if (!executeValidationCreated) throw new Error("Workflow execution is unavailable.");
          await executeValidationCreated(submission.workflowRunId);
        } else {
          if (!executeCreated) throw new Error("Workflow execution is unavailable.");
          await executeCreated(submission.workflowRunId, submission.executionMode);
        }
        return submission.workflowRunId;
      }
      const { command } = submission;
      const result = await api.createWorkflowRun(
        tenantId,
        model.model_id,
        command,
        globalThis.crypto.randomUUID(),
      );
      if (executeCreated && command.workflow_execution_mode) {
        setPendingStart({
          workflowRunId: result.workflow_run_id,
          runKind: "inference",
          executionMode: command.workflow_execution_mode,
        });
        await executeCreated(result.workflow_run_id, command.workflow_execution_mode);
      } else if (executeValidationCreated && command.workflow_execution_mode === null) {
        setPendingStart({
          workflowRunId: result.workflow_run_id,
          runKind: "validation",
        });
        await executeValidationCreated(result.workflow_run_id);
      }
      return result.workflow_run_id;
    },
    onSuccess: async (workflowRunId) => {
      await onCreated(workflowRunId);
      onClose();
    },
  });
  const capabilities = capabilitiesQuery.data;
  const compatibleSdks = capabilities?.sdks.filter((sdk) => (
    capabilities.models.some((candidate) => (
      sdk.provider_codes.includes(candidate.provider_code)
      && candidate.execution_profiles.some((profile) => profile.sdk_code === sdk.code)
    ))
  )) ?? [];
  const compatibleProviders = capabilities?.providers.filter((provider) => (
    capabilities.sdks.find((sdk) => sdk.code === sdkCode)
      ?.provider_codes.includes(provider.code) === true
    && capabilities.models.some((candidate) => (
      candidate.provider_code === provider.code
      && candidate.execution_profiles.some((profile) => profile.sdk_code === sdkCode)
    ))
  )) ?? [];
  const compatibleExecutionModes = capabilities
    ? listCompatibleExecutionModes(capabilities, sdkCode, providerCode)
    : [];
  const compatibleModels = capabilities?.models.filter((candidate) => (
    candidate.provider_code === providerCode
    && findAgentExecutionProfile(candidate, sdkCode, executionMode) !== undefined
  )) ?? [];
  const selectedModel = compatibleModels.find((candidate) => candidate.code === modelCode);
  const selectedProfile = selectedModel
    ? findAgentExecutionProfile(selectedModel, sdkCode, executionMode)
    : undefined;
  const compatibleReasoning = capabilities?.reasoning_efforts.filter((effort) => (
    selectedProfile?.reasoning_effort_codes.includes(effort.code)
  )) ?? [];
  const parsedMaxTurns = Number(maxTurns);
  const parsedRetries = Number(validationRetryCount);
  const agentSelectionValid = capabilities !== undefined
    && compatibleSdks.some((sdk) => sdk.code === sdkCode)
    && compatibleProviders.some((provider) => provider.code === providerCode)
    && compatibleExecutionModes.includes(executionMode)
    && selectedModel !== undefined
    && compatibleReasoning.some((effort) => effort.code === reasoningEffortCode)
    && Number.isInteger(parsedMaxTurns)
    && parsedMaxTurns >= capabilities.max_turns.minimum
    && parsedMaxTurns <= capabilities.max_turns.maximum
    && Number.isInteger(parsedRetries)
    && parsedRetries >= capabilities.validation_retries.minimum
    && parsedRetries <= capabilities.validation_retries.maximum;

  useEffect(() => closeButton.current?.focus(), []);
  useEffect(() => {
    if (!capabilities || kind !== "inference") return;
    const resolved = resolveAgentProfileSelection(capabilities, executionMode, {
      sdkCode,
      providerCode,
      modelCode,
      reasoningEffortCode,
    });
    if (!resolved) return;
    if (executionMode !== resolved.executionMode) {
      form.setFieldValue("executionMode", resolved.executionMode);
    }
    if (sdkCode !== resolved.sdkCode) form.setFieldValue("sdkCode", resolved.sdkCode);
    if (providerCode !== resolved.providerCode) {
      form.setFieldValue("providerCode", resolved.providerCode);
    }
    if (modelCode !== resolved.modelCode) form.setFieldValue("modelCode", resolved.modelCode);
    if (reasoningEffortCode !== resolved.reasoningEffortCode) {
      form.setFieldValue("reasoningEffortCode", resolved.reasoningEffortCode);
    }
    if (!maxTurns) {
      form.setFieldValue("maxTurns", String(model.default_max_turns ?? capabilities.max_turns.default));
    }
    if (!validationRetryCount) {
      form.setFieldValue(
        "validationRetryCount",
        String(model.default_validation_retry_count ?? capabilities.validation_retries.default),
      );
    }
  }, [
    capabilities,
    executionMode,
    form,
    kind,
    maxTurns,
    model.default_max_turns,
    model.default_validation_retry_count,
    modelCode,
    providerCode,
    reasoningEffortCode,
    sdkCode,
    validationRetryCount,
  ]);
  const title = workflow === "analysis"
    ? `Configure Analysis ${kind}`
    : `Configure ${authoringWorkflowName} run`;

  return (
    <div className="dialog-scrim" role="presentation">
      <section
        className="run-configuration-dialog"
        role="dialog"
        aria-modal="true"
        aria-labelledby="workflow-run-dialog-heading"
        onKeyDown={(event) => {
          if (event.key === "Escape" && !runMutation.isPending) onClose();
        }}
      >
        <header className="drawer-header">
          <div>
            <small>{workflow !== "analysis"
              ? "Agentic authoring"
              : kind === "inference"
                ? "Agentic inference"
                : "Deterministic validation"}</small>
            <h2 id="workflow-run-dialog-heading">{title}</h2>
          </div>
          <button
            ref={closeButton}
            className="panel-close"
            type="button"
            aria-label={`Close ${title}`}
            disabled={runMutation.isPending}
            onClick={onClose}
          >
            <span aria-hidden="true">×</span>
          </button>
        </header>

        <form
          onSubmit={(event) => {
            event.preventDefault();
            event.stopPropagation();
            void form.handleSubmit();
          }}
        >
          {kind === "inference" ? (
            <section className="agent-run-configuration" aria-labelledby="agent-run-heading">
              <header>
                <strong id="agent-run-heading">Run configuration</strong>
                <span>Model defaults are preselected and remain editable for this run.</span>
              </header>
              <div className="agent-run-grid">
                <form.Field name="executionMode">
                  {(field) => (
                    <SelectField
                      label="Execution mode"
                      value={field.state.value}
                      options={compatibleExecutionModes.map((mode) => [
                        mode,
                        WORKFLOW_EXECUTION_MODE_NAMES[mode],
                      ])}
                      onBlur={field.handleBlur}
                      onChange={(value) => field.handleChange(value as typeof field.state.value)}
                    />
                  )}
                </form.Field>
                <form.Field name="sdkCode">
                  {(field) => (
                    <SelectField
                      label="Agent SDK"
                      value={field.state.value}
                      options={compatibleSdks.map((item) => [item.code, item.name])}
                      onBlur={field.handleBlur}
                      onChange={field.handleChange}
                    />
                  )}
                </form.Field>
                <form.Field name="providerCode">
                  {(field) => (
                    <SelectField
                      label="Provider"
                      value={field.state.value}
                      options={compatibleProviders.map((item) => [item.code, item.name])}
                      onBlur={field.handleBlur}
                      onChange={field.handleChange}
                    />
                  )}
                </form.Field>
                <form.Field name="modelCode">
                  {(field) => (
                    <SelectField
                      label="Model"
                      value={field.state.value}
                      options={compatibleModels.map((item) => [item.code, item.name])}
                      onBlur={field.handleBlur}
                      onChange={field.handleChange}
                    />
                  )}
                </form.Field>
                <form.Field name="reasoningEffortCode">
                  {(field) => (
                    <SelectField
                      label="Reasoning effort"
                      value={field.state.value}
                      options={compatibleReasoning.map((item) => [
                        item.code,
                        reasoningEffortDisplayName(item),
                      ])}
                      onBlur={field.handleBlur}
                      onChange={field.handleChange}
                    />
                  )}
                </form.Field>
                <form.Field name="maxTurns">
                  {(field) => (
                    <NumericField
                      label="Maximum turns"
                      value={field.state.value}
                      minimum={capabilitiesQuery.data?.max_turns.minimum ?? 1}
                      maximum={capabilitiesQuery.data?.max_turns.maximum ?? 50}
                      onBlur={field.handleBlur}
                      onChange={field.handleChange}
                    />
                  )}
                </form.Field>
                <form.Field name="validationRetryCount">
                  {(field) => (
                    <NumericField
                      label="Validation retries"
                      value={field.state.value}
                      minimum={capabilitiesQuery.data?.validation_retries.minimum ?? 0}
                      maximum={capabilitiesQuery.data?.validation_retries.maximum ?? 5}
                      onBlur={field.handleBlur}
                      onChange={field.handleChange}
                    />
                  )}
                </form.Field>
              </div>
            </section>
          ) : (
            <p className="run-kind-note">
              Pending relationships are validated with deterministic queries. Agent settings are not used.
            </p>
          )}

          <fieldset className="scope-mode-options">
            <legend>Object coverage</legend>
            <form.Field name="scopeMode">
              {(field) => (
                <>
                  <label>
                    <input
                      type="radio"
                      name={field.name}
                      checked={field.state.value === "all"}
                      onChange={() => field.handleChange("all")}
                    />
                    <span>
                      <strong>All Objects</strong>
                      <small>Every eligible active {scopeZoneName} Object in Scope</small>
                    </span>
                  </label>
                  <label>
                    <input
                      type="radio"
                      name={field.name}
                      checked={field.state.value === "selected"}
                      onChange={() => field.handleChange("selected")}
                    />
                    <span><strong>Selected Objects</strong><small>Choose an exact subset</small></span>
                  </label>
                </>
              )}
            </form.Field>
          </fieldset>

          <section className="run-object-selection" aria-labelledby="workflow-run-scope-heading">
            <header>
              <strong id="workflow-run-scope-heading">Active {scopeZoneName} Scope</strong>
              <span>{effectiveObjects.length} selected</span>
            </header>
            {scopeQuery.isPending ? (
              <div className="surface-state compact" aria-busy="true">Loading active Scope…</div>
            ) : scopeQuery.isError ? (
              <div className="surface-state is-error compact" role="alert">
                Active Scope could not be loaded.
              </div>
            ) : (
              <form.Field name="selectedObjectIds">
                {(field) => (
                  <div className="run-object-list">
                    {scopeQuery.data.items.map((item) => (
                      <label key={item.object_id}>
                        <input
                          type="checkbox"
                          checked={scopeMode === "all" || field.state.value.includes(item.object_id)}
                          disabled={scopeMode === "all"}
                          onChange={(event) => field.handleChange(event.target.checked
                            ? [...field.state.value, item.object_id]
                            : field.state.value.filter((id) => id !== item.object_id))}
                        />
                        <span>
                          <strong>{item.object_name}</strong>
                          <small>{item.system_code} · {item.source_tenant_code}</small>
                        </span>
                      </label>
                    ))}
                  </div>
                )}
              </form.Field>
            )}
          </section>

          <form.Field name="requestedBatchId">
            {(field) => (
              <label className="batch-input">
                <span>Batch ID (optional)</span>
                <input
                  aria-label="Batch ID (optional)"
                  value={field.state.value}
                  onBlur={field.handleBlur}
                  onChange={(event) => field.handleChange(event.target.value)}
                />
                <small>A Batch ID requires selected Objects from one System.</small>
              </label>
            )}
          </form.Field>

          {kind === "inference" && capabilitiesQuery.isError ? (
            <p className="inline-error" role="alert">Agent options could not be loaded.</p>
          ) : null}
          {kind === "inference" && capabilitiesQuery.data && !agentSelectionValid ? (
            <p className="inline-error" role="alert">No compatible agent configuration is available.</p>
          ) : null}
          {batchIsIncoherent ? (
            <p className="inline-error" role="alert">
              Select Objects from one System when using a Batch ID.
            </p>
          ) : null}
          {revisionChanged ? (
            <p className="inline-error" role="alert">
              The Model changed. Close this dialog and refresh before creating the run.
            </p>
          ) : null}
          {runMutation.isError ? (
            <p className="inline-error" role="alert">
              {pendingStart && isTenantWorkflowConflict(runMutation.error)
                ? TENANT_WORKFLOW_CONFLICT_MESSAGE
                : pendingStart
                  ? `The ${workflowName} run remains queued because it could not be started.`
                  : workflow !== "analysis"
                    ? `The ${authoringWorkflowName} run could not be created.`
                    : "The Analysis run could not be created."}
            </p>
          ) : null}

          <footer className="dialog-actions">
            <p>The backend revalidates Scope, Model revision, agent options, and Tenant Lock.</p>
            <div>
              <button
                className="button button-secondary button-small"
                type="button"
                disabled={runMutation.isPending}
                onClick={onClose}
              >
                Cancel
              </button>
              <button
                className="button button-primary button-small"
                type="submit"
                disabled={
                  runMutation.isPending
                  || (pendingStart === null && (
                    scopeQuery.isPending
                    || scopeQuery.isError
                    || effectiveObjects.length === 0
                    || batchIsIncoherent
                    || revisionChanged
                    || (kind === "inference" && (capabilitiesQuery.isPending || !agentSelectionValid))
                  ))
                }
              >
                {runMutation.isPending
                  ? pendingStart
                    ? "Starting…"
                    : workflow !== "analysis" || executeCreated || executeValidationCreated
                      ? "Creating and starting…"
                      : "Creating…"
                  : pendingStart
                    ? "Retry start"
                    : workflow !== "analysis"
                      ? `Create and run ${authoringWorkflowName}`
                      : executeCreated || executeValidationCreated
                        ? `Create and run ${kind}`
                        : `Create queued ${kind} run`}
              </button>
            </div>
          </footer>
        </form>
      </section>
    </div>
  );
}

function SelectField({
  label,
  value,
  options,
  onBlur,
  onChange,
}: {
  label: string;
  value: string;
  options: [string, string][];
  onBlur: () => void;
  onChange: (value: string) => void;
}) {
  return (
    <label>
      <span>{label}</span>
      <select
        aria-label={label}
        value={value}
        onBlur={onBlur}
        onChange={(event) => onChange(event.target.value)}
      >
        <option value="">Select…</option>
        {options.map(([optionValue, optionLabel]) => (
          <option key={optionValue} value={optionValue}>{optionLabel}</option>
        ))}
      </select>
    </label>
  );
}

function NumericField({
  label,
  value,
  minimum,
  maximum,
  onBlur,
  onChange,
}: {
  label: string;
  value: string;
  minimum: number;
  maximum: number;
  onBlur: () => void;
  onChange: (value: string) => void;
}) {
  return (
    <label>
      <span>{label}</span>
      <input
        aria-label={label}
        type="number"
        min={minimum}
        max={maximum}
        value={value}
        onBlur={onBlur}
        onChange={(event) => onChange(event.target.value)}
      />
    </label>
  );
}
