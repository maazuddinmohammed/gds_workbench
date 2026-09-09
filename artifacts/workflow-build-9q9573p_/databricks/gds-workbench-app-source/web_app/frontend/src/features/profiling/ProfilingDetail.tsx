import { useEffect, useRef, useState } from "react";
import { Link } from "@tanstack/react-router";
import { useQuery } from "@tanstack/react-query";

import { formatRequiredDateTime as formatDateTime } from "../../shared/presentation";
import {
  profilingQueryKeys,
  type AttributeProfile,
  type ProfilingApi,
  type ProfilingRouteSearch,
} from "./api";
import { formatPercent } from "./shared";

export function ProfilingObjectDetailPage({
  api,
  tenantId,
  modelId,
  objectId,
  returnSearch,
}: {
  api: ProfilingApi;
  tenantId: number;
  modelId: number;
  objectId: number;
  returnSearch: ProfilingRouteSearch;
}) {
  const heading = useRef<HTMLHeadingElement>(null);
  const reviewButton = useRef<HTMLButtonElement | null>(null);
  const [selectedAttributeId, setSelectedAttributeId] = useState<number | null>(null);
  const detailQuery = useQuery({
    queryKey: profilingQueryKeys.result(tenantId, modelId, objectId),
    queryFn: () => api.readProfilingObject(tenantId, modelId, objectId),
  });

  useEffect(() => {
    if (detailQuery.isSuccess) heading.current?.focus();
  }, [detailQuery.isSuccess]);

  if (detailQuery.isPending) {
    return (
      <div className="surface-state detail-state" aria-busy="true">
        Loading profile evidence…
      </div>
    );
  }
  if (detailQuery.isError) {
    return (
      <div className="surface-state is-error detail-state" role="alert">
        Profile evidence could not be loaded.
      </div>
    );
  }

  const detail = detailQuery.data;
  const returnedProfileCount = detail.attribute_profiles.length;
  const selectedProfile = detail.attribute_profiles.find((profile) => profile.attribute_id === selectedAttributeId);
  function closeProfile() {
    setSelectedAttributeId(null);
    reviewButton.current?.focus();
  }
  return (
    <article className="workflow-detail-page profiling-detail-page page-enter">
      <header className="workflow-detail-header">
        <div>
          <Link
            className="text-action"
            aria-label="Back to Profiling"
            to="/tenants/$tenantId/models/$modelId/profiling"
            params={{ tenantId: String(tenantId), modelId: String(modelId) }}
            search={returnSearch}
          >
            ← Back to Profiling
          </Link>
          <p className="eyebrow">Profile evidence · Object {detail.object_id}</p>
          <h1 ref={heading} tabIndex={-1}>{detail.object_name}</h1>
        </div>
        <span className="status-badge is-neutral">
          {detail.profiled_attribute_count} Attribute profiles
        </span>
      </header>

      <section className="detail-section" aria-labelledby="profiled-object-context-heading">
        <header><h2 id="profiled-object-context-heading">Profiled Object context</h2></header>
        <dl className="detail-fact-grid profiling-object-facts">
          <Fact label="Model revision" value={`r${detail.model_revision}`} />
          <Fact label="Object" value={`${detail.object_schema}.${detail.object_name}`} />
          <Fact
            label="Source Tenant"
            value={`${detail.source_tenant_name} (${detail.source_tenant_code})`}
          />
          <Fact label="System" value={`${detail.system_name} (${detail.system_code})`} />
          <Fact label="Connection" value={detail.connection_code} />
          <Fact label="Profiles returned" value={String(returnedProfileCount)} />
          <Fact label="Last profiled" value={formatDateTime(detail.last_profiled_at)} />
        </dl>
      </section>

      <section className="detail-section" aria-labelledby="attribute-profiles-heading">
        <header>
          <h2 id="attribute-profiles-heading">Attribute profiles</h2>
          <span>{returnedProfileCount} returned</span>
        </header>
        {detail.profiles_truncated ? (
          <p className="drawer-warning">
            This response contains {returnedProfileCount} of {detail.profiled_attribute_count}
            {" "}Attribute profiles.
          </p>
        ) : null}
        {returnedProfileCount ? (
          <div
            className="profile-evidence-table-scroll table-scroll"
            role="region"
            aria-label="Scrollable Attribute profile metrics"
            tabIndex={0}
          >
            <table className="profile-evidence-table">
              <caption className="sr-only">Attribute profiles</caption>
              <thead>
                <tr>
                  <th scope="col">Attribute</th>
                  <th scope="col">Catalog type</th>
                  <th scope="col">Rows</th>
                  <th scope="col">Populated</th>
                  <th scope="col">Distinct</th>
                  <th scope="col">Duplicates</th>
                  <th scope="col">Null</th>
                  <th scope="col">Blank</th>
                  <th scope="col">Review</th>
                </tr>
              </thead>
              <tbody>
                {detail.attribute_profiles.map((profile) => (
                  <AttributeProfileRow
                    key={profile.attribute_id}
                    profile={profile}
                    selected={selectedAttributeId === profile.attribute_id}
                    onReview={(button) => {
                      reviewButton.current = button;
                      setSelectedAttributeId(profile.attribute_id);
                    }}
                  />
                ))}
              </tbody>
            </table>
          </div>
        ) : (
          <p className="detail-empty">No Attribute profiles were returned.</p>
        )}
      </section>
      {selectedProfile ? <AttributeProfileInspector profile={selectedProfile} onClose={closeProfile} /> : null}
      <details className="profile-record-details">
        <summary>Object record details</summary>
        <dl className="detail-fact-grid">
          <Fact label="Object ID" value={String(detail.object_id)} />
          <Fact label="Model ID" value={String(detail.model_id)} />
          <Fact label="Source Tenant ID" value={String(detail.source_tenant_id)} />
          <Fact label="System ID" value={String(detail.system_id)} />
          <Fact label="Connection ID" value={String(detail.connection_id)} />
        </dl>
      </details>
    </article>
  );
}

