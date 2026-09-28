import { useState, type FormEvent, type RefObject } from "react";
import { useQuery } from "@tanstack/react-query";
import { Link } from "@tanstack/react-router";

import { ApiError } from "../../core/http";
import type { JsonObject } from "../../shared/contracts";
import { reasoningEffortDisplayName, type WorkflowsApi } from "../workflows/api";
import type { CreateModelCommand, ModelDetail } from "./api";

const layerFields = [
  { title: "Silver settings", fields: [
    { name: "silver_model_naming_instructions", label: "Silver naming instructions", json: false },
    { name: "silver_model_audit_columns_template", label: "Silver audit columns template", json: true },
  ] },
  { title: "Gold settings", fields: [
    { name: "gold_model_naming_instructions", label: "Gold naming instructions", json: false },
    { name: "gold_model_technical_columns_template", label: "Gold technical columns template", json: true },
    { name: "gold_model_audit_columns_template", label: "Gold audit columns template", json: true },
  ] },
] as const;

export function ModelForm({
  api, tenantId, hasTenantLock, initialModel, disabledReason, isPending, error,
  onSubmit, onCancel, onDirty, nameInput,
}: {
  api: Pick<WorkflowsApi, "readAgentCapabilities">;
  tenantId: number;
  hasTenantLock: boolean;
  initialModel?: ModelDetail;
  disabledReason?: string | undefined;
  isPending: boolean;
  error: unknown;
  onSubmit: (command: CreateModelCommand) => void;
  onCancel?: () => void;
  onDirty?: () => void;
  nameInput?: RefObject<HTMLInputElement | null>;
}) {
  const [logicalSchemas, setLogicalSchemas] = useState(() => initialModel?.logical_schemas.length
    ? initialModel.logical_schemas.map((row) => ({ ...row, description: row.description ?? "" }))
    : [{ schema_name: "", description: "" }]);
  const [dimensionalSchemas, setDimensionalSchemas] = useState(() => initialModel?.dimensional_schemas.length
    ? initialModel.dimensional_schemas.map((row) => ({ ...row, description: row.description ?? "" }))
    : [{ schema_name: "", description: "" }]);
  const [agentModelCode, setAgentModelCode] = useState(initialModel?.default_agent_model_code ?? "");
  const [reasoningCode, setReasoningCode] = useState(initialModel?.default_reasoning_effort_code ?? "");
  const [agentDefaultsChanged, setAgentDefaultsChanged] = useState(false);
  const [agentSettingsOpen, setAgentSettingsOpen] = useState(false);
  const [validationError, setValidationError] = useState<{ field: string; message: string } | null>(null);
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
    const command: CreateModelCommand = {
      model_name: text("model_name"),
      model_description: text("model_description") || null,
      logical_schemas: logicalSchemas.filter((item) => item.schema_name.trim() || item.description.trim()).map((item) => ({ schema_name: item.schema_name.trim(), description: item.description.trim() || null })),
      dimensional_schemas: dimensionalSchemas.filter((item) => item.schema_name.trim() || item.description.trim()).map((item) => ({ schema_name: item.schema_name.trim(), description: item.description.trim() || null })),
      silver_model_naming_instructions: null,
      silver_model_audit_columns_template: null,
      gold_model_naming_instructions: null,
      gold_model_technical_columns_template: null,
      gold_model_audit_columns_template: null,
      default_agent_sdk_code: initialModel?.default_agent_sdk_code ?? null,
      default_agent_provider_code: initialModel?.default_agent_provider_code ?? null,
      default_agent_model_code: initialModel?.default_agent_model_code ?? null,
      default_reasoning_effort_code: initialModel?.default_reasoning_effort_code ?? null,
      default_max_turns: initialModel?.default_max_turns ?? null,
      default_validation_retry_count: initialModel?.default_validation_retry_count ?? null,
    };
    if (!command.model_name || command.model_name.length > 255) {
      invalid("model_name", "Enter a Model name of 1–255 characters.");
      return;
    }
    if ((command.model_description?.length ?? 0) > 2000) {
      invalid("model_description", "Keep the description within 2,000 characters.");
      return;
    }
    for (const layer of ["logical", "dimensional"] as const) {
      const schemas = command[`${layer}_schemas`];
      if (schemas.some((item) => !item.schema_name || item.schema_name.length > 400) || new Set(schemas.map((item) => item.schema_name.toLowerCase())).size !== schemas.length) {
        invalid(`${layer}_schema_0`, "Use a distinct, nonblank name for each configured schema.");
        return;
      }
    }
    for (const group of layerFields) {
      for (const field of group.fields) {
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
    if (agentModelCode && (!initialModel || agentDefaultsChanged)) {
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
    model_name_conflict: "This Tenant already has a Model with that name, including archived Models. Choose another name.",
    authorization_denied: initialModel ? "Architect permission is required to update Model settings." : "Only Super Admins and Tenant Admins can create Models.",
    tenant_lock_required: "Acquire the Tenant Lock on Home, then return to save this Model.",
    tenant_locked: "Another user holds the Tenant Lock. Acquire it on Home before retrying.",
    tenant_not_found: "This Tenant is no longer available to you.",
    model_revision_conflict: "The Model changed. Your edits are preserved. Refresh saved settings before retrying.",
    model_schema_conflict: "An existing Entity still uses a removed or renamed schema, including inactive Entities. Restore its schema name before saving. Your edits are preserved.",
    model_not_found: "This Model is no longer available for editing. Refresh saved settings.",
    invalid_request: "Some settings are no longer valid. Check the fields and agent defaults, then retry.",
  };

  return (
    <form noValidate onSubmit={submit} onChange={onDirty} aria-busy={isPending}>
          <fieldset className="create-model-fields" disabled={isPending || Boolean(disabledReason)}>
            <label>
              <span>Model name <small>Required</small></span>
              <input ref={nameInput} name="model_name" required maxLength={255} autoComplete="off" defaultValue={initialModel?.model_name ?? ""}
                aria-invalid={validationError?.field === "model_name"} aria-describedby={validationError?.field === "model_name" ? "model-form-error" : undefined} />
            </label>
            <label>
              <span>Description <small>Optional</small></span>
              <textarea name="model_description" rows={3} maxLength={2000} defaultValue={initialModel?.model_description ?? ""} />
            </label>
            {!initialModel ? <p className="field-help">Add source Objects to Input Scope after creating the Model.</p> : null}
            {([{ layer: "logical", title: "Logical schemas", rows: logicalSchemas, update: setLogicalSchemas }, { layer: "dimensional", title: "Dimensional schemas", rows: dimensionalSchemas, update: setDimensionalSchemas }] as const).map(({ layer, title, rows, update }) => <details key={layer} className="create-model-settings"><summary>{title}<span>Configure before generation</span></summary><div className="create-model-fields">
              <p className="field-help">Entities use one of these schemas. Export preserves each Entity’s saved schema.</p>
              {rows.map((row, index) => <fieldset key={index} className="create-model-fields"><label><span>Schema name</span><input name={`${layer}_schema_${index}`} value={row.schema_name} maxLength={400} onChange={(event) => update(rows.map((item, position) => position === index ? { ...item, schema_name: event.target.value } : item))} /></label><label><span>Description</span><textarea value={row.description} maxLength={2000} rows={2} onChange={(event) => update(rows.map((item, position) => position === index ? { ...item, description: event.target.value } : item))} /></label><button type="button" className="text-action" onClick={() => { update(rows.filter((_, position) => position !== index)); onDirty?.(); }}>Remove schema</button></fieldset>)}
              <button type="button" className="button button-secondary button-small" disabled={rows.length >= 100} onClick={() => { update([...rows, { schema_name: "", description: "" }]); onDirty?.(); }}>Add schema</button>
            </div></details>)}
            {layerFields.map((group) => (
              <details key={group.title} className="create-model-settings">
                <summary>{group.title}<span>Optional</span></summary>
                <div className="create-model-fields">
                  {group.fields.map((field) => (
                    <label key={field.name}>
                      <span>{field.label}{field.json ? <small>JSON object</small> : null}</span>
                      <textarea name={field.name} rows={3} maxLength={32 * 1024} spellCheck={!field.json}
                        defaultValue={initialModel?.[field.name] == null ? "" : field.json ? JSON.stringify(initialModel[field.name], null, 2) : String(initialModel[field.name])}
                        aria-invalid={validationError?.field === field.name} aria-describedby={validationError?.field === field.name ? "model-form-error" : undefined} />
                    </label>
                  ))}
                </div>
              </details>
            ))}
            <details className="create-model-settings" onToggle={(event) => setAgentSettingsOpen(event.currentTarget.open)}>
              <summary>Agent defaults<span>Optional</span></summary>
              <div className="create-model-fields" onChange={() => setAgentDefaultsChanged(true)}>
                <p className="field-help">Leave unset to use the available defaults when starting a Workflow Run.</p>
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
                  <div className="create-model-agent-limits">
                    <label><span>Maximum turns</span><input name="max_turns" type="number" min={capabilities.data.max_turns.minimum} max={capabilities.data.max_turns.maximum} defaultValue={initialModel?.default_max_turns ?? capabilities.data.max_turns.default} /></label>
                    <label><span>Validation retries</span><input name="validation_retries" type="number" min={capabilities.data.validation_retries.minimum} max={capabilities.data.validation_retries.maximum} defaultValue={initialModel?.default_validation_retry_count ?? capabilities.data.validation_retries.default} /></label>
                  </div>
                </> : null}
              </div>
            </details>
          </fieldset>
          {validationError ? <p id="model-form-error" role="alert">{validationError.message}</p> : null}
          {error ? <p role="alert">{errorMessages[errorCode] ?? (initialModel ? "Saving could not be confirmed. Your edits are preserved. Refresh saved settings before retrying." : "Creation could not be confirmed. Check the Models list before retrying.")}</p> : null}
          {!hasTenantLock ? <p className="field-help">Acquire the Tenant Lock on <Link to="/tenants/$tenantId" params={{ tenantId: String(tenantId) }}>Home</Link> to save a Model.</p> : null}
          <footer className="dialog-actions">
            <p>{initialModel ? `Editing revision ${initialModel.model_revision}.` : "Created in the current Tenant at revision 1."}</p>
            <div>
              {onCancel ? <button className="button button-secondary" type="button" disabled={isPending} onClick={onCancel}>Cancel</button> : null}
              <button className="button button-primary" type="submit" disabled={!hasTenantLock || Boolean(disabledReason) || isPending} title={disabledReason ?? (!hasTenantLock ? "Tenant Lock required" : undefined)}>{initialModel ? isPending ? "Saving…" : "Save settings" : isPending ? "Creating…" : "Create Model"}</button>
            </div>
          </footer>
    </form>
  );
}
