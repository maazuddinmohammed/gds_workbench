import { useEffect, useMemo, useRef, useState } from "react";
import { useForm, useStore } from "@tanstack/react-form";
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import {
  flexRender,
  getCoreRowModel,
  useReactTable,
  type ColumnDef,
} from "@tanstack/react-table";

import { ApiError } from "../../core/http";
import type { ModelDetail } from "../models/api";
import {
  loadAssignableTenantPromptVersions,
  promptQueryKeys,
  type ModelPromptAssignmentState,
  type PromptAssignmentTarget,
  type PromptsApi,
} from "./api";
import { humanize, modeLabel, shortDigest } from "./PromptsLedger";

export function ModelPromptSettings({
  api,
  tenantId,
  model,
  hasTenantLock,
  hasAppPermission,
}: {
  api: PromptsApi;
  tenantId: number;
  model: ModelDetail;
  hasTenantLock: boolean;
  hasAppPermission: boolean;
}) {
  const [configure, setConfigure] = useState<ModelPromptAssignmentState | null>(null);
  const queryClient = useQueryClient();
  const query = useQuery({
    queryKey: promptQueryKeys.modelAssignments(tenantId, model.model_id),
    queryFn: () => api.listModelPromptAssignments(tenantId, model.model_id),
  });
  const canAssign = hasTenantLock && hasAppPermission;
  const permissionLabel = !hasAppPermission
    ? "Architect permission required to assign Prompts"
    : !hasTenantLock
      ? "Tenant Lock required to assign Prompts"
      : "Tenant Lock held · Prompt assignment available";
  const columns = useMemo<ColumnDef<ModelPromptAssignmentState>[]>(() => [
    {
      id: "stage",
      header: "Workflow / stage",
      cell: ({ row }) => (
        <span className="prompt-stage-cell">
          <strong>{humanize(row.original.model_workflow)}</strong>
          <small>{row.original.workflow_stage_name} · {row.original.workflow_stage_code}</small>
        </span>
      ),
    },
    {
      accessorKey: "workflow_execution_mode",
      header: "Mode",
      cell: ({ getValue }) => modeLabel(getValue<ModelPromptAssignmentState["workflow_execution_mode"]>()),
    },
    {
      id: "effective",
      header: "Effective Prompt",
      cell: ({ row }) => row.original.effective_assignment ? (
        <AssignmentIdentity assignment={row.original.effective_assignment} />
      ) : (
        <span className="prompt-assignment-none">No effective Prompt</span>
      ),
    },
    {
      id: "provenance",
      header: "Version / provenance",
      cell: ({ row }) => row.original.effective_assignment ? (
        <span className="prompt-assignment-provenance">
          <strong>v{row.original.effective_assignment.prompt_template_version_number}</strong>
          <code title={row.original.effective_assignment.prompt_template_digest}>
            {shortDigest(row.original.effective_assignment.prompt_template_digest)}
          </code>
          <small>{sourceLabel(row.original.effective_source)}</small>
        </span>
      ) : (
        <span className="prompt-assignment-provenance"><small>No configured fallback</small></span>
      ),
    },
    {
      id: "override",
      header: "Model override",
      cell: ({ row }) => row.original.model_assignment ? (
        <span className="status-badge is-warning">Configured</span>
      ) : (
        <span className="status-badge is-neutral">Use global</span>
      ),
    },
    {
      id: "action",
      header: "",
      cell: ({ row }) => (
        <button
          className="button button-secondary button-small"
          type="button"
          disabled={!canAssign}
          title={permissionLabel}
          aria-label={`Configure ${row.original.workflow_stage_name} Prompt`}
          onClick={() => setConfigure(row.original)}
        >
          Configure
        </button>
      ),
    },
  ], [canAssign, permissionLabel]);
  const table = useReactTable({
    data: query.data?.items ?? [],
    columns,
    getCoreRowModel: getCoreRowModel(),
  });

  return (
    <section className="model-prompt-settings page-enter" aria-labelledby="model-prompts-heading">
      <header className="model-prompts-commandbar">
        <div>
          <p className="eyebrow">Model Settings</p>
          <h1 id="model-prompts-heading">Prompts</h1>
          <p>Review the exact effective Prompt version for every agentic workflow stage.</p>
        </div>
        <div>
          <span className={canAssign ? "lock-context is-held" : "lock-context"}>
            {permissionLabel}
          </span>
          <button
            className="button button-secondary button-small"
            type="button"
            disabled={query.isFetching}
            onClick={() => void Promise.all([
              query.refetch(),
              queryClient.invalidateQueries({ queryKey: ["tenant-home", tenantId] }),
            ])}
          >
            {query.isFetching ? "Refreshing…" : "Refresh"}
          </button>
        </div>
      </header>
      <div className="model-prompts-context">
        <strong>{model.model_name} · revision {model.model_revision}</strong>
        <span>Use global removes the Model override. Tenant versions must be active and published.</span>
      </div>

      {query.isPending ? (
        <div className="surface-state" aria-busy="true">Loading effective Prompt assignments…</div>
      ) : query.error instanceof ApiError && query.error.status === 403 ? (
        <div className="surface-state is-error" role="alert">
          You do not have permission to view this Model's Prompt assignments.
        </div>
      ) : query.isError ? (
        <div className="surface-state is-error" role="alert">
          Effective Prompt assignments could not be loaded.
        </div>
      ) : query.data.items.length === 0 ? (
        <div className="empty-state compact">No agentic workflow stages are available for this Model.</div>
      ) : (
        <div className="table-scroll model-prompts-table-scroll">
          <table aria-label="Effective Model Prompt assignments">
            <thead>
              {table.getHeaderGroups().map((group) => (
                <tr key={group.id}>
                  {group.headers.map((header) => (
                    <th key={header.id}>
                      {header.isPlaceholder
                        ? null
                        : flexRender(header.column.columnDef.header, header.getContext())}
                    </th>
                  ))}
                </tr>
              ))}
            </thead>
            <tbody>
              {table.getRowModel().rows.map((row) => (
                <tr key={row.id}>
                  {row.getVisibleCells().map((cell) => (
                    <td key={cell.id}>{flexRender(cell.column.columnDef.cell, cell.getContext())}</td>
                  ))}
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      )}

      <section className="global-default-gap" aria-labelledby="global-default-heading">
        <div>
          <strong id="global-default-heading">Global defaults are read-only here</strong>
          <span>The API exposes effective global assignments but no global-default mutation route.</span>
        </div>
        <button className="button button-secondary button-small" type="button" disabled>
          Global assignment unavailable
        </button>
      </section>

      {configure ? (
        <PromptAssignmentDialog
          api={api}
          tenantId={tenantId}
          modelId={model.model_id}
          assignment={configure}
          onClose={() => setConfigure(null)}
          onSaved={async () => {
            setConfigure(null);
            await Promise.all([
              queryClient.invalidateQueries({
                queryKey: promptQueryKeys.modelAssignments(tenantId, model.model_id),
              }),
              queryClient.invalidateQueries({ queryKey: ["prompt-templates", tenantId] }),
            ]);
          }}
        />
      ) : null}
    </section>
  );
}

function PromptAssignmentDialog({
  api,
  tenantId,
  modelId,
  assignment,
  onClose,
  onSaved,
}: {
  api: PromptsApi;
  tenantId: number;
  modelId: number;
  assignment: ModelPromptAssignmentState;
  onClose: () => void;
  onSaved: () => Promise<void>;
}) {
  const closeButton = useRef<HTMLButtonElement>(null);
  const currentIsTenant = assignment.model_assignment?.prompt_template_ownership_scope === "tenant";
  const currentValue = currentIsTenant && assignment.model_assignment
    ? `version:${assignment.model_assignment.prompt_template_version_id}`
    : assignment.model_assignment
      ? `unsupported:${assignment.model_assignment.prompt_template_version_id}`
      : "global";
  const versionsQuery = useQuery({
    queryKey: promptQueryKeys.assignableVersions(tenantId, assignment.workflow_stage_id),
    queryFn: () => loadAssignableTenantPromptVersions(
      api,
      tenantId,
      assignment.workflow_stage_id,
      assignment.workflow_stage_code,
    ),
  });
  const mutation = useMutation({
    mutationFn: (promptTemplateVersionId: number | null) => api.setModelPromptAssignment(
      tenantId,
      modelId,
      assignment.workflow_stage_id,
      {
        prompt_template_version_id: promptTemplateVersionId,
        expected_prompt_assignment_id: assignment.model_assignment?.prompt_assignment_id ?? null,
      },
    ),
    onSuccess: onSaved,
  });
  const form = useForm({
    defaultValues: { selection: currentValue },
    onSubmit: ({ value }) => {
      mutation.mutate(value.selection === "global"
        ? null
        : Number(value.selection.replace("version:", "")));
    },
  });
  const selection = useStore(form.store, (state) => state.values.selection);
  const isDirty = useStore(form.store, (state) => state.isDirty);
  const selectedVersionId = selection.startsWith("version:")
    ? Number(selection.replace("version:", ""))
    : null;
  const selectionValid = selection === "global"
    || versionsQuery.data?.some((version) => (
      version.promptTemplateVersionId === selectedVersionId
    )) === true;

  useEffect(() => closeButton.current?.focus(), []);

  return (
    <div className="dialog-scrim prompt-dialog-scrim" role="presentation">
      <section
        className="run-configuration-dialog prompt-assignment-dialog"
        role="dialog"
        aria-modal="true"
        aria-labelledby="prompt-assignment-heading"
        onKeyDown={(event) => {
          if (event.key === "Escape") onClose();
        }}
      >
        <header className="drawer-header">
          <div>
            <small>{humanize(assignment.model_workflow)} · {modeLabel(assignment.workflow_execution_mode)}</small>
            <h2 id="prompt-assignment-heading">{assignment.workflow_stage_name}</h2>
          </div>
          <button
            ref={closeButton}
            className="panel-close"
            type="button"
            aria-label={`Close ${assignment.workflow_stage_name} Prompt assignment`}
            onClick={onClose}
          >
            <span aria-hidden="true">×</span>
          </button>
        </header>
        <form
          className="prompt-assignment-form"
          onSubmit={(event) => {
            event.preventDefault();
            event.stopPropagation();
            void form.handleSubmit();
          }}
        >
          <form.Field name="selection">
            {(field) => (
              <fieldset className="prompt-assignment-options">
                <legend>Effective Prompt source</legend>
                {assignment.model_assignment
                  && assignment.model_assignment.prompt_template_ownership_scope === "global" ? (
                    <label className="is-unavailable">
                      <input
                        type="radio"
                        name={field.name}
                        value={currentValue}
                        checked={field.state.value === currentValue}
                        readOnly
                      />
                      <span>
                        <strong>Existing global Model override</strong>
                        <small>This legacy shape is visible but cannot be newly selected here.</small>
                      </span>
                    </label>
                  ) : null}
                <label>
                  <input
                    type="radio"
                    name={field.name}
                    value="global"
                    checked={field.state.value === "global"}
                    onChange={() => field.handleChange("global")}
                  />
                  <span>
                    <strong>Use global</strong>
                    <small>
                      {assignment.global_assignment
                        ? `${assignment.global_assignment.prompt_template_name} · v${assignment.global_assignment.prompt_template_version_number}`
                        : "No global default is configured; effective source becomes none."}
                    </small>
                  </span>
                </label>
                {versionsQuery.data?.map((version) => (
                  <label key={version.promptTemplateVersionId}>
                    <input
                      type="radio"
                      name={field.name}
                      value={`version:${version.promptTemplateVersionId}`}
                      checked={field.state.value === `version:${version.promptTemplateVersionId}`}
                      onChange={() => field.handleChange(`version:${version.promptTemplateVersionId}`)}
                    />
                    <span>
                      <strong>{version.promptTemplateName} · v{version.versionNumber}</strong>
                      <small>{version.promptTemplateCode} · {shortDigest(version.digest)}</small>
                    </span>
                  </label>
                ))}
              </fieldset>
            )}
          </form.Field>
          {versionsQuery.isPending ? (
            <div className="surface-state compact" aria-busy="true">Loading allowed Tenant versions…</div>
          ) : versionsQuery.error instanceof ApiError && versionsQuery.error.status === 403 ? (
            <p className="inline-error" role="alert">You do not have permission to load assignable Prompt versions.</p>
          ) : versionsQuery.isError ? (
            <p className="inline-error" role="alert">Allowed Tenant Prompt versions could not be loaded.</p>
          ) : versionsQuery.data.length === 0 ? (
            <p className="prompt-assignment-empty">No active published Tenant versions are available for this stage.</p>
          ) : null}
          {mutation.isError ? (
            <p className="inline-error" role="alert">
              The Prompt assignment could not be saved. Refresh before retrying.
            </p>
          ) : null}
          <footer className="dialog-actions">
            <p>The API rechecks Tenant Lock, role, Model ownership, version status, and assignment fencing.</p>
            <div>
              <button className="button button-secondary button-small" type="button" onClick={onClose}>
                Cancel
              </button>
              <button
                className="button button-primary button-small"
                type="submit"
                disabled={
                  !isDirty
                  || !selectionValid
                  || versionsQuery.isPending
                  || versionsQuery.isError
                  || mutation.isPending
                }
              >
                {mutation.isPending ? "Saving…" : "Save assignment"}
              </button>
            </div>
          </footer>
        </form>
      </section>
    </div>
  );
}

function AssignmentIdentity({ assignment }: { assignment: PromptAssignmentTarget }) {
  return (
    <span className="prompt-template-name">
      <strong>{assignment.prompt_template_name}</strong>
      <code>{assignment.prompt_template_code}</code>
    </span>
  );
}

function sourceLabel(value: ModelPromptAssignmentState["effective_source"]): string {
  return value === "model_default"
    ? "Model override"
    : value === "global_default"
      ? "Global default"
      : "None";
}
