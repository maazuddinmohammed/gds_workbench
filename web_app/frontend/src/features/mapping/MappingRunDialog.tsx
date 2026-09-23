import { useEffect, useMemo, useRef, useState, type FormEvent } from "react";
import { useQuery } from "@tanstack/react-query";

import { ApiError } from "../../core/http";
import { trapDialogFocus, useDialogFocus } from "../../shared/dialog";
import { SelectField } from "../../shared/ui";
import type { ModelDetail } from "../models/api";
import { useWorkflowRunSubmission } from "../workflows/useWorkflowRunSubmission";
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
import { isTenantWorkflowConflict, TENANT_WORKFLOW_CONFLICT_MESSAGE } from "../workflows/presentation";
import {
  loadActiveMappingOutputTemplates,
  loadMappingGenerationTargets,
  mappingQueryKeys,
  type MappingApi,
  type MappingEntityType,
  type MappingGenerationTarget,
} from "./api";
import { MappingOutputTemplateSelection } from "./MappingOutputTemplateSelection";

type ExecutionMode = NonNullable<CreateWorkflowRunCommand["workflow_execution_mode"]>;
const targetKey = (target: MappingGenerationTarget) => `${target.object_id}:${target.source_system.system_id}`;

export function MappingRunDialog({ api, tenantId, model, entityType, onClose, onCompleted }: {
  api: MappingApi;
  tenantId: number;
  model: ModelDetail;
  entityType: MappingEntityType;
  onClose: () => void;
  onCompleted: (workflowRunId: number) => Promise<void>;
}) {
  const closeButton = useRef<HTMLButtonElement>(null);
  const attributeHeading = useRef<HTMLHeadingElement>(null);
  const returnToObject = useRef<string | null>(null);
  useDialogFocus(closeButton);
  const [scopeMode, setScopeMode] = useState<"all" | "selected">("all");
  const [system, setSystem] = useState("");
  const [search, setSearch] = useState("");
  const [excluded, setExcluded] = useState<Set<string>>(new Set());
  const [attributes, setAttributes] = useState<Record<string, number[]>>({});
  const [viewedKey, setViewedKey] = useState<string | null>(null);
  const [attributePage, setAttributePage] = useState(0);
  const [executionMode, setExecutionMode] = useState<ExecutionMode>("tool_assisted");
  const [modelCode, setModelCode] = useState(model.default_agent_model_code ?? "");
  const [reasoningCode, setReasoningCode] = useState(model.default_reasoning_effort_code ?? "");
  const [objectTemplate, setObjectTemplate] = useState("");
  const [attributeTemplate, setAttributeTemplate] = useState("");
  const capabilities = useQuery({
    queryKey: workflowCreationQueryKeys.capabilities,
    queryFn: api.readAgentCapabilities,
  });
  const targets = useQuery({
    queryKey: ["mapping-generation-targets", tenantId, model.model_id, entityType],
    queryFn: () => loadMappingGenerationTargets(api, tenantId, model.model_id, entityType),
  });
  const templates = useQuery({
    queryKey: mappingQueryKeys.outputTemplates(tenantId, model.model_id),
    queryFn: () => loadActiveMappingOutputTemplates(api, tenantId),
  });
  const rows = useMemo(() => targets.data?.items ?? [], [targets.data?.items]);
  const systems = [...new Map(rows.map((row) => [row.source_system.system_id, row.source_system])).values()];
  const scoped = rows.filter((row) => !system || String(row.source_system.system_id) === system);
  // Search only narrows the list; it never silently removes a selected target from the run.
  const visible = scoped.filter((row) => `${row.object_schema}.${row.object_name} ${row.entity_name}`
    .toLowerCase().includes(search.trim().toLowerCase()));
  const eligible = scoped.filter((row) => !row.is_locked && row.attributes.length > 0);
  const eligibleKeys = new Set(eligible.map(targetKey));
  const selected = eligible.filter((row) => scopeMode === "all" || !excluded.has(targetKey(row)));
  const selectedKeys = new Set(selected.map(targetKey));
  const selectedAttributes = (row: MappingGenerationTarget) => attributes[targetKey(row)]
    ?? row.attributes.filter((attribute) => !attribute.is_locked).map((attribute) => attribute.attribute_id);
  const attributeCount = selected.reduce((count, row) => count + selectedAttributes(row).length, 0);
  const preservedCount = selected.reduce((count, row) => count + row.attributes.length - selectedAttributes(row).length, 0);
  const incompleteCount = selected.filter((row) => row.attributes.some((attribute) =>
    !attribute.is_authored && !selectedAttributes(row).includes(attribute.attribute_id))).length;
  const viewed = rows.find((row) => targetKey(row) === viewedKey);
  const viewedAttributes = viewed ? selectedAttributes(viewed) : [];
  const revisionChanged = targets.data !== undefined && targets.data.modelRevision !== model.model_revision;
  const models = capabilities.data?.models.filter((item) => findAgentExecutionProfile(item, executionMode)) ?? [];
  const profile = models.find((item) => item.code === modelCode);
  const efforts = capabilities.data?.reasoning_efforts.filter((item) => profile
    && findAgentExecutionProfile(profile, executionMode)?.reasoning_effort_codes.includes(item.code)) ?? [];
  const agent = capabilities.data ? resolveDefaultAgent(capabilities.data, executionMode, {
    modelCode,
    reasoningEffortCode: reasoningCode,
    maxTurns: model.default_max_turns,
    validationRetryCount: model.default_validation_retry_count,
  }) : null;
  const agentValid = agent !== null && agent.model_code === modelCode && agent.reasoning_effort_code === reasoningCode;

  useEffect(() => {
    if (!capabilities.data) return;
    const resolved = resolveAgentProfileSelection(capabilities.data, executionMode, { modelCode, reasoningEffortCode: reasoningCode });
    if (!resolved) return;
    setExecutionMode(resolved.executionMode);
    setModelCode(resolved.modelCode);
    setReasoningCode(resolved.reasoningEffortCode);
  }, [capabilities.data, executionMode, modelCode, reasoningCode]);
  useEffect(() => {
    setAttributePage(0);
    if (viewedKey !== null) attributeHeading.current?.focus();
    else if (returnToObject.current !== null) document.getElementById(`mapping-choose-${returnToObject.current}`)?.focus();
  }, [viewedKey]);

  const { mutation, pendingRunId } = useWorkflowRunSubmission({
    api,
    tenantId,
    modelId: model.model_id,
    execute: (id, command) => api.executeMappingRun(
      tenantId, model.model_id, id, command.workflow_execution_mode!, command.expected_model_revision,
    ),
    onSuccess: async (id) => { await onCompleted(id); onClose(); },
  });
  const frozen = mutation.isPending || pendingRunId !== null;
  const selectionUnavailable = frozen || targets.isPending || targets.isError || revisionChanged;
  const viewedSelected = viewedKey !== null && selectedKeys.has(viewedKey);

  function submit(event: FormEvent) {
    event.preventDefault();
    if (mutation.isPending) return;
    if (pendingRunId !== null) { mutation.mutate(undefined); return; }
    if (selectionUnavailable || !selected.length || !agentValid || incompleteCount) return;
    mutation.mutate({
      expected_model_revision: model.model_revision,
      model_workflow: "mapping",
      workflow_execution_mode: executionMode,
      selected_object_ids: [...new Set(selected.map((row) => row.object_id))],
      requested_batch_id: null,
      agent,
      prompt_overrides: {},
      mapping_operation: "generate",
      mapping_coverage_mode: "selected_targets",
      mapping_targets: selected.map((row) => ({
        object_id: row.object_id,
        source_system_id: row.source_system.system_id,
        selected_attribute_ids: selectedAttributes(row),
      })),
      mapping_object_output_template_id: objectTemplate ? Number(objectTemplate) : null,
      mapping_attribute_output_template_id: attributeTemplate ? Number(attributeTemplate) : null,
    });
  }

  return <div className="dialog-scrim" role="presentation">
    <section
      className="run-configuration-dialog mapping-run-dialog"
      role="dialog" aria-modal="true" aria-labelledby="mapping-run-heading"
      onKeyDown={(event) => {
        trapDialogFocus(event);
        if (event.key === "Escape" && !mutation.isPending) onClose();
      }}
    >
      <header className="drawer-header">
        <div>
          <h2 id="mapping-run-heading">Generate mappings</h2>
          <p>{entityType === "logical_entity" ? "Logical → Silver" : "Dimensional → Gold"}</p>
        </div>
        <button ref={closeButton} className="panel-close" type="button" aria-label="Close Generate mappings"
          disabled={mutation.isPending} onClick={onClose}>×</button>
      </header>
      <form onSubmit={submit}>
        <fieldset className="agent-run-grid" disabled={frozen}>
          <legend className="sr-only">Agent configuration</legend>
          <SelectField label="Execution mode" value={executionMode}
            options={capabilities.data ? listCompatibleExecutionModes(capabilities.data).map((mode) => [mode, WORKFLOW_EXECUTION_MODE_NAMES[mode]]) : []}
            onChange={(value) => setExecutionMode(value as ExecutionMode)} />
          <SelectField label="Model" value={modelCode} options={models.map((item) => [item.code, item.name])} onChange={setModelCode} />
          <SelectField label="Reasoning effort" value={reasoningCode}
            options={efforts.map((item) => [item.code, reasoningEffortDisplayName(item)])} onChange={setReasoningCode} />
        </fieldset>
        <fieldset className="mapping-target-selection" disabled={selectionUnavailable}>
          <legend className="sr-only">Mapping selection</legend>
          {!viewed ? <div className="agent-run-grid mapping-scope-controls">
            <SelectField label="Source System" value={system}
              options={[["", "All input Systems"], ...systems.map((item) => [String(item.system_id), item.system_code] as [string, string])]}
              onChange={setSystem} />
          </div> : null}
          <fieldset className="scope-mode-options">
            <legend>Objects</legend>
            <label><input type="radio" name="mapping-object-scope" checked={scopeMode === "all"}
              onChange={() => setScopeMode("all")} /><span><strong>All unlocked Objects</strong></span></label>
            <label><input type="radio" name="mapping-object-scope" checked={scopeMode === "selected"}
              onChange={() => setScopeMode("selected")} /><span><strong>Selected Objects</strong></span></label>
          </fieldset>
          <div className="enrichment-selection-summary" aria-live="polite">
            <strong>{selected.length} Object–System mappings · {attributeCount} Attributes to generate</strong>
            <span>{preservedCount} Attributes preserved. Locked and unselected mappings stay unchanged.</span>
          </div>
          <p className="field-help">Each selected Object is assessed for every selected input System. Relevant sources produce complete mappings; unrelated Systems are reported without creating a mapping. Dependency order does not affect this selection.</p>
          {targets.isPending ? <div className="surface-state" aria-busy="true">Loading all Mapping targets and Attributes…</div>
            : targets.isError ? <p className="inline-error" role="alert">Targets could not be fully loaded.</p>
            : revisionChanged ? <p className="inline-error" role="alert">The Model changed. Close this dialog and refresh.</p>
            : viewed ? <section aria-label="Choose Object Attributes">
              <button className="text-action" type="button" onClick={() => setViewedKey(null)}>Back to Objects</button>
              <header className="enrichment-selection-header">
                <div>
                  <small>{viewed.object_schema} · {viewed.source_system.system_code}</small>
                  <h3 ref={attributeHeading} tabIndex={-1}>{viewed.object_name}</h3>
                </div>
                <span>{viewedSelected ? viewedAttributes.length : 0} selected · {viewed.attributes.length - (viewedSelected ? viewedAttributes.length : 0)} unselected · {viewed.attributes.filter((item) => item.is_locked).length} locked</span>
              </header>
              <div className="enrichment-selection-actions">
                <button type="button" className="button button-secondary button-small" disabled={!viewedSelected}
                  onClick={() => setAttributes((previous) => ({ ...previous, [targetKey(viewed)]: viewed.attributes.filter((item) => !item.is_locked).map((item) => item.attribute_id) }))}>
                  Select all unlocked Attributes
                </button>
                <button type="button" className="button button-secondary button-small" disabled={!viewedSelected}
                  onClick={() => setAttributes((previous) => ({ ...previous, [targetKey(viewed)]: [] }))}>
                  Clear Attribute selection
                </button>
              </div>
              <div className="workflow-table-scroll table-scroll">
                <table className="enrichment-selection-table" aria-label={`Attributes for ${viewed.object_name} from ${viewed.source_system.system_code}`}>
                  <thead><tr><th className="selection-cell"><span className="sr-only">Selected</span></th><th>Target Attribute</th><th>Modeled Attribute</th><th>Mapping</th></tr></thead>
                  <tbody>{viewed.attributes.slice(attributePage * 50, (attributePage + 1) * 50).map((attribute) => <tr key={attribute.attribute_id}>
                    <td className="selection-cell"><input type="checkbox"
                      aria-label={`Generate ${viewed.object_name}.${attribute.attribute_name} from ${viewed.source_system.system_code}`}
                      disabled={!viewedSelected || attribute.is_locked}
                      checked={viewedSelected && !attribute.is_locked && viewedAttributes.includes(attribute.attribute_id)}
                      onChange={(event) => setAttributes((previous) => ({
                        ...previous,
                        [targetKey(viewed)]: event.target.checked
                          ? [...viewedAttributes, attribute.attribute_id]
                          : viewedAttributes.filter((id) => id !== attribute.attribute_id),
                      }))} /></td>
                    <td>{attribute.attribute_name}</td><td>{attribute.modeled_attribute_name}</td>
                    <td>{attribute.is_locked ? "Locked · preserved" : attribute.is_authored ? "Existing" : "Missing"}</td>
                  </tr>)}</tbody>
                </table>
              </div>
              {viewed.attributes.length > 50 ? <div className="enrichment-pagination">
                <span>{attributePage * 50 + 1}–{Math.min((attributePage + 1) * 50, viewed.attributes.length)} of {viewed.attributes.length}</span>
                <button className="button button-secondary button-small" type="button" disabled={attributePage === 0}
                  onClick={() => setAttributePage((page) => page - 1)}>Previous Attributes</button>
                <button className="button button-secondary button-small" type="button" disabled={(attributePage + 1) * 50 >= viewed.attributes.length}
                  onClick={() => setAttributePage((page) => page + 1)}>Next Attributes</button>
              </div> : null}
            </section> : <>
              <div className="agent-run-grid mapping-scope-controls">
                <label><span>Find Objects</span><input type="search" value={search} placeholder="Schema, Object or Entity"
                  onChange={(event) => setSearch(event.target.value)} /></label>
              </div>
              {scopeMode === "selected" ? <div className="enrichment-selection-actions">
                <button type="button" className="button button-secondary button-small" disabled={!visible.some((row) => eligibleKeys.has(targetKey(row)))}
                  onClick={() => setExcluded((previous) => {
                    const next = new Set(previous);
                    for (const row of visible) if (eligibleKeys.has(targetKey(row))) next.delete(targetKey(row));
                    return next;
                  })}>Select all shown Objects</button>
                <button type="button" className="button button-secondary button-small" disabled={!selected.length}
                  onClick={() => setExcluded((previous) => new Set([...previous, ...eligibleKeys]))}>Clear Object selection</button>
              </div> : null}
              {search.trim() ? <p className="field-help">Showing {visible.length} of {scoped.length} mappings. Searching keeps your selections.</p> : null}
              <div className="workflow-table-scroll table-scroll">
                <table className="enrichment-selection-table" aria-label="Objects for Mapping">
                  <thead><tr><th className="selection-cell"><span className="sr-only">Selected</span></th><th>Schema</th><th>Object</th><th>Source System</th><th>Attributes</th><th>Locks</th></tr></thead>
                  <tbody>{visible.map((row) => {
                    const key = targetKey(row);
                    const checked = selectedKeys.has(key);
                    const chosenCount = checked ? selectedAttributes(row).length : 0;
                    return <tr key={key}>
                      <td className="selection-cell"><input type="checkbox"
                        aria-label={`Generate ${row.object_schema}.${row.object_name} from ${row.source_system.system_code}`}
                        checked={checked} disabled={scopeMode === "all" || !eligibleKeys.has(key)}
                        onChange={(event) => setExcluded((previous) => {
                          const next = new Set(previous);
                          if (event.target.checked) next.delete(key); else next.add(key);
                          return next;
                        })} /></td>
                      <td>{row.object_schema}</td>
                      <td><button type="button" className="text-action" id={`mapping-choose-${key}`}
                        aria-label={`Choose Attributes for ${row.object_name} from ${row.source_system.system_code}`}
                        disabled={!checked} onClick={() => { returnToObject.current = key; setViewedKey(key); }}>
                        {row.object_name}
                      </button><small>{row.entity_name}</small></td>
                      <td>{row.source_system.system_code}</td>
                      <td>{chosenCount} selected · {row.attributes.length - chosenCount} unselected</td>
                      <td>{row.is_locked ? "Object locked" : `${row.attributes.filter((item) => item.is_locked).length} locked`}</td>
                    </tr>;
                  })}</tbody>
                </table>
                {!visible.length ? <p className="empty-state compact">No targets match. Check target bindings and Systems represented in Model Input Scope.</p> : null}
              </div>
            </>}
        </fieldset>
        {targets.isError ? <button type="button" className="text-action" disabled={frozen} onClick={() => void targets.refetch()}>Retry loading targets</button> : null}
        {incompleteCount > 0 ? <p className="inline-error" role="alert">{incompleteCount} selected Objects have missing Attributes excluded. Select those Attributes to complete their mappings.</p> : null}
        <details className="mapping-advanced"><summary>Advanced settings</summary>
          <MappingOutputTemplateSelection
            mappingObjects={templates.data?.mappingObjects ?? []} mappingAttributes={templates.data?.mappingAttributes ?? []}
            objectValue={objectTemplate} attributeValue={attributeTemplate} disabled={frozen || templates.isPending || templates.isError}
            onObjectChange={setObjectTemplate} onAttributeChange={setAttributeTemplate} />
        </details>
        {capabilities.isError || (capabilities.data && !agentValid) ? <p className="inline-error" role="alert">No compatible agent configuration is available. Refresh and check Model settings.</p> : null}
        {templates.isError ? <p className="field-help">Custom templates could not be loaded. Global defaults remain available.</p> : null}
        {mutation.isError ? <p className="inline-error" role="alert">{mappingRunError(mutation.error, pendingRunId !== null)}</p> : null}
        <footer className="dialog-actions">
          <button className="button button-secondary" type="button" disabled={mutation.isPending} onClick={onClose}>Cancel</button>
          <button className="button button-primary" type="submit"
            disabled={mutation.isPending || (pendingRunId === null && (selectionUnavailable || !selected.length || !agentValid || incompleteCount > 0))}>
            {mutation.isPending ? "Starting…" : pendingRunId !== null ? "Retry start" : "Generate mappings"}
          </button>
        </footer>
      </form>
    </section>
  </div>;
}

function mappingRunError(error: Error, runWasCreated: boolean): string {
  if (runWasCreated && isTenantWorkflowConflict(error)) return TENANT_WORKFLOW_CONFLICT_MESSAGE;
  if (runWasCreated) return "The Mapping run remains queued because it could not be started.";
  if (error instanceof ApiError && error.status === 403) return "You no longer have permission or the required Tenant Lock to run Mapping.";
  if (error instanceof ApiError && error.status === 409) return "The Model or Mapping state changed. Refresh before creating another run.";
  return "The Mapping run could not be created or started.";
}
