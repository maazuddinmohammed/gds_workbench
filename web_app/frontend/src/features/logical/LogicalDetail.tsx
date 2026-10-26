import { SourceMappings } from "../projects/SourceMappings";
import { EntityAttributes } from "../projects/EntityAttributes";
import { EntitySubjectAreas } from "../projects/EntitySubjectAreas";
import { ModelSubjectAreaView } from "../projects/ModelSubjectAreas";
import { useEffect, useRef, type ReactNode } from "react";
import { useInfiniteQuery, useQuery } from "@tanstack/react-query";
import { Link } from "@tanstack/react-router";

import { DetailState, Fact } from "../../shared/ui";
import type {
  LogicalAttributeDetail,
  LogicalEntityDetail,
  LogicalRelationshipDetail,
} from "./api";
import { formatRequiredDateTime as formatDateTime } from "../../shared/presentation";
import { logicalQueryKeys, type LogicalApi } from "./api";

export function LogicalEntityDetailPage({
  actions,
  api,
  tenantId,
  projectId,
  projectRevision,
  hasTenantLock,
  entityId,
}: {
  actions?: ReactNode;
  api: LogicalApi;
  tenantId: number;
  projectId: number;
  projectRevision: number;
  hasTenantLock: boolean;
  entityId: number;
}) {
  const query = useQuery({
    queryKey: logicalQueryKeys.entity(tenantId, projectId, entityId),
    queryFn: () => api.readLogicalEntity(tenantId, projectId, entityId),
  });
  if (query.isPending) return <DetailState label="Loading Logical Entity…" />;
  if (query.isError) return <DetailState label="Logical Entity details could not be loaded." error />;
  return <LogicalEntityView actions={actions} projectRevision={projectRevision} hasTenantLock={hasTenantLock} api={api} tenantId={tenantId} projectId={projectId} entity={query.data} />;
}

