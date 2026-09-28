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
import { CodeMappingWarnings } from "./CodeMappingWarnings";

export type CodeGenerationCoverage = "selected_targets" | "all_eligible_targets";

export function CodeGenerationRunDialog({ api, tenantId, model, entityType, coverage, selectedTargets, onClose, onStarted }: {
  api: CodeGenerationApi; tenantId: number; model: ModelDetail; entityType: MappingEntityType;
  coverage: CodeGenerationCoverage; selectedTargets: CodeGenerationTarget[];
  onClose: () => void; onStarted: (workflowRunId: number) => Promise<void>;
}) {
  const closeButton = useRef<HTMLButtonElement>(null);
  useDialogFocus(closeButton);
  const [scope, setScope] = useState(coverage);
  const [objectIds, setObjectIds] = useState(new Set(selectedTargets.map((item) => item.target.entity_id)));
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
  const objects = unlocked.filter((item) => scope === "all_eligible_targets" || objectIds.has(item.target.entity_id));
  const systems = [...new Map(objects.flatMap((item) => item.source_systems.map((system) => [system.system_code, system] as const))).values()];
  const unavailableSystemCodes = systemCodes.filter((code) => !systems.some((item) => item.system_code === code));
  const hasUnavailableSystems = systemScope === "selected" && unavailableSystemCodes.length > 0;
  const selectedCodes = systemScope === "all" ? systems.map((item) => item.system_code) : systemCodes.filter((code) => systems.some((item) => item.system_code === code));
  const requestedEntities = objects.filter((item) => item.source_systems.some((system) => selectedCodes.includes(system.system_code)));
  const scopedRows = rows.filter((item) => systemScope === "all" || item.source_systems.some((system) => systemCodes.includes(system.system_code)));
  const visible = scopedRows.filter((item) => `${item.target.entity_schema_name}.${item.target.entity_name} ${item.target.entity_type}`.toLowerCase().includes(search.trim().toLowerCase()));
  const shown = visible.slice(page * 50, (page + 1) * 50);
  const selectable = shown.filter((item) => !item.is_locked);
  const partialFiles = requestedEntities.some((item) => item.artifacts.some((artifact) => artifact.generated_code_status === "active"
    && artifact.source_system_codes.some((code) => selectedCodes.includes(code))
    && artifact.source_system_codes.some((code) => item.source_systems.some((system) => system.system_code === code) && !selectedCodes.includes(code))));
  const mappingCount = requestedEntities.reduce((count, item) => count + item.source_systems.filter((system) => selectedCodes.includes(system.system_code)).length, 0);
  const fileCount = fileLayout === "combined" ? requestedEntities.length : mappingCount;
  const unavailable = targets.isPending || targets.isError || targets.data?.model_revision !== model.model_revision;
  const valid = !unavailable && !hasUnavailableSystems && requestedEntities.length > 0 && selectedCodes.length > 0 && !partialFiles
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
      selected_object_ids: [], selected_entity_ids: requestedEntities.map((item) => item.target.entity_id), selected_system_codes: selectedCodes,
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
        <p className="field-help">Mode: <strong>Tool-assisted</strong>. Reads the selected Mapping documents and supporting context before generating SQL.</p>
        <fieldset disabled={mutation.isPending || pendingRunId !== null || unavailable}>
          <legend className="sr-only">SQL generation selection</legend>
          <div className="agent-run-grid agent-run-grid-two code-delivery-options">
            <div className="code-system-options"><SelectField label="Contributing Systems" value={systemScope} options={[["all", "All Systems"], ["selected", "Selected Systems"]]} onChange={(value) => { setSystemScope(value); setPage(0); }} />
            {systemScope === "selected" ? <MultiSelectField label="Systems" value={systemCodes} emptyLabel="Choose Systems"
              options={[...systems.map((item): [string, string] => [item.system_code, item.system_code]),
                ...unavailableSystemCodes.map((code): [string, string] => [code, `${code} (unavailable)`])]}
              onChange={(value) => { setSystemCodes(value); setPage(0); }} /> : null}</div>
            <SelectField label="SQL files" value={fileLayout} options={[["per_system", "Separate file per Object and System"], ["combined", "Combined file per Object"]]} onChange={(value) => setFileLayout(value as typeof fileLayout)} />
          </div>
          <p className="field-help">{fileLayout === "per_system" ? "Each file contains one System’s transformation for one Object and runs independently." : "Each Object gets one file with System-specific transformations and a final combined query, following its applied Mapping."}</p>
          <div className="scope-mode-options" role="group" aria-label="Entities">
            <label><input type="radio" name="code-objects" checked={scope === "all_eligible_targets"} onChange={() => setScope("all_eligible_targets")} />All unlocked Entities</label>
            <label><input type="radio" name="code-objects" checked={scope === "selected_targets"} onChange={() => {
              if (scope === "all_eligible_targets" && !objectIds.size) setObjectIds(new Set(unlocked.map((item) => item.target.entity_id)));
              setScope("selected_targets");
            }} />Selected Entities</label>
          </div>
          <p className="field-help">Partial mappings are included. Missing Attribute transformations become typed NULL values; review the generated SQL before applying.</p>
          <div className="agent-run-grid mapping-scope-controls"><label><span>Find Entities</span><input type="search" aria-label="Find Entities" value={search} onChange={(event) => { setSearch(event.target.value); setPage(0); }} /></label></div>
          {scope === "selected_targets" ? <div className="scope-selection-actions">
            <button className="button button-secondary button-small" type="button" onClick={() => setObjectIds(new Set([...objectIds, ...selectable.map((item) => item.target.entity_id)]))}>Select all shown Entities</button>
            <button className="button button-secondary button-small" type="button" onClick={() => setObjectIds(new Set())}>Clear Entity selection</button>
          </div> : null}
          <div className="workflow-table-scroll mapping-target-selection"><table className="enrichment-selection-table" aria-label="Entities for SQL generation">
            <thead><tr><th>Select</th><th>Entity</th><th>Contributing Systems</th><th>Lock</th></tr></thead>
            <tbody>{shown.map((item) => <tr key={item.target.entity_id}><td><input type="checkbox" aria-label={`Generate ${item.target.entity_schema_name}.${item.target.entity_name}`} disabled={scope === "all_eligible_targets" || item.is_locked} checked={!item.is_locked && (scope === "all_eligible_targets" || objectIds.has(item.target.entity_id))} onChange={(event) => {
              const next = new Set(objectIds); if (event.target.checked) next.add(item.target.entity_id); else next.delete(item.target.entity_id); setObjectIds(next);
            }} /></td><td><strong>{item.target.entity_schema_name}.{item.target.entity_name}</strong></td><td>{item.source_systems.map((system) => system.system_code).join(", ")}
              <CodeMappingWarnings supports={item.mapping_supports} systemCodes={selectedCodes} />
            </td><td>{item.is_locked ? "Locked" : "Open"}</td></tr>)}</tbody>
          </table>{!shown.length ? <p className="empty-state compact">{systemScope === "selected" && !selectedCodes.length ? "Choose at least one contributing System to see its Entities." : "No Entities match this selection."}</p> : null}</div>
          {visible.length > 50 ? <nav className="code-generation-pagination" aria-label="Generation Object pages"><button type="button" className="button button-secondary button-small" disabled={!page} onClick={() => setPage(page - 1)}>Previous</button><span>Page {page + 1}</span><button type="button" className="button button-secondary button-small" disabled={(page + 1) * 50 >= visible.length} onClick={() => setPage(page + 1)}>Next</button></nav> : null}
          <p className="scope-selection-summary" role="status">{requestedEntities.length} Entities · {mappingCount} Entity/System mappings · {fileCount} SQL files</p>
          {partialFiles ? <p className="inline-error" role="alert">An existing SQL file combines selected and unselected Systems. Select all Systems covered by that file to regenerate it.</p> : null}
          {hasUnavailableSystems ? <p className="inline-error" role="alert">A selected System no longer contributes to the selected Entities. Remove unavailable Systems from the selection or choose All Systems.</p> : null}
        </fieldset>
        {targets.isPending ? <p className="surface-state compact" aria-busy="true">Loading Entities…</p> : targets.isError ? <p className="inline-error" role="alert">Entities could not be loaded. Close and retry.</p> : targets.data?.model_revision !== model.model_revision ? <p className="inline-error" role="alert">The Model changed. Close and refresh before generating SQL.</p> : null}
        {capabilities.isError ? <p className="inline-error" role="alert">Generator options could not be loaded.</p> : null}
        {mutation.isError ? <p className="inline-error" role="alert">{generationError(mutation.error, pendingRunId !== null)}
          {mutation.error instanceof ApiError && mutation.error.correlationId ? <span> Reference {mutation.error.correlationId}.</span> : null}</p> : null}
        <footer className="dialog-actions"><button type="button" className="button button-secondary" disabled={mutation.isPending} onClick={onClose}>Cancel</button><button className="button button-primary" type="submit" disabled={mutation.isPending || (pendingRunId === null && !valid)}>{mutation.isPending ? "Starting…" : pendingRunId !== null ? "Retry start" : "Generate SQL"}</button></footer>
      </form>
    </section>
  </div>;
}

