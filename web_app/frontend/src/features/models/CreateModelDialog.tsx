import { useRef } from "react";
import { useMutation } from "@tanstack/react-query";

import { trapDialogFocus, useDialogFocus } from "../../shared/dialog";
import type { WorkflowsApi } from "../workflows/api";
import type { CreateModelCommand, ModelCommandResult, ModelsApi } from "./api";
import { ModelForm } from "./ModelForm";

export function CreateModelDialog({
  api, tenantId, hasTenantLock, onClose, onCreated,
}: {
  api: Pick<ModelsApi, "createModel"> & Pick<WorkflowsApi, "readAgentCapabilities">;
  tenantId: number;
  hasTenantLock: boolean;
  onClose: () => void;
  onCreated: (created: ModelCommandResult) => void;
}) {
  const nameInput = useRef<HTMLInputElement>(null);
  const mutation = useMutation({
    mutationFn: (command: CreateModelCommand) => api.createModel(tenantId, command),
    retry: false,
    onSuccess: onCreated,
  });
  useDialogFocus(nameInput);
  return (
    <div className="dialog-scrim" role="presentation">
      <section className="run-configuration-dialog create-model-dialog" role="dialog" aria-modal="true"
        aria-labelledby="create-model-heading" aria-busy={mutation.isPending}
        onKeyDown={(event) => { trapDialogFocus(event); if (event.key === "Escape" && !mutation.isPending) onClose(); }}>
        <header className="drawer-header">
          <h2 id="create-model-heading">Create Model</h2>
          <button className="panel-close" type="button" aria-label="Close Model creation" disabled={mutation.isPending} onClick={onClose}>×</button>
        </header>
        <ModelForm api={api} tenantId={tenantId} hasTenantLock={hasTenantLock} nameInput={nameInput}
          isPending={mutation.isPending} error={mutation.error} onCancel={onClose}
          onSubmit={(command) => mutation.mutate(command)} />
      </section>
    </div>
  );
}