/** One Subject Area's active Logical Entities, each opening the usual Entity page. */
export function LogicalSubjectAreaPage({ api, tenantId, projectId, projectRevision, subjectAreaId }: {
  api: LogicalApi;
  tenantId: number;
  projectId: number;
  projectRevision: number;
  subjectAreaId: number;
}) {
  // Same cache entry as the Subject Areas tab.
  const areasQuery = useQuery({
    queryKey: logicalQueryKeys.subjectAreas(tenantId, projectId),
    queryFn: () => api.listLogicalSubjectAreas(tenantId, projectId),
  });
  const filters = { subjectAreaId, active: true };
  const entitiesQuery = useInfiniteQuery({
    queryKey: logicalQueryKeys.entities(tenantId, projectId, filters),
    queryFn: ({ pageParam }) => api.listLogicalEntities(tenantId, projectId, filters, 200, pageParam),
    initialPageParam: undefined as string | undefined,
    getNextPageParam: (lastPage) => lastPage.next_cursor ?? undefined,
  });
  if (areasQuery.isPending) return <DetailState label="Loading Subject Area…" />;
  if (areasQuery.isError) return <DetailState label="Subject Area could not be loaded." error />;
  const area = areasQuery.data.items.find((item) => item.subject_area_id === subjectAreaId);
  if (!area) return <DetailState label="This Subject Area is not active. Return to Logical and refresh." error />;
  return <ModelSubjectAreaView layer="logical" tenantId={tenantId} projectId={projectId} area={area}
    entities={(entitiesQuery.data?.pages.flatMap((page) => page.items) ?? []).map((entity) => ({
      id: entity.logical_entity_id,
      schema: entity.logical_entity_schema_name,
      name: entity.logical_entity_name,
      type: humanize(entity.logical_entity_type),
      active: entity.logical_entity_is_active,
      locked: entity.logical_entity_is_locked,
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

export function LogicalAttributeDetailPage({
  actions,
  api,
  tenantId,
  projectId,
  attributeId,
}: {
  actions?: ReactNode;
  api: LogicalApi;
  tenantId: number;
  projectId: number;
  attributeId: number;
}) {
  const query = useQuery({
    queryKey: logicalQueryKeys.attribute(tenantId, projectId, attributeId),
    queryFn: () => api.readLogicalAttribute(tenantId, projectId, attributeId),
  });
  if (query.isPending) return <DetailState label="Loading Logical Attribute…" />;
  if (query.isError) return <DetailState label="Logical Attribute details could not be loaded." error />;
  return <LogicalAttributeView actions={actions} tenantId={tenantId} projectId={projectId} attribute={query.data} />;
}

export function LogicalRelationshipDetailPage({
  actions,
  api,
  tenantId,
  projectId,
  relationshipId,
}: {
  actions?: ReactNode;
  api: LogicalApi;
  tenantId: number;
  projectId: number;
  relationshipId: number;
}) {
  const query = useQuery({
    queryKey: logicalQueryKeys.relationship(tenantId, projectId, relationshipId),
    queryFn: () => api.readLogicalRelationship(tenantId, projectId, relationshipId),
  });
  if (query.isPending) return <DetailState label="Loading Logical Relationship…" />;
  if (query.isError) {
    return <DetailState label="Logical Relationship details could not be loaded." error />;
  }
  return (
    <LogicalRelationshipView
      actions={actions}
      tenantId={tenantId}
      projectId={projectId}
      relationship={query.data}
    />
  );
}

function LogicalEntityView({
  actions,
  api,
  tenantId,
  projectId,
  projectRevision,
  hasTenantLock,
  entity,
}: {
  actions?: ReactNode;
  tenantId: number;
  projectId: number;
  projectRevision: number;
  hasTenantLock: boolean;
  entity: LogicalEntityDetail;
  api: LogicalApi;
}) {
  return (
    <article className="workflow-detail-page logical-detail-page modeled-detail-page page-enter">
      <LogicalDetailHeader
        actions={actions}
        tenantId={tenantId} projectId={projectId}
        recordId={entity.logical_entity_id}
        title={`${entity.logical_entity_schema_name}.${entity.logical_entity_name}`}
        active={entity.logical_entity_is_active}
        locked={entity.logical_entity_is_locked}
      />

      <section className="detail-section detail-primary" aria-labelledby="logical-entity-overview">
        <header><h2 id="logical-entity-overview">Entity definition</h2></header>
        <dl className="modeled-detail-fields">
          <div className="is-definition"><dt>Definition</dt><dd>{entity.logical_entity_definition}</dd></div>
          <Fact label="Grain" value={entity.logical_entity_grain} />
          <Fact label="Type" value={humanize(entity.logical_entity_type)} />
          <Fact label="Dependency order" value={String(entity.logical_entity_dependency_order)} />
          <EntitySubjectAreas tenantId={tenantId} projectId={projectId} areas={entity.subject_areas} />
          <Fact label="Updated" value={formatDateTime(entity.updated_at)} />
        </dl>
      </section>

      <EntityAttributes projectRevision={projectRevision} hasTenantLock={hasTenantLock} api={api} layer="logical" tenantId={tenantId} projectId={projectId} entityId={entity.logical_entity_id} />
      <SourceMappings sources={entity.sources} />
    </article>
  );
}

function LogicalAttributeView({
  actions,
  tenantId,
  projectId,
  attribute,
}: {
  actions?: ReactNode;
  tenantId: number;
  projectId: number;
  attribute: LogicalAttributeDetail;
}) {
  return (
    <article className="workflow-detail-page logical-detail-page modeled-detail-page page-enter">
      <LogicalDetailHeader
        actions={actions}
        tenantId={tenantId}
        projectId={projectId}
        parentEntityId={attribute.logical_entity_id}
        recordId={attribute.logical_attribute_id}
        title={attribute.logical_attribute_name}
        active={attribute.logical_attribute_is_active}
        locked={attribute.logical_attribute_is_locked}
      />
      <section className="detail-section detail-primary" aria-labelledby="logical-attribute-overview">
        <header><h2 id="logical-attribute-overview">Attribute definition</h2></header>
        <dl className="modeled-detail-fields">
          <div className="is-definition"><dt>Definition</dt><dd>{attribute.logical_attribute_definition}</dd></div>
          <Fact label="Entity" value={`${attribute.logical_entity_schema_name}.${attribute.logical_entity_name}`} />
        </dl>
        <h3>Type and nullability</h3>
        <dl className="modeled-detail-fields">
          <Fact label="Data type" value={attribute.logical_attribute_data_type} />
          <Fact label="Ordinal" value={String(attribute.logical_attribute_ordinal_position)} />
          <Fact label="Nullable" value={attribute.logical_attribute_is_nullable ? "Yes" : "No"} />
          <Fact label="Audit column" value={attribute.logical_attribute_is_audit_column ? "Yes" : "No"} />
        </dl>
        <h3>Keys</h3>
        <dl className="modeled-detail-fields">
          <Fact label="Natural key" value={attribute.logical_attribute_is_natural_key ? "Yes" : "No"} />
          <Fact label="Surrogate key" value={attribute.logical_attribute_is_surrogate_key ? "Yes" : "No"} />
        </dl>
      </section>
      <SourceMappings sources={attribute.sources} />
    </article>
  );
}

/** A Relationship points from the child Entity's foreign key to the parent Entity's key. */
function LogicalRelationshipView({
  actions,
  tenantId,
  projectId,
  relationship,
}: {
  actions?: ReactNode;
  tenantId: number;
  projectId: number;
  relationship: LogicalRelationshipDetail;
}) {
  const from = `${relationship.from_logical_entity_schema_name}.${relationship.from_logical_entity_name}`;
  const to = `${relationship.to_logical_entity_schema_name}.${relationship.to_logical_entity_name}`;
  return (
    <article className="workflow-detail-page logical-detail-page modeled-detail-page page-enter">
      <LogicalDetailHeader
        actions={actions}
        tenantId={tenantId}
        projectId={projectId}
        recordId={relationship.logical_relationship_id}
        title={`${from}.${relationship.from_logical_attribute_name} → ${to}.${relationship.to_logical_attribute_name}`}
        active={relationship.logical_relationship_is_active}
        locked={relationship.logical_relationship_is_locked}
      />
      <section className="detail-section detail-primary" aria-labelledby="logical-relationship-overview">
        <header><h2 id="logical-relationship-overview">Relationship definition</h2></header>
        <dl className="modeled-detail-fields">
          <div><dt>From Entity</dt><dd>
            <Link className="text-action" to="/tenants/$tenantId/projects/$projectId/logical/entities/$entityId"
              params={{ tenantId: String(tenantId), projectId: String(projectId), entityId: String(relationship.from_logical_entity_id) }}>
              {from}
            </Link>
          </dd></div>
          <Fact label="Foreign key Attribute" value={relationship.from_logical_attribute_name} />
          <div><dt>To Entity</dt><dd>
            <Link className="text-action" to="/tenants/$tenantId/projects/$projectId/logical/entities/$entityId"
              params={{ tenantId: String(tenantId), projectId: String(projectId), entityId: String(relationship.to_logical_entity_id) }}>
              {to}
            </Link>
          </dd></div>
          <Fact label="Key Attribute" value={relationship.to_logical_attribute_name} />
          <Fact label="Cardinality" value={humanize(relationship.logical_relationship_cardinality)} />
          <div className="is-definition"><dt>Basis</dt><dd>{relationship.logical_relationship_basis}</dd></div>
          <Fact label="Updated" value={formatDateTime(relationship.updated_at)} />
        </dl>
      </section>
    </article>
  );
}

function LogicalDetailHeader({
  actions,
  tenantId,
  projectId,
  recordId,
  title,
  active,
  locked,
  parentEntityId,
}: {
  actions?: ReactNode;
  tenantId: number;
  projectId: number;
  recordId: number;
  title: string;
  active: boolean;
  locked: boolean;
  parentEntityId?: number;
}) {
  const heading = useRef<HTMLHeadingElement>(null);
  useEffect(() => heading.current?.focus(), [recordId]);
  return (
    <header className="workflow-detail-header">
      <div>
        <Link
          className="text-action"
          aria-label={parentEntityId ? "Back to Entity" : "Back to Logical"}
          to={parentEntityId ? "/tenants/$tenantId/projects/$projectId/logical/entities/$entityId" : "/tenants/$tenantId/projects/$projectId/logical"}
          params={{ tenantId: String(tenantId), projectId: String(projectId), ...(parentEntityId ? { entityId: String(parentEntityId) } : {}) }}
        >
          ← {parentEntityId ? "Back to Entity" : "Back to Logical"}
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

function humanize(value: string): string {
  return value.replaceAll("_", " ").replace(/^./, (character) => character.toLocaleUpperCase());
}
