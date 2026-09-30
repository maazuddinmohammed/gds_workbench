import { useEffect, useRef, type ReactNode } from "react";
import { useQuery } from "@tanstack/react-query";
import { Link } from "@tanstack/react-router";
import { DetailState, Fact } from "../../shared/ui";
import { formatRequiredDateTime } from "../../shared/presentation";

import { ApiError } from "../../core/http";
import type { MappingAttributeDetail, MappingObjectDetail } from "./api";
import { mappingQueryKeys, type MappingApi } from "./api";
import { MappingDocumentView } from "./MappingDocumentView";
import { MappingObjectAttributes } from "./MappingObjectAttributes";
import { MappingLogicDocument } from "./MappingLogicDocument";

export function MappingObjectDetailPage({
  api,
  tenantId,
  modelId,
  mappingObjectId,
  modelRevision,
  hasTenantLock,
}: {
  api: MappingApi;
  tenantId: number;
  modelId: number;
  mappingObjectId: number;
  modelRevision: number;
  hasTenantLock: boolean;
}) {
  const query = useQuery({
    queryKey: mappingQueryKeys.object(tenantId, modelId, mappingObjectId),
    queryFn: () => api.readMappingObject(tenantId, modelId, mappingObjectId),
  });
  if (query.isPending) return <DetailState label="Loading Object Mapping…" />;
  if (query.isError) return <DetailState label={detailError(query.error, "Object")} error />;
  return (
    <MappingObjectDetailView tenantId={tenantId} modelId={modelId} detail={query.data}>
      <MappingObjectAttributes key={mappingObjectId} api={api} tenantId={tenantId} modelId={modelId}
        mappingObjectId={mappingObjectId} modelRevision={modelRevision} hasTenantLock={hasTenantLock} />
    </MappingObjectDetailView>
  );
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
  children,
}: {
  tenantId: number;
  modelId: number;
  detail: MappingObjectDetail;
  children: ReactNode;
}) {
  const heading = useRef<HTMLHeadingElement>(null);
  useEffect(() => heading.current?.focus(), []);
  return (
    <article className="workflow-detail-page mapping-detail-page mapping-object-detail page-enter">
      <DetailHeader
        tenantId={tenantId}
        modelId={modelId}
        layer={detail.target.entity_type === "logical_entity" ? "logical" : "dimensional"}
        eyebrow={detail.target.entity_type === "logical_entity" ? "Logical entity" : "Dimensional entity"}
        title={detail.target.entity_name}
        status={detail.status}
        locked={detail.is_locked}
        headingRef={heading}
        context={<dl className="mapping-identity-strip">
          <Fact label="Schema" value={detail.target.entity_schema_name} />
          <Fact label="System" value={detail.source_system.system_code} />
        </dl>}
      />
      <section className="mapping-transformation-panel" aria-label="Entity transformation">
        <header><h2>Entity transformation</h2></header>
        {detail.mapping_document === null ? null
          : <MappingLogicDocument document={detail.mapping_document} path="Entity transformation" />}
      </section>
      {children}
      <details className="mapping-inspector-details"><summary>Mapping details</summary>
        <dl className="detail-fact-grid">
          <Fact label="Object Mapping" value={String(detail.mapping_object_id)} />
          <Fact label="Entity order" value={String(detail.dependency_order)} />
          <Fact label="Updated" value={formatRequiredDateTime(detail.updated_at)} />
          <Fact label="Created" value={formatRequiredDateTime(detail.created_at)} />
        </dl>
        <OutputTemplate template={detail.output_template} />
        {detail.mapping_document !== null ? <details className="support-record-details"><summary>Original document</summary>
          <pre className="mapping-original-document" tabIndex={0}><code>{JSON.stringify(detail.mapping_document, null, 2)}</code></pre>
        </details> : null}
      </details>
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
        parentObjectId={detail.parent_object_mapping.mapping_object_id}
        layer={target.entity.entity_type === "logical_entity" ? "logical" : "dimensional"}
        eyebrow={`Attribute Mapping ${detail.mapping_attribute_id}`}
        title={`${target.entity.entity_schema_name}.${target.entity.entity_name}.${target.attribute_name}`}
        status={detail.status}
        locked={detail.is_locked}
        headingRef={heading}
      />
      <section className="detail-section detail-primary" aria-labelledby="mapping-attribute-context">
        <header><h2 id="mapping-attribute-context">Mapping context</h2></header>
        <dl className="detail-fact-grid">
          <Fact label="Schema" value={target.entity.entity_schema_name} />
          <Fact label="Entity name" value={target.entity.entity_name} />
          <Fact label="Attribute" value={target.attribute_name} />
          <Fact label="Data type" value={target.data_type} />
          <Fact label="Source System" value={detail.source_system.system_code} />
        </dl>
        <details className="support-record-details"><summary>Source and template details</summary>
        <dl className="detail-fact-grid">
          <Fact label="Ordinal" value={String(target.ordinal_position)} />
          <Fact label="Updated" value={formatRequiredDateTime(detail.updated_at)} />
          <Fact label="Created" value={formatRequiredDateTime(detail.created_at)} />
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
              search={{ layer: target.entity.entity_type === "logical_entity" ? "logical" : "dimensional" }}
              params={{ tenantId: String(tenantId), modelId: String(modelId), mappingObjectId: String(detail.parent_object_mapping.mapping_object_id) }}>
              Object Mapping {detail.parent_object_mapping.mapping_object_id}
            </Link>
          </dd></div>
          <Fact label="Entity order" value={String(detail.parent_object_mapping.dependency_order)} />
          <Fact label="Status" value={humanize(detail.parent_object_mapping.status)} />
          <Fact label="Lock" value={detail.parent_object_mapping.is_locked ? "Locked" : "Open"} />
        </dl>
      </details>
    </article>
  );
}

function DetailHeader({
  tenantId,
  modelId,
  parentObjectId,
  layer,
  eyebrow,
  title,
  status,
  locked,
  headingRef,
  context,
}: {
  tenantId: number;
  modelId: number;
  parentObjectId?: number;
  layer?: "logical" | "dimensional";
  eyebrow: string;
  title: string;
  status: string;
  locked: boolean;
  headingRef: React.RefObject<HTMLHeadingElement | null>;
  context?: ReactNode;
}) {
  return (
    <header className="workflow-detail-header mapping-detail-heading">
        <Link
          className="text-action"
          aria-label={parentObjectId ? "Back to Object Mapping" : "Back to Object mappings"}
          to={parentObjectId
            ? "/tenants/$tenantId/mapping/models/$modelId/objects/$mappingObjectId"
            : "/tenants/$tenantId/mapping/models/$modelId"}
          params={{ tenantId: String(tenantId), modelId: String(modelId),
            ...(parentObjectId ? { mappingObjectId: String(parentObjectId) } : {}) }}
          search={layer ? { layer } : {}}
        >
          ← {parentObjectId ? "Back to Object Mapping" : "Back to Object mappings"}
        </Link>
      <div className="mapping-detail-identity">
        <div className="mapping-detail-name">
          <p className="eyebrow">{eyebrow}</p>
          <h1 ref={headingRef} tabIndex={-1}>{title}</h1>
        </div>
        {context}
        <div className="detail-badge-stack">
        <span className={`status-badge ${statusTone(status)}`}>{humanize(status)}</span>
          <span className="status-badge is-neutral">{locked ? "Locked" : "Open"}</span>
        </div>
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
