import { SourceMappings } from "../projects/SourceMappings";
import { EntityAttributes } from "../projects/EntityAttributes";
import { EntitySubjectAreas } from "../projects/EntitySubjectAreas";
import { ModelSubjectAreaView } from "../projects/ModelSubjectAreas";
import { useEffect, useRef, type ReactNode } from "react";
import { useInfiniteQuery, useQuery } from "@tanstack/react-query";
import { Link } from "@tanstack/react-router";

import { DetailState, Fact } from "../../shared/ui";
import { ApiError } from "../../core/http";
import type {
  DimensionalAttributeDetail,
  DimensionalObjectDetail,
  DimensionalRelationshipDetail,
} from "./api";
import { formatRequiredDateTime as formatDateTime } from "../../shared/presentation";
import { dimensionalQueryKeys, type DimensionalApi } from "./api";

export function DimensionalObjectDetailPage({
  actions,
  api,
  tenantId,
  projectId,
  projectRevision,
  hasTenantLock,
  entityId,
}: {
  actions?: ReactNode;
  api: DimensionalApi;
  tenantId: number;
  projectId: number;
  projectRevision: number;
  hasTenantLock: boolean;
  entityId: number;
}) {
  const query = useQuery({
    queryKey: dimensionalQueryKeys.object(tenantId, projectId, entityId),
    queryFn: () => api.readDimensionalObject(tenantId, projectId, entityId),
  });
  if (query.isPending) return <DetailState label="Loading Dimensional Entity…" />;
  if (query.isError) {
    return <DetailState
      label={query.error instanceof ApiError && query.error.status === 403
        ? "You do not have permission to view this Dimensional Entity."
        : "Dimensional Entity details could not be loaded."}
      error
    />;
  }
  return <DimensionalObjectView actions={actions} projectRevision={projectRevision} hasTenantLock={hasTenantLock} api={api} tenantId={tenantId} projectId={projectId} object={query.data} />;
}

/** One Subject Area's active Dimensional Entities, each opening the usual Entity page. */
export function DimensionalSubjectAreaPage({ api, tenantId, projectId, projectRevision, subjectAreaId }: {
  api: DimensionalApi;
  tenantId: number;
  projectId: number;
  projectRevision: number;
  subjectAreaId: number;
}) {
  // Same cache entry as the Subject Areas tab.
  const areasQuery = useQuery({
    queryKey: dimensionalQueryKeys.subjectAreas(tenantId, projectId),
    queryFn: () => api.listDimensionalSubjectAreas(tenantId, projectId),
  });
  const filters = { subjectAreaId, active: true };
  const entitiesQuery = useInfiniteQuery({
    queryKey: dimensionalQueryKeys.objects(tenantId, projectId, filters),
    queryFn: ({ pageParam }) => api.listDimensionalObjects(tenantId, projectId, filters, 200, pageParam),
    initialPageParam: undefined as string | undefined,
    getNextPageParam: (lastPage) => lastPage.next_cursor ?? undefined,
  });
  if (areasQuery.isPending) return <DetailState label="Loading Subject Area…" />;
  if (areasQuery.isError) return <DetailState label="Subject Area could not be loaded." error />;
  const area = areasQuery.data.items.find((item) => item.subject_area_id === subjectAreaId);
  if (!area) return <DetailState label="This Subject Area is not active. Return to Dimensional and refresh." error />;
  return <ModelSubjectAreaView layer="dimensional" tenantId={tenantId} projectId={projectId} area={area}
    projectRevision={projectRevision} quickView={{ layer: "dimensional", api }}
    entities={(entitiesQuery.data?.pages.flatMap((page) => page.items) ?? []).map((entity) => ({
      id: entity.dimensional_entity_id,
      schema: entity.dimensional_entity_schema_name,
      name: entity.dimensional_entity_name,
      type: entity.dimensional_fact_type
        ? `${humanize(entity.dimensional_entity_type)} · ${humanize(entity.dimensional_fact_type)}`
        : humanize(entity.dimensional_entity_type),
      active: entity.dimensional_entity_is_active,
      locked: entity.dimensional_entity_is_locked,
      updatedAt: entity.updated_at,
    }))}
    state={{
      isLoading: entitiesQuery.isPending,
      isError: entitiesQuery.isError,
      revisionMismatch: areasQuery.data.project_revision !== projectRevision
        || (entitiesQuery.data?.pages.some((page) => page.project_revision !== projectRevision) ?? false),
    }}
    hasMore={entitiesQuery.hasNextPage} isLoadingMore={entitiesQuery.isFetchingNextPage}
    onLoadMore={() => void entitiesQuery.fetchNextPage()} />;
}

