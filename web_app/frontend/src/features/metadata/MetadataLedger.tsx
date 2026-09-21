import {
  metadataFieldLabel,
  metadataValueText,
  type MetadataDatasetDescription,
  type MetadataRow,
} from "./api";

export interface MetadataLedgerState {
  isLoading: boolean;
  isFetching: boolean;
  isDenied: boolean;
  isError: boolean;
  hasNext: boolean;
  hasPrevious: boolean;
}

export function MetadataLedger({
  descriptor, items, state, canAdd, addDisabledReason,
  onOpenRow, onAdd, onNext, onPrevious,
}: {
  descriptor: MetadataDatasetDescription;
  items: MetadataRow[];
  state: MetadataLedgerState;
  canAdd: boolean;
  addDisabledReason: string;
  onOpenRow: (row: MetadataRow) => void;
  onAdd: () => void;
  onNext: () => void;
  onPrevious: () => void;
}) {
  return (
    <section className="metadata-catalog-browser" aria-labelledby="metadata-sheet-heading">
      <header>
        <div className="metadata-catalog-sheet-summary">
          <p className="eyebrow">{descriptor.section} sheet</p>
          <h2 id="metadata-sheet-heading">{descriptor.label}</h2>
          <span>{descriptor.columns.length} columns · {items.length} rows on this page</span>
        </div>
        {descriptor.section === "operational" ? (
          <button
            className="button button-secondary button-small"
            type="button"
            disabled={!canAdd}
            title={canAdd ? "Stage a complete normalized row" : addDisabledReason}
            onClick={onAdd}
          >
            Add row
          </button>
        ) : (
          <span className="metadata-readonly-badge">Read-only</span>
        )}
      </header>

      {state.isLoading ? (
        <div className="surface-state" aria-busy="true">Loading {descriptor.label}…</div>
      ) : state.isDenied ? (
        <div className="surface-state is-error" role="alert">You do not have permission to view this Metadata sheet.</div>
      ) : state.isError ? (
        <div className="surface-state is-error" role="alert">This Metadata sheet could not be loaded. Refresh to retry.</div>
      ) : items.length === 0 ? (
        <div className="empty-state compact">No rows are available for this sheet.</div>
      ) : (
        <div className="metadata-catalog-table-frame">
          <div className="metadata-catalog-table-guide">
            <span>All {descriptor.columns.length} columns shown</span>
            <span>Scroll horizontally for additional fields · first column and actions remain visible</span>
          </div>
          <div className="metadata-catalog-table" role="region" aria-label={`${descriptor.label} table scroll area`} tabIndex={0}>
            <table aria-label={`${descriptor.label} normalized Metadata`}>
              <thead>
                <tr>
                  {descriptor.columns.map((field, index) => (
                    <th key={field} scope="col" className={columnClass(field, index)}>{metadataFieldLabel(field)}</th>
                  ))}
                  <th scope="col" className="is-sticky-action">Actions</th>
                </tr>
              </thead>
              <tbody>
                {items.map((row, rowIndex) => (
                  <tr key={`${descriptor.dataset}-${rowIndex}`}>
                    {descriptor.columns.map((field, index) => (
                      <td key={field} className={columnClass(field, index)}>
                        <span className={descriptor.natural_key.includes(field) ? "is-key" : undefined}>
                          {metadataValueText(row[field])}
                        </span>
                      </td>
                    ))}
                    <td className="is-sticky-action">
                      <button className="text-action" type="button" onClick={() => onOpenRow(row)}>Show details</button>
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        </div>
      )}

      <footer className="metadata-catalog-pagination" aria-label="Metadata sheet pagination">
        <span aria-live="polite">{state.isFetching && !state.isLoading ? "Refreshing page…" : `${items.length} rows on page`}</span>
        <div>
          <button className="button button-secondary button-small" type="button" disabled={!state.hasPrevious || state.isFetching} onClick={onPrevious}>Previous</button>
          <button className="button button-secondary button-small" type="button" disabled={!state.hasNext || state.isFetching} onClick={onNext}>Next</button>
        </div>
      </footer>
    </section>
  );
}

function columnClass(field: string, index: number): string {
  return `${index === 0 ? "is-sticky-key " : ""}${/(?:description|transformation|script|sql)/.test(field) ? "is-wide" : ""}`;
}
