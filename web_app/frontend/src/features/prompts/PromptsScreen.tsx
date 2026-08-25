import { useMemo, useState } from "react";
import { useForm } from "@tanstack/react-form";
import { useQuery, useQueryClient } from "@tanstack/react-query";
import { useNavigate } from "@tanstack/react-router";

import { ApiError } from "../../core/http";
import type {
  ModelWorkflow,
  WorkflowExecutionMode,
} from "../workflows/api";
import {
  promptQueryKeys,
  type PromptStage,
  type PromptTemplateFilters,
  type PromptsApi,
} from "./api";
import { CreatePromptDialog } from "./PromptTemplateDialogs";
import {
  PromptsLedger,
  humanize,
  modeLabel,
  type PromptVisibilityFilter,
} from "./PromptsLedger";

const WORKFLOWS: ModelWorkflow[] = [
  "profiling",
  "analysis",
  "conceptual",
  "logical",
  "dimensional",
  "mapping",
  "code_generation",
];

const EXECUTION_MODES: WorkflowExecutionMode[] = [
  "one_shot",
  "tool_assisted",
  "detailed_coverage",
];

export function PromptsScreen({
  api,
  tenantId,
  tenantName,
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
      if (value.workflow) next.workflow = value.workflow as ModelWorkflow;
      if (value.mode) next.mode = value.mode as WorkflowExecutionMode;
      if (value.stageCode) next.stageCode = value.stageCode;
      if (value.status) next.status = value.status as "draft" | "published" | "retired";
      setFilters(next);
      setCursor(undefined);
      setCursorHistory([]);
      setVisibility("");
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
      <header className="prompts-commandbar">
        <div>
          <p className="eyebrow">Governed language layer</p>
          <h1>Prompts</h1>
          <p>
            Global defaults and {tenantName} variants, versioned by agentic workflow stage.
          </p>
        </div>
        <div className="prompts-command-actions">
          <span className={hasTenantLock || isSuperAdmin ? "lock-context is-held" : "lock-context"}>
            {authoringLabel}
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

      <section className="prompt-filter-band" aria-label="Prompt Template server filters">
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
              Apply server filters
            </button>
          </div>
        </form>
      </section>

      {stagesQuery.isPending || templatesQuery.isPending ? (
        <div className="surface-state" aria-busy="true">Loading governed Prompt Library…</div>
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
            onVisibilityChange={setVisibility}
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
          <strong>Allowed-variable reference</strong>
          <small>{stages.length} filtered agentic stage{stages.length === 1 ? "" : "s"}</small>
        </span>
        <span aria-hidden="true">+</span>
      </summary>
      <div className="prompt-variable-reference-body">
        {stages.length === 0 ? (
          <p>No agentic stages match the active server filters.</p>
        ) : stages.map((stage) => (
          <section key={stage.workflow_stage_id}>
            <header>
              <div>
                <strong>{stage.workflow_stage_name}</strong>
                <small>
                  {humanize(stage.model_workflow)} · {modeLabel(stage.workflow_execution_mode)} · {stage.workflow_stage_code}
                </small>
              </div>
              <span>{stage.allowed_variables.length} variables</span>
            </header>
            {stage.allowed_variables.length ? (
              <dl className="prompt-variable-list">
                {stage.allowed_variables.map((variable) => (
                  <div key={variable.name}>
                    <dt>
                      <code>{`{{${variable.name}}}`}</code>
                      {variable.is_required ? <span>Required</span> : null}
                    </dt>
                    <dd>
                      {variable.description}
                      <small>{variable.data_type} · resolver {variable.resolver_key}</small>
                      {variable.example === null ? null : (
                        <code>Example: {boundedExample(variable.example)}</code>
                      )}
                    </dd>
                  </div>
                ))}
              </dl>
            ) : (
              <p>No variables are available for this stage.</p>
            )}
          </section>
        ))}
      </div>
    </details>
  );
}

function boundedExample(value: unknown): string {
  const text = typeof value === "string" ? value : JSON.stringify(value);
  if (!text) return "Unavailable";
  return text.length > 160 ? `${text.slice(0, 157)}…` : text;
}
