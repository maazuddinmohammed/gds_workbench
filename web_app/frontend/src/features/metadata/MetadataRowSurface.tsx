import { useEffect, useMemo, useRef, useState } from "react";

import type {
  MetadataDatasetDescription,
  MetadataRow,
  MetadataRowSchema,
} from "./api";
import {
  metadataFieldLabel,
  metadataPropertyIsNullable,
  metadataPropertySchema,
  metadataRowKey,
  metadataValueText,
} from "./api";

export function MetadataRowDetail({
  descriptor,
  row,
  isStaged,
  canEdit,
  editDisabledReason,
  onClose,
  onEdit,
}: {
  descriptor: MetadataDatasetDescription;
  row: MetadataRow;
  isStaged: boolean;
  canEdit: boolean;
  editDisabledReason: string;
  onClose: () => void;
  onEdit: () => void;
}) {
  const closeRef = useRef<HTMLButtonElement>(null);
  useEffect(() => {
    closeRef.current?.focus();
    const onKeyDown = (event: KeyboardEvent) => {
      if (event.key === "Escape") onClose();
    };
    document.addEventListener("keydown", onKeyDown);
    return () => document.removeEventListener("keydown", onKeyDown);
  }, [onClose]);

  return (
    <div className="metadata-detail-scrim">
      <aside
        className="metadata-row-detail page-enter"
        role="dialog"
        aria-modal="true"
        aria-labelledby="metadata-row-detail-title"
      >
        <header>
          <div>
            <p className="eyebrow">{descriptor.label} · normalized row</p>
            <h2 id="metadata-row-detail-title">Row details</h2>
            <p>
              {descriptor.natural_key.map((field) => metadataValueText(row[field])).join(" · ")}
            </p>
          </div>
          <div>
            {isStaged ? <span className="metadata-staged-badge">Pending change</span> : null}
            {descriptor.change_set_eligible ? (
              <button
                className="button button-secondary button-small"
                type="button"
                disabled={!canEdit}
                title={canEdit ? "Stage an edit in the open change set" : editDisabledReason}
                onClick={onEdit}
              >
                Edit row
              </button>
            ) : null}
            <button
              ref={closeRef}
              className="dialog-close"
              type="button"
              aria-label="Close Metadata row details"
              onClick={onClose}
            >
              ×
            </button>
          </div>
        </header>
        <dl className="metadata-detail-grid">
          {descriptor.columns.map((field) => {
            const value = row[field];
            const multiline = typeof value === "string" && (
              value.includes("\n") || value.length > 160
            );
            return (
              <div key={field} className={multiline ? "is-wide" : undefined}>
                <dt>
                  {metadataFieldLabel(field)}
                  {descriptor.natural_key.includes(field) ? <small>Natural key</small> : null}
                </dt>
                <dd>
                  {multiline ? <pre>{value}</pre> : metadataValueText(value)}
                </dd>
              </div>
            );
          })}
        </dl>
      </aside>
    </div>
  );
}

