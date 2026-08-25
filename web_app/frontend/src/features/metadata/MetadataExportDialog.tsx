import { useEffect, useRef, useState } from "react";

import type { MetadataDatasetDescription, MetadataWorkbookDownload } from "./api";

export function MetadataExportDialog({
  datasets,
  activeDataset,
  onClose,
  onExport,
}: {
  datasets: MetadataDatasetDescription[];
  activeDataset: string | null;
  onClose: () => void;
  onExport: (sheetCodes: "all" | string[]) => Promise<MetadataWorkbookDownload>;
}) {
  const closeRef = useRef<HTMLButtonElement>(null);
  const [mode, setMode] = useState<"selected" | "all">(activeDataset ? "selected" : "all");
  const [selected, setSelected] = useState(() => new Set(
    activeDataset ? [activeDataset] : datasets[0] ? [datasets[0].dataset] : [],
  ));
  const [isExporting, setIsExporting] = useState(false);
  const [message, setMessage] = useState("");
  useEffect(() => {
    closeRef.current?.focus();
    const onKeyDown = (event: KeyboardEvent) => {
      if (event.key === "Escape" && !isExporting) onClose();
    };
    document.addEventListener("keydown", onKeyDown);
    return () => document.removeEventListener("keydown", onKeyDown);
  }, [isExporting, onClose]);

  const runExport = async () => {
    const sheetCodes = datasets
      .filter((dataset) => selected.has(dataset.dataset))
      .map((dataset) => dataset.dataset);
    if (mode === "selected" && sheetCodes.length === 0) {
      setMessage("Select at least one Operational sheet.");
      return;
    }
    setIsExporting(true);
    setMessage("");
    try {
      const download = await onExport(mode === "all" ? "all" : sheetCodes);
      const url = URL.createObjectURL(download.blob);
      const anchor = document.createElement("a");
      anchor.href = url;
      anchor.download = download.filename;
      anchor.click();
      URL.revokeObjectURL(url);
      onClose();
    } catch {
      setMessage("The governed workbook could not be exported. No local file was retained.");
    } finally {
      setIsExporting(false);
    }
  };

  return (
    <div className="dialog-scrim prompt-dialog-scrim" role="presentation">
      <section
        className="prompt-dialog metadata-export-dialog"
        role="dialog"
        aria-modal="true"
        aria-labelledby="metadata-export-title"
      >
        <header>
          <div>
            <p className="eyebrow">Operational Metadata only</p>
            <h2 id="metadata-export-title">Export Excel workbook</h2>
          </div>
          <button
            ref={closeRef}
            className="dialog-close"
            type="button"
            aria-label="Close Metadata export"
            disabled={isExporting}
            onClick={onClose}
          >×</button>
        </header>
        <p>
          The server creates one bounded, versioned workbook in memory. Export does not require
          a Tenant Lock.
        </p>
        <div className="metadata-export-modes">
          <label>
            <input
              type="radio"
              name="metadata-export-mode"
              value="selected"
              checked={mode === "selected"}
              onChange={() => setMode("selected")}
            />
            <span><strong>Selected sheets</strong><small>Choose one or more below.</small></span>
          </label>
          <label>
            <input
              type="radio"
              name="metadata-export-mode"
              value="all"
              checked={mode === "all"}
              onChange={() => setMode("all")}
            />
            <span><strong>All Operational sheets</strong><small>{datasets.length} canonical sheets.</small></span>
          </label>
        </div>
        <div className="metadata-export-sheets" aria-label="Operational sheets to export">
          {datasets.map((dataset) => (
            <label key={dataset.dataset}>
              <input
                type="checkbox"
                checked={selected.has(dataset.dataset)}
                disabled={mode === "all" || isExporting}
                onChange={(event) => setSelected((current) => {
                  const next = new Set(current);
                  if (event.target.checked) next.add(dataset.dataset);
                  else next.delete(dataset.dataset);
                  return next;
                })}
              />
              <span>{dataset.label}</span>
              <code>{dataset.dataset}</code>
            </label>
          ))}
        </div>
        <footer>
          <span role="alert">{message}</span>
          <div>
            <button className="button button-secondary" type="button" onClick={onClose} disabled={isExporting}>
              Cancel
            </button>
            <button
              className="button button-accent"
              type="button"
              disabled={isExporting || (mode === "selected" && selected.size === 0)}
              onClick={() => void runExport()}
            >
              {isExporting
                ? "Exporting…"
                : mode === "all"
                  ? `Export all ${datasets.length}`
                  : `Export selected (${selected.size})`}
            </button>
          </div>
        </footer>
      </section>
    </div>
  );
}
