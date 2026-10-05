import { useEffect, useRef, useState } from "react";
import { useMutation, useQueryClient } from "@tanstack/react-query";
import { Link, useSearch } from "@tanstack/react-router";
import { WorkspaceToolbar } from "../../shared/ui";

import type { TenantHomeRecord, TenantsApi } from "../tenants/api";
import { canAuthorModels } from "../tenants/presentation";
import type { WorkflowsApi } from "../workflows/api";
import type { CreateModelCommand, ModelDetail, ModelsApi } from "./api";
import { ModelForm } from "./ModelForm";

export function ModelSettingsScreen({ api, home, model }: {
  api: Pick<ModelsApi, "readModel" | "updateModel"> & Pick<WorkflowsApi, "readAgentCapabilities"> & Pick<TenantsApi, "readTenantHome">;
  home: TenantHomeRecord;
  model: ModelDetail;
}) {
  const client = useQueryClient();
  const heading = useRef<HTMLHeadingElement>(null);
  const [initialModel, setInitialModel] = useState(model);
  const [formVersion, setFormVersion] = useState(0);
  const [dirty, setDirty] = useState(false);
  const [confirmRefresh, setConfirmRefresh] = useState(false);
  const [refreshing, setRefreshing] = useState(false);
  const [refreshFailed, setRefreshFailed] = useState(false);
  const [needsRefresh, setNeedsRefresh] = useState(false);
  const [savedRevision, setSavedRevision] = useState<number | null>(null);
  const tenantId = model.tenant_id;
  const modelId = model.model_id;
  const hasTenantLock = home.lock.owned_by_current_principal === true;
  const stale = initialModel.model_revision !== model.model_revision;
  const disabledReason = model.is_locked ? "Model locked. Unlock it before changing settings." : !model.is_active ? "Archived Models are read-only."
    : !canAuthorModels(home.tenant.effective_role) ? "Architect permission required to update Model settings."
      : !hasTenantLock ? "Tenant Lock required to update Model settings."
        : stale || needsRefresh ? "The Model changed. Your edits are preserved. Refresh saved settings before retrying."
          : undefined;

  useEffect(() => { heading.current?.focus(); }, []);

  async function refresh() {
    setRefreshing(true);
    setRefreshFailed(false);
    setConfirmRefresh(false);
    try {
      const [current, currentHome] = await Promise.all([
        api.readModel(tenantId, modelId), api.readTenantHome(tenantId),
      ]);
      client.setQueryData(["model", tenantId, modelId], current);
      client.setQueryData(["tenant-home", tenantId], currentHome);
      setInitialModel(current);
      setFormVersion((version) => version + 1);
      setDirty(false);
      setNeedsRefresh(false);
      heading.current?.focus();
    } catch {
      setRefreshFailed(true);
    } finally {
      setRefreshing(false);
    }
  }

  const mutation = useMutation({
    mutationFn: (command: CreateModelCommand) => api.updateModel(tenantId, modelId, {
      ...command, expected_model_revision: initialModel.model_revision,
    }),
    retry: false,
    onSuccess: async (result) => {
      setSavedRevision(result.model_revision);
      setNeedsRefresh(true);
      await client.invalidateQueries({ predicate: (query) => query.queryKey[1] === tenantId, refetchType: "none" });
      await refresh();
    },
  });
  const busy = mutation.isPending || refreshing;

  return <section className="model-settings-page page-enter" aria-labelledby="model-settings-heading">
    <h1 className="model-section-title sr-only" id="model-settings-heading" ref={heading} tabIndex={-1}>Definition</h1>
    <WorkspaceToolbar actions={
      <button className="button button-secondary button-small" type="button" disabled={busy} onClick={() => {
        if (dirty) setConfirmRefresh(true);
        else { mutation.reset(); void refresh(); }
      }}>{refreshing ? "Refreshing…" : "Refresh saved settings"}</button>
    }><ModelSettingsTabs model={model} active="definition" /></WorkspaceToolbar>
    {disabledReason ? <p className="lock-context">{disabledReason}</p> : null}
    {confirmRefresh ? <div className="model-settings-refresh" role="alert">
      <p>Refreshing replaces your unsaved edits with the saved Model settings.</p>
      <button className="button button-secondary button-small" type="button" onClick={() => setConfirmRefresh(false)}>Keep editing</button>
      <button className="button button-secondary button-small" type="button" onClick={() => { mutation.reset(); void refresh(); }}>Discard edits and refresh</button>
    </div> : null}
    {refreshFailed ? <p role="alert">Saved settings could not be loaded. Your edits are preserved. Retry Refresh saved settings.</p> : null}
    {savedRevision !== null ? <p role="status">Model settings saved at revision {savedRevision}.</p> : null}
    <ModelForm key={`${modelId}:${formVersion}`} api={api} tenantId={tenantId} initialModel={initialModel}
      systems={home.systems}
      hasTenantLock={hasTenantLock} disabledReason={disabledReason} isPending={busy} error={mutation.error}
      onDirty={() => { setDirty(true); setSavedRevision(null); }} onSubmit={(command) => mutation.mutate(command)} />
  </section>;
}

export function ModelSettingsTabs({ model, active }: { model: ModelDetail; active: "definition" | "prompts" }) {
  const { layer } = useSearch({ strict: false });
  const params = { tenantId: String(model.tenant_id), modelId: String(model.model_id) };
  return <nav className="workspace-tabs" aria-label="Model settings pages">
    <Link className={active === "definition" ? "is-active" : ""} to="/tenants/$tenantId/models/$modelId/settings"
      params={params} search={layer ? { layer } : {}} aria-current={active === "definition" ? "page" : undefined}>Definition</Link>
    <Link className={active === "prompts" ? "is-active" : ""} to="/tenants/$tenantId/models/$modelId/settings/prompts"
      params={params} search={layer ? { layer } : {}} aria-current={active === "prompts" ? "page" : undefined}>Prompts</Link>
  </nav>;
}
