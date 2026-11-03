import { useEffect, useRef, useState } from "react";

import {
  metadataFieldLabel,
  metadataValueText,
  type MetadataChangeSetDetail,
  type MetadataDatasetDescription,
  type MetadataValidationReview,
} from "./api";
import { trapDialogFocus, useDialogFocus } from "../../shared/dialog";

const MAX_WORKBOOK_BYTES = 32 * 1024 * 1024;

export function MetadataChangeSetPanel({
  changeSet, selectedDataset, review, canWrite, hasTenantLock, isBusy,
  onCreateOrResume, onValidate, onApply, onArchive, onImport,
}: {
  changeSet: MetadataChangeSetDetail | null;
  selectedDataset: MetadataDatasetDescription | null;
  review: MetadataValidationReview | null;
  canWrite: boolean;
  hasTenantLock: boolean;
  isBusy: boolean;
  onCreateOrResume: () => Promise<void>;
  onValidate: () => Promise<void>;
  onApply: () => Promise<void>;
  onArchive: () => Promise<void>;
  onImport: (file: File) => Promise<void>;
}) {
  const fileInput = useRef<HTMLInputElement>(null);
  const [file, setFile] = useState<File | null>(null);
  const [message, setMessage] = useState("");
  const [confirmation, setConfirmation] = useState<"apply" | "archive" | null>(null);
  const active = changeSet?.status === "active" || changeSet?.status === "validated";
  const canMutate = canWrite && hasTenantLock && active;
  const stagedCount = changeSet?.dataset_counts.reduce((total, item) => total + item.record_count, 0) ?? 0;
  const selectedCount = changeSet?.dataset_counts.find((item) => item.dataset === selectedDataset?.dataset)?.record_count ?? 0;
  const canApply = canMutate && changeSet?.status === "validated" && review?.valid === true;
  const currentStep = changeSet?.status === "applied" ? 4
    : changeSet?.status === "validated" && review?.valid ? 3
      : active ? file || stagedCount > 0 ? 2 : 1 : 0;
  const writeReason = !canWrite ? "Developer permission or higher is required."
    : !hasTenantLock ? "Tenant Lock is required"
      : !active ? "Start a change set first." : "";
  const status = changeSet ? metadataFieldLabel(changeSet.status) : "No active draft";

  useEffect(() => {
    setFile(null);
    setMessage("");
    if (fileInput.current) fileInput.current.value = "";
  }, [changeSet?.metadata_change_set_id, active]);

  const run = async (action: () => Promise<void>, fallback: string) => {
    setMessage("");
    try {
      await action();
    } catch {
      setMessage(fallback);
    }
  };

  return (
    <section className="metadata-catalog-change-set" aria-labelledby="metadata-change-set-title">
      <div className="metadata-catalog-change-toolbar">
        <header>
          <div>
            <p className="eyebrow">Excel change set</p>
            <h2 id="metadata-change-set-title">Review changes before apply</h2>
          </div>
          <span className={`status-badge metadata-change-status is-${changeSet?.status ?? "idle"}`}>{status}</span>
        </header>
        <ol className="metadata-catalog-change-steps" aria-label="Change-set progress">
          {["Start draft", "Choose .xlsx", "Import & validate", "Apply"].map((label, index) => (
            <li key={label} className={index < currentStep ? "is-complete" : index === currentStep ? "is-current" : undefined} aria-current={index === currentStep ? "step" : undefined}>
              <b>{index + 1}</b><span>{label}</span>
            </li>
          ))}
        </ol>
        <div className="metadata-catalog-change-actions">
          <button
            className="button button-secondary button-small"
            type="button"
            disabled={!canWrite || !hasTenantLock || active || isBusy}
            title={!canWrite || !hasTenantLock ? writeReason : active ? "Your draft is already open." : "Start or resume your active draft"}
            onClick={() => void run(onCreateOrResume, "The Metadata Change Set could not be opened.")}
          >
            {!changeSet && isBusy ? "Opening…" : active ? "Draft open" : "Start change set"}
          </button>
          <label className={`button button-secondary button-small${!canMutate || isBusy ? " is-disabled" : ""}`} title={writeReason || "Choose a .xlsx workbook up to 32 MB"}>
            Choose Excel
            <input
              ref={fileInput}
              type="file"
              aria-label="Choose Excel"
              accept=".xlsx,application/vnd.openxmlformats-officedocument.spreadsheetml.sheet"
              disabled={!canMutate || isBusy}
              onChange={(event) => { setFile(event.target.files?.[0] ?? null); setMessage(""); }}
            />
          </label>
          <button
            className="button button-primary button-small"
            type="button"
            disabled={!canMutate || !file || isBusy}
            title={writeReason || (file ? "Import and validate the workbook" : "Choose an Excel workbook first")}
            onClick={() => {
              if (!file) return;
              if (!file.name.toLowerCase().endsWith(".xlsx") || file.size < 1 || file.size > MAX_WORKBOOK_BYTES) {
                setMessage("Choose one non-empty .xlsx file no larger than 32 MB.");
                return;
              }
              void run(async () => {
                await onImport(file);
                setFile(null);
                if (fileInput.current) fileInput.current.value = "";
              }, "The workbook was rejected or could not be imported.");
            }}
          >
            Import Excel
          </button>
        </div>
        <small className="metadata-catalog-change-note">
          {hasTenantLock ? "Tenant Lock held" : "Tenant Lock is required"}
          {file ? <span> · {file.name}</span> : null}
        </small>
      </div>

      {changeSet ? (
        <div className="metadata-catalog-change-review">
          <details className="metadata-catalog-draft-details">
            <summary>Revision {changeSet.draft_revision} · {stagedCount} staged rows</summary>
            <dl className="metadata-change-facts">
              <div><dt>Pending rows</dt><dd>{stagedCount}</dd></div>
              <div><dt>Selected sheet</dt><dd>{selectedCount}</dd></div>
              <div><dt>Expires</dt><dd>{formatTimestamp(changeSet.expires_at)}</dd></div>
              <div><dt>Digest</dt><dd><code>{changeSet.candidate_digest?.slice(0, 12) ?? "Not validated"}</code></dd></div>
            </dl>
            {changeSet.records && selectedDataset ? (
              <details className="metadata-staged-records">
                <summary>Review {selectedCount} staged {selectedDataset.label} rows</summary>
                {changeSet.records.length ? (
                  <ol>{changeSet.records.map((record, index) => (
                    <li key={`${selectedDataset.dataset}-${index}`}>
                      {selectedDataset.natural_key.map((field) => (
                        <span key={field}><small>{metadataFieldLabel(field)}</small><strong>{metadataValueText(record[field])}</strong></span>
                      ))}
                    </li>
                  ))}</ol>
                ) : <p>No rows staged for this sheet.</p>}
              </details>
            ) : null}
          </details>
          {review ? <MetadataValidationReviewView review={review} /> : null}
          {active ? (
            <footer className="metadata-catalog-review-actions">
              <button className="button button-secondary button-small" type="button" disabled={!canMutate || stagedCount === 0 || isBusy} title={writeReason || (stagedCount ? "Validate staged rows" : "Stage rows or import Excel first")} onClick={() => void run(onValidate, "The staged Metadata could not be validated.")}>Validate</button>
              <button className="button button-secondary button-small" type="button" disabled={!canMutate || isBusy} title={writeReason || "Close this draft without applying it"} onClick={() => setConfirmation("archive")}>Archive</button>
              <button className="button button-accent button-small" type="button" disabled={!canApply || isBusy} title={writeReason || (!canApply ? "Validate the draft before applying" : "Apply the validated candidate")} onClick={() => setConfirmation("apply")}>Apply validated changes</button>
            </footer>
          ) : null}
        </div>
      ) : null}
      {message ? <p className="metadata-catalog-change-error" role="alert">{message}</p> : null}

      {confirmation ? (
        <MetadataChangeSetConfirmation
          action={confirmation}
          isBusy={isBusy}
          onClose={() => setConfirmation(null)}
          onConfirm={() => void run(async () => {
            if (confirmation === "apply") await onApply();
            else await onArchive();
            setConfirmation(null);
          }, confirmation === "apply" ? "The validated Metadata could not be applied." : "The Metadata Change Set could not be archived.")}
        />
      ) : null}
    </section>
  );
}

