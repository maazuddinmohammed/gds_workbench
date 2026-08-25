import type { ReactNode } from "react";
import { Link } from "@tanstack/react-router";

import type { ModelDetail } from "../features/models/api";
import type { TenantHomeRecord } from "../features/tenants/api";
import { roleLabel } from "../features/tenants/presentation";
import {
  Avatar,
  Brand,
  CodeIcon,
  DatabaseIcon,
  HomeIcon,
  MappingIcon,
  ModelIcon,
  PromptsIcon,
} from "../shared/ui";

export type WorkspaceNavigation =
  | "home"
  | "metadata"
  | "models"
  | "mapping"
  | "code-generation"
  | "prompts";

export function TenantWorkspace({
  home,
  activeNav,
  model,
  children,
}: {
  home: TenantHomeRecord;
  activeNav: WorkspaceNavigation;
  model?: ModelDetail;
  children: ReactNode;
}) {
  const tenantId = String(home.tenant.tenant_id);
  return (
    <div className="app-shell page-enter">
      <header className="topbar">
        <Brand compact />
        <div className="tenant-context">
          <strong className="tenant-context-name">{home.tenant.tenant_name}</strong>
          <span className="tenant-code-badge">{home.tenant.tenant_code}</span>
          {model ? (
            <>
              <span className="context-divider" aria-hidden="true" />
              <small>Model</small>
              <strong className="model-context-name">{model.model_name}</strong>
              <span className="tenant-code-badge">r{model.model_revision}</span>
            </>
          ) : null}
        </div>
        <div className="topbar-actions">
          <Link className="button button-secondary switch-tenant" to="/">
            Switch Tenant
          </Link>
          <span className="role-badge">{roleLabel(home.tenant.effective_role)}</span>
          <Avatar name={home.tenant.tenant_name} />
        </div>
      </header>

      <aside className="sidebar" aria-label="Workspace navigation">
        <p className="sidebar-label">Workspace</p>
        <nav>
          <Link
            aria-label="Home"
            className={`nav-item${activeNav === "home" ? " is-active" : ""}`}
            data-short-label="Home"
            to="/tenants/$tenantId"
            params={{ tenantId }}
            activeOptions={{ exact: true }}
          >
            <HomeIcon />Home
          </Link>
          <Link
            aria-label="Metadata"
            className={`nav-item${activeNav === "metadata" ? " is-active" : ""}`}
            data-short-label="Metadata"
            to="/tenants/$tenantId/metadata"
            params={{ tenantId }}
          >
            <DatabaseIcon />Metadata
          </Link>
          <Link
            aria-label="Models"
            className={`nav-item${activeNav === "models" ? " is-active" : ""}`}
            data-short-label="Models"
            to="/tenants/$tenantId/models"
            params={{ tenantId }}
          >
            <ModelIcon />Models
          </Link>
          <Link
            aria-label="Mapping"
            className={`nav-item${activeNav === "mapping" ? " is-active" : ""}`}
            data-short-label="Mapping"
            to="/tenants/$tenantId/mapping"
            params={{ tenantId }}
          >
            <MappingIcon />Mapping
          </Link>
          <Link
            aria-label="Code generation"
            className={`nav-item${activeNav === "code-generation" ? " is-active" : ""}`}
            data-short-label="Code"
            to="/tenants/$tenantId/code-generation"
            params={{ tenantId }}
          >
            <CodeIcon />Code generation
          </Link>
          <Link
            aria-label="Prompts"
            className={`nav-item${activeNav === "prompts" ? " is-active" : ""}`}
            data-short-label="Prompts"
            to="/tenants/$tenantId/prompts"
            params={{ tenantId }}
          >
            <PromptsIcon />Prompts
          </Link>
        </nav>
        {model ? (
          <div className="open-model">
            <small>Open Model</small>
            <strong>{model.model_name}</strong>
            <span>Owner · {home.tenant.tenant_name}</span>
            <Link
              to="/tenants/$tenantId/models/$modelId"
              params={{ tenantId, modelId: String(model.model_id) }}
              activeOptions={{ exact: true }}
            >
              Model overview →
            </Link>
          </div>
        ) : null}
      </aside>
      {children}
    </div>
  );
}
