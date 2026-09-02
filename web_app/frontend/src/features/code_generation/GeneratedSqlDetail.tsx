import { useEffect, useRef, useState } from "react";
import { useQuery, useQueryClient } from "@tanstack/react-query";
import { Link } from "@tanstack/react-router";

import { ApiError } from "../../core/http";
import { formatRequiredDateTime as formatDateTime } from "../../shared/presentation";
import type { ModelDetail } from "../models/api";
import {
  codeGenerationQueryKeys,
  generatedSqlArtifactDownloadPath,
  type CodeGenerationApi,
  type CodeGenerationTarget,
  type GeneratedSqlArtifactDetail,
} from "./api";
import { CodeGenerationRunDialog } from "./CodeGenerationRunDialog";

export function GeneratedSqlDetailPage({
  api,
  tenantId,
  model,
  artifactId,
  hasTenantLock,
  hasAppPermission,
}: {
  api: CodeGenerationApi;
  tenantId: number;
  model: ModelDetail;
  artifactId: number;
  hasTenantLock: boolean;
  hasAppPermission: boolean;
}) {
  const queryClient = useQueryClient();
  const [runDialogOpen, setRunDialogOpen] = useState(false);
  const [startedRunId, setStartedRunId] = useState<number | null>(null);
  const query = useQuery({
    queryKey: codeGenerationQueryKeys.artifact(tenantId, model.model_id, artifactId),
    queryFn: () => api.readGeneratedSqlArtifact(tenantId, model.model_id, artifactId),
  });
  if (query.isPending) return <DetailState label="Loading stored SQL…" />;
  if (query.isError) return <DetailState label={detailError(query.error)} error />;
  const canGenerate = hasTenantLock && hasAppPermission;
  const permissionLabel = !hasAppPermission
    ? "Architect permission required to regenerate SQL"
    : !hasTenantLock
      ? "Tenant Lock required to regenerate SQL"
      : "Tenant Lock held · ready to regenerate";
  return (
    <>
      <GeneratedSqlDetailView
        tenantId={tenantId}
        model={model}
        detail={query.data}
        canGenerate={canGenerate}
        permissionLabel={permissionLabel}
        startedRunId={startedRunId}
        onRegenerate={() => setRunDialogOpen(true)}
      />
      {runDialogOpen ? (
        <CodeGenerationRunDialog
          api={api}
          tenantId={tenantId}
          model={model}
          entityType={query.data.entity_type}
          coverage="selected_targets"
          selectedTargets={[targetFromArtifact(query.data)]}
          onClose={() => setRunDialogOpen(false)}
          onStarted={async (workflowRunId) => {
            setStartedRunId(workflowRunId);
            await Promise.all([
              queryClient.invalidateQueries({
                queryKey: ["code-generation-targets", tenantId, model.model_id],
              }),
              queryClient.invalidateQueries({
                queryKey: codeGenerationQueryKeys.artifact(tenantId, model.model_id, artifactId),
              }),
            ]);
          }}
        />
      ) : null}
    </>
  );
}

