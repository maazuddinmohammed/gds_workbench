import { useState } from "react";
import { Link } from "@tanstack/react-router";
import { useInfiniteQuery, useQuery, useQueryClient } from "@tanstack/react-query";

import { DetailState, Fact } from "../../shared/ui";
import { formatRequiredDateTime as formatDateTime } from "../../shared/presentation";
import { assertionsQueryKeys, type AssertionsApi, type AssertionRecordFilters, type AssertionDocumentReference } from "./api";
import { AssertionRecordsLedger } from "./AssertionLedgers";
import { AssertionEditor } from "./AssertionEditor";
import { ModelRecordReview } from "../model_record_review/ModelRecordReview";
import { NormalizedJson } from "./NormalizedJson";

export function AssertionDocumentDetailPage({ api, tenantId, modelId, documentId, modelRevision, hasTenantLock }: {
  api: AssertionsApi; tenantId: number; modelId: number; documentId: number; modelRevision: number; hasTenantLock: boolean;
}) {
  const queryClient = useQueryClient();
  const [editing, setEditing] = useState(false);
  const [filters, setFilters] = useState<AssertionRecordFilters>({});
  const query = useQuery({
    queryKey: assertionsQueryKeys.document(tenantId, modelId, documentId),
    queryFn: () => api.readAssertionDocument(tenantId, modelId, documentId),
  });
  const scopedFilters = { ...filters, documentId };
  const records = useInfiniteQuery({
    queryKey: assertionsQueryKeys.records(tenantId, modelId, scopedFilters),
    queryFn: ({ pageParam }) => api.listAssertionRecords(tenantId, modelId, scopedFilters, 200, pageParam),
    initialPageParam: undefined as string | undefined,
    getNextPageParam: (page) => page.next_cursor ?? undefined,
    enabled: query.isSuccess,
  });
  const saved = async () => {
    setFilters({});
    await Promise.all([
      queryClient.invalidateQueries({ queryKey: ["assertion-records", tenantId, modelId] }),
      queryClient.invalidateQueries({ queryKey: ["assertion-document", tenantId, modelId, documentId] }),
      queryClient.invalidateQueries({ queryKey: ["assertion-documents", tenantId, modelId] }),
      queryClient.invalidateQueries({ queryKey: ["model", tenantId, modelId] }),
    ]);
  };
  if (query.isPending) return <DetailState label="Loading Assertion Document…" />;
  if (query.isError) return <DetailState label="Assertion Document details could not be loaded." error />;
  const document = query.data;
  return <article className="assertions-page page-enter">
    <DetailHeader tenantId={tenantId} modelId={modelId} eyebrow="Assertion document" title={document.modeling_assertion_document_name} active={document.is_active} />
    <header className="workflow-commandbar">
      <h2>Records</h2>
      <div className="workflow-command-actions">
        <button className="button button-primary button-small" type="button" disabled={!hasTenantLock || !document.is_active} title={!hasTenantLock ? "Tenant Lock required" : !document.is_active ? "Document is inactive" : undefined} onClick={() => setEditing(true)}>Add Assertion</button>
        <button className="button button-secondary button-small" type="button" onClick={async () => { await Promise.all([query.refetch(), records.refetch(), queryClient.invalidateQueries({ queryKey: ["model", tenantId, modelId] }), queryClient.invalidateQueries({ queryKey: ["tenant-home", tenantId] })]); }}>Refresh</button>
      </div>
    </header>
    {editing ? <AssertionEditor api={api} tenantId={tenantId} modelId={modelId} modelRevision={modelRevision} hasTenantLock={hasTenantLock} document={document} onClose={() => setEditing(false)} onSaved={saved} /> : null}
    <AssertionRecordsLedger key={JSON.stringify(scopedFilters)} tenantId={tenantId} modelId={modelId} items={records.data?.pages.flatMap((page) => page.items) ?? []} filters={filters}
      state={{ isLoading: records.isPending, isError: records.isError, revisionMismatch: records.data?.pages.some((page) => page.model_revision !== modelRevision) ?? false, hasMore: records.hasNextPage, isLoadingMore: records.isFetchingNextPage }}
      onApplyFilters={setFilters} onLoadMore={() => { void records.fetchNextPage(); }} />
    <details className="detail-section detail-disclosure">
      <summary><h2>Document details</h2></summary>
      {document.modeling_assertion_document_description ? <p className="detail-prose">{document.modeling_assertion_document_description}</p> : null}
      <dl className="detail-fact-grid">
        <Fact label="Type" value={document.modeling_assertion_document_type ?? "Not classified"} />
        <Fact label="Source Tenant" value={document.source_tenant?.tenant_code ?? "Entire Model"} />
        <Fact label="Source System" value={document.source_system?.system_code ?? "All Systems"} />
        <Fact label="Updated" value={formatDateTime(document.updated_at)} />
      </dl>
      <NormalizedJson value={document.modeling_assertion_document_metadata} />
    </details>
  </article>;
}

