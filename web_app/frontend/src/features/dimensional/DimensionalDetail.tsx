import { SourceMappings } from "../models/SourceMappings";
import { EntityAttributes } from "../models/EntityAttributes";
import { useEffect, useRef } from "react";
import { useQuery } from "@tanstack/react-query";
import { Link } from "@tanstack/react-router";

import { DetailState } from "../../shared/ui";
import { ApiError } from "../../core/http";
import type {
  DimensionalAttributeDetail,
  DimensionalObjectDetail,
  DimensionalRelationshipDetail,
} from "./api";
import { formatRequiredDateTime as formatDateTime } from "../../shared/presentation";
import { dimensionalQueryKeys, type DimensionalApi } from "./api";

export function DimensionalObjectDetailPage({
  api,
  tenantId,
  modelId,
  modelRevision,
  hasTenantLock,
  entityId,
}: {
  api: DimensionalApi;
  tenantId: number;
  modelId: number;
  modelRevision: number;
  hasTenantLock: boolean;
  entityId: number;
}) {
  const query = useQuery({
    queryKey: dimensionalQueryKeys.object(tenantId, modelId, entityId),
    queryFn: () => api.readDimensionalObject(tenantId, modelId, entityId),
  });
  if (query.isPending) return <DetailState label="Loading Dimensional Object…" />;
  if (query.isError) {
    return <DetailState
      label={query.error instanceof ApiError && query.error.status === 403
        ? "You do not have permission to view this Dimensional Object."
        : "Dimensional Object details could not be loaded."}
      error
    />;
  }
  return <DimensionalObjectView modelRevision={modelRevision} hasTenantLock={hasTenantLock} api={api} tenantId={tenantId} modelId={modelId} object={query.data} />;
}

export function DimensionalAttributeDetailPage({
  api,
  tenantId,
  modelId,
  attributeId,
}: {
  api: DimensionalApi;
  tenantId: number;
  modelId: number;
  attributeId: number;
}) {
  const query = useQuery({
    queryKey: dimensionalQueryKeys.attribute(tenantId, modelId, attributeId),
    queryFn: () => api.readDimensionalAttribute(tenantId, modelId, attributeId),
  });
  if (query.isPending) return <DetailState label="Loading Dimensional Attribute…" />;
  if (query.isError) return <DetailState label={detailErrorLabel(query.error, "Attribute")} error />;
  return <DimensionalAttributeView
    tenantId={tenantId}
    modelId={modelId}
    attribute={query.data}
  />;
}

export function DimensionalRelationshipDetailPage({
  api,
  tenantId,
  modelId,
  relationshipId,
}: {
  api: DimensionalApi;
  tenantId: number;
  modelId: number;
  relationshipId: number;
}) {
  const query = useQuery({
    queryKey: dimensionalQueryKeys.relationship(tenantId, modelId, relationshipId),
    queryFn: () => api.readDimensionalRelationship(tenantId, modelId, relationshipId),
  });
  if (query.isPending) return <DetailState label="Loading Dimensional Relationship…" />;
  if (query.isError) return <DetailState label={detailErrorLabel(query.error, "Relationship")} error />;
  return <DimensionalRelationshipView
    tenantId={tenantId}
    modelId={modelId}
    relationship={query.data}
  />;
}

