import { useEffect, useRef, useState } from "react";
import { Link } from "@tanstack/react-router";

import type { ModelSubjectArea } from "../../shared/contracts";
import { formatRequiredDateTime as formatDateTime } from "../../shared/presentation";
import { BuildStatus, Fact } from "../../shared/ui";
import { EntityQuickView, type EntityQuickViewSource } from "./EntityQuickView";

type ModelLayer = "logical" | "dimensional";
const LAYER_NAMES: Record<ModelLayer, string> = { logical: "Logical", dimensional: "Dimensional" };

interface ListState {
  isLoading: boolean;
  isError: boolean;
  revisionMismatch: boolean;
}

/** One Entity of either layer, as the Subject Area page lists it. */
export interface ModelSubjectAreaEntity {
  id: number;
  schema: string;
  name: string;
  type: string;
  active: boolean;
  locked: boolean;
  updatedAt: string;
}

/** The layer's Subject Areas tab: each active area with its Objects and this layer's Entities. */
export function ModelSubjectAreasLedger({ layer, tenantId, projectId, areas, state }: {
  layer: ModelLayer;
  tenantId: number;
  projectId: number;
  areas: ModelSubjectArea[];
  state: ListState;
}) {
  const layerName = LAYER_NAMES[layer];
  const params = (area: ModelSubjectArea) => ({
    tenantId: String(tenantId), projectId: String(projectId), subjectAreaId: String(area.subject_area_id),
  });
  return <section className="workflow-surface" aria-label={`${layerName} Subject Areas`}>
    {state.isLoading ? <div className="surface-state" aria-busy="true">Loading Subject Areas…</div>
      : state.isError ? <div className="surface-state is-error" role="alert">Subject Areas could not be loaded.</div>
        : state.revisionMismatch ? <div className="surface-state is-error" role="alert">
          The Project changed while Subject Areas were loading. Refresh to reconcile revisions.
        </div>
          : areas.length === 0 ? <div className="empty-state compact">
            No active Subject Areas yet. Group the Input Scope in Subject Areas first.
          </div>
            : <div className="workflow-table-scroll table-scroll ledger-grid" tabIndex={0} role="region"
              aria-label={`Scrollable ${layerName} Subject Areas`}>
              <table className="model-subject-area-ledger" aria-label={`${layerName} Subject Areas`}>
                <thead><tr>
                  <th>Subject Area</th><th>Objects</th>
                  <th>{layerName} Entities</th><th>Last build</th><th />
                </tr></thead>
                <tbody>{areas.map((area) => <tr key={area.subject_area_id}>
                  <td><span className="endpoint-cell">
                    <strong>{area.subject_area_name}</strong>
                    <span>{area.subject_area_definition}</span>
                  </span></td>
                  <td className="is-numeric">{area.table_count}</td>
                  <td className="is-numeric">{area.entity_count}</td>
                  <td><BuildStatus build={area.build} /></td>
                  <td>{layer === "logical"
                    ? <Link className="text-action" aria-label={`Show ${area.subject_area_name} Entities`}
                      to="/tenants/$tenantId/projects/$projectId/logical/subject-areas/$subjectAreaId" params={params(area)}>
                      Show Entities
                    </Link>
                    : <Link className="text-action" aria-label={`Show ${area.subject_area_name} Entities`}
                      to="/tenants/$tenantId/projects/$projectId/dimensional/subject-areas/$subjectAreaId" params={params(area)}>
                      Show Entities
                    </Link>}</td>
                </tr>)}</tbody>
              </table>
            </div>}
  </section>;
}

/**
 * One Subject Area inside a model layer: its Entities, each opening the same Entity page
 * as the Entities tab, or a quick view beside the list. The area itself is edited in the
 * Subject Areas section.
 */
