import { useEffect, useId, useRef, useState, type ReactNode } from "react";
import { Link, useSearch } from "@tanstack/react-router";
import { useQuery, useQueryClient } from "@tanstack/react-query";

import { ProjectIcon, RefreshIcon } from "../../shared/ui";
import type { TenantLockState } from "../tenant_locks/api";
import type { ProjectDetail, ProjectsApi, ProjectSectionState } from "./api";

export type ProjectStage =
  | "overview" | "settings" | "settings-prompts" | "scope" | "metadata-enrichment"
  | "profiling" | "context" | "analysis" | "subject-area" | "logical"
  | "dimensional" | "mapping" | "code-generation" | "validation";

const stages = [
  { id: "overview", label: "Overview", to: "/tenants/$tenantId/projects/$projectId" },
  { id: "settings", label: "Settings", to: "/tenants/$tenantId/projects/$projectId/settings" },
  { id: "scope", label: "Input scope", to: "/tenants/$tenantId/projects/$projectId/input-scope", accessibleName: "Project Input Scope" },
  { id: "context", label: "Context", to: "/tenants/$tenantId/projects/$projectId/context" },
  { id: "profiling", label: "Profiling", to: "/tenants/$tenantId/projects/$projectId/profiling" },
  { id: "metadata-enrichment", label: "Enrichment", to: "/tenants/$tenantId/projects/$projectId/metadata-enrichment", accessibleName: "Metadata enrichment" },
  { id: "analysis", label: "Analysis", to: "/tenants/$tenantId/projects/$projectId/analysis" },
  { id: "subject-area", label: "Subject Areas", to: "/tenants/$tenantId/projects/$projectId/subject-areas" },
  { id: "logical", label: "Logical", to: "/tenants/$tenantId/projects/$projectId/logical" },
  { id: "dimensional", label: "Dimensional", to: "/tenants/$tenantId/projects/$projectId/dimensional" },
  { id: "mapping", label: "Mapping", to: "/tenants/$tenantId/mapping/projects/$projectId" },
  { id: "code-generation", label: "Code generation", to: "/tenants/$tenantId/code-generation/projects/$projectId" },
  { id: "validation", label: "Validation", to: "/tenants/$tenantId/validation/projects/$projectId" },
] as const;

