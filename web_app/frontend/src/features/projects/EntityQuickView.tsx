import { useQuery } from "@tanstack/react-query";
import { Link } from "@tanstack/react-router";

import { SidePanel } from "../../shared/SidePanel";
import { Fact } from "../../shared/ui";
import type { DimensionalTransport } from "../dimensional/api";
import type { LogicalTransport } from "../logical/api";

/** Where a layer's quick view reads one Entity and its active Attributes. */
export type EntityQuickViewSource =
  | { layer: "logical"; api: Pick<LogicalTransport, "readLogicalEntity" | "listLogicalAttributes"> }
  | { layer: "dimensional"; api: Pick<DimensionalTransport, "readDimensionalObject" | "listDimensionalAttributes"> };

interface QuickViewDetail {
  definition: string;
  grain: string | null;
  subjectAreas: string[];
  /** Active sources: a Physical or Logical name, or null for a Context record. */
  sources: (string | null)[];
}

/**
 * One Entity's definition, facts and active Attributes in the side panel Activity uses, without
 * leaving its Subject Area. Show details opens the full Entity page.
 */
export function EntityQuickView({ source, tenantId, projectId, projectRevision, entity, onClose }: {
  source: EntityQuickViewSource;
  tenantId: number;
  projectId: number;
  projectRevision: number;
  /** The row's identity, shown while the details load. */
  entity: { id: number; schema: string; name: string; type: string };
  onClose: () => void;
}) {
  const detailQuery = useQuery({
    // Tenant second, like every key, so a review apply that refreshes the Tenant also refreshes this.
    queryKey: ["entity-quick-view", tenantId, projectId, source.layer, entity.id],
    queryFn: async (): Promise<QuickViewDetail> => {
      if (source.layer === "logical") {
        const detail = await source.api.readLogicalEntity(tenantId, projectId, entity.id);
        return {
          definition: detail.logical_entity_definition,
          grain: detail.logical_entity_grain,
          subjectAreas: detail.subject_areas.map((area) => area.subject_area_name),
          sources: detail.sources.filter((item) => item.is_active).map((item) => item.support_source_type === "object"
            ? `${item.source_object.object_schema}.${item.source_object.object_name}` : null),
        };
      }
      const detail = await source.api.readDimensionalObject(tenantId, projectId, entity.id);
      return {
        definition: detail.dimensional_entity_definition,
        grain: detail.dimensional_entity_grain_definition,
        subjectAreas: detail.subject_areas.map((area) => area.subject_area_name),
        sources: detail.sources.filter((item) => item.is_active).map((item) => item.support_source_type === "logical_entity"
          ? `${item.source_logical_entity.logical_entity_schema_name}.${item.source_logical_entity.logical_entity_name}` : null),
      };
    },
  });
  const attributesQuery = useQuery({
    queryKey: ["entity-quick-view-attributes", tenantId, projectId, source.layer, entity.id],
    queryFn: async () => {
      if (source.layer === "logical") {
        const page = await source.api.listLogicalAttributes(tenantId, projectId, { logicalEntityId: entity.id, active: true }, 200);
        return { revision: page.project_revision, more: page.next_cursor !== null, items: page.items.map((item) => ({
          id: item.logical_attribute_id, name: item.logical_attribute_name, type: item.logical_attribute_data_type,
          nullable: item.logical_attribute_is_nullable,
          role: role(item.logical_attribute_is_natural_key, item.logical_attribute_is_surrogate_key, item.logical_attribute_is_audit_column),
        })) };
      }
      const page = await source.api.listDimensionalAttributes(tenantId, projectId, { dimensionalEntityId: entity.id, active: true }, 200);
      return { revision: page.project_revision, more: page.next_cursor !== null, items: page.items.map((item) => ({
        id: item.dimensional_attribute_id, name: item.dimensional_attribute_name, type: item.dimensional_attribute_data_type,
        nullable: item.dimensional_attribute_is_nullable,
        role: role(item.dimensional_attribute_is_natural_key, item.dimensional_attribute_is_surrogate_key, item.dimensional_attribute_is_audit_column),
      })) };
    },
  });
  const detail = detailQuery.data;
  const attributes = attributesQuery.data;
  const objectSources = detail?.sources.filter((item) => item !== null) ?? [];
  const contextSources = (detail?.sources.length ?? 0) - objectSources.length;
  const params = { tenantId: String(tenantId), projectId: String(projectId), entityId: String(entity.id) };
  return <SidePanel id="entity-quick-view" className="entity-quick-view" title={entity.name} subtitle={`${entity.schema} · ${entity.type}`}
    labels={{ panel: `Quick view of ${entity.name}`, close: "Close quick view", expand: "Expand quick view", reduce: "Reduce quick view" }}
    actions={source.layer === "logical"
      ? <Link className="button button-secondary button-small" to="/tenants/$tenantId/projects/$projectId/logical/entities/$entityId"
        params={params}>Show details</Link>
      : <Link className="button button-secondary button-small" to="/tenants/$tenantId/projects/$projectId/dimensional/objects/$entityId"
        params={params}>Show details</Link>}
    onClose={onClose}>
    <div className="entity-quick-view-body">
      {detailQuery.isPending ? <p className="surface-state compact" aria-busy="true">Loading Entity…</p>
        : detailQuery.isError || !detail ? <p className="inline-error" role="alert">This Entity could not be loaded. Close the quick view and refresh.</p>
          : <>
            <p className="entity-quick-view-definition">{detail.definition}</p>
            <dl className="drawer-facts entity-quick-view-facts">
              <Fact label="Grain" value={detail.grain ?? "Not stated"} />
              <Fact label="Type" value={entity.type} />
              <Fact label="Subject Areas" value={detail.subjectAreas.join(", ") || "None"} />
              <Fact label="Sources" value={[...objectSources, ...(contextSources
                ? [`${contextSources} Context ${contextSources === 1 ? "record" : "records"}`] : [])].join(", ") || "None"} />
            </dl>
          </>}
      <section aria-labelledby="entity-quick-view-attributes">
        <h3 id="entity-quick-view-attributes">Attributes{attributes ? <span>{attributes.items.length}{attributes.more ? "+" : ""}</span> : null}</h3>
        {attributesQuery.isPending ? <p className="surface-state compact" aria-busy="true">Loading Attributes…</p>
          : attributesQuery.isError || !attributes || attributes.revision !== projectRevision
            ? <p className="inline-error" role="alert">Attributes could not be loaded consistently. Close the quick view and refresh.</p>
            : attributes.items.length === 0 ? <p className="detail-empty">No active Attributes.</p>
              : <div className="table-scroll">
                <table className="entity-quick-view-attributes" aria-label={`${entity.name} Attributes`}>
                  <thead><tr><th>Attribute</th><th>Data type</th><th>Nullable</th><th>Role</th></tr></thead>
                  <tbody>{attributes.items.map((item) => <tr key={item.id}>
                    <td><strong>{item.name}</strong></td><td>{item.type}</td><td>{item.nullable ? "Yes" : "No"}</td><td>{item.role}</td>
                  </tr>)}</tbody>
                </table>
              </div>}
        {attributes?.more ? <p className="field-help">Showing the first 200 Attributes. Show details lists every Attribute.</p> : null}
      </section>
    </div>
  </SidePanel>;
}

function role(naturalKey: boolean, surrogateKey: boolean, audit: boolean): string {
  return [naturalKey && "Natural key", surrogateKey && "Surrogate key", audit && "Audit"].filter(Boolean).join(" · ") || "—";
}