export function ModelSubjectAreaView({
  layer, tenantId, projectId, projectRevision, area, entities, state, hasMore, isLoadingMore, onLoadMore, quickView,
}: {
  layer: ModelLayer;
  tenantId: number;
  projectId: number;
  projectRevision: number;
  area: ModelSubjectArea;
  entities: ModelSubjectAreaEntity[];
  state: ListState;
  hasMore: boolean;
  isLoadingMore: boolean;
  onLoadMore: () => void;
  quickView: EntityQuickViewSource;
}) {
  const layerName = LAYER_NAMES[layer];
  const [quickViewId, setQuickViewId] = useState<number | null>(null);
  const quickViewEntity = entities.find((entity) => entity.id === quickViewId);
  // Closing the quick view returns focus to the icon that opened it.
  const quickViewButtons = useRef(new Map<number, HTMLButtonElement>());
  const closeQuickView = () => {
    const openedFrom = quickViewId === null ? undefined : quickViewButtons.current.get(quickViewId);
    setQuickViewId(null);
    openedFrom?.focus({ preventScroll: true });
  };
  const heading = useRef<HTMLHeadingElement>(null);
  useEffect(() => heading.current?.focus(), [area.subject_area_id]);
  const projectParams = { tenantId: String(tenantId), projectId: String(projectId) };
  return <article className="workflow-detail-page modeled-detail-page page-enter">
    <header className="workflow-detail-header">
      <div>
        {layer === "logical"
          ? <Link className="text-action" to="/tenants/$tenantId/projects/$projectId/logical" params={projectParams}
            search={{ view: "subject_areas" }}>← Back to Subject Areas</Link>
          : <Link className="text-action" to="/tenants/$tenantId/projects/$projectId/dimensional" params={projectParams}
            search={{ view: "subject_areas" }}>← Back to Subject Areas</Link>}
        <h1 ref={heading} tabIndex={-1}>{area.subject_area_name}</h1>
      </div>
      <div className="workflow-command-actions">
        <Link className="button button-secondary button-small" to="/tenants/$tenantId/projects/$projectId/subject-areas/$subjectAreaId"
          params={{ ...projectParams, subjectAreaId: String(area.subject_area_id) }}>Edit Subject Area</Link>
      </div>
    </header>

    <section className="detail-section detail-primary" aria-labelledby="model-subject-area-overview">
      <header><h2 id="model-subject-area-overview">Subject Area</h2></header>
      <dl className="modeled-detail-fields">
        <div className="is-definition"><dt>Definition</dt><dd>{area.subject_area_definition}</dd></div>
        <Fact label="Objects" value={String(area.table_count)} />
        <Fact label={`${layerName} Entities`} value={String(area.entity_count)} />
        <div><dt>Last build</dt><dd><BuildStatus build={area.build} showLabel /></dd></div>
      </dl>
    </section>

    <section className="detail-section" aria-labelledby="model-subject-area-entities">
      <header><h2 id="model-subject-area-entities">{layerName} Entities</h2></header>
      {state.isLoading ? <div className="surface-state" aria-busy="true">Loading {layerName} Entities…</div>
        : state.isError ? <div className="surface-state is-error" role="alert">{layerName} Entities could not be loaded.</div>
          : state.revisionMismatch ? <div className="surface-state is-error" role="alert">
            The Project changed while {layerName} Entities were loading. Refresh to reconcile revisions.
          </div>
            : entities.length === 0 ? <p className="detail-empty">
              No active {layerName} Entities come from this Subject Area yet. Run a {layerName} Build for it.
            </p>
              : <div className="table-scroll" role="region" aria-label={`Scrollable ${area.subject_area_name} Entities`} tabIndex={0}>
                <table className="model-subject-area-entities" aria-label={`${area.subject_area_name} ${layerName} Entities`}>
                  <thead><tr>
                    <th>Schema</th><th>Entity name</th><th>Status</th><th>Lock</th><th>Updated</th>
                    <th className="quick-view-cell"><span className="sr-only">Quick view</span></th><th />
                  </tr></thead>
                  <tbody>{entities.map((entity) => {
                    const entityParams = { ...projectParams, entityId: String(entity.id) };
                    return <tr key={entity.id} className={entity.id === quickViewId ? "is-active" : undefined}>
                      <td>{entity.schema}</td>
                      <td><span className="endpoint-cell"><strong>{entity.name}</strong><span>{entity.type}</span></span></td>
                      <td>{entity.active ? "Active" : "Inactive"}</td>
                      <td>{entity.locked ? "Locked" : "Open"}</td>
                      <td>{formatDateTime(entity.updatedAt)}</td>
                      <td className="quick-view-cell">
                        <button type="button" className="quick-view-button" title="Quick view"
                          aria-label={`Quick view of ${entity.name}`} aria-expanded={entity.id === quickViewId} aria-controls="entity-quick-view"
                          ref={(node) => { if (node) quickViewButtons.current.set(entity.id, node); else quickViewButtons.current.delete(entity.id); }}
                          onClick={() => setQuickViewId(entity.id)}>
                          <svg aria-hidden="true" viewBox="0 0 24 24">
                            <path d="M2.5 12S6 5.5 12 5.5 21.5 12 21.5 12 18 18.5 12 18.5 2.5 12 2.5 12Z" /><circle cx="12" cy="12" r="2.75" />
                          </svg>
                        </button>
                      </td>
                      <td>{layer === "logical"
                        ? <Link className="text-action" aria-label={`Open Logical Entity ${entity.id}`}
                          to="/tenants/$tenantId/projects/$projectId/logical/entities/$entityId" params={entityParams}>Show details</Link>
                        : <Link className="text-action" aria-label={`Open Dimensional Entity ${entity.id}`}
                          to="/tenants/$tenantId/projects/$projectId/dimensional/objects/$entityId" params={entityParams}>Show details</Link>}</td>
                    </tr>;
                  })}</tbody>
                </table>
                {hasMore ? <div className="ledger-pagination">
                  <button className="button button-secondary button-small" type="button" disabled={isLoadingMore} onClick={onLoadMore}>
                    {isLoadingMore ? "Loading…" : `Load more ${layerName} Entities`}
                  </button>
                </div> : null}
              </div>}
    </section>
    {quickViewEntity ? <EntityQuickView key={quickViewEntity.id} source={quickView} tenantId={tenantId} projectId={projectId}
      projectRevision={projectRevision} entity={quickViewEntity} onClose={closeQuickView} /> : null}
  </article>;
}
