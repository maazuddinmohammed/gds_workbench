import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { createMemoryHistory, createRootRoute, createRouter, RouterProvider } from "@tanstack/react-router";
import { act, render, screen, waitFor, within } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { describe, expect, it, vi } from "vitest";

import type { TenantLockState } from "../tenant_locks/api";
import type { ModelDetail, ModelsApi, ModelWorkflowOverview } from "./api";
import { ModelWorkspaceShell, type ModelStage } from "./ModelWorkspaceShell";

const model: ModelDetail = {
  model_id: 18, tenant_id: 7, model_name: "Customer 360", model_description: "Cross-system customer domain",
  model_revision: 18, model_input_scope_object_count: 0,
  logical_schemas: [], dimensional_schemas: [], silver_model_naming_instructions: null,
  silver_model_audit_columns_template: null, gold_model_naming_instructions: null,
  gold_model_technical_columns_template: null, gold_model_audit_columns_template: null,
  default_agent_sdk_code: null, default_agent_provider_code: null, default_agent_model_code: null,
  default_reasoning_effort_code: null, default_max_turns: null, default_validation_retry_count: null,
  is_active: true, updated_at: "2026-09-28T01:00:00Z",
};
const tenantLock: TenantLockState = {
  is_locked: true, owner_display_name: "Architect", owned_by_current_principal: true,
  purpose: "Model review", acquired_at: "2026-09-28T01:00:00Z", expires_at: "2026-09-28T02:00:00Z",
};
const overview = {
  model_id: 18, model_revision: 18, items: [],
  section_states: [
    { section: "overview", state: "available" },
    { section: "settings", state: "ready" },
    { section: "scope", state: "empty" },
    { section: "metadata-enrichment", state: "completed" },
    { section: "profiling", state: "queued" },
    { section: "assertions", state: "results_available" },
    { section: "analysis", state: "running" },
    { section: "conceptual", state: "not_run" },
    { section: "logical", state: "failed" },
    { section: "dimensional", state: "failed" },
    { section: "mapping", state: "results_available" },
    { section: "code-generation", state: "completed" },
    { section: "validation", state: "empty" },
  ],
} satisfies ModelWorkflowOverview;
const sectionNames = [
  "Overview", "Settings", "Model Input Scope", "Assertions", "Metadata enrichment", "Profiling",
  "Analysis", "Conceptual", "Logical", "Dimensional", "Mapping", "Code generation", "Validation",
];

