import { useEffect, useRef } from "react";
import { Link } from "@tanstack/react-router";
import { useQuery } from "@tanstack/react-query";

import { formatRequiredDateTime } from "../../shared/presentation";
import {
  profilingQueryKeys,
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
          <p className="eyebrow">Profiled Object</p>
          <h1 ref={heading} tabIndex={-1}>{detail.object_name}</h1>
        </div>
        <span className="status-badge is-neutral">
          {detail.profiled_attribute_count} Attribute profiles
        </span>
      </header>

      <section className="detail-section detail-primary" aria-labelledby="profiled-object-description-heading">
        <header><h2 id="profiled-object-description-heading">Object description</h2></header>
        <p className="detail-prose is-prominent">{detail.object_description ?? "No description provided."}</p>
      </section>

      <section className="detail-section" aria-labelledby="attribute-profiles-heading">
        <header>
          <h2 id="attribute-profiles-heading">Attribute profiles</h2>
          <span>{returnedProfileCount} returned</span>
        </header>
        <p className="field-help">
          Populated means non-null, including blanks. Blank, distinct, and duplicate percentages
          use non-null rows. Lengths are measured in characters.
        </p>
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
                  <th scope="col" className="profile-evidence-number">Position</th>
                  <th scope="col">Data type</th>
                  <th scope="col">Inferred data type</th>
                  <th scope="col">Attribute description</th>
                  <th scope="col" className="profile-evidence-number">Total rows</th>
                  <th scope="col" className="profile-evidence-number">Non-null rows</th>
                  <th scope="col" className="profile-evidence-number">Null rows</th>
                  <th scope="col" className="profile-evidence-number">Blank rows</th>
                  <th scope="col" className="profile-evidence-number">Distinct values</th>
                  <th scope="col" className="profile-evidence-number">Populated (%)</th>
                  <th scope="col" className="profile-evidence-number">Null (%)</th>
                  <th scope="col" className="profile-evidence-number">Blank (%)</th>
                  <th scope="col" className="profile-evidence-number">Distinct (%)</th>
                  <th scope="col" className="profile-evidence-number">Duplicate (%)</th>
                  <th scope="col" className="profile-evidence-number">Minimum length</th>
                  <th scope="col" className="profile-evidence-number">Maximum length</th>
                  <th scope="col" className="profile-evidence-number">Average length</th>
                  <th scope="col">Last profiled</th>
                </tr>
              </thead>
              <tbody>
                {detail.attribute_profiles.map((profile) => (
                  <tr key={profile.attribute_id}>
                    <th scope="row" className="profile-evidence-name">{profile.attribute_name}</th>
                    <td className="profile-evidence-number">{profile.attribute_ordinal_position}</td>
                    <td className="profile-evidence-wrap">{profile.attribute_data_type}</td>
                    <td className="profile-evidence-wrap">{profile.attribute_inferred_data_type ?? "Not inferred"}</td>
                    <td className="profile-evidence-wrap">{profile.attribute_description ?? "No description"}</td>
                    <td className="profile-evidence-number">{formatMetric(profile.row_count)}</td>
                    <td className="profile-evidence-number">{formatMetric(profile.non_null_count)}</td>
                    <td className="profile-evidence-number">{formatMetric(profile.null_count)}</td>
                    <td className="profile-evidence-number">{formatMetric(profile.blank_count)}</td>
                    <td className="profile-evidence-number">{formatMetric(profile.distinct_count)}</td>
                    <td className="profile-evidence-number">{formatPercent(profile.percent_populated)}</td>
                    <td className="profile-evidence-number">{formatPercent(profile.percent_null)}</td>
                    <td className="profile-evidence-number">{formatPercent(profile.percent_blank)}</td>
                    <td className="profile-evidence-number">{formatPercent(profile.percent_distinct)}</td>
                    <td className="profile-evidence-number">{formatPercent(profile.percent_duplicates)}</td>
                    <td className="profile-evidence-number">{formatMetric(profile.min_data_length)}</td>
                    <td className="profile-evidence-number">{formatMetric(profile.max_data_length)}</td>
                    <td className="profile-evidence-number">{formatMetric(profile.avg_data_length)}</td>
                    <td><time dateTime={profile.updated_at}>{formatRequiredDateTime(profile.updated_at)}</time></td>
                  </tr>
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

function formatMetric(value: number | string | null): string {
  if (value === null) return "Not recorded";
  const parsed = Number(value);
  if (!Number.isFinite(parsed)) return String(value);
  return new Intl.NumberFormat(undefined, { maximumFractionDigits: 6 }).format(parsed);
}
