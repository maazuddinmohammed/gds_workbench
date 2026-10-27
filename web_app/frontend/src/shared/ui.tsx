import type { ReactNode, Ref } from "react";
import { Link } from "@tanstack/react-router";

import atlasMarkUrl from "../../public/assets/atlas.svg?no-inline";
import type { SubjectAreaBuild } from "./contracts";
import { formatRequiredDateTime, initials } from "./presentation";

export function SelectAllCheckbox({ label, selectedCount, totalCount, disabled, onChange }: {
  label: string;
  selectedCount: number;
  totalCount: number;
  disabled?: boolean;
  onChange: (checked: boolean) => void;
}) {
  return <input type="checkbox" aria-label={label}
    checked={totalCount > 0 && selectedCount === totalCount}
    ref={(element) => { if (element) element.indeterminate = selectedCount > 0 && selectedCount < totalCount; }}
    disabled={disabled || totalCount === 0}
    onChange={(event) => onChange(event.target.checked)} />;
}

export function WorkspaceToolbar({ children, actions }: {
  children?: ReactNode;
  actions: ReactNode;
}) {
  return <header className="workspace-toolbar">
    {children ? <div className="workflow-command-context">{children}</div> : null}
    <div className="workflow-command-actions">{actions}</div>
  </header>;
}

export function Brand({ compact = false }: { compact?: boolean }) {
  return (
    <div className={compact ? "brand is-compact" : "brand"} aria-label="Atlas">
      <img className="brand-mark" src={atlasMarkUrl} width="32" height="32" alt="" />
      <strong>ATLAS</strong>
    </div>
  );
}

export function Avatar({ name, large = false }: { name: string; large?: boolean }) {
  return <span className={large ? "avatar is-large" : "avatar"}>{initials(name)}</span>;
}

export function LoadingPage({ label }: { label: string }) {
  return (
    <main className="message-page" aria-busy="true">
      <span className="loading-mark" aria-hidden="true" />
      <p>{label}…</p>
    </main>
  );
}

export function DetailState({ label, error = false }: { label: string; error?: boolean }) {
  return (
    <div
      className={`surface-state detail-state${error ? " is-error" : ""}`}
      {...(error ? { role: "alert" } : { "aria-busy": true })}
    >
      {label}
    </div>
  );
}

export function ErrorPage() {
  return (
    <main className="message-page">
      <Brand />
      <h1>Workspace unavailable</h1>
      <p>The requested information could not be loaded.</p>
      <Link className="button button-primary" to="/">Choose a Tenant</Link>
    </main>
  );
}

export function StatusBadge({ value }: { value: string | null }) {
  if (!value) return <span className="status-badge is-neutral">No runs</span>;
  const normalized = value.toLocaleLowerCase();
  const tone = normalized === "completed"
    ? "is-success"
    : normalized === "failed"
      ? "is-danger"
      : "is-neutral";
  return <span className={`status-badge ${tone}`}>{value.replaceAll("_", " ")}</span>;
}

// The Project ribbon's status circles, plus an amber clock for a draft waiting for Apply.
const BUILD_STATES: Record<SubjectAreaBuild["state"], { label: string; tone: string; path: string | null }> = {
  applied: { label: "Applied", tone: "is-complete", path: "m4 8 2.5 2.5L12 5" },
  draft_waiting: { label: "Draft waiting for Apply", tone: "is-waiting", path: "M8 4.5V8l2.2 1.4" },
  running: { label: "Build running", tone: "is-running", path: null },
  failed: { label: "Last Build failed", tone: "is-failed", path: "M8 4v4M8 11v.2" },
  not_built: { label: "Not built yet", tone: "is-neutral", path: null },
};

/**
 * A Subject Area's last Build as one status circle. Its words show on hover and to screen
 * readers; showLabel prints them where there is room, such as detail pages.
 */
export function BuildStatus({ build, showLabel = false }: { build: SubjectAreaBuild; showLabel?: boolean }) {
  const state = BUILD_STATES[build.state];
  const text = build.at ? `${state.label} · ${formatRequiredDateTime(build.at)}` : state.label;
  return <span className={`build-status ${state.tone}`} title={text}>
    <span className="build-status-icon" aria-hidden="true">
      {state.path ? <svg viewBox="0 0 16 16"><path d={state.path} /></svg> : null}
    </span>
    <span className={showLabel ? undefined : "sr-only"}>{text}</span>
  </span>;
}

export function Fact({ label, value, code = false }: { label: string; value: string; code?: boolean }) {
  return <div><dt>{label}</dt><dd>{code ? <code title={value}>{value}</code> : value}</dd></div>;
}

