import { Link } from "@tanstack/react-router";

export type ProjectLayer = "logical" | "dimensional";
export const projectLayerSearch = (search: Record<string, unknown>): { layer?: ProjectLayer } => (
  search.layer === "logical" || search.layer === "dimensional" ? { layer: search.layer } : {}
);

export function ProjectLayerTabs({ tenantId, projectId, layer, workflow, title }: {
  tenantId: number; projectId: number; layer: ProjectLayer;
  workflow: "code-generation" | "validation"; title: string;
}) {
  return <div className="mapping-layer-header">
    <h1 className="project-section-title sr-only">{title}</h1>
    <nav className="target-layer-switch" aria-label={`${title} layer`}>
      {(["logical", "dimensional"] as const).map((value) => <Link key={value}
        to={workflow === "code-generation" ? "/tenants/$tenantId/code-generation/projects/$projectId" : "/tenants/$tenantId/validation/projects/$projectId"}
        params={{ tenantId: String(tenantId), projectId: String(projectId) }} search={{ layer: value }}
        className={layer === value ? "is-active" : ""} aria-current={layer === value ? "page" : undefined}
      >{value === "logical" ? "Logical" : "Dimensional"}</Link>)}
    </nav>
    <span>{layer === "logical" ? "Logical Entities → Silver" : "Dimensional Entities → Gold"}</span>
  </div>;
}
