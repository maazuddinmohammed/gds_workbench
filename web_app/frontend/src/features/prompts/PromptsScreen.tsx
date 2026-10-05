import { useMemo, useState } from "react";
import { useForm } from "@tanstack/react-form";
import { useQuery, useQueryClient } from "@tanstack/react-query";
import { useNavigate } from "@tanstack/react-router";

import { WorkflowCommandCenter, WorkflowCommandTools, WorkflowFilters } from "../workflows/WorkflowCommandCenter";
import { ApiError } from "../../core/http";
import type {
  WorkflowExecutionMode,
} from "../workflows/api";
import {
  promptQueryKeys,
  type PromptStage,
  type PromptTemplateFilters,
  type PromptWorkflow,
  type PromptsApi,
} from "./api";
import { CreatePromptDialog } from "./PromptTemplateDialogs";
import { PromptVariables } from "./PromptVariables";
import {
  PromptsLedger,
  humanize,
  modeLabel,
  type PromptVisibilityFilter,
} from "./PromptsLedger";

const WORKFLOWS: PromptWorkflow[] = [
  "profiling",
  "metadata_enrichment",
  "metadata_enrichment_object",
  "metadata_enrichment_attribute",
  "analysis",
  "conceptual",
  "logical",
  "dimensional",
  "mapping",
  "code_generation",
  "validation",
];

const EXECUTION_MODES: WorkflowExecutionMode[] = [
  "one_shot",
  "tool_assisted",
];