function DimensionalObjectView({
  api,
  tenantId,
  modelId,
  modelRevision,
  hasTenantLock,
  object,
}: {
  tenantId: number;
  modelId: number;
  modelRevision: number;
  hasTenantLock: boolean;
  object: DimensionalObjectDetail;
  api: DimensionalApi;
}) {
  const heading = useRef<HTMLHeadingElement>(null);
  useEffect(() => heading.current?.focus(), []);
  return (
    <article className="workflow-detail-page dimensional-detail-page page-enter">
      <header className="workflow-detail-header">
        <div>
          <Link
            className="text-action"
            aria-label="Back to Dimensional"
            to="/tenants/$tenantId/models/$modelId/dimensional"
            params={{ tenantId: String(tenantId), modelId: String(modelId) }}
          >
            ← Back to Dimensional
          </Link>
          <p className="eyebrow">Dimensional Object {object.dimensional_entity_id}</p>
          <h1 ref={heading} tabIndex={-1}>{object.dimensional_entity_name}</h1>
        </div>
        <div className="detail-badge-stack">
          <span className={`status-badge ${statusTone(object.dimensional_entity_status)}`}>
            {humanize(object.dimensional_entity_status)}
          </span>
          <span className="status-badge is-neutral">
            {object.dimensional_entity_is_locked ? "Locked" : "Open"}
          </span>
        </div>
      </header>
      <section className="detail-section detail-primary" aria-labelledby="dimensional-object-overview">
        <header><h2 id="dimensional-object-overview">Object definition</h2></header>
        <p className="detail-prose is-prominent">{object.dimensional_entity_definition}</p>
        <dl className="detail-fact-grid">
          <Fact label="Type" value={humanize(object.dimensional_entity_type)} />
          {object.dimensional_fact_type !== null ? <Fact label="Fact type" value={humanize(object.dimensional_fact_type)} /> : null}
          <Fact label="Grain" value={object.dimensional_entity_grain_definition ?? "Not specified"} />
          <Fact label="Dependency order" value={String(object.dimensional_entity_dependency_order)} />
          <Fact label="Confidence" value={humanize(object.dimensional_entity_confidence)} />
          <Fact label="Updated" value={formatDateTime(object.updated_at)} />
        </dl>
      </section>
      <EntityAttributes modelRevision={modelRevision} hasTenantLock={hasTenantLock} api={api} layer="dimensional" tenantId={tenantId} modelId={modelId} entityId={object.dimensional_entity_id} />
      <SourceMappings sources={object.sources} />
      <details className="detail-section detail-disclosure" aria-labelledby="dimensional-submodel-membership">
        <summary>
          <h2 id="dimensional-submodel-membership">Submodel membership</h2>
          <span>{object.submodels.length} records</span>
        </summary>
        {object.submodels.length === 0 ? (
          <p className="detail-empty">No Submodel membership is recorded.</p>
        ) : (
          <div className="table-scroll">
            <table aria-label="Submodel memberships">
              <thead><tr><th>Submodel</th><th>ID</th><th>Status</th><th>Lock</th><th>Workflow</th></tr></thead>
              <tbody>{object.submodels.map((membership) => (
                <tr key={membership.dimensional_entity_submodel_id}>
                  <td>{membership.dimensional_submodel_name}</td>
                  <td>{membership.dimensional_submodel_id}</td>
                  <td>{humanize(membership.membership_status)}</td>
                  <td>{membership.membership_is_locked ? "Locked" : "Open"}</td>
                  <td>{membership.workflow_run_id === null ? "No workflow provenance" : `Workflow run ${membership.workflow_run_id}`}</td>
                </tr>
              ))}</tbody>
            </table>
          </div>
        )}
      </details>
      <details className="detail-section detail-disclosure" aria-labelledby="dimensional-record-provenance">
        <summary><h2 id="dimensional-record-provenance">Provenance</h2></summary>
        <dl className="detail-fact-grid">
          <Fact label="Workflow" value={object.workflow_run_id === null ? "No workflow provenance" : `Workflow run ${object.workflow_run_id}`} />
          <Fact label="Created" value={formatDateTime(object.created_at)} />
        </dl>
      </details>
    </article>
  );
}


