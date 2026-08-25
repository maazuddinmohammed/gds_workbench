import { useEffect, useRef } from "react";
import { useQuery } from "@tanstack/react-query";
import { Link } from "@tanstack/react-router";

import { ApiError } from "../../core/http";
import type {
  DimensionalAttributeDetail,
  DimensionalAttributeSource,
  DimensionalObjectDetail,
  DimensionalObjectSource,
  DimensionalRelationshipDetail,
} from "./api";
import { formatRequiredDateTime as formatDateTime } from "../../shared/presentation";
import { dimensionalQueryKeys, type DimensionalApi } from "./api";

export function DimensionalObjectDetailPage({
  api,
  tenantId,
  modelId,
  entityId,
}: {
  api: DimensionalApi;
  tenantId: number;
  modelId: number;
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
  return <DimensionalObjectView tenantId={tenantId} modelId={modelId} object={query.data} />;
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
  tenantId,
  modelId,
  object,
}: {
  tenantId: number;
  modelId: number;
  object: DimensionalObjectDetail;
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
      <section className="detail-section" aria-labelledby="dimensional-object-overview">
        <header><h2 id="dimensional-object-overview">Object definition</h2></header>
        <p className="detail-prose is-prominent">{object.dimensional_entity_definition}</p>
        <dl className="detail-fact-grid">
          <Fact label="Type" value={humanize(object.dimensional_entity_type)} />
          <Fact label="Fact type" value={object.dimensional_fact_type ? humanize(object.dimensional_fact_type) : "Not applicable"} />
          <Fact label="Grain" value={object.dimensional_entity_grain_definition ?? "Not specified"} />
          <Fact label="Dependency order" value={String(object.dimensional_entity_dependency_order)} />
          <Fact label="Confidence" value={humanize(object.dimensional_entity_confidence)} />
          <Fact label="Updated" value={formatDateTime(object.updated_at)} />
        </dl>
      </section>
      <section className="detail-section" aria-labelledby="dimensional-submodel-membership">
        <header>
          <h2 id="dimensional-submodel-membership">Submodel membership</h2>
          <span>{object.submodels.length} records</span>
        </header>
        {object.submodels.length === 0 ? (
          <p className="detail-empty">No Submodel membership is recorded.</p>
        ) : (
          <div className="normalized-membership-ledger">
            {object.submodels.map((membership) => (
              <article key={membership.dimensional_entity_submodel_id}>
                <strong>{membership.dimensional_submodel_name}</strong>
                <dl className="support-facts">
                  <Fact label="Submodel ID" value={String(membership.dimensional_submodel_id)} />
                  <Fact label="Status" value={humanize(membership.membership_status)} />
                  <Fact label="Lock" value={membership.membership_is_locked ? "Locked" : "Open"} />
                  <Fact label="Workflow" value={membership.workflow_run_id === null ? "No workflow provenance" : `Workflow run ${membership.workflow_run_id}`} />
                </dl>
              </article>
            ))}
          </div>
        )}
      </section>
      <ObjectSourceMappings sources={object.sources} />
      <section className="detail-section" aria-labelledby="dimensional-record-provenance">
        <header><h2 id="dimensional-record-provenance">Provenance</h2></header>
        <dl className="detail-fact-grid">
          <Fact label="Workflow" value={object.workflow_run_id === null ? "No workflow provenance" : `Workflow run ${object.workflow_run_id}`} />
          <Fact label="Created" value={formatDateTime(object.created_at)} />
        </dl>
      </section>
    </article>
  );
}

function ObjectSourceMappings({ sources }: { sources: DimensionalObjectSource[] }) {
  return (
    <section className="detail-section" aria-labelledby="dimensional-source-mappings">
      <header>
        <h2 id="dimensional-source-mappings">Source mappings</h2>
        <span>{sources.length} records</span>
      </header>
      {sources.length === 0 ? (
        <p className="detail-empty">No source mappings are recorded.</p>
      ) : (
        <div className="support-ledger">
          {sources.map((source, index) => (
            <article key={source.dimensional_entity_source_mapping_id} className="support-record">
              <header>
                <span className="support-index">{String(index + 1).padStart(2, "0")}</span>
                <div>
                  <small>{source.support_source_type === "object" ? "Physical Object" : "Modeling Assertion"}</small>
                  <strong>{source.support_source_type === "object"
                    ? `${source.source_object.object_schema}.${source.source_object.object_name}`
                    : source.assertion_record.modeling_assertion_record_key}</strong>
                </div>
                <span className={`status-badge ${statusTone(source.status)}`}>
                  {humanize(source.status)}
                </span>
              </header>
              <p>{source.rationale}</p>
              <dl className="support-facts">
                <Fact label="Role" value={source.source_role} />
                <Fact label="Order" value={source.source_order === null ? "Not assigned" : String(source.source_order)} />
                {source.support_source_type === "object" ? (
                  <>
                    <Fact label="Source" value={`${source.source_object.tenant_code} · ${source.source_object.system_code} · ${source.source_object.connection_code}`} />
                    <Fact label="Object" value={`${source.source_object.object_schema}.${source.source_object.object_name}`} />
                  </>
                ) : (
                  <>
                    <Fact label="Document" value={source.assertion_record.modeling_assertion_document_name} />
                    <Fact label="Type" value={humanize(source.assertion_record.modeling_assertion_record_type)} />
                  </>
                )}
                <Fact label="Lock" value={source.is_locked ? "Locked" : "Open"} />
              </dl>
              {source.support_source_type === "assertion" ? (
                <p className="assertion-support-detail">{source.assertion_record.modeling_assertion_text}</p>
              ) : null}
            </article>
          ))}
        </div>
      )}
    </section>
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
      <section className="detail-section" aria-labelledby="dimensional-attribute-overview">
        <header><h2 id="dimensional-attribute-overview">Attribute definition</h2></header>
        <p className="detail-prose is-prominent">{attribute.dimensional_attribute_definition}</p>
        <dl className="detail-fact-grid">
          <Fact label="Object" value={attribute.dimensional_entity_name} />
          <Fact label="Data type" value={attribute.dimensional_attribute_data_type} />
          <Fact label="Ordinal" value={String(attribute.dimensional_attribute_ordinal_position)} />
          <Fact label="Role" value={humanize(attribute.dimensional_attribute_role)} />
          <Fact label="Key role" value={humanize(attribute.dimensional_attribute_key_role)} />
          <Fact label="Nullable" value={attribute.dimensional_attribute_is_nullable ? "Yes" : "No"} />
          <Fact label="Grain component" value={attribute.dimensional_attribute_is_grain_component ? "Yes" : "No"} />
          <Fact label="Additivity" value={attribute.dimensional_attribute_additivity ? humanize(attribute.dimensional_attribute_additivity) : "Not applicable"} />
          <Fact label="Default aggregation" value={attribute.dimensional_attribute_default_aggregation ?? "Not specified"} />
          <Fact label="Aggregation basis" value={attribute.dimensional_attribute_aggregation_basis ?? "Not specified"} />
          <Fact label="Change behavior" value={attribute.dimensional_attribute_change_behavior ? humanize(attribute.dimensional_attribute_change_behavior) : "Not applicable"} />
          <Fact label="Audit column" value={attribute.dimensional_attribute_is_audit_column ? "Yes" : "No"} />
        </dl>
      </section>
      <AttributeSourceMappings sources={attribute.sources} />
      <DimensionalProvenance workflowRunId={attribute.workflow_run_id} createdAt={attribute.created_at} />
    </article>
  );
}

