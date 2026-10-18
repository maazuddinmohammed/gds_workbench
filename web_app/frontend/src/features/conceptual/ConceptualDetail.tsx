import { Fragment, useEffect, useRef, useState, type ReactNode } from "react";
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
  actions,
  api,
  tenantId,
  projectId,
  objectId,
}: {
  actions?: ReactNode;
  api: ConceptualApi;
  tenantId: number;
  projectId: number;
  objectId: number;
}) {
  const query = useQuery({
    queryKey: conceptualQueryKeys.object(tenantId, projectId, objectId),
    queryFn: () => api.readConceptualObject(tenantId, projectId, objectId),
  });
  if (query.isPending) return <DetailState label="Loading Conceptual Object…" />;
  if (query.isError) {
    return <DetailState label={detailErrorLabel(query.error, "Object")} error />;
  }
  return <ConceptualObjectView actions={actions} tenantId={tenantId} projectId={projectId} object={query.data} />;
}

export function ConceptualRelationshipDetailPage({
  actions,
  api,
  tenantId,
  projectId,
  relationshipId,
}: {
  actions?: ReactNode;
  api: ConceptualApi;
  tenantId: number;
  projectId: number;
  relationshipId: number;
}) {
  const query = useQuery({
    queryKey: conceptualQueryKeys.relationship(tenantId, projectId, relationshipId),
    queryFn: () => api.readConceptualRelationship(tenantId, projectId, relationshipId),
  });
  if (query.isPending) return <DetailState label="Loading Conceptual Relationship…" />;
  if (query.isError) {
    return <DetailState label={detailErrorLabel(query.error, "Relationship")} error />;
  }
  return (
    <ConceptualRelationshipView
      actions={actions}
      tenantId={tenantId}
      projectId={projectId}
      relationship={query.data}
    />
  );
}

function ConceptualObjectView({
  actions,
  tenantId,
  projectId,
  object,
}: {
  actions?: ReactNode;
  tenantId: number;
  projectId: number;
  object: ConceptualObjectDetail;
}) {
  return (
    <article className="workflow-detail-page conceptual-detail-page modeled-detail-page page-enter">
      <DetailHeader
        actions={actions}
        tenantId={tenantId}
        projectId={projectId}
        title={object.conceptual_object_name}
        status={object.conceptual_object_status}
        locked={object.conceptual_object_is_locked}
      />
      <section className="detail-section detail-primary" aria-label="Object definition">
        <dl className="modeled-detail-fields">
          <div className="is-definition"><dt>Definition</dt><dd>{object.conceptual_object_definition}</dd></div>
          <Fact label="Grain" value={object.conceptual_object_grain} />
          <Fact label="Type" value={humanize(object.conceptual_object_type)} />
          {object.conceptual_object_aliases.length ? (
            <div aria-label="Object aliases">
              <dt>Aliases</dt>
              <dd><div className="chip-list">
                {object.conceptual_object_aliases.map((alias) => <span key={alias}>{alias}</span>)}
              </div></dd>
            </div>
          ) : null}
          <Fact label="Confidence" value={humanize(object.conceptual_object_confidence)} />
          <Fact label="Updated" value={formatDateTime(object.updated_at)} />
        </dl>
      </section>
      <SupportEvidence supports={object.supports} />
    </article>
  );
}

