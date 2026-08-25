import { Link } from "@tanstack/react-router";
import { useQuery } from "@tanstack/react-query";

import { formatRequiredDateTime as formatDateTime } from "../../shared/presentation";
import { assertionsQueryKeys, type AssertionsApi } from "./api";
import { NormalizedJson } from "./NormalizedJson";

export function AssertionDocumentDetailPage({
  api,
  tenantId,
  modelId,
  documentId,
}: {
  api: AssertionsApi;
  tenantId: number;
  modelId: number;
  documentId: number;
}) {
  const query = useQuery({
    queryKey: assertionsQueryKeys.document(tenantId, modelId, documentId),
    queryFn: () => api.readAssertionDocument(tenantId, modelId, documentId),
  });
  if (query.isPending) return <DetailState label="Loading Assertion Document…" />;
  if (query.isError) return <DetailState label="Assertion Document details could not be loaded." error />;
  const document = query.data;
  return (
    <article className="workflow-detail-page page-enter">
      <DetailHeader
        tenantId={tenantId}
        modelId={modelId}
        eyebrow={`Assertion Document ${document.modeling_assertion_document_id}`}
        title={document.modeling_assertion_document_name}
        active={document.is_active}
      />
      <section className="detail-section" aria-labelledby="document-overview-heading">
        <header><h2 id="document-overview-heading">Document overview</h2></header>
        <p className="detail-prose">
          {document.modeling_assertion_document_description ?? "No description recorded."}
        </p>
        <dl className="detail-fact-grid">
          <Fact label="Type" value={document.modeling_assertion_document_type ?? "Not classified"} />
          <Fact label="File pattern" value={document.modeling_assertion_file_pattern ?? "Not recorded"} />
          <Fact label="Source Tenant" value={document.source_tenant?.tenant_name ?? "Not assigned"} />
          <Fact label="Source System" value={document.source_system?.system_name ?? "Not assigned"} />
          <Fact label="Records" value={String(document.record_count)} />
          <Fact label="Needs review" value={String(document.needs_review_record_count)} />
          <Fact label="Locked" value={String(document.locked_record_count)} />
          <Fact label="Updated" value={formatDateTime(document.updated_at)} />
        </dl>
      </section>
      <section className="detail-section" aria-labelledby="document-metadata-heading">
        <header><h2 id="document-metadata-heading">Normalized metadata</h2></header>
        <NormalizedJson value={document.modeling_assertion_document_metadata} />
      </section>
      <Provenance
        workflowRunId={document.workflow_run_id}
        agentRunId={document.agent_run_id}
        createdAt={document.created_at}
      />
    </article>
  );
}

export function AssertionRecordDetailPage({
  api,
  tenantId,
  modelId,
  recordId,
}: {
  api: AssertionsApi;
  tenantId: number;
  modelId: number;
  recordId: number;
}) {
  const query = useQuery({
    queryKey: assertionsQueryKeys.record(tenantId, modelId, recordId),
    queryFn: () => api.readAssertionRecord(tenantId, modelId, recordId),
  });
  if (query.isPending) return <DetailState label="Loading Assertion Record…" />;
  if (query.isError) return <DetailState label="Assertion Record details could not be loaded." error />;
  const record = query.data;
  return (
    <article className="workflow-detail-page page-enter">
      <DetailHeader
        tenantId={tenantId}
        modelId={modelId}
        eyebrow={`Assertion Record ${record.modeling_assertion_record_id}`}
        title={record.modeling_assertion_record_key}
        active={record.modeling_assertion_record_status !== "inactive"}
      />
      <section className="detail-section" aria-labelledby="assertion-text-heading">
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
          <Fact
            label="Applicable layers"
            value={record.modeling_assertion_applicable_layers.map(humanize).join(", ")}
          />
          <Fact label="Updated" value={formatDateTime(record.updated_at)} />
        </dl>
      </section>
      <section className="detail-section" aria-labelledby="assertion-details-heading">
        <header><h2 id="assertion-details-heading">Normalized details</h2></header>
        <NormalizedJson value={record.modeling_assertion_details} />
      </section>
      {record.modeling_assertion_source_location ? (
        <section className="detail-section" aria-labelledby="assertion-source-heading">
          <header><h2 id="assertion-source-heading">Source location</h2></header>
          <NormalizedJson value={record.modeling_assertion_source_location} />
        </section>
      ) : null}
      <Provenance
        workflowRunId={record.workflow_run_id}
        agentRunId={record.agent_run_id}
        createdAt={record.created_at}
      />
    </article>
  );
}

function DetailHeader({
  tenantId,
  modelId,
  eyebrow,
  title,
  active,
}: {
  tenantId: number;
  modelId: number;
  eyebrow: string;
  title: string;
  active: boolean;
}) {
  return (
    <header className="workflow-detail-header">
      <div>
        <Link
          className="text-action"
          to="/tenants/$tenantId/models/$modelId/assertions"
          params={{ tenantId: String(tenantId), modelId: String(modelId) }}
        >
          ← Back to Assertions
        </Link>
        <p className="eyebrow">{eyebrow}</p>
        <h1>{title}</h1>
      </div>
      <span className={`status-badge ${active ? "is-success" : "is-neutral"}`}>
        {active ? "Active" : "Inactive"}
      </span>
    </header>
  );
}

function Provenance({
  workflowRunId,
  agentRunId,
  createdAt,
}: {
  workflowRunId: number | null;
  agentRunId: string | null;
  createdAt: string;
}) {
  return (
    <section className="detail-section" aria-labelledby="assertion-provenance-heading">
      <header><h2 id="assertion-provenance-heading">Provenance</h2></header>
      <dl className="detail-fact-grid">
        <Fact
          label="Workflow"
          value={workflowRunId === null ? "No workflow provenance" : `Workflow run ${workflowRunId}`}
        />
        <Fact label="Agent run" value={agentRunId ?? "Not recorded"} />
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

function Fact({ label, value }: { label: string; value: string }) {
  return <div><dt>{label}</dt><dd>{value}</dd></div>;
}

function humanize(value: string): string {
  return value.replaceAll("_", " ").replace(/^./, (character) => character.toLocaleUpperCase());
}
