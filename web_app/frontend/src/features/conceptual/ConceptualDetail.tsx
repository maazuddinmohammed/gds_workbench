import { Fragment, useEffect, useRef, useState } from "react";
import { Link } from "@tanstack/react-router";
import { useQuery } from "@tanstack/react-query";

import { DetailState, Fact } from "../../shared/ui";
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
      <section className="detail-section detail-primary" aria-labelledby="conceptual-object-overview">
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
      <section className="detail-section detail-primary" aria-labelledby="conceptual-relationship-overview">
        <header><h2 id="conceptual-relationship-overview">Relationship definition</h2></header>
        <p className="detail-prose is-prominent">
          {relationship.conceptual_relationship_definition}
        </p>
        <div className="conceptual-endpoints" aria-label="Relationship endpoints">
          <section>
            <small>From</small>
            <strong>{relationship.from_conceptual_object_name}</strong>
          </section>
          <span aria-hidden="true">→</span>
          <section>
            <small>To</small>
            <strong>{relationship.to_conceptual_object_name}</strong>
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
        <div className="conceptual-detail-title">
          <h1 ref={heading} tabIndex={-1}>{title}</h1>
          <div className="detail-badge-stack">
            <span className={`status-badge ${status === "active" ? "is-success" : "is-warning"}`}>
              {humanize(status)}
            </span>
            <span className="status-badge is-neutral">{locked ? "Locked" : "Open"}</span>
          </div>
        </div>
      </div>
    </header>
  );
}

function SupportEvidence({ supports }: { supports: ConceptualSupport[] }) {
  const [expandedSupportId, setExpandedSupportId] = useState<number | null>(null);
  return (
    <section className="detail-section modeled-source-mappings conceptual-support" aria-labelledby="conceptual-support-heading">
      <header>
        <h2 id="conceptual-support-heading">Support evidence</h2>
        <span>{supports.length} {supports.length === 1 ? "record" : "records"}</span>
      </header>
      {supports.length === 0 ? (
        <p className="detail-empty">No support evidence is recorded.</p>
      ) : (
        <div className="workflow-table-scroll table-scroll">
          <table aria-label="Support evidence">
            <thead>
              <tr><th>Source</th><th>Rationale</th><th>Confidence</th><th>Status</th><th>Details</th></tr>
            </thead>
            <tbody>
              {supports.map((support) => {
                const name = support.support_source_type === "object"
                  ? `${support.source_object.object_schema}.${support.source_object.object_name}`
                  : support.assertion_record.modeling_assertion_record_key;
                const expanded = expandedSupportId === support.conceptual_support_id;
                const detailId = `conceptual-support-${support.conceptual_support_id}`;
                return (
                  <Fragment key={support.conceptual_support_id}>
                    <tr aria-label={`Support ${support.conceptual_support_id}`}>
                      <td>
                        <strong>{name}</strong>
                        <small className="modeled-source-role">
                          {support.support_source_type === "object" ? "Physical Object" : "Modeling Assertion"}
                        </small>
                      </td>
                      <td className="modeled-source-rationale">{support.support_reason}</td>
                      <td>
                        <span className={`status-badge confidence-${support.support_confidence}`}>
                          {humanize(support.support_confidence)}
                        </span>
                      </td>
                      <td>
                        {humanize(support.support_status)}
                        <small className="modeled-source-role">{support.support_is_locked ? "Locked" : "Open"}</small>
                      </td>
                      <td>
                        <button
                          type="button"
                          className="text-action"
                          aria-label={`${expanded ? "Hide" : "Show"} details for ${name}`}
                          aria-expanded={expanded}
                          aria-controls={detailId}
                          onClick={() => setExpandedSupportId(expanded ? null : support.conceptual_support_id)}
                        >
                          {expanded ? "Hide details" : "Show details"}
                        </button>
                      </td>
                    </tr>
                    <tr id={detailId} aria-label={`Details for ${name}`} hidden={!expanded} className="conceptual-support-detail">
                      <td colSpan={5}>
                        <dl className="detail-fact-grid">
                          <Fact label="Role" value={support.support_role ?? "Not assigned"} />
                          {support.support_reason_detail ? <Fact label="Reason detail" value={support.support_reason_detail} /> : null}
                          {support.support_source_type === "object" ? (
                            <>
                              <Fact label="Tenant" value={support.source_object.tenant_code} />
                              <Fact label="System" value={support.source_object.system_code} />
                              <Fact label="Connection" value={support.source_object.connection_code} />
                            </>
                          ) : (
                            <>
                              <Fact label="Assertion" value={support.assertion_record.modeling_assertion_text} />
                              <Fact label="Document" value={support.assertion_record.modeling_assertion_document_name} />
                              <Fact label="Type" value={humanize(support.assertion_record.modeling_assertion_record_type)} />
                              <Fact
                                label="Assertion confidence"
                                value={support.assertion_record.modeling_assertion_confidence
                                  ? humanize(support.assertion_record.modeling_assertion_confidence)
                                  : "Not recorded"}
                              />
                              <Fact label="Assertion status" value={humanize(support.assertion_record.modeling_assertion_record_status)} />
                            </>
                          )}
                        </dl>
                      </td>
                    </tr>
                  </Fragment>
                );
              })}
            </tbody>
          </table>
        </div>
      )}
    </section>
  );
}

function detailErrorLabel(error: Error, kind: "Object" | "Relationship"): string {
  return error instanceof ApiError && error.status === 403
    ? `You do not have permission to view this Conceptual ${kind}.`
    : `Conceptual ${kind} details could not be loaded.`;
}

function humanize(value: string): string {
  return value.replaceAll("_", " ").replace(/^./, (character) => character.toLocaleUpperCase());
}
