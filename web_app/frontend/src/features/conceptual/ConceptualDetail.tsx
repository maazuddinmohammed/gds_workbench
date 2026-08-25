import { useEffect, useRef } from "react";
import { Link } from "@tanstack/react-router";
import { useQuery } from "@tanstack/react-query";

import { ApiError } from "../../core/http";
import type {
  ConceptualObjectDetail,
  ConceptualRelationshipDetail,
  ConceptualSupport,
} from "./api";
import { formatRequiredDateTime as formatDateTime } from "../../shared/presentation";
import { conceptualQueryKeys, type ConceptualApi } from "./api";

export function ConceptualObjectDetailPage({
  api,
  tenantId,
  modelId,
  objectId,
}: {
  api: ConceptualApi;
  tenantId: number;
  modelId: number;
  objectId: number;
}) {
  const query = useQuery({
    queryKey: conceptualQueryKeys.object(tenantId, modelId, objectId),
    queryFn: () => api.readConceptualObject(tenantId, modelId, objectId),
  });
  if (query.isPending) return <DetailState label="Loading Conceptual Object…" />;
  if (query.isError) {
    return <DetailState label={detailErrorLabel(query.error, "Object")} error />;
  }
  return <ConceptualObjectView tenantId={tenantId} modelId={modelId} object={query.data} />;
}

export function ConceptualRelationshipDetailPage({
  api,
  tenantId,
  modelId,
  relationshipId,
}: {
  api: ConceptualApi;
  tenantId: number;
  modelId: number;
  relationshipId: number;
}) {
  const query = useQuery({
    queryKey: conceptualQueryKeys.relationship(tenantId, modelId, relationshipId),
    queryFn: () => api.readConceptualRelationship(tenantId, modelId, relationshipId),
  });
  if (query.isPending) return <DetailState label="Loading Conceptual Relationship…" />;
  if (query.isError) {
    return <DetailState label={detailErrorLabel(query.error, "Relationship")} error />;
  }
  return (
    <ConceptualRelationshipView
      tenantId={tenantId}
      modelId={modelId}
      relationship={query.data}
    />
  );
}

function ConceptualObjectView({
  tenantId,
  modelId,
  object,
}: {
  tenantId: number;
  modelId: number;
  object: ConceptualObjectDetail;
}) {
  return (
    <article className="workflow-detail-page conceptual-detail-page page-enter">
      <DetailHeader
        tenantId={tenantId}
        modelId={modelId}
        eyebrow={`Conceptual Object ${object.conceptual_object_id}`}
        title={object.conceptual_object_name}
        status={object.conceptual_object_status}
        locked={object.conceptual_object_is_locked}
      />
      <section className="detail-section" aria-labelledby="conceptual-object-overview">
        <header><h2 id="conceptual-object-overview">Object definition</h2></header>
        <p className="detail-prose is-prominent">{object.conceptual_object_definition}</p>
        <dl className="detail-fact-grid">
          <Fact label="Type" value={humanize(object.conceptual_object_type)} />
          <Fact label="Grain" value={object.conceptual_object_grain} />
          <Fact label="Confidence" value={humanize(object.conceptual_object_confidence)} />
          <Fact label="Updated" value={formatDateTime(object.updated_at)} />
        </dl>
        {object.conceptual_object_aliases.length ? (
          <div className="detail-tag-group" aria-label="Object aliases">
            <small>Aliases</small>
            <div className="chip-list">
              {object.conceptual_object_aliases.map((alias) => <span key={alias}>{alias}</span>)}
            </div>
          </div>
        ) : null}
      </section>
      <SupportEvidence supports={object.supports} />
      <Provenance workflowRunId={object.workflow_run_id} createdAt={object.created_at} />
    </article>
  );
}

function ConceptualRelationshipView({
  tenantId,
  modelId,
  relationship,
}: {
  tenantId: number;
  modelId: number;
  relationship: ConceptualRelationshipDetail;
}) {
  return (
    <article className="workflow-detail-page conceptual-detail-page page-enter">
      <DetailHeader
        tenantId={tenantId}
        modelId={modelId}
        eyebrow={`Conceptual Relationship ${relationship.conceptual_relationship_id}`}
        title={relationship.conceptual_relationship_name}
        status={relationship.conceptual_relationship_status}
        locked={relationship.conceptual_relationship_is_locked}
      />
      <section className="detail-section" aria-labelledby="conceptual-relationship-overview">
        <header><h2 id="conceptual-relationship-overview">Relationship definition</h2></header>
        <p className="detail-prose is-prominent">
          {relationship.conceptual_relationship_definition}
        </p>
        <div className="conceptual-endpoints" aria-label="Relationship endpoints">
          <section>
            <small>From</small>
            <strong>{humanize(relationship.from_conceptual_object_name)}</strong>
          </section>
          <span aria-hidden="true">→</span>
          <section>
            <small>To</small>
            <strong>{humanize(relationship.to_conceptual_object_name)}</strong>
          </section>
        </div>
        <dl className="detail-fact-grid">
          <Fact label="Type" value={humanize(relationship.conceptual_relationship_type)} />
          <Fact label="Cardinality" value={humanize(relationship.conceptual_relationship_cardinality)} />
          <Fact label="Confidence" value={humanize(relationship.conceptual_relationship_confidence)} />
          <Fact label="Updated" value={formatDateTime(relationship.updated_at)} />
        </dl>
      </section>
      <section className="detail-section" aria-labelledby="relationship-reasoning-heading">
        <header><h2 id="relationship-reasoning-heading">Reasoning</h2></header>
        <dl className="conceptual-reasoning">
          <Fact label="Relationship basis" value={relationship.conceptual_relationship_basis} />
          <Fact
            label="Cardinality basis"
            value={relationship.conceptual_relationship_cardinality_basis}
          />
        </dl>
      </section>
      <SupportEvidence supports={relationship.supports} />
      <Provenance workflowRunId={relationship.workflow_run_id} createdAt={relationship.created_at} />
    </article>
  );
}