function GeneratedSqlDetailView({
  tenantId,
  model,
  detail,
  canGenerate,
  permissionLabel,
  startedRunId,
  onRegenerate,
}: {
  tenantId: number;
  model: ModelDetail;
  detail: GeneratedSqlArtifactDetail;
  canGenerate: boolean;
  permissionLabel: string;
  startedRunId: number | null;
  onRegenerate: () => void;
}) {
  const heading = useRef<HTMLHeadingElement>(null);
  useEffect(() => heading.current?.focus(), []);
  const title = `${detail.target.object_schema}.${detail.target.object_name}`;
  const downloadPath = generatedSqlArtifactDownloadPath(
    tenantId,
    model.model_id,
    detail.generated_sql_artifact_id,
  );
  return (
    <article className="workflow-detail-page code-generation-detail-page page-enter">
      <header className="workflow-detail-header code-generation-detail-header">
        <div>
          <Link
            className="text-action"
            aria-label="Back to Code Generation"
            to="/tenants/$tenantId/code-generation/models/$modelId"
            params={{ tenantId: String(tenantId), modelId: String(model.model_id) }}
          >
            ← Back to Code Generation
          </Link>
          <p className="eyebrow">Stored SQL artifact {detail.generated_sql_artifact_id}</p>
          <h1 ref={heading} tabIndex={-1}>{detail.artifact_name}</h1>
          <p>{title}</p>
        </div>
        <div className="code-generation-detail-actions">
          <div className="detail-badge-stack">
            <span className={`status-badge ${detail.artifact_is_current ? "is-success" : "is-stale"}`}>
              {detail.artifact_is_current ? "Current" : "Stale"}
            </span>
            <span className="status-badge is-neutral">{layerLabel(detail.entity_type)}</span>
          </div>
          <div>
            <a className="button button-secondary button-small" href={downloadPath}>Download .sql</a>
            <button
              className="button button-primary button-small"
              type="button"
              disabled={!canGenerate}
              title={permissionLabel}
              onClick={onRegenerate}
            >
              Regenerate SQL
            </button>
          </div>
        </div>
      </header>
      {startedRunId ? (
        <p className="code-generation-run-notice" role="status">
          Code Generation run {startedRunId} started. The applied artifact remains unchanged until its validated draft is reviewed and applied.
        </p>
      ) : null}

      <section className="detail-section" aria-labelledby="generated-sql-target-heading">
        <header><h2 id="generated-sql-target-heading">Target Object</h2></header>
        <dl className="detail-fact-grid">
          <Fact label="Object" value={title} />
          <Fact label="Object ID" value={String(detail.target.object_id)} />
          <Fact label="Target Tenant" value={`${detail.target.tenant_name} (${detail.target.tenant_code})`} />
          <Fact label="Target System" value={`${detail.target.system_name} (${detail.target.system_code})`} />
          <Fact label="Zone" value={detail.target.zone_code} />
          <Fact label="Modeled layer" value={layerLabel(detail.entity_type)} />
          <Fact label="Artifact status" value={humanize(detail.generated_code_status)} />
        </dl>
      </section>

      <section className="detail-section" aria-labelledby="generated-sql-systems-heading">
        <header>
          <h2 id="generated-sql-systems-heading">Contributing source Systems</h2>
          <span>{detail.source_system_count} System{detail.source_system_count === 1 ? "" : "s"}</span>
        </header>
        {detail.source_systems.length ? (
          <ul className="code-generation-system-ledger">
            {detail.source_systems.map((system) => (
              <li key={system.system_id}>
                <strong>{system.system_name}</strong>
                <span>{system.system_code} · System {system.system_id}</span>
              </li>
            ))}
          </ul>
        ) : (
          <p className="detail-empty-note">Current contributing Systems are unavailable for this stale artifact.</p>
        )}
      </section>

      <section className="detail-section" aria-labelledby="generated-sql-mapping-heading">
        <header>
          <h2 id="generated-sql-mapping-heading">Applied Mapping provenance</h2>
          <span>{detail.mapping_support_count} support{detail.mapping_support_count === 1 ? "" : "s"}</span>
        </header>
        {detail.mapping_supports.length ? (
          <div className="table-scroll code-generation-support-scroll">
            <table aria-label="Applied Mapping supports">
              <thead>
                <tr>
                  <th>Mapping</th>
                  <th>Modeled source</th>
                  <th>Source System</th>
                  <th>Dependency order</th>
                </tr>
              </thead>
              <tbody>
                {detail.mapping_supports.map((support) => (
                  <tr key={support.mapping_object_id}>
                    <td>Object Mapping {support.mapping_object_id}</td>
                    <td>
                      <span className="endpoint-cell">
                        <strong>{support.source.entity_name}</strong>
                        <span>{layerLabel(support.source.entity_type)} Entity {support.source.entity_id}</span>
                      </span>
                    </td>
                    <td>{support.source_system.system_name} ({support.source_system.system_code})</td>
                    <td>{support.dependency_order}</td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        ) : (
          <p className="detail-empty-note">Current Mapping support is unavailable for this stale artifact.</p>
        )}
        {detail.mapping_supports_truncated ? (
          <p className="bounded-more-note">
            Showing {detail.mapping_supports.length} of {detail.mapping_support_count} Mapping supports.
          </p>
        ) : null}
      </section>

      <section className="detail-section" aria-labelledby="generated-sql-provenance-heading">
        <header><h2 id="generated-sql-provenance-heading">Generation provenance</h2></header>
        <dl className="detail-fact-grid code-generation-provenance-grid">
          {detail.guide ? (
            <>
              <Fact
                label="SQL guide"
                value={`${detail.guide.sql_generation_guide_name} (${detail.guide.sql_generation_guide_code})`}
              />
              <Fact
                label="Guide version"
                value={`v${detail.guide.sql_generation_guide_version_number} · ${humanize(detail.guide.sql_generation_guide_version_status)} · ${detail.guide.guide_is_active ? "Guide active" : "Guide inactive"}`}
              />
              <DigestFact label="Guide digest" value={detail.guide.sql_generation_guide_digest} />
            </>
          ) : (
            <Fact label="SQL guide" value="No legacy guide provenance" />
          )}
          {detail.generator ? (
            <>
              <Fact
                label="Generator"
                value={`${detail.generator.generator_code}@${detail.generator.generator_version}`}
              />
              <Fact label="Generated by" value={detail.generator.generated_by_display_name} />
            </>
          ) : (
            <Fact label="Generator" value="No legacy generator provenance" />
          )}
          <Fact
            label="Workflow"
            value={detail.workflow_run_id === null ? "No workflow provenance" : `Workflow run ${detail.workflow_run_id}`}
          />
          <Fact label="Generated" value={formatDateTime(detail.generated_at)} />
          <Fact label="SQL size" value={`${detail.generated_sql_byte_count.toLocaleString()} bytes`} />
        </dl>
      </section>

      <section className="detail-section generated-sql-section" aria-labelledby="stored-sql-heading">
        <header>
          <h2 id="stored-sql-heading">Stored SQL</h2>
          <span>Read-only · rendered as literal text</span>
        </header>
        <pre tabIndex={0} aria-label={`Stored SQL for ${title}`}><code>{detail.generated_sql}</code></pre>
      </section>
    </article>
  );
}

function Fact({ label, value }: { label: string; value: string }) {
  return <div><dt>{label}</dt><dd>{value}</dd></div>;
}

function DigestFact({ label, value }: { label: string; value: string }) {
  return <div className="digest-fact"><dt>{label}</dt><dd><code>{value}</code></dd></div>;
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

function detailError(error: Error): string {
  return error instanceof ApiError && error.status === 403
    ? "You do not have permission to view this stored SQL artifact."
    : "Stored SQL artifact could not be loaded.";
}

function layerLabel(entityType: string): string {
  return entityType === "logical_entity" ? "Logical" : "Dimensional";
}

function humanize(value: string): string {
  return value.replaceAll("_", " ").replace(/^./, (character) => character.toLocaleUpperCase());
}

function targetFromArtifact(detail: GeneratedSqlArtifactDetail): CodeGenerationTarget {
  return {
    target: detail.target,
    entity_type: detail.entity_type,
    mapping_supports: detail.mapping_supports,
    mapping_support_count: detail.mapping_support_count,
    mapping_supports_truncated: detail.mapping_supports_truncated,
    source_systems: detail.source_systems,
    source_system_count: detail.source_system_count,
    artifacts: [{
      generated_sql_artifact_id: detail.generated_sql_artifact_id,
      artifact_name: detail.artifact_name,
      workflow_run_id: detail.workflow_run_id,
      generated_at: detail.generated_at,
      generated_code_status: detail.generated_code_status,
      source_system_codes: detail.source_systems.map((system) => system.system_code),
      artifact_is_current: detail.artifact_is_current,
    }],
    artifact_count: 1,
  };
}
