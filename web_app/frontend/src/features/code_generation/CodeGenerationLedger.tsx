import { useMemo } from "react";
import { useForm } from "@tanstack/react-form";
import { Link } from "@tanstack/react-router";
import {
  flexRender,
  getCoreRowModel,
  useReactTable,
  type ColumnDef,
} from "@tanstack/react-table";

import { formatRequiredDateTime as formatDateTime } from "../../shared/presentation";
import type { MappingEntityType } from "../mapping/api";
import type { CodeGenerationTarget, CodeGenerationTargetFilters } from "./api";

export type ArtifactStatusFilter = "" | "current" | "stale" | "not_generated";

export interface CodeGenerationLedgerState {
  isLoading: boolean;
  isError: boolean;
  isDenied: boolean;
  revisionMismatch: boolean;
  hasNextPage: boolean;
  hasPreviousPage: boolean;
  isPaging: boolean;
  pageNumber: number;
}

export function CodeGenerationLedger({
  tenantId,
  modelId,
  items,
  filters,
  artifactStatus,
  selectedTargetIds,
  canGenerate,
  permissionLabel,
  state,
  onApplyFilters,
  onArtifactStatusChange,
  onToggleTarget,
  onToggleVisible,
  onGenerateTarget,
  onNextPage,
  onPreviousPage,
}: {
  tenantId: number;
  modelId: number;
  items: CodeGenerationTarget[];
  filters: CodeGenerationTargetFilters & { entityType: MappingEntityType };
  artifactStatus: ArtifactStatusFilter;
  selectedTargetIds: ReadonlySet<number>;
  canGenerate: boolean;
  permissionLabel: string;
  state: CodeGenerationLedgerState;
  onApplyFilters: (filters: CodeGenerationTargetFilters & { entityType: MappingEntityType }) => void;
  onArtifactStatusChange: (status: ArtifactStatusFilter) => void;
  onToggleTarget: (target: CodeGenerationTarget, selected: boolean) => void;
  onToggleVisible: (targets: CodeGenerationTarget[], selected: boolean) => void;
  onGenerateTarget: (target: CodeGenerationTarget) => void;
  onNextPage: () => void;
  onPreviousPage: () => void;
}) {
  const visibleItems = useMemo(
    () => items.filter((item) => artifactStatusMatches(item, artifactStatus)),
    [artifactStatus, items],
  );
  const allVisibleSelected = visibleItems.length > 0
    && visibleItems.every((item) => selectedTargetIds.has(item.target.object_id));
  const columns = useMemo<ColumnDef<CodeGenerationTarget>[]>(() => [
    {
      id: "select",
      header: () => (
        <input
          type="checkbox"
          aria-label="Select all visible target Objects"
          checked={allVisibleSelected}
          disabled={!visibleItems.length}
          onChange={(event) => onToggleVisible(visibleItems, event.target.checked)}
        />
      ),
      cell: ({ row }) => (
        <input
          type="checkbox"
          aria-label={`Select ${targetName(row.original)}`}
          checked={selectedTargetIds.has(row.original.target.object_id)}
          onChange={(event) => onToggleTarget(row.original, event.target.checked)}
        />
      ),
    },
    {
      id: "target",
      header: "Target Object",
      cell: ({ row }) => (
        <span className="code-target-name">
          <strong>{targetName(row.original)}</strong>
          <span>
            {row.original.target.system_name} ({row.original.target.system_code}) · {row.original.target.zone_code}
          </span>
        </span>
      ),
    },
    {
      accessorKey: "entity_type",
      header: "Modeled layer",
      cell: ({ getValue }) => layerLabel(getValue<MappingEntityType>()),
    },
    {
      id: "source_systems",
      header: "Contributing Systems",
      cell: ({ row }) => (
        <span className="code-source-systems">
          <span className="chip-list">
            {row.original.source_systems.slice(0, 3).map((system) => (
              <span key={system.system_id}>{system.system_code}</span>
            ))}
          </span>
          {row.original.source_system_count > 3 ? (
            <small>+{row.original.source_system_count - 3} more</small>
          ) : null}
        </span>
      ),
    },
    {
      id: "mapping",
      header: "Applied Mapping",
      cell: ({ row }) => (
        <span className="code-mapping-count">
          <strong>{row.original.mapping_support_count}</strong>
          <span>support{row.original.mapping_support_count === 1 ? "" : "s"}</span>
        </span>
      ),
    },
    {
      id: "artifact",
      header: "Latest artifact",
      cell: ({ row }) => {
        const artifact = row.original.latest_artifact;
        return (
          <span className="code-artifact-cell">
            <ArtifactBadge target={row.original} />
            {artifact ? (
              <small>
                {formatDateTime(artifact.generated_at)} · <code title={artifact.generated_sql_digest}>
                  {artifact.generated_sql_digest.slice(0, 10)}…
                </code>
              </small>
            ) : <small>No stored SQL</small>}
          </span>
        );
      },
    },
    {
      id: "review",
      header: "Review",
      cell: ({ row }) => row.original.latest_artifact ? (
        <Link
          className="text-action"
          aria-label={`Show generated SQL for ${targetName(row.original)}`}
          to="/tenants/$tenantId/code-generation/models/$modelId/artifacts/$artifactId"
          params={{
            tenantId: String(tenantId),
            modelId: String(modelId),
            artifactId: String(row.original.latest_artifact.generated_sql_artifact_id),
          }}
        >
          Show generated SQL
        </Link>
      ) : <span className="unavailable-action">Not generated</span>,
    },
    {
      id: "generate",
      header: "",
      cell: ({ row }) => (
        <button
          className="generation-text-action"
          type="button"
          disabled={!canGenerate}
          title={permissionLabel}
          onClick={() => onGenerateTarget(row.original)}
        >
          {row.original.latest_artifact ? "Regenerate" : "Generate"}
        </button>
      ),
    },
  ], [
    allVisibleSelected,
    canGenerate,
    modelId,
    onGenerateTarget,
    onToggleTarget,
    onToggleVisible,
    permissionLabel,
    selectedTargetIds,
    tenantId,
    visibleItems,
  ]);
  const table = useReactTable({
    data: visibleItems,
    columns,
    getCoreRowModel: getCoreRowModel(),
    getRowId: (row) => String(row.target.object_id),
  });

  return (
    <section className="workflow-surface code-generation-surface" aria-labelledby="code-generation-targets-heading">
      <CodeGenerationFilters
        filters={filters}
        artifactStatus={artifactStatus}
        onApplyFilters={onApplyFilters}
        onArtifactStatusChange={onArtifactStatusChange}
      />
      <header className="code-generation-ledger-heading">
        <div>
          <p className="eyebrow">Eligible delivery targets</p>
          <h2 id="code-generation-targets-heading">Target Objects</h2>
        </div>
        <span>{visibleItems.length} shown · {items.length} on server page {state.pageNumber}</span>
      </header>
      {state.isLoading ? (
        <div className="surface-state" aria-busy="true">Loading eligible target Objects…</div>
      ) : state.isDenied ? (
        <div className="surface-state is-error" role="alert">
          You do not have permission to view Code Generation targets.
        </div>
      ) : state.isError ? (
        <div className="surface-state is-error" role="alert">
          Code Generation targets could not be loaded.
        </div>
      ) : state.revisionMismatch ? (
        <div className="surface-state is-error" role="alert">
          The Model changed while Code Generation targets were loading. Refresh before generating SQL.
        </div>
      ) : items.length === 0 ? (
        <div className="empty-state compact">No eligible target Objects match these server filters.</div>
      ) : visibleItems.length === 0 ? (
        <div className="empty-state compact">
          No target Objects on this server page match the artifact status view.
        </div>
      ) : (
        <div className="workflow-table-scroll code-generation-table-scroll">
          <table aria-label="Code Generation target Objects">
            <thead>
              {table.getHeaderGroups().map((group) => (
                <tr key={group.id}>
                  {group.headers.map((header) => (
                    <th key={header.id}>
                      {header.isPlaceholder
                        ? null
                        : flexRender(header.column.columnDef.header, header.getContext())}
                    </th>
                  ))}
                </tr>
              ))}
            </thead>
            <tbody>
              {table.getRowModel().rows.map((row) => {
                const selected = selectedTargetIds.has(row.original.target.object_id);
                return (
                  <tr key={row.id} className={selected ? "is-selected" : ""} aria-selected={selected}>
                    {row.getVisibleCells().map((cell) => (
                      <td key={cell.id}>{flexRender(cell.column.columnDef.cell, cell.getContext())}</td>
                    ))}
                  </tr>
                );
              })}
            </tbody>
          </table>
        </div>
      )}
      {!state.isLoading && !state.isError && !state.isDenied && !state.revisionMismatch ? (
        <nav className="code-generation-pagination" aria-label="Code Generation target pages">
          <button
            className="button button-secondary button-small"
            type="button"
            disabled={!state.hasPreviousPage || state.isPaging}
            onClick={onPreviousPage}
          >
            Previous
          </button>
          <span>Server page {state.pageNumber}</span>
          <button
            className="button button-secondary button-small"
            type="button"
            disabled={!state.hasNextPage || state.isPaging}
            onClick={onNextPage}
          >
            Next
          </button>
        </nav>
      ) : null}
    </section>
  );
}

