import type { JsonObject, JsonValue } from "../../shared/contracts";

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
          <DocumentValue value={document} path={title} />
          <details className="support-record-details"><summary>Original document</summary><pre className="mapping-original-document" tabIndex={0}><code>{JSON.stringify(document, null, 2)}</code></pre></details>
        </>
      )}
    </section>
  );
}

function DocumentValue({ value, path }: { value: JsonValue; path: string }) {
  if (value === null) return <span className="mapping-json-scalar"><span>Not set</span></span>;
  if (Array.isArray(value)) {
    if (value.length === 0) return <span className="mapping-json-scalar"><span>No items</span></span>;
    return (
      <ol className="mapping-value-list" aria-label={path}>
        {value.map((entry, index) => (
          <li key={index}><DocumentValue value={entry} path={`${path}[${index}]`} /></li>
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
            <dd><DocumentValue value={entry} path={`${path}[${JSON.stringify(key)}]`} /></dd>
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
