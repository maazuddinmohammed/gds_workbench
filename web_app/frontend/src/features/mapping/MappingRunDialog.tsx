import { useEffect, useMemo, useRef, useState } from "react";
import { useForm, useStore } from "@tanstack/react-form";
import { useMutation, useQuery } from "@tanstack/react-query";

import { ApiError } from "../../core/http";
import type { ModelDetail } from "../models/api";
import {
  findAgentExecutionProfile,
  listCompatibleExecutionModes,
  reasoningEffortDisplayName,
  resolveAgentProfileSelection,
  WORKFLOW_EXECUTION_MODE_NAMES,
  workflowCreationQueryKeys,
  type CreateWorkflowRunCommand,
} from "../workflows/api";
import {
  isTenantWorkflowConflict,
  TENANT_WORKFLOW_CONFLICT_MESSAGE,
} from "../workflows/presentation";
import {
  loadActiveMappingOutputTemplates,
  loadAllMappingScope,
  mappingQueryKeys,
  type MappingApi,
  type MappingEntityType,
} from "./api";
import { MappingOutputTemplateSelection } from "./MappingOutputTemplateSelection";

type ExecutionMode = NonNullable<CreateWorkflowRunCommand["workflow_execution_mode"]>;
type PendingMappingStart = {
  workflowRunId: number;
  executionMode: ExecutionMode;
};
type MappingRunSubmission =
  | { kind: "create"; command: CreateWorkflowRunCommand }
  | ({ kind: "retry" } & PendingMappingStart);