function MetadataValidationReviewView({ review }: { review: MetadataValidationReview }) {
  return (
    <section className={review.valid ? "metadata-validation is-valid" : "metadata-validation is-invalid"}>
      <header>
        <strong>{review.valid ? "Validation passed" : "Validation needs attention"}</strong>
        <span>{review.staged_record_count} rows · {metadataFieldLabel(review.phase)}</span>
      </header>
      {review.errors.length ? (
        <ul aria-label="Metadata validation errors">
          {review.errors.map((error, index) => (
            <li key={`${error.code}-${index}`}>
              <strong>{error.dataset} · {error.code}</strong>
              <span>{error.message}</span>
              {error.fields.length ? <small>{error.fields.join(", ")}</small> : null}
            </li>
          ))}
        </ul>
      ) : null}
      {review.action_review.length ? (
        <table aria-label="Metadata action review">
          <thead><tr><th>Sheet</th><th>Insert</th><th>Update</th><th>Deactivate</th><th>Reactivate</th><th>No change</th></tr></thead>
          <tbody>
            {review.action_review.map((item) => (
              <tr key={item.dataset}>
                <td>{item.dataset}</td><td>{item.insert_count}</td><td>{item.update_count}</td>
                <td>{item.deactivate_count}</td><td>{item.reactivate_count}</td><td>{item.no_change_count}</td>
              </tr>
            ))}
          </tbody>
        </table>
      ) : null}
    </section>
  );
}

