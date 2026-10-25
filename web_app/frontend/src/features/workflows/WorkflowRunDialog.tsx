import type { LogicalTransport, LogicalEntity } from "../logical/api";
import type { ProjectInputScopeApi, ProjectInputScopeDetail } from "../project_input_scope/api";
import { EnrichmentAttributeSelection, type EnrichmentAttributeSelectionValue } from "../metadata_enrichment/EnrichmentAttributeSelection";
import type { MetadataEnrichmentTransport, ReviewEnrichmentCommand, ReviewEnrichmentResult } from "../metadata_enrichment/api";
import { useEffect, useRef, useState } from "react";
import { useForm, useStore } from "@tanstack/react-form";
import { useMutation, useQuery } from "@tanstack/react-query";

import { ApiError } from "../../core/http";
import { SelectAllCheckbox } from "../../shared/ui";
import { useWorkflowRunSubmission } from "./useWorkflowRunSubmission";
import type { ProjectDetail } from "../projects/api";
import type { CreateWorkflowRunCommand } from "./api";
import {
  findAgentExecutionProfile,
  listCompatibleExecutionModes,
  loadWorkflowScope,
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
type AgenticWorkflow = "analysis" | "subject_area" | "logical" | "dimensional" | "metadata_enrichment";
type WorkflowExecutionMode = NonNullable<CreateWorkflowRunCommand["workflow_execution_mode"]>;
export function WorkflowRunDialog({
  api,
  tenantId,
  project,
  kind,
  workflow = "analysis",
  executeCreated,
  enrichmentObject,
  logicalEntitySource,
  enrichmentTarget,
  readEnrichmentObject,
  reviewEnrichment,
  onImported,
  initialSelectedIds = [],
  executeValidationCreated,
  onClose,
  onCreated,
}: {
  api: WorkflowCreationApi;
  tenantId: number;
  project: ProjectDetail;
  kind: AnalysisRunKind;
  workflow?: AgenticWorkflow;
  enrichmentObject?: ProjectInputScopeDetail;
  logicalEntitySource?: Pick<LogicalTransport, "listLogicalEntities">;
  enrichmentTarget?: "object" | "attribute";
  readEnrichmentObject?: ProjectInputScopeApi["readProjectInputScopeObject"];
  reviewEnrichment?: MetadataEnrichmentTransport["reviewEnrichment"];
  onImported?: (result: ReviewEnrichmentResult) => Promise<void>;
  initialSelectedIds?: number[];
  executeCreated?: (
    workflowRunId: number,
    executionMode: WorkflowExecutionMode,
    expectedProjectRevision: number,
  ) => Promise<void>;
  executeValidationCreated?: (workflowRunId: number, expectedProjectRevision: number) => Promise<void>;
  onClose: () => void;
  onCreated: (workflowRunId: number) => Promise<void>;
}) {
  const dialog = useRef<HTMLElement>(null);
  const closeButton = useRef<HTMLButtonElement>(null);
  const isEnrichment = workflow === "metadata_enrichment";
  const [enrichmentMethod, setEnrichmentMethod] = useState<"agent" | "metadata">("agent");
  const [replaceDescriptions, setReplaceDescriptions] = useState(false);
  const [importRefreshRequired, setImportRefreshRequired] = useState(false);
  const pendingImport = useRef<{
    tenantId: number; projectId: number; projectRevision: number;
    command: ReviewEnrichmentCommand; key: string;
  } | null>(null);
  const isMetadataImport = isEnrichment && enrichmentMethod === "metadata";
  const importMutation = useMutation({
    mutationFn: async () => {
      const attempt = pendingImport.current;
      if (!attempt || !reviewEnrichment) throw new Error("Metadata import is unavailable.");
      const receipt = await reviewEnrichment(attempt.tenantId, attempt.projectId, attempt.projectRevision, attempt.command, attempt.key);
      const expected = new Set(attempt.command.records.map((row) => row.record_id));
      if (receipt.records.length !== expected.size || new Set(receipt.records.map((row) => row.record_id)).size !== expected.size
        || receipt.records.some((row) => !expected.has(row.record_id) || !/^[0-9a-f]{64}$/.test(row.review_revision))) {
        throw new Error("Import outcome unconfirmed.");
      }
      return receipt;
    },
    onSuccess: async (receipt) => {
      await onImported?.(receipt);
      pendingImport.current = null;
      onClose();
    },
    onError: (error) => {
      if (error instanceof ApiError && error.status < 500 && error.status !== 408) {
        pendingImport.current = null;
        setImportRefreshRequired(true);
      }
    },
  });
  const uncertainImport = importMutation.isError && pendingImport.current !== null;
  const isAttributeEnrichment = isEnrichment && (enrichmentTarget === "attribute" || enrichmentObject !== undefined);
  const [attributeSelection, setAttributeSelection] = useState<EnrichmentAttributeSelectionValue>({ targets: [], ready: false });
  const isDimensional = workflow === "dimensional";
  // Subject Areas group the whole Bronze Input Scope, so their runs have no picker.
  const isSubjectArea = workflow === "subject_area";
  const authoringWorkflowName = isEnrichment ? "Metadata enrichment" : isSubjectArea
    ? "Subject Areas"
    : workflow === "logical"
      ? "Logical"
      : "Dimensional";
  const workflowName = workflow === "analysis" ? "Analysis" : authoringWorkflowName;
  const scopeZoneName = isEnrichment ? "Source and Bronze" : isDimensional ? "Logical Entity" : "Bronze";
  const scopeQuery = useQuery({
    queryKey: isEnrichment
      ? workflowCreationQueryKeys.enrichmentScope(tenantId, project.project_id)
      : workflowCreationQueryKeys.bronzeScope(tenantId, project.project_id),
    enabled: !isDimensional,
    queryFn: () => loadWorkflowScope(
      api, tenantId, project.project_id, isEnrichment ? "enrichment" : "bronze",
    ),
  });
  const entityQuery = useQuery({
    queryKey: ["dimensional-logical-inputs", tenantId, project.project_id],
    enabled: isDimensional,
    queryFn: async () => {
      if (!logicalEntitySource) throw new Error("Logical Entity selection unavailable.");
      const items: LogicalEntity[] = [];
      const cursors = new Set<string>();
      let cursor: string | undefined;
      let projectRevision: number | undefined;
      for (;;) {
        const page = await logicalEntitySource.listLogicalEntities(tenantId, project.project_id, { status: "active" }, 200, cursor);
        if (projectRevision !== undefined && page.project_revision !== projectRevision) throw new Error("Project changed while loading Entities.");
        projectRevision = page.project_revision;
        items.push(...page.items);
        if (!page.next_cursor) return { items, projectRevision };
        if (cursors.has(page.next_cursor)) throw new Error("Entity cursor repeated.");
        cursors.add(page.next_cursor);
        cursor = page.next_cursor;
      }
    },
  });
  const selectionQuery = isDimensional ? entityQuery : scopeQuery;
  const scopeRows = isDimensional ? (entityQuery.data?.items ?? []).map((item) => ({ id: item.logical_entity_id, objectId: item.logical_entity_id, attributeId: null as number | null, name: item.logical_entity_name, context: item.logical_entity_schema_name, revision: "" })) : enrichmentObject
    ? (enrichmentObject.is_locked || enrichmentObject.source_tenant_id !== tenantId ? [] : enrichmentObject.attributes
      .filter((item) => item.is_active && !item.is_locked && /^[0-9a-f]{64}$/.test(item.review_revision ?? ""))
      .map((item) => ({ id: item.attribute_id, objectId: enrichmentObject.object_id, attributeId: item.attribute_id as number | null,
        name: item.attribute_name, context: `${enrichmentObject.object_schema}.${enrichmentObject.object_name}`, revision: item.review_revision! })))
    : (scopeQuery.data?.items ?? []).filter((item) => !isEnrichment || (!item.is_locked && item.source_tenant_id === tenantId && /^[0-9a-f]{64}$/.test(item.review_revision ?? "")))
      .map((item) => ({ id: item.object_id, objectId: item.object_id, attributeId: null as number | null, name: item.object_name,
        context: isEnrichment ? `${item.object_schema ?? ""} · ${item.zone_code}` : `${item.system_code} · ${item.source_tenant_code}`, revision: item.review_revision ?? "" }));
  const recordName = isAttributeEnrichment ? "Attributes" : isDimensional ? "Entities" : "Objects";
  const capabilitiesQuery = useQuery({
    queryKey: workflowCreationQueryKeys.capabilities,
    queryFn: api.readAgentCapabilities,
    enabled: kind === "inference" && !isMetadataImport,
  });
  const form = useForm({
    defaultValues: {
      scopeMode: (initialSelectedIds.length ? "selected" : "all") as "all" | "selected",
      selectedObjectIds: initialSelectedIds,
      executionMode: (isEnrichment ? "one_shot" : "tool_assisted") as "one_shot" | "tool_assisted",
      requestedBatchId: "",
      modelCode: project.default_agent_model_code ?? "",
      reasoningEffortCode: project.default_reasoning_effort_code ?? "",
    },
    onSubmit: ({ value }) => {
      if (submitting) return;
      if (isMetadataImport && pendingImport.current) {
        importMutation.mutate();
        return;
      }
      if (pendingStart) {
        runMutation.mutate(undefined);
        return;
      }
      if (!isMetadataImport && kind === "inference" && !agentSelectionValid) return;
      if (isAttributeEnrichment && (!attributeSelection.ready || scopeQuery.isFetching || scopeQuery.isError || revisionChanged)) return;
      const selectedRows = value.scopeMode === "all" ? scopeRows : scopeRows.filter((item) => value.selectedObjectIds.includes(item.id));
      const descriptionTargets = isAttributeEnrichment ? attributeSelection.targets
        : selectedRows.map((item) => ({ object_id: item.objectId, attribute_id: item.attributeId, expected_revision: item.revision }));
      const selectedObjectIds = [...new Set(isAttributeEnrichment
        ? descriptionTargets.map((target) => target.object_id) : selectedRows.map((item) => item.objectId))];
      if (isEnrichment && (selectedObjectIds.length === 0
        || value.executionMode !== "one_shot" || selectedObjectIds.some((id) =>
          !scopeQuery.data?.items.some((item) => item.object_id === id)))) return;
      if (isMetadataImport) {
        if (!reviewEnrichment || importRefreshRequired || revisionChanged || scopeQuery.isFetching
          || scopeQuery.isError || descriptionTargets.length === 0 || descriptionTargets.length > 200) return;
        pendingImport.current = {
          tenantId, projectId: project.project_id, projectRevision: project.project_revision,
          key: crypto.randomUUID(),
          command: {
            record_type: isAttributeEnrichment ? "attribute" : "object",
            action: replaceDescriptions ? "reimport" : "import",
            records: descriptionTargets.map((target) => ({
              record_id: target.attribute_id ?? target.object_id,
              expected_revision: target.expected_revision,
            })),
          },
        };
        importMutation.mutate();
        return;
      }
      runMutation.mutate({
        expected_project_revision: project.project_revision,
        project_workflow: workflow,
        workflow_execution_mode: kind === "inference" ? value.executionMode : null,
        selected_object_ids: isDimensional ? [] : selectedObjectIds,
        ...(isDimensional ? { selected_entity_ids: selectedObjectIds, modeled_entity_type: "logical_entity" as const } : {}),
        requested_batch_id: isEnrichment || isDimensional || isSubjectArea ? null : value.requestedBatchId.trim() || null,
        agent: kind === "inference" ? agent : null,
        prompt_overrides: {},
        ...(isEnrichment ? { description_targets: descriptionTargets } : {}),
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
  const revisionChanged = selectionQuery.data?.projectRevision !== undefined
    && selectionQuery.data.projectRevision !== project.project_revision;
  const { mutation: runMutation, pendingRunId: pendingStart } = useWorkflowRunSubmission({
    api,
    tenantId,
    projectId: project.project_id,
    execute: kind === "validation"
      ? executeValidationCreated && ((workflowRunId, command) => executeValidationCreated(
        workflowRunId, command.expected_project_revision,
      ))
      : executeCreated && ((workflowRunId, command) => {
        if (!command.workflow_execution_mode) throw new Error("Workflow execution mode is required.");
        return executeCreated(workflowRunId, command.workflow_execution_mode, command.expected_project_revision);
      }),
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
    maxTurns: project.default_max_turns,
    validationRetryCount: project.default_validation_retry_count,
  }) : null;
  const agentSelectionValid = agent !== null
    && compatibleExecutionModes.includes(executionMode)
    && agent.model_code === modelCode && agent.reasoning_effort_code === reasoningEffortCode;
  const importingCount = isAttributeEnrichment ? attributeSelection.targets.length : effectiveRows.length;
  const submitting = runMutation.isPending || importMutation.isPending;
  const selectionDisabled = submitting || pendingStart !== null || uncertainImport;

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
          if (event.key === "Escape" && !submitting && !uncertainImport) onClose();
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
            disabled={submitting || uncertainImport}
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
          {isEnrichment && reviewEnrichment ? <fieldset className="scope-mode-options" disabled={selectionDisabled}>
            <legend>Description source</legend>
            <label><input type="radio" name="enrichment-method" checked={!isMetadataImport}
              onChange={() => setEnrichmentMethod("agent")} /><span><strong>Generate with AI</strong></span></label>
            <label><input type="radio" name="enrichment-method" checked={isMetadataImport}
              onChange={() => setEnrichmentMethod("metadata")} /><span><strong>Import from Metadata</strong></span></label>
          </fieldset> : null}
          {isMetadataImport ? <div className="run-kind-note">
            <p>Copy registered descriptions into this Project. No AI is used. Empty Metadata descriptions are skipped; other enrichment fields stay unchanged.</p>
            <label><input type="checkbox" checked={replaceDescriptions} disabled={selectionDisabled}
              onChange={(event) => setReplaceDescriptions(event.target.checked)} /> Replace existing enrichment descriptions</label>
            <p>{replaceDescriptions ? "Import will replace saved descriptions for the selected records where Metadata has a description." : "Existing enrichment descriptions will be kept."}</p>
          </div> : kind === "inference" ? (
            <section className="agent-run-configuration" aria-labelledby="agent-run-heading">
              <header className={isEnrichment ? "sr-only" : undefined}>
                <strong id="agent-run-heading">Run configuration</strong>
              </header>
              <fieldset className={`agent-run-grid${isEnrichment ? " agent-run-grid-two" : ""}`} disabled={selectionDisabled}>
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
                objects={scopeQuery.data.items} tenantId={tenantId} projectId={project.project_id}
                readObject={readEnrichmentObject} {...(enrichmentObject ? { initialObject: enrichmentObject } : {})}
                initialSelectedIds={initialSelectedIds} disabled={selectionDisabled || scopeQuery.isFetching || revisionChanged}
                onChange={setAttributeSelection} />
                : <p className="inline-error" role="alert">Attribute selection is unavailable.</p>
            : isSubjectArea ? <section className="run-object-selection" aria-labelledby="workflow-run-scope-heading">
              <header>
                <strong id="workflow-run-scope-heading">Active Bronze Scope</strong>
                <span>{scopeRows.length} table{scopeRows.length === 1 ? "" : "s"}</span>
              </header>
              {scopeQuery.isPending ? <div className="surface-state compact" aria-busy="true">Loading active Scope…</div>
                : scopeQuery.isError ? <div className="surface-state is-error compact" role="alert">Active Scope could not be loaded.</div>
                  : <p className="run-kind-note">Subject Areas group every active Bronze table in the Input Scope, so this run always covers the whole Scope. Locked areas and locked tables stay as saved.</p>}
            </section>
            : <><fieldset className="scope-mode-options" disabled={selectionDisabled}>
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
                      {!isEnrichment ? <small>Every active {scopeZoneName}{isDimensional ? "" : " Object in Scope"}</small> : null}
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
            {selectionQuery.isPending ? (
              <div className="surface-state compact" aria-busy="true">Loading active Scope…</div>
            ) : selectionQuery.isError ? (
              <div className="surface-state is-error compact" role="alert">
                Active Scope could not be loaded.
              </div>
            ) : (
              <form.Field name="selectedObjectIds">
                {(field) => (
                  <div className="run-object-list">
                    <label className="run-selection-all">
                      <SelectAllCheckbox label={`Select all ${isEnrichment ? "unlocked " : ""}${recordName}`}
                        selectedCount={effectiveRows.length} totalCount={scopeRows.length}
                        disabled={selectionDisabled}
                        onChange={(checked) => {
                          form.setFieldValue("scopeMode", "selected");
                          field.handleChange(checked ? scopeRows.map((item) => item.id) : []);
                        }} />
                      <span>Select all {isEnrichment ? "unlocked " : ""}{recordName}</span>
                    </label>
                    {scopeRows.map((item) => (
                      <label key={item.id}>
                        <input
                          type="checkbox"
                          checked={scopeMode === "all" || field.state.value.includes(item.id)}
                          disabled={selectionDisabled || scopeMode === "all"}
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


          {!isEnrichment && !isDimensional && !isSubjectArea ? <form.Field name="requestedBatchId">
            {(field) => (
              <label className="batch-input">
                <span>Batch ID (optional)</span>
                <input
                  aria-label="Batch ID (optional)"
                  disabled={selectionDisabled}
                  value={field.state.value}
                  onBlur={field.handleBlur}
                  onChange={(event) => field.handleChange(event.target.value)}
                />
                <small>A Batch ID requires selected Objects from one System.</small>
              </label>
            )}
          </form.Field> : null}

          {!isMetadataImport && kind === "inference" && capabilitiesQuery.isError ? (
            <p className="inline-error" role="alert">Agent options could not be loaded.</p>
          ) : null}
          {!isMetadataImport && kind === "inference" && capabilitiesQuery.data && !agentSelectionValid ? (
            <p className="inline-error" role="alert">No compatible agent configuration is available.</p>
          ) : null}
          {batchIsIncoherent ? (
            <p className="inline-error" role="alert">
              Select Objects from one System when using a Batch ID.
            </p>
          ) : null}
          {revisionChanged ? (
            <p className="inline-error" role="alert">
              The Project changed. Close this dialog and refresh before creating the run.
            </p>
          ) : null}
          {isMetadataImport && importingCount > 200 ? <p className="inline-error" role="alert">Select up to 200 {recordName.toLowerCase()} per Metadata import.</p> : null}
          {isMetadataImport && importMutation.isError ? <p className="inline-error" role="alert">
            {uncertainImport ? "Import outcome is unconfirmed. Retry the same import to check its saved result."
              : isTenantWorkflowConflict(importMutation.error) ? TENANT_WORKFLOW_CONFLICT_MESSAGE
                : importMutation.error instanceof ApiError && importMutation.error.code === "invalid_request"
                  ? "Import was rejected. Check Metadata descriptions for unsupported characters or text over 2,000 UTF-8 bytes, then refresh and retry."
                : "Metadata import could not be completed. Close this dialog, refresh, and check selection and locks before retrying."}
          </p> : null}
          {!isMetadataImport && runMutation.isError ? (
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
                disabled={submitting || uncertainImport}
                onClick={onClose}
              >
                Cancel
              </button>
              <button
                className="button button-primary button-small"
                type="submit"
                disabled={
                  isMetadataImport ? submitting || importRefreshRequired || (!uncertainImport && (
                    !reviewEnrichment || selectionQuery.isPending || selectionQuery.isError || scopeQuery.isFetching
                    || revisionChanged || importingCount === 0 || importingCount > 200
                    || (isAttributeEnrichment && !attributeSelection.ready)
                  )) : runMutation.isPending
                  || (pendingStart === null && (
                    selectionQuery.isPending
                    || selectionQuery.isError
                    || (isAttributeEnrichment ? !attributeSelection.ready || scopeQuery.isFetching : effectiveRows.length === 0)
                    || batchIsIncoherent
                    || revisionChanged
                    || (kind === "inference" && (capabilitiesQuery.isPending || !agentSelectionValid))
                  ))
                }
              >
                {isMetadataImport ? importMutation.isPending ? "Importing…" : uncertainImport ? "Retry same import" : "Import descriptions"
                  : runMutation.isPending
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
