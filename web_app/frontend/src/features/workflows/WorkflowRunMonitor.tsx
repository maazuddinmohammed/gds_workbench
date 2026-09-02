import { useEffect, useId, useRef, useState, type RefObject } from "react";
import { createPortal } from "react-dom";
import {
  useInfiniteQuery,
  useMutation,
  useQuery,
  useQueryClient,
} from "@tanstack/react-query";

import { ApiError } from "../../core/http";
import { formatRequiredDateTime as formatDateTime } from "../../shared/presentation";
import {
  workflowRunQueryKeys,
  type ModelWorkflow,
  type WorkflowDraftReview,
  type WorkflowRunDetail,
  type WorkflowRunMonitorApi,
} from "./api";
import {
  isActiveRun,
  RunStateBadge,
  WorkflowEventProgress,
  workflowStageLabel,
} from "./presentation";

type DraftWorkflow = Extract<
  ModelWorkflow,
  | "analysis"
  | "conceptual"
  | "logical"
  | "dimensional"
  | "mapping"
  | "code_generation"
  | "validation"
>;

const WORKFLOW_EVENT_PAGE_SIZE = 200;

export function WorkflowRunMonitor({
  api,
  tenantId,
  modelId,
  modelRevision,
  workflow,
  hasTenantLock,
  focusRunId,
  onApplied,
}: {
  api: WorkflowRunMonitorApi;
  tenantId: number;
  modelId: number;
  modelRevision: number;
  workflow: DraftWorkflow;
  hasTenantLock: boolean;
  focusRunId: number | null;
  onApplied: () => Promise<void>;
}) {
  const queryClient = useQueryClient();
  const monitorBodyId = useId();
  const [expanded, setExpanded] = useState(focusRunId !== null || workflow === "analysis");
  const [selectedRunId, setSelectedRunId] = useState<number | null>(focusRunId);
  const [runIdInput, setRunIdInput] = useState(focusRunId === null ? "" : String(focusRunId));
  const [confirmApply, setConfirmApply] = useState(false);
  const applyIdempotencyKey = useRef<string | null>(null);
  const applyTrigger = useRef<HTMLButtonElement>(null);
  const label = workflowLabel(workflow);
  const recentKey = workflowRunQueryKeys.recent(tenantId, modelId, workflow);
  const recentQuery = useInfiniteQuery({
    queryKey: recentKey,
    queryFn: ({ pageParam }) => api.listWorkflowRuns(
      tenantId,
      modelId,
      workflow,
      "",
      5,
      pageParam,
    ),
    initialPageParam: undefined as string | undefined,
    getNextPageParam: (lastPage) => lastPage.next_cursor ?? undefined,
  });
  const recentRuns = recentQuery.data?.pages.flatMap((page) => page.items) ?? [];

  useEffect(() => {
    applyIdempotencyKey.current = null;
    setSelectedRunId(focusRunId);
    setRunIdInput(focusRunId === null ? "" : String(focusRunId));
    if (focusRunId !== null || workflow === "analysis") {
      setExpanded(true);
    }
    if (focusRunId !== null) {
      void queryClient.invalidateQueries({
        queryKey: workflowRunQueryKeys.recent(tenantId, modelId, workflow),
      });
    }
  }, [focusRunId, modelId, queryClient, tenantId, workflow]);
  useEffect(() => {
    if (selectedRunId === null && recentRuns[0]) {
      setSelectedRunId(recentRuns[0].workflow_run_id);
      setRunIdInput(String(recentRuns[0].workflow_run_id));
    }
  }, [recentRuns, selectedRunId]);

  const runQuery = useQuery({
    queryKey: workflowRunQueryKeys.detail(tenantId, modelId, selectedRunId ?? 0),
    queryFn: () => api.readWorkflowRun(tenantId, modelId, selectedRunId ?? 0),
    enabled: selectedRunId !== null,
  });
  const eventsQuery = useInfiniteQuery({
    queryKey: workflowRunQueryKeys.events(tenantId, modelId, selectedRunId ?? 0),
    queryFn: ({ pageParam }) => api.listWorkflowRunEvents(
      tenantId,
      modelId,
      selectedRunId ?? 0,
      pageParam,
    ),
    enabled: selectedRunId !== null,
    initialPageParam: 0,
    getNextPageParam: (lastPage) => (
      lastPage.items.length === WORKFLOW_EVENT_PAGE_SIZE
        ? lastPage.next_after_sequence
        : undefined
    ),
  });
  const events = eventsQuery.data?.pages.flatMap((page) => page.items) ?? [];
  useEffect(() => {
    if (eventsQuery.hasNextPage && !eventsQuery.isFetchingNextPage) {
      void eventsQuery.fetchNextPage();
    }
  }, [eventsQuery.fetchNextPage, eventsQuery.hasNextPage, eventsQuery.isFetchingNextPage]);
  const run = runQuery.data;
  const validatedDraft = isValidatedDraft(run) ? run : null;
  const draftReviewQuery = useQuery({
    queryKey: workflowRunQueryKeys.draftReview(
      tenantId,
      modelId,
      run?.model_change_set_id ?? "none",
    ),
    queryFn: () => api.readWorkflowDraftReview(
      tenantId,
      modelId,
      run?.model_change_set_id ?? "",
    ),
    enabled: Boolean(validatedDraft),
  });
  const [, setExpiryTick] = useState(0);
  const reviewExpired = isDraftReviewExpired(draftReviewQuery.data ?? null);
  useEffect(() => {
    const expiresAt = Date.parse(draftReviewQuery.data?.expires_at ?? "");
    if (!Number.isFinite(expiresAt)) return;
    const remaining = expiresAt - Date.now();
    if (remaining <= 0) {
      setExpiryTick((tick) => tick + 1);
      return;
    }
    const timeout = globalThis.setTimeout(
      () => setExpiryTick((tick) => tick + 1),
      Math.min(remaining + 25, 2_147_483_647),
    );
    return () => globalThis.clearTimeout(timeout);
  }, [draftReviewQuery.data?.expires_at]);
  const reviewMatches = Boolean(
    validatedDraft
    && draftReviewQuery.data
    && isAuthoritativeReview(validatedDraft, draftReviewQuery.data),
  );
  const canApply = validatedDraft !== null && reviewMatches;
  const applyMutation = useMutation({
    mutationFn: async () => {
      if (!validatedDraft || !reviewMatches || !applyIdempotencyKey.current) {
        throw new Error("Validated draft is unavailable.");
      }
      return api.applyWorkflowDraft(
        tenantId,
        modelId,
        validatedDraft.workflow_run_id,
        modelRevision,
        validatedDraft.draft_revision,
        validatedDraft.candidate_digest,
        applyIdempotencyKey.current,
      );
    },
    onSuccess: async (result) => {
      setConfirmApply(false);
      applyIdempotencyKey.current = null;
      await Promise.all([
        queryClient.invalidateQueries({ queryKey: recentKey }),
        queryClient.invalidateQueries({
          queryKey: workflowRunQueryKeys.detail(tenantId, modelId, result.workflow_run_id),
        }),
        queryClient.invalidateQueries({
          queryKey: workflowRunQueryKeys.draftReview(
            tenantId,
            modelId,
            result.model_change_set_id,
          ),
        }),
        queryClient.invalidateQueries({ queryKey: ["model", tenantId, modelId] }),
        queryClient.invalidateQueries({ queryKey: ["tenant-home", tenantId] }),
        onApplied(),
      ]);
      setExpanded(false);
    },
    onError: (error) => {
      if (!isAmbiguousTransportFailure(error)) applyIdempotencyKey.current = null;
    },
  });
  const selectRun = (workflowRunId: number) => {
    if (workflowRunId !== selectedRunId) applyIdempotencyKey.current = null;
    setSelectedRunId(workflowRunId);
    setRunIdInput(String(workflowRunId));
    setConfirmApply(false);
    applyMutation.reset();
  };
  const parsedRunId = Number(runIdInput);
  const runIdIsValid = Number.isSafeInteger(parsedRunId) && parsedRunId > 0;
  const refreshing = recentQuery.isFetching
    || runQuery.isFetching
    || eventsQuery.isFetching
    || draftReviewQuery.isFetching;
  const refreshAll = async () => {
    const refreshes: Promise<unknown>[] = [recentQuery.refetch()];
    if (selectedRunId !== null) {
      refreshes.push(runQuery.refetch(), eventsQuery.refetch());
    }
    if (validatedDraft) refreshes.push(draftReviewQuery.refetch());
    await Promise.all(refreshes);
  };

  return (
    <section
      className={`workflow-run-monitor${expanded ? "" : " is-collapsed"}`}
      aria-label={`${label} recent runs`}
    >
      <header className="workflow-run-monitor-header">
        <div>
          <small>Workflow activity</small>
          <h2>Recent {label} runs</h2>
          {!expanded && recentRuns[0] ? (
            <span
              className="workflow-run-monitor-summary"
              aria-label={`Latest ${label} run`}
            >
              <strong>Run {recentRuns[0].workflow_run_id}</strong>
              <RunStateBadge state={recentRuns[0].workflow_run_state} />
              {applyMutation.data?.workflow_run_id === recentRuns[0].workflow_run_id ? (
                <span className="workflow-run-monitor-applied">Draft applied</span>
              ) : null}
            </span>
          ) : null}
        </div>
        <div className="workflow-run-monitor-actions">
          <button
            className="button button-secondary button-small"
            type="button"
            disabled={refreshing}
            onClick={() => void refreshAll()}
          >
            {refreshing ? "Refreshing…" : "Refresh runs"}
          </button>
          <button
            className="button button-secondary button-small"
            type="button"
            aria-label={expanded
              ? `Hide ${label} run activity`
              : `Show ${label} run activity`}
            aria-controls={monitorBodyId}
            aria-expanded={expanded}
            onClick={() => setExpanded((current) => !current)}
          >
            {expanded ? "Hide activity" : "Show activity"}
          </button>
        </div>
      </header>

      <div id={monitorBodyId} hidden={!expanded}>
        {recentQuery.isPending ? (
          <div className="surface-state compact" aria-busy="true">Loading recent runs…</div>
        ) : recentQuery.isError ? (
          <div className="surface-state is-error compact" role="alert">
            Recent runs could not be loaded.
          </div>
        ) : recentRuns.length === 0 && selectedRunId === null ? (
          <div className="empty-state compact">No recent {label} runs.</div>
        ) : (
          <div className="workflow-run-monitor-layout">
          <div className="workflow-run-browser">
            <form
              className="workflow-run-id-navigation"
              onSubmit={(event) => {
                event.preventDefault();
                if (runIdIsValid) selectRun(parsedRunId);
              }}
            >
              <label>
                <span>Run ID</span>
                <input
                  aria-label="Run ID"
                  inputMode="numeric"
                  min="1"
                  step="1"
                  type="number"
                  value={runIdInput}
                  onChange={(event) => setRunIdInput(event.target.value)}
                />
              </label>
              <button
                className="button button-secondary button-small"
                type="submit"
                disabled={!runIdIsValid}
              >
                Open run
              </button>
            </form>
            <ol className="workflow-recent-runs" aria-label={`${label} run list`}>
              {recentRuns.map((item) => (
                <li key={item.workflow_run_id}>
                  <button
                    className={selectedRunId === item.workflow_run_id ? "is-selected" : ""}
                    type="button"
                    aria-pressed={selectedRunId === item.workflow_run_id}
                    onClick={() => selectRun(item.workflow_run_id)}
                  >
                    <span>
                      <strong>Run {item.workflow_run_id}</strong>
                      <small>{runKind(item.workflow_execution_mode, workflow)}</small>
                    </span>
                    <RunStateBadge state={item.workflow_run_state} />
                  </button>
                </li>
              ))}
            </ol>
            {recentQuery.hasNextPage ? (
              <button
                className="workflow-runs-load-more"
                type="button"
                disabled={recentQuery.isFetchingNextPage}
                onClick={() => void recentQuery.fetchNextPage()}
              >
                {recentQuery.isFetchingNextPage ? "Loading more…" : "Load more runs"}
              </button>
            ) : null}
          </div>
          <div className="workflow-run-monitor-detail">
            {runQuery.isPending ? (
              <div className="surface-state compact" aria-busy="true">Loading run details…</div>
            ) : runQuery.isError || !run ? (
              <div className="surface-state is-error compact" role="alert">
                Run details could not be loaded.
              </div>
            ) : (
              <WorkflowRunDetailView
                run={run}
                events={events}
                eventsPending={eventsQuery.isPending}
                eventsLoadingMore={eventsQuery.isFetchingNextPage}
                eventsError={eventsQuery.isError}
                draftReview={draftReviewQuery.data ?? null}
                draftReviewPending={draftReviewQuery.isPending && Boolean(validatedDraft)}
                draftReviewError={draftReviewQuery.isError}
                reviewMatches={reviewMatches}
                reviewExpired={reviewExpired}
                hasTenantLock={hasTenantLock}
                canApply={canApply}
                applyPending={applyMutation.isPending}
                applyError={confirmApply ? null : applyMutation.error}
                appliedRunId={applyMutation.data?.workflow_run_id ?? null}
                applyTriggerRef={applyTrigger}
                onApply={() => {
                  applyMutation.reset();
                  applyIdempotencyKey.current ??= globalThis.crypto.randomUUID();
                  setConfirmApply(true);
                }}
              />
            )}
          </div>
          </div>
        )}
      </div>

      {confirmApply && validatedDraft && canApply ? (
        <ApplyDraftConfirmation
          label={label}
          runId={validatedDraft.workflow_run_id}
          draftRevision={validatedDraft.draft_revision}
          isPending={applyMutation.isPending}
          error={applyMutation.error}
          returnFocusRef={applyTrigger}
          onClose={() => setConfirmApply(false)}
          onConfirm={() => applyMutation.mutate()}
        />
      ) : null}
    </section>
  );
}

