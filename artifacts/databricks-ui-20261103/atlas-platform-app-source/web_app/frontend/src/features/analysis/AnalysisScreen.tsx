import { WorkflowCommandCenter, WorkflowCommandTools, WorkflowMenu } from "../workflows/WorkflowCommandCenter";
import { useRef, useState } from "react";
import { useInfiniteQuery, useMutation, useQuery, useQueryClient } from "@tanstack/react-query";

import { ApiError } from "../../core/http";
import type { ProjectDetail } from "../projects/api";
import {
  loadWorkflowScope,
  workflowCreationQueryKeys,
  workflowRunQueryKeys,
} from "../workflows/api";
import { WorkflowRunDialog } from "../workflows/WorkflowRunDialog";
import { WorkflowRunMonitor } from "../workflows/WorkflowRunMonitor";
import {
  analysisQueryKeys,
  type AnalysisApi,
  type AnalysisFilters,
  type AnalysisReviewAction,
  type AnalysisReviewCommand,
} from "./api";
import { AnalysisResults } from "./AnalysisResults";
import { RefreshButton } from "../../shared/ui";

type RunDialogKind = "inference" | "validation" | null;

export function AnalysisScreen({
  api,
  tenantId,
  project,
  hasTenantLock,
}: {
  api: AnalysisApi;
  tenantId: number;
  project: ProjectDetail;
  hasTenantLock: boolean;
}) {
  const queryClient = useQueryClient();
  const [filters, setFilters] = useState<AnalysisFilters>({});
  const [selectedIds, setSelectedIds] = useState<Set<number>>(new Set());
  const [runDialog, setRunDialog] = useState<RunDialogKind>(null);
  const [recentRunId, setRecentRunId] = useState<number | null>(null);
  const [reviewNotice, setReviewNotice] = useState("");
  const reviewRequest = useRef<{
    command: AnalysisReviewCommand;
    idempotencyKey: string;
  } | null>(null);
  const findingsQuery = useInfiniteQuery({
    queryKey: analysisQueryKeys.findings(tenantId, project.project_id, filters),
    queryFn: ({ pageParam }) => api.listAnalysisFindings(
      tenantId,
      project.project_id,
      filters,
      200,
      pageParam,
    ),
    initialPageParam: undefined as string | undefined,
    getNextPageParam: (lastPage) => lastPage.next_cursor ?? undefined,
  });
  const endpointOptionsQuery = useQuery({
    queryKey: workflowCreationQueryKeys.bronzeScope(tenantId, project.project_id),
    queryFn: () => loadWorkflowScope(api, tenantId, project.project_id, "bronze"),
  });
  const revisionMismatch = findingsQuery.data !== undefined
    && findingsQuery.data.pages.some((page) => page.project_revision !== project.project_revision);
  const download = useMutation({
    mutationFn: () => api.exportAnalysis(tenantId, project.project_id, project.project_revision, filters),
    onSuccess: ({ blob, filename }) => {
      const url = URL.createObjectURL(blob);
      const link = document.createElement("a");
      link.href = url; link.download = filename; document.body.append(link); link.click(); link.remove();
      URL.revokeObjectURL(url);
    },
  });
  const reviewMutation = useMutation({
    mutationFn: (request: NonNullable<typeof reviewRequest.current>) => api.reviewAnalysisFindings(
      tenantId,
      project.project_id,
      request.command,
      request.idempotencyKey,
    ),
    onSuccess: async (result) => {
      reviewRequest.current = null;
      setSelectedIds(new Set());
      setReviewNotice(`${result.action_count} finding${result.action_count === 1 ? "" : "s"} updated.`);
      await Promise.all([
        queryClient.invalidateQueries({ queryKey: ["analysis-findings", tenantId, project.project_id] }),
        queryClient.invalidateQueries({ queryKey: ["analysis-finding", tenantId, project.project_id] }),
        queryClient.invalidateQueries({ queryKey: ["project", tenantId, project.project_id] }),
        queryClient.invalidateQueries({ queryKey: ["project-overview", tenantId, project.project_id] }),
        queryClient.invalidateQueries({ queryKey: workflowCreationQueryKeys.bronzeScope(tenantId, project.project_id) }),
        queryClient.invalidateQueries({ queryKey: ["tenant-home", tenantId] }),
      ]);
    },
    onError: (error) => {
      if (error instanceof ApiError && error.status < 500 && error.status !== 408) {
        reviewRequest.current = null;
      }
    },
  });
  const reviewRetryable = reviewMutation.isError && reviewRequest.current !== null;
  const reviewFindings = (action: AnalysisReviewAction) => {
    if (!hasTenantLock || selectedIds.size === 0 || selectedIds.size > 200
      || revisionMismatch || findingsQuery.isPending || findingsQuery.isError
      || reviewMutation.isPending || reviewRetryable) return;
    setReviewNotice("");
    reviewRequest.current = {
      command: {
        record_ids: [...selectedIds].sort((left, right) => left - right),
        action,
        expected_project_revision: project.project_revision,
      },
      idempotencyKey: globalThis.crypto.randomUUID(),
    };
    reviewMutation.mutate(reviewRequest.current);
  };
  const refresh = async () => {
    await Promise.all([
      findingsQuery.refetch(),
      endpointOptionsQuery.refetch(),
      queryClient.invalidateQueries({ queryKey: ["project", tenantId, project.project_id] }),
      queryClient.invalidateQueries({ queryKey: ["tenant-home", tenantId] }),
    ]);
  };

  return (
    <WorkflowCommandCenter filterCount={Object.values(filters).filter(Boolean).length} className="analysis-page page-enter">
      <header className="workflow-commandbar project-section-toolbar">
        <h1 className="project-section-title sr-only">Analysis</h1>
        <div className="workflow-command-actions">
          <WorkflowCommandTools />
          <button className="button button-secondary button-small" type="button"
            disabled={download.isPending || revisionMismatch || findingsQuery.isPending || findingsQuery.isError}
            onClick={() => download.mutate()}>{download.isPending ? "Exporting…" : "Export"}</button>
          <RefreshButton refreshing={false} onClick={refresh} />
          <WorkflowMenu label="Run" primary>
          <button
            className="button button-secondary button-small"
            type="button"
            disabled={!hasTenantLock}
            title={hasTenantLock ? undefined : "Tenant Lock required"}
            onClick={() => setRunDialog("inference")}
          >
            Run inference
          </button>
          <button
            className="button button-primary button-small"
            type="button"
            disabled={!hasTenantLock}
            title={hasTenantLock ? undefined : "Tenant Lock required"}
            onClick={() => setRunDialog("validation")}
          >
            Validate pending
          </button>
          </WorkflowMenu>
        </div>
      </header>


        {download.isError ? <p role="alert">Export failed. Refresh the Project and retry.</p> : null}
        <AnalysisResults
          items={findingsQuery.data?.pages.flatMap((page) => page.items) ?? []}
          endpointOptions={endpointOptionsQuery.data?.items ?? []}
          filters={filters}
          selectedIds={selectedIds}
          isLoading={findingsQuery.isPending}
          isError={findingsQuery.isError}
          revisionMismatch={revisionMismatch}
          hasMore={findingsQuery.hasNextPage}
          isLoadingMore={findingsQuery.isFetchingNextPage}
          hasTenantLock={hasTenantLock}
          reviewPending={reviewMutation.isPending}
          reviewRetryable={reviewRetryable}
          reviewError={reviewMutation.error ? reviewFailureMessage(reviewMutation.error) : null}
          reviewNotice={reviewNotice}
          onReview={reviewFindings}
          onRetryReview={() => {
            if (reviewRequest.current && hasTenantLock && !reviewMutation.isPending) {
              reviewMutation.mutate(reviewRequest.current);
            }
          }}
          onApplyFilters={(nextFilters) => {
            setSelectedIds(new Set());
            setFilters(nextFilters);
          }}
          onSelectionChange={setSelectedIds}
          onLoadMore={() => {
            void findingsQuery.fetchNextPage();
          }}
        />
          <WorkflowRunMonitor
            api={api}
            tenantId={tenantId}
            projectId={project.project_id}
            projectRevision={project.project_revision}
            workflow="analysis"
            hasTenantLock={hasTenantLock}
            focusRunId={recentRunId}
            onApplied={async () => {
              await queryClient.invalidateQueries({
                queryKey: ["analysis-findings", tenantId, project.project_id],
              });
            }}
          />

      {runDialog ? (
        <WorkflowRunDialog
          api={api}
          tenantId={tenantId}
          project={project}
          kind={runDialog}
          executeCreated={(workflowRunId, executionMode, expectedProjectRevision) => api.executeAnalysisInferenceRun(
            tenantId,
            project.project_id,
            workflowRunId,
            executionMode,
            expectedProjectRevision,
          ).then(() => undefined)}
          executeValidationCreated={(workflowRunId, expectedProjectRevision) => api.executeAnalysisValidationRun(
            tenantId,
            project.project_id,
            workflowRunId,
            expectedProjectRevision,
          ).then(() => undefined)}
          onClose={() => setRunDialog(null)}
          onCreated={async (workflowRunId) => {
            setRecentRunId(workflowRunId);
            await queryClient.invalidateQueries({
              queryKey: workflowRunQueryKeys.recent(tenantId, project.project_id, "analysis"),
            });

          }}
        />
      ) : null}
    </WorkflowCommandCenter>
  );
}

function reviewFailureMessage(error: Error): string {
  if (!(error instanceof ApiError) || error.status >= 500 || error.status === 408) {
    return "The review result could not be confirmed. Retry review to safely check the same request.";
  }
  if (error.code === "record_locked") return "Unlock selected findings before changing their status.";
  if (error.code === "tenant_workflow_conflict") {
    return "A Workflow Run is active. Wait for it to finish, then refresh before reviewing findings.";
  }
  if (error.status === 403) return "Review was not authorized. Confirm your role and owned Tenant Lock, then retry.";
  if (error.status === 409 || error.code === "project_record_not_found") {
    return "The Project or selected findings changed. Refresh, check your selection, then retry.";
  }
  return "The review was rejected. Refresh and check the selected findings before retrying.";
}