export function SelectField({
  label,
  value,
  options,
  onChange,
}: {
  label: string;
  value: string;
  options: [string, string][];
  onChange: (value: string) => void;
}) {
  return (
    <label>
      <span>{label}</span>
      <select aria-label={label} value={value} onChange={(event) => onChange(event.target.value)}>
        {options.some(([optionValue]) => optionValue === "") ? null : <option value="">Select…</option>}
        {options.map(([optionValue, optionLabel]) => (
          <option key={optionValue} value={optionValue}>{optionLabel}</option>
        ))}
      </select>
    </label>
  );
}

export function RefreshIcon() {
  return (
    <svg aria-hidden="true" viewBox="0 0 24 24">
      <path d="M20 7v5h-5M4 17v-5h5M5.5 8a7 7 0 0 1 11.7-3L20 8M4 16l2.8 3A7 7 0 0 0 18.5 16" />
    </svg>
  );
}

// Icon-only Refresh for command bars. Its name stays "Refresh" (or "Refreshing…") for screen
// readers and tooltips; the arrows spin while a refresh is running.
export function RefreshButton({ refreshing, disabled = refreshing, onClick, label = "Refresh", ref }: {
  refreshing: boolean;
  disabled?: boolean;
  onClick: () => void;
  label?: string;
  ref?: Ref<HTMLButtonElement>;
}) {
  const name = refreshing ? "Refreshing…" : label;
  return <button ref={ref} className="button button-secondary button-small refresh-button" type="button"
    aria-label={name} title={name} aria-busy={refreshing} disabled={disabled} onClick={onClick}>
    <RefreshIcon />
  </button>;
}

export function SearchIcon() {
  return (
    <svg aria-hidden="true" viewBox="0 0 24 24">
      <circle cx="11" cy="11" r="6" />
      <path d="m16 16 4 4" />
    </svg>
  );
}

export function HomeIcon() {
  return (
    <NavIcon>
      <path d="m3.5 10.5 8.5-7 8.5 7" />
      <path d="M5.5 9.25V20h13V9.25M9.5 20v-6h5v6" />
    </NavIcon>
  );
}

export function DatabaseIcon() {
  return (
    <NavIcon>
      <ellipse cx="12" cy="5.5" rx="7.5" ry="3" />
      <path d="M4.5 5.5v6c0 1.66 3.36 3 7.5 3s7.5-1.34 7.5-3v-6" />
      <path d="M4.5 11.5v6c0 1.66 3.36 3 7.5 3s7.5-1.34 7.5-3v-6" />
    </NavIcon>
  );
}

export function ProjectIcon() {
  return (
    <NavIcon>
      <path d="m12 3 8 4.25-8 4.25-8-4.25L12 3Z" />
      <path d="m4 12 8 4.25L20 12M4 16.75 12 21l8-4.25" />
    </NavIcon>
  );
}

export function MappingIcon() {
  return (
    <NavIcon>
      <circle cx="5" cy="12" r="2.25" />
      <circle cx="19" cy="6" r="2.25" />
      <circle cx="19" cy="18" r="2.25" />
      <path d="M7.25 12H10a4 4 0 0 0 4-4V6h2.75M10 12a4 4 0 0 1 4 4v2h2.75" />
    </NavIcon>
  );
}

export function CodeIcon() {
  return (
    <NavIcon>
      <path d="m8 8-4 4 4 4M16 8l4 4-4 4M14 4l-4 16" />
    </NavIcon>
  );
}

export function ValidationIcon() {
  return (
    <NavIcon>
      <path d="M12 3 20 6v5c0 5.1-3.1 8.4-8 10-4.9-1.6-8-4.9-8-10V6l8-3Z" />
      <path d="m8.5 12 2.2 2.2 4.8-5" />
    </NavIcon>
  );
}

export function PromptsIcon() {
  return (
    <NavIcon>
      <path d="M21 15a4 4 0 0 1-4 4H8l-5 3V7a4 4 0 0 1 4-4h10a4 4 0 0 1 4 4v8Z" />
      <path d="m8 9 2 2-2 2M13 13h3" />
    </NavIcon>
  );
}

export function PanelToggleIcon({ collapsed }: { collapsed: boolean }) {
  return (
    <NavIcon>
      <rect x="3" y="3" width="18" height="18" rx="2.5" />
      <path d="M9 3v18" />
      <path d={collapsed ? "m14 9 3 3-3 3" : "m16 9-3 3 3 3"} />
    </NavIcon>
  );
}

function NavIcon({ children }: { children: ReactNode }) {
  return (
    <svg aria-hidden="true" focusable="false" viewBox="0 0 24 24">
      {children}
    </svg>
  );
}