describe("Model workspace status ribbon", () => {
  it("keeps setup sections neutral and describes workflow states without adding counts", async () => {
    const readModelOverview = vi.fn<ModelsApi["readModelOverview"]>().mockResolvedValue(overview);
    renderShell({ readModelOverview });
    const navigation = await screen.findByRole("navigation", { name: "Model sections" });
    const links = within(navigation).getAllByRole("link");
    expect(links.map((link) => link.getAttribute("aria-label"))).toEqual(sectionNames);
    const descriptions = [
      "", "", "", "", "Completed", "Queued", "Running",
      "Not run", "Failed", "Failed", "Results available", "Completed", "Not run",
    ];
    await waitFor(() => {
      for (const [index, link] of links.entries()) expect(link).toHaveAccessibleDescription(descriptions[index]);
    });
    for (const link of links.slice(0, 4)) {
      expect(link).not.toHaveAttribute("aria-describedby");
      expect(link.querySelector(".model-stage-circle")).toHaveClass("is-neutral");
      expect(link.querySelector(".model-stage-status")).toBeEmptyDOMElement();
    }
    for (const link of links.slice(4)) {
      const statusId = link.getAttribute("aria-describedby");
      expect(statusId).toBeTruthy();
      expect(document.getElementById(statusId!)).toBeVisible();
    }
    expect(navigation.querySelectorAll(".model-stage-circle[aria-hidden='true']")).toHaveLength(13);
    expect([...navigation.querySelectorAll(".is-group-end")].map((link) => link.getAttribute("aria-label"))).toEqual([
      "Assertions", "Dimensional",
    ]);
    expect(within(navigation).queryByText(/\d+ (?:Objects|results|Mappings|checks)/i)).not.toBeInTheDocument();
    expect(within(navigation).getByRole("link", { name: "Mapping" })).toHaveAttribute("aria-current", "page");
    expect(readModelOverview).toHaveBeenCalledExactlyOnceWith(7, 18);
    expect(screen.getByText("Tenant Lock held by you")).toBeVisible();
    expect(screen.getByText("Revision 18")).toBeVisible();
  });

  it.each(["request failure", "stale revision", "missing section states"])("shows Unavailable for %s, never a guessed Not run state", async (condition) => {
    const readModelOverview = vi.fn<ModelsApi["readModelOverview"]>();
    if (condition === "request failure") readModelOverview.mockRejectedValue(new Error("Private transport diagnostic"));
    else if (condition === "stale revision") readModelOverview.mockResolvedValue({ ...overview, model_revision: 17 });
    else readModelOverview.mockResolvedValue({ model_id: 18, model_revision: 18, items: [] });
    renderShell({ readModelOverview });
    const navigation = await screen.findByRole("navigation", { name: "Model sections" });
    await waitFor(() => expect(within(navigation).getByRole("link", { name: "Mapping" })).toHaveAccessibleDescription("Unavailable"));
    expect(within(navigation).queryByText("Not run")).not.toBeInTheDocument();
    expect(screen.queryByText("Private transport diagnostic")).not.toBeInTheDocument();
  });

  it("refreshes the shared overview only on request and hides prior states after a failed refresh", async () => {
    const readModelOverview = vi.fn<ModelsApi["readModelOverview"]>().mockResolvedValue(overview);
    const { client } = renderShell({ readModelOverview });
    const navigation = await screen.findByRole("navigation", { name: "Model sections" });
    const mapping = within(navigation).getByRole("link", { name: "Mapping" });
    await waitFor(() => expect(mapping).toHaveAccessibleDescription("Results available"));
    expect(client.getQueryData(["model-overview", 7, 18])).toEqual(overview);
    vi.useFakeTimers();
    try {
      await act(async () => { await vi.advanceTimersByTimeAsync(120_000); });
      expect(readModelOverview).toHaveBeenCalledTimes(1);
    } finally {
      vi.useRealTimers();
    }
    readModelOverview.mockResolvedValue({ ...overview, section_states: overview.section_states.map((entry) => (
      entry.section === "mapping" ? { ...entry, state: "running" } : entry
    )) });
    const user = userEvent.setup();
    await user.click(screen.getByRole("button", { name: "Refresh section status" }));
    await waitFor(() => expect(mapping).toHaveAccessibleDescription("Running"));
    expect(readModelOverview).toHaveBeenCalledTimes(2);
    readModelOverview.mockRejectedValue(new Error("Private refresh diagnostic"));
    await user.click(screen.getByRole("button", { name: "Refresh section status" }));
    await waitFor(() => expect(mapping).toHaveAccessibleDescription("Unavailable"));
    expect(screen.queryByText("Private refresh diagnostic")).not.toBeInTheDocument();
    expect(readModelOverview).toHaveBeenCalledTimes(3);
  });

  it.each(["logical", "dimensional"] as const)("retains %s context and keyboard navigation through the ribbon", async (layer) => {
    const readModelOverview = vi.fn<ModelsApi["readModelOverview"]>().mockResolvedValue(overview);
    renderShell({ readModelOverview }, { activeStage: layer, path: `/?layer=${layer}` });
    const navigation = await screen.findByRole("navigation", { name: "Model sections" });
    const sections = within(navigation);
    for (const name of ["Mapping", "Code generation", "Validation"]) {
      expect(sections.getByRole("link", { name }).getAttribute("href")).toContain(`layer=${layer}`);
    }
    expect(sections.getByRole("link", { name: layer === "logical" ? "Logical" : "Dimensional" })).toHaveAttribute("aria-current", "page");
    const user = userEvent.setup();
    sections.getByRole("link", { name: "Overview" }).focus();
    await user.keyboard("{ArrowLeft}");
    expect(sections.getByRole("link", { name: "Validation" })).toHaveFocus();
    await user.keyboard("{Home}{ArrowRight}");
    expect(sections.getByRole("link", { name: "Settings" })).toHaveFocus();
    await user.keyboard("{ArrowRight}{ArrowRight}");
    expect(sections.getByRole("link", { name: "Assertions" })).toHaveFocus();
    await user.keyboard("{ArrowRight}");
    expect(sections.getByRole("link", { name: "Metadata enrichment" })).toHaveFocus();
    await user.keyboard("{End}{ArrowRight}");
    expect(sections.getByRole("link", { name: "Overview" })).toHaveFocus();
  });

  it("keeps the Prompts route represented by Settings without adding another stage", async () => {
    renderShell({ readModelOverview: vi.fn<ModelsApi["readModelOverview"]>().mockResolvedValue(overview) }, {
      activeStage: "settings-prompts",
    });
    const sections = within(await screen.findByRole("navigation", { name: "Model sections" }));
    expect(sections.getAllByRole("link")).toHaveLength(13);
    expect(sections.getByRole("link", { name: "Settings" })).toHaveAttribute("aria-current", "page");
    expect(sections.queryByRole("link", { name: "Prompts" })).not.toBeInTheDocument();
  });
});

function renderShell(api: Pick<ModelsApi, "readModelOverview">, options: { activeStage?: ModelStage; path?: string } = {}) {
  const client = new QueryClient({ defaultOptions: { queries: {
    retry: false, staleTime: 30_000, refetchOnWindowFocus: false,
  } } });
  const route = createRootRoute({ component: () => <ModelWorkspaceShell api={api} model={model}
    activeStage={options.activeStage ?? "mapping"} tenantLock={tenantLock}><p>Selected section content</p></ModelWorkspaceShell> });
  const router = createRouter({ routeTree: route, history: createMemoryHistory({ initialEntries: [options.path ?? "/"] }) });
  return { ...render(<QueryClientProvider client={client}><RouterProvider router={router} /></QueryClientProvider>), client };
}
