import { SourceMappings } from "../projects/SourceMappings";
import { EntityAttributes } from "../projects/EntityAttributes";
import { useEffect, useRef, type ReactNode } from "react";
import { useQuery } from "@tanstack/react-query";
import { Link } from "@tanstack/react-router";

import { DetailState, Fact } from "../../shared/ui";
import type {
  LogicalAttributeDetail,
  LogicalEntityDetail,
  LogicalRelationshipDetail,
  LogicalSubmodelDetail,
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

export function LogicalSubmodelDetailPage({
  actions,
  api,
  tenantId,
  projectId,
  submodelId,
}: {
  actions?: ReactNode;
  api: LogicalApi;
  tenantId: number;
  projectId: number;
  submodelId: number;
}) {
  const query = useQuery({
    queryKey: logicalQueryKeys.submodel(tenantId, projectId, submodelId),
    queryFn: () => api.readLogicalSubmodel(tenantId, projectId, submodelId),
  });
  if (query.isPending) return <DetailState label="Loading Logical Submodel…" />;
  if (query.isError) return <DetailState label="Logical Submodel details could not be loaded." error />;
  return <LogicalSubmodelView actions={actions} tenantId={tenantId} projectId={projectId} submodel={query.data} />;
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
        status={entity.logical_entity_status}
        locked={entity.logical_entity_is_locked}
      />

      <section className="detail-section detail-primary" aria-labelledby="logical-entity-overview">
        <header><h2 id="logical-entity-overview">Entity definition</h2></header>
        <dl className="modeled-detail-fields">
          <div className="is-definition"><dt>Definition</dt><dd>{entity.logical_entity_definition}</dd></div>
          <Fact label="Grain" value={entity.logical_entity_grain} />
          <Fact label="Type" value={humanize(entity.logical_entity_type)} />
          <Fact label="Type detail" value={entity.logical_entity_type_detail ?? "Not specified"} />
          <Fact label="Dependency order" value={String(entity.logical_entity_dependency_order)} />
          <Fact label="Updated" value={formatDateTime(entity.updated_at)} />
        </dl>
      </section>

      <EntityAttributes projectRevision={projectRevision} hasTenantLock={hasTenantLock} api={api} layer="logical" tenantId={tenantId} projectId={projectId} entityId={entity.logical_entity_id} />
      <SourceMappings sources={entity.sources} />

      <details className="detail-section detail-disclosure" aria-labelledby="logical-submodel-membership">
        <summary>
          <h2 id="logical-submodel-membership">Submodel membership</h2>
          <span>{entity.submodels.length} records</span>
        </summary>
        {entity.submodels.length === 0 ? (
          <p className="detail-empty">No Submodel membership is recorded.</p>
        ) : (
          <div className="table-scroll" role="region" aria-label="Scrollable Submodel memberships" tabIndex={0}>
            <table aria-label="Submodel memberships">
              <thead><tr><th>Submodel</th><th>Status</th><th>Lock</th></tr></thead>
              <tbody>{entity.submodels.map((membership) => (
                <tr key={membership.logical_entity_submodel_id}>
                  <td><Link className="text-action" to="/tenants/$tenantId/projects/$projectId/logical/submodels/$submodelId"
                    params={{ tenantId: String(tenantId), projectId: String(projectId), submodelId: String(membership.logical_submodel_id) }}>
                    {membership.logical_submodel_name}
                  </Link></td>
                  <td>{humanize(membership.membership_status)}</td>
                  <td>{membership.membership_is_locked ? "Locked" : "Open"}</td>
                </tr>
              ))}</tbody>
            </table>
          </div>
        )}
      </details>

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
        status={attribute.logical_attribute_status}
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
  return (
    <article className="workflow-detail-page logical-detail-page modeled-detail-page page-enter">
      <LogicalDetailHeader
        actions={actions}
        tenantId={tenantId}
        projectId={projectId}
        recordId={relationship.logical_relationship_id}
        title={relationship.logical_relationship_name}
        status={relationship.logical_relationship_status}
        locked={relationship.logical_relationship_is_locked}
      />
      <section className="detail-section detail-primary" aria-labelledby="logical-relationship-overview">
        <header><h2 id="logical-relationship-overview">Relationship definition</h2></header>
        <dl className="modeled-detail-fields">
          <div className="is-definition"><dt>Definition</dt><dd>{relationship.logical_relationship_definition}</dd></div>
          <Fact label="From Attribute" value={`${relationship.from_logical_entity_schema_name}.${relationship.from_logical_entity_name}.${relationship.from_logical_attribute_name}`} />
          <Fact label="To Attribute" value={`${relationship.to_logical_entity_schema_name}.${relationship.to_logical_entity_name}.${relationship.to_logical_attribute_name}`} />
          <Fact label="Cardinality" value={humanize(relationship.logical_relationship_cardinality)} />
          <Fact label="Updated" value={formatDateTime(relationship.updated_at)} />
        </dl>
      </section>
      <section className="detail-section" aria-labelledby="logical-relationship-reasoning">
        <header><h2 id="logical-relationship-reasoning">Reasoning</h2></header>
        <dl className="modeled-detail-fields">
          <Fact label="Relationship basis" value={relationship.logical_relationship_basis} />
          <Fact label="Cardinality basis" value={relationship.logical_relationship_cardinality_basis} />
        </dl>
      </section>
    </article>
  );
}

function LogicalSubmodelView({
  actions,
  tenantId,
  projectId,
  submodel,
}: {
  actions?: ReactNode;
  tenantId: number;
  projectId: number;
  submodel: LogicalSubmodelDetail;
}) {
  return (
    <article className="workflow-detail-page logical-detail-page modeled-detail-page page-enter">
      <LogicalDetailHeader
        actions={actions}
        tenantId={tenantId}
        projectId={projectId}
        recordId={submodel.logical_submodel_id}
        title={submodel.logical_submodel_name}
        status={submodel.logical_submodel_status}
        locked={submodel.logical_submodel_is_locked}
      />
      <section className="detail-section detail-primary" aria-labelledby="logical-submodel-overview">
        <header><h2 id="logical-submodel-overview">Submodel definition</h2></header>
        <dl className="modeled-detail-fields">
          <div className="is-definition"><dt>Definition</dt><dd>{submodel.logical_submodel_definition}</dd></div>
          <Fact label="Entities" value={String(submodel.entity_count)} />
          <Fact label="Updated" value={formatDateTime(submodel.updated_at)} />
        </dl>
      </section>
      <section className="detail-section" aria-labelledby="logical-submodel-entities">
        <header>
          <h2 id="logical-submodel-entities">Member entities</h2>
          <span>{submodel.entities.length} records</span>
        </header>
        {submodel.entities.length === 0 ? (
          <p className="detail-empty">No member entities are recorded.</p>
        ) : (
          <div className="table-scroll" role="region" aria-label="Scrollable Member entities" tabIndex={0}>
            <table aria-label="Member entities">
              <thead><tr><th>Entity</th><th>Type</th><th>Entity status</th><th>Membership status</th><th>Entity ID</th></tr></thead>
              <tbody>{submodel.entities.map((membership) => (
                <tr key={membership.logical_entity_submodel_id}>
                  <td><Link className="text-action" to="/tenants/$tenantId/projects/$projectId/logical/entities/$entityId"
                    params={{ tenantId: String(tenantId), projectId: String(projectId), entityId: String(membership.logical_entity_id) }}>
                    {membership.logical_entity_schema_name}.{membership.logical_entity_name}
                  </Link></td>
                  <td>{humanize(membership.logical_entity_type)}</td>
                  <td>{humanize(membership.logical_entity_status)}</td>
                  <td>{humanize(membership.membership_status)}</td>
                  <td>{membership.logical_entity_id}</td>
                </tr>
              ))}</tbody>
            </table>
          </div>
        )}
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
  status,
  locked,
  parentEntityId,
}: {
  actions?: ReactNode;
  tenantId: number;
  projectId: number;
  recordId: number;
  title: string;
  status: string;
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
          <span className={`status-badge ${statusTone(status)}`}>{humanize(status)}</span>
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

function statusTone(status: string): string {
  if (status === "active") return "is-success";
  return "is-neutral";
}