export function DimensionalAttributeDetailPage({
  actions,
  api,
  tenantId,
  projectId,
  attributeId,
}: {
  actions?: ReactNode;
  api: DimensionalApi;
  tenantId: number;
  projectId: number;
  attributeId: number;
}) {
  const query = useQuery({
    queryKey: dimensionalQueryKeys.attribute(tenantId, projectId, attributeId),
    queryFn: () => api.readDimensionalAttribute(tenantId, projectId, attributeId),
  });
  if (query.isPending) return <DetailState label="Loading Dimensional Attribute…" />;
  if (query.isError) return <DetailState label={detailErrorLabel(query.error, "Attribute")} error />;
  return <DimensionalAttributeView
    actions={actions}
    tenantId={tenantId}
    projectId={projectId}
    attribute={query.data}
  />;
}

export function DimensionalRelationshipDetailPage({
  actions,
  api,
  tenantId,
  projectId,
  relationshipId,
}: {
  actions?: ReactNode;
  api: DimensionalApi;
  tenantId: number;
  projectId: number;
  relationshipId: number;
}) {
  const query = useQuery({
    queryKey: dimensionalQueryKeys.relationship(tenantId, projectId, relationshipId),
    queryFn: () => api.readDimensionalRelationship(tenantId, projectId, relationshipId),
  });
  if (query.isPending) return <DetailState label="Loading Dimensional Relationship…" />;
  if (query.isError) return <DetailState label={detailErrorLabel(query.error, "Relationship")} error />;
  return <DimensionalRelationshipView
    actions={actions}
    tenantId={tenantId}
    projectId={projectId}
    relationship={query.data}
  />;
}

function DimensionalObjectView({
  actions,
  api,
  tenantId,
  projectId,
  projectRevision,
  hasTenantLock,
  object,
}: {
  actions?: ReactNode;
  tenantId: number;
  projectId: number;
  projectRevision: number;
  hasTenantLock: boolean;
  object: DimensionalObjectDetail;
  api: DimensionalApi;
}) {
  const heading = useRef<HTMLHeadingElement>(null);
  useEffect(() => heading.current?.focus(), []);
  return (
    <article className="workflow-detail-page dimensional-detail-page modeled-detail-page page-enter">
      <header className="workflow-detail-header workspace-entity-heading">
        <div>
          <Link
            className="text-action"
            aria-label="Back to Dimensional"
            to="/tenants/$tenantId/projects/$projectId/dimensional"
            params={{ tenantId: String(tenantId), projectId: String(projectId) }}
          >
            ← Back to Dimensional
          </Link>
          <h1 ref={heading} tabIndex={-1}>{object.dimensional_entity_schema_name}.{object.dimensional_entity_name}</h1>
        </div>
        <div className="workflow-command-actions">
          <div className="detail-badge-stack">
            <span className={`status-badge ${object.dimensional_entity_is_active ? "is-success" : "is-neutral"}`}>
              {object.dimensional_entity_is_active ? "Active" : "Inactive"}
            </span>
            <span className="status-badge is-neutral">
              {object.dimensional_entity_is_locked ? "Locked" : "Open"}
            </span>
          </div>
          {actions}
        </div>
      </header>
      <section className="detail-section detail-primary" aria-labelledby="dimensional-object-overview">
        <header><h2 id="dimensional-object-overview">Entity definition</h2></header>
        <dl className="modeled-detail-fields">
          <div className="is-definition"><dt>Definition</dt><dd>{object.dimensional_entity_definition}</dd></div>
          <Fact label="Type" value={humanize(object.dimensional_entity_type)} />
          {object.dimensional_fact_type !== null ? <Fact label="Fact type" value={humanize(object.dimensional_fact_type)} /> : null}
          <Fact label="Grain" value={object.dimensional_entity_grain_definition ?? "Not specified"} />
          <Fact label="Dependency order" value={String(object.dimensional_entity_dependency_order)} />
          <EntitySubjectAreas tenantId={tenantId} projectId={projectId} areas={object.subject_areas} />
          <Fact label="Updated" value={formatDateTime(object.updated_at)} />
        </dl>
      </section>
      <EntityAttributes projectRevision={projectRevision} hasTenantLock={hasTenantLock} api={api} layer="dimensional" tenantId={tenantId} projectId={projectId} entityId={object.dimensional_entity_id} />
      <SourceMappings sources={object.sources} />
    </article>
  );
}

