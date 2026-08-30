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
  PanelToggleIcon,
  PromptsIcon,
} from "../shared/ui";
import { useStoredBoolean } from "../shared/useStoredBoolean";

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
  const [globalNavigationCollapsed, setGlobalNavigationCollapsed] = useStoredBoolean(
    "gds-workbench:workspace-navigation-collapsed",
  );
  const globalNavigationAction = globalNavigationCollapsed
    ? "Expand workspace navigation"
    : "Collapse workspace navigation";

  return (
    <div className={`app-shell page-enter${globalNavigationCollapsed ? " is-global-nav-collapsed" : ""}`}>
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
          <button
            aria-controls="workspace-navigation-links"
            aria-expanded={!globalNavigationCollapsed}
            aria-label={globalNavigationAction}
            className="mobile-sidebar-toggle"
            onClick={() => setGlobalNavigationCollapsed((collapsed) => !collapsed)}
            title={globalNavigationAction}
            type="button"
          >
            <PanelToggleIcon collapsed={globalNavigationCollapsed} />
          </button>
          <Link className="button button-secondary switch-tenant" to="/">
            Switch Tenant
          </Link>
          <span className="role-badge">{roleLabel(home.tenant.effective_role)}</span>
          <Avatar name={home.tenant.tenant_name} />
        </div>
      </header>

      <aside
        className="sidebar"
        aria-label="Workspace navigation"
        data-collapsed={globalNavigationCollapsed}
      >
        <div className="sidebar-header">
          <button
            aria-controls="workspace-navigation-links"
            aria-expanded={!globalNavigationCollapsed}
            aria-label={globalNavigationAction}
            className="sidebar-toggle"
            onClick={() => setGlobalNavigationCollapsed((collapsed) => !collapsed)}
            title={globalNavigationAction}
            type="button"
          >
            <PanelToggleIcon collapsed={globalNavigationCollapsed} />
            <span>{globalNavigationCollapsed ? "Show" : "Hide"}</span>
          </button>
        </div>
        <nav id="workspace-navigation-links">
          <Link
            aria-label="Home"
            className={`nav-item${activeNav === "home" ? " is-active" : ""}`}
            data-short-label="Home"
            to="/tenants/$tenantId"
            params={{ tenantId }}
            activeOptions={{ exact: true }}
            title="Home"
          >
            <HomeIcon /><span className="nav-item-label">Home</span>
          </Link>
          <Link
            aria-label="Metadata"
            className={`nav-item${activeNav === "metadata" ? " is-active" : ""}`}
            data-short-label="Metadata"
            to="/tenants/$tenantId/metadata"
            params={{ tenantId }}
            title="Metadata"
          >
            <DatabaseIcon /><span className="nav-item-label">Metadata</span>
          </Link>
          <Link
            aria-label="Models"
            className={`nav-item${activeNav === "models" ? " is-active" : ""}`}
            data-short-label="Models"
            to="/tenants/$tenantId/models"
            params={{ tenantId }}
            title="Models"
          >
            <ModelIcon /><span className="nav-item-label">Models</span>
          </Link>
          <Link
            aria-label="Mapping"
            className={`nav-item${activeNav === "mapping" ? " is-active" : ""}`}
            data-short-label="Mapping"
            to="/tenants/$tenantId/mapping"
            params={{ tenantId }}
            title="Mapping"
          >
            <MappingIcon /><span className="nav-item-label">Mapping</span>
          </Link>
          <Link
            aria-label="Code generation"
            className={`nav-item${activeNav === "code-generation" ? " is-active" : ""}`}
            data-short-label="Code"
            to="/tenants/$tenantId/code-generation"
            params={{ tenantId }}
            title="Code generation"
          >
            <CodeIcon /><span className="nav-item-label">Code generation</span>
          </Link>
          <Link
            aria-label="Prompts"
            className={`nav-item${activeNav === "prompts" ? " is-active" : ""}`}
            data-short-label="Prompts"
            to="/tenants/$tenantId/prompts"
            params={{ tenantId }}
            title="Prompts"
          >
            <PromptsIcon /><span className="nav-item-label">Prompts</span>
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
