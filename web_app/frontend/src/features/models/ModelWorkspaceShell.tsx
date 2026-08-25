import type { ReactNode } from "react";
import { Link } from "@tanstack/react-router";

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

  return (
    <main className="workspace workspace-model">
      <div className="model-layout">
        <aside className="model-rail" aria-label="Model journey">
          <div className="model-rail-title">
            <small>Model journey</small>
            <strong>{model.model_name}</strong>
            <span>Revision {model.model_revision}</span>
          </div>
          <nav>
            <Link
              className={`model-step${activeStage === "overview" ? " is-active" : ""}`}
              to="/tenants/$tenantId/models/$modelId"
              params={{ tenantId, modelId }}
              activeOptions={{ exact: true }}
            >
              <i>0</i><span><strong>Overview</strong><small>Workflow ledger</small></span>
            </Link>
            <Link
              className={`model-step${activeStage === "scope" ? " is-active" : ""}`}
              to="/tenants/$tenantId/models/$modelId/scope"
              params={{ tenantId, modelId }}
            >
              <i>1</i><span><strong>Scope</strong><small>{model.model_scope_object_count} Objects</small></span>
            </Link>
            <Link
              className={`model-step${activeStage === "profiling" ? " is-active" : ""}`}
              to="/tenants/$tenantId/models/$modelId/profiling"
              params={{ tenantId, modelId }}
            >
              <i>2</i><span><strong>Profiling</strong><small>Run evidence</small></span>
            </Link>
            <Link
              className={`model-step${activeStage === "analysis" ? " is-active" : ""}`}
              to="/tenants/$tenantId/models/$modelId/analysis"
              params={{ tenantId, modelId }}
            >
              <i>3</i><span><strong>Analysis</strong><small>Relationship evidence</small></span>
            </Link>
            <Link
              className={`model-step${activeStage === "assertions" ? " is-active" : ""}`}
              to="/tenants/$tenantId/models/$modelId/assertions"
              params={{ tenantId, modelId }}
            >
              <i>4</i><span><strong>Assertions</strong><small>Modeling assertions</small></span>
            </Link>
            <Link
              className={`model-step${activeStage === "conceptual" ? " is-active" : ""}`}
              to="/tenants/$tenantId/models/$modelId/conceptual"
              params={{ tenantId, modelId }}
            >
              <i>5</i><span><strong>Conceptual</strong><small>Objects and relationships</small></span>
            </Link>
            <Link
              className={`model-step${activeStage === "logical" ? " is-active" : ""}`}
              to="/tenants/$tenantId/models/$modelId/logical"
              params={{ tenantId, modelId }}
            >
              <i>6</i><span><strong>Logical</strong><small>Normalized model</small></span>
            </Link>
            <Link
              className={`model-step${activeStage === "dimensional" ? " is-active" : ""}`}
              to="/tenants/$tenantId/models/$modelId/dimensional"
              params={{ tenantId, modelId }}
            >
              <i>7</i><span><strong>Dimensional</strong><small>Dimensional records</small></span>
            </Link>
            <Link
              className={`model-step${activeStage === "settings-prompts" ? " is-active" : ""}`}
              to="/tenants/$tenantId/models/$modelId/settings/prompts"
              params={{ tenantId, modelId }}
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
