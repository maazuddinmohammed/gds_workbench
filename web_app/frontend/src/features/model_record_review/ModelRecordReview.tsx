import { WorkflowCommandContext } from "../workflows/WorkflowCommandCenter";
import { useContext, useEffect, useRef, useState } from "react";
import { useInfiniteQuery, useMutation } from "@tanstack/react-query";

import { ApiError } from "../../core/http";
import type { ModelRecordReviewApi, ModelReviewCommand, ModelReviewDataset } from "./api";
import "./model-review.css";

const deletionSections = [
  { label: "Conceptual", datasets: /^conceptual_/ },
  { label: "Logical", datasets: /^logical_/ },
  { label: "Dimensional", datasets: /^dimensional_/ },
  { label: "Mapping", datasets: /^mapping_/ },
  { label: "Code generation", datasets: /^generated_/ },
  { label: "Validation", datasets: /^validation_/ },
  { label: "Assertions", datasets: /^modeling_assertion/ },
  { label: "Other records", datasets: /.*/ },
] as const;

export function ModelRecordReview({
  api, tenantId, modelId, modelRevision, dataset, selectedIds, hasTenantLock, disabled, onApplied, deleteIds, actions = ["lock", "unlock", "deactivate", "reactivate"],
}: {
  api: ModelRecordReviewApi;
  tenantId: number;
  modelId: number;
  modelRevision: number;
  dataset: ModelReviewDataset;
  selectedIds: Set<number>;
  hasTenantLock: boolean;
  disabled: boolean;
  onApplied: () => Promise<void>;
  actions?: readonly ModelReviewCommand["action"][];
  deleteIds?: ReadonlySet<number>;
}) {
  const commandCenter = useContext(WorkflowCommandContext);
  const [command, setCommand] = useState<ModelReviewCommand | null>(null);
  const [notice, setNotice] = useState("");
  const reason = !hasTenantLock ? "Tenant Lock required for review updates."
    : disabled ? "Refresh the ledger before reviewing records."
    : selectedIds.size > 200 ? "Select at most 200 records per review." : undefined;
  return (
    <>
      <div className="review-selectionbar" tabIndex={-1} hidden={Boolean(commandCenter) && selectedIds.size === 0}>
        <span>{selectedIds.size} selected</span>
        <div className="workflow-command-actions">
          {actions.map((action) => (
            <button
              key={action} className={`button button-secondary button-small${action === "delete" ? " model-delete-action" : ""}`} type="button"
              disabled={selectedIds.size === 0 || Boolean(reason) || (action === "delete" && deleteIds?.size === 0)} title={reason ?? (action === "delete" && deleteIds ? "Delete selected unlocked mappings; locked mappings are skipped" : action === "lock" ? "Protect selected records from edits and regeneration" : action === "unlock" ? "Allow selected records to be edited or regenerated" : undefined)}
              onClick={() => {
                setNotice("");
                setCommand({
                  dataset, record_ids: [...(action === "delete" && deleteIds ? deleteIds : selectedIds)].sort((a, b) => a - b), action,
                  expected_model_revision: modelRevision,
                });
              }}
            >{action === "deactivate" ? "Deactivate" : action === "reactivate" ? "Activate" : action.charAt(0).toUpperCase() + action.slice(1)} selected</button>
          ))}
        </div>
      </div>
      {hasTenantLock && reason ? <p className="field-help">{reason}</p> : null}
      {notice ? <p role="status">{notice}</p> : null}
      {command ? (
        <ReviewDialog key={`${command.dataset}:${command.action}:${command.record_ids.join(",")}`}
          api={api} tenantId={tenantId} modelId={modelId} command={command}
          hasTenantLock={hasTenantLock} modelRevision={modelRevision}
          onReview={setCommand}
          onClose={() => setCommand(null)}
          onApplied={async (count) => {
            setCommand(null);
            setNotice(`${count} record${count === 1 ? "" : "s"} ${command.action === "delete" ? "deleted" : "updated"}.`);
            await onApplied();
          }}
        />
      ) : null}
    </>
  );
}

