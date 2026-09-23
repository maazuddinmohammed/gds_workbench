import { useEffect, useRef, useState, type FormEvent } from "react";
import { useQuery } from "@tanstack/react-query";

import { ApiError } from "../../core/http";
import { trapDialogFocus, useDialogFocus } from "../../shared/dialog";
import { MultiSelectField } from "../../shared/MultiSelectField";
import { SelectField } from "../../shared/ui";
import type { MappingEntityType } from "../mapping/api";
import type { ModelDetail } from "../models/api";
import { useWorkflowRunSubmission } from "../workflows/useWorkflowRunSubmission";
import { findAgentExecutionProfile, reasoningEffortDisplayName, resolveDefaultAgent, workflowCreationQueryKeys } from "../workflows/api";
import { isTenantWorkflowConflict, TENANT_WORKFLOW_CONFLICT_MESSAGE } from "../workflows/presentation";
import { codeGenerationQueryKeys, loadCodeGenerationTargets, type CodeGenerationApi, type CodeGenerationTarget } from "./api";

export type CodeGenerationCoverage = "selected_targets" | "all_eligible_targets";

export function CodeGenerationRunDialog({ api, tenantId, model, entityType, coverage, selectedTargets, onClose, onStarted }: {
  api: CodeGenerationApi; tenantId: number; model: ModelDetail; entityType: MappingEntityType;
  coverage: CodeGenerationCoverage; selectedTargets: CodeGenerationTarget[];
  onClose: () => void; onStarted: (workflowRunId: number) => Promise<void>;
}) {
  const closeButton = useRef<HTMLButtonElement>(null);
  useDialogFocus(closeButton);
  const [scope, setScope] = useState(coverage);
  const [objectIds, setObjectIds] = useState(new Set(selectedTargets.map((item) => item.target.object_id)));
  const [systemScope, setSystemScope] = useState("all");
  const [systemCodes, setSystemCodes] = useState<string[]>([]);
  const [fileLayout, setFileLayout] = useState<"combined" | "per_system">("per_system");
  const [search, setSearch] = useState("");
  const [page, setPage] = useState(0);
  const [modelCode, setModelCode] = useState(model.default_agent_model_code ?? "");
  const [reasoningCode, setReasoningCode] = useState(model.default_reasoning_effort_code ?? "");
  const targets = useQuery({
    queryKey: codeGenerationQueryKeys.targets(tenantId, model.model_id, { entityType }, undefined),
    queryFn: () => loadCodeGenerationTargets(api, tenantId, model.model_id, entityType),
  });
  const capabilities = useQuery({ queryKey: workflowCreationQueryKeys.capabilities, queryFn: api.readAgentCapabilities });
  const models = capabilities.data?.models.filter((item) => findAgentExecutionProfile(item, "tool_assisted")) ?? [];
  const profile = models.find((item) => item.code === modelCode);
  const efforts = capabilities.data?.reasoning_efforts.filter((item) => profile && findAgentExecutionProfile(profile, "tool_assisted")?.reasoning_effort_codes.includes(item.code)) ?? [];
  const agent = capabilities.data ? resolveDefaultAgent(capabilities.data, "tool_assisted", {
    modelCode, reasoningEffortCode: reasoningCode, maxTurns: model.default_max_turns, validationRetryCount: model.default_validation_retry_count,
  }) : null;
  useEffect(() => {
    if (!agent) return;
    if (modelCode !== agent.model_code) setModelCode(agent.model_code);
    if (reasoningCode !== agent.reasoning_effort_code) setReasoningCode(agent.reasoning_effort_code);
  }, [agent?.model_code, agent?.reasoning_effort_code, modelCode, reasoningCode]);
  const rows = targets.data?.items ?? [];
  const unlocked = rows.filter((item) => !item.is_locked);
  const objects = unlocked.filter((item) => scope === "all_eligible_targets" || objectIds.has(item.target.object_id));
  const systems = [...new Map(unlocked.flatMap((item) => item.source_systems.map((system) => [system.system_code, system] as const))).values()];
  const selectedCodes = systemScope === "all" ? systems.map((item) => item.system_code) : systemCodes.filter((code) => systems.some((item) => item.system_code === code));
  const requestedObjects = objects.filter((item) => item.source_systems.some((system) => selectedCodes.includes(system.system_code)));
  const scopedRows = rows.filter((item) => systemScope === "all" || item.source_systems.some((system) => selectedCodes.includes(system.system_code)));
  const visible = scopedRows.filter((item) => `${item.target.object_schema}.${item.target.object_name} ${item.target.system_code}`.toLowerCase().includes(search.trim().toLowerCase()));
  const shown = visible.slice(page * 50, (page + 1) * 50);
  const selectable = shown.filter((item) => !item.is_locked);
  const partialFiles = requestedObjects.some((item) => item.artifacts.some((artifact) => artifact.generated_code_status === "active"
    && artifact.source_system_codes.some((code) => selectedCodes.includes(code))
    && artifact.source_system_codes.some((code) => !selectedCodes.includes(code))));
  const fileCount = fileLayout === "combined" ? requestedObjects.length : requestedObjects.reduce((count, item) => count + item.source_systems.filter((system) => selectedCodes.includes(system.system_code)).length, 0);
  const unavailable = targets.isPending || targets.isError || targets.data?.model_revision !== model.model_revision;
  const valid = !unavailable && requestedObjects.length > 0 && selectedCodes.length > 0 && !partialFiles
    && agent?.model_code === modelCode && agent?.reasoning_effort_code === reasoningCode;
  const { mutation, pendingRunId } = useWorkflowRunSubmission({ api, tenantId, modelId: model.model_id,
    execute: (id, command) => api.executeCodeGenerationRun(tenantId, model.model_id, id, command.expected_model_revision),
    onSuccess: async (id) => { await onStarted(id); onClose(); },
  });
  const submit = (event: FormEvent) => {
    event.preventDefault();
    if (pendingRunId !== null) { mutation.mutate(undefined); return; }
    if (!valid) return;
    mutation.mutate({ expected_model_revision: model.model_revision, model_workflow: "code_generation", workflow_execution_mode: null,
      selected_object_ids: requestedObjects.map((item) => item.target.object_id), selected_system_codes: selectedCodes,
      modeled_entity_type: entityType, requested_batch_id: null, agent, prompt_overrides: {},
      code_generation_coverage_mode: "selected_targets", code_generation_file_layout: fileLayout, sql_generation_guide_version_id: null });
  };
  return <div className="dialog-scrim" role="presentation">
    <section className="run-configuration-dialog mapping-run-dialog" role="dialog" aria-modal="true" aria-labelledby="code-generation-run-heading" onKeyDown={(event) => {
      trapDialogFocus(event); if (event.key === "Escape" && !mutation.isPending) onClose();
    }}>
      <header className="drawer-header"><div><small>{entityType === "logical_entity" ? "Logical · Silver" : "Dimensional · Gold"}</small><h2 id="code-generation-run-heading">Generate SQL</h2></div>
        <button ref={closeButton} className="panel-close" type="button" aria-label="Close Generate SQL" disabled={mutation.isPending} onClick={onClose}>×</button>
      </header>
      <form onSubmit={submit}>
        <fieldset className="agent-run-grid agent-run-grid-two" disabled={mutation.isPending || pendingRunId !== null}>
          <legend className="sr-only">Generator configuration</legend>
          <SelectField label="Model" value={modelCode} options={models.map((item) => [item.code, item.name])} onChange={setModelCode} />
          <SelectField label="Reasoning effort" value={reasoningCode} options={efforts.map((item) => [item.code, reasoningEffortDisplayName(item)])} onChange={setReasoningCode} />
        </fieldset>
        <fieldset disabled={mutation.isPending || pendingRunId !== null || unavailable}>
          <legend className="sr-only">SQL generation selection</legend>
          <div className="agent-run-grid agent-run-grid-two code-delivery-options">
            <div className="code-system-options"><SelectField label="Contributing Systems" value={systemScope} options={[["all", "All Systems"], ["selected", "Selected Systems"]]} onChange={(value) => { setSystemScope(value); setPage(0); }} />
            {systemScope === "selected" ? <MultiSelectField label="Systems" value={selectedCodes} emptyLabel="Choose Systems" options={systems.map((item) => [item.system_code, item.system_code])} onChange={(value) => { setSystemCodes(value); setPage(0); }} /> : null}</div>
            <SelectField label="SQL files" value={fileLayout} options={[["per_system", "Separate file per Object and System"], ["combined", "Combined file per Object"]]} onChange={(value) => setFileLayout(value as typeof fileLayout)} />
          </div>
          <p className="field-help">{fileLayout === "per_system" ? "Each file contains one System’s transformation for one Object and runs independently." : "Each Object gets one file with System-specific transformations and a final combined query, following its applied Mapping."}</p>
          <div className="scope-mode-options" role="group" aria-label="Objects">
            <label><input type="radio" name="code-objects" checked={scope === "all_eligible_targets"} onChange={() => setScope("all_eligible_targets")} />All unlocked Objects</label>
            <label><input type="radio" name="code-objects" checked={scope === "selected_targets"} onChange={() => {
              if (scope === "all_eligible_targets" && !objectIds.size) setObjectIds(new Set(unlocked.map((item) => item.target.object_id)));
              setScope("selected_targets");
            }} />Selected Objects</label>
          </div>
          <div className="agent-run-grid mapping-scope-controls"><label><span>Find Objects</span><input type="search" aria-label="Find Objects" value={search} onChange={(event) => { setSearch(event.target.value); setPage(0); }} /></label></div>
          {scope === "selected_targets" ? <div className="scope-selection-actions">
            <button className="button button-secondary button-small" type="button" onClick={() => setObjectIds(new Set([...objectIds, ...selectable.map((item) => item.target.object_id)]))}>Select all shown Objects</button>
            <button className="button button-secondary button-small" type="button" onClick={() => setObjectIds(new Set())}>Clear Object selection</button>
          </div> : null}
          <div className="workflow-table-scroll mapping-target-selection"><table className="enrichment-selection-table" aria-label="Objects for SQL generation">
            <thead><tr><th>Select</th><th>Object</th><th>Contributing Systems</th><th>Lock</th></tr></thead>
            <tbody>{shown.map((item) => <tr key={item.target.object_id}><td><input type="checkbox" aria-label={`Generate ${item.target.object_schema}.${item.target.object_name}`} disabled={scope === "all_eligible_targets" || item.is_locked} checked={!item.is_locked && (scope === "all_eligible_targets" || objectIds.has(item.target.object_id))} onChange={(event) => {
              const next = new Set(objectIds); if (event.target.checked) next.add(item.target.object_id); else next.delete(item.target.object_id); setObjectIds(next);
            }} /></td><td><strong>{item.target.object_schema}.{item.target.object_name}</strong></td><td>{item.source_systems.map((system) => system.system_code).join(", ")}</td><td>{item.is_locked ? "Locked" : "Open"}</td></tr>)}</tbody>
          </table>{!shown.length ? <p className="empty-state compact">{systemScope === "selected" && !selectedCodes.length ? "Choose at least one contributing System to see its Objects." : "No Objects match this selection."}</p> : null}</div>
          {visible.length > 50 ? <nav className="code-generation-pagination" aria-label="Generation Object pages"><button type="button" className="button button-secondary button-small" disabled={!page} onClick={() => setPage(page - 1)}>Previous</button><span>Page {page + 1}</span><button type="button" className="button button-secondary button-small" disabled={(page + 1) * 50 >= visible.length} onClick={() => setPage(page + 1)}>Next</button></nav> : null}
          <p className="scope-selection-summary" role="status">{requestedObjects.length} Objects · {selectedCodes.length} Systems · {fileCount} transformation SQL files</p>
          {partialFiles ? <p className="inline-error" role="alert">An existing SQL file combines selected and unselected Systems. Select all Systems covered by that file to regenerate it.</p> : null}
        </fieldset>
        {targets.isPending ? <p className="surface-state compact" aria-busy="true">Loading Objects…</p> : targets.isError ? <p className="inline-error" role="alert">Objects could not be loaded. Close and retry.</p> : targets.data?.model_revision !== model.model_revision ? <p className="inline-error" role="alert">The Model changed. Close and refresh before generating SQL.</p> : null}
        {capabilities.isError ? <p className="inline-error" role="alert">Generator options could not be loaded.</p> : null}
        {mutation.isError ? <p className="inline-error" role="alert">{generationError(mutation.error, pendingRunId !== null)}</p> : null}
        <footer className="dialog-actions"><button type="button" className="button button-secondary" disabled={mutation.isPending} onClick={onClose}>Cancel</button><button className="button button-primary" type="submit" disabled={mutation.isPending || (pendingRunId === null && !valid)}>{mutation.isPending ? "Starting…" : pendingRunId !== null ? "Retry start" : "Generate SQL"}</button></footer>
      </form>
    </section>
  </div>;
}

function generationError(error: Error, created: boolean): string {
  if (created && isTenantWorkflowConflict(error)) return TENANT_WORKFLOW_CONFLICT_MESSAGE;
  if (created) return "The Code Generation run remains queued because it could not be started.";
  if (error instanceof ApiError && error.status === 403) return "You no longer have permission or the required Tenant Lock to generate SQL.";
  if (error instanceof ApiError && error.status === 409) return "The Model or Code Generation state changed. Refresh before creating another run.";
  return "The Code Generation run could not be created or started.";
}
