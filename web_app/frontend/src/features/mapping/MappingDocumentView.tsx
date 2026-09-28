import type { JsonObject, JsonValue } from "../../shared/contracts";

// JSON object key order is not a source identity contract (PostgreSQL JSONB
// may reorder it). Keep familiar source columns first, retaining custom fields.
const sourceColumnOrder = [
  "tenant_code", "system_code", "connection_code", "object_schema", "object_name", "attribute_name", "alias",
];

export function MappingDocumentView({
  title,
  document,
}: {
  title: string;
  document: JsonObject | null;
}) {
  return (
    <section className="detail-section mapping-document-section" aria-label={title}>
      <header>
        <h2>{title}</h2>
        {document === null ? <span>Not authored</span> : null}
      </header>
      {document === null ? (
        <p className="detail-empty">No {title.toLocaleLowerCase()} is stored.</p>
      ) : (
        <>
          <MappingDocumentValue value={document} path={title} />
          <details className="support-record-details"><summary>Original document</summary><pre className="mapping-original-document" tabIndex={0}><code>{JSON.stringify(document, null, 2)}</code></pre></details>
        </>
      )}
    </section>
  );
}

export function MappingDocumentValue({ value, path, tabular = false }: {
  value: JsonValue; path: string; tabular?: boolean;
}) {
  if (value === null) return <span className="mapping-json-scalar"><span>Not set</span></span>;
  if (Array.isArray(value)) {
    if (value.length === 0) return <span className="mapping-json-scalar"><span>No items</span></span>;
    if (tabular && value.every((entry): entry is JsonObject => entry !== null
      && typeof entry === "object" && !Array.isArray(entry) && Object.keys(entry).length > 0)) {
      const columns = [...new Set(value.flatMap((entry) => Object.keys(entry)))];
      columns.sort((left, right) => {
        const a = sourceColumnOrder.indexOf(left), b = sourceColumnOrder.indexOf(right);
        return (a < 0 ? sourceColumnOrder.length : a) - (b < 0 ? sourceColumnOrder.length : b);
      });
      return <div className="mapping-document-table-scroll" role="region" aria-label={path} tabIndex={0}>
        <table className="mapping-document-table" aria-label={path}>
          <thead><tr>{columns.map((key) => <th key={key} scope="col" title={key} data-source-field={key}>{humanize(key) || "Unnamed field"}</th>)}</tr></thead>
          <tbody>{value.map((entry, index) => <tr key={index}>
            {columns.map((key) => <td key={key} data-source-field={key}>{Object.hasOwn(entry, key)
              ? <MappingDocumentValue value={entry[key] as JsonValue} path={`${path}[${index}][${JSON.stringify(key)}]`} tabular={tabular} />
              : <span className="mapping-json-scalar"><span>Not provided</span></span>}</td>)}
          </tr>)}</tbody>
        </table>
      </div>;
    }
    return (
      <ol className="mapping-value-list" aria-label={path}>
        {value.map((entry, index) => (
          <li key={index}><MappingDocumentValue value={entry} path={`${path}[${index}]`} tabular={tabular} /></li>
        ))}
      </ol>
    );
  }
  if (typeof value === "object") {
    if (Object.keys(value).length === 0) return <span className="mapping-json-scalar"><span>No fields</span></span>;
    return (
      <dl className="normalized-json mapping-normalized-document">
        {Object.entries(value).map(([key, entry]) => (
          <div key={key} className={entry !== null && typeof entry === "object" ? "mapping-document-branch" : undefined}>
            <dt title={key}>{humanize(key) || "Unnamed field"}</dt>
            <dd><MappingDocumentValue value={entry} path={`${path}[${JSON.stringify(key)}]`} tabular={tabular} /></dd>
          </div>
        ))}
      </dl>
    );
  }
  return (
    <span className="mapping-json-scalar">
      <span>{value === "" ? '\"\"' : String(value)}</span>
    </span>
  );
}

function humanize(value: string): string {
  return value.replaceAll("_", " ").replace(/^./, (character) => character.toLocaleUpperCase());
}
