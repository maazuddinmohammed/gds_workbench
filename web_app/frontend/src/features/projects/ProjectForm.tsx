import { useRef, useState, type FormEvent, type RefObject } from "react";
import { useQuery } from "@tanstack/react-query";
import { Link } from "@tanstack/react-router";

import { ApiError } from "../../core/http";
import type { JsonObject } from "../../shared/contracts";
import type { SystemRecord } from "../tenants/api";
import { reasoningEffortDisplayName, type WorkflowsApi } from "../workflows/api";
import type { CreateProjectCommand, ProjectEntityScdType, ProjectDetail, ProjectsApi } from "./api";
import "./project-schemas.css";

const layerFields = [
  { title: "Silver settings", fields: [
    { name: "silver_model_naming_instructions", label: "Silver naming instructions", json: false },
    { name: "silver_model_audit_columns_template", label: "Silver audit columns template", json: true },
  ] },
  { title: "Gold settings", fields: [
    { name: "gold_model_naming_instructions", label: "Gold naming instructions", json: false },
    { name: "gold_model_audit_columns_template", label: "Gold audit columns template", json: true },
  ] },
] as const;

export function ProjectForm({
  api, tenantId, hasTenantLock, initialProject, disabledReason, isPending, error,
  onSubmit, onCancel, onDirty, nameInput, systems = [],
}: {
  api: Pick<WorkflowsApi, "readAgentCapabilities"> & Partial<Pick<ProjectsApi, "readProjectTemplates">>;
  tenantId: number;
  hasTenantLock: boolean;
  initialProject?: ProjectDetail;
  disabledReason?: string | undefined;
  isPending: boolean;
  error: unknown;
  onSubmit: (command: CreateProjectCommand) => void;
  onCancel?: () => void;
  onDirty?: () => void;
  nameInput?: RefObject<HTMLInputElement | null>;
  systems?: SystemRecord[];
}) {
  const [logicalSchemas, setLogicalSchemas] = useState(() => initialProject
    ? initialProject.logical_schemas.map((row, index) => ({ ...row, description: row.description ?? "", key: index, editing: false }))
    : [{ schema_name: "", description: "", key: 0, editing: true }]);
  const [dimensionalSchemas, setDimensionalSchemas] = useState(() => initialProject
    ? initialProject.dimensional_schemas.map((row, index) => ({ ...row, description: row.description ?? "", key: index, editing: false }))
    : [{ schema_name: "", description: "", key: 0, editing: true }]);
  const nextSchemaKey = useRef(Math.max(logicalSchemas.length, dimensionalSchemas.length));
  const schemaToFocus = useRef<string | null>(null);
  const [agentModelCode, setAgentModelCode] = useState(initialProject?.default_agent_model_code ?? "");
  const [mappingSourceSystemId, setMappingSourceSystemId] = useState(initialProject?.default_mapping_source_system_id?.toString() ?? "");
  const [logicalScdType, setLogicalScdType] = useState<ProjectEntityScdType | "">(initialProject?.logical_entity_scd_type ?? "");
  const [dimensionalScdType, setDimensionalScdType] = useState<ProjectEntityScdType | "">(initialProject?.dimensional_entity_scd_type ?? "");
  const [reasoningCode, setReasoningCode] = useState(initialProject?.default_reasoning_effort_code ?? "");
  const [agentDefaultsChanged, setAgentDefaultsChanged] = useState(false);
  const [agentSettingsOpen, setAgentSettingsOpen] = useState(false);
  const [validationError, setValidationError] = useState<{ field: string; message: string } | null>(null);
  const [templateOverrides, setTemplateOverrides] = useState<Record<string, string | null>>(() =>
    Object.fromEntries(layerFields.flatMap((group) => group.fields.map((field) => [field.name,
      initialProject?.[field.name] == null ? null : field.json
        ? JSON.stringify(initialProject[field.name], null, 2) : String(initialProject[field.name]),
    ]))));
  const templates = useQuery({
    queryKey: ["project-templates", tenantId],
    queryFn: () => api.readProjectTemplates!(tenantId),
    enabled: Boolean(api.readProjectTemplates),
  });
  const capabilities = useQuery({
    queryKey: ["agent-capabilities"],
    queryFn: api.readAgentCapabilities,
    enabled: agentSettingsOpen,
  });
  const selectedModel = capabilities.data?.models.find((model) => model.code === agentModelCode);
  const reasoningOptions = capabilities.data?.reasoning_efforts.filter((effort) =>
    selectedModel?.execution_profiles.some((profile) => profile.reasoning_effort_codes.includes(effort.code))) ?? [];
  function submit(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    if (!hasTenantLock || disabledReason || isPending) return;
    const form = event.currentTarget;
    const data = new FormData(form);
    const text = (field: string) => String(data.get(field) ?? "").trim();
    const invalid = (field: string, message: string) => {
      setValidationError({ field, message });
      const control = form.elements.namedItem(field);
      if (control instanceof HTMLElement) {
        const section = control.closest("details");
        if (section) section.open = true;
        control.focus();
      }
    };
    setValidationError(null);
    const command: CreateProjectCommand = {
      project_name: text("project_name"),
      project_description: text("project_description") || null,
      logical_schemas: logicalSchemas.filter((item) => item.schema_name.trim() || item.description.trim()).map((item) => ({ schema_name: item.schema_name.trim(), description: item.description.trim() || null })),
      dimensional_schemas: dimensionalSchemas.filter((item) => item.schema_name.trim() || item.description.trim()).map((item) => ({ schema_name: item.schema_name.trim(), description: item.description.trim() || null })),
      silver_model_naming_instructions: null,
      silver_model_audit_columns_template: null,
      logical_entity_scd_type: logicalScdType || null,
      dimensional_entity_scd_type: dimensionalScdType || null,
      logical_coverage_threshold_percent: null,
      dimensional_coverage_threshold_percent: null,
      logical_enforce_coverage_threshold: data.has("logical_enforce_coverage_threshold"),
      dimensional_enforce_coverage_threshold: data.has("dimensional_enforce_coverage_threshold"),
      gold_model_naming_instructions: null,
      gold_model_technical_columns_template: null,
      gold_model_audit_columns_template: null,
      default_agent_sdk_code: initialProject?.default_agent_sdk_code ?? null,
      default_agent_provider_code: initialProject?.default_agent_provider_code ?? null,
      default_agent_model_code: initialProject?.default_agent_model_code ?? null,
      default_reasoning_effort_code: initialProject?.default_reasoning_effort_code ?? null,
      default_max_turns: initialProject?.default_max_turns ?? null,
      default_validation_retry_count: initialProject?.default_validation_retry_count ?? null,
      default_mapping_source_system_id: mappingSourceSystemId ? Number(mappingSourceSystemId) : null,
    };
    if (!command.project_name || command.project_name.length > 255) {
      invalid("project_name", "Enter a Project name of 1–255 characters.");
      return;
    }
    if ((command.project_description?.length ?? 0) > 2000) {
      invalid("project_description", "Keep the description within 2,000 characters.");
      return;
    }
    for (const layer of ["logical", "dimensional"] as const) {
      const field = `${layer}_coverage_threshold_percent` as const;
      const value = text(field);
      if (value && (!/^\d+$/.test(value) || Number(value) < 1 || Number(value) > 100)) {
        invalid(field, "Enter a whole number from 1 to 100, or leave blank for the default.");
        return;
      }
      command[field] = value ? Number(value) : null;
      const rows = layer === "logical" ? logicalSchemas : dimensionalSchemas;
      const invalidIndex = rows.findIndex((item, index) => {
        const name = item.schema_name.trim();
        return (!name && Boolean(item.description.trim())) || name.length > 400
          || Boolean(name && rows.some((other, otherIndex) => otherIndex < index && other.schema_name.trim().toLowerCase() === name.toLowerCase()));
      });
      if (invalidIndex >= 0) {
        invalid(`${layer}_schema_${invalidIndex}`, "Use a distinct, nonblank name for each configured schema.");
        return;
      }
    }
    for (const group of layerFields) {
      for (const field of group.fields) {
        if (templateOverrides[field.name] == null) continue;
        const value = text(field.name);
        if (!value) continue;
        if (!field.json && new TextEncoder().encode(value).length > 32 * 1024) {
          invalid(field.name, `${field.label} must fit within 32 KB.`);
          return;
        }
        if (field.json) {
          try {
            const parsed: unknown = JSON.parse(value);
            if (!parsed || typeof parsed !== "object" || Array.isArray(parsed)) throw new Error();
            if (new TextEncoder().encode(JSON.stringify(parsed)).length > 32 * 1024) {
              invalid(field.name, `${field.label} must fit within 32 KB.`);
              return;
            }
            command[field.name] = parsed as JsonObject;
          } catch {
            invalid(field.name, `${field.label} must be a JSON object.`);
            return;
          }
        } else command[field.name] = value;
      }
    }
    if (agentModelCode && (!initialProject || agentDefaultsChanged)) {
      const registry = capabilities.data;
      const profile = selectedModel?.execution_profiles.find((item) => item.reasoning_effort_codes.includes(reasoningCode));
      if (!registry || !selectedModel || !profile || capabilities.isError) {
        invalid("agent_model", "Choose an available agent model and reasoning effort.");
        return;
      }
      const maxTurns = Number(text("max_turns"));
      const retries = Number(text("validation_retries"));
      for (const [field, value, bounds] of [
        ["max_turns", maxTurns, registry.max_turns],
        ["validation_retries", retries, registry.validation_retries],
      ] as const) {
        if (!text(field) || !Number.isInteger(value) || value < bounds.minimum || value > bounds.maximum) {
          invalid(field, `Enter a whole number from ${bounds.minimum} to ${bounds.maximum}.`);
          return;
        }
      }
      Object.assign(command, {
        default_agent_sdk_code: profile.sdk_code,
        default_agent_provider_code: selectedModel.provider_code,
        default_agent_model_code: selectedModel.code,
        default_reasoning_effort_code: reasoningCode,
        default_max_turns: maxTurns,
        default_validation_retry_count: retries,
      });
    }
    if (!agentModelCode) {
      Object.assign(command, {
        default_agent_sdk_code: null, default_agent_provider_code: null,
        default_agent_model_code: null, default_reasoning_effort_code: null,
        default_max_turns: null, default_validation_retry_count: null,
      });
    }
    onSubmit(command);
  }

  const errorCode = error instanceof ApiError ? error.code : "";
  const errorMessages: Record<string, string> = {
    project_name_conflict: "This Tenant already has a Project with that name, including archived Projects. Choose another name.",
    authorization_denied: initialProject ? "Architect permission is required to update Project settings." : "Only Super Admins and Tenant Admins can create Projects.",
    tenant_lock_required: "Acquire the Tenant Lock on Home, then return to save this Project.",
    tenant_locked: "Another user holds the Tenant Lock. Acquire it on Home before retrying.",
    tenant_not_found: "This Tenant is no longer available to you.",
    project_locked: "The Project is locked. A human must unlock it before saving. Your edits are preserved.",
    project_revision_conflict: "The Project changed. Your edits are preserved. Refresh saved settings before retrying.",
    project_schema_conflict: "An existing Entity still uses a removed or renamed schema, including inactive Entities. Restore its schema name before saving. Your edits are preserved.",
    project_not_found: "This Project is no longer available for editing. Refresh saved settings.",
    invalid_request: "Some settings are no longer valid. Check the fields and agent defaults, then retry.",
  };

  return (
    <form className="project-definition-form" noValidate onSubmit={submit} onChange={onDirty} aria-busy={isPending}>
          <fieldset className="create-project-fields" disabled={isPending || Boolean(disabledReason)}>
            <div className="project-definition-identity">
              <label>
                <span>Project name <small>Required</small></span>
                <input ref={nameInput} name="project_name" required maxLength={255} autoComplete="off" defaultValue={initialProject?.project_name ?? ""}
                  aria-invalid={validationError?.field === "project_name"} aria-describedby={validationError?.field === "project_name" ? "project-form-error" : undefined} />
              </label>
              <label>
                <span>Description</span>
                <textarea name="project_description" rows={2} maxLength={2000} defaultValue={initialProject?.project_description ?? ""} />
              </label>
            </div>
            {!initialProject ? <p className="field-help">Add source Objects to Input Scope after creating the Project.</p> : null}
            {([
              { layer: "logical", title: "Logical schemas", rows: logicalSchemas, update: setLogicalSchemas },
              { layer: "dimensional", title: "Dimensional schemas", rows: dimensionalSchemas, update: setDimensionalSchemas },
            ] as const).map(({ layer, title, rows, update }) => (
              <details key={layer} className="create-project-settings project-schema-settings" open={Boolean(initialProject)}>
                <summary>{title}<span>{rows.filter((row) => row.schema_name.trim()).length}</span></summary>
                <div className="create-project-fields">
                  {!rows.length ? <p className="field-help">Add a schema before generation.</p> : null}
                  {rows.map((row, index) => (
                    <fieldset key={row.key} className={`project-schema-row${row.editing ? " is-editing" : " is-saved"}`}>
                      <label>
                        <span className={row.editing ? undefined : "sr-only"}>Schema name</span>
                        <input name={`${layer}_schema_${index}`} value={row.schema_name} maxLength={400}
                          readOnly={!row.editing}
                          ref={(element) => {
                            if (element && schemaToFocus.current === `${layer}:${row.key}`) {
                              element.focus();
                              schemaToFocus.current = null;
                            }
                          }}
                          aria-invalid={validationError?.field === `${layer}_schema_${index}`}
                          aria-describedby={validationError?.field === `${layer}_schema_${index}` ? "project-form-error" : undefined}
                          onChange={(event) => update(rows.map((item, position) => position === index ? { ...item, schema_name: event.target.value } : item))} />
                      </label>
                      <label>
                        <span className={row.editing ? undefined : "sr-only"}>Description</span>
                        <textarea value={row.description} maxLength={2000} rows={row.editing ? 2 : 1} readOnly={!row.editing}
                          onChange={(event) => update(rows.map((item, position) => position === index ? { ...item, description: event.target.value } : item))} />
                      </label>
                      <div className="project-schema-actions">
                        <span className="status-badge is-neutral">{row.editing ? "Unsaved" : "Saved"}</span>
                        {row.editing ? (
                          <button type="button" className="text-action" onClick={() => {
                            update(rows.filter((_, position) => position !== index));
                            onDirty?.();
                          }}>Remove schema</button>
                        ) : (
                          <button type="button" className="text-action" onClick={() => {
                            schemaToFocus.current = `${layer}:${row.key}`;
                            update(rows.map((item, position) => position === index ? { ...item, editing: true } : item));
                          }}>Edit schema</button>
                        )}
                      </div>
                    </fieldset>
                  ))}
                  <div className="project-schema-add">
                    <button type="button" className="button button-secondary button-small" disabled={rows.length >= 100} onClick={() => {
                      const key = nextSchemaKey.current++;
                      schemaToFocus.current = `${layer}:${key}`;
                      update([...rows, { schema_name: "", description: "", key, editing: true }]);
                      onDirty?.();
                    }}>Add schema</button>
                  </div>
                </div>
              </details>
            ))}
            <details className="create-project-settings">
              <summary>Mapping settings</summary>
              <div className="create-project-fields project-mapping-default">
                <label>
                  <span>Default mapping System</span>
                  <select name="default_mapping_source_system_id" value={mappingSourceSystemId}
                    aria-describedby="mapping-default-system-help"
                    onChange={(event) => setMappingSourceSystemId(event.target.value)}>
                    <option value="">No default System</option>
                    {mappingSourceSystemId && !systems.some((system) => String(system.system_id) === mappingSourceSystemId)
                      ? <option value={mappingSourceSystemId}>Saved System (unavailable)</option> : null}
                    {systems.map((system) => <option key={system.system_id} value={system.system_id}>{system.system_code}</option>)}
                  </select>
                </label>
                <p id="mapping-default-system-help" className="field-help">Used when an Entity has only Context sources.</p>
              </div>
            </details>
            {layerFields.map((group) => (
              <details key={group.title} className="create-project-settings">
                <summary>{group.title}</summary>
                <div className="create-project-fields">
                  {group.title === "Silver settings" ? <label>
                    <span id="logical-scd-type-label">Logical entity SCD type</span>
                    <select name="logical_entity_scd_type" value={logicalScdType}
                      aria-labelledby="logical-scd-type-label"
                      aria-describedby="logical-scd-type-help"
                      onChange={(event) => setLogicalScdType(event.target.value as ProjectEntityScdType | "")}>
                      <option value="">Not specified</option>
                      <option value="type_1">SCD Type 1 — overwrite changes</option>
                      <option value="type_2">SCD Type 2 — preserve history</option>
                    </select>
                    <small id="logical-scd-type-help" className="field-help">Guides Logical entity and Mapping generation.</small>
                  </label> : null}
                  {group.title === "Gold settings" ? <label>
                    <span id="dimensional-scd-type-label">Dimensional entity SCD type</span>
                    <select name="dimensional_entity_scd_type" value={dimensionalScdType}
                      aria-labelledby="dimensional-scd-type-label"
                      aria-describedby="dimensional-scd-type-help"
                      onChange={(event) => setDimensionalScdType(event.target.value as ProjectEntityScdType | "")}>
                      <option value="">Not specified</option>
                      <option value="type_1">SCD Type 1 — overwrite changes</option>
                      <option value="type_2">SCD Type 2 — preserve history</option>
                    </select>
                    <small id="dimensional-scd-type-help" className="field-help">Controls Dimension history and Mapping generation. Type 1 overwrites changes; Type 2 keeps versions. Facts and Bridges are unaffected.</small>
                  </label> : null}
                  {(() => {
                    const layer = group.title === "Silver settings" ? "logical" : "dimensional";
                    const field = `${layer}_coverage_threshold_percent` as const;
                    const defaultPercent = layer === "logical" ? 70 : 60;
                    const enforcementField = `${layer}_enforce_coverage_threshold` as const;
                    return <div><label>
                      <span id={`${field}-label`}>{layer === "logical" ? "Logical" : "Dimensional"} coverage threshold (%)</span>
                      <input name={field} type="number" min={1} max={100} step={1}
                        aria-labelledby={`${field}-label`}
                        defaultValue={initialProject?.[field] ?? ""} placeholder={String(defaultPercent)}
                        aria-invalid={validationError?.field === field}
                        aria-describedby={`${field}-help${validationError?.field === field ? " project-form-error" : ""}`} />
                      <small id={`${field}-help`} className="field-help">Whole number from 1 to 100. Blank uses {defaultPercent}%. Counts distinct selected {layer === "logical" ? "tables" : "Logical entities"} with active supporting mappings.</small>
                    </label>
                    <label className="checkbox-field">
                      <input name={enforcementField} type="checkbox"
                        defaultChecked={initialProject?.[enforcementField] ?? false}
                        aria-describedby={`${enforcementField}-help`} />
                      <span>Enforce {layer === "logical" ? "Logical" : "Dimensional"} coverage threshold</span>
                    </label>
                    <small id={`${enforcementField}-help`} className="field-help">On: reject results below the threshold after repair attempts. Off: allow them with a warning.</small>
                    </div>;
                  })()}
                  {group.fields.map((field) => (
                    <div key={field.name}>
                      <label htmlFor={field.name}>{field.label}{field.json ? <small>JSON object</small> : null}</label>
                      <textarea id={field.name} name={field.name} rows={3} maxLength={32 * 1024} spellCheck={!field.json}
                        readOnly={templateOverrides[field.name] == null}
                        value={templateOverrides[field.name] ?? (templates.data?.[field.name] == null ? "" : field.json
                          ? JSON.stringify(templates.data[field.name], null, 2) : String(templates.data[field.name]))}
                        onChange={(event) => setTemplateOverrides((current) => ({ ...current, [field.name]: event.target.value }))}
                        aria-invalid={validationError?.field === field.name} aria-describedby={validationError?.field === field.name ? "project-form-error" : undefined} />
                      <small className="field-help">{templateOverrides[field.name] == null ? "Using shared default template." : "Custom template for this Project. Copy to reuse in another Project."}</small>
                      <button type="button" className="button button-secondary button-small"
                        disabled={templateOverrides[field.name] == null && !templates.data}
                        onClick={() => {
                          const value = templates.data?.[field.name];
                          setTemplateOverrides((current) => ({ ...current, [field.name]: current[field.name] == null
                            ? (field.json ? JSON.stringify(value, null, 2) : String(value)) : null }));
                          onDirty?.();
                        }}>{templateOverrides[field.name] == null ? "Customize" : "Reset to defaults"}</button>
                    </div>
                  ))}
                </div>
              </details>
            ))}
            {templates.isError ? <p role="alert">Could not load default templates. <button type="button" className="text-action" onClick={() => void templates.refetch()}>Retry templates</button></p> : null}
            <details className="create-project-settings" onToggle={(event) => setAgentSettingsOpen(event.currentTarget.open)}>
              <summary>Agent defaults</summary>
              <div className="create-project-fields" onChange={() => setAgentDefaultsChanged(true)}>
                {capabilities.isPending ? <p className="field-help" aria-busy="true">Loading agent options…</p> : null}
                {capabilities.isError ? <p role="alert">Agent options could not be loaded. <button type="button" className="text-action" onClick={() => void capabilities.refetch()}>Retry agent options</button></p> : null}
                <label><span>Agent model</span>
                  <select name="agent_model" value={agentModelCode} onChange={(event) => {
                    setAgentModelCode(event.target.value);
                    setReasoningCode(capabilities.data?.models.find((model) => model.code === event.target.value)?.execution_profiles[0]?.reasoning_effort_codes[0] ?? "");
                  }}>
                    <option value="">Use defaults at run time</option>
                    {agentModelCode && !selectedModel ? <option value={agentModelCode}>{agentModelCode} (saved)</option> : null}
                    {capabilities.data?.models.map((model) => <option key={model.code} value={model.code}>{model.name}</option>)}
                  </select>
                </label>
                {selectedModel && capabilities.data ? <>
                  <label><span>Reasoning effort</span><select name="reasoning_effort" value={reasoningCode} onChange={(event) => setReasoningCode(event.target.value)}>
                    {reasoningOptions.map((effort) => <option key={effort.code} value={effort.code}>{reasoningEffortDisplayName(effort)}</option>)}
                  </select></label>
                  <div className="create-project-agent-limits">
                    <label><span>Maximum turns</span><input name="max_turns" type="number" min={capabilities.data.max_turns.minimum} max={capabilities.data.max_turns.maximum} defaultValue={initialProject?.default_max_turns ?? capabilities.data.max_turns.default} /></label>
                    <label><span>Validation retries</span><input name="validation_retries" type="number" min={capabilities.data.validation_retries.minimum} max={capabilities.data.validation_retries.maximum} defaultValue={initialProject?.default_validation_retry_count ?? capabilities.data.validation_retries.default} /></label>
                  </div>
                </> : null}
              </div>
            </details>
          </fieldset>
          {validationError ? <p id="project-form-error" role="alert">{validationError.message}</p> : null}
          {error ? <p role="alert">{errorMessages[errorCode] ?? (initialProject ? "Saving could not be confirmed. Your edits are preserved. Refresh saved settings before retrying." : "Creation could not be confirmed. Check the Projects list before retrying.")}</p> : null}
          {!hasTenantLock && !initialProject ? <p className="field-help">Acquire the Tenant Lock on <Link to="/tenants/$tenantId" params={{ tenantId: String(tenantId) }}>Home</Link> to save a Project.</p> : null}
          <footer className="dialog-actions">
            <p>{initialProject ? `Editing revision ${initialProject.project_revision}.` : "Created in the current Tenant at revision 1."}</p>
            <div>
              {onCancel ? <button className="button button-secondary" type="button" disabled={isPending} onClick={onCancel}>Cancel</button> : null}
              <button className="button button-primary" type="submit" disabled={!hasTenantLock || Boolean(disabledReason) || isPending} title={disabledReason ?? (!hasTenantLock ? "Tenant Lock required" : undefined)}>{initialProject ? isPending ? "Saving…" : "Save settings" : isPending ? "Creating…" : "Create Project"}</button>
            </div>
          </footer>
    </form>
  );
}
