import { useEffect, useId, useRef, useState, type ReactNode } from "react";
import { Link, useSearch } from "@tanstack/react-router";
import { useQuery, useQueryClient } from "@tanstack/react-query";

import { ModelIcon } from "../../shared/ui";
import type { TenantLockState } from "../tenant_locks/api";
import type { ModelDetail, ModelsApi, ModelSectionState } from "./api";

export type ModelStage =
  | "overview" | "settings" | "settings-prompts" | "scope" | "metadata-enrichment"
  | "profiling" | "assertions" | "analysis" | "conceptual" | "logical"
  | "dimensional" | "mapping" | "code-generation" | "validation";

const stages = [
  { id: "overview", label: "Overview", to: "/tenants/$tenantId/models/$modelId" },
  { id: "settings", label: "Settings", to: "/tenants/$tenantId/models/$modelId/settings" },
  { id: "scope", label: "Input scope", to: "/tenants/$tenantId/models/$modelId/input-scope", accessibleName: "Model Input Scope" },
  { id: "assertions", label: "Assertions", to: "/tenants/$tenantId/models/$modelId/assertions" },
  { id: "profiling", label: "Profiling", to: "/tenants/$tenantId/models/$modelId/profiling" },
  { id: "metadata-enrichment", label: "Enrichment", to: "/tenants/$tenantId/models/$modelId/metadata-enrichment", accessibleName: "Metadata enrichment" },
  { id: "analysis", label: "Analysis", to: "/tenants/$tenantId/models/$modelId/analysis" },
  { id: "conceptual", label: "Conceptual", to: "/tenants/$tenantId/models/$modelId/conceptual" },
  { id: "logical", label: "Logical", to: "/tenants/$tenantId/models/$modelId/logical" },
  { id: "dimensional", label: "Dimensional", to: "/tenants/$tenantId/models/$modelId/dimensional" },
  { id: "mapping", label: "Mapping", to: "/tenants/$tenantId/mapping/models/$modelId" },
  { id: "code-generation", label: "Code generation", to: "/tenants/$tenantId/code-generation/models/$modelId" },
  { id: "validation", label: "Validation", to: "/tenants/$tenantId/validation/models/$modelId" },
] as const;

export function ModelWorkspaceShell({ api, model, activeStage, tenantLock, lockControl, children }: {
  api: Pick<ModelsApi, "readModelOverview">;
  model: ModelDetail;
  activeStage: ModelStage;
  tenantLock: TenantLockState;
  lockControl?: ReactNode;
  children: ReactNode;
}) {
  const statusId = useId();
  const client = useQueryClient();
  const overview = useQuery({
    queryKey: ["model-overview", model.tenant_id, model.model_id],
    queryFn: () => api.readModelOverview(model.tenant_id, model.model_id),
  });
  const previousRevision = useRef(model.model_revision);
  useEffect(() => {
    if (previousRevision.current !== model.model_revision) {
      previousRevision.current = model.model_revision;
      void client.invalidateQueries({ queryKey: ["model-overview", model.tenant_id, model.model_id] });
    }
  }, [client, model.model_id, model.model_revision, model.tenant_id]);
  const statusLabels: Record<ModelSectionState["state"], string> = {
    available: "Available", ready: "Ready", empty: "Not set", not_run: "Not run",
    queued: "Queued", running: "Running", completed: "Completed", failed: "Failed", cancelled: "Cancelled",
    results_available: "Results available",
  };
  const currentStates = !overview.isError && overview.data?.model_revision === model.model_revision
    && overview.data.model_id === model.model_id ? overview.data.section_states : undefined;
  const navigation = useRef<HTMLElement>(null);
  const highlightedTab = useRef<HTMLAnchorElement | null>(null);
  const [highlight, setHighlight] = useState<{ left: number; width: number; visible: boolean } | null>(null);
  const [scrollAvailable, setScrollAvailable] = useState({ left: false, right: false });
  const search = useSearch({ strict: false });
  const layer = activeStage === "dimensional" ? "dimensional"
    : activeStage === "logical" ? "logical" : search.layer;
  const active = activeStage === "settings-prompts" ? "settings" : activeStage;
  const params = { tenantId: String(model.tenant_id), modelId: String(model.model_id) };
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
    <div className="workspace workspace-model">
      <header className="model-identity">
        <div className="model-identity-main">
          <span className="model-identity-symbol"><ModelIcon /></span>
          <div><strong className="model-identity-name">{model.model_name}</strong>
            {model.model_description ? <p>{model.model_description}</p> : null}
          </div>
        </div>
        <div className="model-identity-status">
          <span>Revision {model.model_revision}</span>
          {!model.is_active ? <span className="status-badge">Archived</span> : null}
          {lockControl ?? <span className={tenantLock.owned_by_current_principal ? "model-lock is-held" : "model-lock"}>{lockLabel}</span>}
          <button className="model-status-refresh" type="button" aria-label="Refresh section status"
            title="Refresh section status" disabled={overview.isFetching}
            onClick={() => void Promise.all([
              overview.refetch(), client.invalidateQueries({ queryKey: ["model", model.tenant_id, model.model_id] }),
              client.invalidateQueries({ queryKey: ["tenant-home", model.tenant_id] }),
            ])}>
            <svg aria-hidden="true" viewBox="0 0 24 24"><path d="M20 7v5h-5M4 17v-5h5M5.5 8a7 7 0 0 1 11.7-3L20 8M4 16l2.8 3A7 7 0 0 0 18.5 16" /></svg>
          </button>
        </div>
      </header>
      <div className="model-navigation">
        <button className="model-navigation-scroll" type="button" aria-label="Scroll Model sections left" disabled={!scrollAvailable.left}
          onClick={() => navigation.current?.scrollBy({ left: -260 })}>
          <svg aria-hidden="true" viewBox="0 0 24 24"><path d="m15 6-6 6 6 6" /></svg>
        </button>
        <nav ref={navigation} aria-label="Model sections" className="model-tabs"
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
          {highlight ? <span aria-hidden="true" className={`model-tab-highlight${highlight.visible ? " is-visible" : ""}`}
            style={{ width: highlight.width, transform: `translateX(${highlight.left}px)` }} /> : null}
          {stages.map((stage) => {
            const isSetup = stage.id === "overview" || stage.id === "settings"
              || stage.id === "scope" || stage.id === "assertions";
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
            className={`model-tab${active === stage.id ? " is-active" : ""}${stage.id === "assertions" || stage.id === "dimensional" ? " is-group-end" : ""}`}>
            <span className={`model-stage-circle ${tone}`} aria-hidden="true">
              {tone === "is-complete" ? <svg viewBox="0 0 16 16"><path d="m4 8 2.5 2.5L12 5" /></svg>
                : tone === "is-failed" ? <svg viewBox="0 0 16 16"><path d="M8 4v4M8 11v.2" /></svg> : null}
            </span>
            <span className="model-stage-label">{stage.label}</span>
            <span className={`model-stage-status ${tone}`} id={`${statusId}-${stage.id}`} aria-hidden={isSetup || undefined}>{label}</span>
          </Link>;
          })}
        </nav>
        <button className="model-navigation-scroll" type="button" aria-label="Scroll Model sections right" disabled={!scrollAvailable.right}
          onClick={() => navigation.current?.scrollBy({ left: 260 })}>
          <svg aria-hidden="true" viewBox="0 0 24 24"><path d="m9 6 6 6-6 6" /></svg>
        </button>
      </div>
      <main className="model-workspace">{children}</main>
    </div>
  );
}
