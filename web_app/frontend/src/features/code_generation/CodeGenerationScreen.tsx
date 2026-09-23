import { ModelLayerTabs, type ModelLayer } from "../../shared/ModelLayerTabs";
import { ModelRecordHistory } from "../model_record_review/ModelRecordHistory";
import { useState } from "react";
import { useQuery, useQueryClient } from "@tanstack/react-query";
import { Link } from "@tanstack/react-router";

import { ApiError } from "../../core/http";
import type { MappingEntityType } from "../mapping/api";
import type { ModelDetail } from "../models/api";
import { WorkflowRunMonitor } from "../workflows/WorkflowRunMonitor";
import {
  codeGenerationQueryKeys,
  loadCodeGenerationTargets,
  type CodeGenerationApi,
  type CodeGenerationTarget,
} from "./api";
import {
  CodeGenerationLedger,
  type ArtifactStatusFilter,
} from "./CodeGenerationLedger";
import {
  CodeGenerationRunDialog,
  type CodeGenerationCoverage,
} from "./CodeGenerationRunDialog";

interface OpenRunDialog {
  coverage: CodeGenerationCoverage;
  selectedTargets: CodeGenerationTarget[];
}

export function CodeGenerationScreen({
  api,
  tenantId,
  model,
  hasTenantLock,
  hasAppPermission,
  layer,
}: {
  layer: ModelLayer;
  api: CodeGenerationApi;
  tenantId: number;
  model: ModelDetail;
  hasTenantLock: boolean;
  hasAppPermission: boolean;
}) {
  const queryClient = useQueryClient();
  const [view, setView] = useState<"targets" | "artifacts">("targets");
  const entityType: MappingEntityType = layer === "logical" ? "logical_entity" : "dimensional_entity";
  const [artifactStatus, setArtifactStatus] = useState<ArtifactStatusFilter>("");
  const [objectIds, setObjectIds] = useState<string[]>([]);
  const [page, setPage] = useState(0);

  const [selectedTargets, setSelectedTargets] = useState<Map<number, CodeGenerationTarget>>(
    () => new Map(),
  );
  const [runDialog, setRunDialog] = useState<OpenRunDialog | null>(null);
  const [startedRunId, setStartedRunId] = useState<number | null>(null);
  const targetsQuery = useQuery({
    queryKey: codeGenerationQueryKeys.targets(tenantId, model.model_id, { entityType }, undefined),
    queryFn: () => loadCodeGenerationTargets(api, tenantId, model.model_id, entityType),
  });
  const canGenerate = hasTenantLock && hasAppPermission;
  const permissionLabel = !hasAppPermission
    ? "Architect permission required to generate SQL"
    : !hasTenantLock
      ? "Tenant Lock required to generate SQL"
      : "Tenant Lock held · ready to generate";
  const revisionMismatch = targetsQuery.data !== undefined
    && targetsQuery.data.model_revision !== model.model_revision;
  const canStartRun = canGenerate
    && !revisionMismatch
    && !targetsQuery.isPending
    && !targetsQuery.isError;
  const generationTitle = revisionMismatch
    ? "The Model changed; refresh before generating SQL"
    : permissionLabel;
  const selected = [...selectedTargets.values()];

  const refresh = async () => {
    await Promise.all([
      queryClient.invalidateQueries({ queryKey: ["code-generation-targets", tenantId, model.model_id] }),
      queryClient.invalidateQueries({ queryKey: ["validation-systems", tenantId, model.model_id] }),
      queryClient.invalidateQueries({ queryKey: ["validation-ledger", tenantId, model.model_id] }),
      queryClient.invalidateQueries({ queryKey: ["model", tenantId, model.model_id] }),
      queryClient.invalidateQueries({ queryKey: ["tenant-home", tenantId] }),
    ]);
  };
  const changeArtifactStatus = (status: ArtifactStatusFilter) => {
    setArtifactStatus(status);
    setPage(0);
    setSelectedTargets(new Map());
  };
  const toggleTarget = (target: CodeGenerationTarget, isSelected: boolean) => {
    setSelectedTargets((current) => {
      const next = new Map(current);
      if (isSelected) next.set(target.target.object_id, target);
      else next.delete(target.target.object_id);
      return next;
    });
  };
  const toggleVisible = (targets: CodeGenerationTarget[], isSelected: boolean) => {
    setSelectedTargets((current) => {
      const next = new Map(current);
      for (const target of targets) {
        if (isSelected) next.set(target.target.object_id, target);
        else next.delete(target.target.object_id);
      }
      return next;
    });
  };

  return (
    <main className="workspace mapping-workspace code-generation-workspace page-enter">
      <ModelLayerTabs tenantId={tenantId} modelId={model.model_id} layer={layer} workflow="code-generation" title="Code generation" />
      <header className="workflow-commandbar code-generation-commandbar">
        <div className="workflow-command-context code-generation-command-context">
          <Link
            className="text-action"
            aria-label="Back to Code Generation Models"
            to="/tenants/$tenantId/code-generation"
            params={{ tenantId: String(tenantId) }}
          >
            ← Back to Models
          </Link>
          <span className={canGenerate ? "lock-context is-held" : "lock-context"}>
            {permissionLabel}
          </span>
        </div>
        <div className="workflow-command-actions code-generation-command-actions">
          <span>{selected.length} selected</span>
          <button
            className="button button-secondary button-small"
            type="button"
            disabled={targetsQuery.isFetching}
            onClick={() => void refresh()}
          >
            {targetsQuery.isFetching ? "Refreshing…" : "Refresh"}
          </button>
          <button
            className="button button-primary button-small"
            type="button"
            disabled={!canStartRun || !targetsQuery.data?.items.some((item) => !item.is_locked)}
            title={generationTitle}
            onClick={() => setRunDialog({
              coverage: selected.length ? "selected_targets" : "all_eligible_targets",
              selectedTargets: selected,
            })}
          >
            Generate SQL
          </button>
        </div>
      </header>
      <div className="workflow-context-line code-generation-context-line">
        <strong>{model.model_name} · r{model.model_revision}</strong>

      </div>
      {startedRunId ? (
        <p className="code-generation-run-notice" role="status">
          Code Generation run {startedRunId} started. Refresh runs to review the draft, then Apply the validated draft.
        </p>
      ) : null}
      <WorkflowRunMonitor
        api={api}
        tenantId={tenantId}
        modelId={model.model_id}
        modelRevision={model.model_revision}
        workflow="code_generation"
        hasTenantLock={canGenerate}
        focusRunId={startedRunId}
        onApplied={refresh}
      />
      <nav className="workflow-tabs" aria-label="Code views">
        <button type="button" className={view === "targets" ? "is-active" : ""} aria-pressed={view === "targets"} onClick={() => setView("targets")}>Generation targets</button>
        <button type="button" className={view === "artifacts" ? "is-active" : ""} aria-pressed={view === "artifacts"} onClick={() => setView("artifacts")}>Applied Code</button>
      </nav>
      {view === "artifacts" ? <ModelRecordHistory
        api={api} tenantId={tenantId} modelId={model.model_id} modelRevision={model.model_revision}
        dataset="generated_code" label="Applied Code" hasTenantLock={canGenerate}
        entityType={entityType}
      /> : <CodeGenerationLedger
        tenantId={tenantId}
        modelId={model.model_id}
        items={targetsQuery.data?.items ?? []}
        objectIds={objectIds}
        onObjectIdsChange={(ids) => { setObjectIds(ids); setPage(0); }}
        page={page}
        artifactStatus={artifactStatus}
        selectedTargetIds={new Set(selectedTargets.keys())}
        canGenerate={canStartRun}
        permissionLabel={generationTitle}
        state={{
          isLoading: targetsQuery.isPending,
          isError: targetsQuery.isError,
          isDenied: targetsQuery.error instanceof ApiError && targetsQuery.error.status === 403,
          revisionMismatch,
          hasPreviousPage: page > 0,
          isPaging: targetsQuery.isFetching && !targetsQuery.isPending,
          pageNumber: page + 1,
        }}
        onArtifactStatusChange={changeArtifactStatus}
        onToggleTarget={toggleTarget}
        onToggleVisible={toggleVisible}
        onGenerateTarget={(target) => setRunDialog({
          coverage: "selected_targets",
          selectedTargets: [target],
        })}
        onNextPage={() => setPage((value) => value + 1)}
        onPreviousPage={() => setPage((value) => Math.max(0, value - 1))}
      />}
      {runDialog ? (
        <CodeGenerationRunDialog
          api={api}
          tenantId={tenantId}
          model={model}
          entityType={entityType}
          coverage={runDialog.coverage}
          selectedTargets={runDialog.selectedTargets}
          onClose={() => setRunDialog(null)}
          onStarted={async (workflowRunId) => {
            setStartedRunId(workflowRunId);
            setSelectedTargets(new Map());
            await queryClient.invalidateQueries({
              queryKey: ["code-generation-targets", tenantId, model.model_id],
            });
          }}
        />
      ) : null}
    </main>
  );
}