function DimensionalAttributeView({
  tenantId,
  modelId,
  attribute,
}: {
  tenantId: number;
  modelId: number;
  attribute: DimensionalAttributeDetail;
}) {
  return (
    <article className="workflow-detail-page dimensional-detail-page page-enter">
      <DimensionalDetailHeader
        tenantId={tenantId}
        modelId={modelId}
        eyebrow={`Dimensional Attribute ${attribute.dimensional_attribute_id}`}
        title={attribute.dimensional_attribute_name}
        status={attribute.dimensional_attribute_status}
        locked={attribute.dimensional_attribute_is_locked}
      />
      <section className="detail-section detail-primary" aria-labelledby="dimensional-attribute-overview">
        <header><h2 id="dimensional-attribute-overview">Attribute definition</h2></header>
        <p className="detail-prose is-prominent">{attribute.dimensional_attribute_definition}</p>
        <dl className="detail-fact-grid">
          <Fact label="Object" value={attribute.dimensional_entity_name} />
          <Fact label="Confidence" value={humanize(attribute.dimensional_attribute_confidence)} />
        </dl>
        <h3>Type and role</h3>
        <dl className="detail-fact-grid">
          <Fact label="Data type" value={attribute.dimensional_attribute_data_type} />
          <Fact label="Ordinal" value={String(attribute.dimensional_attribute_ordinal_position)} />
          <Fact label="Role" value={humanize(attribute.dimensional_attribute_role)} />
          <Fact label="Nullable" value={attribute.dimensional_attribute_is_nullable ? "Yes" : "No"} />
          <Fact label="Audit column" value={attribute.dimensional_attribute_is_audit_column ? "Yes" : "No"} />
        </dl>
        <h3>Keys and grain</h3>
        <dl className="detail-fact-grid">
          <Fact label="Key role" value={humanize(attribute.dimensional_attribute_key_role)} />
          <Fact label="Grain component" value={attribute.dimensional_attribute_is_grain_component ? "Yes" : "No"} />
        </dl>
        {attribute.dimensional_attribute_role === "measure"
          || attribute.dimensional_attribute_additivity !== null
          || attribute.dimensional_attribute_default_aggregation !== null
          || attribute.dimensional_attribute_aggregation_basis !== null ? (
          <>
            <h3>Aggregation</h3>
            <dl className="detail-fact-grid">
              <Fact label="Additivity" value={attribute.dimensional_attribute_additivity === null ? "Not recorded" : humanize(attribute.dimensional_attribute_additivity)} />
              <Fact label="Default aggregation" value={attribute.dimensional_attribute_default_aggregation ?? "Not recorded"} />
            </dl>
            <dl className="conceptual-reasoning">
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
      <DimensionalProvenance workflowRunId={attribute.workflow_run_id} createdAt={attribute.created_at} />
    </article>
  );
}


function DimensionalRelationshipView({
  tenantId,
  modelId,
  relationship,
}: {
  tenantId: number;
  modelId: number;
  relationship: DimensionalRelationshipDetail;
}) {
  return (
    <article className="workflow-detail-page dimensional-detail-page page-enter">
      <DimensionalDetailHeader
        tenantId={tenantId}
        modelId={modelId}
        eyebrow={`Dimensional Relationship ${relationship.dimensional_relationship_id}`}
        title={relationship.dimensional_relationship_name}
        status={relationship.dimensional_relationship_status}
        locked={relationship.dimensional_relationship_is_locked}
      />
      <section className="detail-section detail-primary" aria-labelledby="dimensional-relationship-overview">
        <header><h2 id="dimensional-relationship-overview">Relationship definition</h2></header>
        <p className="detail-prose is-prominent">{relationship.dimensional_relationship_definition}</p>
        <div className="conceptual-endpoints" aria-label="Relationship endpoints">
          <section>
            <small>From</small>
            <strong>{relationship.from_dimensional_entity_name}.{relationship.from_dimensional_attribute_name}</strong>
          </section>
          <span aria-hidden="true">→</span>
          <section>
            <small>To</small>
            <strong>{relationship.to_dimensional_entity_name}.{relationship.to_dimensional_attribute_name}</strong>
          </section>
        </div>
        <dl className="detail-fact-grid">
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
        <dl className="conceptual-reasoning">
          <Fact label="Relationship basis" value={relationship.dimensional_relationship_basis} />
          <Fact label="Cardinality basis" value={relationship.dimensional_relationship_cardinality_basis} />
        </dl>
      </section>
      <DimensionalProvenance workflowRunId={relationship.workflow_run_id} createdAt={relationship.created_at} />
    </article>
  );
}

function DimensionalDetailHeader({
  tenantId,
  modelId,
  eyebrow,
  title,
  status,
  locked,
}: {
  tenantId: number;
  modelId: number;
  eyebrow: string;
  title: string;
  status: string;
  locked: boolean;
}) {
  const heading = useRef<HTMLHeadingElement>(null);
  useEffect(() => heading.current?.focus(), []);
  return (
    <header className="workflow-detail-header">
      <div>
        <Link
          className="text-action"
          aria-label="Back to Dimensional"
          to="/tenants/$tenantId/models/$modelId/dimensional"
          params={{ tenantId: String(tenantId), modelId: String(modelId) }}
        >
          ← Back to Dimensional
        </Link>
        <p className="eyebrow">{eyebrow}</p>
        <h1 ref={heading} tabIndex={-1}>{title}</h1>
      </div>
      <div className="detail-badge-stack">
        <span className={`status-badge ${statusTone(status)}`}>{humanize(status)}</span>
        <span className="status-badge is-neutral">{locked ? "Locked" : "Open"}</span>
      </div>
    </header>
  );
}

function DimensionalProvenance({
  workflowRunId,
  createdAt,
}: {
  workflowRunId: number | null;
  createdAt: string;
}) {
  return (
    <details className="detail-section detail-disclosure" aria-labelledby="dimensional-record-provenance">
      <summary><h2 id="dimensional-record-provenance">Provenance</h2></summary>
      <dl className="detail-fact-grid">
        <Fact label="Workflow" value={workflowRunId === null ? "No workflow provenance" : `Workflow run ${workflowRunId}`} />
        <Fact label="Created" value={formatDateTime(createdAt)} />
      </dl>
    </details>
  );
}

function detailErrorLabel(error: Error, artifact: "Attribute" | "Relationship"): string {
  return error instanceof ApiError && error.status === 403
    ? `You do not have permission to view this Dimensional ${artifact}.`
    : `Dimensional ${artifact} details could not be loaded.`;
}

function Fact({ label, value }: { label: string; value: string }) {
  return <div><dt>{label}</dt><dd>{value}</dd></div>;
}

function humanize(value: string): string {
  return value.replaceAll("_", " ").replace(/^./, (character) => character.toLocaleUpperCase());
}

function statusTone(status: string): string {
  if (status === "active") return "is-success";
  return "is-neutral";
}