export function ReviewDialog({
  api, tenantId, modelId, command, hasTenantLock, modelRevision, onClose, onApplied, onReview,
}: {
  api: ModelRecordReviewApi;
  tenantId: number;
  modelId: number;
  command: ModelReviewCommand;
  hasTenantLock: boolean;
  modelRevision: number;
  onReview: (command: ModelReviewCommand) => void;
  onClose: () => void;
  onApplied: (count: number) => Promise<void>;
}) {
  const [requestKey] = useState(() => globalThis.crypto.randomUUID());
  const dialog = useRef<HTMLElement>(null);
  const closeButton = useRef<HTMLButtonElement>(null);
  const request = useRef<{ command: ModelReviewCommand; key: string } | null>(null);
  const previewQuery = useInfiniteQuery({
    queryKey: ["model-record-review", tenantId, modelId, requestKey],
    initialPageParam: { page: 1, digest: undefined as string | undefined },
    queryFn: ({ pageParam }) => api.previewModelRecordReview(
      tenantId, modelId,
      { ...command, ...(pageParam.digest ? { expected_plan_digest: pageParam.digest } : {}) },
      pageParam.page,
    ),
    getNextPageParam: (page) => page.next_page === null ? undefined
      : { page: page.next_page, digest: page.plan_digest },
    retry: false,
    staleTime: Infinity,
    refetchOnWindowFocus: false,
    refetchOnReconnect: false,
  });
  const applyMutation = useMutation({
    mutationFn: (attempt: NonNullable<typeof request.current>) => api.applyModelRecordReview(
      tenantId, modelId, attempt.command, attempt.key,
    ),
    onSuccess: (result) => {
      request.current = null;
      return onApplied(result.action_count);
    },
    onError: (error) => {
      if (error instanceof ApiError && error.status < 500 && error.status !== 408) {
        request.current = null;
      }
    },
  });
  const retryable = applyMutation.isError && request.current !== null;
  const cannotClose = applyMutation.isPending || retryable;
  const preview = previewQuery.data?.pages[0];
  const items = previewQuery.data?.pages.flatMap((page) => page.items) ?? [];
  const stale = modelRevision !== command.expected_model_revision;
  const deleting = command.action === "delete";
  const deletionGroups = deleting ? [...new Set([
    ...Object.keys(preview?.changes_by_dataset ?? {}), ...items.map((item) => item.dataset),
  ])].map((dataset) => {
    const records = items.filter((item) => item.dataset === dataset);
    return { dataset, records, count: preview?.changes_by_dataset?.[dataset] ?? records.length,
      section: deletionSections.find((section) => section.datasets.test(dataset))!.label,
      label: dataset.replaceAll("_", " ").replace(/^./, (letter) => letter.toUpperCase()) };
  }) : [];
  const deletionWorkflows = deletionSections.map(({ label }) => {
    const groups = deletionGroups.filter((group) => group.section === label).sort((left, right) => {
      const kinds = ["entity", "object", "attribute", "relationship", "submodel"];
      const leftKind = kinds.findIndex((kind) => left.dataset.endsWith(`_${kind}`));
      const rightKind = kinds.findIndex((kind) => right.dataset.endsWith(`_${kind}`));
      return (leftKind < 0 ? kinds.length : leftKind) - (rightKind < 0 ? kinds.length : rightKind)
        || left.dataset.localeCompare(right.dataset);
    });
    return { label, groups, count: groups.reduce((sum, group) => sum + group.count, 0) };
  }).filter((section) => section.groups.length);
  const canApply = hasTenantLock && !stale && preview?.can_apply && preview.action_count > 0
    && !previewQuery.isError && !previewQuery.isFetching && !applyMutation.isPending
    && !applyMutation.isError;
  useEffect(() => {
    const previous = document.activeElement;
    closeButton.current?.focus();
    return () => {
      if (!(previous instanceof HTMLElement) || !previous.isConnected) return;
      if (previous.matches(":disabled")) previous.closest<HTMLElement>(".review-selectionbar")?.focus();
      else previous.focus();
    };
  }, []);
  useEffect(() => {
    if (applyMutation.isPending || applyMutation.isError) dialog.current?.focus();
  }, [applyMutation.isPending, applyMutation.isError]);
  return (
    <div className="dialog-scrim" role="presentation">
      <section
        ref={dialog} tabIndex={-1} role="dialog" aria-modal="true" aria-labelledby="record-review-heading"
        className="run-configuration-dialog model-record-review-dialog"
        onKeyDown={(event) => {
          if (event.key === "Escape" && !cannotClose) onClose();
          if (event.key !== "Tab") return;
          const elements = [...(dialog.current?.querySelectorAll<HTMLElement>("*") ?? [])]
            .filter((element) => element.matches("button:not(:disabled), summary, [tabindex='0']"))
            .filter((element) => {
              for (let parent = element.parentElement; parent; parent = parent.parentElement) {
                if (parent.matches("details:not([open])") && parent.querySelector("summary") !== element) return false;
              }
              return true;
            });
          if (event.shiftKey && (document.activeElement === elements[0] || document.activeElement === dialog.current)) {
            event.preventDefault(); elements.at(-1)?.focus();
          } else if (!event.shiftKey && document.activeElement === elements.at(-1)) {
            event.preventDefault(); elements[0]?.focus();
          }
        }}
      >
        <header className="drawer-header">
          <div>
            <small>Model revision {command.expected_model_revision}</small>
            <h2 id="record-review-heading">{command.layer ? `Clear ${command.layer} layer` : deleting ? "Delete records permanently" : command.action === "deactivate" ? "Deactivate records" : command.action === "reactivate" ? "Activate records" : `Review ${command.action}`}</h2>
          </div>
          <button ref={closeButton} className="panel-close" type="button" aria-label="Close review"
            disabled={cannotClose} onClick={onClose}><span aria-hidden="true">×</span></button>
        </header>
        <div className="model-record-review-body">
          {previewQuery.isPending ? <p aria-busy="true">Checking selected records and dependencies…</p> : null}
          {previewQuery.isError ? <p role="alert">{failureMessage(previewQuery.error, false)}</p> : null}
          {stale ? <p role="alert">The Model changed. Close this preview and refresh before reviewing again.</p> : null}
          {!hasTenantLock ? <p role="alert">Tenant Lock required to apply this review.</p> : null}
          {command.layer ? <p>{deleting ? "Includes all records in this layer, across pages and filters." : command.layer === "conceptual"
            ? "This includes every active Conceptual object, relationship, and support link, across all pages and filters."
            : `This includes every active ${command.layer === "logical" ? "Logical" : "Dimensional"} entity, attribute, relationship, and submodel, including memberships and support records, across all pages and filters.`}</p> : null}
          {deleting ? <p className="model-delete-warning">Permanently deletes these records, including inactive records. This cannot be undone. Unlock locked records first.</p> : null}
          {command.action === "deactivate" ? <p>Deactivation keeps records in the database and excludes them from active workflows. You can activate them again. Required dependent status changes are listed below.</p> : null}
          {preview ? <>
            {!deleting && preview.changes_by_dataset ? <details className="model-review-breakdown"><summary>Counts by record type</summary><dl className="detail-fact-grid">{Object.entries(preview.changes_by_dataset).map(([dataset, count]) => <div key={dataset}><dt>{dataset.replaceAll("_", " ")}</dt><dd>{count}</dd></div>)}</dl></details> : null}
            {!deleting ? <>
              {preview.warnings?.map((warning) => <p className="field-help" key={warning}>{warning}</p>)}
              <p>{preview.action_count} {preview.action_count === 1 ? "change" : "changes"}: {preview.action_count - preview.additional_change_count} selected,
                {" "}{preview.additional_change_count} required by dependencies.</p>
            </> : <p className="model-delete-count">{preview.action_count} {preview.action_count === 1 ? "record" : "records"} to delete</p>}
            {preview.issues.length ? <div role="alert">
              <p>This review is blocked. Resolve these issues, then preview again.</p>
              <ul>{preview.issues.map((issue, index) => <li key={index}>{issue.message}</li>)}</ul>
              {preview.issue_count > preview.issues.length ? <p>{preview.issue_count} issues in total.</p> : null}
            </div> : null}
            {deleting ? <section className="model-delete-sections" aria-label="Records to delete">
              {deletionWorkflows.map((workflow) => <details key={workflow.label} className="model-delete-section model-delete-workflow"
                open={workflow.groups.some((group) => group.records.some((item) => item.is_locked))}>
                <summary tabIndex={0}><span>{workflow.label}</span><span>{workflow.count} {workflow.count === 1 ? "record" : "records"}</span></summary>
                <div className="model-delete-record-types">
                {workflow.groups.map(({ dataset, label, records, count }) => <details key={dataset} className="model-delete-section" open={records.some((item) => item.is_locked)}>
                <summary tabIndex={0}><span>{label}</span><span>{count} {count === 1 ? "record" : "records"}</span></summary>
                {records.length ? <div className="workflow-table-scroll table-scroll" tabIndex={0} aria-label={`${label} affected records`}>
                  <table aria-label={`${label} affected records`}>
                    <thead><tr><th scope="col">Record</th><th scope="col">Status</th><th scope="col">Lock</th></tr></thead>
                    <tbody>{records.map((item) => <tr key={item.record_id}>
                      <td><strong>{item.label}</strong></td>
                      <td>{item.status}</td>
                      <td>{item.is_locked ? "Locked" : "Open"}
                        {item.is_locked && item.can_unlock !== false ? <button className="text-action" type="button"
                          disabled={cannotClose || stale || !hasTenantLock}
                          onClick={() => onReview({ dataset: item.dataset as ModelReviewDataset, record_ids: [item.record_id],
                            action: "unlock", expected_model_revision: command.expected_model_revision })}
                        >Review unlock for {item.label}</button> : null}
                      </td>
                    </tr>)}</tbody>
                  </table>
                </div> : <p className="field-help">Details not loaded yet.</p>}
                {records.length < count ? <p className="field-help">{records.length} of {count} records loaded. Use Load more affected records below to continue.</p> : null}
                </details>)}
                </div>
              </details>)}
            </section> : <div className="workflow-table-scroll table-scroll" tabIndex={0} aria-label="Review changes">
              <table aria-label="Review changes">
                <thead><tr><th>Record</th><th>Change</th><th>Reason</th></tr></thead>
                <tbody>{items.map((item) => <tr key={`${item.dataset}:${item.record_id}`}>
                  <td><strong>{item.label}</strong><small>{item.dataset.replaceAll("_", " ")} · {item.record_id}</small></td>
                  <td>{item.changed
                    ? command.action === "lock" || command.action === "unlock"
                      ? `${item.is_locked ? "Locked" : "Open"} → ${item.desired_locked ? "Locked" : "Open"}`
                      : `${item.status} → ${item.desired_status}`
                    : "Unchanged"}{item.is_locked ? <small>Locked</small> : null}</td>
                  <td>{item.reason}
                    {item.is_locked && item.can_unlock !== false && command.action !== "lock" && command.action !== "unlock" ? (
                      <button className="text-action" type="button"
                        disabled={cannotClose || stale || !hasTenantLock}
                        onClick={() => onReview({ dataset: item.dataset as ModelReviewDataset, record_ids: [item.record_id],
                          action: "unlock", expected_model_revision: command.expected_model_revision })}
                      >Review unlock for {item.label}</button>
                    ) : null}
                  </td>
                </tr>)}</tbody>
              </table>
            </div>}
            <p>Showing {items.length} of {preview.total_record_count} affected records.</p>
            {previewQuery.hasNextPage ? <button className="button button-secondary button-small" type="button"
              disabled={previewQuery.isFetching || cannotClose || stale}
              onClick={() => void previewQuery.fetchNextPage()}>Load more affected records</button> : null}
            {deleting && Boolean(preview.warnings?.length) ? <details className="model-delete-notes">
              <summary tabIndex={0}>Scope notes</summary>
              <ul>{preview.warnings?.map((warning) => <li key={warning}>{warning}</li>)}</ul>
            </details> : null}
          </> : null}
          {applyMutation.isError ? <p role="alert">{failureMessage(applyMutation.error, retryable)}</p> : null}
          <div className="workflow-command-actions">
            <button className="button button-secondary" type="button" disabled={cannotClose} onClick={onClose}>Cancel</button>
            {retryable ? <button className="button button-primary" type="button"
              disabled={!hasTenantLock || applyMutation.isPending}
              onClick={() => { if (request.current) applyMutation.mutate(request.current); }}>Retry review</button>
              : <button className={`button button-primary${deleting ? " model-delete-confirm" : ""}`} type="button" disabled={!canApply}
                onClick={() => {
                  if (!canApply || !preview) return;
                  request.current = {
                    command: { ...command, expected_plan_digest: preview.plan_digest }, key: requestKey,
                  };
                  applyMutation.mutate(request.current);
                }}>{applyMutation.isPending ? deleting ? "Deleting…" : "Applying…" : deleting ? `Delete ${preview?.action_count ?? 0} records permanently` : preview?.action_count === 1 ? "Apply this change" : `Apply these ${preview?.action_count ?? 0} changes`}</button>}
          </div>
        </div>
      </section>
    </div>
  );
}

function failureMessage(error: Error, retryable: boolean): string {
  if (retryable) return "The review result could not be confirmed. Retry review to check the same request safely.";
  if (error instanceof ApiError) {
    if (error.status === 403) return "Review was not authorized. Check your role and owned Tenant Lock.";
    if (error.code === "model_locked") return "The Model is locked. A human must unlock it before changing records.";
    if (error.code === "record_locked") return "Unlock the selected or required records before changing their status.";
    if (error.code === "tenant_workflow_conflict") return "A Workflow Run is active. Refresh after it finishes, then preview again.";
    if (error.status === 409 || error.code === "model_record_not_found") return "The records or review plan changed. Close this preview and refresh before reviewing again.";
  }
  return "The review could not be checked. Close this preview and try again.";
}
