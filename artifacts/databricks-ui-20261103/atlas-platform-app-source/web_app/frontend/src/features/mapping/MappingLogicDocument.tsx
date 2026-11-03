import type { JsonObject } from "../../shared/contracts";
import { MappingDocumentValue } from "./MappingDocumentView";

const sourceFields = new Set([
  "source_tables", "source_columns",
  "source_objects", "source_logical_entities", "source_dimensional_entities",
  "source_attributes", "source_logical_attributes", "source_dimensional_attributes",
]);
const primaryFields = ["transformation_logic", "filter_criteria", "sample_query", "transformation", "steps", "transformation_steps"];

export function MappingLogicDocument({ document, path }: { document: JsonObject; path: string }) {
  const sources = Object.entries(document).filter(([key]) => sourceFields.has(key));
  const main = Object.entries(document).filter(([key]) => !sourceFields.has(key))
    .sort(([left], [right]) => {
      const leftIndex = primaryFields.indexOf(left);
      const rightIndex = primaryFields.indexOf(right);
      return (leftIndex < 0 ? primaryFields.length : leftIndex)
        - (rightIndex < 0 ? primaryFields.length : rightIndex);
    });

  if (!sources.length && !main.length) return <MappingDocumentValue value={document} path={path} />;
  return <div className="mapping-logic-document mapping-logic-grid">
    {[...sources, ...main].map(([key, value]) => {
      const label = key.replaceAll("_", " ").replace(/^./, (letter) => letter.toLocaleUpperCase()) || "Unnamed field";
      return <section className={`mapping-logic-field${sourceFields.has(key) ? " is-source" : ""}`}
        key={key} aria-label={label}>
        <h3 title={key}>{label}</h3>
        <div className="mapping-logic-value">
          {(key === "transformation" || key === "sample_query") && typeof value === "string"
            ? <p className="mapping-logic-expression">{value === "" ? '\"\"' : value}</p>
            : <MappingDocumentValue value={value} path={`${path}[${JSON.stringify(key)}]`}
              tabular={key !== "steps" && key !== "transformation_steps"} />}
        </div>
      </section>;
    })}
  </div>;
}
