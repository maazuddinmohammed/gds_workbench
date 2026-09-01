import { useState } from "react";
import { useQuery, useQueryClient } from "@tanstack/react-query";
import { Link } from "@tanstack/react-router";

import { ApiError } from "../../core/http";
import type { ModelDetail } from "../models/api";
import { WorkflowRunMonitor } from "../workflows/WorkflowRunMonitor";
import { qaQueryKeys, type QAApi } from "./api";
import { QALedger } from "./QALedger";
import { QARunDialog } from "./QARunDialog";

export function QAScreen({
  api,
  tenantId,
  model,
  hasTenantLock,
  hasAppPermission,
}: {
  api: QAApi;
  tenantId: number;
  model: ModelDetail;
  hasTenantLock: boolean;
  hasAppPermission: boolean;
}) {
  const queryClient = useQueryClient();
  const [runDialogOpen, setRunDialogOpen] = useState(false);
  const [startedRunId, setStartedRunId] = useState<number | null>(null);
  const systemsQuery = useQuery({
    queryKey: qaQueryKeys.systems(tenantId, model.model_id),
    queryFn: () => api.listQAEligibleSystems(tenantId, model.model_id),
  });
  const ledgerQuery = useQuery({
    queryKey: qaQueryKeys.ledger(tenantId, model.model_id),
    queryFn: () => api.readQALedger(tenantId, model.model_id),
  });
  const canAuthor = hasTenantLock && hasAppPermission;
  const systemsRevisionMismatch = systemsQuery.data !== undefined
    && systemsQuery.data.model_revision !== model.model_revision;
  const canOpenRun = canAuthor
    && !systemsQuery.isPending
    && !systemsQuery.isError
    && !systemsRevisionMismatch
    && Boolean(systemsQuery.data?.items.length);
  const permissionLabel = !hasAppPermission
    ? "Architect permission required to run QA"
    : !hasTenantLock
      ? "Tenant Lock required to run QA"
      : systemsQuery.isPending
        ? "Loading eligible QA Systems"
        : systemsQuery.isError
          ? "Eligible QA Systems are unavailable; refresh to try again"
          : systemsRevisionMismatch
            ? "The Model changed; refresh before running QA"
            : !systemsQuery.data?.items.length
              ? "No eligible Systems are available for QA"
              : "Tenant Lock held · ready to run QA";
  const invalidateQA = async () => {
    await Promise.all([
      queryClient.invalidateQueries({ queryKey: qaQueryKeys.systems(tenantId, model.model_id) }),
      queryClient.invalidateQueries({ queryKey: qaQueryKeys.ledger(tenantId, model.model_id) }),
      queryClient.invalidateQueries({ queryKey: ["model", tenantId, model.model_id] }),
      queryClient.invalidateQueries({ queryKey: ["tenant-home", tenantId] }),
    ]);
  };
  const refresh = async () => {
    await Promise.all([systemsQuery.refetch(), ledgerQuery.refetch()]);
  };

  return (
    <main className="workspace mapping-workspace qa-workspace page-enter">
      <header className="workflow-commandbar qa-commandbar">
        <div className="workflow-command-context qa-command-context">
          <Link
            className="text-action"
            aria-label="Back to QA Models"
            to="/tenants/$tenantId/qa"
            params={{ tenantId: String(tenantId) }}
          >
            ← Back to Models
          </Link>
          <span className={canAuthor ? "lock-context is-held" : "lock-context"}>
            {permissionLabel}
          </span>
        </div>
        <div className="workflow-command-actions">
          <button
            className="button button-secondary button-small"
            type="button"
            disabled={systemsQuery.isFetching || ledgerQuery.isFetching}
            onClick={() => void refresh()}
          >
            {systemsQuery.isFetching || ledgerQuery.isFetching ? "Refreshing…" : "Refresh"}
          </button>
          <button
            className="button button-primary button-small"
            type="button"
            disabled={!canOpenRun}
            title={permissionLabel}
            onClick={() => setRunDialogOpen(true)}
          >
            Run QA
          </button>
        </div>
      </header>
      <div className="workflow-context-line qa-context-line">
        <strong>{model.model_name} · r{model.model_revision}</strong>
        <span>QA uses applied Mapping and any current relevant Code when present to author a validated Model Change Set draft.</span>
      </div>
      {systemsQuery.error instanceof ApiError && systemsQuery.error.status === 403 ? (
        <p className="inline-error qa-system-error" role="alert">
          You do not have permission to load eligible QA Systems.
        </p>
      ) : systemsQuery.isError ? (
        <p className="inline-error qa-system-error" role="alert">
          Eligible QA Systems could not be loaded. Refresh to try again.
        </p>
      ) : systemsRevisionMismatch ? (
        <p className="inline-error qa-system-error" role="alert">
          The Model changed while eligible QA Systems were loading. Refresh before starting a run.
        </p>
      ) : systemsQuery.data?.is_truncated ? (
        <p className="code-generation-run-notice" role="status">
          The eligible QA System register is truncated to its safe server bound.
        </p>
      ) : null}
      {startedRunId ? (
        <p className="code-generation-run-notice" role="status">
          QA run {startedRunId} started. Refresh runs to review the draft, then Apply the validated draft.
        </p>
      ) : null}
      <WorkflowRunMonitor
        api={api}
        tenantId={tenantId}
        modelId={model.model_id}
        modelRevision={model.model_revision}
        workflow="qa"
        hasTenantLock={canAuthor}
        focusRunId={startedRunId}
        onApplied={invalidateQA}
      />
      <QALedger
        groups={ledgerQuery.data?.groups ?? []}
        modelRevision={model.model_revision}
        loadedModelRevision={ledgerQuery.data?.model_revision}
        isLoading={ledgerQuery.isPending}
        error={ledgerQuery.error}
      />
      {runDialogOpen && systemsQuery.data ? (
        <QARunDialog
          api={api}
          tenantId={tenantId}
          model={model}
          systems={systemsQuery.data.items}
          systemsTruncated={systemsQuery.data.is_truncated}
          onClose={() => setRunDialogOpen(false)}
          onStarted={async (workflowRunId) => {
            setStartedRunId(workflowRunId);
            await invalidateQA();
          }}
        />
      ) : null}
    </main>
  );
}