function AttributeProfileRow({ profile, selected, onReview }: {
  profile: AttributeProfile;
  selected: boolean;
  onReview: (button: HTMLButtonElement) => void;
}) {
  return (
    <tr className={selected ? "is-active" : undefined}>
      <th scope="row" className="profile-evidence-name">{profile.attribute_name}</th>
      <td className="profile-evidence-wrap">{profile.attribute_data_type}</td>
      <td>{formatMetric(profile.row_count)}</td>
      <td>{formatPercent(profile.percent_populated)}</td>
      <td>{formatPercent(profile.percent_distinct)}</td>
      <td>{formatPercent(profile.percent_duplicates)}</td>
      <td>{formatPercent(profile.percent_null)}</td>
      <td>{formatPercent(profile.percent_blank)}</td>
      <td className="profile-evidence-actions">
        <button type="button" className="text-action" aria-label={`Review ${profile.attribute_name}`}
          aria-expanded={selected} aria-controls="attribute-profile-inspector"
          onClick={(event) => onReview(event.currentTarget)}>Review</button>
      </td>
    </tr>
  );
}

function AttributeProfileInspector({ profile, onClose }: { profile: AttributeProfile; onClose: () => void }) {
  const heading = useRef<HTMLHeadingElement>(null);
  useEffect(() => heading.current?.focus(), [profile.attribute_id]);
  return (
    <section className="detail-section profile-inspector" id="attribute-profile-inspector"
      aria-labelledby="attribute-profile-inspector-heading"
      onKeyDown={(event) => { if (event.key === "Escape") { event.preventDefault(); onClose(); } }}>
      <header>
        <h2 id="attribute-profile-inspector-heading" ref={heading} tabIndex={-1}>{profile.attribute_name}</h2>
        <button type="button" className="text-action" onClick={onClose} aria-label="Close Attribute profile">Close</button>
      </header>
      <dl className="detail-fact-grid">
        <Fact label="Catalog type" value={profile.attribute_data_type} />
        <Fact label="Ordinal position" value={String(profile.attribute_ordinal_position)} />
        <Fact label="Attribute ID" value={String(profile.attribute_id)} />
      </dl>
      <h3>Recorded counts and lengths</h3>
      <dl className="detail-fact-grid">
        <Fact label="Rows" value={formatMetric(profile.row_count)} />
        <Fact label="Non-null rows" value={formatMetric(profile.non_null_count)} />
        <Fact label="Null rows" value={formatMetric(profile.null_count)} />
        <Fact label="Blank rows" value={formatMetric(profile.blank_count)} />
        <Fact label="Distinct values" value={formatMetric(profile.distinct_count)} />
        <Fact label="Minimum length" value={formatMetric(profile.min_data_length)} />
        <Fact label="Maximum length" value={formatMetric(profile.max_data_length)} />
        <Fact label="Average length" value={formatMetric(profile.avg_data_length)} />
      </dl>
      <h3>Recorded percentages</h3>
      <dl className="detail-fact-grid">
        <Fact label="Populated" value={formatPercent(profile.percent_populated)} />
        <Fact label="Distinct" value={formatPercent(profile.percent_distinct)} />
        <Fact label="Duplicates" value={formatPercent(profile.percent_duplicates)} />
        <Fact label="Null" value={formatPercent(profile.percent_null)} />
        <Fact label="Blank" value={formatPercent(profile.percent_blank)} />
      </dl>
      <h3>Provenance</h3>
      <dl className="detail-fact-grid">
        <Fact label="Workflow run" value={profile.provenance.workflow_run_id === null ? "Not recorded" : `Run ${profile.provenance.workflow_run_id}`} />
        <Fact label="Agent run" value={profile.provenance.agent_run_id ?? "Not recorded"} />
        <Fact label="Created" value={formatDateTime(profile.created_at)} />
        <Fact label="Updated" value={formatDateTime(profile.updated_at)} />
        <Fact label="Source context digest" value={profile.source_context_digest} code />
      </dl>
    </section>
  );
}

function Fact({
  label,
  value,
  code = false,
}: {
  label: string;
  value: string;
  code?: boolean;
}) {
  return (
    <div>
      <dt>{label}</dt>
      <dd>{code ? <code>{value}</code> : value}</dd>
    </div>
  );
}

function formatMetric(value: number | string | null): string {
  if (value === null) return "Not recorded";
  const parsed = Number(value);
  if (!Number.isFinite(parsed)) return String(value);
  return new Intl.NumberFormat(undefined, { maximumFractionDigits: 6 }).format(parsed);
}