function WorkflowRunDetailView({
  run,
  events,
  eventsPending,
  eventsLoadingMore,
  eventsError,
  draftReview,
  draftReviewPending,
  draftReviewError,
  reviewMatches,
  reviewExpired,
  hasTenantLock,
  canApply,
  applyPending,
  applyError,
  appliedRunId,
  applyTriggerRef,
  onApply,
}: {
  run: WorkflowRunDetail;
  events: Awaited<ReturnType<WorkflowRunMonitorApi["listWorkflowRunEvents"]>>["items"];
  eventsPending: boolean;
  eventsLoadingMore: boolean;
  eventsError: boolean;
  draftReview: WorkflowDraftReview | null;
  draftReviewPending: boolean;
  draftReviewError: boolean;
  reviewMatches: boolean;
  reviewExpired: boolean;
  hasTenantLock: boolean;
  canApply: boolean;
  applyPending: boolean;
  applyError: Error | null;
  appliedRunId: number | null;
  applyTriggerRef: RefObject<HTMLButtonElement | null>;
  onApply: () => void;
}) {
  const failureEvent = [...events]
    .reverse()
    .find((event) => event.status === "failed" || event.status === "blocked");
  const agentIdentity = run.agent_provider_code && run.agent_model_code
    ? `${run.agent_provider_code} · ${run.agent_model_code}`
    : run.agent_provider_code ?? run.agent_model_code ?? "Not recorded";
  return (
    <article aria-label={`Run ${run.workflow_run_id} details`}>
      <header className="workflow-run-detail-header">
        <div>
          <small>Run {run.workflow_run_id}</small>
          <strong>{runKind(run.workflow_execution_mode, run.model_workflow)}</strong>
        </div>
        <RunStateBadge state={run.workflow_run_state} />
      </header>
      <dl className="workflow-run-facts">
        <div><dt>Created</dt><dd>{formatDateTime(run.created_at)}</dd></div>
        <div><dt>Actor</dt><dd>{run.actor_display_name}</dd></div>
        <div><dt>Objects</dt><dd>{run.selected_scope_count}</dd></div>
        <div><dt>Mode</dt><dd>{run.workflow_execution_mode?.replaceAll("_", " ") ?? "Deterministic"}</dd></div>
      </dl>

      {run.workflow_run_state === "failed" ? (
        <section
          className="workflow-run-failure"
          role="alert"
          aria-label="Run failure details"
        >
          <header>
            <strong>Failure reason</strong>
            <code>{run.failure_code?.replaceAll("_", " ") ?? "run failed"}</code>
          </header>
          <p>{run.failure_message ?? "No additional safe failure detail was recorded."}</p>
          <dl>
            <div>
              <dt>Last stage</dt>
              <dd>{failureEvent ? workflowStageLabel(failureEvent.stage) : "Not recorded"}</dd>
            </div>
            <div>
              <dt>Attempt</dt>
              <dd>{failureEvent ? `Attempt ${failureEvent.attempt}` : "Not recorded"}</dd>
            </div>
            <div>
              <dt>Agent</dt>
              <dd>{agentIdentity}</dd>
            </div>
          </dl>
          <small>Reference {run.correlation_id}</small>
        </section>
      ) : null}

      {run.model_change_set_status === "validated" ? (
        <AuthoritativeDraftReview
          run={run}
          review={draftReview}
          isPending={draftReviewPending}
          isError={draftReviewError}
          matches={reviewMatches}
          expired={reviewExpired}
        />
      ) : null}

      <section className="workflow-draft-status" aria-label="Validated draft status">
        <div>
          <strong>{draftStatus(run)}</strong>
          {run.draft_revision && run.candidate_digest ? (
            <small>
              Draft r{run.draft_revision} · digest {run.candidate_digest.slice(0, 12)}…
            </small>
          ) : (
            <small>Apply appears only after a completed authoring run validates its draft.</small>
          )}
        </div>
        {canApply ? (
          <button
            ref={applyTriggerRef}
            className="button button-accent button-small"
            type="button"
            disabled={!hasTenantLock || applyPending}
            title={hasTenantLock
              ? "Review and apply this exact validated draft"
              : "Owned Tenant Lock required"}
            onClick={onApply}
          >
            {applyPending ? "Applying…" : "Apply validated draft"}
          </button>
        ) : null}
      </section>
      {applyError ? (
        <p className="inline-error" role="alert">{safeApplyFailure(applyError)}</p>
      ) : null}
      {appliedRunId === run.workflow_run_id ? (
        <p className="inline-success" role="status">Validated draft applied.</p>
      ) : null}

      <section className="workflow-run-events" aria-labelledby={`run-${run.workflow_run_id}-events`}>
        <h3 id={`run-${run.workflow_run_id}-events`}>Events</h3>
        {eventsPending ? (
          <div className="surface-state compact" aria-busy="true">Loading events…</div>
        ) : eventsError ? (
          <div className="surface-state is-error compact" role="alert">
            Run events could not be loaded.
          </div>
        ) : events.length === 0 ? (
          <div className="empty-state compact">
            No run events yet. Use Refresh runs to check again.
          </div>
        ) : (
          <>
            <ol>
              {events.map((event) => (
                <li key={event.sequence}>
                  <span className={`status-badge is-${event.status}`}>{event.status}</span>
                  <div>
                    <strong>{workflowStageLabel(event.stage)}</strong>
                    <p>{event.message}</p>
                    <WorkflowEventProgress event={event} />
                    <small className="workflow-event-meta">
                      <span>Event {event.sequence} · Attempt {event.attempt}</span>
                      {event.current !== null && event.total !== null ? (
                        <span>{event.current} of {event.total}</span>
                      ) : null}
                      {event.finding_count > 0 ? (
                        <span>
                          {event.finding_count} {event.finding_count === 1 ? "finding" : "findings"}
                        </span>
                      ) : null}
                    </small>
                  </div>
                  <time>{formatDateTime(event.created_at)}</time>
                </li>
              ))}
            </ol>
            {eventsLoadingMore ? (
              <p className="workflow-events-loading" role="status">Loading additional events…</p>
            ) : null}
          </>
        )}
      </section>
    </article>
  );
}

