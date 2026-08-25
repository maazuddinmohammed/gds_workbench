import type { JsonObject, JsonValue } from "../../shared/contracts";

export function NormalizedJson({ value }: { value: JsonObject }) {
  const entries = Object.entries(value);
  if (!entries.length) return <p className="detail-empty">No structured values recorded.</p>;
  return (
    <dl className="normalized-json">
      {entries.map(([key, item]) => (
        <div key={key}>
          <dt>{humanize(key)}</dt>
          <dd><JsonNode value={item} /></dd>
        </div>
      ))}
    </dl>
  );
}

function JsonNode({ value }: { value: JsonValue }) {
  if (value === null) return <span className="json-null">Not recorded</span>;
  if (Array.isArray(value)) {
    if (!value.length) return <span className="json-null">None</span>;
    return (
      <ol className="json-array">
        {value.map((item, index) => (
          <li key={`${index}-${primitiveKey(item)}`}><JsonNode value={item} /></li>
        ))}
      </ol>
    );
  }
  if (typeof value === "object") return <NormalizedJson value={value} />;
  if (typeof value === "boolean") return <span>{value ? "Yes" : "No"}</span>;
  if (typeof value === "string") return <span>{value}</span>;
  return <span>{new Intl.NumberFormat().format(value)}</span>;
}

function primitiveKey(value: JsonValue): string {
  return typeof value === "object" ? "group" : String(value).slice(0, 40);
}

function humanize(value: string): string {
  return value
    .replaceAll("_", " ")
    .replaceAll(".", " · ")
    .replace(/^./, (character) => character.toLocaleUpperCase());
}
