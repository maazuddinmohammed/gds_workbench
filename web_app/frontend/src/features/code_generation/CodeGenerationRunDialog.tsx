import { useEffect, useRef } from "react";
import { useForm, useStore } from "@tanstack/react-form";
import { useMutation, useQuery } from "@tanstack/react-query";

import { ApiError } from "../../core/http";
import type { MappingEntityType } from "../mapping/api";
import type { ModelDetail } from "../models/api";
import {
  resolveDefaultAgent,
  workflowCreationQueryKeys,
  type CreateWorkflowRunCommand,
} from "../workflows/api";
import type { CodeGenerationApi, CodeGenerationTarget } from "./api";

export type CodeGenerationCoverage = "selected_targets" | "all_eligible_targets";

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
      createMutation.mutate({
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
      });
    },
  });
  const values = useStore(form.store, (state) => state.values);
  const capabilities = capabilitiesQuery.data;
  const compatibleProviders = capabilities?.providers.filter((provider) => (
    capabilities.sdks.find((sdk) => sdk.code === values.sdkCode)
      ?.provider_codes.includes(provider.code)
  )) ?? [];
  const compatibleModels = capabilities?.models.filter((candidate) => (
    candidate.provider_code === values.providerCode
    && candidate.sdk_codes.includes(values.sdkCode)
  )) ?? [];
  const selectedModel = compatibleModels.find((candidate) => candidate.code === values.modelCode);
  const compatibleReasoning = capabilities?.reasoning_efforts.filter((effort) => (
    selectedModel?.reasoning_effort_codes.includes(effort.code)
  )) ?? [];
  const parsedMaxTurns = Number(values.maxTurns);
  const parsedRetries = Number(values.validationRetryCount);
  const agentSelectionValid = capabilities !== undefined
    && capabilities.sdks.some((sdk) => sdk.code === values.sdkCode)
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
  const createMutation = useMutation({
    mutationFn: async (command: CreateWorkflowRunCommand) => {
      const result = await api.createWorkflowRun(
        tenantId,
        model.model_id,
        command,
        globalThis.crypto.randomUUID(),
      );
      await api.executeCodeGenerationRun(
        tenantId,
        model.model_id,
        result.workflow_run_id,
        model.model_revision,
      );
      return result;
    },
    onSuccess: async (result) => {
      await onStarted(result.workflow_run_id);
      onClose();
    },
  });

  useEffect(() => closeButton.current?.focus(), []);
  useEffect(() => {
    if (!capabilities) return;
    const resolved = resolveDefaultAgent(capabilities, {
      sdkCode: model.default_agent_sdk_code,
      providerCode: model.default_agent_provider_code,
      modelCode: model.default_agent_model_code,
      reasoningEffortCode: model.default_reasoning_effort_code,
      maxTurns: model.default_max_turns,
      validationRetryCount: model.default_validation_retry_count,
    });
    if (!resolved) return;
    if (!form.state.values.sdkCode) form.setFieldValue("sdkCode", resolved.sdk_code);
    if (!form.state.values.providerCode) form.setFieldValue("providerCode", resolved.provider_code);
    if (!form.state.values.modelCode) form.setFieldValue("modelCode", resolved.model_code);
    if (!form.state.values.reasoningEffortCode) {
      form.setFieldValue("reasoningEffortCode", resolved.reasoning_effort_code);
    }
    if (!form.state.values.maxTurns) form.setFieldValue("maxTurns", String(resolved.max_turns));
    if (!form.state.values.validationRetryCount) {
      form.setFieldValue("validationRetryCount", String(resolved.validation_retry_count));
    }
  }, [capabilities, form, model]);

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
          if (event.key === "Escape") onClose();
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
                  options={capabilities?.sdks.map((item) => [item.code, item.name]) ?? []}
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
                  options={compatibleReasoning.map((item) => [item.code, item.name])}
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
          {createMutation.isError ? (
            <p className="inline-error" role="alert">{runError(createMutation.error)}</p>
          ) : null}

          <footer className="dialog-actions">
            <p>Nothing runs until you confirm. The backend rechecks role, lock, revision, eligibility, guide, and agent options.</p>
            <div>
              <button className="button button-secondary button-small" type="button" onClick={onClose}>
                Cancel
              </button>
              <button
                className="button button-primary button-small"
                type="submit"
                disabled={
                  capabilitiesQuery.isPending
                  || capabilitiesQuery.isError
                  || createMutation.isPending
                  || !selectionValid
                  || !agentSelectionValid
                }
              >
                {createMutation.isPending ? "Creating and starting…" : title}
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

function runError(error: Error): string {
  if (error instanceof ApiError && error.status === 403) {
    return "You no longer have permission or the required Tenant Lock to generate SQL.";
  }
  if (error instanceof ApiError && error.status === 409) {
    return "The Model, Mapping, or guide changed. Refresh before creating another run.";
  }
  return "The Code Generation run could not be created or started.";
}
