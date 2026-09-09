import { useState } from "react";
import { useQuery } from "@tanstack/react-query";

import { NormalizedJson } from "../assertions/NormalizedJson";
import type { WorkflowDraftReview, WorkflowRunDetail, WorkflowRunMonitorApi } from "./api";

/** Inspect canonical staged records only; provider responses never enter this view. */
export function FailedWorkflowDraft({
  api, tenantId, modelId, run, review, isPending, isError, expired,
}: {
  api: WorkflowRunMonitorApi;
  tenantId: number;
  modelId: number;
  run: WorkflowRunDetail;
  review: WorkflowDraftReview | null;
  isPending: boolean;
  isError: boolean;
  expired: boolean;
}) {
  const [dataset, setDataset] = useState("");
  const [recordNumber, setRecordNumber] = useState(1);
  const matches = (candidate: WorkflowDraftReview | null | undefined) => Boolean(candidate
    && candidate.model_id === modelId
    && candidate.model_change_set_id === run.model_change_set_id
    && candidate.draft_revision === run.draft_revision
    && candidate.status === "active"
    && candidate.candidate_digest === null
    && candidate.validation_outcome?.valid === false
    && Date.parse(candidate.expires_at) > Date.now());
  const available = !isError && !isPending && !expired && matches(review);
  const recordsQuery = useQuery({
    queryKey: ["workflow-draft-records", tenantId, modelId,
      run.model_change_set_id, run.draft_revision, dataset],
    queryFn: () => api.readWorkflowDraftReview(
      tenantId, modelId, run.model_change_set_id ?? "", dataset,
    ),
    enabled: available && Boolean(dataset),
  });
  const recordsMatch = matches(recordsQuery.data) && recordsQuery.data?.dataset === dataset;
  const records = recordsMatch ? recordsQuery.data?.records ?? [] : [];
  const record = records[recordNumber - 1];
  const outcome = review?.validation_outcome;
  const selectRecord = (nextDataset: string, nextRecord = 1) => {
    setDataset(nextDataset);
    setRecordNumber(nextRecord);
  };

  return (
    <section className="workflow-draft-review workflow-failed-draft" aria-label="Retained draft review">
      <header><strong>Generated draft · corrections required</strong></header>
      {isPending ? (
        <p className="surface-state compact" aria-busy="true">Loading retained draft…</p>
      ) : !available || !review || !outcome ? (
        <p className="inline-error" role="alert">
          {expired ? "This retained draft has expired." : "The retained draft is unavailable or changed. Refresh runs to reload it."}
        </p>
      ) : (
        <>
          <p>
            {outcome.staged_record_count} generated records retained. {outcome.error_count} validation {outcome.error_count === 1 ? "error prevents" : "errors prevent"} Apply.
            Review the affected records and correct the inputs or instructions before running again.
          </p>
          {!!outcome.error_groups?.length && (
            <div className="workflow-draft-review-scroll">
              <table aria-label="Validation error groups">
                <thead><tr><th>Dataset</th><th>Problem</th><th>Count</th></tr></thead>
                <tbody>{outcome.error_groups.map((group) => (
                  <tr key={`${group.dataset}-${group.code}`}>
                    <td>{group.dataset.replaceAll("_", " ")}</td>
                    <td>{group.code.replaceAll("_", " ")}</td>
                    <td>{group.count}</td>
                  </tr>
                ))}</tbody>
              </table>
            </div>
          )}
          {!!outcome.errors?.length && (
            <ol className="workflow-draft-errors" aria-label="Validation error examples">
              {outcome.errors.map((error, index) => (
                <li key={index}>
                  <strong>{error.dataset.replaceAll("_", " ")}</strong>
                  <p>{error.message}</p>
                  {!!error.fields.length && <small>Fields: {error.fields.join(", ")}</small>}
                  {error.record_number !== null && error.record_number > 0
                    && review.dataset_counts.some((item) => item.dataset === error.dataset
                      && item.record_count >= (error.record_number ?? 0)) ? (
                      <button className="text-action" type="button"
                        onClick={() => selectRecord(error.dataset, error.record_number ?? 1)}>
                        Inspect {error.dataset.replaceAll("_", " ")} record {error.record_number}
                      </button>
                    ) : null}
                </li>
              ))}
            </ol>
          )}
          {outcome.errors_truncated && <p>Showing bounded examples. Group counts include all validation errors.</p>}
          <div className="workflow-draft-inspector" aria-label="Generated record inspector">
            <label>
              <span>Inspect generated dataset</span>
              <select value={dataset} onChange={(event) => selectRecord(event.target.value)}>
                <option value="">Choose a dataset…</option>
                {review.dataset_counts.filter((item) => item.record_count > 0).map((item) => (
                  <option key={item.dataset} value={item.dataset}>
                    {item.dataset.replaceAll("_", " ")} ({item.record_count})
                  </option>
                ))}
              </select>
            </label>
            {dataset && (recordsQuery.isPending ? (
              <p aria-busy="true">Loading generated records…</p>
            ) : recordsQuery.isError || !recordsMatch ? (
              <p className="inline-error" role="alert">Generated records could not be loaded or the draft changed. Refresh runs to reload it.</p>
            ) : (
              <>
                <div className="workflow-draft-record-navigation">
                  <label>
                    <span>Record number</span>
                    <input type="number" min={1} max={records.length} value={recordNumber}
                      onChange={(event) => {
                        const value = Number(event.target.value);
                        if (Number.isSafeInteger(value) && value >= 1 && value <= records.length) setRecordNumber(value);
                      }} />
                  </label>
                  <span>of {records.length}</span>
                  <button className="button button-secondary button-small" type="button" disabled={recordNumber <= 1}
                    onClick={() => setRecordNumber((value) => value - 1)}>Previous record</button>
                  <button className="button button-secondary button-small" type="button" disabled={recordNumber >= records.length}
                    onClick={() => setRecordNumber((value) => value + 1)}>Next record</button>
                </div>
                {record ? (
                  <article aria-label={`Generated ${dataset.replaceAll("_", " ")} record ${recordNumber}`}>
                    <NormalizedJson value={record} />
                  </article>
                ) : <p>No generated record at this position.</p>}
              </>
            ))}
          </div>
        </>
      )}
    </section>
  );
}
