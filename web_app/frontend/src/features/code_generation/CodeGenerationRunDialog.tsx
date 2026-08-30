import { useEffect, useRef, useState } from "react";
import { useForm, useStore } from "@tanstack/react-form";
import { useMutation, useQuery } from "@tanstack/react-query";

import { ApiError } from "../../core/http";
import type { MappingEntityType } from "../mapping/api";
import type { ModelDetail } from "../models/api";
import {
  findAgentExecutionProfile,
  reasoningEffortDisplayName,
  resolveDefaultAgent,
  workflowCreationQueryKeys,
  type CreateWorkflowRunCommand,
} from "../workflows/api";
import {
  isTenantWorkflowConflict,
  TENANT_WORKFLOW_CONFLICT_MESSAGE,
} from "../workflows/presentation";
import type { CodeGenerationApi, CodeGenerationTarget } from "./api";

export type CodeGenerationCoverage = "selected_targets" | "all_eligible_targets";
type CodeGenerationRunSubmission =
  | { kind: "create"; command: CreateWorkflowRunCommand }
  | { kind: "retry"; workflowRunId: number };
const CODE_GENERATION_AGENT_EXECUTION_MODE = "detailed_coverage" as const;

export function CodeGenerationRunDialog({
  api,
  tenantId,
  model,
  entityType,
  coverage,
  selectedTargets,
  onClose,
  onStarted,
}: {
  api: CodeGenerationApi;
  tenantId: number;
  model: ModelDetail;
  entityType: MappingEntityType;
  coverage: CodeGenerationCoverage;
  selectedTargets: CodeGenerationTarget[];
  onClose: () => void;
  onStarted: (workflowRunId: number) => Promise<void>;
}) {
  const closeButton = useRef<HTMLButtonElement>(null);
  const [pendingWorkflowRunId, setPendingWorkflowRunId] = useState<number | null>(null);
  const capabilitiesQuery = useQuery({
    queryKey: workflowCreationQueryKeys.capabilities,
    queryFn: api.readAgentCapabilities,
  });
  const form = useForm({
    defaultValues: {
      sdkCode: model.default_agent_sdk_code ?? "",
      providerCode: model.default_agent_provider_code ?? "",
      modelCode: model.default_agent_model_code ?? "",
      reasoningEffortCode: model.default_reasoning_effort_code ?? "",
      maxTurns: model.default_max_turns === null ? "" : String(model.default_max_turns),
      validationRetryCount: model.default_validation_retry_count === null
        ? ""
        : String(model.default_validation_retry_count),
    },
    onSubmit: ({ value }) => {
      if (pendingWorkflowRunId !== null) {
        runMutation.mutate({ kind: "retry", workflowRunId: pendingWorkflowRunId });
        return;
      }
      runMutation.mutate({
        kind: "create",
        command: {
          expected_model_revision: model.model_revision,
          model_workflow: "code_generation",
          workflow_execution_mode: null,
          selected_object_ids: coverage === "selected_targets"
            ? selectedTargets.map((item) => item.target.object_id)
            : [],
          modeled_entity_type: entityType,
          requested_batch_id: null,
          agent: {
            sdk_code: value.sdkCode,
            provider_code: value.providerCode,
            model_code: value.modelCode,
            reasoning_effort_code: value.reasoningEffortCode,
            max_turns: Number(value.maxTurns),
            validation_retry_count: Number(value.validationRetryCount),
          },
          prompt_overrides: {},
          code_generation_coverage_mode: coverage,
          sql_generation_guide_version_id: null,
        },
      });
    },
  });
  const values = useStore(form.store, (state) => state.values);
  const capabilities = capabilitiesQuery.data;
  const compatibleSdks = capabilities?.sdks.filter((sdk) => (
    capabilities.models.some((candidate) => (
      sdk.provider_codes.includes(candidate.provider_code)
      && findAgentExecutionProfile(
        candidate,
        sdk.code,
        CODE_GENERATION_AGENT_EXECUTION_MODE,
      ) !== undefined
    ))
  )) ?? [];
  const compatibleProviders = capabilities?.providers.filter((provider) => (
    capabilities.sdks.find((sdk) => sdk.code === values.sdkCode)
      ?.provider_codes.includes(provider.code) === true
    && capabilities.models.some((candidate) => (
      candidate.provider_code === provider.code
      && findAgentExecutionProfile(
        candidate,
        values.sdkCode,
        CODE_GENERATION_AGENT_EXECUTION_MODE,
      ) !== undefined
    ))
  )) ?? [];
  const compatibleModels = capabilities?.models.filter((candidate) => (
    candidate.provider_code === values.providerCode
    && findAgentExecutionProfile(
      candidate,
      values.sdkCode,
      CODE_GENERATION_AGENT_EXECUTION_MODE,
    ) !== undefined
  )) ?? [];
  const selectedModel = compatibleModels.find((candidate) => candidate.code === values.modelCode);
  const selectedProfile = selectedModel
    ? findAgentExecutionProfile(
      selectedModel,
      values.sdkCode,
      CODE_GENERATION_AGENT_EXECUTION_MODE,
    )
    : undefined;
  const compatibleReasoning = capabilities?.reasoning_efforts.filter((effort) => (
    selectedProfile?.reasoning_effort_codes.includes(effort.code)
  )) ?? [];
  const parsedMaxTurns = Number(values.maxTurns);
  const parsedRetries = Number(values.validationRetryCount);
  const agentSelectionValid = capabilities !== undefined
    && compatibleSdks.some((sdk) => sdk.code === values.sdkCode)
    && compatibleProviders.some((provider) => provider.code === values.providerCode)
    && selectedModel !== undefined
    && compatibleReasoning.some((effort) => effort.code === values.reasoningEffortCode)
    && Number.isInteger(parsedMaxTurns)
    && parsedMaxTurns >= capabilities.max_turns.minimum
    && parsedMaxTurns <= capabilities.max_turns.maximum
    && Number.isInteger(parsedRetries)
    && parsedRetries >= capabilities.validation_retries.minimum
    && parsedRetries <= capabilities.validation_retries.maximum;
  const selectionValid = coverage === "all_eligible_targets" || selectedTargets.length > 0;
  const runMutation = useMutation({
    mutationFn: async (submission: CodeGenerationRunSubmission) => {
      if (submission.kind === "retry") {
        await api.executeCodeGenerationRun(
          tenantId,
          model.model_id,
          submission.workflowRunId,
          model.model_revision,
        );
        return submission.workflowRunId;
      }
      const { command } = submission;
      const result = await api.createWorkflowRun(
        tenantId,
        model.model_id,
        command,
        globalThis.crypto.randomUUID(),
      );
      setPendingWorkflowRunId(result.workflow_run_id);
      await api.executeCodeGenerationRun(
        tenantId,
        model.model_id,
        result.workflow_run_id,
        model.model_revision,
      );
      return result.workflow_run_id;
    },
    onSuccess: async (workflowRunId) => {
      await onStarted(workflowRunId);
      onClose();
    },
  });

  useEffect(() => closeButton.current?.focus(), []);
  useEffect(() => {
    if (!capabilities) return;
    const resolved = resolveDefaultAgent(
      capabilities,
      CODE_GENERATION_AGENT_EXECUTION_MODE,
      {
        sdkCode: values.sdkCode,
        providerCode: values.providerCode,
        modelCode: values.modelCode,
        reasoningEffortCode: values.reasoningEffortCode,
        maxTurns: model.default_max_turns,
        validationRetryCount: model.default_validation_retry_count,
      },
    );
    if (!resolved) return;
    if (values.sdkCode !== resolved.sdk_code) form.setFieldValue("sdkCode", resolved.sdk_code);
    if (values.providerCode !== resolved.provider_code) {
      form.setFieldValue("providerCode", resolved.provider_code);
    }
    if (values.modelCode !== resolved.model_code) {
      form.setFieldValue("modelCode", resolved.model_code);
    }
    if (values.reasoningEffortCode !== resolved.reasoning_effort_code) {
      form.setFieldValue("reasoningEffortCode", resolved.reasoning_effort_code);
    }
    if (!values.maxTurns) form.setFieldValue("maxTurns", String(resolved.max_turns));
    if (!values.validationRetryCount) {
      form.setFieldValue("validationRetryCount", String(resolved.validation_retry_count));
    }
  }, [
    capabilities,
    form,
    model.default_max_turns,
    model.default_validation_retry_count,
    values.maxTurns,
    values.modelCode,
    values.providerCode,
    values.reasoningEffortCode,
    values.sdkCode,
    values.validationRetryCount,
  ]);

  const allTargets = coverage === "all_eligible_targets";
  const title = allTargets ? "Generate all eligible SQL" : selectedRunTitle(selectedTargets);

  return (
    <div className="dialog-scrim code-generation-dialog-scrim" role="presentation">
      <section
        className="run-configuration-dialog code-generation-run-dialog"
        role="dialog"
        aria-modal="true"
        aria-labelledby="code-generation-run-heading"
        onKeyDown={(event) => {
          if (event.key === "Escape" && !runMutation.isPending) onClose();
        }}
      >
        <header className="drawer-header">
          <div>
            <small>Explicit SQL generation</small>
            <h2 id="code-generation-run-heading">{title}</h2>
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
          <section className="code-generation-run-scope" aria-labelledby="code-generation-scope-heading">
            <header>
              <strong id="code-generation-scope-heading">Run scope</strong>
              <span>The backend freezes eligibility and provenance when the run is created.</span>
            </header>
            <dl className="detail-fact-grid">
              <Fact label="Model" value={`${model.model_name} · r${model.model_revision}`} />
              <Fact label="Modeled layer" value={layerLabel(entityType)} />
              <Fact label="Execution mode" value="Detailed coverage" />
              <Fact
                label="Coverage"
                value={allTargets ? "All eligible target Objects" : `${selectedTargets.length} selected target Object${selectedTargets.length === 1 ? "" : "s"}`}
              />
              <Fact label="SQL guide" value="Default active published guide" />
            </dl>
            {!allTargets ? (
              <ul className="code-generation-run-targets" aria-label="Selected target Objects">
                {selectedTargets.slice(0, 12).map((item) => (
                  <li key={item.target.object_id}>
                    <strong>{item.target.object_schema}.{item.target.object_name}</strong>
                    <span>{item.target.system_code}</span>
                  </li>
                ))}
                {selectedTargets.length > 12 ? (
                  <li><strong>{selectedTargets.length - 12} more selected</strong></li>
                ) : null}
              </ul>
            ) : null}
          </section>

          <section className="agent-run-configuration" aria-labelledby="code-generation-agent-heading">
            <header>
              <strong id="code-generation-agent-heading">Generator configuration</strong>
              <span>Model defaults are preselected and editable for this run.</span>
            </header>
            <div className="agent-run-grid">
              <form.Field name="sdkCode">
                {(field) => <SelectField
                  label="Agent SDK"
                  value={field.state.value}
                  options={compatibleSdks.map((item) => [item.code, item.name])}
                  onChange={field.handleChange}
                />}
              </form.Field>
              <form.Field name="providerCode">
                {(field) => <SelectField
                  label="Provider"
                  value={field.state.value}
                  options={compatibleProviders.map((item) => [item.code, item.name])}
                  onChange={field.handleChange}
                />}
              </form.Field>
              <form.Field name="modelCode">
                {(field) => <SelectField
                  label="Model"
                  value={field.state.value}
                  options={compatibleModels.map((item) => [item.code, item.name])}
                  onChange={field.handleChange}
                />}
              </form.Field>
              <form.Field name="reasoningEffortCode">
                {(field) => <SelectField
                  label="Reasoning effort"
                  value={field.state.value}
                  options={compatibleReasoning.map((item) => [
                    item.code,
                    reasoningEffortDisplayName(item),
                  ])}
                  onChange={field.handleChange}
                />}
              </form.Field>
              <form.Field name="maxTurns">
                {(field) => <NumberField
                  label="Maximum turns"
                  value={field.state.value}
                  minimum={capabilities?.max_turns.minimum ?? 1}
                  maximum={capabilities?.max_turns.maximum ?? 50}
                  onChange={field.handleChange}
                />}
              </form.Field>
              <form.Field name="validationRetryCount">
                {(field) => <NumberField
                  label="Validation retries"
                  value={field.state.value}
                  minimum={capabilities?.validation_retries.minimum ?? 0}
                  maximum={capabilities?.validation_retries.maximum ?? 5}
                  onChange={field.handleChange}
                />}
              </form.Field>
            </div>
          </section>

          {capabilitiesQuery.isError ? (
            <p className="inline-error" role="alert">Generator options could not be loaded.</p>
          ) : null}
          {capabilities && !agentSelectionValid ? (
            <p className="inline-error" role="alert">No compatible generator configuration is available.</p>
          ) : null}
          {runMutation.isError ? (
            <p className="inline-error" role="alert">
              {runError(runMutation.error, pendingWorkflowRunId !== null)}
            </p>
          ) : null}

          <footer className="dialog-actions">
            <p>Nothing runs until you confirm. The backend rechecks role, lock, revision, eligibility, guide, and agent options.</p>
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
                  || (pendingWorkflowRunId === null && (
                    capabilitiesQuery.isPending
                    || capabilitiesQuery.isError
                    || !selectionValid
                    || !agentSelectionValid
                  ))
                }
              >
                {runMutation.isPending
                  ? pendingWorkflowRunId === null ? "Creating and starting…" : "Starting…"
                  : pendingWorkflowRunId === null ? title : "Retry start"}
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
  onChange,
}: {
  label: string;
  value: string;
  options: [string, string][];
  onChange: (value: string) => void;
}) {
  return (
    <label>
      <span>{label}</span>
      <select aria-label={label} value={value} onChange={(event) => onChange(event.target.value)}>
        <option value="">Select…</option>
        {options.map(([optionValue, optionLabel]) => (
          <option key={optionValue} value={optionValue}>{optionLabel}</option>
        ))}
      </select>
    </label>
  );
}

