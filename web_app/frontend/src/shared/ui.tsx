import type { ReactNode } from "react";
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

export function ModelIcon() {
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
