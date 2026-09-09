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

const EMPTY_FIXED_VALUES: MetadataRow = {};

function isValidCalendarDate(value: string): boolean {
  const match = /^(\d{4})-(\d{2})-(\d{2})$/.exec(value);
  if (!match) return false;
  const year = Number(match[1]);
  const month = Number(match[2]);
  const day = Number(match[3]);
  const leapYear = year % 4 === 0 && (year % 100 !== 0 || year % 400 === 0);
  const daysInMonth = [31, leapYear ? 29 : 28, 31, 30, 31, 30, 31, 31, 30, 31, 30, 31];
  const maximumDay = daysInMonth[month - 1];
  return year >= 1 && maximumDay !== undefined && day >= 1 && day <= maximumDay;
}

function isValidDateTime(value: string): boolean {
  const dateTimePattern = /^\d{4}-\d{2}-\d{2}T(?:[01]\d|2[0-3]):[0-5]\d:[0-5]\d(?:\.\d+)?(?:Z|[+-](?:[01]\d|2[0-3]):[0-5]\d)$/i;
  return dateTimePattern.test(value)
    && isValidCalendarDate(value.slice(0, 10))
    && Number.isFinite(Date.parse(value));
}

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
        className="metadata-row-detail"
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
  fixedValues = EMPTY_FIXED_VALUES,
  baseRow,
  isSaving,
  onClose,
  onStage,
}: {
  mode: "add" | "edit";
  descriptor: MetadataDatasetDescription;
  rowSchema: MetadataRowSchema;
  fixedValues?: MetadataRow;
  baseRow: MetadataRow;
  isSaving: boolean;
  onClose: () => void;
  onStage: (record: MetadataRow, previousKey?: string) => Promise<void>;
}) {
  const closeRef = useRef<HTMLButtonElement>(null);
  const initialDraft = useMemo(() => Object.fromEntries(
    descriptor.columns.map((field) => {
      const value = Object.hasOwn(fixedValues, field) ? fixedValues[field] : baseRow[field];
      const property = metadataPropertySchema(rowSchema.properties[field] ?? {});
      if (mode === "add" && !Object.hasOwn(fixedValues, field)) {
        return [field, property.type === "boolean" ? false : ""];
      }
      return [field, typeof value === "boolean" ? value : value === null ? "" : String(value)];
    }),
  ), [baseRow, descriptor.columns, fixedValues, mode, rowSchema.properties]);
  const initialNullFields = useMemo(() => new Set(descriptor.columns.filter((field) => (
    !Object.hasOwn(fixedValues, field)
    &&
    metadataPropertyIsNullable(rowSchema.properties[field] ?? {})
    && (mode === "add" || baseRow[field] === null)
  ))), [baseRow, descriptor.columns, fixedValues, mode, rowSchema.properties]);
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
      const label = metadataFieldLabel(field);
      const isRequired = rowSchema.required?.includes(field) ?? false;
      if (Object.hasOwn(fixedValues, field)) {
        record[field] = fixedValues[field] ?? null;
      } else if (nullFields.has(field)) {
        record[field] = null;
      } else if (property.type === "boolean") {
        const parsed = value === true;
        if (property.enum && !property.enum.includes(parsed)) {
          setMessage(`${label} must use one of the available values.`);
          return;
        }
        record[field] = parsed;
      } else if (property.type === "integer" || property.type === "number") {
        const rawValue = String(value).trim();
        if (!rawValue) {
          setMessage(isRequired
            ? `${label} is required.`
            : `${label} must be a valid ${property.type}.`);
          return;
        }
        const parsed = Number(rawValue);
        if (!Number.isFinite(parsed) || (
          property.type === "integer" && !Number.isSafeInteger(parsed)
        )) {
          setMessage(`${label} must be a valid ${property.type}.`);
          return;
        }
        if (property.minimum !== undefined && parsed < property.minimum) {
          setMessage(`${label} must be at least ${property.minimum}.`);
          return;
        }
        if (property.maximum !== undefined && parsed > property.maximum) {
          setMessage(`${label} must be at most ${property.maximum}.`);
          return;
        }
        if (property.exclusiveMinimum !== undefined && parsed <= property.exclusiveMinimum) {
          setMessage(`${label} must be greater than ${property.exclusiveMinimum}.`);
          return;
        }
        if (property.exclusiveMaximum !== undefined && parsed >= property.exclusiveMaximum) {
          setMessage(`${label} must be less than ${property.exclusiveMaximum}.`);
          return;
        }
        if (property.enum && !property.enum.includes(parsed)) {
          setMessage(`${label} must use one of the available values.`);
          return;
        }
        record[field] = parsed;
      } else {
        const text = String(value);
        const length = [...text].length;
        if (!text && isRequired && (
          (property.minLength ?? 0) > 0 || property.enum?.length
        )) {
          setMessage(`${label} is required.`);
          return;
        }
        if (property.minLength !== undefined && length < property.minLength) {
          setMessage(`${label} is too short.`);
          return;
        }
        if (property.maxLength !== undefined && length > property.maxLength) {
          setMessage(`${label} is too long.`);
          return;
        }
        if (property.enum && !property.enum.includes(text)) {
          setMessage(`${label} must use one of the available values.`);
          return;
        }
        if (property.format === "date" && !isValidCalendarDate(text)) {
          setMessage(`${label} must be a valid YYYY-MM-DD date.`);
          return;
        }
        if (property.format === "date-time" && !isValidDateTime(text)) {
          setMessage(`${label} must be a valid ISO 8601 date-time with a timezone.`);
          return;
        }
        if (property.pattern !== undefined) {
          let matches = false;
          try {
            matches = new RegExp(property.pattern, "u").test(text);
          } catch {
            setMessage(`${label} has an invalid field definition.`);
            return;
          }
          if (!matches) {
            setMessage(`${label} has an invalid format.`);
            return;
          }
        }
        record[field] = text;
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
        className="run-configuration-dialog prompt-dialog metadata-row-editor"
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
          noValidate
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
              const isFixed = Object.hasOwn(fixedValues, field);
              const isNullable = metadataPropertyIsNullable(rawProperty);
              const isRequired = rowSchema.required?.includes(field) ?? false;
              const isNull = nullFields.has(field);
              const value = draft[field];
              const multiline = property.type === "string" && (
                String(baseRow[field] ?? "").includes("\n")
                || String(baseRow[field] ?? "").length > 160
                || /(?:description|script|transformation|custom_code)$/.test(field)
              );
              const disabled = isSaving || isNull || isFixed || (mode === "edit" && isNaturalKey);
              return (
                <label key={field} className={multiline ? "is-wide" : undefined}>
                  <span>
                    {metadataFieldLabel(field)}
                    <small>{isFixed
                      ? "Fixed value"
                      : isNaturalKey
                        ? "Natural key"
                        : isNullable
                          ? "Nullable"
                          : isRequired
                            ? "Required"
                            : "Optional"}</small>
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
                      min={property.minimum}
                      max={property.maximum}
                      step={property.type === "integer" ? 1 : undefined}
                      minLength={property.minLength}
                      maxLength={property.maxLength}
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