function NumberField({
  label,
  value,
  minimum,
  maximum,
  onChange,
}: {
  label: string;
  value: string;
  minimum: number;
  maximum: number;
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
        onChange={(event) => onChange(event.target.value)}
      />
    </label>
  );
}

function Fact({ label, value }: { label: string; value: string }) {
  return <div><dt>{label}</dt><dd>{value}</dd></div>;
}

function selectedRunTitle(targets: CodeGenerationTarget[]): string {
  if (targets.length === 1) {
    return targets[0]?.latest_artifact ? "Regenerate stored SQL" : "Generate SQL";
  }
  return "Generate selected SQL";
}

function layerLabel(entityType: MappingEntityType): string {
  return entityType === "logical_entity" ? "Logical" : "Dimensional";
}

function runError(error: Error, runWasCreated: boolean): string {
  if (runWasCreated && isTenantWorkflowConflict(error)) {
    return TENANT_WORKFLOW_CONFLICT_MESSAGE;
  }
  if (runWasCreated) {
    return "The Code Generation run remains queued because it could not be started.";
  }
  if (error instanceof ApiError && error.status === 403) {
    return "You no longer have permission or the required Tenant Lock to generate SQL.";
  }
  if (error instanceof ApiError && error.status === 409) {
    return "The Model, Mapping, or guide changed. Refresh before creating another run.";
  }
  return "The Code Generation run could not be created or started.";
}