function MetadataChangeSetConfirmation({
  action,
  isBusy,
  onClose,
  onConfirm,
}: {
  action: "apply" | "archive";
  isBusy: boolean;
  onClose: () => void;
  onConfirm: () => void;
}) {
  const closeRef = useRef<HTMLButtonElement>(null);
  useDialogFocus(closeRef);
  const apply = action === "apply";
  return (
    <div className="dialog-scrim prompt-dialog-scrim" role="presentation">
      <section className="run-configuration-dialog prompt-dialog metadata-confirm-dialog" role="dialog" aria-modal="true" aria-labelledby="metadata-confirm-title" onKeyDown={(event) => {
        if (event.key === "Escape" && !isBusy) { event.stopPropagation(); onClose(); }
        trapDialogFocus(event);
      }}>
        <header>
          <div><p className="eyebrow">Governed transition</p><h2 id="metadata-confirm-title">{apply ? "Apply validated Metadata" : "Archive Change Set"}</h2></div>
          <button ref={closeRef} className="dialog-close" type="button" aria-label="Close Metadata confirmation" disabled={isBusy} onClick={onClose}>×</button>
        </header>
        <p>{apply ? "This writes the reviewed candidate to Tenant Metadata." : "This closes the draft without applying it."}</p>
        <footer><span /><div><button className="button button-secondary" type="button" disabled={isBusy} onClick={onClose}>Cancel</button><button className={apply ? "button button-accent" : "button button-primary"} type="button" disabled={isBusy} onClick={onConfirm}>{apply ? "Apply changes" : "Archive draft"}</button></div></footer>
      </section>
    </div>
  );
}

function formatTimestamp(value: string): string {
  const timestamp = new Date(value);
  return Number.isNaN(timestamp.valueOf()) ? "Unavailable" : timestamp.toLocaleString();
}
