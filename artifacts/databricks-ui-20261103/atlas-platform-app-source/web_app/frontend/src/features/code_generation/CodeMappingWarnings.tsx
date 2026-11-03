import type { CodeMappingSupport } from "./api";

export function CodeMappingWarnings({ supports, systemCodes }: {
  supports: CodeMappingSupport[];
  systemCodes: string[];
}) {
  return <>{supports.map((support) => {
    if (!systemCodes.includes(support.source_system.system_code)) return null;
    const missingAttributes = support.unmapped_attribute_count ?? 0;
    const gaps = [
      ...(support.object_transformation_missing ? ["Entity transformation missing"] : []),
      ...(missingAttributes > 0 ? [`${missingAttributes} Attribute${missingAttributes === 1 ? "" : "s"} without transformations`] : []),
    ];
    if (!gaps.length) return null;
    return <div className="code-mapping-warning" key={support.mapping_object_id}>
      <strong>{support.source_system.system_code}:</strong> {gaps.join("; ")}. {missingAttributes > 0
        ? "Typed NULL placeholders need review." : "Entity logic needs review."}
      {support.unmapped_attribute_names?.length ? <details>
        <summary>Unmapped Attributes</summary>
        <p>{support.unmapped_attribute_names.join(", ")}{missingAttributes > support.unmapped_attribute_names.length ? " …" : ""}</p>
      </details> : null}
    </div>;
  })}</>;
}
