import { useEffect, useMemo, useState } from "react";
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";

import { ApiError } from "../../core/http";
import type { TenantLockState } from "../tenant_locks/api";
import {
  mergeStagedRecord,
  metadataQueryKeys,
  metadataRowKey,
  validationReviewFromOutcome,
  validationReviewFromResult,
  type MetadataApi,
  type MetadataFilters,
  type MetadataRow,
  type MetadataSection,
  type MetadataValidationReview,
} from "./api";
import { MetadataChangeSetPanel } from "./MetadataChangeSetPanel";
import { MetadataExportDialog } from "./MetadataExportDialog";
import { MetadataLedger } from "./MetadataLedger";
import { MetadataRowDetail, MetadataRowEditor } from "./MetadataRowSurface";

const SECTIONS: Array<{ section: MetadataSection; label: string }> = [
  { section: "reference", label: "Reference" },
  { section: "foundational", label: "Foundational" },
  { section: "operational", label: "Operational" },
];

export function MetadataScreen({
  api,
  tenantId,
  tenantName,
  tenantLock,
  canWriteMetadata,
}: {
  api: MetadataApi;
  tenantId: number;
  tenantName: string;
  tenantLock: TenantLockState;
  canWriteMetadata: boolean;
}) {
  const queryClient = useQueryClient();
  const [section, setSection] = useState<MetadataSection>("reference");
  const [datasetCode, setDatasetCode] = useState<string | null>(null);
  const [filters, setFilters] = useState<MetadataFilters>({});
  const [cursor, setCursor] = useState<string | undefined>();
  const [cursorHistory, setCursorHistory] = useState<Array<string | undefined>>([]);
  const [selectedRow, setSelectedRow] = useState<MetadataRow | null>(null);
  const [editor, setEditor] = useState<{ mode: "add" | "edit"; row: MetadataRow } | null>(null);
  const [exportOpen, setExportOpen] = useState(false);
  const [changeSetId, setChangeSetId] = useState<string | null>(null);
  const [review, setReview] = useState<MetadataValidationReview | null>(null);
  const registryQuery = useQuery({
    queryKey: metadataQueryKeys.registry(tenantId),
    queryFn: () => api.listMetadataDatasets(tenantId),
  });
  const sectionDatasets = useMemo(() => (
    registryQuery.data?.datasets.filter((dataset) => dataset.section === section) ?? []
  ), [registryQuery.data, section]);
  const descriptor = sectionDatasets.find((dataset) => dataset.dataset === datasetCode)
    ?? sectionDatasets[0]
    ?? null;
  const operationalDatasets = registryQuery.data?.datasets.filter((dataset) => (
    dataset.section === "operational" && dataset.change_set_eligible && !dataset.read_only
  )) ?? [];

  useEffect(() => {
    if (descriptor && descriptor.dataset !== datasetCode) setDatasetCode(descriptor.dataset);
  }, [datasetCode, descriptor]);

  const rowsQuery = useQuery({
    queryKey: metadataQueryKeys.rows(tenantId, descriptor?.dataset ?? "", filters, cursor),
    queryFn: () => api.listMetadataRows(
      tenantId,
      descriptor?.dataset ?? "",
      filters,
      50,
      cursor,
    ),
    enabled: Boolean(descriptor),
  });
  const datasetDetailQuery = useQuery({
    queryKey: metadataQueryKeys.dataset(tenantId, descriptor?.dataset ?? ""),
    queryFn: () => api.describeMetadataDataset(tenantId, descriptor?.dataset ?? ""),
    enabled: Boolean(descriptor),
  });
  const changeSetDataset = descriptor?.section === "operational" ? descriptor.dataset : undefined;
  const changeSetQuery = useQuery({
    queryKey: metadataQueryKeys.changeSet(tenantId, changeSetId ?? "", changeSetDataset),
    queryFn: () => api.readMetadataChangeSet(tenantId, changeSetId ?? "", changeSetDataset),
    enabled: Boolean(changeSetId),
  });
  useEffect(() => {
    if (!review) setReview(validationReviewFromOutcome(changeSetQuery.data?.validation_outcome ?? null));
  }, [changeSetQuery.data?.validation_outcome, review]);

  const hasTenantLock = tenantLock.is_locked && tenantLock.owned_by_current_principal === true;
  const editableChangeSet = changeSetQuery.data?.status === "active"
    || changeSetQuery.data?.status === "validated";
  const canStage = Boolean(
    descriptor?.change_set_eligible
    && !descriptor.read_only
    && canWriteMetadata
    && hasTenantLock
    && editableChangeSet
    && datasetDetailQuery.data?.dataset === descriptor.dataset
    && changeSetQuery.data?.dataset === descriptor.dataset,
  );
  const stagedRecords = changeSetQuery.data?.records ?? [];

  const createMutation = useMutation({
    mutationFn: () => api.createMetadataChangeSet(tenantId, newIdempotencyKey()),
    onSuccess: (result) => {
      setChangeSetId(result.metadata_change_set_id);
      setReview(null);
    },
  });
  const stageMutation = useMutation({
    mutationFn: async ({ record, previousKey }: { record: MetadataRow; previousKey?: string }) => {
      if (!descriptor || !changeSetQuery.data) throw new Error("Metadata Change Set unavailable");
      const records = mergeStagedRecord(
        changeSetQuery.data.records ?? [],
        record,
        descriptor.natural_key,
        previousKey,
      );
      return api.stageMetadataChangeSet(
        tenantId,
        changeSetQuery.data.metadata_change_set_id,
        {
          schema_version: "1.0",
          expected_draft_revision: changeSetQuery.data.draft_revision,
          changes: [{ dataset: descriptor.dataset, records }],
        },
        newIdempotencyKey(),
      );
    },
    onSuccess: async () => {
      setReview(null);
      await queryClient.invalidateQueries({
        queryKey: ["metadata-change-set", tenantId],
      });
    },
  });
  const validateMutation = useMutation({
    mutationFn: async () => {
      if (!changeSetQuery.data) throw new Error("Metadata Change Set unavailable");
      return api.validateMetadataChangeSet(
        tenantId,
        changeSetQuery.data.metadata_change_set_id,
        changeSetQuery.data.draft_revision,
      );
    },
    onSuccess: async (result) => {
      setReview(validationReviewFromResult(result));
      await queryClient.invalidateQueries({ queryKey: ["metadata-change-set", tenantId] });
    },
  });
  const applyMutation = useMutation({
    mutationFn: async () => {
      if (!changeSetQuery.data) throw new Error("Metadata Change Set unavailable");
      return api.applyMetadataChangeSet(
        tenantId,
        changeSetQuery.data.metadata_change_set_id,
        changeSetQuery.data.draft_revision,
        newIdempotencyKey(),
      );
    },
    onSuccess: async (result) => {
      setReview({
        valid: result.valid,
        phase: result.phase,
        staged_record_count: result.staged_record_count,
        error_count: result.error_count,
        errors: result.errors,
        action_review: result.action_review,
      });
      await Promise.all([
        queryClient.invalidateQueries({ queryKey: ["metadata-change-set", tenantId] }),
        queryClient.invalidateQueries({ queryKey: ["metadata-rows", tenantId] }),
        queryClient.invalidateQueries({ queryKey: ["tenant-home", tenantId] }),
      ]);
    },
  });
  const archiveMutation = useMutation({
    mutationFn: async () => {
      if (!changeSetQuery.data) throw new Error("Metadata Change Set unavailable");
      return api.archiveMetadataChangeSet(
        tenantId,
        changeSetQuery.data.metadata_change_set_id,
        changeSetQuery.data.draft_revision,
        newIdempotencyKey(),
      );
    },
    onSuccess: async () => {
      await queryClient.invalidateQueries({ queryKey: ["metadata-change-set", tenantId] });
    },
  });
  const importMutation = useMutation({
    mutationFn: async (file: File) => {
      if (!changeSetQuery.data) throw new Error("Metadata Change Set unavailable");
      return api.importMetadataWorkbook(
        tenantId,
        changeSetQuery.data.metadata_change_set_id,
        changeSetQuery.data.draft_revision,
        file,
        newIdempotencyKey(),
      );
    },
    onSuccess: async (result) => {
      setReview(validationReviewFromResult(result.validation));
      await queryClient.invalidateQueries({ queryKey: ["metadata-change-set", tenantId] });
    },
  });
  const isChangeSetBusy = createMutation.isPending
    || stageMutation.isPending
    || validateMutation.isPending
    || applyMutation.isPending
    || archiveMutation.isPending
    || importMutation.isPending
    || changeSetQuery.isFetching;

  const selectSection = (next: MetadataSection) => {
    setSection(next);
    setDatasetCode(registryQuery.data?.datasets.find((dataset) => dataset.section === next)?.dataset ?? null);
    setFilters({});
    setCursor(undefined);
    setCursorHistory([]);
    setSelectedRow(null);
  };
  const selectDataset = (next: string) => {
    setDatasetCode(next);
    setFilters({});
    setCursor(undefined);
    setCursorHistory([]);
    setSelectedRow(null);
  };

  if (registryQuery.isPending) {
    return <main className="workspace metadata-workspace"><div className="surface-state" aria-busy="true">Loading Metadata registry…</div></main>;
  }
  if (registryQuery.error instanceof ApiError && registryQuery.error.status === 403) {
    return <main className="workspace metadata-workspace"><div className="surface-state is-error" role="alert">You do not have permission to view this Tenant Metadata catalog.</div></main>;
  }
  if (registryQuery.isError || !descriptor) {
    return <main className="workspace metadata-workspace"><div className="surface-state is-error" role="alert">The governed Metadata registry could not be loaded.</div></main>;
  }

  const selectedStagedRow = selectedRow
    ? stagedRecords.find((row) => metadataRowKey(row, descriptor.natural_key) === (
      metadataRowKey(selectedRow, descriptor.natural_key)
    ))
    : undefined;
  const effectiveSelectedRow = selectedStagedRow ?? selectedRow;
  const editDisabledReason = !canWriteMetadata
    ? "Developer permission or higher is required"
    : !hasTenantLock
      ? "Own the Tenant Lock to stage Metadata"
      : !changeSetId
        ? "Start or resume a Metadata Change Set first"
        : !editableChangeSet
          ? "The open Metadata Change Set is terminal"
          : "Loading the selected sheet’s staged rows";
  const addDisabledReason = !canStage
    ? editDisabledReason
    : "Stage a new complete normalized row";

  return (
    <main className="workspace metadata-workspace page-enter">
      <header className="metadata-commandbar">
        <div>
          <p className="eyebrow">Governed catalog · {tenantName}</p>
          <h1>Metadata</h1>
          <p>Normalized server records, operational workbook exchange, and reviewed Tenant changes.</p>
        </div>
        <div>
          <button
            className="button button-secondary button-small"
            type="button"
            disabled={registryQuery.isFetching || rowsQuery.isFetching}
            onClick={() => void Promise.all([
              registryQuery.refetch(),
              datasetDetailQuery.refetch(),
              rowsQuery.refetch(),
              changeSetId ? changeSetQuery.refetch() : Promise.resolve(),
            ])}
          >
            {registryQuery.isFetching || rowsQuery.isFetching ? "Refreshing…" : "Refresh"}
          </button>
          <button className="button button-accent button-small" type="button" onClick={() => setExportOpen(true)}>
            Export Excel
          </button>
        </div>
      </header>

      <nav className="metadata-section-tabs" aria-label="Metadata sections">
        {SECTIONS.map((item) => {
          const count = registryQuery.data.datasets.filter((dataset) => dataset.section === item.section).length;
          return (
            <button
              key={item.section}
              className={section === item.section ? "is-active" : undefined}
              type="button"
              aria-label={`${item.label} ${count} sheets`}
              aria-current={section === item.section ? "page" : undefined}
              onClick={() => selectSection(item.section)}
            >
              <strong>{item.label}</strong><span>{count} sheets</span>
            </button>
          );
        })}
      </nav>

      <div className="metadata-layout">
        <aside className="metadata-control-rail" aria-label="Metadata access and Change Set">
          <section className="metadata-access-state">
            <p className="eyebrow">Access state</p>
            <h2>{hasTenantLock ? "Tenant Lock held" : "Read-only view"}</h2>
            <p>{lockStateText(tenantLock)}</p>
            <dl>
              <div><dt>Reference</dt><dd>Read-only</dd></div>
              <div><dt>Foundational</dt><dd>Read-only</dd></div>
              <div><dt>Operational</dt><dd>{hasTenantLock && canWriteMetadata ? "Staging available" : "Read-only"}</dd></div>
            </dl>
          </section>
          <MetadataChangeSetPanel
            changeSet={changeSetQuery.data ?? null}
            selectedDataset={descriptor.section === "operational" ? descriptor : null}
            review={review}
            canWrite={canWriteMetadata}
            hasTenantLock={hasTenantLock}
            isBusy={isChangeSetBusy}
            onCreateOrResume={() => createMutation.mutateAsync().then(() => undefined)}
            onValidate={() => validateMutation.mutateAsync().then(() => undefined)}
            onApply={() => applyMutation.mutateAsync().then(() => undefined)}
            onArchive={() => archiveMutation.mutateAsync().then(() => undefined)}
            onImport={(file) => importMutation.mutateAsync(file).then(() => undefined)}
          />
        </aside>

        <section className="metadata-catalog-plane">
          <nav className="metadata-sheet-tabs" aria-label={`${section} Metadata sheets`}>
            {sectionDatasets.map((dataset) => (
              <button
                key={dataset.dataset}
                className={dataset.dataset === descriptor.dataset ? "is-active" : undefined}
                type="button"
                onClick={() => selectDataset(dataset.dataset)}
              >
                {dataset.label}
              </button>
            ))}
          </nav>
          <MetadataLedger
            descriptor={descriptor}
            items={rowsQuery.data?.items ?? []}
            filters={filters}
            rowSchema={datasetDetailQuery.data?.row_schema ?? null}
            state={{
              isLoading: rowsQuery.isPending,
              isFetching: rowsQuery.isFetching,
              isDenied: rowsQuery.error instanceof ApiError && rowsQuery.error.status === 403,
              isError: rowsQuery.isError,
              hasNext: Boolean(rowsQuery.data?.next_cursor),
              hasPrevious: cursorHistory.length > 0,
            }}
            canAdd={canStage}
            addDisabledReason={addDisabledReason}
            onApplyFilters={(next) => {
              setFilters(next);
              setCursor(undefined);
              setCursorHistory([]);
            }}
            onOpenRow={setSelectedRow}
            onAdd={() => setEditor({ mode: "add", row: {} })}
            onNext={() => {
              if (!rowsQuery.data?.next_cursor) return;
              setCursorHistory((current) => [...current, cursor]);
              setCursor(rowsQuery.data.next_cursor ?? undefined);
            }}
            onPrevious={() => {
              setCursorHistory((current) => {
                const next = [...current];
                setCursor(next.pop());
                return next;
              });
            }}
          />
        </section>
      </div>

      {effectiveSelectedRow ? (
        <MetadataRowDetail
          descriptor={descriptor}
          row={effectiveSelectedRow}
          isStaged={Boolean(selectedStagedRow)}
          canEdit={canStage}
          editDisabledReason={editDisabledReason}
          onClose={() => setSelectedRow(null)}
          onEdit={() => setEditor({ mode: "edit", row: effectiveSelectedRow })}
        />
      ) : null}
      {editor ? (
        <MetadataRowEditor
          mode={editor.mode}
          descriptor={descriptor}
          rowSchema={datasetDetailQuery.data?.row_schema ?? { properties: {} }}
          baseRow={editor.row}
          isSaving={stageMutation.isPending}
          onClose={() => setEditor(null)}
          onStage={(record, previousKey) => stageMutation.mutateAsync({
            record,
            ...(previousKey ? { previousKey } : {}),
          }).then(() => {
            setSelectedRow(record);
          })}
        />
      ) : null}
      {exportOpen ? (
        <MetadataExportDialog
          datasets={operationalDatasets}
          activeDataset={descriptor.section === "operational" ? descriptor.dataset : null}
          onClose={() => setExportOpen(false)}
          onExport={(sheetCodes) => api.exportMetadataWorkbook(tenantId, sheetCodes)}
        />
      ) : null}
    </main>
  );
}

function newIdempotencyKey(): string {
  if (typeof globalThis.crypto?.randomUUID !== "function") {
    throw new Error("Secure browser UUID support is required");
  }
  return globalThis.crypto.randomUUID();
}

function lockStateText(lock: TenantLockState): string {
  if (lock.is_locked && lock.owned_by_current_principal) {
    return lock.expires_at ? `Owned by you until ${new Date(lock.expires_at).toLocaleString()}.` : "Owned by you.";
  }
  if (lock.is_locked) {
    return `Held by ${lock.owner_display_name ?? "another Principal"}. Catalog reads remain available.`;
  }
  return "No active Tenant Lock. Catalog reads and Excel export remain available.";
}