export function ProjectWorkspaceShell({ api, project, activeStage, tenantLock, lockControl, children }: {
  api: Pick<ProjectsApi, "readProjectOverview">;
  project: ProjectDetail;
  activeStage: ProjectStage;
  tenantLock: TenantLockState;
  lockControl?: ReactNode;
  children: ReactNode;
}) {
  const statusId = useId();
  const client = useQueryClient();
  const overview = useQuery({
    queryKey: ["project-overview", project.tenant_id, project.project_id],
    queryFn: () => api.readProjectOverview(project.tenant_id, project.project_id),
  });
  const previousRevision = useRef(project.project_revision);
  useEffect(() => {
    if (previousRevision.current !== project.project_revision) {
      previousRevision.current = project.project_revision;
      void client.invalidateQueries({ queryKey: ["project-overview", project.tenant_id, project.project_id] });
    }
  }, [client, project.project_id, project.project_revision, project.tenant_id]);
  const statusLabels: Record<ProjectSectionState["state"], string> = {
    available: "Available", ready: "Ready", empty: "Not set", not_run: "Not run",
    queued: "Queued", running: "Running", completed: "Completed", failed: "Failed", cancelled: "Cancelled",
    results_available: "Results available",
  };
  const currentStates = !overview.isError && overview.data?.project_revision === project.project_revision
    && overview.data.project_id === project.project_id ? overview.data.section_states : undefined;
  const navigation = useRef<HTMLElement>(null);
  const highlightedTab = useRef<HTMLAnchorElement | null>(null);
  const [highlight, setHighlight] = useState<{ left: number; width: number; visible: boolean } | null>(null);
  const [scrollAvailable, setScrollAvailable] = useState({ left: false, right: false });
  const search = useSearch({ strict: false });
  const layer = activeStage === "dimensional" ? "dimensional"
    : activeStage === "logical" ? "logical" : search.layer;
  const active = activeStage === "settings-prompts" ? "settings" : activeStage;
  const params = { tenantId: String(project.tenant_id), projectId: String(project.project_id) };
  const lockLabel = tenantLock.owned_by_current_principal
    ? "Tenant Lock held by you"
    : tenantLock.is_locked ? `Tenant Lock held by ${tenantLock.owner_display_name ?? "another Principal"}`
      : "Tenant Lock available";

  const highlightTab = (tab: HTMLAnchorElement | null) => {
    highlightedTab.current = tab;
    setHighlight((previous) => tab
      ? { left: tab.offsetLeft, width: tab.offsetWidth, visible: true }
      : previous ? { ...previous, visible: false } : null);
  };

  useEffect(() => {
    const strip = navigation.current;
    if (!strip) return;
    const updateScrollControls = () => setScrollAvailable({
      left: strip.scrollLeft > 1,
      right: strip.scrollLeft + strip.clientWidth < strip.scrollWidth - 1,
    });
    const revealActive = () => {
      const current = strip.querySelector<HTMLElement>('[aria-current="page"]');
      if (current && typeof strip.scrollTo === "function") {
        // Keep the active section visible after navigation or viewport resizing.
        const left = current.offsetLeft;
        if (left < strip.scrollLeft) strip.scrollTo({ left });
        else if (left + current.offsetWidth > strip.scrollLeft + strip.clientWidth) {
          strip.scrollTo({ left: left + current.offsetWidth - strip.clientWidth });
        }
      }
      const hovered = highlightedTab.current;
      if (hovered) setHighlight({ left: hovered.offsetLeft, width: hovered.offsetWidth, visible: true });
      updateScrollControls();
    };
    revealActive();
    strip.addEventListener("scroll", updateScrollControls, { passive: true });
    const resize = typeof ResizeObserver === "undefined" ? null : new ResizeObserver(revealActive);
    resize?.observe(strip);
    return () => {
      strip.removeEventListener("scroll", updateScrollControls);
      resize?.disconnect();
    };
  }, [active]);

  return (
    <div className="workspace workspace-project">
      <header className="project-identity">
        <div className="project-identity-main">
          <span className="project-identity-symbol"><ProjectIcon /></span>
          <div><strong className="project-identity-name">{project.project_name}</strong>
            {project.project_description ? <p>{project.project_description}</p> : null}
          </div>
        </div>
        <div className="project-identity-status">
          <span>Revision {project.project_revision}</span>
          {!project.is_active ? <span className="status-badge">Archived</span> : null}
          {project.is_locked ? <span className="status-badge">Project locked</span> : null}
          {lockControl ?? <span className={tenantLock.owned_by_current_principal ? "project-lock is-held" : "project-lock"}>{lockLabel}</span>}
          <button className="project-status-refresh" type="button" aria-label="Refresh section status"
            title="Refresh section status" disabled={overview.isFetching}
            onClick={() => void Promise.all([
              overview.refetch(), client.invalidateQueries({ queryKey: ["project", project.tenant_id, project.project_id] }),
              client.invalidateQueries({ queryKey: ["tenant-home", project.tenant_id] }),
            ])}>
            <RefreshIcon />
          </button>
        </div>
      </header>
      <div className="project-navigation">
        <button className="project-navigation-scroll" type="button" aria-label="Scroll Project sections left" disabled={!scrollAvailable.left}
          onClick={() => navigation.current?.scrollBy({ left: -260 })}>
          <svg aria-hidden="true" viewBox="0 0 24 24"><path d="m15 6-6 6 6 6" /></svg>
        </button>
        <nav ref={navigation} aria-label="Project sections" className="project-tabs"
          onPointerLeave={() => {
            const focused = document.activeElement;
            highlightTab(focused instanceof HTMLAnchorElement && navigation.current?.contains(focused)
              && focused.matches(":focus-visible") ? focused : null);
          }}
          onBlur={(event) => {
            if (!event.currentTarget.contains(event.relatedTarget)) highlightTab(null);
          }}
          onKeyDown={(event) => {
            if (!(["ArrowLeft", "ArrowRight", "Home", "End"].includes(event.key))) return;
            const links = [...event.currentTarget.querySelectorAll<HTMLAnchorElement>("a")];
            const index = links.indexOf(event.target as HTMLAnchorElement);
            if (index < 0) return;
            event.preventDefault();
            const next = event.key === "Home" ? 0 : event.key === "End" ? links.length - 1
              : (index + (event.key === "ArrowRight" ? 1 : -1) + links.length) % links.length;
            links[next]?.focus();
          }}>
          {highlight ? <span aria-hidden="true" className={`project-tab-highlight${highlight.visible ? " is-visible" : ""}`}
            style={{ width: highlight.width, transform: `translateX(${highlight.left}px)` }} /> : null}
          {stages.map((stage) => {
            const isSetup = stage.id === "overview" || stage.id === "settings"
              || stage.id === "scope" || stage.id === "context";
            const state = currentStates?.find((entry) => entry.section === stage.id)?.state;
            const label = isSetup ? undefined : state === "empty" ? "Not run"
              : state ? statusLabels[state] ?? "Unavailable" : overview.isPending ? "Loading…" : "Unavailable";
            const tone = isSetup ? "is-neutral" : state === "completed" || state === "results_available" || state === "ready" ? "is-complete"
              : state === "failed" ? "is-failed" : state === "running" || state === "queued" ? "is-running" : "is-neutral";
            return <Link key={stage.id} to={stage.to} params={params}
            search={layer === undefined ? {} : { layer }}
            aria-label={"accessibleName" in stage ? stage.accessibleName : stage.label}
            aria-describedby={label ? `${statusId}-${stage.id}` : undefined}
            aria-current={active === stage.id ? "page" : undefined}
            activeOptions={{ exact: true }}
            onPointerEnter={(event) => { if (event.pointerType !== "touch") highlightTab(event.currentTarget); }}
            onFocus={(event) => highlightTab(event.currentTarget)}
            className={`project-tab${active === stage.id ? " is-active" : ""}${stage.id === "context" || stage.id === "analysis" || stage.id === "dimensional" ? " is-group-end" : ""}`}>
            <span className={`project-stage-circle ${tone}`} aria-hidden="true">
              {tone === "is-complete" ? <svg viewBox="0 0 16 16"><path d="m4 8 2.5 2.5L12 5" /></svg>
                : tone === "is-failed" ? <svg viewBox="0 0 16 16"><path d="M8 4v4M8 11v.2" /></svg> : null}
            </span>
            <span className="project-stage-label">{stage.label}</span>
            <span className={`project-stage-status ${tone}`} id={`${statusId}-${stage.id}`} aria-hidden={isSetup || undefined}>{label}</span>
          </Link>;
          })}
        </nav>
        <button className="project-navigation-scroll" type="button" aria-label="Scroll Project sections right" disabled={!scrollAvailable.right}
          onClick={() => navigation.current?.scrollBy({ left: 260 })}>
          <svg aria-hidden="true" viewBox="0 0 24 24"><path d="m9 6 6 6-6 6" /></svg>
        </button>
      </div>
      <main className="project-workspace">{project.is_locked ? <p className="lock-context" role="status">Project locked. Project changes and workflows are disabled. Metadata remains available.</p> : null}{children}</main>
    </div>
  );
}
