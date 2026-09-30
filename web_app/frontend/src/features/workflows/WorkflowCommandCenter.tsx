import { createContext, useContext, useEffect, useId, useRef, useState, type ReactNode } from "react";
import { createPortal } from "react-dom";

// Presentation state only. Existing screens still own queries and governed commands.
export const WorkflowCommandContext = createContext<{
  filtersOpen: boolean;
  setFiltersOpen: (open: boolean) => void;
  filterId: string;
  filterCount: number;
  activityHost: HTMLSpanElement | null;
  setActivityHost: (host: HTMLSpanElement | null) => void;
} | null>(null);

export function WorkflowCommandCenter({ children, className, filterCount = 0, enabled = true }: {
  children: ReactNode; className: string; filterCount?: number; enabled?: boolean;
}) {
  const [filtersOpen, setFiltersOpen] = useState(false);
  const [activityHost, setActivityHost] = useState<HTMLSpanElement | null>(null);
  const filterId = useId();
  return <WorkflowCommandContext.Provider value={enabled ? {
    filtersOpen, setFiltersOpen, filterId, filterCount, activityHost, setActivityHost,
  } : null}>
    <div className={`${className}${enabled ? " workflow-command-center" : ""}`}>{children}</div>
  </WorkflowCommandContext.Provider>;
}

export function WorkflowCommandTools({ filters = true }: { filters?: boolean }) {
  const context = useContext(WorkflowCommandContext);
  if (!context) return null;
  return <>
    {filters ? <button type="button" className="button button-secondary button-small workflow-filter-toggle"
      aria-expanded={context.filtersOpen} aria-controls={context.filterId}
      onClick={() => context.setFiltersOpen(!context.filtersOpen)}>
      <svg aria-hidden="true" viewBox="0 0 24 24"><path d="M4 6h16M7 12h10M10 18h4" /></svg>
      Filters{context.filterCount > 0 ? <span className="command-count">{context.filterCount}</span> : null}
    </button> : null}
    <span className="workflow-activity-slot" ref={context.setActivityHost} />
  </>;
}

export function WorkflowFilters({ children }: { children: ReactNode }) {
  const context = useContext(WorkflowCommandContext);
  if (!context) return children;
  return <div id={context.filterId} className="workflow-filter-panel" hidden={!context.filtersOpen}>{children}</div>;
}

export function WorkflowMenu({ label = "More", children, primary = false }: {
  label?: string; children: ReactNode; primary?: boolean;
}) {
  const menu = useRef<HTMLDetailsElement>(null);
  useEffect(() => {
    const closeOutside = (event: PointerEvent) => {
      const element = menu.current;
      if (element?.open && !element.contains(event.target as Node)
        && !document.querySelector('[role="dialog"]')) element.open = false;
    };
    document.addEventListener("pointerdown", closeOutside);
    return () => document.removeEventListener("pointerdown", closeOutside);
  }, []);
  return <details ref={menu} className="workflow-command-menu" onKeyDown={(event) => {
    if (event.key === "Escape" && !(event.target as HTMLElement).closest('[role="dialog"]')) {
      event.preventDefault(); event.stopPropagation();
      if (menu.current) { menu.current.open = false; menu.current.querySelector("summary")?.focus(); }
    }
  }}>
    <summary className={`button button-${primary ? "primary" : "secondary"} button-small`}>
      {label}<svg aria-hidden="true" viewBox="0 0 24 24"><path d="m7 10 5 5 5-5" /></svg>
    </summary>
    <div className="workflow-command-menu-content">{children}</div>
  </details>;
}

export function WorkflowActivityPanel({ label, open, onOpenChange, actions, children }: {
  label: string; open: boolean; onOpenChange: (open: boolean) => void;
  actions?: ReactNode; children: ReactNode;
}) {
  const context = useContext(WorkflowCommandContext);
  const panelId = useId();
  const trigger = useRef<HTMLButtonElement>(null);
  const close = useRef<HTMLButtonElement>(null);
  const [wide, setWide] = useState(false);
  useEffect(() => {
    if (!open) return;
    const previous = document.activeElement;
    close.current?.focus({ preventScroll: true });
    return () => {
      const target = trigger.current ?? previous;
      if (target instanceof HTMLElement && target.isConnected) target.focus({ preventScroll: true });
    };
  }, [open]);
  const toggle = <button ref={trigger} type="button" className="button button-secondary button-small workflow-activity-toggle"
    aria-label={`Show ${label} run activity`} aria-expanded={open} aria-controls={panelId}
    onClick={() => onOpenChange(!open)}>
    <svg aria-hidden="true" viewBox="0 0 24 24"><circle cx="12" cy="12" r="8" /><path d="M12 7v5l3 2" /></svg>Activity
  </button>;
  return <>
    {context?.activityHost ? createPortal(toggle, context.activityHost) : toggle}
    {open ? <aside id={panelId} className={`workflow-activity-panel${wide ? " is-wide" : ""}`}
      aria-label={`${label} activity`} onKeyDown={(event) => {
        if (event.key === "Escape" && !(event.target as HTMLElement).closest('[role="dialog"]')) {
          event.stopPropagation(); onOpenChange(false);
        }
      }}>
      <header className="workflow-activity-heading">
        <div><h2>{label} activity</h2><span>Run history and details</span></div>
        <div className="workflow-activity-actions">{actions}
          <button type="button" className="button button-secondary button-small" aria-label={wide ? "Reduce activity panel" : "Expand activity panel"}
            onClick={() => setWide(!wide)}>{wide ? "Reduce" : "Expand"}</button>
          <button ref={close} type="button" className="panel-close" aria-label="Close activity" onClick={() => onOpenChange(false)}>×</button>
        </div>
      </header>
      <div className="workflow-activity-body">{children}</div>
    </aside> : null}
  </>;
}
