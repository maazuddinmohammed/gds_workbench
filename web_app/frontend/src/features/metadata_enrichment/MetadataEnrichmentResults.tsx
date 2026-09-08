import { useState } from "react";
import { useQuery } from "@tanstack/react-query";

import { enrichmentResultKey, type EnrichmentEvidence, type EnrichmentField,
  type EnrichmentStatus, type MetadataEnrichmentTransport } from "./api";

const FIELD_NAMES: Record<EnrichmentField, string> = {
  object_description: "Object description",
  attribute_description: "Attribute description",
  attribute_inferred_data_type: "Inferred type",
};
const STATUS_NAMES: Record<EnrichmentStatus, string> = {
  applied: "Filled", existing: "Preserved", locked: "Locked", inactive: "Inactive",
  changed: "Changed since run started", unavailable: "Evidence unavailable", inconclusive: "Inconclusive",
};
const EVIDENCE_NAMES: Record<EnrichmentEvidence, string> = {
  agent_description: "Agent description", source_comment: "Source comment",
  registered_type: "Registered metadata type", source_schema: "Source schema",
  bronze_schema: "Bronze schema", source_sample: "Source samples", bronze_sample: "Bronze samples",
  none: "No evidence used",
};

export function MetadataEnrichmentResults({ api, tenantId, modelId, runId }: {
  api: Pick<MetadataEnrichmentTransport, "readMetadataEnrichmentResults">; tenantId: number; modelId: number; runId: number;
}) {
  const [offset, setOffset] = useState(0);
  const query = useQuery({
    queryKey: [...enrichmentResultKey(tenantId, modelId, runId), offset],
    queryFn: () => api.readMetadataEnrichmentResults(tenantId, modelId, runId, 100, offset),
  });
  if (query.isPending) return <p aria-busy="true">Loading enrichment results…</p>;
  const page = query.data;
  if (query.isError || !page || page.tenant_id !== tenantId || page.model_id !== modelId
    || page.workflow_run_id !== runId || page.offset !== offset
    || !["completed", "completed_with_repair"].includes(page.workflow_run_state)) {
    return <p className="inline-error" role="alert">Enrichment results could not be loaded. Use Refresh runs to try again.</p>;
  }
  const filled = page.counts.applied ?? 0;
  const unresolved = (page.counts.unavailable ?? 0) + (page.counts.inconclusive ?? 0);
  return (
    <section className="enrichment-results" aria-label="Metadata enrichment results" aria-busy={query.isFetching}>
      <h3>{filled ? `${filled} missing fields filled` : "No missing values filled"}</h3>
      <dl className="enrichment-totals" aria-label="Fields filled across this run">
        <div><dt>Object descriptions</dt><dd>{page.applied_field_counts.object_description}</dd></div>
        <div><dt>Attribute descriptions</dt><dd>{page.applied_field_counts.attribute_description}</dd></div>
        <div><dt>Inferred types</dt><dd>{page.applied_field_counts.attribute_inferred_data_type}</dd></div>
      </dl>
      <p>{page.counts.existing ?? 0} preserved · {page.counts.locked ?? 0} locked · {unresolved} unresolved</p>
      {unresolved > 0 ? <p className="inline-warning">Unresolved fields remain empty because evidence was unavailable or inconclusive.</p> : null}
      {(page.counts.changed ?? 0) > 0 ? <p className="inline-warning">{page.counts.changed} fields were skipped because physical metadata changed during the run.</p> : null}
      {(page.counts.inactive ?? 0) > 0 ? <p>{page.counts.inactive} inactive fields skipped.</p> : null}
      <p className="enrichment-history-note">Saved values from Run {runId} · Model revision {page.model_revision}. Names and storage types reflect current metadata.</p>
      {page.total_count > 0 ? <>
        <div className="enrichment-table-scroll" tabIndex={0} role="region" aria-label="Scrollable enrichment results">
          <table className="enrichment-result-table" aria-label="Enrichment field results">
            <thead><tr><th scope="col">Record</th><th scope="col">Field</th><th scope="col">Outcome</th><th scope="col">Value and evidence</th></tr></thead>
            <tbody>{page.results.map((result) => (
              <tr key={result.result_id}>
                <th scope="row">
                  <strong>{result.object_name ? [result.object_schema, result.object_name].filter(Boolean).join(".") : `Object ${result.object_id}`}</strong>
                  {result.attribute_id !== null ? <span>{result.attribute_name ?? `Attribute ${result.attribute_id}`}</span> : null}
                </th>
                <td>{FIELD_NAMES[result.field_name]}</td>
                <td>{STATUS_NAMES[result.status]}</td>
                <td><details>
                  <summary>Inspect {FIELD_NAMES[result.field_name].toLowerCase()}</summary>
                  <dl>
                    {result.applied_value !== null ? <div><dt>{result.field_name === "attribute_inferred_data_type" ? "Inferred type filled by this run" : "Description filled by this run"}</dt><dd className="enrichment-value">{result.applied_value}</dd></div> : <div><dt>Value filled by this run</dt><dd>None — {STATUS_NAMES[result.status].toLowerCase()}</dd></div>}
                    {result.attribute_id !== null ? <div><dt>Current storage type</dt><dd>{result.storage_type ?? "Unavailable"}</dd></div> : null}
                    <div><dt>Evidence</dt><dd>{EVIDENCE_NAMES[result.evidence_method]}{result.sample_count > 0 ? ` · ${result.sample_count} samples` : ""}</dd></div>
                    <div><dt>Record reference</dt><dd>Object {result.object_id}{result.attribute_id !== null ? ` · Attribute ${result.attribute_id}` : ""}</dd></div>
                  </dl>
                </details></td>
              </tr>
            ))}</tbody>
          </table>
        </div>
        <nav className="enrichment-pagination" aria-label="Enrichment result pages">
          <span>{offset + 1}–{offset + page.results.length} of {page.total_count} fields</span>
          <button className="button button-secondary button-small" disabled={offset === 0 || query.isFetching} onClick={() => setOffset(Math.max(0, offset - 100))}>Previous results</button>
          <button className="button button-secondary button-small" disabled={page.next_offset === null || query.isFetching} onClick={() => { if (page.next_offset !== null) setOffset(page.next_offset); }}>Next results</button>
        </nav>
      </> : null}
    </section>
  );
}