export function AssertionRecordDetailPage({
  api,
  tenantId,
  modelId,
  recordId,
  modelRevision,
  hasTenantLock,
}: {
  api: AssertionsApi;
  tenantId: number;
  modelId: number;
  recordId: number;
  modelRevision: number;
  hasTenantLock: boolean;
}) {
  const [editing, setEditing] = useState(false);
  const queryClient = useQueryClient();
  const query = useQuery({
    queryKey: assertionsQueryKeys.record(tenantId, modelId, recordId),
    queryFn: () => api.readAssertionRecord(tenantId, modelId, recordId),
  });
  if (query.isPending) return <DetailState label="Loading Assertion Record…" />;
  if (query.isError) return <DetailState label="Assertion Record details could not be loaded." error />;
  const record = query.data;
  const saved = async () => {
    await Promise.all([
      queryClient.invalidateQueries({ queryKey: ["assertion-record", tenantId, modelId, recordId] }),
      queryClient.invalidateQueries({ queryKey: ["assertion-records", tenantId, modelId] }),
      queryClient.invalidateQueries({ queryKey: ["assertion-documents", tenantId, modelId] }),
      queryClient.invalidateQueries({ queryKey: ["model", tenantId, modelId] }),
    ]);
  };
  return (
    <article className="workflow-detail-page page-enter">
      <DetailHeader
        tenantId={tenantId}
        modelId={modelId}
        eyebrow={`Assertion Record ${record.modeling_assertion_record_id}`}
        document={record.document}
        title={record.modeling_assertion_record_key}
        active={record.modeling_assertion_record_status === "active"}
      />
      <ModelRecordReview api={api} tenantId={tenantId} modelId={modelId} modelRevision={modelRevision}
        dataset="modeling_assertion_record" selectedIds={new Set([recordId])} hasTenantLock={hasTenantLock}
        disabled={query.isFetching} onApplied={saved} />
      {(record.modeling_assertion_source_location?.entry_method === "manual" || record.document.modeling_assertion_document_type === "manual_input") ? <div className="workflow-command-actions">
        <button className="button button-secondary button-small" type="button"
          disabled={!hasTenantLock || record.modeling_assertion_record_is_locked || query.isFetching}
          title={!hasTenantLock ? "Tenant Lock required" : record.modeling_assertion_record_is_locked ? "Unlock this Assertion before editing" : undefined}
          onClick={() => setEditing(true)}>Edit Assertion</button>
      </div> : null}
      {editing ? <AssertionEditor api={api} tenantId={tenantId} modelId={modelId} modelRevision={modelRevision}
        hasTenantLock={hasTenantLock} record={record} onClose={() => setEditing(false)} onSaved={saved} /> : null}
      <section className="detail-section detail-primary" aria-labelledby="assertion-text-heading">
        <header>
          <h2 id="assertion-text-heading">Assertion</h2>
          <span>{humanize(record.modeling_assertion_record_type)}</span>
        </header>
        <p className="detail-prose is-prominent">{record.modeling_assertion_text}</p>
        <dl className="detail-fact-grid">
          <Fact label="Document" value={record.document.modeling_assertion_document_name} />
          <Fact label="Status" value={humanize(record.modeling_assertion_record_status)} />
          <Fact label="Confidence" value={record.modeling_assertion_confidence ?? "Not set"} />
          <Fact label="Lock" value={record.modeling_assertion_record_is_locked ? "Locked" : "Open"} />
          <Fact label="Updated" value={formatDateTime(record.updated_at)} />
        </dl>
      </section>
      <details className="detail-section detail-disclosure" aria-labelledby="assertion-details-heading" open={(record.modeling_assertion_source_location?.entry_method === "manual" || record.document.modeling_assertion_document_type === "manual_input")}>
        <summary><h2 id="assertion-details-heading">{(record.modeling_assertion_source_location?.entry_method === "manual" || record.document.modeling_assertion_document_type === "manual_input") ? "Additional context" : "Normalized details"}</h2></summary>
        <NormalizedJson value={record.modeling_assertion_details} />
      </details>
      {record.modeling_assertion_source_location ? (
        <details className="detail-section detail-disclosure" aria-labelledby="assertion-source-heading">
          <summary><h2 id="assertion-source-heading">Source location</h2></summary>
          <NormalizedJson value={record.modeling_assertion_source_location} />
        </details>
      ) : null}
    </article>
  );
}

function DetailHeader({
  tenantId,
  modelId,
  eyebrow,
  title,
  active,
  document,
}: {
  tenantId: number;
  modelId: number;
  eyebrow: string;
  title: string;
  active: boolean;
  document?: AssertionDocumentReference;
}) {
  return (
    <header className="workflow-detail-header">
      <div>
        {document ? <Link className="text-action" to="/tenants/$tenantId/models/$modelId/assertions/documents/$documentId" params={{ tenantId: String(tenantId), modelId: String(modelId), documentId: String(document.modeling_assertion_document_id) }}>← Back to {document.modeling_assertion_document_name}</Link> : <Link className="text-action" to="/tenants/$tenantId/models/$modelId/assertions" params={{ tenantId: String(tenantId), modelId: String(modelId) }}>← Back to Documents</Link>}
        <p className="eyebrow">{eyebrow}</p>
        <h1>{title}</h1>
      </div>
      <span className={`status-badge ${active ? "is-success" : "is-neutral"}`}>
        {active ? "Active" : "Inactive"}
      </span>
    </header>
  );
}

function humanize(value: string): string {
  return value.replaceAll("_", " ").replace(/^./, (character) => character.toLocaleUpperCase());
}
