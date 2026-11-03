import { useEffect, useRef, useState, type ReactNode } from "react";

/**
 * The right-hand panel Activity and the Entity quick view share: a title and subtitle, the
 * caller's actions, then Expand/Reduce and Close. It opens with focus on Close, and Escape
 * closes it unless a dialog inside handles the key. Callers return focus when it closes.
 */
export function SidePanel({ id, labels, title, subtitle, actions, className, onClose, children }: {
  id?: string;
  /** Accessible names: the panel, and its Close, Expand and Reduce buttons. */
  labels: { panel: string; close: string; expand: string; reduce: string };
  title: ReactNode;
  subtitle: ReactNode;
  actions?: ReactNode;
  className?: string;
  onClose: () => void;
  children: ReactNode;
}) {
  const close = useRef<HTMLButtonElement>(null);
  const [wide, setWide] = useState(false);
  useEffect(() => close.current?.focus({ preventScroll: true }), []);
  return <aside id={id} className={["workflow-activity-panel", className, wide ? "is-wide" : null].filter(Boolean).join(" ")}
    aria-label={labels.panel} onKeyDown={(event) => {
      if (event.key === "Escape" && !(event.target as HTMLElement).closest('[role="dialog"]')) {
        event.stopPropagation(); onClose();
      }
    }}>
    <header className="workflow-activity-heading">
      <div><h2>{title}</h2><span>{subtitle}</span></div>
      <div className="workflow-activity-actions">{actions}
        <button type="button" className="button button-secondary button-small" aria-label={wide ? labels.reduce : labels.expand}
          onClick={() => setWide(!wide)}>{wide ? "Reduce" : "Expand"}</button>
        <button ref={close} type="button" className="panel-close" aria-label={labels.close} onClick={onClose}>×</button>
      </div>
    </header>
    <div className="workflow-activity-body">{children}</div>
  </aside>;
}
