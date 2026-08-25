import { useState } from "react";
import { useQuery, useQueryClient } from "@tanstack/react-query";
import { Link } from "@tanstack/react-router";

import { ApiError } from "../../core/http";
import type { MappingEntityType } from "../mapping/api";
import type { ModelDetail } from "../models/api";
import {
  codeGenerationQueryKeys,
  type CodeGenerationApi,
  type CodeGenerationTarget,
  type CodeGenerationTargetFilters,
} from "./api";
import {
  CodeGenerationLedger,
  type ArtifactStatusFilter,
} from "./CodeGenerationLedger";
import {
  CodeGenerationRunDialog,
  type CodeGenerationCoverage,
} from "./CodeGenerationRunDialog";

type RequiredLayerFilters = CodeGenerationTargetFilters & { entityType: MappingEntityType };

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
}: {
  api: CodeGenerationApi;
  tenantId: number;
  model: ModelDetail;
  hasTenantLock: boolean;
  hasAppPermission: boolean;
}) {
  const queryClient = useQueryClient();
  const [filters, setFilters] = useState<RequiredLayerFilters>({
    entityType: "logical_entity",
  });
  const [artifactStatus, setArtifactStatus] = useState<ArtifactStatusFilter>("");
  const [cursor, setCursor] = useState<string | undefined>();
  const [cursorHistory, setCursorHistory] = useState<(string | undefined)[]>([]);
  const [selectedTargets, setSelectedTargets] = useState<Map<number, CodeGenerationTarget>>(
    () => new Map(),
  );
  const [runDialog, setRunDialog] = useState<OpenRunDialog | null>(null);
  const [startedRunId, setStartedRunId] = useState<number | null>(null);
  const targetsQuery = useQuery({
    queryKey: codeGenerationQueryKeys.targets(tenantId, model.model_id, filters, cursor),
    queryFn: () => api.listCodeGenerationTargets(
      tenantId,
      model.model_id,
      filters,
      50,
      cursor,
    ),
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
    setStartedRunId(null);
    await Promise.all([
      targetsQuery.refetch(),
      queryClient.invalidateQueries({ queryKey: ["model", tenantId, model.model_id] }),
      queryClient.invalidateQueries({ queryKey: ["tenant-home", tenantId] }),
    ]);
  };
  const applyFilters = (nextFilters: RequiredLayerFilters) => {
    setFilters(normalizeFilters(nextFilters));
    setCursor(undefined);
    setCursorHistory([]);
    setSelectedTargets(new Map());
    setStartedRunId(null);
  };
  const changeArtifactStatus = (status: ArtifactStatusFilter) => {
    setArtifactStatus(status);
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
  const openSelectedRun = () => {
    if (selected.length) {
      setRunDialog({ coverage: "selected_targets", selectedTargets: selected });
    }
  };

  return (
    <main className="workspace mapping-workspace code-generation-workspace page-enter">
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
            disabled={!canStartRun || selected.length === 0}
            title={selected.length ? generationTitle : "Select at least one target Object"}
            onClick={openSelectedRun}
          >
            Generate selected
          </button>
          <button
            className="button button-primary button-small"
            type="button"
            disabled={!canStartRun}
            title={generationTitle}
            onClick={() => setRunDialog({
              coverage: "all_eligible_targets",
              selectedTargets: [],
            })}
          >
            Generate all eligible
          </button>
        </div>
      </header>
      <div className="workflow-context-line code-generation-context-line">
        <strong>{model.model_name} · r{model.model_revision}</strong>
        <span>Target Objects are primary. Modeled Entities appear only as applied Mapping support.</span>
      </div>
      {startedRunId ? (
        <p className="code-generation-run-notice" role="status">
          Code Generation run {startedRunId} started. Refresh after completion to review stored SQL.
        </p>
      ) : null}
      <CodeGenerationLedger
        tenantId={tenantId}
        modelId={model.model_id}
        items={targetsQuery.data?.items ?? []}
        filters={filters}
        artifactStatus={artifactStatus}
        selectedTargetIds={new Set(selectedTargets.keys())}
        canGenerate={canStartRun}
        permissionLabel={generationTitle}
        state={{
          isLoading: targetsQuery.isPending,
          isError: targetsQuery.isError,
          isDenied: targetsQuery.error instanceof ApiError && targetsQuery.error.status === 403,
          revisionMismatch,
          hasNextPage: targetsQuery.data?.next_cursor !== null
            && targetsQuery.data?.next_cursor !== undefined,
          hasPreviousPage: cursorHistory.length > 0,
          isPaging: targetsQuery.isFetching && !targetsQuery.isPending,
          pageNumber: cursorHistory.length + 1,
        }}
        onApplyFilters={applyFilters}
        onArtifactStatusChange={changeArtifactStatus}
        onToggleTarget={toggleTarget}
        onToggleVisible={toggleVisible}
        onGenerateTarget={(target) => setRunDialog({
          coverage: "selected_targets",
          selectedTargets: [target],
        })}
        onNextPage={() => {
          const nextCursor = targetsQuery.data?.next_cursor;
          if (!nextCursor) return;
          setCursorHistory((history) => [...history, cursor]);
          setCursor(nextCursor);
        }}
        onPreviousPage={() => {
          if (!cursorHistory.length) return;
          setCursor(cursorHistory.at(-1));
          setCursorHistory(cursorHistory.slice(0, -1));
        }}
      />
      {runDialog ? (
        <CodeGenerationRunDialog
          api={api}
          tenantId={tenantId}
          model={model}
          entityType={filters.entityType}
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

function normalizeFilters(filters: RequiredLayerFilters): RequiredLayerFilters {
  const systemCode = filters.systemCode?.trim().toLocaleLowerCase();
  const sourceSystemCode = filters.sourceSystemCode?.trim().toLocaleLowerCase();
  return {
    entityType: filters.entityType,
    ...(systemCode ? { systemCode } : {}),
    ...(sourceSystemCode ? { sourceSystemCode } : {}),
  };
}
