import { render, screen, waitFor, within } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { describe, expect, it, vi } from "vitest";

import { ApiError, createHttpRequest } from "../../core/http";
import { createModelRecordReviewApi, type ModelRecordReviewApi, type ModelReviewCommand, type ModelReviewPreview } from "./api";
import { ModelRecordReview } from "./ModelRecordReview";

const preview: ModelReviewPreview = {
  model_id: 18, model_revision: 7, plan_digest: "a".repeat(64), can_apply: true,
  action_count: 2, additional_change_count: 1, total_record_count: 2,
  items: [
    { dataset: "conceptual_object", record_id: 41, label: "Customer", selected: true,
      reason: "Selected record.", is_locked: false, desired_locked: false,
      status: "active", desired_status: "inactive", changed: true },
    { dataset: "conceptual_relationship", record_id: 51, label: "Customer places Order", selected: false,
      reason: "An active Relationship requires both endpoint Objects to remain active.",
      is_locked: false, desired_locked: false, status: "active", desired_status: "inactive", changed: true },
  ],
  issues: [], issue_count: 0, page: 1, next_page: null,
};

function fixture() {
  const api = {
    previewModelRecordReview: vi.fn<ModelRecordReviewApi["previewModelRecordReview"]>().mockResolvedValue(preview),
    applyModelRecordReview: vi.fn<ModelRecordReviewApi["applyModelRecordReview"]>().mockResolvedValue({
      model_id: 18, model_revision: 8, model_change_set_id: "test-receipt", action_count: 2,
    }),
  };
  const props = {
    api, tenantId: 9, modelId: 18, modelRevision: 7, dataset: "conceptual_object" as const,
    selectedIds: new Set([41]), hasTenantLock: true, disabled: false,
    actions: ["lock", "unlock", "deactivate", "reactivate"] as ModelReviewCommand["action"][],
    onApplied: vi.fn<() => Promise<void>>().mockResolvedValue(undefined),
  };
  const client = new QueryClient({ defaultOptions: { queries: { retry: false }, mutations: { retry: false } } });
  const renderReview = (overrides: Partial<typeof props> = {}) => (
    <QueryClientProvider client={client}><ModelRecordReview {...props} {...overrides} /></QueryClientProvider>
  );
  return { api, props, renderReview };
}

