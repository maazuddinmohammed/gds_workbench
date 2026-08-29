import { useEffect, useRef, type ReactNode } from "react";
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
          <div className="profile-evidence-list">
            {detail.attribute_profiles.map((profile) => (
              <AttributeProfileEvidence key={profile.attribute_id} profile={profile} />
            ))}
          </div>
        ) : (
          <p className="detail-empty">No Attribute profiles were returned.</p>
        )}
      </section>
    </article>
  );
}

function AttributeProfileEvidence({ profile }: { profile: AttributeProfile }) {
  return (
    <article className="profile-evidence-card" aria-labelledby={`profile-${profile.attribute_id}`}>
      <header>
        <div>
          <small>Attribute {profile.attribute_id}</small>
          <h3 id={`profile-${profile.attribute_id}`}>{profile.attribute_name}</h3>
        </div>
        <span>{profile.attribute_data_type}</span>
      </header>

      <ProfileFactGroup heading="Identity">
        <Fact label="Attribute ID" value={String(profile.attribute_id)} />
        <Fact label="Ordinal position" value={String(profile.attribute_ordinal_position)} />
        <Fact label="Data type" value={profile.attribute_data_type} />
      </ProfileFactGroup>

      <ProfileFactGroup heading="Counts">
        <Fact label="Rows" value={formatMetric(profile.row_count)} />
        <Fact label="Non-null rows" value={formatMetric(profile.non_null_count)} />
        <Fact label="Null rows" value={formatMetric(profile.null_count)} />
        <Fact label="Blank rows" value={formatMetric(profile.blank_count)} />
        <Fact label="Distinct values" value={formatMetric(profile.distinct_count)} />
      </ProfileFactGroup>

      <ProfileFactGroup heading="Data lengths">
        <Fact label="Minimum length" value={formatMetric(profile.min_data_length)} />
        <Fact label="Maximum length" value={formatMetric(profile.max_data_length)} />
        <Fact label="Average length" value={formatMetric(profile.avg_data_length)} />
      </ProfileFactGroup>

      <ProfileFactGroup heading="Percentages">
        <Fact label="Populated" value={formatPercent(profile.percent_populated)} />
        <Fact label="Duplicate rate" value={formatPercent(profile.percent_duplicates)} />
        <Fact label="Null rate" value={formatPercent(profile.percent_null)} />
        <Fact label="Blank rate" value={formatPercent(profile.percent_blank)} />
        <Fact label="Distinct rate" value={formatPercent(profile.percent_distinct)} />
      </ProfileFactGroup>

      <ProfileFactGroup heading="Provenance">
        <Fact
          label="Workflow run"
          value={profile.provenance.workflow_run_id === null
            ? "Not recorded"
            : `Run ${profile.provenance.workflow_run_id}`}
        />
        <Fact label="Agent run" value={profile.provenance.agent_run_id ?? "Not recorded"} />
        <Fact label="Created" value={formatDateTime(profile.created_at)} />
        <Fact label="Updated" value={formatDateTime(profile.updated_at)} />
        <Fact label="Source context digest" value={profile.source_context_digest} code />
      </ProfileFactGroup>
    </article>
  );
}

function ProfileFactGroup({
  heading,
  children,
}: {
  heading: string;
  children: ReactNode;
}) {
  return (
    <section className="profile-fact-group">
      <h4>{heading}</h4>
      <dl className="profile-fact-grid">{children}</dl>
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
