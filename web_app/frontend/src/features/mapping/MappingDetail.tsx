import { useEffect, useRef } from "react";
import { useQuery } from "@tanstack/react-query";
import { Link } from "@tanstack/react-router";
import { DetailState } from "../../shared/ui";

import { ApiError } from "../../core/http";
import type { MappingAttributeDetail, MappingObjectDetail } from "./api";
import { formatRequiredDateTime as formatDateTime } from "../../shared/presentation";
import { mappingQueryKeys, type MappingApi } from "./api";
import { MappingDocumentView } from "./MappingDocumentView";

export function MappingObjectDetailPage({
  api,
  tenantId,
  modelId,
  mappingObjectId,
}: {
  api: MappingApi;
  tenantId: number;
  modelId: number;
  mappingObjectId: number;
}) {
  const query = useQuery({
    queryKey: mappingQueryKeys.object(tenantId, modelId, mappingObjectId),
    queryFn: () => api.readMappingObject(tenantId, modelId, mappingObjectId),
  });
  if (query.isPending) return <DetailState label="Loading Object Mapping…" />;
  if (query.isError) return <DetailState label={detailError(query.error, "Object")} error />;
  return <MappingObjectDetailView tenantId={tenantId} modelId={modelId} detail={query.data} />;
}

export function MappingAttributeDetailPage({
  api,
  tenantId,
  modelId,
  mappingAttributeId,
}: {
  api: MappingApi;
  tenantId: number;
  modelId: number;
  mappingAttributeId: number;
}) {
  const query = useQuery({
    queryKey: mappingQueryKeys.attribute(tenantId, modelId, mappingAttributeId),
    queryFn: () => api.readMappingAttribute(tenantId, modelId, mappingAttributeId),
  });
  if (query.isPending) return <DetailState label="Loading Attribute Mapping…" />;
  if (query.isError) return <DetailState label={detailError(query.error, "Attribute")} error />;
  return <MappingAttributeDetailView tenantId={tenantId} modelId={modelId} detail={query.data} />;
}

function MappingObjectDetailView({
  tenantId,
  modelId,
  detail,
}: {
  tenantId: number;
  modelId: number;
  detail: MappingObjectDetail;
}) {
  const heading = useRef<HTMLHeadingElement>(null);
  useEffect(() => heading.current?.focus(), []);
  return (
    <article className="workflow-detail-page mapping-detail-page page-enter">
      <DetailHeader
        tenantId={tenantId}
        modelId={modelId}
        view="objects"
        eyebrow={`Object Mapping ${detail.mapping_object_id}`}
        title={`${detail.target.object_schema}.${detail.target.object_name}`}
        status={detail.status}
        locked={detail.is_locked}
        headingRef={heading}
      />
      <section className="detail-section detail-primary" aria-labelledby="mapping-object-context">
        <header><h2 id="mapping-object-context">Mapping context</h2></header>
        <div className="endpoint-comparison">
          <section><small>Modeled source</small><h3>{detail.source.entity_name}</h3><span>{humanize(detail.source.entity_type)}</span></section>
          <span aria-hidden="true">→</span>
          <section><small>Target Object</small><h3>{detail.target.object_schema}.{detail.target.object_name}</h3><span>{detail.target.zone_code}</span></section>
        </div>
        <details className="support-record-details"><summary>Connection and template details</summary>
        <dl className="detail-fact-grid">
          <Fact label="Target Tenant" value={`${detail.target.tenant_name} (${detail.target.tenant_code})`} />
          <Fact label="Target System" value={`${detail.target.system_name} (${detail.target.system_code})`} />
          <Fact label="Connection" value={detail.target.connection_code} />
          <Fact label="Source System" value={`${detail.source_system.system_name} (${detail.source_system.system_code})`} />
          <Fact label="Dependency order" value={String(detail.dependency_order)} />
        </dl>
        <OutputTemplate template={detail.output_template} />
        </details>
      </section>
      <MappingDocumentView title="Transformation document" document={detail.mapping_document} />
      <MappingProvenance detail={detail} />
    </article>
  );
}

function MappingAttributeDetailView({
  tenantId,
  modelId,
  detail,
}: {
  tenantId: number;
  modelId: number;
  detail: MappingAttributeDetail;
}) {
  const heading = useRef<HTMLHeadingElement>(null);
  useEffect(() => heading.current?.focus(), []);
  const target = detail.target;
  return (
    <article className="workflow-detail-page mapping-detail-page page-enter">
      <DetailHeader
        tenantId={tenantId}
        modelId={modelId}
        view="attributes"
        eyebrow={`Attribute Mapping ${detail.mapping_attribute_id}`}
        title={`${target.object.object_schema}.${target.object.object_name}.${target.attribute_name}`}
        status={detail.status}
        locked={detail.is_locked}
        headingRef={heading}
      />
      <section className="detail-section detail-primary" aria-labelledby="mapping-attribute-context">
        <header><h2 id="mapping-attribute-context">Mapping context</h2></header>
        <div className="endpoint-comparison">
          <section><small>Modeled source</small><h3>{detail.source.entity.entity_name}.{detail.source.attribute_name}</h3><span>{humanize(detail.source.entity.entity_type)}</span></section>
          <span aria-hidden="true">→</span>
          <section><small>Target Attribute</small><h3>{target.object.object_schema}.{target.object.object_name}.{target.attribute_name}</h3><span>{target.attribute_data_type} · {target.object.zone_code}</span></section>
        </div>
        <details className="support-record-details"><summary>Connection and template details</summary>
        <dl className="detail-fact-grid">
          <Fact label="Target Tenant" value={`${target.object.tenant_name} (${target.object.tenant_code})`} />
          <Fact label="Target System" value={`${target.object.system_name} (${target.object.system_code})`} />
          <Fact label="Connection" value={target.object.connection_code} />
          <Fact label="Source System" value={`${detail.source_system.system_name} (${detail.source_system.system_code})`} />
          <Fact label="Ordinal" value={String(target.attribute_ordinal_position)} />
        </dl>
        <OutputTemplate template={detail.output_template} />
        </details>
      </section>
      <MappingDocumentView title="Transformation document" document={detail.mapping_document} />
      <details className="detail-section detail-disclosure" aria-labelledby="mapping-parent-object">
        <summary><h2 id="mapping-parent-object">Parent Object Mapping</h2></summary>
        <dl className="detail-fact-grid">
          <div><dt>Object Mapping</dt><dd>
            <Link className="text-action" to="/tenants/$tenantId/mapping/models/$modelId/objects/$mappingObjectId"
              params={{ tenantId: String(tenantId), modelId: String(modelId), mappingObjectId: String(detail.parent_object_mapping.mapping_object_id) }}>
              Object Mapping {detail.parent_object_mapping.mapping_object_id}
            </Link>
          </dd></div>
          <Fact label="Dependency order" value={String(detail.parent_object_mapping.dependency_order)} />
          <Fact label="Status" value={humanize(detail.parent_object_mapping.status)} />
          <Fact label="Lock" value={detail.parent_object_mapping.is_locked ? "Locked" : "Open"} />
        </dl>
      </details>
      <MappingProvenance detail={detail} />
    </article>
  );
}