export function PromptsScreen({
  api,
  tenantId,
  canAuthorPrompts,
  isSuperAdmin,
  hasTenantLock,
}: {
  api: PromptsApi;
  tenantId: number;
  tenantName: string;
  canAuthorPrompts: boolean;
  isSuperAdmin: boolean;
  hasTenantLock: boolean;
}) {
  const queryClient = useQueryClient();
  const navigate = useNavigate();
  const [filters, setFilters] = useState<PromptTemplateFilters>({});
  const [visibility, setVisibility] = useState<PromptVisibilityFilter>("");
  const [cursor, setCursor] = useState<string | undefined>();
  const [cursorHistory, setCursorHistory] = useState<(string | undefined)[]>([]);
  const [createOpen, setCreateOpen] = useState(false);
  const stagesQuery = useQuery({
    queryKey: promptQueryKeys.stages(tenantId),
    queryFn: () => api.listPromptStages(tenantId),
  });
  const templatesQuery = useQuery({
    queryKey: promptQueryKeys.templates(tenantId, filters, cursor),
    queryFn: () => api.listPromptTemplates(tenantId, filters, 50, cursor),
  });
  const filterForm = useForm({
    defaultValues: {
      workflow: "",
      mode: "",
      stageCode: "",
      status: "",
    },
    onSubmit: ({ value }) => {
      const next: PromptTemplateFilters = {};
      if (value.workflow) next.workflow = value.workflow as PromptWorkflow;
      if (value.mode) next.mode = value.mode as WorkflowExecutionMode;
      if (value.stageCode) next.stageCode = value.stageCode;
      if (value.status) next.status = value.status as "draft" | "published" | "retired";
      setFilters(next);
      setCursor(undefined);
      setCursorHistory([]);
    },
  });
  const stageCodes = useMemo(() => {
    const unique = new Map<string, string>();
    for (const stage of stagesQuery.data?.items ?? []) {
      unique.set(stage.workflow_stage_code, stage.workflow_stage_name);
    }
    return [...unique.entries()].sort((left, right) => left[1].localeCompare(right[1]));
  }, [stagesQuery.data]);
  const referenceStages = (stagesQuery.data?.items ?? []).filter((stage) => (
    (!filters.workflow || stage.model_workflow === filters.workflow)
    && (!filters.mode || stage.workflow_execution_mode === filters.mode)
    && (!filters.stageCode || stage.workflow_stage_code === filters.stageCode)
  ));
  const denied = [stagesQuery.error, templatesQuery.error].some((error) => (
    error instanceof ApiError && error.status === 403
  ));
  const canCreate = (isSuperAdmin || (canAuthorPrompts && hasTenantLock))
    && !stagesQuery.isError
    && Boolean(stagesQuery.data?.items.length);
  const authoringLabel = !canAuthorPrompts
    ? "Architect permission required"
    : hasTenantLock
      ? "Tenant Lock held · Prompt authoring available"
      : isSuperAdmin
        ? "Global authoring available · Tenant Lock required for Tenant Prompts"
        : "Tenant Lock required for Prompt authoring";

  const refresh = async () => {
    await Promise.all([
      stagesQuery.refetch(),
      templatesQuery.refetch(),
      queryClient.invalidateQueries({ queryKey: ["tenant-home", tenantId] }),
    ]);
  };

  return (
    <main className="workspace prompts-workspace page-enter">
      <WorkflowCommandCenter className="prompts-library" filterCount={Object.keys(filters).length + (visibility ? 1 : 0)}>
      <header className="prompts-commandbar">
        <div>
          <h1>Prompts</h1>
        </div>
        <div className="prompts-command-actions">
          <WorkflowCommandTools />
          <span className={hasTenantLock || isSuperAdmin ? "lock-context is-held" : "lock-context"}>
            {hasTenantLock ? "Lock held" : isSuperAdmin ? "Global authoring" : "Read-only"}
          </span>
          <button
            className="button button-secondary button-small"
            type="button"
            disabled={stagesQuery.isFetching || templatesQuery.isFetching}
            onClick={() => void refresh()}
          >
            {stagesQuery.isFetching || templatesQuery.isFetching ? "Refreshing…" : "Refresh"}
          </button>
          <button
            className="button button-primary button-small"
            type="button"
            disabled={!canCreate}
            title={canCreate
              ? "Create a governed Prompt Template"
              : `${authoringLabel}; an available workflow stage is also required`}
            onClick={() => setCreateOpen(true)}
          >
            New Prompt Template
          </button>
        </div>
      </header>

      <WorkflowFilters><section className="prompt-filter-band" aria-label="Prompt Template server filters">
        <form
          onSubmit={(event) => {
            event.preventDefault();
            event.stopPropagation();
            void filterForm.handleSubmit();
          }}
        >
          <filterForm.Field name="workflow">
            {(field) => (
              <label>
                <span>Workflow</span>
                <select
                  aria-label="Workflow"
                  value={field.state.value}
                  onChange={(event) => field.handleChange(event.target.value)}
                >
                  <option value="">All workflows</option>
                  {WORKFLOWS.map((workflow) => (
                    <option key={workflow} value={workflow}>{humanize(workflow)}</option>
                  ))}
                </select>
              </label>
            )}
          </filterForm.Field>
          <filterForm.Field name="mode">
            {(field) => (
              <label>
                <span>Execution mode</span>
                <select
                  aria-label="Execution mode"
                  value={field.state.value}
                  onChange={(event) => field.handleChange(event.target.value)}
                >
                  <option value="">All modes</option>
                  {EXECUTION_MODES.map((mode) => (
                    <option key={mode} value={mode}>{humanize(mode)}</option>
                  ))}
                </select>
              </label>
            )}
          </filterForm.Field>
          <filterForm.Field name="stageCode">
            {(field) => (
              <label>
                <span>Workflow stage</span>
                <select
                  aria-label="Workflow stage filter"
                  value={field.state.value}
                  onChange={(event) => field.handleChange(event.target.value)}
                >
                  <option value="">All stages</option>
                  {stageCodes.map(([code, name]) => (
                    <option key={code} value={code}>{name} · {code}</option>
                  ))}
                </select>
              </label>
            )}
          </filterForm.Field>
          <filterForm.Field name="status">
            {(field) => (
              <label>
                <span>Latest version status</span>
                <select
                  aria-label="Latest version status"
                  value={field.state.value}
                  onChange={(event) => field.handleChange(event.target.value)}
                >
                  <option value="">Any status</option>
                  <option value="draft">Draft</option>
                  <option value="published">Published</option>
                  <option value="retired">Retired</option>
                </select>
              </label>
            )}
          </filterForm.Field>
          <label>
            <span>Visibility on this page</span>
            <select aria-label="Visibility on this page" value={visibility}
              onChange={(event) => setVisibility(event.target.value as PromptVisibilityFilter)}>
              <option value="">Global and Tenant</option>
              <option value="global">Global only</option>
              <option value="tenant">This Tenant only</option>
            </select>
          </label>
          <div className="scope-filter-actions">
            <button
              className="button button-secondary button-small"
              type="button"
              onClick={() => {
                filterForm.reset();
                setFilters({});
                setCursor(undefined);
                setCursorHistory([]);
                setVisibility("");
              }}
            >
              Clear
            </button>
            <button className="button button-primary button-small" type="submit">
              Apply filters
            </button>
          </div>
        </form>
      </section></WorkflowFilters>

      {stagesQuery.isPending || templatesQuery.isPending ? (
        <div className="surface-state" aria-busy="true">Loading Prompts…</div>
      ) : denied ? (
        <div className="surface-state is-error" role="alert">
          You do not have permission to view this Tenant Prompt Library.
        </div>
      ) : stagesQuery.isError || templatesQuery.isError ? (
        <div className="surface-state is-error" role="alert">
          The Prompt Library could not be loaded.
        </div>
      ) : (
        <>
          <PromptsLedger
            tenantId={tenantId}
            items={templatesQuery.data.items}
            visibility={visibility}
            pageNumber={cursorHistory.length + 1}
            hasPreviousPage={cursorHistory.length > 0}
            hasNextPage={Boolean(templatesQuery.data.next_cursor)}
            isPaging={templatesQuery.isFetching}
            onPreviousPage={() => {
              if (!cursorHistory.length) return;
              setCursor(cursorHistory.at(-1));
              setCursorHistory(cursorHistory.slice(0, -1));
            }}
            onNextPage={() => {
              if (!templatesQuery.data.next_cursor) return;
              setCursorHistory((history) => [...history, cursor]);
              setCursor(templatesQuery.data.next_cursor ?? undefined);
            }}
          />
          <AllowedVariableReference stages={referenceStages} />
        </>
      )}

      </WorkflowCommandCenter>
      {createOpen && stagesQuery.data ? (
        <CreatePromptDialog
          api={api}
          tenantId={tenantId}
          stages={stagesQuery.data.items}
          isSuperAdmin={isSuperAdmin}
          hasTenantLock={hasTenantLock}
          onClose={() => setCreateOpen(false)}
          onCreated={async (promptTemplateId) => {
            setCreateOpen(false);
            await queryClient.invalidateQueries({ queryKey: ["prompt-templates", tenantId] });
            await navigate({
              to: "/tenants/$tenantId/prompts/templates/$promptTemplateId",
              params: {
                tenantId: String(tenantId),
                promptTemplateId: String(promptTemplateId),
              },
            });
          }}
        />
      ) : null}
    </main>
  );
}

function AllowedVariableReference({ stages }: { stages: PromptStage[] }) {
  return (
    <details className="prompt-variable-reference">
      <summary>
        <span>
          <strong>Variable reference</strong>
          <small>{stages.length} workflow stage{stages.length === 1 ? "" : "s"}</small>
        </span>
        <span aria-hidden="true">+</span>
      </summary>
      <div className="prompt-variable-reference-body">
        {stages.length === 0 ? (
          <p>No agentic stages match the active filters.</p>
        ) : stages.map((stage) => (
          <details className="prompt-stage-reference" key={stage.workflow_stage_id}>
            <summary>
              <span>
                <strong>{stage.workflow_stage_name}</strong>
                <small>
                  {humanize(stage.model_workflow)} · {modeLabel(stage.workflow_execution_mode)} · {stage.workflow_stage_code}
                </small>
              </span>
              <span>{stage.allowed_variables.length} variables</span>
            </summary>
            <PromptVariables
              variables={stage.allowed_variables}
              label={`${stage.workflow_stage_name} inputs · ${stage.model_workflow} · ${modeLabel(stage.workflow_execution_mode)}`}
            />
          </details>
        ))}
      </div>
    </details>
  );
}