export function MetadataRowEditor({
  mode,
  descriptor,
  rowSchema,
  baseRow,
  isSaving,
  onClose,
  onStage,
}: {
  mode: "add" | "edit";
  descriptor: MetadataDatasetDescription;
  rowSchema: MetadataRowSchema;
  baseRow: MetadataRow;
  isSaving: boolean;
  onClose: () => void;
  onStage: (record: MetadataRow, previousKey?: string) => Promise<void>;
}) {
  const closeRef = useRef<HTMLButtonElement>(null);
  const initialDraft = useMemo(() => Object.fromEntries(
    descriptor.columns.map((field) => {
      const value = baseRow[field];
      const property = metadataPropertySchema(rowSchema.properties[field] ?? {});
      if (mode === "add") return [field, property.type === "boolean" ? false : ""];
      return [field, typeof value === "boolean" ? value : value === null ? "" : String(value)];
    }),
  ), [baseRow, descriptor.columns, mode, rowSchema.properties]);
  const initialNullFields = useMemo(() => new Set(descriptor.columns.filter((field) => (
    metadataPropertyIsNullable(rowSchema.properties[field] ?? {})
    && (mode === "add" || baseRow[field] === null)
  ))), [baseRow, descriptor.columns, mode, rowSchema.properties]);
  const [draft, setDraft] = useState<Record<string, string | boolean>>(initialDraft);
  const [nullFields, setNullFields] = useState(initialNullFields);
  const [message, setMessage] = useState("");
  useEffect(() => {
    closeRef.current?.focus();
    const onKeyDown = (event: KeyboardEvent) => {
      if (event.key === "Escape" && !isSaving) onClose();
    };
    document.addEventListener("keydown", onKeyDown);
    return () => document.removeEventListener("keydown", onKeyDown);
  }, [isSaving, onClose]);

  const submit = async () => {
    const record: MetadataRow = {};
    for (const field of descriptor.columns) {
      const property = metadataPropertySchema(rowSchema.properties[field] ?? {});
      const value = draft[field];
      if (nullFields.has(field)) {
        record[field] = null;
      } else if (property.type === "boolean") {
        record[field] = value === true;
      } else if (property.type === "integer" || property.type === "number") {
        const parsed = Number(value);
        if (!Number.isFinite(parsed) || (
          property.type === "integer" && !Number.isSafeInteger(parsed)
        )) {
          setMessage(`${metadataFieldLabel(field)} must be a valid ${property.type}.`);
          return;
        }
        record[field] = parsed;
      } else {
        record[field] = String(value);
      }
    }
    setMessage("");
    try {
      await onStage(
        record,
        mode === "edit" ? metadataRowKey(baseRow, descriptor.natural_key) : undefined,
      );
      onClose();
    } catch {
      setMessage("The row could not be staged. Review its complete normalized values and retry.");
    }
  };

  return (
    <div className="dialog-scrim prompt-dialog-scrim metadata-editor-scrim" role="presentation">
      <section
        className="prompt-dialog metadata-row-editor"
        role="dialog"
        aria-modal="true"
        aria-labelledby="metadata-row-editor-title"
      >
        <header>
          <div>
            <p className="eyebrow">Pending Metadata Change Set</p>
            <h2 id="metadata-row-editor-title">
              {mode === "add" ? "Add" : "Edit"} {descriptor.label} row
            </h2>
          </div>
          <button
            ref={closeRef}
            className="dialog-close"
            type="button"
            aria-label={`Close ${mode === "add" ? "Add" : "Edit"} Metadata row`}
            disabled={isSaving}
            onClick={onClose}
          >
            ×
          </button>
        </header>
        <p className="metadata-editor-note">
          All canonical columns are submitted together. Natural keys cannot be renamed during an edit.
        </p>
        <form
          className="metadata-row-form"
          onSubmit={(event) => {
            event.preventDefault();
            void submit();
          }}
        >
          <div className="metadata-row-fields">
            {descriptor.columns.map((field) => {
              const rawProperty = rowSchema.properties[field] ?? {};
              const property = metadataPropertySchema(rawProperty);
              const isNaturalKey = descriptor.natural_key.includes(field);
              const isNullable = metadataPropertyIsNullable(rawProperty);
              const isRequired = rowSchema.required?.includes(field) ?? false;
              const isNull = nullFields.has(field);
              const value = draft[field];
              const multiline = property.type === "string" && (
                String(baseRow[field] ?? "").includes("\n")
                || String(baseRow[field] ?? "").length > 160
                || /(?:description|script|transformation|custom_code)$/.test(field)
              );
              const disabled = isSaving || isNull || (mode === "edit" && isNaturalKey);
              return (
                <label key={field} className={multiline ? "is-wide" : undefined}>
                  <span>
                    {metadataFieldLabel(field)}
                    <small>{isNaturalKey ? "Natural key" : isRequired ? "Required" : "Optional"}</small>
                  </span>
                  {property.type === "boolean" ? (
                    <select
                      aria-label={metadataFieldLabel(field)}
                      value={value === true ? "true" : "false"}
                      disabled={disabled}
                      onChange={(event) => setDraft((current) => ({
                        ...current,
                        [field]: event.target.value === "true",
                      }))}
                    >
                      <option value="true">Yes</option>
                      <option value="false">No</option>
                    </select>
                  ) : property.enum?.length ? (
                    <select
                      aria-label={metadataFieldLabel(field)}
                      value={String(value)}
                      disabled={disabled}
                      onChange={(event) => setDraft((current) => ({
                        ...current,
                        [field]: event.target.value,
                      }))}
                    >
                      <option value="">Choose…</option>
                      {property.enum.filter((option) => option !== null).map((option) => (
                        <option key={String(option)} value={String(option)}>{String(option)}</option>
                      ))}
                    </select>
                  ) : multiline ? (
                    <textarea
                      aria-label={metadataFieldLabel(field)}
                      value={String(value)}
                      disabled={disabled}
                      minLength={property.minLength}
                      maxLength={property.maxLength}
                      onChange={(event) => setDraft((current) => ({
                        ...current,
                        [field]: event.target.value,
                      }))}
                    />
                  ) : (
                    <input
                      aria-label={metadataFieldLabel(field)}
                      type={property.type === "integer" || property.type === "number" ? "number" : "text"}
                      inputMode={property.type === "integer" || property.type === "number" ? "numeric" : undefined}
                      min={property.minimum ?? property.exclusiveMinimum}
                      max={property.maximum ?? property.exclusiveMaximum}
                      step={property.type === "integer" ? 1 : undefined}
                      minLength={property.minLength}
                      maxLength={property.maxLength}
                      pattern={property.pattern}
                      placeholder={property.format === "date"
                        ? "YYYY-MM-DD"
                        : property.format === "date-time"
                          ? "ISO 8601 date-time"
                          : undefined}
                      value={String(value)}
                      disabled={disabled}
                      onChange={(event) => setDraft((current) => ({
                        ...current,
                        [field]: event.target.value,
                      }))}
                    />
                  )}
                  {isNullable && !(mode === "edit" && isNaturalKey) ? (
                    <span className="metadata-null-toggle">
                      <input
                        aria-label={`Set ${metadataFieldLabel(field)} to null`}
                        type="checkbox"
                        checked={isNull}
                        disabled={isSaving}
                        onChange={(event) => setNullFields((current) => {
                          const next = new Set(current);
                          if (event.target.checked) next.add(field);
                          else next.delete(field);
                          return next;
                        })}
                      />
                      Store null
                    </span>
                  ) : null}
                </label>
              );
            })}
          </div>
          <footer>
            <span role="alert">{message}</span>
            <div>
              <button
                className="button button-secondary"
                type="button"
                disabled={isSaving}
                onClick={onClose}
              >
                Cancel
              </button>
              <button className="button button-primary" type="submit" disabled={isSaving}>
                {isSaving ? "Staging…" : "Stage complete row"}
              </button>
            </div>
          </footer>
        </form>
      </section>
    </div>
  );
}