function AuthoritativeDraftReview({
  run,
  review,
  isPending,
  isError,
  matches,
  expired,
}: {
  run: WorkflowRunDetail;
  review: WorkflowDraftReview | null;
  isPending: boolean;
  isError: boolean;
  matches: boolean;
  expired: boolean;
}) {
  if (isPending) {
    return (
      <section className="workflow-draft-review" aria-label="Authoritative draft review">
        <div className="surface-state compact" aria-busy="true">Loading validated draft review…</div>
      </section>
    );
  }
  if (expired) {
    return (
      <section className="workflow-draft-review" aria-label="Authoritative draft review">
        <p className="inline-error" role="alert">
          This validated draft has expired. Apply is disabled.
        </p>
      </section>
    );
  }
  if (isError || !review || !matches || !review.validation_outcome) {
    return (
      <section className="workflow-draft-review" aria-label="Authoritative draft review">
        <p className="inline-error" role="alert">
          The authoritative draft review is unavailable or no longer matches this Run. Apply is disabled.
        </p>
      </section>
    );
  }
  const actions = new Map(review.validation_outcome.action_review.map((item) => (
    [item.dataset, item] as const
  )));
  const datasets = new Set([
    ...review.dataset_counts.map((item) => item.dataset),
    ...review.validation_outcome.action_review.map((item) => item.dataset),
  ]);
  return (
    <section className="workflow-draft-review" aria-label="Authoritative draft review">
      <header>
        <div>
          <strong>Validated candidate review</strong>
          <small>
            {review.validation_outcome.staged_record_count} staged records · {review.validation_outcome.error_count} errors
          </small>
        </div>
        <code title="Candidate digest">{run.candidate_digest}</code>
      </header>
      <div className="workflow-draft-review-scroll">
        <table aria-label="Validated draft action counts">
          <thead>
            <tr>
              <th>Dataset</th>
              <th>Staged</th>
              <th>Insert</th>
              <th>Update</th>
              <th>Deactivate</th>
              <th>Reactivate</th>
              <th>No change</th>
            </tr>
          </thead>
          <tbody>
            {[...datasets].sort().map((dataset) => {
              const action = actions.get(dataset);
              return (
                <tr key={dataset}>
                  <td>{dataset.replaceAll("_", " ")}</td>
                  <td>{review.dataset_counts.find((item) => item.dataset === dataset)?.record_count ?? 0}</td>
                  <td>{action?.insert_count ?? 0}</td>
                  <td>{action?.update_count ?? 0}</td>
                  <td>{action?.deactivate_count ?? 0}</td>
                  <td>{action?.reactivate_count ?? 0}</td>
                  <td>{action?.no_change_count ?? 0}</td>
                </tr>
              );
            })}
          </tbody>
        </table>
      </div>
    </section>
  );
}

