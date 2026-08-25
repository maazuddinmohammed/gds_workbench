import { Link } from "@tanstack/react-router";

import { initials } from "./presentation";

export function Brand({ compact = false }: { compact?: boolean }) {
  return (
    <div className={compact ? "brand is-compact" : "brand"} aria-label="GDS Workbench">
      <span className="brand-mark">G</span>
      <strong>GDS</strong>
      <span>Workbench</span>
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

export function ErrorPage() {
  return (
    <main className="message-page">
      <p className="eyebrow">GDS Workbench</p>
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

export function SearchIcon() {
  return (
    <svg aria-hidden="true" viewBox="0 0 24 24">
      <circle cx="11" cy="11" r="6" />
      <path d="m16 16 4 4" />
    </svg>
  );
}

export function HomeIcon() {
  return <NavIcon path="M4 10.5 12 4l8 6.5V20h-5v-6H9v6H4z" />;
}

export function DatabaseIcon() {
  return <NavIcon path="M5 6c0-2 14-2 14 0v12c0 2-14 2-14 0zm0 0c0 2 14 2 14 0M5 12c0 2 14 2 14 0" />;
}

export function ModelIcon() {
  return <NavIcon path="M5 5h5v5H5zm9 0h5v5h-5zM9 14h6v5H9zm3-4v4M10 8h4" />;
}

export function MappingIcon() {
  return <NavIcon path="M4 7h13m-3-3 3 3-3 3m6 7H7m3-3-3 3 3 3" />;
}

export function CodeIcon() {
  return <NavIcon path="m9 5-6 7 6 7m6-14 6 7-6 7" />;
}

export function PromptsIcon() {
  return <NavIcon path="M5 5h14v10H9l-4 4zm4 4h6m-6 3h4" />;
}

function NavIcon({ path }: { path: string }) {
  return (
    <svg aria-hidden="true" viewBox="0 0 24 24">
      <path d={path} />
    </svg>
  );
}