export function MappingRunDialog({
  api,
  tenantId,
  model,
  onClose,
  onCompleted,
}: {
  api: MappingApi;
  tenantId: number;
  model: ModelDetail;
  onClose: () => void;
  onCompleted: (workflowRunId: number) => Promise<void>;
}) {
  const closeButton = useRef<HTMLButtonElement>(null);
  const [pendingStart, setPendingStart] = useState<PendingMappingStart | null>(null);
  const scopeQuery = useQuery({
    queryKey: mappingQueryKeys.runScope(tenantId, model.model_id),
    queryFn: () => loadAllMappingScope(api, tenantId, model.model_id),
  });
  const capabilitiesQuery = useQuery({
    queryKey: workflowCreationQueryKeys.capabilities,
    queryFn: api.readAgentCapabilities,
  });
  const outputTemplatesQuery = useQuery({
    queryKey: mappingQueryKeys.outputTemplates(tenantId, model.model_id),
    queryFn: () => loadActiveMappingOutputTemplates(api, tenantId),
  });
  const form = useForm({
    defaultValues: {
      entityType: "logical_entity" as MappingEntityType,
      targetObjectId: "",
      sourceSystemId: "",
      operation: "build" as "build" | "extend",
      artifactType: "sql_file" as "sql_file" | "python_file" | "python_notebook",
      executionMode: "tool_assisted" as ExecutionMode,
      objectOutputTemplateId: "",
      attributeOutputTemplateId: "",
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
      if (pendingStart) {
        runMutation.mutate({ kind: "retry", ...pendingStart });
        return;
      }
      const targetObjectId = Number(value.targetObjectId);
      const sourceSystemId = Number(value.sourceSystemId);
      const objectOutputTemplateId = value.objectOutputTemplateId
        ? Number(value.objectOutputTemplateId)
        : null;
      const attributeOutputTemplateId = value.attributeOutputTemplateId
        ? Number(value.attributeOutputTemplateId)
        : null;
      if (
        !Number.isSafeInteger(targetObjectId)
        || !Number.isSafeInteger(sourceSystemId)
        || (objectOutputTemplateId !== null && !Number.isSafeInteger(objectOutputTemplateId))
        || (attributeOutputTemplateId !== null && !Number.isSafeInteger(attributeOutputTemplateId))
      ) return;
      runMutation.mutate({
        kind: "create",
        command: {
          expected_model_revision: model.model_revision,
          model_workflow: "mapping",
          workflow_execution_mode: value.executionMode,
          selected_object_ids: [targetObjectId],
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
          mapping_operation: value.operation,
          mapping_coverage_mode: "selected_targets",
          mapping_artifact_type: value.artifactType,
          mapping_source_system_id: sourceSystemId,
          mapping_object_output_template_id: objectOutputTemplateId,
          mapping_attribute_output_template_id: attributeOutputTemplateId,
        },
      });
    },
  });
  const values = useStore(form.store, (state) => state.values);
  const targets = useMemo(() => (
    (scopeQuery.data?.items ?? []).filter((item) => values.entityType === "logical_entity"
      ? item.is_logical_mapping_target_eligible
      : item.is_dimensional_mapping_target_eligible)
  ), [scopeQuery.data?.items, values.entityType]);
  const sourceSystems = useMemo(() => {
    const byId = new Map<number, { system_id: number; system_code: string; system_name: string }>();
    for (const item of scopeQuery.data?.items ?? []) {
      byId.set(item.system_id, {
        system_id: item.system_id,
        system_code: item.system_code,
        system_name: item.system_name,
      });
    }
    return [...byId.values()].sort((left, right) => left.system_code.localeCompare(right.system_code));
  }, [scopeQuery.data?.items]);
  const capabilities = capabilitiesQuery.data;
  const compatibleSdks = capabilities?.sdks.filter((sdk) => (
    capabilities.models.some((candidate) => (
      sdk.provider_codes.includes(candidate.provider_code)
      && candidate.execution_profiles.some((profile) => profile.sdk_code === sdk.code)
    ))
  )) ?? [];
  const compatibleProviders = capabilities?.providers.filter((provider) => (
    capabilities.sdks.find((sdk) => sdk.code === values.sdkCode)
      ?.provider_codes.includes(provider.code) === true
    && capabilities.models.some((candidate) => (
      candidate.provider_code === provider.code
      && candidate.execution_profiles.some((profile) => profile.sdk_code === values.sdkCode)
    ))
  )) ?? [];
  const compatibleExecutionModes = capabilities
    ? listCompatibleExecutionModes(capabilities, values.sdkCode, values.providerCode)
    : [];
  const compatibleModels = capabilities?.models.filter((candidate) => (
    candidate.provider_code === values.providerCode
    && findAgentExecutionProfile(candidate, values.sdkCode, values.executionMode) !== undefined
  )) ?? [];
  const selectedModel = compatibleModels.find((candidate) => candidate.code === values.modelCode);
  const selectedProfile = selectedModel
    ? findAgentExecutionProfile(selectedModel, values.sdkCode, values.executionMode)
    : undefined;
  const compatibleReasoning = capabilities?.reasoning_efforts.filter((effort) => (
    selectedProfile?.reasoning_effort_codes.includes(effort.code)
  )) ?? [];
  const targetId = Number(values.targetObjectId);
  const sourceSystemId = Number(values.sourceSystemId);
  const parsedMaxTurns = Number(values.maxTurns);
  const parsedRetries = Number(values.validationRetryCount);
  const targetSelectionValid = targets.some((target) => target.object_id === targetId);
  const sourceSystemSelectionValid = sourceSystems.some((system) => system.system_id === sourceSystemId);
  const objectOutputTemplateSelectionValid = values.objectOutputTemplateId === ""
    || Boolean(outputTemplatesQuery.data?.mappingObjects.some((template) => (
      template.output_template_id === Number(values.objectOutputTemplateId)
      && template.output_template_schema_digest_is_valid
    )));
  const attributeOutputTemplateSelectionValid = values.attributeOutputTemplateId === ""
    || Boolean(outputTemplatesQuery.data?.mappingAttributes.some((template) => (
      template.output_template_id === Number(values.attributeOutputTemplateId)
      && template.output_template_schema_digest_is_valid
    )));
  const agentSelectionValid = capabilities !== undefined
    && compatibleSdks.some((sdk) => sdk.code === values.sdkCode)
    && compatibleProviders.some((provider) => provider.code === values.providerCode)
    && compatibleExecutionModes.includes(values.executionMode)
    && selectedModel !== undefined
    && compatibleReasoning.some((effort) => effort.code === values.reasoningEffortCode)
    && Number.isInteger(parsedMaxTurns)
    && parsedMaxTurns >= capabilities.max_turns.minimum
    && parsedMaxTurns <= capabilities.max_turns.maximum
    && Number.isInteger(parsedRetries)
    && parsedRetries >= capabilities.validation_retries.minimum
    && parsedRetries <= capabilities.validation_retries.maximum;
  const revisionChanged = scopeQuery.data !== undefined
    && scopeQuery.data.modelRevision !== model.model_revision;
  const runMutation = useMutation({
    mutationFn: async (submission: MappingRunSubmission) => {
      if (submission.kind === "retry") {
        await api.executeMappingRun(
          tenantId,
          model.model_id,
          submission.workflowRunId,
          submission.executionMode,
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
      const pending = {
        workflowRunId: result.workflow_run_id,
        executionMode: command.workflow_execution_mode as ExecutionMode,
      };
      setPendingStart(pending);
      await api.executeMappingRun(
        tenantId,
        model.model_id,
        pending.workflowRunId,
        pending.executionMode,
        model.model_revision,
      );
      return pending.workflowRunId;
    },
    onSuccess: async (workflowRunId) => {
      await onCompleted(workflowRunId);
      onClose();
    },
  });

  useEffect(() => closeButton.current?.focus(), []);
  useEffect(() => {
    if (!capabilities) return;
    const resolved = resolveAgentProfileSelection(capabilities, values.executionMode, {
      sdkCode: values.sdkCode,
      providerCode: values.providerCode,
      modelCode: values.modelCode,
      reasoningEffortCode: values.reasoningEffortCode,
    });
    if (!resolved) return;
    if (values.executionMode !== resolved.executionMode) {
      form.setFieldValue("executionMode", resolved.executionMode);
    }
    if (values.sdkCode !== resolved.sdkCode) form.setFieldValue("sdkCode", resolved.sdkCode);
    if (values.providerCode !== resolved.providerCode) {
      form.setFieldValue("providerCode", resolved.providerCode);
    }
    if (values.modelCode !== resolved.modelCode) {
      form.setFieldValue("modelCode", resolved.modelCode);
    }
    if (values.reasoningEffortCode !== resolved.reasoningEffortCode) {
      form.setFieldValue("reasoningEffortCode", resolved.reasoningEffortCode);
    }
    if (!values.maxTurns) {
      form.setFieldValue("maxTurns", String(model.default_max_turns ?? capabilities.max_turns.default));
    }
    if (!values.validationRetryCount) {
      form.setFieldValue(
        "validationRetryCount",
        String(model.default_validation_retry_count ?? capabilities.validation_retries.default),
      );
    }
  }, [
    capabilities,
    form,
    model.default_max_turns,
    model.default_validation_retry_count,
    values.executionMode,
    values.maxTurns,
    values.modelCode,
    values.providerCode,
    values.reasoningEffortCode,
    values.sdkCode,
    values.validationRetryCount,
  ]);
  useEffect(() => {
    if (values.targetObjectId && !targets.some((target) => target.object_id === targetId)) {
      form.setFieldValue("targetObjectId", "");
    }
  }, [form, targetId, targets, values.targetObjectId]);

  return (
    <div className="dialog-scrim" role="presentation">
      <section
        className="run-configuration-dialog mapping-run-dialog"
        role="dialog"
        aria-modal="true"
        aria-labelledby="mapping-run-dialog-heading"
        onKeyDown={(event) => {
          if (event.key === "Escape" && !runMutation.isPending) onClose();
        }}
      >
        <header className="drawer-header">
          <div>
            <small>Agentic authoring</small>
            <h2 id="mapping-run-dialog-heading">Configure Mapping run</h2>
          </div>
          <button
            ref={closeButton}
            className="panel-close"
            type="button"
            aria-label="Close Configure Mapping run"
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
          <section className="agent-run-configuration" aria-labelledby="mapping-target-heading">
            <header>
              <strong id="mapping-target-heading">Target and delivery</strong>
              <span>Exactly one eligible target and one source System per run.</span>
            </header>
            <div className="agent-run-grid">
              <form.Field name="entityType">
                {(field) => <SelectField
                  label="Entity type"
                  value={field.state.value}
                  options={[["logical_entity", "Logical Entity"], ["dimensional_entity", "Dimensional Entity"]]}
                  onChange={(value) => field.handleChange(value as MappingEntityType)}
                />}
              </form.Field>
              <form.Field name="targetObjectId">
                {(field) => <SelectField
                  label="Target Object"
                  value={field.state.value}
                  options={targets.map((target) => [
                    String(target.object_id),
                    `${target.object_schema}.${target.object_name} · ${target.system_code}`,
                  ])}
                  onChange={field.handleChange}
                />}
              </form.Field>
              <form.Field name="sourceSystemId">
                {(field) => <SelectField
                  label="Source System"
                  value={field.state.value}
                  options={sourceSystems.map((system) => [
                    String(system.system_id),
                    `${system.system_name} (${system.system_code})`,
                  ])}
                  onChange={field.handleChange}
                />}
              </form.Field>
              <form.Field name="operation">
                {(field) => <SelectField
                  label="Mapping operation"
                  value={field.state.value}
                  options={[["build", "Build"], ["extend", "Extend"]]}
                  onChange={(value) => field.handleChange(value as "build" | "extend")}
                />}
              </form.Field>
              <form.Field name="artifactType">
                {(field) => <SelectField
                  label="Artifact type"
                  value={field.state.value}
                  options={[
                    ["sql_file", "SQL file"],
                    ["python_file", "Python file"],
                    ["python_notebook", "Python notebook"],
                  ]}
                  onChange={(value) => field.handleChange(value as typeof field.state.value)}
                />}
              </form.Field>
              <form.Field name="executionMode">
                {(field) => <SelectField
                  label="Execution mode"
                  value={field.state.value}
                  options={compatibleExecutionModes.map((mode) => [
                    mode,
                    WORKFLOW_EXECUTION_MODE_NAMES[mode],
                  ])}
                  onChange={(value) => field.handleChange(value as ExecutionMode)}
                />}
              </form.Field>
            </div>
          </section>

          <form.Field name="objectOutputTemplateId">
            {(objectField) => (
              <form.Field name="attributeOutputTemplateId">
                {(attributeField) => <MappingOutputTemplateSelection
                  mappingObjects={outputTemplatesQuery.data?.mappingObjects ?? []}
                  mappingAttributes={outputTemplatesQuery.data?.mappingAttributes ?? []}
                  objectValue={objectField.state.value}
                  attributeValue={attributeField.state.value}
                  disabled={outputTemplatesQuery.isPending || outputTemplatesQuery.isError}
                  onObjectChange={objectField.handleChange}
                  onAttributeChange={attributeField.handleChange}
                />}
              </form.Field>
            )}
          </form.Field>

          <section className="agent-run-configuration" aria-labelledby="mapping-agent-heading">
            <header>
              <strong id="mapping-agent-heading">Agent configuration</strong>
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

          {scopeQuery.isPending ? <p className="surface-state compact" aria-busy="true">Loading active Scope…</p> : null}
          {scopeQuery.isError ? <p className="inline-error" role="alert">Active Scope could not be loaded.</p> : null}
          {outputTemplatesQuery.isPending ? <p className="surface-state compact" aria-busy="true">Loading active Output Templates…</p> : null}
          {outputTemplatesQuery.isError ? <p className="inline-error" role="alert">Active Output Templates could not be loaded. Free-form remains available.</p> : null}
          {capabilitiesQuery.isError ? <p className="inline-error" role="alert">Agent options could not be loaded.</p> : null}
          {capabilities && !agentSelectionValid ? <p className="inline-error" role="alert">No compatible agent configuration is available.</p> : null}
          {scopeQuery.data && targets.length === 0 ? <p className="inline-error" role="alert">No eligible target Objects are available for this Entity type.</p> : null}
          {revisionChanged ? <p className="inline-error" role="alert">The Model changed. Close this dialog and refresh before creating the run.</p> : null}
          {runMutation.isError ? (
            <p className="inline-error" role="alert">
              {mappingRunError(runMutation.error, pendingStart !== null)}
            </p>
          ) : null}

          <footer className="dialog-actions">
            <p>The backend revalidates eligibility, Output Templates, Model revision, agent options, App permission, and Tenant Lock.</p>
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
                    || capabilitiesQuery.isPending
                    || capabilitiesQuery.isError
                    || outputTemplatesQuery.isPending
                    || revisionChanged
                    || !targetSelectionValid
                    || !sourceSystemSelectionValid
                    || !objectOutputTemplateSelectionValid
                    || !attributeOutputTemplateSelectionValid
                    || !agentSelectionValid
                  ))
                }
              >
                {runMutation.isPending
                  ? pendingStart ? "Starting…" : "Creating and starting…"
                  : pendingStart ? "Retry start" : "Create and run Mapping"}
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

function mappingRunError(error: Error, runWasCreated: boolean): string {
  if (runWasCreated && isTenantWorkflowConflict(error)) {
    return TENANT_WORKFLOW_CONFLICT_MESSAGE;
  }
  if (runWasCreated) {
    return "The Mapping run remains queued because it could not be started.";
  }
  if (error instanceof ApiError && error.status === 403) {
    return "You no longer have permission or the required Tenant Lock to run Mapping.";
  }
  if (error instanceof ApiError && error.status === 409) {
    return "The Model or Mapping state changed. Refresh before creating another run.";
  }
  return "The Mapping run could not be created or started.";
}