function ApplyDraftConfirmation({
  label,
  runId,
  draftRevision,
  isPending,
  error,
  returnFocusRef,
  onClose,
  onConfirm,
}: {
  label: string;
  runId: number;
  draftRevision: number;
  isPending: boolean;
  error: Error | null;
  returnFocusRef: RefObject<HTMLButtonElement | null>;
  onClose: () => void;
  onConfirm: () => void;
}) {
  const closeButton = useRef<HTMLButtonElement>(null);
  const dialog = useRef<HTMLElement>(null);
  const portalHost = useRef<HTMLDivElement | null>(null);
  if (portalHost.current === null) {
    portalHost.current = document.createElement("div");
    portalHost.current.dataset.workflowModalHost = "true";
  }
  useEffect(() => {
    const host = portalHost.current;
    if (!host) return;
    document.body.append(host);
    const appRoot = document.getElementById("root");
    const rootWasInert = appRoot?.hasAttribute("inert") ?? false;
    const previousAriaHidden = appRoot?.getAttribute("aria-hidden") ?? null;
    appRoot?.setAttribute("inert", "");
    appRoot?.setAttribute("aria-hidden", "true");
    closeButton.current?.focus();
    return () => {
      if (appRoot) {
        if (!rootWasInert) appRoot.removeAttribute("inert");
        if (previousAriaHidden === null) appRoot.removeAttribute("aria-hidden");
        else appRoot.setAttribute("aria-hidden", previousAriaHidden);
      }
      host.remove();
      globalThis.queueMicrotask(() => returnFocusRef.current?.focus());
    };
  }, [returnFocusRef]);
  const modal = (
    <div className="dialog-scrim prompt-dialog-scrim" role="presentation">
      <section
        ref={dialog}
        className="prompt-dialog workflow-draft-confirmation"
        role="dialog"
        aria-modal="true"
        aria-labelledby="workflow-draft-confirmation-title"
        onKeyDown={(event) => {
          if (event.key === "Escape") {
            if (!isPending) onClose();
            return;
          }
          if (event.key !== "Tab") return;
          const focusable = [...(dialog.current?.querySelectorAll<HTMLElement>(
            "button:not([disabled]), [href], input:not([disabled]), select:not([disabled]), "
            + "textarea:not([disabled]), [tabindex]:not([tabindex='-1'])",
          ) ?? [])];
          if (focusable.length === 0) {
            event.preventDefault();
            return;
          }
          const first = focusable[0];
          const last = focusable.at(-1);
          if (event.shiftKey && (document.activeElement === first || !dialog.current?.contains(document.activeElement))) {
            event.preventDefault();
            last?.focus();
          } else if (!event.shiftKey && (
            document.activeElement === last || !dialog.current?.contains(document.activeElement)
          )) {
            event.preventDefault();
            first?.focus();
          }
        }}
      >
        <header>
          <div>
            <small>Governed transition</small>
            <h2 id="workflow-draft-confirmation-title">Apply validated {label} draft?</h2>
          </div>
          <button
            ref={closeButton}
            className="dialog-close"
            type="button"
            aria-label="Close draft confirmation"
            disabled={isPending}
            onClick={onClose}
          >
            ×
          </button>
        </header>
        <p>
          Run {runId}, draft revision {draftRevision}, will be applied to the Model under the
          current Tenant Lock. The backend rechecks every revision and digest fence.
        </p>
        {error ? <p className="inline-error" role="alert">{safeApplyFailure(error)}</p> : null}
        <footer>
          <button className="button button-secondary" type="button" disabled={isPending} onClick={onClose}>
            Cancel
          </button>
          <button className="button button-accent" type="button" disabled={isPending} onClick={onConfirm}>
            {isPending ? "Applying…" : "Apply exact draft"}
          </button>
        </footer>
      </section>
    </div>
  );
  return createPortal(modal, portalHost.current);
}