function generationError(error: Error, created: boolean): string {
  if (created && isTenantWorkflowConflict(error)) return TENANT_WORKFLOW_CONFLICT_MESSAGE;
  if (error instanceof ApiError) {
    const messages: Record<string, string> = {
      code_mapping_incomplete: "The selected Entities need at least one saved Object or Attribute transformation. Review their applied Mapping, then refresh before generating SQL.",
      code_no_eligible_targets: "No selected Entities have a saved Mapping transformation. Apply at least one Object or Attribute transformation, then refresh.",
      code_system_unavailable: "A selected System no longer contributes to the selected Entities. Refresh and select the contributing Systems again.",
      sql_generation_guide_unavailable: "An active, published SQL generation guide is required. Ask an administrator to configure it, then retry.",
      workflow_prompt_unavailable: "A published Code generation prompt is unavailable. Review the Model’s prompt settings, then retry.",
      tenant_lock_required: "Acquire the Tenant Lock on Home before generating SQL.",
      tenant_locked: "Another user holds the Tenant Lock. Acquire it on Home before generating SQL.",
      model_revision_conflict: "The Model changed. Close this dialog and refresh before generating SQL.",
    };
    const message = messages[error.code];
    if (message) return message + (created ? " This run remains queued." : "");
  }
  if (created) return "The Code Generation run remains queued because it could not be started.";
  if (error instanceof ApiError && error.status === 403) return "You no longer have permission or the required Tenant Lock to generate SQL.";
  if (error instanceof ApiError && error.status === 409) return "The Model or Code Generation state changed. Refresh before creating another run.";
  return "The Code Generation run could not be created or started.";
}
