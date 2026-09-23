import { Link } from "@tanstack/react-router";

export type ModelLayer = "logical" | "dimensional";
export const modelLayerSearch = (search: Record<string, unknown>): { layer?: ModelLayer } => (
  search.layer === "logical" || search.layer === "dimensional" ? { layer: search.layer } : {}
);

export function ModelLayerTabs({ tenantId, modelId, layer, workflow, title }: {
  tenantId: number; modelId: number; layer: ModelLayer;
  workflow: "code-generation" | "validation"; title: string;
}) {
  return <header className="mapping-layer-header">
    <h1>{title}</h1>
    <nav className="target-layer-switch" aria-label={`${title} layer`}>
      {(["logical", "dimensional"] as const).map((value) => <Link key={value}
        to={workflow === "code-generation" ? "/tenants/$tenantId/code-generation/models/$modelId" : "/tenants/$tenantId/validation/models/$modelId"}
        params={{ tenantId: String(tenantId), modelId: String(modelId) }} search={{ layer: value }}
        className={layer === value ? "is-active" : ""} aria-current={layer === value ? "page" : undefined}
      >{value === "logical" ? "Logical" : "Dimensional"}</Link>)}
    </nav>
    <span>{layer === "logical" ? "Logical Entities → Silver" : "Dimensional Entities → Gold"}</span>
  </header>;
}
