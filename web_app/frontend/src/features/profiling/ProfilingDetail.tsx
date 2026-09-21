import { useEffect, useRef } from "react";
import { Link } from "@tanstack/react-router";
import { useQuery } from "@tanstack/react-query";

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
                  <th scope="col">Inferred data type</th>
                  <th scope="col">Attribute description</th>
                  <th scope="col">Number of rows</th>
                  <th scope="col">Unique distinct rows</th>
                  <th scope="col">Duplicate percentage</th>
                </tr>
              </thead>
              <tbody>
                {detail.attribute_profiles.map((profile) => (
                  <tr key={profile.attribute_id}>
                    <th scope="row" className="profile-evidence-name">{profile.attribute_name}</th>
                    <td className="profile-evidence-wrap">{profile.attribute_inferred_data_type ?? "Not inferred"}</td>
                    <td className="profile-evidence-wrap">{profile.attribute_description ?? "No description"}</td>
                    <td>{formatMetric(profile.row_count)}</td>
                    <td>{formatMetric(profile.distinct_count)}</td>
                    <td>{formatPercent(profile.percent_duplicates)}</td>
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
