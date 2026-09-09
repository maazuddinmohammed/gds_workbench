import { useEffect, useMemo, useRef, useState } from "react";
import { useForm, useStore } from "@tanstack/react-form";
import { useMutation, useQuery } from "@tanstack/react-query";

import { ApiError } from "../../core/http";
import { SelectField } from "../../shared/ui";
import type { ModelDetail } from "../models/api";
import {
  findAgentExecutionProfile,
  listCompatibleExecutionModes,
  reasoningEffortDisplayName,
  resolveAgentProfileSelection,
  resolveDefaultAgent,
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
  loadAllMappingDependencies,
  loadAllMappingTargets,
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
  const createAttempt = useRef<{ fingerprint: string; key: string } | null>(null);
  const [pendingStart, setPendingStart] = useState<PendingMappingStart | null>(null);
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
      executionMode: "tool_assisted" as ExecutionMode,
      objectOutputTemplateId: "",
      attributeOutputTemplateId: "",
      modelCode: model.default_agent_model_code ?? "",
      reasoningEffortCode: model.default_reasoning_effort_code ?? "",
    },
    onSubmit: ({ value }) => {
      if (pendingStart) {
        runMutation.mutate({ kind: "retry", ...pendingStart });
        return;
      }
      if (!agentSelectionValid) return;
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
          agent,
          prompt_overrides: {},
          mapping_operation: value.operation,
          mapping_coverage_mode: "selected_targets",
          mapping_source_system_id: sourceSystemId,
          mapping_object_output_template_id: objectOutputTemplateId,
          mapping_attribute_output_template_id: attributeOutputTemplateId,
        },
      });
    },
  });
  const values = useStore(form.store, (state) => state.values);
  const targetsQuery = useQuery({
    queryKey: mappingQueryKeys.runTargets(tenantId, model.model_id, values.entityType),
    queryFn: () => loadAllMappingTargets(api, tenantId, model.model_id, values.entityType),
  });
  const dependenciesQuery = useQuery({
    queryKey: mappingQueryKeys.runSystems(tenantId, model.model_id, values.entityType),
    queryFn: () => loadAllMappingDependencies(api, tenantId, model.model_id, values.entityType),
  });
  const targets = useMemo(() => targetsQuery.data?.items ?? [], [targetsQuery.data?.items]);
  const sourceSystems = useMemo(() => {
    const byId = new Map<number, { system_id: number; system_code: string; system_name: string }>();
    for (const item of dependenciesQuery.data?.items ?? []) {
      if (item.status !== "active") continue;
      byId.set(item.source_system.system_id, {
        system_id: item.source_system.system_id,
        system_code: item.source_system.system_code,
        system_name: item.source_system.system_name,
      });
    }
    return [...byId.values()].sort((left, right) => left.system_code.localeCompare(right.system_code));
  }, [dependenciesQuery.data?.items]);
  const capabilities = capabilitiesQuery.data;
  const compatibleExecutionModes = capabilities
    ? listCompatibleExecutionModes(capabilities)
    : [];
  const compatibleModels = capabilities?.models.filter((candidate) => (
    findAgentExecutionProfile(candidate, values.executionMode) !== undefined
  )) ?? [];
  const selectedModel = compatibleModels.find((candidate) => candidate.code === values.modelCode);
  const selectedProfile = selectedModel
    ? findAgentExecutionProfile(selectedModel, values.executionMode)
    : undefined;
  const compatibleReasoning = capabilities?.reasoning_efforts.filter((effort) => (
    selectedProfile?.reasoning_effort_codes.includes(effort.code)
  )) ?? [];
  const targetId = Number(values.targetObjectId);
  const sourceSystemId = Number(values.sourceSystemId);
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
  const agent = capabilities ? resolveDefaultAgent(capabilities, values.executionMode, {
    modelCode: values.modelCode,
    reasoningEffortCode: values.reasoningEffortCode,
    maxTurns: model.default_max_turns,
    validationRetryCount: model.default_validation_retry_count,
  }) : null;
  const agentSelectionValid = agent !== null
    && compatibleExecutionModes.includes(values.executionMode)
    && agent.model_code === values.modelCode
    && agent.reasoning_effort_code === values.reasoningEffortCode;
  const revisionChanged = (
    targetsQuery.data !== undefined
    && targetsQuery.data.modelRevision !== model.model_revision
  ) || (
    dependenciesQuery.data !== undefined
    && dependenciesQuery.data.modelRevision !== model.model_revision
  );
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
      const fingerprint = JSON.stringify(command);
      if (createAttempt.current?.fingerprint !== fingerprint) {
        createAttempt.current = { fingerprint, key: globalThis.crypto.randomUUID() };
      }
      const result = await api.createWorkflowRun(
        tenantId,
        model.model_id,
        command,
        createAttempt.current.key,
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
      modelCode: values.modelCode,
      reasoningEffortCode: values.reasoningEffortCode,
    });
    if (!resolved) return;
    if (values.executionMode !== resolved.executionMode) {
      form.setFieldValue("executionMode", resolved.executionMode);
    }
    if (values.modelCode !== resolved.modelCode) {
      form.setFieldValue("modelCode", resolved.modelCode);
    }
    if (values.reasoningEffortCode !== resolved.reasoningEffortCode) {
      form.setFieldValue("reasoningEffortCode", resolved.reasoningEffortCode);
    }
  }, [
    capabilities,
    form,
    values.executionMode,
    values.modelCode,
    values.reasoningEffortCode,
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
                  disabled={outputTemplatesQuery.isPending || outputTemplatesQuery.isError || runMutation.isPending || pendingStart !== null}
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
            <fieldset className="agent-run-grid agent-run-grid-two" disabled={runMutation.isPending || pendingStart !== null}>
              <legend className="sr-only">Model and reasoning</legend>
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
            </fieldset>
          </section>

          {targetsQuery.isPending || dependenciesQuery.isPending ? <p className="surface-state compact" aria-busy="true">Loading Mapping bindings…</p> : null}
          {targetsQuery.isError || dependenciesQuery.isError ? <p className="inline-error" role="alert">Mapping bindings could not be loaded.</p> : null}
          {outputTemplatesQuery.isPending ? <p className="surface-state compact" aria-busy="true">Loading active Output Templates…</p> : null}
          {outputTemplatesQuery.isError ? <p className="inline-error" role="alert">Custom Output Templates could not be loaded. Global defaults remain available.</p> : null}
          {capabilitiesQuery.isError ? <p className="inline-error" role="alert">Agent options could not be loaded.</p> : null}
          {capabilities && !agentSelectionValid ? <p className="inline-error" role="alert">No compatible agent configuration is available.</p> : null}
          {targetsQuery.data && targets.length === 0 ? <p className="inline-error" role="alert">No eligible target Objects are available for this Entity type.</p> : null}
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
                    targetsQuery.isPending
                    || targetsQuery.isError
                    || dependenciesQuery.isPending
                    || dependenciesQuery.isError
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