function isValidatedDraft(run: WorkflowRunDetail | undefined): run is WorkflowRunDetail & {
  draft_revision: number;
  candidate_digest: string;
} {
  return Boolean(
    run
    && (run.workflow_run_state === "completed" || run.workflow_run_state === "completed_with_repair")
    && run.workflow_execution_mode !== null
    && run.model_change_set_id
    && run.model_change_set_status === "validated"
    && run.draft_revision
    && run.candidate_digest,
  );
}

function isAuthoritativeReview(
  run: WorkflowRunDetail & { draft_revision: number; candidate_digest: string },
  review: WorkflowDraftReview,
): boolean {
  return review.model_change_set_id === run.model_change_set_id
    && review.status === "validated"
    && review.draft_revision === run.draft_revision
    && review.candidate_digest === run.candidate_digest
    && review.validation_outcome?.valid === true
    && review.validation_outcome.error_count === 0
    && !isDraftReviewExpired(review);
}

function isDraftReviewExpired(review: WorkflowDraftReview | null): boolean {
  if (!review) return false;
  const expiresAt = Date.parse(review.expires_at);
  return !Number.isFinite(expiresAt) || expiresAt <= Date.now();
}

function workflowLabel(workflow: DraftWorkflow): string {
  if (workflow === "validation") return "Validation";
  if (workflow === "code_generation") return "Code Generation";
  return workflow.charAt(0).toUpperCase() + workflow.slice(1);
}

