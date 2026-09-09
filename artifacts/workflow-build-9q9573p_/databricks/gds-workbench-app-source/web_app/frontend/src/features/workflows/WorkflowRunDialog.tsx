import type { ModelInputScopeApi, ModelInputScopeDetail } from "../model_input_scope/api";
import { EnrichmentAttributeSelection, type EnrichmentAttributeSelectionValue } from "../metadata_enrichment/EnrichmentAttributeSelection";
import { useEffect, useRef, useState } from "react";
import { useForm, useStore } from "@tanstack/react-form";
import { useMutation, useQuery } from "@tanstack/react-query";

import { ApiError } from "../../core/http";
import type { ModelDetail } from "../models/api";
import type { CreateWorkflowRunCommand } from "./api";
import {
  findAgentExecutionProfile,
  listCompatibleExecutionModes,
  loadAllBronzeScope,
  loadAllDimensionalScope,
  loadAllEnrichmentScope,
  reasoningEffortDisplayName,
  resolveAgentProfileSelection,
  resolveDefaultAgent,
  WORKFLOW_EXECUTION_MODE_NAMES,
  workflowCreationQueryKeys,
  type WorkflowCreationApi,
} from "./api";
import {
  isTenantWorkflowConflict,
  TENANT_WORKFLOW_CONFLICT_MESSAGE,
} from "./presentation";

