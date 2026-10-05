import { useEffect, useMemo, useRef, useState } from "react";
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";

import { ApiError } from "../../core/http";
import { trapDialogFocus } from "../../shared/dialog";
import type { TenantLockState } from "../tenant_locks/api";
import {
  metadataQueryKeys,
  validationReviewFromOutcome,
  validationReviewFromResult,
  type MetadataApi,
  type MetadataSection,
  type MetadataValidationReview,
} from "./api";
import { MetadataChangeSetPanel } from "./MetadataChangeSetPanel";
import { MetadataExportDialog } from "./MetadataExportDialog";
import { MetadataLedger } from "./MetadataLedger";
import { PhysicalMetadataScreen } from "./PhysicalMetadataScreen";

export type MetadataCategory = MetadataSection | "objects";
const SECTIONS: Array<{ section: MetadataCategory; label: string }> = [
  { section: "reference", label: "Reference" },
  { section: "foundational", label: "Foundational" },
  { section: "objects", label: "Objects" },
  { section: "operational", label: "Operational" },
];

export function MetadataScreen({
  api,
  tenantId,
  tenantLock,
  canWriteMetadata,
  section, objectId, onSectionChange, onObjectChange,
}: {
  api: MetadataApi;
  tenantId: number;
  tenantLock: TenantLockState;
  canWriteMetadata: boolean;
  section: MetadataCategory;
  objectId: number | null;
  onSectionChange: (section: MetadataCategory) => void;
  onObjectChange: (objectId: number | null) => void;
}) {
  const queryClient = useQueryClient();
  const [datasetCode, setDatasetCode] = useState<string | null>(null);
  const [cursor, setCursor] = useState<string | undefined>();
  const [cursorHistory, setCursorHistory] = useState<Array<string | undefined>>([]);
  const [exportOpen, setExportOpen] = useState(false);
  const [importOpen, setImportOpen] = useState(false);
  const importCloseRef = useRef<HTMLButtonElement>(null);
  const [changeSetId, setChangeSetId] = useState<string | null>(null);
  const [review, setReview] = useState<MetadataValidationReview | null>(null);
  const registryQuery = useQuery({
    queryKey: metadataQueryKeys.registry(tenantId),
    queryFn: () => api.listMetadataDatasets(tenantId),
  });
  const sectionDatasets = useMemo(() => (
    registryQuery.data?.datasets.filter((dataset) => dataset.section === section
      && !(section === "operational" && /^(source|bronze|silver|gold)_(object|attribute)$/.test(dataset.dataset))) ?? []
  ), [registryQuery.data, section]);
  const descriptor = (section === "objects"
    ? registryQuery.data?.datasets.find((dataset) => dataset.dataset === (datasetCode ?? "source_object"))
      ?? registryQuery.data?.datasets.find((dataset) => dataset.dataset === "source_object")
    : sectionDatasets.find((dataset) => dataset.dataset === datasetCode))
    ?? sectionDatasets[0]
    ?? null;
  const operationalDatasets = registryQuery.data?.datasets.filter((dataset) => (
    dataset.section === "operational" && dataset.change_set_eligible && !dataset.read_only
  )) ?? [];

  useEffect(() => {
    if (descriptor && descriptor.dataset !== datasetCode) setDatasetCode(descriptor.dataset);
  }, [datasetCode, descriptor]);

  useEffect(() => {
    if (!importOpen) return;
    const previousFocus = document.activeElement;
    importCloseRef.current?.focus();
    return () => { if (previousFocus instanceof HTMLElement && previousFocus.isConnected) previousFocus.focus(); };
  }, [importOpen]);

  const rowsQuery = useQuery({
    queryKey: metadataQueryKeys.rows(tenantId, descriptor?.dataset ?? "", {}, cursor),
    queryFn: () => api.listMetadataRows(
      tenantId,
      descriptor?.dataset ?? "",
      {},
      50,
      cursor,
    ),
    enabled: Boolean(descriptor) && section !== "objects",
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

  const hasTenantLock = tenantLock.is_locked && tenantLock.owned_by_current_principal === true
    && tenantLock.expires_at !== null && Date.parse(tenantLock.expires_at) > Date.now();
  const editableChangeSet = changeSetQuery.data?.status === "active"
    || changeSetQuery.data?.status === "validated";
  const createMutation = useMutation({
    mutationFn: () => api.createMetadataChangeSet(tenantId, newIdempotencyKey()),
    onSuccess: (result) => {
      setChangeSetId(result.metadata_change_set_id);
      setReview(null);
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
        queryClient.invalidateQueries({ queryKey: ["metadata-objects", tenantId] }),
        queryClient.invalidateQueries({ queryKey: ["metadata-object", tenantId] }),
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
    || validateMutation.isPending
    || applyMutation.isPending
    || archiveMutation.isPending
    || importMutation.isPending
    || changeSetQuery.isFetching;

  const selectSection = (next: MetadataCategory) => {
    onSectionChange(next);
    setDatasetCode(null);
    setCursor(undefined);
    setCursorHistory([]);
  };
  const selectDataset = (next: string) => {
    setDatasetCode(next);
    setCursor(undefined);
    setCursorHistory([]);
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

  const exportDialog = exportOpen ? (
    <MetadataExportDialog
      datasets={operationalDatasets}
      activeDataset={section !== "objects" && descriptor.section === "operational" ? descriptor.dataset : null}
      onClose={() => setExportOpen(false)}
      onExport={(sheetCodes) => api.exportMetadataWorkbook(tenantId, sheetCodes)}
    />
  ) : null;

  return (
    <main className="metadata-catalog">
      <header className="metadata-catalog-titlebar">
        <h1>Metadata</h1>
        <div className="metadata-catalog-actions">
          <span className={`metadata-catalog-state${hasTenantLock ? " is-held" : ""}`} title={lockStateText(tenantLock)}>
            {hasTenantLock ? "Lock held" : "Read-only"}
          </span>
          {section !== "objects" ? <button
            className="button button-secondary button-small"
            type="button"
            disabled={registryQuery.isFetching || rowsQuery.isFetching || isChangeSetBusy}
            onClick={() => void Promise.all([
              registryQuery.refetch(),
              rowsQuery.refetch(),
              changeSetId ? changeSetQuery.refetch() : Promise.resolve(),
            ])}
          >
            {registryQuery.isFetching || rowsQuery.isFetching ? "Refreshing…" : "Refresh"}
          </button> : null}
          <button className="button button-secondary button-small" type="button" onClick={() => setExportOpen(true)}>
            Export Excel
          </button>
          <button className="button button-accent button-small" type="button" aria-expanded={importOpen} aria-controls="metadata-import-panel" onClick={() => setImportOpen(true)}>Import{editableChangeSet ? " · Draft" : ""}</button>
        </div>
      </header>

      <div className="metadata-import-scrim" hidden={!importOpen}>
        <aside id="metadata-import-panel" className="metadata-import-panel" role="dialog" aria-modal="true" aria-label="Import Metadata"
          onKeyDown={(event) => {
            if ((event.target as HTMLElement).closest('[role="dialog"]') !== event.currentTarget) return;
            if (event.key === "Escape" && !isChangeSetBusy) { event.stopPropagation(); setImportOpen(false); }
            trapDialogFocus(event);
          }}>
          <header><h2>Import Metadata</h2><button ref={importCloseRef} className="dialog-close" type="button" aria-label="Close import" disabled={isChangeSetBusy} onClick={() => setImportOpen(false)}>×</button></header>
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
      </div>

      <nav className="metadata-category-tabs" aria-label="Metadata catalog navigation">
        {SECTIONS.map((item) => <button key={item.section} type="button" aria-current={section === item.section ? "page" : undefined} onClick={() => selectSection(item.section)}>{item.label}</button>)}
      </nav>
      <div className="metadata-catalog-content">
      {section === "objects" ? <PhysicalMetadataScreen api={api} tenantId={tenantId}
        objectId={objectId} onObjectChange={onObjectChange} embedded /> : <>
        <div className="metadata-sheetbar"><nav className="metadata-sheet-tabs" aria-label={`${section} sheets`}>
          {sectionDatasets.map((dataset) => <button key={dataset.dataset} type="button" aria-current={dataset.dataset === descriptor.dataset ? "page" : undefined} onClick={() => selectDataset(dataset.dataset)}>{dataset.label}</button>)}
        </nav>
        <span className="metadata-readonly-badge">{descriptor.read_only ? "Read-only" : "Read-only · Edit through Excel import"}</span>
        </div>
        <MetadataLedger
          descriptor={descriptor}
          items={rowsQuery.data?.items ?? []}
          state={{
            isLoading: rowsQuery.isPending,
            isFetching: rowsQuery.isFetching,
            isDenied: rowsQuery.error instanceof ApiError && rowsQuery.error.status === 403,
            isError: rowsQuery.isError,
            hasNext: Boolean(rowsQuery.data?.next_cursor),
            hasPrevious: cursorHistory.length > 0,
          }}
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
        </>}
      </div>

      {exportDialog}
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
