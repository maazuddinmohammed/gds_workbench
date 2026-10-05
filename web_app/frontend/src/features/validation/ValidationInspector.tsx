import { useEffect, useRef, useState, type ReactNode } from "react";
import { createPortal } from "react-dom";

export function ValidationInspector({ children, onClose, returnFocus }: {
  children: ReactNode;
  onClose: () => void;
  returnFocus: HTMLElement | null;
}) {
  const close = useRef<HTMLButtonElement>(null);
  const [expanded, setExpanded] = useState(false);
  useEffect(() => {
    close.current?.focus();
    return () => { if (returnFocus?.isConnected) returnFocus.focus({ preventScroll: true }); };
  }, [returnFocus]);

  return createPortal(<aside className={`workflow-activity-panel validation-inspector${expanded ? " is-wide" : ""}`}
    aria-label="Validation details" onKeyDown={(event) => {
      if (event.key === "Escape" && !(event.target as HTMLElement).closest('[role="dialog"]')) {
        event.stopPropagation(); onClose();
      }
    }}>
    <header className="workflow-activity-heading">
      <h2>Validation details</h2>
      <div className="workflow-activity-actions">
        <button type="button" className="button button-secondary button-small validation-expand"
          aria-label={expanded ? "Reduce Validation details" : "Expand Validation details"}
          title={expanded ? "Reduce" : "Expand"} onClick={() => setExpanded(!expanded)}>
          <svg aria-hidden="true" viewBox="0 0 24 24"><rect x="4" y="4" width="16" height="16" rx="2" />
            <path d={expanded ? "M9 4v16M13 12h4" : "M9 4v16M12 12h5m-2-2 2 2-2 2"} /></svg>
        </button>
        <button ref={close} type="button" className="panel-close" aria-label="Close Validation details" onClick={onClose}>×</button>
      </div>
    </header>
    <div className="workflow-activity-body validation-inspector-body">{children}</div>
  </aside>, returnFocus?.closest(".app-shell") ?? document.body);
}
