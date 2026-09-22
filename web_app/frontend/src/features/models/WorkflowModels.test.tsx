import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { createMemoryHistory, createRootRoute, createRouter, RouterProvider } from "@tanstack/react-router";
import { act, render, screen, waitFor, within } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { describe, expect, it, vi } from "vitest";

import { ApiError } from "../../core/http";
import type { ModelCollection, ModelLedgerRecord, ModelsApi } from "./api";
import { WorkflowModels } from "./WorkflowModels";

const workflows = [
  { workflow: "mapping", title: "Mapping", path: "mapping" },
  { workflow: "code_generation", title: "Code Generation", path: "code-generation" },
  { workflow: "validation", title: "Validation", path: "validation" },
] as const;

const model: ModelLedgerRecord = {
  model_id: 18,
  model_name: "Customer 360",
  model_description: null,
  model_revision: 5,
  model_input_scope_object_count: 3,
  latest_workflow: "validation",
  latest_run_status: "completed_with_repair",
  updated_at: "2026-09-21T12:00:00Z",
};

describe.each(workflows)("$title Model picker", ({ workflow, title, path }) => {
  it("loads active Models, follows opaque cursors, and refreshes only on request", async () => {
    let resolveInitial!: (value: ModelCollection) => void;
    let resolveNext!: (value: ModelCollection) => void;
    const initial = new Promise<ModelCollection>((resolve) => { resolveInitial = resolve; });
    const next = new Promise<ModelCollection>((resolve) => { resolveNext = resolve; });
    const listModels = vi.fn<ModelsApi["listModels"]>()
      .mockReturnValueOnce(initial)
      .mockReturnValueOnce(next);
    const user = userEvent.setup();
    renderModels({ listModels }, workflow);

    expect(await screen.findByText(`Loading Models for ${title}…`)).toHaveAttribute("aria-busy", "true");
    expect(listModels).toHaveBeenCalledExactlyOnceWith(7, "active", 200, undefined);
    if (workflow === "mapping") {
      expect(screen.getByRole("button", { name: "Refresh" })).toBeEnabled();
    } else {
      expect(screen.getByRole("button", { name: "Refreshing…" })).toBeDisabled();
    }

    await act(async () => resolveInitial({ items: [model], next_cursor: "opaque/+cursor=" }));
    const table = await screen.findByRole("table", { name: `Models for ${title}` });
    expect(within(table).getByRole("link", { name: `Open Customer 360 ${title}` })).toHaveAttribute(
      "href", `/tenants/7/${path}/models/18`,
    );
    expect(within(table).getByText("No description provided")).toBeVisible();
    expect(within(table).getByText("r5")).toBeVisible();
    expect(within(table).getByText("3 Objects")).toBeVisible();
    expect(within(table).getByText("Validation")).toBeVisible();
    expect(within(table).getByText("Completed with repair")).toBeVisible();
    expect(listModels).toHaveBeenCalledTimes(1);

    await user.click(screen.getByRole("button", { name: "Load more Models" }));
    expect(screen.getByRole("button", { name: "Loading…" })).toBeDisabled();
    expect(listModels).toHaveBeenLastCalledWith(7, "active", 200, "opaque/+cursor=");
    await act(async () => resolveNext({
      items: [{ ...model, model_id: 19, model_name: "Orders" }], next_cursor: null,
    }));
    expect(await screen.findByRole("link", { name: `Open Orders ${title}` })).toHaveAttribute(
      "href", `/tenants/7/${path}/models/19`,
    );
    expect(screen.queryByRole("button", { name: "Load more Models" })).not.toBeInTheDocument();
    expect(listModels).toHaveBeenCalledTimes(2);

    listModels.mockResolvedValueOnce({
      items: [{ ...model, model_name: "Refreshed Customer" }], next_cursor: null,
    });
    await user.click(screen.getByRole("button", { name: "Refresh" }));
    expect(await screen.findByRole("link", { name: `Open Refreshed Customer ${title}` })).toBeVisible();
    expect(screen.queryByRole("link", { name: `Open Orders ${title}` })).not.toBeInTheDocument();
    expect(listModels).toHaveBeenCalledTimes(3);
    expect(listModels).toHaveBeenLastCalledWith(7, "active", 200, undefined);
  });

  it.each([403, 500])("shows a safe %s error and can refresh into the empty state", async (status) => {
    const listModels = vi.fn<ModelsApi["listModels"]>().mockRejectedValueOnce(
      status === 403 ? new ApiError(403, "authorization_denied", null) : new Error("Private failure details"),
    );
    const user = userEvent.setup();
    renderModels({ listModels }, workflow);

    expect(await screen.findByRole("alert")).toHaveTextContent(status === 403
      ? `You do not have permission to view Models for ${title}.`
      : `Models for ${title} could not be loaded.`);
    expect(screen.queryByText("Private failure details")).not.toBeInTheDocument();
    expect(screen.queryByRole("table")).not.toBeInTheDocument();
    listModels.mockResolvedValueOnce({ items: [], next_cursor: null });
    await user.click(screen.getByRole("button", { name: "Refresh" }));
    expect(await screen.findByText(`No active Models are available for ${title}.`)).toBeVisible();
    await waitFor(() => expect(listModels).toHaveBeenCalledTimes(2));
  });
});

function renderModels(api: Pick<ModelsApi, "listModels">, workflow: typeof workflows[number]["workflow"]) {
  const client = new QueryClient({ defaultOptions: { queries: { retry: false } } });
  const route = createRootRoute({ component: () => (
    <WorkflowModels api={api} tenantId={7} workflow={workflow} />
  ) });
  const router = createRouter({ routeTree: route, history: createMemoryHistory({ initialEntries: ["/"] }) });
  return render(<QueryClientProvider client={client}><RouterProvider router={router} /></QueryClientProvider>);
}
