import { render, screen, waitFor } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { expect, it, vi } from "vitest";
import { createApiClient } from "../../api";
import { ApiError } from "../../core/http";
import type { ModelRecordEditor as Editor, ModelReviewPreview } from "./api";
import { ModelRecordTools } from "./ModelRecordEditor";
import { ModelLayerActions } from "./ModelLayerActions";

const navigate = vi.hoisted(() => vi.fn().mockResolvedValue(undefined));
vi.mock("@tanstack/react-router", () => ({ useNavigate: () => navigate }));

const editor: Editor = { label: "Customer", model_revision: 7, is_locked: false, fields: [
  { name: "logical_entity_definition", label: "Definition", kind: "multiline", value: "A customer.", required: true, options: [], minimum: null, maximum_length: null },
  { name: "logical_entity_type", label: "Type", kind: "choice", value: "core", required: true, options: ["core", "transaction", "other"], minimum: null, maximum_length: null },
] };
const preview: ModelReviewPreview = { model_id: 18, model_revision: 7, plan_digest: "a".repeat(64), can_apply: true,
  action_count: 250, additional_change_count: 20, total_record_count: 250, changes_by_dataset: { logical_entity: 230, mapping_object: 20 },
  warnings: ["Physical tables remain unchanged."], items: [], issues: [], issue_count: 0, page: 1, next_page: null,
};
function fixture() {
  const api = { ...createApiClient(),
    readModelRecordEditor: vi.fn().mockResolvedValue(editor),
    saveModelRecord: vi.fn().mockResolvedValue({ model_revision: 8 }),
    previewModelRecordReview: vi.fn().mockResolvedValue(preview),
    applyModelRecordReview: vi.fn().mockResolvedValue({ model_id: 18, model_revision: 8, model_change_set_id: "receipt", action_count: 250 }),
  };
  const client = new QueryClient({ defaultOptions: { queries: { retry: false } } });
  const props = { api, tenantId: 7, modelId: 18, modelRevision: 7, hasTenantLock: true, canDelete: true };
  const view = (revision = 7) => <QueryClientProvider client={client}><ModelRecordTools {...props} modelRevision={revision} dataset="logical_entity" recordId={41} /></QueryClientProvider>;
  return { api, client, props, view };
}

it("edits only changed definition fields and preserves the draft on a rejected save", async () => {
  const { api, view } = fixture();
  api.saveModelRecord.mockRejectedValueOnce(new ApiError(422, "invalid_request", null));
  render(view());
  const user = userEvent.setup();
  await user.click(screen.getByRole("button", { name: "Edit definition" }));
  const definition = await screen.findByLabelText("Definition");
  expect(screen.getByLabelText("Type")).toHaveValue("core");
  await user.clear(definition); await user.type(definition, "A person or organization buying goods.");
  await user.click(screen.getByRole("button", { name: "Save changes" }));
  await screen.findByRole("alert");
  expect(definition).toHaveValue("A person or organization buying goods.");
  expect(api.saveModelRecord.mock.calls[0]?.[2]).toEqual({ dataset: "logical_entity", record_id: 41, expected_model_revision: 7,
    changes: { logical_entity_definition: "A person or organization buying goods." } });
  await user.click(screen.getByRole("button", { name: "Save changes" }));
  await waitFor(() => expect(screen.queryByRole("dialog")).not.toBeInTheDocument());
  expect(api.saveModelRecord.mock.calls[1]?.[3]).not.toEqual(api.saveModelRecord.mock.calls[0]?.[3]);
});

it("retries uncertain saves with the same command and key after a revision update", async () => {
  const { api, view } = fixture();
  api.saveModelRecord.mockRejectedValueOnce(new ApiError(503, "unavailable", null));
  const rendered = render(view());
  const user = userEvent.setup();
  await user.click(screen.getByRole("button", { name: "Edit definition" }));
  await user.type(await screen.findByLabelText("Definition"), " Reviewed.");
  await user.click(screen.getByRole("button", { name: "Save changes" }));
  await screen.findByRole("button", { name: "Retry save" });
  rendered.rerender(view(8));
  expect(screen.getByRole("button", { name: "Close editor" })).toBeDisabled();
  await user.keyboard("{Escape}");
  expect(screen.getByRole("dialog")).toBeVisible();
  await user.click(screen.getByRole("button", { name: "Retry save" }));
  await waitFor(() => expect(api.saveModelRecord).toHaveBeenCalledTimes(2));
  expect(api.saveModelRecord.mock.calls[1]).toEqual(api.saveModelRecord.mock.calls[0]);
});

