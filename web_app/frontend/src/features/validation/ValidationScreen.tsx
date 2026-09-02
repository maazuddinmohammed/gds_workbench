import { useState } from "react";
import { useQuery, useQueryClient } from "@tanstack/react-query";
import { Link } from "@tanstack/react-router";

import { ApiError } from "../../core/http";
import type { ModelDetail } from "../models/api";
import { WorkflowRunMonitor } from "../workflows/WorkflowRunMonitor";
import { validationQueryKeys, type ValidationApi } from "./api";
import { ValidationLedger } from "./ValidationLedger";
import { ValidationRunDialog } from "./ValidationRunDialog";

export function ValidationScreen({
  api,
  tenantId,
  model,
  hasTenantLock,
  hasAppPermission,
}: {
  api: ValidationApi;
  tenantId: number;
  model: ModelDetail;
  hasTenantLock: boolean;
  hasAppPermission: boolean;
}) {
  const queryClient = useQueryClient();
  const [runDialogOpen, setRunDialogOpen] = useState(false);
  const [startedRunId, setStartedRunId] = useState<number | null>(null);
  const systemsQuery = useQuery({
    queryKey: validationQueryKeys.systems(tenantId, model.model_id),
    queryFn: () => api.listValidationEligibleSystems(tenantId, model.model_id),
  });
  const ledgerQuery = useQuery({
    queryKey: validationQueryKeys.ledger(tenantId, model.model_id),
    queryFn: () => api.readValidationLedger(tenantId, model.model_id),
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
    ? "Architect permission required to run Validation"
    : !hasTenantLock
      ? "Tenant Lock required to run Validation"
      : systemsQuery.isPending
        ? "Loading eligible Validation Systems"
        : systemsQuery.isError
          ? "Eligible Validation Systems are unavailable; refresh to try again"
          : systemsRevisionMismatch
            ? "The Model changed; refresh before running Validation"
            : !systemsQuery.data?.items.length
              ? "No eligible Systems are available for Validation"
              : "Tenant Lock held · ready to run Validation";
  const invalidateValidation = async () => {
    await Promise.all([
      queryClient.invalidateQueries({ queryKey: validationQueryKeys.systems(tenantId, model.model_id) }),
      queryClient.invalidateQueries({ queryKey: validationQueryKeys.ledger(tenantId, model.model_id) }),
      queryClient.invalidateQueries({ queryKey: ["model", tenantId, model.model_id] }),
      queryClient.invalidateQueries({ queryKey: ["tenant-home", tenantId] }),
    ]);
  };
  const refresh = async () => {
    await Promise.all([systemsQuery.refetch(), ledgerQuery.refetch()]);
  };

  return (
    <main className="workspace mapping-workspace validation-workspace page-enter">
      <header className="workflow-commandbar validation-commandbar">
        <div className="workflow-command-context validation-command-context">
          <Link
            className="text-action"
            aria-label="Back to Validation Models"
            to="/tenants/$tenantId/validation"
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
            Run Validation
          </button>
        </div>
      </header>
      <div className="workflow-context-line validation-context-line">
        <strong>{model.model_name} · r{model.model_revision}</strong>
        <span>Validation uses applied Mapping and any current relevant Code when present to author a validated Model Change Set draft.</span>
      </div>
      {systemsQuery.error instanceof ApiError && systemsQuery.error.status === 403 ? (
        <p className="inline-error validation-system-error" role="alert">
          You do not have permission to load eligible Validation Systems.
        </p>
      ) : systemsQuery.isError ? (
        <p className="inline-error validation-system-error" role="alert">
          Eligible Validation Systems could not be loaded. Refresh to try again.
        </p>
      ) : systemsRevisionMismatch ? (
        <p className="inline-error validation-system-error" role="alert">
          The Model changed while eligible Validation Systems were loading. Refresh before starting a run.
        </p>
      ) : systemsQuery.data?.is_truncated ? (
        <p className="code-generation-run-notice" role="status">
          The eligible Validation System register is truncated to its safe server bound.
        </p>
      ) : null}
      {startedRunId ? (
        <p className="code-generation-run-notice" role="status">
          Validation run {startedRunId} started. Refresh runs to review the draft, then Apply the validated draft.
        </p>
      ) : null}
      <WorkflowRunMonitor
        api={api}
        tenantId={tenantId}
        modelId={model.model_id}
        modelRevision={model.model_revision}
        workflow="validation"
        hasTenantLock={canAuthor}
        focusRunId={startedRunId}
        onApplied={invalidateValidation}
      />
      <ValidationLedger
        groups={ledgerQuery.data?.groups ?? []}
        modelRevision={model.model_revision}
        loadedModelRevision={ledgerQuery.data?.model_revision}
        isLoading={ledgerQuery.isPending}
        error={ledgerQuery.error}
      />
      {runDialogOpen && systemsQuery.data ? (
        <ValidationRunDialog
          api={api}
          tenantId={tenantId}
          model={model}
          systems={systemsQuery.data.items}
          systemsTruncated={systemsQuery.data.is_truncated}
          onClose={() => setRunDialogOpen(false)}
          onStarted={async (workflowRunId) => {
            setStartedRunId(workflowRunId);
            await invalidateValidation();
          }}
        />
      ) : null}
    </main>
  );
}
