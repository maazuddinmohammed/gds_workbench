import { useMemo, useState } from "react";
import { MultiSelectField } from "../../shared/MultiSelectField";
import { Link } from "@tanstack/react-router";
import {
  flexRender,
  getCoreRowModel,
  useReactTable,
  type ColumnDef,
} from "@tanstack/react-table";

import { formatRequiredDateTime as formatDateTime } from "../../shared/presentation";
import type { CodeGenerationTarget } from "./api";

export type ArtifactStatusFilter = "" | "current" | "stale" | "not_generated";

export interface CodeGenerationLedgerState {
  isLoading: boolean;
  isError: boolean;
  isDenied: boolean;
  revisionMismatch: boolean;
  hasPreviousPage: boolean;
  isPaging: boolean;
  pageNumber: number;
}

export function CodeGenerationLedger({
  tenantId,
  modelId,
  items,
  objectIds, onObjectIdsChange, page,
  artifactStatus,
  selectedTargetIds,
  canGenerate,
  permissionLabel,
  state,
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
  objectIds: string[]; onObjectIdsChange: (ids: string[]) => void; page: number;
  artifactStatus: ArtifactStatusFilter;
  selectedTargetIds: ReadonlySet<number>;
  canGenerate: boolean;
  permissionLabel: string;
  state: CodeGenerationLedgerState;
  onArtifactStatusChange: (status: ArtifactStatusFilter) => void;
  onToggleTarget: (target: CodeGenerationTarget, selected: boolean) => void;
  onToggleVisible: (targets: CodeGenerationTarget[], selected: boolean) => void;
  onGenerateTarget: (target: CodeGenerationTarget) => void;
  onNextPage: () => void;
  onPreviousPage: () => void;
}) {
  const filteredItems = useMemo(
    () => items.filter((item) => artifactStatusMatches(item, artifactStatus) && (!objectIds.length || objectIds.includes(String(item.target.object_id)))),
    [artifactStatus, items, objectIds],
  );
  const visibleItems = useMemo(
    () => filteredItems.slice(page * 50, (page + 1) * 50),
    [filteredItems, page],
  );
  const selectableItems = useMemo(
    () => visibleItems.filter((item) => !item.is_locked),
    [visibleItems],
  );
  const allVisibleSelected = selectableItems.length > 0
    && selectableItems.every((item) => selectedTargetIds.has(item.target.object_id));
  const columns = useMemo<ColumnDef<CodeGenerationTarget>[]>(() => [
    {
      id: "select",
      header: () => (
        <input
          type="checkbox"
          aria-label="Select all visible target Objects"
          checked={allVisibleSelected}
          disabled={!selectableItems.length}
          onChange={(event) => onToggleVisible(visibleItems.filter((item) => !item.is_locked), event.target.checked)}
        />
      ),
      cell: ({ row }) => (
        <input
          type="checkbox"
          aria-label={`Select ${targetName(row.original)}`}
          disabled={row.original.is_locked}
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
            {row.original.target.system_code} · {row.original.target.zone_code}
          </span>
        </span>
      ),
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
      header: "Artifacts",
      cell: ({ row }) => {
        const activeArtifacts = row.original.artifacts.filter(
          (artifact) => artifact.generated_code_status === "active",
        );
        const newest = activeArtifacts.at(-1);
        return (
          <span className="code-artifact-cell">
            <ArtifactBadge target={row.original} />
            {newest ? (
              <small>
                {activeArtifacts.length} file{activeArtifacts.length === 1 ? "" : "s"} · {formatDateTime(newest.generated_at)}
              </small>
            ) : <small>No stored SQL</small>}
          </span>
        );
      },
    },
    {
      id: "review",
      header: "Review",
      cell: ({ row }) => {
        const artifacts = row.original.artifacts.filter(
          (artifact) => artifact.generated_code_status === "active",
        );
        return artifacts.length ? (
          <span className="code-artifact-links">
            {artifacts.slice(0, 3).map((artifact) => (
              <Link
                key={artifact.generated_sql_artifact_id}
                className="text-action"
                aria-label={`Show ${artifact.artifact_name} for ${targetName(row.original)}`}
                to="/tenants/$tenantId/code-generation/models/$modelId/artifacts/$artifactId"
                params={{
                  tenantId: String(tenantId),
                  modelId: String(modelId),
                  artifactId: String(artifact.generated_sql_artifact_id),
                }}
              >
                {artifact.artifact_name}
              </Link>
            ))}
            {artifacts.length > 3 ? <small>+{artifacts.length - 3} more</small> : null}
          </span>
        ) : <span className="unavailable-action">Not generated</span>;
      },
    },
    {
      id: "generate",
      header: "",
      cell: ({ row }) => (
        <button
          className="generation-text-action"
          type="button"
          disabled={!canGenerate || row.original.is_locked}
          title={row.original.is_locked ? "Unlock the Object’s SQL files before regenerating" : permissionLabel}
          onClick={() => onGenerateTarget(row.original)}
        >
          {row.original.artifacts.some(
            (artifact) => artifact.generated_code_status === "active",
          ) ? "Regenerate" : "Generate"}
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
        items={items} objectIds={objectIds} onObjectIdsChange={onObjectIdsChange}
        artifactStatus={artifactStatus}
        onArtifactStatusChange={onArtifactStatusChange}
      />
      <header className="code-generation-ledger-heading">
        <div>
          <p className="eyebrow">Eligible delivery targets</p>
          <h2 id="code-generation-targets-heading">Target Objects</h2>
        </div>
        <span>{filteredItems.length} Objects · Page {state.pageNumber}</span>
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
        <div className="empty-state compact">No eligible target Objects in this layer.</div>
      ) : visibleItems.length === 0 ? (
        <div className="empty-state compact">
          No Objects match these filters.
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
          <span>Page {state.pageNumber}</span>
          <button
            className="button button-secondary button-small"
            type="button"
            disabled={(page + 1) * 50 >= filteredItems.length || state.isPaging}
            onClick={onNextPage}
          >
            Next
          </button>
        </nav>
      ) : null}
    </section>
  );
}

function CodeGenerationFilters({ items, objectIds, onObjectIdsChange, artifactStatus, onArtifactStatusChange }: {
  items: CodeGenerationTarget[]; objectIds: string[]; onObjectIdsChange: (ids: string[]) => void;
  artifactStatus: ArtifactStatusFilter;
  onArtifactStatusChange: (status: ArtifactStatusFilter) => void;
}) {
  const [draftObjectIds, setDraftObjectIds] = useState(objectIds);
  const [draftStatus, setDraftStatus] = useState(artifactStatus);
  return <form className="workflow-filterbar code-generation-filterbar" aria-label="Filter Code Generation targets" onSubmit={(event) => {
    event.preventDefault(); onObjectIdsChange(draftObjectIds); onArtifactStatusChange(draftStatus);
  }}>
    <MultiSelectField label="Objects" value={draftObjectIds} onChange={setDraftObjectIds}
      options={items.map((item) => [String(item.target.object_id), `${item.target.system_code} · ${targetName(item)}`])} />
    <label><span>Status</span><select aria-label="Status" value={draftStatus}
      onChange={(event) => setDraftStatus(event.target.value as ArtifactStatusFilter)}>
      <option value="">All statuses</option><option value="current">Current</option>
      <option value="stale">Stale</option><option value="not_generated">Not generated</option>
    </select></label>
    <div className="workflow-filter-actions"><button className="button button-secondary button-small" type="button" onClick={() => {
      setDraftObjectIds([]); setDraftStatus("");
      onObjectIdsChange([]); onArtifactStatusChange("");
    }}>Clear</button>
    <button className="button button-primary button-small" type="submit">Apply filters</button></div>
  </form>;
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
  const active = target.artifacts.filter(
    (artifact) => artifact.generated_code_status === "active",
  );
  if (!active.length) return "not_generated";
  return active.every((artifact) => artifact.artifact_is_current) ? "current" : "stale";
}

function targetName(target: CodeGenerationTarget): string {
  return `${target.target.object_schema}.${target.target.object_name}`;
}