function AttributeSourceMappings({ sources }: { sources: DimensionalAttributeSource[] }) {
  return (
    <section className="detail-section" aria-labelledby="dimensional-attribute-sources">
      <header>
        <h2 id="dimensional-attribute-sources">Source mappings</h2>
        <span>{sources.length} records</span>
      </header>
      {sources.length === 0 ? (
        <p className="detail-empty">No source mappings are recorded.</p>
      ) : (
        <div className="support-ledger">
          {sources.map((source, index) => (
            <article key={source.dimensional_attribute_source_mapping_id} className="support-record">
              <header>
                <span className="support-index">{String(index + 1).padStart(2, "0")}</span>
                <div>
                  <small>{source.support_source_type === "attribute" ? "Physical Attribute" : "Modeling Assertion"}</small>
                  <strong>{source.support_source_type === "attribute"
                    ? `${source.source_attribute.object_schema}.${source.source_attribute.object_name}.${source.source_attribute.attribute_name}`
                    : source.assertion_record.modeling_assertion_record_key}</strong>
                </div>
                <span className={`status-badge ${statusTone(source.status)}`}>{humanize(source.status)}</span>
              </header>
              <p>{source.rationale}</p>
              <dl className="support-facts">
                <Fact label="Order" value={source.source_order === null ? "Not assigned" : String(source.source_order)} />
                {source.support_source_type === "attribute" ? (
                  <>
                    <Fact label="Source" value={`${source.source_attribute.tenant_code} · ${source.source_attribute.system_code} · ${source.source_attribute.connection_code}`} />
                    <Fact label="Attribute" value={`${source.source_attribute.object_schema}.${source.source_attribute.object_name}.${source.source_attribute.attribute_name}`} />
                    <Fact label="Object mapping" value={String(source.dimensional_entity_source_mapping_id)} />
                  </>
                ) : (
                  <>
                    <Fact label="Document" value={source.assertion_record.modeling_assertion_document_name} />
                    <Fact label="Type" value={humanize(source.assertion_record.modeling_assertion_record_type)} />
                  </>
                )}
                <Fact label="Lock" value={source.is_locked ? "Locked" : "Open"} />
              </dl>
              {source.support_source_type === "assertion" ? (
                <p className="assertion-support-detail">{source.assertion_record.modeling_assertion_text}</p>
              ) : null}
            </article>
          ))}
        </div>
      )}
    </section>
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
      <section className="detail-section" aria-labelledby="dimensional-relationship-overview">
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
    <section className="detail-section" aria-labelledby="dimensional-record-provenance">
      <header><h2 id="dimensional-record-provenance">Provenance</h2></header>
      <dl className="detail-fact-grid">
        <Fact label="Workflow" value={workflowRunId === null ? "No workflow provenance" : `Workflow run ${workflowRunId}`} />
        <Fact label="Created" value={formatDateTime(createdAt)} />
      </dl>
    </section>
  );
}

function detailErrorLabel(error: Error, artifact: "Attribute" | "Relationship"): string {
  return error instanceof ApiError && error.status === 403
    ? `You do not have permission to view this Dimensional ${artifact}.`
    : `Dimensional ${artifact} details could not be loaded.`;
}

function DetailState({ label, error = false }: { label: string; error?: boolean }) {
  return (
    <div
      className={`surface-state detail-state${error ? " is-error" : ""}`}
      {...(error ? { role: "alert" } : { "aria-busy": true })}
    >
      {label}
    </div>
  );
}

function Fact({ label, value }: { label: string; value: string }) {
  return <div><dt>{label}</dt><dd>{value}</dd></div>;
}

function humanize(value: string): string {
  return value.replaceAll("_", " ").replace(/^./, (character) => character.toLocaleUpperCase());
}

function statusTone(status: string): string {
  if (status === "active") return "is-success";
  if (status === "needs_review") return "is-warning";
  return "is-neutral";
}