function DetailHeader({
  tenantId,
  modelId,
  view,
  eyebrow,
  title,
  status,
  locked,
  headingRef,
}: {
  tenantId: number;
  modelId: number;
  view: "objects" | "attributes";
  eyebrow: string;
  title: string;
  status: string;
  locked: boolean;
  headingRef: React.RefObject<HTMLHeadingElement | null>;
}) {
  return (
    <header className="workflow-detail-header">
      <div>
        <Link
          className="text-action"
          aria-label="Back to Mapping"
          to="/tenants/$tenantId/mapping/models/$modelId"
          params={{ tenantId: String(tenantId), modelId: String(modelId) }}
          search={{ view }}
        >
          ← Back to Mapping
        </Link>
        <p className="eyebrow">{eyebrow}</p>
        <h1 ref={headingRef} tabIndex={-1}>{title}</h1>
      </div>
      <div className="detail-badge-stack">
        <span className={`status-badge ${statusTone(status)}`}>{humanize(status)}</span>
        <span className="status-badge is-neutral">{locked ? "Locked" : "Open"}</span>
      </div>
    </header>
  );
}

function OutputTemplate({ template }: { template: MappingObjectDetail["output_template"] }) {
  return (
    <dl className="detail-fact-grid">
      <Fact label="Output template" value={template?.output_template_name ?? "Free form"} />
      {template ? <>
        <Fact label="Template code" value={template.output_template_code} />
        <Fact label="Template target" value={humanize(template.output_template_target_type)} />
        <Fact label="Template state" value={template.is_active ? "Active" : "Inactive"} />
      </> : null}
    </dl>
  );
}

function MappingProvenance({ detail }: { detail: MappingObjectDetail | MappingAttributeDetail }) {
  const target = "mapping_attribute_id" in detail ? detail.target.object : detail.target;
  const source = "mapping_attribute_id" in detail ? detail.source.entity : detail.source;
  return (
    <details className="detail-section detail-disclosure" aria-labelledby="mapping-provenance">
      <summary><h2 id="mapping-provenance">Provenance</h2></summary>
      <dl className="detail-fact-grid">
        <Fact label="Workflow" value={detail.workflow_run_id === null ? "No workflow provenance" : `Workflow run ${detail.workflow_run_id}`} />
        <Fact label="Created" value={formatDateTime(detail.created_at)} />
        <Fact label="Updated" value={formatDateTime(detail.updated_at)} />
      </dl>
      <details className="support-record-details">
        <summary>Record details</summary>
        <dl className="detail-fact-grid">
          <Fact label="Target Object ID" value={String(target.object_id)} />
          <Fact label="Target System ID" value={String(target.system_id)} />
          <Fact label="Connection ID" value={String(target.connection_id)} />
          <Fact label="Source Entity ID" value={String(source.entity_id)} />
          <Fact label="Source System ID" value={String(detail.source_system.system_id)} />
          {"mapping_attribute_id" in detail ? <>
            <Fact label="Target Attribute ID" value={String(detail.target.attribute_id)} />
            <Fact label="Source Attribute ID" value={String(detail.source.attribute_id)} />
          </> : null}
          {detail.output_template ? <>
            <Fact label="Template ID" value={String(detail.output_template.output_template_id)} />
            <div className="digest-fact"><dt>Template schema digest</dt><dd><code>{detail.output_template.output_template_schema_digest}</code></dd></div>
          </> : null}
        </dl>
      </details>
    </details>
  );
}

function Fact({ label, value }: { label: string; value: string }) {
  return <div><dt>{label}</dt><dd>{value}</dd></div>;
}

function detailError(error: Error, kind: "Object" | "Attribute"): string {
  return error instanceof ApiError && error.status === 403
    ? `You do not have permission to view this ${kind} Mapping.`
    : `${kind} Mapping details could not be loaded.`;
}

function humanize(value: string): string {
  return value.replaceAll("_", " ").replace(/^./, (character) => character.toLocaleUpperCase());
}

function statusTone(status: string): string {
  if (status === "active") return "is-success";
  return "is-neutral";
}