function DetailHeader({
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
          aria-label="Back to Conceptual"
          to="/tenants/$tenantId/models/$modelId/conceptual"
          params={{ tenantId: String(tenantId), modelId: String(modelId) }}
        >
          ← Back to Conceptual
        </Link>
        <p className="eyebrow">{eyebrow}</p>
        <h1 ref={heading} tabIndex={-1}>{title}</h1>
      </div>
      <div className="detail-badge-stack">
        <span className={`status-badge ${status === "active" ? "is-success" : "is-warning"}`}>
          {humanize(status)}
        </span>
        <span className={`status-badge ${locked ? "is-neutral" : "is-success"}`}>
          {locked ? "Locked" : "Open"}
        </span>
      </div>
    </header>
  );
}

function SupportEvidence({ supports }: { supports: ConceptualSupport[] }) {
  return (
    <section className="detail-section" aria-labelledby="conceptual-support-heading">
      <header>
        <h2 id="conceptual-support-heading">Support evidence</h2>
        <span>{supports.length} records</span>
      </header>
      {supports.length === 0 ? (
        <p className="detail-empty">No support evidence is recorded.</p>
      ) : (
        <div className="support-ledger">
          {supports.map((support, index) => (
            <article
              key={support.conceptual_support_id}
              className="support-record"
              aria-label={`Support ${support.conceptual_support_id}`}
            >
              <header>
                <span className="support-index">{String(index + 1).padStart(2, "0")}</span>
                <div>
                  <small>{support.support_source_type === "object" ? "Physical Object" : "Modeling Assertion"}</small>
                  <strong>
                    {support.support_source_type === "object"
                      ? `${support.source_object.object_schema}.${support.source_object.object_name}`
                      : support.assertion_record.modeling_assertion_record_key}
                  </strong>
                </div>
                <span className={`status-badge confidence-${support.support_confidence}`}>
                  {humanize(support.support_confidence)}
                </span>
              </header>
              <p>{support.support_reason}</p>
              {support.support_reason_detail ? <p>{support.support_reason_detail}</p> : null}
              <dl className="support-facts">
                <Fact label="Role" value={support.support_role ?? "Not assigned"} />
                <Fact label="Status" value={humanize(support.support_status)} />
                <Fact label="Lock" value={support.support_is_locked ? "Locked" : "Open"} />
                <Fact
                  label="Workflow"
                  value={support.workflow_run_id === null
                    ? "No workflow provenance"
                    : `Workflow run ${support.workflow_run_id}`}
                />
                <Fact label="Created" value={formatDateTime(support.created_at)} />
                <Fact label="Updated" value={formatDateTime(support.updated_at)} />
                {support.support_source_type === "object" ? (
                  <>
                    <Fact label="Source Object ID" value={`Object ${support.source_object.object_id}`} />
                    <Fact
                      label="Source"
                      value={`${support.source_object.tenant_code} · ${support.source_object.system_code} · ${support.source_object.connection_code}`}
                    />
                    <Fact
                      label="Object"
                      value={`${support.source_object.object_schema}.${support.source_object.object_name}`}
                    />
                  </>
                ) : (
                  <>
                    <Fact
                      label="Assertion ID"
                      value={`Assertion ${support.assertion_record.modeling_assertion_record_id}`}
                    />
                    <Fact label="Document" value={support.assertion_record.modeling_assertion_document_name} />
                    <Fact label="Type" value={humanize(support.assertion_record.modeling_assertion_record_type)} />
                    <Fact
                      label="Assertion confidence"
                      value={support.assertion_record.modeling_assertion_confidence
                        ? humanize(support.assertion_record.modeling_assertion_confidence)
                        : "Not recorded"}
                    />
                    <Fact
                      label="Assertion status"
                      value={humanize(support.assertion_record.modeling_assertion_record_status)}
                    />
                  </>
                )}
              </dl>
              {support.support_source_type === "assertion" ? (
                <div className="assertion-support-detail">
                  <p>{support.assertion_record.modeling_assertion_text}</p>
                </div>
              ) : null}
            </article>
          ))}
        </div>
      )}
    </section>
  );
}

function Provenance({
  workflowRunId,
  createdAt,
}: {
  workflowRunId: number | null;
  createdAt: string;
}) {
  return (
    <section className="detail-section" aria-labelledby="conceptual-provenance-heading">
      <header><h2 id="conceptual-provenance-heading">Provenance</h2></header>
      <dl className="detail-fact-grid">
        <Fact
          label="Workflow"
          value={workflowRunId === null ? "No workflow provenance" : `Workflow run ${workflowRunId}`}
        />
        <Fact label="Created" value={formatDateTime(createdAt)} />
      </dl>
    </section>
  );
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

function detailErrorLabel(error: Error, kind: "Object" | "Relationship"): string {
  return error instanceof ApiError && error.status === 403
    ? `You do not have permission to view this Conceptual ${kind}.`
    : `Conceptual ${kind} details could not be loaded.`;
}

function Fact({ label, value }: { label: string; value: string }) {
  return <div><dt>{label}</dt><dd>{value}</dd></div>;
}

function humanize(value: string): string {
  return value.replaceAll("_", " ").replace(/^./, (character) => character.toLocaleUpperCase());
}