function DimensionalAttributeView({
  actions,
  tenantId,
  projectId,
  attribute,
}: {
  actions?: ReactNode;
  tenantId: number;
  projectId: number;
  attribute: DimensionalAttributeDetail;
}) {
  return (
    <article className="workflow-detail-page dimensional-detail-page modeled-detail-page page-enter">
      <DimensionalDetailHeader
        actions={actions}
        tenantId={tenantId}
        projectId={projectId}
        parentEntityId={attribute.dimensional_entity_id}
        title={attribute.dimensional_attribute_name}
        active={attribute.dimensional_attribute_is_active}
        locked={attribute.dimensional_attribute_is_locked}
      />
      <section className="detail-section detail-primary" aria-labelledby="dimensional-attribute-overview">
        <header><h2 id="dimensional-attribute-overview">Attribute definition</h2></header>
        <dl className="modeled-detail-fields">
          <div className="is-definition"><dt>Definition</dt><dd>{attribute.dimensional_attribute_definition}</dd></div>
          <Fact label="Entity" value={`${attribute.dimensional_entity_schema_name}.${attribute.dimensional_entity_name}`} />
        </dl>
        <h3>Type and nullability</h3>
        <dl className="modeled-detail-fields">
          <Fact label="Data type" value={attribute.dimensional_attribute_data_type} />
          <Fact label="Ordinal" value={String(attribute.dimensional_attribute_ordinal_position)} />
          <Fact label="Nullable" value={attribute.dimensional_attribute_is_nullable ? "Yes" : "No"} />
          <Fact label="Audit column" value={attribute.dimensional_attribute_is_audit_column ? "Yes" : "No"} />
        </dl>
        <h3>Keys</h3>
        <dl className="modeled-detail-fields">
          <Fact label="Natural key" value={attribute.dimensional_attribute_is_natural_key ? "Yes" : "No"} />
          <Fact label="Surrogate key" value={attribute.dimensional_attribute_is_surrogate_key ? "Yes" : "No"} />
        </dl>
      </section>
      <SourceMappings sources={attribute.sources} />
    </article>
  );
}

