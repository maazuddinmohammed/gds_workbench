import type { JsonObject } from "../../shared/contracts";
import { MappingDocumentValue } from "./MappingDocumentView";

const sourceFields = new Set([
  "source_objects", "source_logical_entities", "source_dimensional_entities",
  "source_attributes", "source_logical_attributes", "source_dimensional_attributes",
]);
const primaryFields = ["transformation", "steps", "transformation_steps"];

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
  return <div className="mapping-logic-document">
    {main.length ? <div className="mapping-logic-main">
      {main.map(([key, value]) => <section className="mapping-logic-field" key={key}>
        <h3 title={key}>{key.replaceAll("_", " ").replace(/^./, (letter) => letter.toLocaleUpperCase()) || "Unnamed field"}</h3>
        {key === "transformation" && typeof value === "string"
          ? <p className="mapping-logic-expression">{value === "" ? '\"\"' : value}</p>
          : <MappingDocumentValue value={value} path={`${path}[${JSON.stringify(key)}]`}
            tabular={key !== "steps" && key !== "transformation_steps"} />}
      </section>)}
    </div> : null}
    {sources.length ? <section className="mapping-logic-sources" aria-label="Sources">
      <h3>Sources</h3>
      <MappingDocumentValue value={Object.fromEntries(sources)} path={path} tabular />
    </section> : null}
  </div>;
}
