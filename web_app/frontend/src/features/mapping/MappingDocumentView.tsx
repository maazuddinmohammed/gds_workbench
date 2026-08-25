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
        <span>{document === null ? "Not authored" : `${Object.keys(document).length} sections`}</span>
      </header>
      {document === null ? (
        <p className="detail-empty">No {title.toLocaleLowerCase()} is stored.</p>
      ) : (
        <DocumentValue value={document} path={title} />
      )}
    </section>
  );
}

function DocumentValue({ value, path }: { value: JsonValue; path: string }) {
  if (value === null) return <span className="json-null">Not specified</span>;
  if (Array.isArray(value)) {
    if (value.length === 0) return <span className="json-null">No entries</span>;
    const records = value.some((entry) => typeof entry === "object" && entry !== null);
    return records ? (
      <div className="mapping-document-list">
        {value.map((entry, index) => (
          <article key={`${path}-${index}`} aria-label={`${humanize(lastSegment(path))} ${index + 1}`}>
            <small>Record {index + 1}</small>
            <DocumentValue value={entry} path={`${path}.${index}`} />
          </article>
        ))}
      </div>
    ) : (
      <ul className="mapping-value-list">
        {value.map((entry, index) => <li key={`${path}-${index}`}><DocumentValue value={entry} path={`${path}.${index}`} /></li>)}
      </ul>
    );
  }
  if (typeof value === "object") {
    return (
      <dl className="normalized-json mapping-normalized-document">
        {Object.entries(value).map(([key, entry]) => (
          <div key={`${path}.${key}`}>
            <dt>{humanize(key)}</dt>
            <dd><DocumentValue value={entry} path={`${path}.${key}`} /></dd>
          </div>
        ))}
      </dl>
    );
  }
  if (typeof value === "boolean") return <span>{value ? "Yes" : "No"}</span>;
  return <span>{String(value)}</span>;
}

function lastSegment(path: string): string {
  return path.split(".").at(-1) ?? "record";
}

function humanize(value: string): string {
  return value.replaceAll("_", " ").replace(/^./, (character) => character.toLocaleUpperCase());
}
