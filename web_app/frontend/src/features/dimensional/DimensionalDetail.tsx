import { SourceMappings } from "../projects/SourceMappings";
import { EntityAttributes } from "../projects/EntityAttributes";
import { useEffect, useRef, type ReactNode } from "react";
import { useQuery } from "@tanstack/react-query";
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
            <span className={`status-badge ${statusTone(object.dimensional_entity_status)}`}>
              {humanize(object.dimensional_entity_status)}
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
          <Fact label="Confidence" value={humanize(object.dimensional_entity_confidence)} />
          <Fact label="Updated" value={formatDateTime(object.updated_at)} />
        </dl>
      </section>
      <EntityAttributes projectRevision={projectRevision} hasTenantLock={hasTenantLock} api={api} layer="dimensional" tenantId={tenantId} projectId={projectId} entityId={object.dimensional_entity_id} />
      <SourceMappings sources={object.sources} />
      <details className="detail-section detail-disclosure" aria-labelledby="dimensional-submodel-membership">
        <summary>
          <h2 id="dimensional-submodel-membership">Submodel membership</h2>
          <span>{object.submodels.length} records</span>
        </summary>
        {object.submodels.length === 0 ? (
          <p className="detail-empty">No Submodel membership is recorded.</p>
        ) : (
          <div className="table-scroll" role="region" aria-label="Scrollable Submodel memberships" tabIndex={0}>
            <table aria-label="Submodel memberships">
              <thead><tr><th>Submodel</th><th>ID</th><th>Status</th><th>Lock</th></tr></thead>
              <tbody>{object.submodels.map((membership) => (
                <tr key={membership.dimensional_entity_submodel_id}>
                  <td>{membership.dimensional_submodel_name}</td>
                  <td>{membership.dimensional_submodel_id}</td>
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
        status={attribute.dimensional_attribute_status}
        locked={attribute.dimensional_attribute_is_locked}
      />
      <section className="detail-section detail-primary" aria-labelledby="dimensional-attribute-overview">
        <header><h2 id="dimensional-attribute-overview">Attribute definition</h2></header>
        <dl className="modeled-detail-fields">
          <div className="is-definition"><dt>Definition</dt><dd>{attribute.dimensional_attribute_definition}</dd></div>
          <Fact label="Entity" value={`${attribute.dimensional_entity_schema_name}.${attribute.dimensional_entity_name}`} />
          <Fact label="Confidence" value={humanize(attribute.dimensional_attribute_confidence)} />
        </dl>
        <h3>Type and role</h3>
        <dl className="modeled-detail-fields">
          <Fact label="Data type" value={attribute.dimensional_attribute_data_type} />
          <Fact label="Ordinal" value={String(attribute.dimensional_attribute_ordinal_position)} />
          <Fact label="Role" value={humanize(attribute.dimensional_attribute_role)} />
          <Fact label="Nullable" value={attribute.dimensional_attribute_is_nullable ? "Yes" : "No"} />
          <Fact label="Audit column" value={attribute.dimensional_attribute_is_audit_column ? "Yes" : "No"} />
        </dl>
        <h3>Keys and grain</h3>
        <dl className="modeled-detail-fields">
          <Fact label="Surrogate key" value={attribute.dimensional_attribute_key_role === "surrogate" ? "Yes" : "No"} />
          <Fact label="Natural key" value={attribute.dimensional_attribute_key_role === "business" ? "Yes" : "No"} />
          {attribute.dimensional_attribute_key_role === "foreign" ? <Fact label="Foreign key" value="Yes" /> : null}
          <Fact label="Grain component" value={attribute.dimensional_attribute_is_grain_component ? "Yes" : "No"} />
        </dl>
        {attribute.dimensional_attribute_role === "measure"
          || attribute.dimensional_attribute_additivity !== null
          || attribute.dimensional_attribute_default_aggregation !== null
          || attribute.dimensional_attribute_aggregation_basis !== null ? (
          <>
            <h3>Aggregation</h3>
            <dl className="modeled-detail-fields">
              <Fact label="Additivity" value={attribute.dimensional_attribute_additivity === null ? "Not recorded" : humanize(attribute.dimensional_attribute_additivity)} />
              <Fact label="Default aggregation" value={attribute.dimensional_attribute_default_aggregation ?? "Not recorded"} />
              <Fact label="Aggregation basis" value={attribute.dimensional_attribute_aggregation_basis ?? "Not recorded"} />
            </dl>
          </>
        ) : <p className="detail-empty-note">No aggregation behavior is recorded.</p>}
        {attribute.dimensional_attribute_change_behavior !== null ? (
          <>
            <h3>Change behavior</h3>
            <p className="detail-prose">{humanize(attribute.dimensional_attribute_change_behavior)}</p>
          </>
        ) : <p className="detail-empty-note">No change behavior is recorded.</p>}
      </section>
      <SourceMappings sources={attribute.sources} />
    </article>
  );
}

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
  return (
    <article className="workflow-detail-page dimensional-detail-page modeled-detail-page page-enter">
      <DimensionalDetailHeader
        actions={actions}
        tenantId={tenantId}
        projectId={projectId}
        title={relationship.dimensional_relationship_name}
        status={relationship.dimensional_relationship_status}
        locked={relationship.dimensional_relationship_is_locked}
      />
      <section className="detail-section detail-primary" aria-labelledby="dimensional-relationship-overview">
        <header><h2 id="dimensional-relationship-overview">Relationship definition</h2></header>
        <dl className="modeled-detail-fields">
          <div className="is-definition"><dt>Definition</dt><dd>{relationship.dimensional_relationship_definition}</dd></div>
          <Fact label="From" value={`${relationship.from_dimensional_entity_schema_name}.${relationship.from_dimensional_entity_name}.${relationship.from_dimensional_attribute_name}`} />
          <Fact label="To" value={`${relationship.to_dimensional_entity_schema_name}.${relationship.to_dimensional_entity_name}.${relationship.to_dimensional_attribute_name}`} />
          <Fact label="Kind" value={humanize(relationship.dimensional_relationship_kind)} />
          <Fact label="Cardinality" value={humanize(relationship.dimensional_relationship_cardinality)} />
          <Fact label="Optional" value={relationship.dimensional_relationship_is_optional ? "Yes" : "No"} />
          <Fact label="Role" value={relationship.dimensional_relationship_role_name ?? "Not specified"} />
          <Fact label="Confidence" value={humanize(relationship.dimensional_relationship_confidence)} />
          <Fact label="Updated" value={formatDateTime(relationship.updated_at)} />
        </dl>
      </section>
      <section className="detail-section" aria-labelledby="dimensional-relationship-reasoning">
        <header><h2 id="dimensional-relationship-reasoning">Reasoning</h2></header>
        <dl className="modeled-detail-fields">
          <Fact label="Relationship basis" value={relationship.dimensional_relationship_basis} />
          <Fact label="Cardinality basis" value={relationship.dimensional_relationship_cardinality_basis} />
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
  status,
  locked,
}: {
  actions?: ReactNode;
  tenantId: number;
  projectId: number;
  parentEntityId?: number;
  title: string;
  status: string;
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
          <span className={`status-badge ${statusTone(status)}`}>{humanize(status)}</span>
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

function statusTone(status: string): string {
  if (status === "active") return "is-success";
  return "is-neutral";
}
