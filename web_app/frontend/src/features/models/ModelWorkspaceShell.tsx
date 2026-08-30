import type { ReactNode } from "react";
import { Link } from "@tanstack/react-router";

import { PanelToggleIcon } from "../../shared/ui";
import { useStoredBoolean } from "../../shared/useStoredBoolean";
import type { ModelDetail } from "./api";

export type ModelStage =
  | "overview"
  | "scope"
  | "profiling"
  | "analysis"
  | "assertions"
  | "conceptual"
  | "logical"
  | "dimensional"
  | "settings-prompts";

export function ModelWorkspaceShell({
  model,
  activeStage,
  children,
}: {
  model: ModelDetail;
  activeStage: ModelStage;
  children: ReactNode;
}) {
  const tenantId = String(model.tenant_id);
  const modelId = String(model.model_id);
  const [modelJourneyCollapsed, setModelJourneyCollapsed] = useStoredBoolean(
    "gds-workbench:model-journey-collapsed",
  );
  const modelJourneyAction = modelJourneyCollapsed
    ? "Expand model journey"
    : "Collapse model journey";

  return (
    <main className="workspace workspace-model">
      <div className={`model-layout${modelJourneyCollapsed ? " is-model-journey-collapsed" : ""}`}>
        <aside
          className="model-rail"
          aria-label="Model journey"
          data-collapsed={modelJourneyCollapsed}
        >
          <div className="model-rail-header">
            <button
              aria-controls="model-journey-links"
              aria-expanded={!modelJourneyCollapsed}
              aria-label={modelJourneyAction}
              className="model-journey-toggle"
              onClick={() => setModelJourneyCollapsed((collapsed) => !collapsed)}
              title={modelJourneyAction}
              type="button"
            >
              <PanelToggleIcon collapsed={modelJourneyCollapsed} />
              <span>{modelJourneyCollapsed ? "Show" : "Hide"}</span>
            </button>
          </div>
          <nav id="model-journey-links">
            <Link
              aria-label="Overview"
              className={`model-step${activeStage === "overview" ? " is-active" : ""}`}
              to="/tenants/$tenantId/models/$modelId"
              params={{ tenantId, modelId }}
              activeOptions={{ exact: true }}
              title="Overview — Workflow ledger"
            >
              <i>0</i><span><strong>Overview</strong><small>Workflow ledger</small></span>
            </Link>
            <Link
              aria-label="Scope"
              className={`model-step${activeStage === "scope" ? " is-active" : ""}`}
              to="/tenants/$tenantId/models/$modelId/scope"
              params={{ tenantId, modelId }}
              title={`Scope — ${model.model_scope_object_count} Objects`}
            >
              <i>1</i><span><strong>Scope</strong><small>{model.model_scope_object_count} Objects</small></span>
            </Link>
            <Link
              aria-label="Profiling"
              className={`model-step${activeStage === "profiling" ? " is-active" : ""}`}
              to="/tenants/$tenantId/models/$modelId/profiling"
              params={{ tenantId, modelId }}
              title="Profiling — Run evidence"
            >
              <i>2</i><span><strong>Profiling</strong><small>Run evidence</small></span>
            </Link>
            <Link
              aria-label="Analysis"
              className={`model-step${activeStage === "analysis" ? " is-active" : ""}`}
              to="/tenants/$tenantId/models/$modelId/analysis"
              params={{ tenantId, modelId }}
              title="Analysis — Relationship evidence"
            >
              <i>3</i><span><strong>Analysis</strong><small>Relationship evidence</small></span>
            </Link>
            <Link
              aria-label="Assertions"
              className={`model-step${activeStage === "assertions" ? " is-active" : ""}`}
              to="/tenants/$tenantId/models/$modelId/assertions"
              params={{ tenantId, modelId }}
              title="Assertions — Modeling assertions"
            >
              <i>4</i><span><strong>Assertions</strong><small>Modeling assertions</small></span>
            </Link>
            <Link
              aria-label="Conceptual"
              className={`model-step${activeStage === "conceptual" ? " is-active" : ""}`}
              to="/tenants/$tenantId/models/$modelId/conceptual"
              params={{ tenantId, modelId }}
              title="Conceptual — Objects and relationships"
            >
              <i>5</i><span><strong>Conceptual</strong><small>Objects and relationships</small></span>
            </Link>
            <Link
              aria-label="Logical"
              className={`model-step${activeStage === "logical" ? " is-active" : ""}`}
              to="/tenants/$tenantId/models/$modelId/logical"
              params={{ tenantId, modelId }}
              title="Logical — Normalized model"
            >
              <i>6</i><span><strong>Logical</strong><small>Normalized model</small></span>
            </Link>
            <Link
              aria-label="Dimensional"
              className={`model-step${activeStage === "dimensional" ? " is-active" : ""}`}
              to="/tenants/$tenantId/models/$modelId/dimensional"
              params={{ tenantId, modelId }}
              title="Dimensional — Dimensional records"
            >
              <i>7</i><span><strong>Dimensional</strong><small>Dimensional records</small></span>
            </Link>
            <Link
              aria-label="Settings"
              className={`model-step${activeStage === "settings-prompts" ? " is-active" : ""}`}
              to="/tenants/$tenantId/models/$modelId/settings/prompts"
              params={{ tenantId, modelId }}
              title="Settings — Prompts"
            >
              <i>8</i><span><strong>Settings</strong><small>Prompts</small></span>
            </Link>
          </nav>
          <div className="model-rail-note">
            <strong>Evidence, never blocking</strong>
            <span>Each later workflow stays user-driven.</span>
          </div>
        </aside>
        <section className="model-workspace">{children}</section>
      </div>
    </main>
  );
}