it("blocks editing locked definitions without altering lifecycle", async () => {
  const { api, view } = fixture();
  api.readModelRecordEditor.mockResolvedValue({ ...editor, is_locked: true });
  render(view());
  await userEvent.setup().click(screen.getByRole("button", { name: "Edit definition" }));
  expect(await screen.findByRole("alert")).toHaveTextContent("Unlock this record");
  expect(screen.getByLabelText("Definition")).toBeDisabled();
  expect(screen.getByRole("button", { name: "Save changes" })).toBeDisabled();
  expect(api.saveModelRecord).not.toHaveBeenCalled();
});

it("clears the whole layer only after confirming its server-derived impact digest", async () => {
  const { api, client, props } = fixture();
  render(<QueryClientProvider client={client}><ModelLayerActions {...props} layer="logical" onApplied={vi.fn()} /></QueryClientProvider>);
  const user = userEvent.setup();
  await user.click(screen.getByRole("button", { name: "Clear logical layer" }));
  await screen.findByRole("button", { name: "Delete 250 records permanently" });
  expect(screen.getByText("Physical tables remain unchanged.")).toBeVisible();
  expect(screen.getByText(/every Logical entity, attribute, relationship, and submodel/)).toBeVisible();
  expect(screen.queryByRole("button", { name: "Record history" })).not.toBeInTheDocument();
  expect(api.previewModelRecordReview.mock.calls[0]?.[2]).toEqual({ dataset: "logical_entity", record_ids: [], layer: "logical", action: "delete", expected_model_revision: 7 });
  expect(api.applyModelRecordReview).not.toHaveBeenCalled();
  await user.click(screen.getByRole("button", { name: "Delete 250 records permanently" }));
  await waitFor(() => expect(api.applyModelRecordReview).toHaveBeenCalledOnce());
  expect(api.applyModelRecordReview.mock.calls[0]?.[2].expected_plan_digest).toBe(preview.plan_digest);
});

it("hides permanent deletion for non-admins while keeping lifecycle controls", () => {
  const { client, props } = fixture();
  render(<QueryClientProvider client={client}>
    <ModelRecordTools {...props} canDelete={false} dataset="logical_entity" recordId={41} />
    <ModelLayerActions {...props} canDelete={false} layer="logical" onApplied={vi.fn()} />
  </QueryClientProvider>);
  expect(screen.queryByRole("button", { name: "Delete" })).not.toBeInTheDocument();
  expect(screen.queryByRole("button", { name: "Clear logical layer" })).not.toBeInTheDocument();
  expect(screen.getByRole("button", { name: "Deactivate" })).toBeEnabled();
  expect(screen.getByRole("button", { name: "Activate" })).toBeEnabled();
});

it("previews permanent deletion and returns from deleted details to the layer", async () => {
  const { api, view } = fixture();
  render(view());
  const user = userEvent.setup();
  await user.click(screen.getByRole("button", { name: "Delete" }));
  expect(await screen.findByRole("dialog", { name: "Delete records permanently" })).toBeVisible();
  expect(screen.getByText(/This cannot be undone/)).toBeVisible();
  expect(api.applyModelRecordReview).not.toHaveBeenCalled();
  await user.click(await screen.findByRole("button", { name: "Delete 250 records permanently" }));
  await waitFor(() => expect(navigate).toHaveBeenCalledWith({
    to: "/tenants/$tenantId/models/$modelId/logical", params: { tenantId: "7", modelId: "18" },
  }));
  expect(api.applyModelRecordReview.mock.calls[0]?.[2]).toEqual({
    dataset: "logical_entity", record_ids: [41], action: "delete", expected_model_revision: 7,
    expected_plan_digest: preview.plan_digest,
  });
});
