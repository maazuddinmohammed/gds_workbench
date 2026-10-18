import { useRef } from "react";
import { useMutation } from "@tanstack/react-query";

import { trapDialogFocus, useDialogFocus } from "../../shared/dialog";
import type { WorkflowsApi } from "../workflows/api";
import type { SystemRecord } from "../tenants/api";
import type { CreateProjectCommand, ProjectCommandResult, ProjectsApi } from "./api";
import { ProjectForm } from "./ProjectForm";

export function CreateProjectDialog({
  api, tenantId, hasTenantLock, onClose, onCreated, systems,
}: {
  api: Pick<ProjectsApi, "createProject"> & Pick<WorkflowsApi, "readAgentCapabilities">;
  tenantId: number;
  hasTenantLock: boolean;
  onClose: () => void;
  onCreated: (created: ProjectCommandResult) => void;
  systems: SystemRecord[];
}) {
  const nameInput = useRef<HTMLInputElement>(null);
  const mutation = useMutation({
    mutationFn: (command: CreateProjectCommand) => api.createProject(tenantId, command),
    retry: false,
    onSuccess: onCreated,
  });
  useDialogFocus(nameInput);
  return (
    <div className="dialog-scrim" role="presentation">
      <section className="run-configuration-dialog create-project-dialog" role="dialog" aria-modal="true"
        aria-labelledby="create-project-heading" aria-busy={mutation.isPending}
        onKeyDown={(event) => { trapDialogFocus(event); if (event.key === "Escape" && !mutation.isPending) onClose(); }}>
        <header className="drawer-header">
          <h2 id="create-project-heading">Create Project</h2>
          <button className="panel-close" type="button" aria-label="Close Project creation" disabled={mutation.isPending} onClick={onClose}>×</button>
        </header>
        <ProjectForm api={api} tenantId={tenantId} hasTenantLock={hasTenantLock} nameInput={nameInput} systems={systems}
          isPending={mutation.isPending} error={mutation.error} onCancel={onClose}
          onSubmit={(command) => mutation.mutate(command)} />
      </section>
    </div>
  );
}