function runKind(mode: WorkflowRunDetail["workflow_execution_mode"], workflow: ModelWorkflow): string {
  if (workflow === "analysis" && mode === null) return "Deterministic validation";
  return mode ? `${mode.replaceAll("_", " ")} authoring` : "Deterministic run";
}

function draftStatus(run: WorkflowRunDetail): string {
  if (run.model_change_set_status === "validated") return "Validated draft ready";
  if (run.model_change_set_status === "applied") return "Draft applied";
  if (run.model_change_set_status) {
    return `Draft ${run.model_change_set_status.replaceAll("_", " ")}`;
  }
  return isActiveRun(run) ? "Authoring in progress" : "No applicable draft";
}

function safeApplyFailure(error: Error): string {
  if (error instanceof ApiError && error.status === 409) {
    return "The Model or draft changed before Apply. Refresh the run and review the latest draft.";
  }
  if (error instanceof ApiError && error.status === 403) {
    return "Apply was not authorized. Confirm your role and owned Tenant Lock.";
  }
  return "The validated draft could not be applied. No unverified server detail was displayed.";
}

function isAmbiguousTransportFailure(error: Error): boolean {
  if (error instanceof TypeError) return true;
  return typeof DOMException !== "undefined"
    && error instanceof DOMException
    && ["AbortError", "NetworkError", "TimeoutError"].includes(error.name);
}