function ConceptualRelationshipView({
  actions,
  tenantId,
  projectId,
  relationship,
}: {
  actions?: ReactNode;
  tenantId: number;
  projectId: number;
  relationship: ConceptualRelationshipDetail;
}) {
  return (
    <article className="workflow-detail-page conceptual-detail-page modeled-detail-page page-enter">
      <DetailHeader
        actions={actions}
        tenantId={tenantId}
        projectId={projectId}
        title={relationship.conceptual_relationship_name}
        status={relationship.conceptual_relationship_status}
        locked={relationship.conceptual_relationship_is_locked}
      />
      <section className="detail-section detail-primary" aria-label="Relationship definition">
        <dl className="modeled-detail-fields">
          <div className="is-definition"><dt>Definition</dt><dd>{relationship.conceptual_relationship_definition}</dd></div>
          <Fact label="From Object" value={relationship.from_conceptual_object_name} />
          <Fact label="To Object" value={relationship.to_conceptual_object_name} />
          <Fact label="Type" value={humanize(relationship.conceptual_relationship_type)} />
          <Fact label="Cardinality" value={humanize(relationship.conceptual_relationship_cardinality)} />
          <Fact label="Confidence" value={humanize(relationship.conceptual_relationship_confidence)} />
          <Fact label="Updated" value={formatDateTime(relationship.updated_at)} />
        </dl>
      </section>
      <section className="detail-section" aria-labelledby="relationship-reasoning-heading">
        <header><h2 id="relationship-reasoning-heading">Reasoning</h2></header>
        <dl className="modeled-detail-fields">
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
  actions,
  tenantId,
  projectId,
  title,
  status,
  locked,
}: {
  actions?: ReactNode;
  tenantId: number;
  projectId: number;
  title: string;
  status: string;
  locked: boolean;
}) {
  const heading = useRef<HTMLHeadingElement>(null);
  useEffect(() => heading.current?.focus(), []);
  return (
    <header className="workflow-detail-header">
      <div className="workspace-record-heading">
        <Link
          className="text-action"
          aria-label="Back to Conceptual"
          to="/tenants/$tenantId/projects/$projectId/conceptual"
          params={{ tenantId: String(tenantId), projectId: String(projectId) }}
        >
          ← Back to Conceptual
        </Link>
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
      {actions}
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
        <div className="workflow-table-scroll table-scroll" role="region" aria-label="Scrollable Support evidence" tabIndex={0}>
          <table aria-label="Support evidence">
            <thead>
              <tr><th>Schema</th><th>Object / context</th><th>Rationale</th><th>Role</th><th>Confidence</th><th>Status</th><th>Details</th></tr>
            </thead>
            <tbody>
              {supports.map((support) => {
                const name = support.support_source_type === "object"
                  ? `${support.source_object.object_schema}.${support.source_object.object_name}`
                  : support.context_record.context_group_name;
                const expanded = expandedSupportId === support.conceptual_support_id;
                const detailId = `conceptual-support-${support.conceptual_support_id}`;
                return (
                  <Fragment key={support.conceptual_support_id}>
                    <tr aria-label={`Support ${support.conceptual_support_id}`}>
                      <td>{support.support_source_type === "object" ? support.source_object.object_schema : "—"}</td>
                      <td>
                        <strong>{support.support_source_type === "object" ? support.source_object.object_name : name}</strong>
                        <small className="modeled-source-role">
                          {support.support_source_type === "object" ? "Physical Object" : "Context record"}
                        </small>
                      </td>
                      <td className="modeled-source-rationale">{support.support_reason}</td>
                      <td>{support.support_role ? humanize(support.support_role) : "Not assigned"}</td>
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
                      <td colSpan={7}>
                        <dl className="modeled-detail-fields">
                          {support.support_reason_detail ? <Fact label="Reason detail" value={support.support_reason_detail} /> : null}
                          {support.support_source_type === "object" ? (
                            <>
                              <Fact label="Tenant" value={support.source_object.tenant_code} />
                              <Fact label="System" value={support.source_object.system_code} />
                              <Fact label="Connection" value={support.source_object.connection_code} />
                            </>
                          ) : (
                            <>
                              <Fact label="Context" value={support.context_record.context_text} />
                              <Fact label="Group" value={support.context_record.context_group_name} />
                              <Fact label="Type" value={support.context_record.context_type_name} />
                              <Fact label="Source reference" value={support.context_record.source_reference ?? "Not recorded"} />
                              <Fact label="Context status" value={humanize(support.context_record.status)} />
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
