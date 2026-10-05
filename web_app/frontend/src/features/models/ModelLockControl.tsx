import { useMutation, useQueryClient } from "@tanstack/react-query";
import { ApiError } from "../../core/http";
import type { TenantHomeRecord } from "../tenants/api";
import { canAuthorModels } from "../tenants/presentation";
import type { ModelDetail, ModelsApi } from "./api";

export function ModelLockControl({ api, home, model }: {
  api: Partial<Pick<ModelsApi, "setModelLock">>;
  home: TenantHomeRecord;
  model: Pick<ModelDetail, "tenant_id" | "model_id" | "model_revision" | "is_locked" | "is_active"> | undefined;
}) {
  const client = useQueryClient();
  const mutation = useMutation({
    mutationFn: async () => {
      if (!api.setModelLock || !model) throw new Error("Model lock unavailable");
      return api.setModelLock(model.tenant_id, model.model_id, {
        expected_model_revision: model.model_revision, is_locked: !model.is_locked,
      });
    },
    retry: false,
    onSuccess: async (result) => {
      await client.invalidateQueries({ predicate: (query) => query.queryKey[1] === result.tenant_id });
    },
  });
  const reason = !model ? "Select a Model first." : !model.is_active ? "Archived Models are read-only."
    : !canAuthorModels(home.tenant.effective_role) ? "Architect permission required."
      : !home.lock.owned_by_current_principal ? "Acquire the Tenant Lock first."
        : !api.setModelLock ? "Model lock unavailable." : undefined;
  const error = mutation.error instanceof ApiError && mutation.error.code === "model_workflow_conflict"
    ? "Finish or cancel queued and running workflows before locking the Model."
    : "Model lock could not be changed. Refresh the Model and retry.";
  return <div className="models-lock-action">
    <button className="button button-secondary button-small" type="button" disabled={!!reason || mutation.isPending}
      title={reason ?? (model?.is_locked ? "Allow Model changes and workflows" : "Block all Model changes and workflows")}
      onClick={() => mutation.mutate()}>{mutation.isPending ? "Saving…" : model?.is_locked ? "Unlock Model" : "Lock Model"}</button>
    {mutation.isError ? <p role="alert">{error}</p> : null}
  </div>;
}
