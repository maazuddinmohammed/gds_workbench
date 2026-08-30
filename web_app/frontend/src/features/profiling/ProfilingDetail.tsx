import { useEffect, useRef } from "react";
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
          <Fact label="Object ID" value={String(detail.object_id)} />
          <Fact label="Model ID" value={String(detail.model_id)} />
          <Fact label="Model revision" value={`r${detail.model_revision}`} />
          <Fact label="Object" value={`${detail.object_schema}.${detail.object_name}`} />
          <Fact
            label="Source Tenant"
            value={`${detail.source_tenant_name} (${detail.source_tenant_code})`}
          />
          <Fact label="Source Tenant ID" value={String(detail.source_tenant_id)} />
          <Fact label="System" value={`${detail.system_name} (${detail.system_code})`} />
          <Fact label="System ID" value={String(detail.system_id)} />
          <Fact label="Connection" value={detail.connection_code} />
          <Fact label="Connection ID" value={String(detail.connection_id)} />
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
                <tr className="profile-evidence-groups">
                  <th scope="col" rowSpan={2}>Attribute name</th>
                  <th scope="colgroup" colSpan={3}>Identity</th>
                  <th scope="colgroup" colSpan={5}>Counts</th>
                  <th scope="colgroup" colSpan={3}>Data lengths</th>
                  <th scope="colgroup" colSpan={5}>Percentages</th>
                  <th scope="colgroup" colSpan={5}>Provenance</th>
                </tr>
                <tr>
                  <th scope="col">Attribute ID</th>
                  <th scope="col">Ordinal position</th>
                  <th scope="col">Data type</th>
                  <th scope="col">Rows</th>
                  <th scope="col">Non-null rows</th>
                  <th scope="col">Null rows</th>
                  <th scope="col">Blank rows</th>
                  <th scope="col">Distinct values</th>
                  <th scope="col">Minimum length</th>
                  <th scope="col">Maximum length</th>
                  <th scope="col">Average length</th>
                  <th scope="col">Populated</th>
                  <th scope="col">Duplicate rate</th>
                  <th scope="col">Null rate</th>
                  <th scope="col">Blank rate</th>
                  <th scope="col">Distinct rate</th>
                  <th scope="col">Workflow run</th>
                  <th scope="col">Agent run</th>
                  <th scope="col">Created</th>
                  <th scope="col">Updated</th>
                  <th scope="col">Source context digest</th>
                </tr>
              </thead>
              <tbody>
                {detail.attribute_profiles.map((profile) => (
                  <AttributeProfileRow key={profile.attribute_id} profile={profile} />
                ))}
              </tbody>
            </table>
          </div>
        ) : (
          <p className="detail-empty">No Attribute profiles were returned.</p>
        )}
      </section>
    </article>
  );
}

function AttributeProfileRow({ profile }: { profile: AttributeProfile }) {
  return (
    <tr>
      <th scope="row" className="profile-evidence-name">{profile.attribute_name}</th>
      <td>{profile.attribute_id}</td>
      <td>{profile.attribute_ordinal_position}</td>
      <td className="profile-evidence-wrap">{profile.attribute_data_type}</td>
      <td>{formatMetric(profile.row_count)}</td>
      <td>{formatMetric(profile.non_null_count)}</td>
      <td>{formatMetric(profile.null_count)}</td>
      <td>{formatMetric(profile.blank_count)}</td>
      <td>{formatMetric(profile.distinct_count)}</td>
      <td>{formatMetric(profile.min_data_length)}</td>
      <td>{formatMetric(profile.max_data_length)}</td>
      <td>{formatMetric(profile.avg_data_length)}</td>
      <td>{formatPercent(profile.percent_populated)}</td>
      <td>{formatPercent(profile.percent_duplicates)}</td>
      <td>{formatPercent(profile.percent_null)}</td>
      <td>{formatPercent(profile.percent_blank)}</td>
      <td>{formatPercent(profile.percent_distinct)}</td>
      <td>
        {profile.provenance.workflow_run_id === null
          ? "Not recorded"
          : `Run ${profile.provenance.workflow_run_id}`}
      </td>
      <td className="profile-evidence-wrap">
        {profile.provenance.agent_run_id ?? "Not recorded"}
      </td>
      <td>{formatDateTime(profile.created_at)}</td>
      <td>{formatDateTime(profile.updated_at)}</td>
      <td className="profile-evidence-digest"><code>{profile.source_context_digest}</code></td>
    </tr>
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