type AnalysisRunKind = "inference" | "validation";
type AgenticWorkflow = "analysis" | "conceptual" | "logical" | "dimensional" | "metadata_enrichment";
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
  enrichmentObject,
  enrichmentTarget,
  readEnrichmentObject,
  initialSelectedIds = [],
  executeValidationCreated,
  onClose,
  onCreated,
}: {
  api: WorkflowCreationApi;
  tenantId: number;
  model: ModelDetail;
  kind: AnalysisRunKind;
  workflow?: AgenticWorkflow;
  enrichmentObject?: ModelInputScopeDetail;
  enrichmentTarget?: "object" | "attribute";
  readEnrichmentObject?: ModelInputScopeApi["readModelInputScopeObject"];
  initialSelectedIds?: number[];
  executeCreated?: (
    workflowRunId: number,
    executionMode: WorkflowExecutionMode,
  ) => Promise<void>;
  executeValidationCreated?: (workflowRunId: number) => Promise<void>;
  onClose: () => void;
  onCreated: (workflowRunId: number) => Promise<void>;
}) {
  const dialog = useRef<HTMLElement>(null);
  const createAttempt = useRef<{ fingerprint: string; key: string } | null>(null);
  const closeButton = useRef<HTMLButtonElement>(null);
  const [pendingStart, setPendingStart] = useState<PendingWorkflowStart | null>(null);
  const isEnrichment = workflow === "metadata_enrichment";
  const isAttributeEnrichment = isEnrichment && (enrichmentTarget === "attribute" || enrichmentObject !== undefined);
  const [attributeSelection, setAttributeSelection] = useState<EnrichmentAttributeSelectionValue>({ targets: [], ready: false });
  const isDimensional = workflow === "dimensional";
  const authoringWorkflowName = isEnrichment ? "Metadata enrichment" : workflow === "conceptual"
    ? "Conceptual"
    : workflow === "logical"
      ? "Logical"
      : "Dimensional";
  const workflowName = workflow === "analysis" ? "Analysis" : authoringWorkflowName;
  const scopeZoneName = isEnrichment ? "Source and Bronze" : isDimensional ? "Silver" : "Bronze";
  const scopeQuery = useQuery({
    queryKey: isEnrichment
      ? workflowCreationQueryKeys.enrichmentScope(tenantId, model.model_id)
      : isDimensional
      ? workflowCreationQueryKeys.dimensionalScope(tenantId, model.model_id)
      : workflowCreationQueryKeys.bronzeScope(tenantId, model.model_id),
    queryFn: () => isEnrichment
      ? loadAllEnrichmentScope(api, tenantId, model.model_id)
      : isDimensional
      ? loadAllDimensionalScope(api, tenantId, model.model_id)
      : loadAllBronzeScope(api, tenantId, model.model_id),
  });
  const scopeRows = enrichmentObject
    ? (enrichmentObject.is_locked || enrichmentObject.source_tenant_id !== tenantId ? [] : enrichmentObject.attributes
      .filter((item) => item.is_active && !item.is_locked && /^[0-9a-f]{64}$/.test(item.review_revision ?? ""))
      .map((item) => ({ id: item.attribute_id, objectId: enrichmentObject.object_id, attributeId: item.attribute_id as number | null,
        name: item.attribute_name, context: `${enrichmentObject.object_schema}.${enrichmentObject.object_name}`, revision: item.review_revision! })))
    : (scopeQuery.data?.items ?? []).filter((item) => !isEnrichment || (!item.is_locked && item.source_tenant_id === tenantId && /^[0-9a-f]{64}$/.test(item.review_revision ?? "")))
      .map((item) => ({ id: item.object_id, objectId: item.object_id, attributeId: null as number | null, name: item.object_name,
        context: isEnrichment ? `${item.object_schema ?? ""} · ${item.zone_code}` : `${item.system_code} · ${item.source_tenant_code}`, revision: item.review_revision ?? "" }));
  const recordName = isAttributeEnrichment ? "Attributes" : "Objects";
  const capabilitiesQuery = useQuery({
    queryKey: workflowCreationQueryKeys.capabilities,
    queryFn: api.readAgentCapabilities,
    enabled: kind === "inference",
  });
  const form = useForm({
    defaultValues: {
      scopeMode: (initialSelectedIds.length ? "selected" : "all") as "all" | "selected",
      selectedObjectIds: initialSelectedIds,
      executionMode: (isEnrichment ? "one_shot" : "tool_assisted") as "one_shot" | "tool_assisted",
      requestedBatchId: "",
      modelCode: model.default_agent_model_code ?? "",
      reasoningEffortCode: model.default_reasoning_effort_code ?? "",
    },
    onSubmit: ({ value }) => {
      if (pendingStart) {
        runMutation.mutate({ kind: "retry", ...pendingStart });
        return;
      }
      if (kind === "inference" && !agentSelectionValid) return;
      if (isAttributeEnrichment && (!attributeSelection.ready || scopeQuery.isFetching || scopeQuery.isError || revisionChanged)) return;
      const selectedRows = value.scopeMode === "all" ? scopeRows : scopeRows.filter((item) => value.selectedObjectIds.includes(item.id));
      const descriptionTargets = isAttributeEnrichment ? attributeSelection.targets
        : selectedRows.map((item) => ({ object_id: item.objectId, attribute_id: item.attributeId, expected_revision: item.revision }));
      const selectedObjectIds = [...new Set(isAttributeEnrichment
        ? descriptionTargets.map((target) => target.object_id) : selectedRows.map((item) => item.objectId))];
      if (isEnrichment && (selectedObjectIds.length > 200 || selectedObjectIds.length === 0
        || value.executionMode !== "one_shot" || selectedObjectIds.some((id) =>
          !scopeQuery.data?.items.some((item) => item.object_id === id)))) return;
      runMutation.mutate({
        kind: "create",
        command: {
          expected_model_revision: model.model_revision,
          model_workflow: workflow,
          workflow_execution_mode: kind === "inference" ? value.executionMode : null,
          selected_object_ids: selectedObjectIds,
          requested_batch_id: isEnrichment ? null : value.requestedBatchId.trim() || null,
          agent: kind === "inference" ? agent : null,
          prompt_overrides: {},
          ...(isEnrichment ? { description_targets: descriptionTargets } : {}),
        },
      });
    },
  });
  const scopeMode = useStore(form.store, (state) => state.values.scopeMode);
  const selectedObjectIds = useStore(form.store, (state) => state.values.selectedObjectIds);
  const executionMode = useStore(form.store, (state) => state.values.executionMode);
  const requestedBatchId = useStore(form.store, (state) => state.values.requestedBatchId);
  const modelCode = useStore(form.store, (state) => state.values.modelCode);
  const reasoningEffortCode = useStore(form.store, (state) => state.values.reasoningEffortCode);
  const effectiveRows = scopeMode === "all" ? scopeRows : scopeRows.filter((item) => selectedObjectIds.includes(item.id));
  const effectiveObjects = scopeQuery.data?.items.filter((item) => effectiveRows.some((row) => row.objectId === item.object_id)) ?? [];
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
  const compatibleExecutionModes = capabilities
    ? listCompatibleExecutionModes(capabilities).filter((mode) => !isEnrichment || mode === "one_shot")
    : [];
  const compatibleModels = capabilities?.models.filter((candidate) => (
    findAgentExecutionProfile(candidate, executionMode) !== undefined
  )) ?? [];
  const selectedModel = compatibleModels.find((candidate) => candidate.code === modelCode);
  const selectedProfile = selectedModel
    ? findAgentExecutionProfile(selectedModel, executionMode)
    : undefined;
  const compatibleReasoning = capabilities?.reasoning_efforts.filter((effort) => (
    selectedProfile?.reasoning_effort_codes.includes(effort.code)
  )) ?? [];
  const agent = capabilities ? resolveDefaultAgent(capabilities, executionMode, {
    modelCode,
    reasoningEffortCode,
    maxTurns: model.default_max_turns,
    validationRetryCount: model.default_validation_retry_count,
  }) : null;
  const agentSelectionValid = agent !== null
    && compatibleExecutionModes.includes(executionMode)
    && agent.model_code === modelCode && agent.reasoning_effort_code === reasoningEffortCode;

  useEffect(() => {
    const returnFocus = document.activeElement;
    closeButton.current?.focus();
    return () => { if (returnFocus instanceof HTMLElement) returnFocus.focus(); };
  }, []);
  useEffect(() => {
    if (!capabilities || kind !== "inference") return;
    const resolved = resolveAgentProfileSelection(capabilities, executionMode, {
      modelCode,
      reasoningEffortCode,
    }, isEnrichment ? ["one_shot"] : undefined);
    if (!resolved) return;
    if (executionMode !== resolved.executionMode) {
      form.setFieldValue("executionMode", resolved.executionMode);
    }
    if (modelCode !== resolved.modelCode) form.setFieldValue("modelCode", resolved.modelCode);
    if (reasoningEffortCode !== resolved.reasoningEffortCode) {
      form.setFieldValue("reasoningEffortCode", resolved.reasoningEffortCode);
    }
  }, [
    capabilities,
    executionMode,
    form,
    kind,
    isEnrichment,
    modelCode,
    reasoningEffortCode,
  ]);
  const title = isEnrichment ? `Enrich ${recordName.toLowerCase()}` : workflow === "analysis"
    ? `Configure Analysis ${kind}`
    : `Configure ${authoringWorkflowName} run`;

  return (
    <div className="dialog-scrim" role="presentation">
      <section
        ref={dialog}
        className="run-configuration-dialog"
        role="dialog"
        aria-modal="true"
        aria-labelledby="workflow-run-dialog-heading"
        onKeyDown={(event) => {
          if (event.key === "Escape" && !runMutation.isPending) onClose();
          if (event.key !== "Tab") return;
          const focusable = [...(dialog.current?.querySelectorAll<HTMLElement>("*") ?? [])]
            .filter((element) => element.matches(
              "button:not(:disabled), input:not(:disabled), select:not(:disabled), [tabindex='0']",
            ));
          const first = focusable[0];
          const last = focusable.at(-1);
          if (event.shiftKey && document.activeElement === first) {
            event.preventDefault(); last?.focus();
          } else if (!event.shiftKey && document.activeElement === last) {
            event.preventDefault(); first?.focus();
          }
        }}
      >
        <header className="drawer-header">
          <div>
            {!isEnrichment ? <small>{workflow !== "analysis"
              ? "Agentic authoring"
              : kind === "inference"
                ? "Agentic inference"
                : "Deterministic validation"}</small> : null}
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
          {enrichmentObject ? <p className="run-kind-note">{enrichmentObject.object_schema}.{enrichmentObject.object_name}</p> : null}
          {kind === "inference" ? (
            <section className="agent-run-configuration" aria-labelledby="agent-run-heading">
              <header className={isEnrichment ? "sr-only" : undefined}>
                <strong id="agent-run-heading">Run configuration</strong>
              </header>
              <fieldset className={`agent-run-grid${isEnrichment ? " agent-run-grid-two" : ""}`} disabled={runMutation.isPending || pendingStart !== null}>
                <legend className="sr-only">Run configuration</legend>
                {isEnrichment ? null : <form.Field name="executionMode">
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
                </form.Field>}
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
              </fieldset>
            </section>
          ) : (
            <p className="run-kind-note">
              Pending relationships are validated with deterministic queries. Agent settings are not used.
            </p>
          )}

          {isAttributeEnrichment ? scopeQuery.isPending ? <p className="surface-state compact" aria-busy="true">Loading active Scope…</p>
            : scopeQuery.isError ? <p className="inline-error" role="alert">Active Scope could not be loaded. Close and refresh to retry.</p>
              : readEnrichmentObject && scopeQuery.data ? <EnrichmentAttributeSelection
                objects={scopeQuery.data.items} tenantId={tenantId} modelId={model.model_id}
                readObject={readEnrichmentObject} {...(enrichmentObject ? { initialObject: enrichmentObject } : {})}
                initialSelectedIds={initialSelectedIds} disabled={runMutation.isPending || pendingStart !== null || scopeQuery.isFetching || revisionChanged}
                onChange={setAttributeSelection} />
                : <p className="inline-error" role="alert">Attribute selection is unavailable.</p>
            : <><fieldset className="scope-mode-options" disabled={runMutation.isPending || pendingStart !== null}>
            <legend>{recordName}</legend>
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
                      <strong>All {isEnrichment ? "unlocked " : ""}{recordName}</strong>
                      {!isEnrichment ? <small>Every eligible active {scopeZoneName} Object in Scope</small> : null}
                    </span>
                  </label>
                  <label>
                    <input
                      type="radio"
                      name={field.name}
                      checked={field.state.value === "selected"}
                      onChange={() => field.handleChange("selected")}
                    />
                    <span><strong>Selected {recordName}</strong></span>
                  </label>
                </>
              )}
            </form.Field>
          </fieldset>

          <section className="run-object-selection" aria-labelledby="workflow-run-scope-heading">
            <header>
              <strong id="workflow-run-scope-heading">{isEnrichment ? `Unlocked ${recordName}` : `Active ${scopeZoneName} Scope`}</strong>
              <span>{effectiveRows.length} selected</span>
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
                    {scopeRows.map((item) => (
                      <label key={item.id}>
                        <input
                          type="checkbox"
                          checked={scopeMode === "all" || field.state.value.includes(item.id)}
                          disabled={runMutation.isPending || pendingStart !== null || scopeMode === "all" || (isEnrichment && !enrichmentObject && field.state.value.length >= 200 && !field.state.value.includes(item.id))}
                          onChange={(event) => field.handleChange(event.target.checked
                            ? [...field.state.value, item.id]
                            : field.state.value.filter((id) => id !== item.id))}
                        />
                        <span>
                          <strong>{item.name}</strong>
                          <small>{item.context}</small>
                        </span>
                      </label>
                    ))}
                  </div>
                )}
              </form.Field>
            )}
          </section></>}


          {!isEnrichment ? <form.Field name="requestedBatchId">
            {(field) => (
              <label className="batch-input">
                <span>Batch ID (optional)</span>
                <input
                  aria-label="Batch ID (optional)"
                  disabled={runMutation.isPending || pendingStart !== null}
                  value={field.state.value}
                  onBlur={field.handleBlur}
                  onChange={(event) => field.handleChange(event.target.value)}
                />
                <small>A Batch ID requires selected Objects from one System.</small>
              </label>
            )}
          </form.Field> : null}
          {isEnrichment && !isAttributeEnrichment && effectiveObjects.length > 200 ? (
            <p className="inline-error" role="alert">Select up to 200 Objects. Choose Selected Objects to narrow this run.</p>
          ) : null}

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
              {isEnrichment && runMutation.error instanceof ApiError && runMutation.error.code === "metadata_revision_conflict"
                ? "Metadata changed or was locked. Close this dialog, refresh, and try again."
                : pendingStart && isTenantWorkflowConflict(runMutation.error)
                ? TENANT_WORKFLOW_CONFLICT_MESSAGE
                : pendingStart
                  ? `The ${workflowName} run remains queued because it could not be started.`
                  : workflow !== "analysis"
                    ? `The ${authoringWorkflowName} run could not be created.`
                    : "The Analysis run could not be created."}
            </p>
          ) : null}

          <footer className="dialog-actions">
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
                    || (isAttributeEnrichment ? !attributeSelection.ready || scopeQuery.isFetching : effectiveRows.length === 0)
                    || (isEnrichment && !isAttributeEnrichment && effectiveObjects.length > 200)
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
                    : isEnrichment ? `Run ${isAttributeEnrichment ? "attribute" : "object"} enrichment` : workflow !== "analysis"
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
