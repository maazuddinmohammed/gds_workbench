import { useEffect, useRef } from "react";
import { useQuery } from "@tanstack/react-query";
import { Link } from "@tanstack/react-router";

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
      <section className="detail-section" aria-labelledby="mapping-target-object">
        <header><h2 id="mapping-target-object">Target Object</h2></header>
        <dl className="detail-fact-grid">
          <Fact label="Tenant" value={`${detail.target.tenant_name} (${detail.target.tenant_code})`} />
          <Fact label="System" value={`${detail.target.system_name} (${detail.target.system_code}) · ID ${detail.target.system_id}`} />
          <Fact label="Connection" value={`${detail.target.connection_code} · ID ${detail.target.connection_id}`} />
          <Fact label="Zone" value={detail.target.zone_code} />
          <Fact label="Object ID" value={String(detail.target.object_id)} />
          <Fact label="Dependency order" value={String(detail.dependency_order)} />
        </dl>
      </section>
      <section className="detail-section" aria-labelledby="mapping-modeled-source">
        <header><h2 id="mapping-modeled-source">Modeled source</h2></header>
        <dl className="detail-fact-grid">
          <Fact label="Entity" value={detail.source.entity_name} />
          <Fact label="Entity type" value={humanize(detail.source.entity_type)} />
          <Fact label="Entity ID" value={String(detail.source.entity_id)} />
          <Fact label="Source System" value={`${detail.source_system.system_name} (${detail.source_system.system_code}) · ID ${detail.source_system.system_id}`} />
        </dl>
      </section>
      <section className="detail-section" aria-labelledby="mapping-output-template">
        <header><h2 id="mapping-output-template">Output template</h2></header>
        <dl className="detail-fact-grid">
          <Fact label="Output template" value={detail.output_template?.output_template_name ?? "Free form"} />
          <Fact label="Template code" value={detail.output_template?.output_template_code ?? "Free form"} />
        </dl>
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
      <section className="detail-section" aria-labelledby="mapping-target-attribute">
        <header><h2 id="mapping-target-attribute">Target Attribute</h2></header>
        <dl className="detail-fact-grid">
          <Fact label="Tenant" value={`${target.object.tenant_name} (${target.object.tenant_code})`} />
          <Fact label="System" value={`${target.object.system_name} (${target.object.system_code}) · ID ${target.object.system_id}`} />
          <Fact label="Connection" value={`${target.object.connection_code} · ID ${target.object.connection_id}`} />
          <Fact label="Zone" value={target.object.zone_code} />
          <Fact label="Object ID" value={String(target.object.object_id)} />
          <Fact label="Attribute ID" value={String(target.attribute_id)} />
          <Fact label="Data type" value={target.attribute_data_type} />
          <Fact label="Ordinal" value={String(target.attribute_ordinal_position)} />
        </dl>
      </section>
      <section className="detail-section" aria-labelledby="mapping-source-attribute">
        <header><h2 id="mapping-source-attribute">Modeled source</h2></header>
        <dl className="detail-fact-grid">
          <Fact label="Entity" value={detail.source.entity.entity_name} />
          <Fact label="Entity type" value={humanize(detail.source.entity.entity_type)} />
          <Fact label="Entity ID" value={String(detail.source.entity.entity_id)} />
          <Fact label="Attribute" value={detail.source.attribute_name} />
          <Fact label="Attribute ID" value={String(detail.source.attribute_id)} />
          <Fact label="Source System" value={`${detail.source_system.system_name} (${detail.source_system.system_code}) · ID ${detail.source_system.system_id}`} />
        </dl>
      </section>
      <section className="detail-section" aria-labelledby="mapping-parent-object">
        <header><h2 id="mapping-parent-object">Parent Object Mapping</h2></header>
        <dl className="detail-fact-grid">
          <Fact label="Object Mapping ID" value={String(detail.parent_object_mapping.mapping_object_id)} />
          <Fact label="Dependency order" value={String(detail.parent_object_mapping.dependency_order)} />
          <Fact label="Status" value={humanize(detail.parent_object_mapping.status)} />
          <Fact label="Lock" value={detail.parent_object_mapping.is_locked ? "Locked" : "Open"} />
        </dl>
      </section>
      <section className="detail-section" aria-labelledby="mapping-attribute-delivery">
        <header><h2 id="mapping-attribute-delivery">Delivery contract</h2></header>
        <dl className="detail-fact-grid">
          <Fact label="Output template" value={detail.output_template?.output_template_name ?? "Free form"} />
          <Fact label="Template ID" value={detail.output_template ? String(detail.output_template.output_template_id) : "Free form"} />
          <Fact label="Template code" value={detail.output_template?.output_template_code ?? "Free form"} />
          <Fact label="Template target" value={detail.output_template ? humanize(detail.output_template.output_template_target_type) : "Free form"} />
          <Fact label="Template state" value={detail.output_template ? detail.output_template.is_active ? "Active" : "Inactive" : "Free form"} />
        </dl>
      </section>
      <MappingDocumentView title="Transformation document" document={detail.mapping_document} />
      <section className="detail-section" aria-labelledby="mapping-attribute-provenance">
        <header><h2 id="mapping-attribute-provenance">Provenance</h2></header>
        <dl className="detail-fact-grid">
          <Fact label="Workflow" value={detail.workflow_run_id === null ? "No workflow provenance" : `Workflow run ${detail.workflow_run_id}`} />
          <Fact label="Created" value={formatDateTime(detail.created_at)} />
          <Fact label="Updated" value={formatDateTime(detail.updated_at)} />
        </dl>
      </section>
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

function MappingProvenance({ detail }: { detail: MappingObjectDetail }) {
  return (
    <section className="detail-section" aria-labelledby="mapping-provenance">
      <header><h2 id="mapping-provenance">Provenance</h2></header>
      <dl className="detail-fact-grid">
        <Fact label="Workflow" value={detail.workflow_run_id === null ? "No workflow provenance" : `Workflow run ${detail.workflow_run_id}`} />
        <Fact label="Template ID" value={detail.output_template ? String(detail.output_template.output_template_id) : "Free form"} />
        <Fact label="Template code" value={detail.output_template?.output_template_code ?? "Free form"} />
        <Fact label="Template target" value={detail.output_template ? humanize(detail.output_template.output_template_target_type) : "Free form"} />
        <Fact label="Template state" value={detail.output_template ? detail.output_template.is_active ? "Active" : "Inactive" : "Free form"} />
        <Fact label="Created" value={formatDateTime(detail.created_at)} />
        <Fact label="Updated" value={formatDateTime(detail.updated_at)} />
      </dl>
    </section>
  );
}

function Fact({ label, value }: { label: string; value: string }) {
  return <div><dt>{label}</dt><dd>{value}</dd></div>;
}

function DetailState({ label, error = false }: { label: string; error?: boolean }) {
  return <div className={`surface-state detail-state${error ? " is-error" : ""}`} {...(error ? { role: "alert" } : { "aria-busy": true })}>{label}</div>;
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
