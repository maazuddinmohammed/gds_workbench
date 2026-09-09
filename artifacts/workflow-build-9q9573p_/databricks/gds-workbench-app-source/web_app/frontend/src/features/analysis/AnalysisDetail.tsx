import { useEffect, useRef } from "react";
import { Link } from "@tanstack/react-router";
import { useQuery } from "@tanstack/react-query";

import { formatRequiredDateTime as formatDateTime } from "../../shared/presentation";
import { analysisQueryKeys, type AnalysisApi, type AnalysisEndpoint } from "./api";

export function AnalysisDetail({
  api,
  tenantId,
  modelId,
  findingId,
}: {
  api: AnalysisApi;
  tenantId: number;
  modelId: number;
  findingId: number;
}) {
  const heading = useRef<HTMLHeadingElement>(null);
  const detailQuery = useQuery({
    queryKey: analysisQueryKeys.finding(tenantId, modelId, findingId),
    queryFn: () => api.readAnalysisFinding(tenantId, modelId, findingId),
  });

  useEffect(() => heading.current?.focus(), [detailQuery.data?.analysis_result_id]);

  if (detailQuery.isPending) {
    return <div className="surface-state detail-state" aria-busy="true">Loading finding details…</div>;
  }
  if (detailQuery.isError) {
    return (
      <div className="surface-state is-error detail-state" role="alert">
        Analysis finding details could not be loaded.
      </div>
    );
  }

  const finding = detailQuery.data;
  const from = finding.from_endpoint;
  const to = finding.to_endpoint;
  return (
    <article className="workflow-detail-page page-enter">
      <header className="workflow-detail-header">
        <div>
          <Link
            className="text-action"
            to="/tenants/$tenantId/models/$modelId/analysis"
            params={{ tenantId: String(tenantId), modelId: String(modelId) }}
          >
            ← Back to Analysis
          </Link>
          <p className="eyebrow">Relationship finding {finding.analysis_result_id}</p>
          <h1 ref={heading} tabIndex={-1}>{from.object_name}.{from.attribute_name} → {to.object_name}.{to.attribute_name}</h1>
        </div>
        <div className="detail-badge-stack">
          <span className="status-badge is-neutral">{finding.status === "active" ? "Active" : "Inactive"}</span>
          <span className={`status-badge ${finding.is_locked ? "is-warning" : "is-neutral"}`}>
            {finding.is_locked ? "Locked" : "Open"}
          </span>
          <span className={`status-badge ${finding.validation_result === "supported" ? "is-success" : finding.validation_result ? "is-warning" : "is-neutral"}`}>
            {finding.validation_result ?? "Not validated"}
          </span>
        </div>
      </header>

      <section className="detail-section detail-primary" aria-labelledby="analysis-basis-heading">
        <header>
          <h2 id="analysis-basis-heading">Relationship inference</h2>
          <span>{finding.relationship_kind.replaceAll("_", " ")} · {finding.relationship_confidence} confidence</span>
        </header>
        <p className="detail-prose is-prominent">{finding.relationship_basis}</p>
        {finding.relationship_basis_truncated ? (
          <p className="drawer-warning">The backend returned a safely bounded relationship basis.</p>
        ) : null}
      </section>

      <section className="detail-section" aria-labelledby="analysis-evidence-heading">
        <header><h2 id="analysis-evidence-heading">Recorded validation evidence</h2></header>
        {finding.observed_cardinality ? <p className="field-help">Observed cardinality: {finding.observed_cardinality.replaceAll("_", " ")}, based on recorded endpoint counts.</p> : null}
        {finding.evidence ? (
          <>
            <div className="table-scroll analysis-count-comparison">
              <table aria-label="Recorded endpoint counts">
                <thead><tr><th>Metric</th><th>Source (From)</th><th>Target (To)</th></tr></thead>
                <tbody>
                  <tr><th scope="row">Non-null values</th><td>{finding.evidence.source_non_null_count}</td><td>{finding.evidence.target_non_null_count}</td></tr>
                  <tr><th scope="row">Distinct values</th><td>{finding.evidence.source_distinct_count}</td><td>{finding.evidence.target_distinct_count}</td></tr>
                </tbody>
              </table>
            </div>
            <dl className="detail-fact-grid">
              <Fact label="Recorded result" value={finding.evidence.result} />
              <Fact label="Missing targets" value={`${finding.evidence.source_missing_target_count} missing targets`} />
              <Fact label="Unused targets" value={String(finding.evidence.unused_target_count)} />
              <Fact label="Duplicate target keys" value={String(finding.evidence.duplicate_target_key_count)} />
            </dl>
          </>
        ) : (
          <p className="detail-empty">No validation evidence is recorded for this finding.</p>
        )}
      </section>

      <details className="detail-section detail-disclosure" aria-labelledby="analysis-endpoints-heading">
        <summary><h2 id="analysis-endpoints-heading">Relationship endpoints</h2></summary>
        <div className="endpoint-comparison">
          <EndpointDetail label="From" endpoint={from} />
          <span aria-hidden="true">→</span>
          <EndpointDetail label="To" endpoint={to} />
        </div>
      </details>

      <details className="detail-section detail-disclosure" aria-labelledby="analysis-provenance-heading">
        <summary><h2 id="analysis-provenance-heading">Provenance</h2></summary>
        <dl className="detail-fact-grid">
          <Fact label="Inference run" value={nullableRun(finding.provenance.inference_workflow_run_id)} />
          <Fact label="Validation run" value={nullableRun(finding.provenance.validation_workflow_run_id)} />
          <Fact label="Agent run" value={finding.provenance.agent_run_id ?? "Not recorded"} />
          <Fact label="Created" value={formatDateTime(finding.created_at)} />
          <Fact label="Updated" value={formatDateTime(finding.updated_at)} />
          {finding.evidence ? <Fact label="Validation policy" value={`v${finding.evidence.validation_policy_version}`} /> : null}
        </dl>
        {finding.evidence ? (
          <details className="analysis-policy-details">
            <summary>Validation policy digest</summary>
            <code>{finding.evidence.validation_policy_digest}</code>
          </details>
        ) : null}
      </details>
    </article>
  );
}

function EndpointDetail({
  label,
  endpoint,
}: {
  label: string;
  endpoint: AnalysisEndpoint;
}) {
  return (
    <section>
      <small>{label}</small>
      <h3>{endpoint.object_name}</h3>
      <strong>{endpoint.attribute_name}</strong>
      <span>{endpoint.attribute_data_type}</span>
      <p>{endpoint.source_tenant_name} ({endpoint.source_tenant_code}) · {endpoint.system_name} ({endpoint.system_code})</p>
      <p>Connection: {endpoint.connection_code} · Schema: {endpoint.object_schema}</p>
    </section>
  );
}

function Fact({ label, value }: { label: string; value: string }) {
  return <div><dt>{label}</dt><dd>{value}</dd></div>;
}

function nullableRun(value: number | null): string {
  return value === null ? "Not recorded" : `Run ${value}`;
}