function CodeGenerationFilters({
  filters,
  artifactStatus,
  onApplyFilters,
  onArtifactStatusChange,
}: {
  filters: CodeGenerationTargetFilters & { entityType: MappingEntityType };
  artifactStatus: ArtifactStatusFilter;
  onApplyFilters: (filters: CodeGenerationTargetFilters & { entityType: MappingEntityType }) => void;
  onArtifactStatusChange: (status: ArtifactStatusFilter) => void;
}) {
  const form = useForm({
    defaultValues: {
      entityType: filters.entityType,
      systemCode: filters.systemCode ?? "",
      sourceSystemCode: filters.sourceSystemCode ?? "",
    },
    onSubmit: ({ value }) => onApplyFilters({
      entityType: value.entityType,
      ...(value.systemCode ? { systemCode: value.systemCode } : {}),
      ...(value.sourceSystemCode ? { sourceSystemCode: value.sourceSystemCode } : {}),
    }),
  });
  return (
    <form
      className="workflow-filterbar code-generation-filterbar"
      aria-label="Filter Code Generation targets"
      onSubmit={(event) => {
        event.preventDefault();
        event.stopPropagation();
        void form.handleSubmit();
      }}
    >
      <form.Field name="entityType">
        {(field) => (
          <label>
            <span>Modeled layer</span>
            <select
              aria-label="Modeled layer"
              value={field.state.value}
              onChange={(event) => field.handleChange(event.target.value as MappingEntityType)}
            >
              <option value="logical_entity">Logical</option>
              <option value="dimensional_entity">Dimensional</option>
            </select>
          </label>
        )}
      </form.Field>
      <form.Field name="systemCode">
        {(field) => (
          <label>
            <span>Target System code</span>
            <input
              aria-label="Target System code"
              value={field.state.value}
              onChange={(event) => field.handleChange(event.target.value)}
            />
          </label>
        )}
      </form.Field>
      <form.Field name="sourceSystemCode">
        {(field) => (
          <label>
            <span>Contributing System code</span>
            <input
              aria-label="Contributing System code"
              value={field.state.value}
              onChange={(event) => field.handleChange(event.target.value)}
            />
          </label>
        )}
      </form.Field>
      <label className="local-status-filter">
        <span>Artifact status · this page</span>
        <select
          aria-label="Artifact status on this page"
          value={artifactStatus}
          onChange={(event) => onArtifactStatusChange(event.target.value as ArtifactStatusFilter)}
        >
          <option value="">All artifact states</option>
          <option value="current">Current</option>
          <option value="stale">Stale</option>
          <option value="not_generated">Not generated</option>
        </select>
        <small>Local view</small>
      </label>
      <div className="workflow-filter-actions">
        <button
          className="button button-secondary button-small"
          type="button"
          onClick={() => {
            form.reset();
            onArtifactStatusChange("");
            onApplyFilters({ entityType: "logical_entity" });
          }}
        >
          Clear
        </button>
        <button className="button button-secondary button-small" type="submit">
          Apply server filters
        </button>
      </div>
    </form>
  );
}

function ArtifactBadge({ target }: { target: CodeGenerationTarget }) {
  const state = artifactState(target);
  const label = state === "not_generated" ? "Not generated" : state === "current" ? "Current" : "Stale";
  const tone = state === "current" ? "is-success" : state === "stale" ? "is-stale" : "is-neutral";
  return <span className={`status-badge ${tone}`}>{label}</span>;
}

function artifactStatusMatches(
  target: CodeGenerationTarget,
  status: ArtifactStatusFilter,
): boolean {
  return !status || artifactState(target) === status;
}

function artifactState(target: CodeGenerationTarget): Exclude<ArtifactStatusFilter, ""> {
  if (!target.latest_artifact) return "not_generated";
  return target.latest_artifact.artifact_is_current ? "current" : "stale";
}

function targetName(target: CodeGenerationTarget): string {
  return `${target.target.object_schema}.${target.target.object_name}`;
}

function layerLabel(entityType: MappingEntityType): string {
  return entityType === "logical_entity" ? "Logical" : "Dimensional";
}
