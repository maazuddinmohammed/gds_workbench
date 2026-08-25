import { Link } from "@tanstack/react-router";
import { useQuery } from "@tanstack/react-query";

import { formatRequiredDateTime as formatDateTime } from "../../shared/presentation";
import { analysisQueryKeys, type AnalysisApi } from "./api";

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
  const detailQuery = useQuery({
    queryKey: analysisQueryKeys.finding(tenantId, modelId, findingId),
    queryFn: () => api.readAnalysisFinding(tenantId, modelId, findingId),
  });

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
          <h1>{from.object_name}.{from.attribute_name} → {to.object_name}.{to.attribute_name}</h1>
        </div>
        <div className="detail-badge-stack">
          <span className={`status-badge ${finding.is_locked ? "is-warning" : "is-neutral"}`}>
            {finding.is_locked ? "Locked" : "Open"}
          </span>
          <span className={`status-badge ${finding.validation_result === "supported" ? "is-success" : "is-warning"}`}>
            {finding.validation_result ?? "Pending"}
          </span>
        </div>
      </header>

      <section className="detail-section" aria-labelledby="analysis-endpoints-heading">
        <header><h2 id="analysis-endpoints-heading">Relationship endpoints</h2></header>
        <div className="endpoint-comparison">
          <EndpointDetail label="From" endpoint={from} />
          <span aria-hidden="true">→</span>
          <EndpointDetail label="To" endpoint={to} />
        </div>
      </section>

      <section className="detail-section" aria-labelledby="analysis-basis-heading">
        <header>
          <h2 id="analysis-basis-heading">Relationship basis</h2>
          <span>{finding.relationship_kind.replaceAll("_", " ")} · {finding.relationship_confidence}</span>
        </header>
        <p className="detail-prose">{finding.relationship_basis}</p>
        {finding.relationship_basis_truncated ? (
          <p className="drawer-warning">The backend returned a safely bounded relationship basis.</p>
        ) : null}
      </section>

      <section className="detail-section" aria-labelledby="analysis-evidence-heading">
        <header><h2 id="analysis-evidence-heading">Validation evidence</h2></header>
        {finding.evidence ? (
          <dl className="detail-fact-grid">
            <Fact label="Policy" value={`v${finding.evidence.validation_policy_version}`} />
            <Fact label="Source non-null" value={String(finding.evidence.source_non_null_count)} />
            <Fact label="Source distinct" value={String(finding.evidence.source_distinct_count)} />
            <Fact label="Target non-null" value={String(finding.evidence.target_non_null_count)} />
            <Fact label="Target distinct" value={String(finding.evidence.target_distinct_count)} />
            <Fact label="Missing targets" value={`${finding.evidence.source_missing_target_count} missing targets`} />
            <Fact label="Unused targets" value={String(finding.evidence.unused_target_count)} />
            <Fact label="Duplicate keys" value={String(finding.evidence.duplicate_target_key_count)} />
          </dl>
        ) : (
          <p className="detail-empty">Validation has not run for this finding.</p>
        )}
      </section>

      <section className="detail-section" aria-labelledby="analysis-provenance-heading">
        <header><h2 id="analysis-provenance-heading">Provenance</h2></header>
        <dl className="detail-fact-grid">
          <Fact label="Inference run" value={nullableRun(finding.provenance.inference_workflow_run_id)} />
          <Fact label="Validation run" value={nullableRun(finding.provenance.validation_workflow_run_id)} />
          <Fact label="Agent run" value={finding.provenance.agent_run_id ?? "Not recorded"} />
          <Fact label="Created" value={formatDateTime(finding.created_at)} />
          <Fact label="Updated" value={formatDateTime(finding.updated_at)} />
        </dl>
      </section>
    </article>
  );
}

function EndpointDetail({
  label,
  endpoint,
}: {
  label: string;
  endpoint: {
    object_schema: string;
    object_name: string;
    attribute_name: string;
    attribute_data_type: string;
    system_code: string;
    source_tenant_code: string;
  };
}) {
  return (
    <section>
      <small>{label}</small>
      <h3>{endpoint.object_name}</h3>
      <strong>{endpoint.attribute_name}</strong>
      <span>{endpoint.attribute_data_type}</span>
      <p>{endpoint.source_tenant_code} · {endpoint.system_code} · {endpoint.object_schema}</p>
    </section>
  );
}

function Fact({ label, value }: { label: string; value: string }) {
  return <div><dt>{label}</dt><dd>{value}</dd></div>;
}

function nullableRun(value: number | null): string {
  return value === null ? "Not recorded" : `Run ${value}`;
}