/** A Relationship points from the child Entity's foreign key to the parent Entity's key. */
function DimensionalRelationshipView({
  actions,
  tenantId,
  projectId,
  relationship,
}: {
  actions?: ReactNode;
  tenantId: number;
  projectId: number;
  relationship: DimensionalRelationshipDetail;
}) {
  const from = `${relationship.from_dimensional_entity_schema_name}.${relationship.from_dimensional_entity_name}`;
  const to = `${relationship.to_dimensional_entity_schema_name}.${relationship.to_dimensional_entity_name}`;
  return (
    <article className="workflow-detail-page dimensional-detail-page modeled-detail-page page-enter">
      <DimensionalDetailHeader
        actions={actions}
        tenantId={tenantId}
        projectId={projectId}
        title={`${from}.${relationship.from_dimensional_attribute_name} → ${to}.${relationship.to_dimensional_attribute_name}`}
        active={relationship.dimensional_relationship_is_active}
        locked={relationship.dimensional_relationship_is_locked}
      />
      <section className="detail-section detail-primary" aria-labelledby="dimensional-relationship-overview">
        <header><h2 id="dimensional-relationship-overview">Relationship definition</h2></header>
        <dl className="modeled-detail-fields">
          <div><dt>From Entity</dt><dd>
            <Link className="text-action" to="/tenants/$tenantId/projects/$projectId/dimensional/objects/$entityId"
              params={{ tenantId: String(tenantId), projectId: String(projectId), entityId: String(relationship.from_dimensional_entity_id) }}>
              {from}
            </Link>
          </dd></div>
          <Fact label="Foreign key Attribute" value={relationship.from_dimensional_attribute_name} />
          <div><dt>To Entity</dt><dd>
            <Link className="text-action" to="/tenants/$tenantId/projects/$projectId/dimensional/objects/$entityId"
              params={{ tenantId: String(tenantId), projectId: String(projectId), entityId: String(relationship.to_dimensional_entity_id) }}>
              {to}
            </Link>
          </dd></div>
          <Fact label="Key Attribute" value={relationship.to_dimensional_attribute_name} />
          <Fact label="Role" value={relationship.dimensional_relationship_role_name ?? "None"} />
          <div className="is-definition"><dt>Basis</dt><dd>{relationship.dimensional_relationship_basis ?? "Not recorded"}</dd></div>
          <Fact label="Updated" value={formatDateTime(relationship.updated_at)} />
        </dl>
      </section>
    </article>
  );
}

function DimensionalDetailHeader({
  actions,
  tenantId,
  projectId,
  parentEntityId,
  title,
  active,
  locked,
}: {
  actions?: ReactNode;
  tenantId: number;
  projectId: number;
  parentEntityId?: number;
  title: string;
  active: boolean;
  locked: boolean;
}) {
  const heading = useRef<HTMLHeadingElement>(null);
  useEffect(() => heading.current?.focus(), []);
  return (
    <header className="workflow-detail-header workspace-entity-heading">
      <div>
        <Link
          className="text-action"
          aria-label={parentEntityId ? "Back to Entity" : "Back to Dimensional"}
          to={parentEntityId ? "/tenants/$tenantId/projects/$projectId/dimensional/objects/$entityId" : "/tenants/$tenantId/projects/$projectId/dimensional"}
          params={{ tenantId: String(tenantId), projectId: String(projectId), ...(parentEntityId ? { entityId: String(parentEntityId) } : {}) }}
        >
          ← {parentEntityId ? "Back to Entity" : "Back to Dimensional"}
        </Link>
        <h1 ref={heading} tabIndex={-1}>{title}</h1>
      </div>
      <div className="workflow-command-actions">
        <div className="detail-badge-stack">
          <span className={`status-badge ${active ? "is-success" : "is-neutral"}`}>{active ? "Active" : "Inactive"}</span>
          <span className="status-badge is-neutral">{locked ? "Locked" : "Open"}</span>
        </div>
        {actions}
      </div>
    </header>
  );
}

function detailErrorLabel(error: Error, artifact: "Attribute" | "Relationship"): string {
  return error instanceof ApiError && error.status === 403
    ? `You do not have permission to view this Dimensional ${artifact}.`
    : `Dimensional ${artifact} details could not be loaded.`;
}

function humanize(value: string): string {
  return value.replaceAll("_", " ").replace(/^./, (character) => character.toLocaleUpperCase());
}