describe("Model record review", () => {
  it("previews deletion of only unlocked selected mappings", async () => {
    const { api, props } = fixture();
    render(<QueryClientProvider client={new QueryClient()}><ModelRecordReview {...props}
      dataset="mapping_object" selectedIds={new Set([41, 42])} deleteIds={new Set([42])} actions={["delete"]} />
    </QueryClientProvider>);
    await userEvent.setup().click(screen.getByRole("button", { name: "Delete selected" }));
    await waitFor(() => expect(api.previewModelRecordReview).toHaveBeenCalled());
    expect(api.previewModelRecordReview.mock.calls[0]?.[2]).toEqual({
      dataset: "mapping_object", record_ids: [42], action: "delete", expected_model_revision: 7,
    });
  });

  it("previews every dependent change before explicit apply and uses the scoped HTTP contract", async () => {
    const fetcher = vi.fn<typeof fetch>().mockImplementation(async (input) => new Response(JSON.stringify(
      String(input).includes("/preview") ? preview
        : { model_id: 18, model_revision: 8, model_change_set_id: "receipt", action_count: 2 },
    ), { headers: { "content-type": "application/json" } }));
    const api = createModelRecordReviewApi(createHttpRequest(fetcher));
    const client = new QueryClient();
    const applied = vi.fn().mockResolvedValue(undefined);
    render(<QueryClientProvider client={client}><ModelRecordReview api={api}
      tenantId={9} modelId={18} modelRevision={7} dataset="conceptual_object"
      selectedIds={new Set([41])} hasTenantLock disabled={false} onApplied={applied} /></QueryClientProvider>);
    const user = userEvent.setup();
    expect(fetcher).not.toHaveBeenCalled();
    const trigger = screen.getByRole("button", { name: "Deactivate selected" });
    await user.click(trigger);
    const dialog = await screen.findByRole("dialog", { name: "Deactivate records" });
    expect(within(dialog).getByRole("button", { name: "Close review" })).toHaveFocus();
    expect(await within(dialog).findByText("Customer places Order")).toBeVisible();
    expect(within(dialog).getByText("2 changes: 1 selected, 1 required by dependencies.")).toBeVisible();
    expect(fetcher).toHaveBeenCalledTimes(1);
    await user.click(within(dialog).getByRole("button", { name: "Apply these 2 changes" }));
    await waitFor(() => expect(screen.queryByRole("dialog")).not.toBeInTheDocument());
    expect(applied).toHaveBeenCalledWith();
    expect(trigger).toHaveFocus();
    const [previewCall, applyCall] = fetcher.mock.calls;
    expect(previewCall?.[0]).toBe("/api/v1/tenants/9/models/18/change-sets/review/preview?page=1");
    expect(applyCall?.[0]).toBe("/api/v1/tenants/9/models/18/change-sets/review");
    expect(JSON.parse(String(applyCall?.[1]?.body))).toEqual({
      dataset: "conceptual_object", record_ids: [41], action: "deactivate",
      expected_model_revision: 7, expected_plan_digest: preview.plan_digest,
    });
    expect(applyCall?.[1]?.headers).toMatchObject({ "Idempotency-Key": expect.any(String) });
  });

  it.each(["Lock", "Unlock", "Deactivate", "Reactivate"])("freezes the selected IDs and %s action", async (label) => {
    const { api, renderReview } = fixture();
    render(renderReview({ selectedIds: new Set([52, 41]) }));
    await userEvent.setup().click(screen.getByRole("button", { name: `${label === "Deactivate" ? "Deactivate" : label === "Reactivate" ? "Activate" : label} selected` }));
    await waitFor(() => expect(api.previewModelRecordReview).toHaveBeenCalledWith(9, 18, {
      dataset: "conceptual_object", record_ids: [41, 52], action: label.toLowerCase(), expected_model_revision: 7,
    }, 1));
    expect(api.applyModelRecordReview).not.toHaveBeenCalled();
  });

  it("pages a complete plan with its digest and disables status changes when a dependency is locked", async () => {
    const { api, renderReview } = fixture();
    api.previewModelRecordReview.mockResolvedValueOnce({
      ...preview, items: preview.items.slice(0, 1), next_page: 2, can_apply: false,
      issues: [{ code: "record_locked", dataset: "conceptual_relationship", message: "A required Relationship is locked." }],
      issue_count: 1,
    }).mockResolvedValueOnce({ ...preview, page: 2, can_apply: false,
      items: [{ ...preview.items[1]!, is_locked: true }],
    });
    render(renderReview());
    const user = userEvent.setup();
    await user.click(screen.getByRole("button", { name: "Deactivate selected" }));
    expect(await screen.findByRole("alert")).toHaveTextContent("A required Relationship is locked.");
    expect(screen.getByRole("button", { name: "Apply these 2 changes" })).toBeDisabled();
    await user.click(screen.getByRole("button", { name: "Load more affected records" }));
    expect(await screen.findByText("Customer places Order")).toBeVisible();
    expect(screen.getByText("Showing 2 of 2 affected records.")).toBeVisible();
    expect(api.previewModelRecordReview.mock.calls[1]?.[2].expected_plan_digest).toBe(preview.plan_digest);
    expect(api.previewModelRecordReview.mock.calls[1]?.[3]).toBe(2);
    expect(api.applyModelRecordReview).not.toHaveBeenCalled();
  });

  it("retries an uncertain apply with identical request and key, including after revision changes", async () => {
    const { api, renderReview } = fixture();
    api.applyModelRecordReview.mockRejectedValueOnce(new ApiError(503, "unavailable", "safe-reference"));
    const view = render(renderReview());
    const user = userEvent.setup();
    await user.click(screen.getByRole("button", { name: "Deactivate selected" }));
    await user.click(await screen.findByRole("button", { name: "Apply these 2 changes" }));
    expect(await screen.findByRole("alert")).toHaveTextContent("result could not be confirmed");
    expect(screen.getByRole("button", { name: "Close review" })).toBeDisabled();
    view.rerender(renderReview({ modelRevision: 8, selectedIds: new Set([99]) }));
    await user.keyboard("{Escape}");
    expect(screen.getByRole("dialog")).toBeVisible();
    await user.click(screen.getByRole("button", { name: "Retry review" }));
    await waitFor(() => expect(api.applyModelRecordReview).toHaveBeenCalledTimes(2));
    expect(api.applyModelRecordReview.mock.calls[1]).toEqual(api.applyModelRecordReview.mock.calls[0]);
    expect(api.previewModelRecordReview).toHaveBeenCalledTimes(1);
  });

  it("requires a new preview after a definite conflict; traps focus and restores it on cancel", async () => {
    const { api, renderReview } = fixture();
    api.applyModelRecordReview.mockRejectedValueOnce(new ApiError(409, "review_conflict", null));
    render(renderReview());
    const user = userEvent.setup();
    const trigger = screen.getByRole("button", { name: "Deactivate selected" });
    await user.click(trigger);
    const apply = await screen.findByRole("button", { name: "Apply these 2 changes" });
    await waitFor(() => expect(apply).toBeEnabled());
    const close = screen.getByRole("button", { name: "Close review" });
    close.focus();
    await user.tab({ shift: true });
    expect(apply).toHaveFocus();
    await user.tab();
    expect(close).toHaveFocus();
    await user.click(apply);
    expect(await screen.findByRole("alert")).toHaveTextContent("review plan changed");
    expect(apply).toBeDisabled();
    await user.keyboard("{Escape}");
    expect(screen.queryByRole("dialog")).not.toBeInTheDocument();
    expect(trigger).toHaveFocus();
  });

  it("blocks missing locks, stale ledgers, empty selections, and oversized selections", () => {
    const { renderReview } = fixture();
    const view = render(renderReview({ hasTenantLock: false }));
    for (const overrides of [
      { hasTenantLock: false }, { disabled: true }, { selectedIds: new Set<number>() },
      { selectedIds: new Set(Array.from({ length: 201 }, (_, n) => n + 1)) },
    ]) {
      view.rerender(renderReview(overrides));
      for (const button of screen.getAllByRole("button")) expect(button).toBeDisabled();
    }
  });

  it("groups deletion counts and reveals paged records without change or reason clutter", async () => {
    const { api, renderReview } = fixture();
    const deletion = { ...preview, changes_by_dataset: { conceptual_object: 1, conceptual_relationship: 1 },
      items: preview.items.slice(0, 1).map((item) => ({ ...item, desired_status: "deleted" as const })), next_page: 2 };
    api.previewModelRecordReview.mockResolvedValueOnce(deletion).mockResolvedValueOnce({
      ...deletion, page: 2, next_page: null,
      items: [{ ...preview.items[1]!, desired_status: "deleted" }],
    });
    render(renderReview({ actions: ["delete"] }));
    const user = userEvent.setup();
    const trigger = screen.getByRole("button", { name: "Delete selected" });
    await user.click(trigger);
    const dialog = await screen.findByRole("dialog", { name: "Delete records permanently" });
    await within(dialog).findByText("2 records to delete");
    expect(within(dialog).getByRole("table", { name: "Conceptual object affected records" })).not.toBeVisible();
    expect(within(dialog).queryByText("Selected record.")).not.toBeInTheDocument();
    const close = within(dialog).getByRole("button", { name: "Close review" });
    const apply = within(dialog).getByRole("button", { name: "Delete 2 records permanently" });
    close.focus();
    await user.tab({ shift: true });
    expect(apply).toHaveFocus();
    await user.tab();
    expect(close).toHaveFocus();
    await user.tab();
    expect(document.activeElement?.tagName).toBe("SUMMARY");
    expect(document.activeElement).toHaveTextContent("Conceptual");
    await user.click(within(dialog).getByText("Conceptual", { exact: true }));
    await user.click(within(dialog).getByText("Conceptual object", { exact: true }));
    const objects = within(dialog).getByRole("table", { name: "Conceptual object affected records" });
    expect(within(objects).getAllByRole("columnheader").map((cell) => cell.textContent)).toEqual(["Record", "Status", "Lock"]);
    expect(within(objects).getByText("Customer")).toBeVisible();
    await user.click(within(dialog).getByRole("button", { name: "Load more affected records" }));
    await within(dialog).findByText("Showing 2 of 2 affected records.");
    await user.click(within(dialog).getByText("Conceptual relationship", { exact: true }));
    expect(within(dialog).getByText("Customer places Order")).toBeVisible();
    expect(api.previewModelRecordReview.mock.calls[1]?.[2].expected_plan_digest).toBe(preview.plan_digest);
    expect(api.previewModelRecordReview.mock.calls[1]?.[3]).toBe(2);
    await user.keyboard("{Escape}");
    expect(screen.queryByRole("dialog")).not.toBeInTheDocument();
    expect(trigger).toHaveFocus();
    expect(api.applyModelRecordReview).not.toHaveBeenCalled();
  });

  it("keeps blocked deletion and a locked dependent record's governed unlock visible", async () => {
    const { api, renderReview } = fixture();
    api.previewModelRecordReview.mockResolvedValueOnce({ ...preview, can_apply: false,
      changes_by_dataset: { mapping_object: 1 }, action_count: 1, total_record_count: 1,
      items: [{ ...preview.items[0]!, dataset: "mapping_object", record_id: 900,
        label: "silver.Customer Mapping", is_locked: true, desired_status: "deleted" }],
      issues: [{ code: "record_locked", dataset: "mapping_object", message: "Unlock the Mapping before deleting it." }], issue_count: 1,
    });
    render(renderReview({ actions: ["delete"] }));
    const user = userEvent.setup();
    await user.click(screen.getByRole("button", { name: "Delete selected" }));
    expect(await screen.findByRole("alert")).toHaveTextContent("Unlock the Mapping before deleting it.");
    expect(screen.getByRole("button", { name: "Delete 1 records permanently" })).toBeDisabled();
    const unlock = screen.getByRole("button", { name: "Review unlock for silver.Customer Mapping" });
    expect(unlock).toBeVisible();
    await user.click(unlock);
    await screen.findByRole("dialog", { name: "Review unlock" });
    expect(api.previewModelRecordReview).toHaveBeenLastCalledWith(9, 18,
      { dataset: "mapping_object", record_ids: [900], action: "unlock", expected_model_revision: 7 }, 1);
    expect(api.applyModelRecordReview).not.toHaveBeenCalled();
  });

  it("sums workflow sections without losing dataset counts or unknown record types", async () => {
    const { api, renderReview } = fixture();
    api.previewModelRecordReview.mockResolvedValueOnce({ ...preview, action_count: 8, total_record_count: 8,
      changes_by_dataset: { logical_attribute: 3, future_record: 1, mapping_object: 2, logical_entity: 2 },
      items: [], next_page: 2,
    });
    render(renderReview({ actions: ["delete"] }));
    const user = userEvent.setup();
    await user.click(screen.getByRole("button", { name: "Delete selected" }));
    const sections = await screen.findByRole("region", { name: "Records to delete" });
    const summaries = [...sections.querySelectorAll(":scope > details > summary")];
    expect(summaries.map((item) => item.textContent)).toEqual(["Logical5 records", "Mapping2 records", "Other records1 record"]);
    await user.click(within(sections).getByText("Logical", { exact: true }));
    const types = [...summaries[0]!.parentElement!.querySelectorAll(".model-delete-record-types > details > summary")];
    expect(types.map((item) => item.textContent)).toEqual(["Logical entity2 records", "Logical attribute3 records"]);
    await user.click(within(sections).getByText("Other records", { exact: true }));
    expect(within(sections).getByText("Future record", { exact: true })).toBeVisible();
    expect(api.applyModelRecordReview).not.toHaveBeenCalled();
  });
});


it("previews an explicit unlock for a hidden locked Mapping before applying it", async () => {
  const { api, renderReview } = fixture();
  api.previewModelRecordReview.mockResolvedValueOnce({ ...preview, can_apply: false,
    items: [{ ...preview.items[1]!, dataset: "mapping_object", record_id: 900, label: "silver.Customer Mapping", is_locked: true }],
    issues: [{ code: "record_locked", dataset: "mapping_object", message: "Unlock the Mapping before changing status." }], issue_count: 1,
  });
  render(renderReview());
  const user = userEvent.setup();
  await user.click(screen.getByRole("button", { name: "Deactivate selected" }));
  await user.click(await screen.findByRole("button", { name: "Review unlock for silver.Customer Mapping" }));
  await screen.findByRole("dialog", { name: "Review unlock" });
  await waitFor(() => expect(api.previewModelRecordReview).toHaveBeenLastCalledWith(9, 18,
    { dataset: "mapping_object", record_ids: [900], action: "unlock", expected_model_revision: 7 }, 1));
  expect(api.applyModelRecordReview).not.toHaveBeenCalled();
});
