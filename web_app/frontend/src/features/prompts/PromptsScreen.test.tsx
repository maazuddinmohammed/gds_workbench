import { render, screen, within } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { createMemoryHistory } from "@tanstack/react-router";
import { describe, expect, it, vi } from "vitest";

import { createApiClient } from "../../api";
import { WorkbenchApp, createWorkbenchRouter } from "../../app";
import type {
  ModelPromptAssignmentState,
  PromptAssignmentTarget,
  PromptStageCatalog,
  PromptTemplateDetail,
  PromptTemplateHeader,
  PromptTemplateSummary,
  PromptTemplateVersion,
} from "./api";

describe("governed Prompts experience", () => {
  it("opens from the shell with server filters, page-local visibility, and allowed variables", async () => {
    const fetcher = promptFetchStub();
    const user = userEvent.setup();
    render(<WorkbenchApp router={createWorkbenchRouter({
      api: createApiClient(fetcher),
      history: createMemoryHistory({ initialEntries: ["/tenants/7"] }),
    })} />);

    const promptsLink = await screen.findByRole("link", { name: "Prompts" });
    expect(promptsLink).toHaveAttribute("href", "/tenants/7/prompts");
    await user.click(promptsLink);

    const ledger = await screen.findByRole("table", { name: "Prompt Templates" });
    expect(within(ledger).getByText("Tenant entity review")).toBeVisible();
    expect(within(ledger).getByText("Global entity review")).toBeVisible();

    await user.selectOptions(screen.getByLabelText("Workflow"), "logical");
    await user.selectOptions(screen.getByLabelText("Execution mode"), "tool_assisted");
    await user.selectOptions(screen.getByLabelText("Workflow stage filter"), "entity_review");
    await user.selectOptions(screen.getByLabelText("Latest version status"), "published");
    await user.click(screen.getByRole("button", { name: "Apply server filters" }));

    expect(fetcher).toHaveBeenCalledWith(
      "/api/v1/tenants/7/prompts/templates?workflow=logical&mode=tool_assisted&stage_code=entity_review&status=published&page_size=50",
      expect.objectContaining({ credentials: "same-origin" }),
    );
    await screen.findByRole("table", { name: "Prompt Templates" });
    const callsBeforeVisibility = templateListCalls(fetcher).length;
    await user.selectOptions(screen.getByLabelText("Visibility on this page"), "tenant");
    expect(screen.getByText("Local view · no server filter available")).toBeVisible();
    expect(screen.getByText("Tenant entity review")).toBeVisible();
    expect(screen.queryByText("Global entity review")).not.toBeInTheDocument();
    expect(templateListCalls(fetcher)).toHaveLength(callsBeforeVisibility);

    await user.click(screen.getByText("Allowed-variable reference"));
    expect(screen.getByText("{{entity_name}}")).toBeVisible();
    expect(screen.getByText(/Canonical Entity name/)).toBeVisible();
  });

  it("creates a Tenant Template in a focused dialog and navigates to its real detail route", async () => {
    const fetcher = promptFetchStub();
    const user = userEvent.setup();
    render(<WorkbenchApp router={createWorkbenchRouter({
      api: createApiClient(fetcher),
      history: createMemoryHistory({ initialEntries: ["/tenants/7/prompts"] }),
    })} />);

    await screen.findByRole("table", { name: "Prompt Templates" });
    await user.click(screen.getByRole("button", { name: "New Prompt Template" }));
    const dialog = await screen.findByRole("dialog", { name: "Create Prompt Template" });
    expect(within(dialog).getByRole("button", {
      name: "Close Prompt Template creation",
    })).toHaveFocus();
    await user.type(within(dialog).getByLabelText("Template code"), "logical.new_review");
    await user.type(within(dialog).getByLabelText("Template name"), "New review prompt");
    await user.type(within(dialog).getByLabelText("Description (optional)"), "Tenant review instructions");
    await user.click(within(dialog).getByRole("button", { name: "Create Template" }));

    const heading = await screen.findByRole("heading", { name: "New review prompt" });
    expect(heading).toHaveFocus();
    const createCall = fetcher.mock.calls.find(([input, init]) => (
      String(input) === "/api/v1/tenants/7/prompts/templates" && init?.method === "POST"
    ));
    expect(JSON.parse(String(createCall?.[1]?.body))).toEqual({
      workflow_stage_id: 4,
      prompt_template_ownership_scope: "tenant",
      prompt_template_code: "logical.new_review",
      prompt_template_name: "New review prompt",
      prompt_template_description: "Tenant review instructions",
      is_active: true,
    });

    await user.click(screen.getByRole("button", { name: "Start first draft" }));
    await user.type(screen.getByLabelText("System Prompt"), "New governed system body");
    await user.type(screen.getByLabelText("Instruction Prompt"), "New governed instruction body");
    await user.click(screen.getByRole("button", { name: "Save new draft" }));
    const newDraftCall = await waitForCall(fetcher, (input, init) => (
      input.endsWith("/prompts/templates/32/draft") && init?.method === "PUT"
    ));
    expect(JSON.parse(String(newDraftCall[1]?.body))).toEqual({
      expected_prompt_template_version_id: null,
      expected_updated_at: null,
      system_prompt_template: "New governed system body",
      instruction_prompt_template: "New governed instruction body",
      tool_instruction_prompt_template: null,
    });
  });

  it("saves a fenced draft, publishes it immutably, retires it, and renders bodies as inert text", async () => {
    const fetcher = promptFetchStub();
    const user = userEvent.setup();
    const { container } = render(<WorkbenchApp router={createWorkbenchRouter({
      api: createApiClient(fetcher),
      history: createMemoryHistory({ initialEntries: ["/tenants/7/prompts/templates/31"] }),
    })} />);

    const heading = await screen.findByRole("heading", { name: "Tenant entity review" });
    expect(heading).toHaveFocus();
    expect(screen.getByRole("table", { name: "Allowed Prompt variables" })).toBeVisible();
    expect(screen.getByRole("button", { name: "Usage list unavailable" })).toBeDisabled();
    expect(container.querySelector("script")).toBeNull();

    const systemEditor = screen.getByLabelText("System Prompt");
    expect(systemEditor).toHaveValue("Treat <script> as literal Prompt text.");
    await user.clear(systemEditor);
    await user.type(systemEditor, "Updated governed system body");
    await user.click(screen.getByRole("button", { name: "Save draft" }));

    const draftCall = await waitForCall(fetcher, (input, init) => (
      input.endsWith("/prompts/templates/31/draft") && init?.method === "PUT"
    ));
    expect(JSON.parse(String(draftCall[1]?.body))).toEqual({
      expected_prompt_template_version_id: 91,
      expected_updated_at: "2026-08-24T12:00:00Z",
      system_prompt_template: "Updated governed system body",
      instruction_prompt_template: "Review the modeled Entity.",
      tool_instruction_prompt_template: null,
    });

    await user.click(await screen.findByRole("button", { name: "Publish version" }));
    const publishDialog = await screen.findByRole("dialog", { name: "Publish immutable version" });
    expect(within(publishDialog).getByRole("button", {
      name: "Close Publish immutable version",
    })).toHaveFocus();
    await user.click(within(publishDialog).getByRole("button", { name: "Publish version" }));
    expect(await screen.findByLabelText("System Prompt immutable")).toHaveValue(
      "Updated governed system body",
    );
    expect(fetcher).toHaveBeenCalledWith(
      "/api/v1/tenants/7/prompts/templates/31/versions/91/publish",
      expect.objectContaining({ method: "POST" }),
    );

    await user.click(screen.getByRole("button", { name: "Retire version" }));
    const retireDialog = await screen.findByRole("dialog", { name: "Retire published version" });
    await user.click(within(retireDialog).getByRole("button", { name: "Retire version" }));
    expect(fetcher).toHaveBeenCalledWith(
      "/api/v1/tenants/7/prompts/templates/31/versions/91/retire",
      expect.objectContaining({ method: "POST" }),
    );
    expect((await screen.findAllByText("Retired"))[0]).toBeVisible();
  });

  it("shows effective Model provenance and changes only a lock-gated Model override", async () => {
    const fetcher = promptFetchStub();
    const user = userEvent.setup();
    const view = render(<WorkbenchApp router={createWorkbenchRouter({
      api: createApiClient(fetcher),
      history: createMemoryHistory({ initialEntries: ["/tenants/7/models/18/settings/prompts"] }),
    })} />);

    const table = await screen.findByRole("table", { name: "Effective Model Prompt assignments" });
    expect(within(table).getByText("Tenant entity review")).toBeVisible();
    expect(within(table).getAllByText("Model override")[0]).toBeVisible();
    expect(screen.getByRole("button", { name: "Global assignment unavailable" })).toBeDisabled();
    await user.click(screen.getByRole("button", { name: "Configure Entity review Prompt" }));
    const dialog = await screen.findByRole("dialog", { name: "Entity review" });
    expect(within(dialog).getByRole("button", {
      name: "Close Entity review Prompt assignment",
    })).toHaveFocus();
    await user.click(within(dialog).getByRole("radio", { name: /Use global/ }));
    await user.click(within(dialog).getByRole("button", { name: "Save assignment" }));

    const assignmentCall = await waitForCall(fetcher, (input, init) => (
      input.endsWith("/prompts/models/18/assignments/4") && init?.method === "PUT"
    ));
    expect(JSON.parse(String(assignmentCall[1]?.body))).toEqual({
      prompt_template_version_id: null,
      expected_prompt_assignment_id: 501,
    });
    expect(await screen.findByText("Global entity review")).toBeVisible();
    expect(screen.getByText("Global default")).toBeVisible();
    view.unmount();

    render(<WorkbenchApp router={createWorkbenchRouter({
      api: createApiClient(promptFetchStub({ hasLock: false })),
      history: createMemoryHistory({ initialEntries: ["/tenants/7/models/18/settings/prompts"] }),
    })} />);
    await screen.findByRole("table", { name: "Effective Model Prompt assignments" });
    expect(screen.getByText("Tenant Lock required to assign Prompts")).toBeVisible();
    expect(screen.getByRole("button", { name: "Configure Entity review Prompt" })).toBeDisabled();
  });

  it("keeps loading, empty, denied, and error Library states exact and redacted", async () => {
    const loading = render(<WorkbenchApp router={createWorkbenchRouter({
      api: createApiClient(promptFetchStub({ pendingLibrary: true })),
      history: createMemoryHistory({ initialEntries: ["/tenants/7/prompts"] }),
    })} />);
    expect(await screen.findByText("Loading governed Prompt Library…")).toBeVisible();
    loading.unmount();

    const empty = render(<WorkbenchApp router={createWorkbenchRouter({
      api: createApiClient(promptFetchStub({ emptyLibrary: true })),
      history: createMemoryHistory({ initialEntries: ["/tenants/7/prompts"] }),
    })} />);
    expect(await screen.findByText("No Prompt Templates match these server filters.")).toBeVisible();
    empty.unmount();

    const denied = render(<WorkbenchApp router={createWorkbenchRouter({
      api: createApiClient(promptFetchStub({ libraryStatus: 403 })),
      history: createMemoryHistory({ initialEntries: ["/tenants/7/prompts"] }),
    })} />);
    expect(await screen.findByRole("alert")).toHaveTextContent(
      "You do not have permission to view this Tenant Prompt Library.",
    );
    denied.unmount();

    render(<WorkbenchApp router={createWorkbenchRouter({
      api: createApiClient(promptFetchStub({ libraryStatus: 503 })),
      history: createMemoryHistory({ initialEntries: ["/tenants/7/prompts"] }),
    })} />);
    expect(await screen.findByRole("alert")).toHaveTextContent(
      "The Prompt Library could not be loaded.",
    );
    expect(screen.queryByText("secret persisted Prompt and physical row")).not.toBeInTheDocument();
  });
});

function promptFetchStub(options: {
  hasLock?: boolean;
  pendingLibrary?: boolean;
  emptyLibrary?: boolean;
  libraryStatus?: number;
} = {}) {
  let detail = structuredClone(promptDetail);
  let createdDetail = structuredClone(newPromptDetail);
  let modelAssignment = structuredClone(modelAssignmentState);
  return vi.fn<typeof fetch>(async (input, init) => {
    const url = String(input);
    const method = init?.method ?? "GET";
    if (url === "/api/v1/tenants/7/home") {
      return jsonResponse({
        ...tenantHome,
        lock: {
          ...tenantHome.lock,
          is_locked: options.hasLock ?? true,
          owned_by_current_principal: options.hasLock ?? true,
        },
      });
    }
    if (url === "/api/v1/tenants/7/models/18") return jsonResponse(modelDetail);
    if (url === "/api/v1/tenants/7/prompts/stages") {
      if (options.pendingLibrary) return await new Promise<Response>(() => undefined);
      if (options.libraryStatus) return libraryFailure(options.libraryStatus);
      return jsonResponse(promptStageCatalog);
    }
    if (url.startsWith("/api/v1/tenants/7/prompts/templates?") && method === "GET") {
      if (options.pendingLibrary) return await new Promise<Response>(() => undefined);
      if (options.libraryStatus) return libraryFailure(options.libraryStatus);
      return jsonResponse({
        tenant_id: 7,
        items: options.emptyLibrary ? [] : [detail.template, globalTemplateSummary],
        next_cursor: null,
      });
    }
    if (url === "/api/v1/tenants/7/prompts/templates" && method === "POST") {
      return jsonResponse(newPromptHeader, 201);
    }
    if (url === "/api/v1/tenants/7/prompts/templates/32" && method === "GET") {
      return jsonResponse(createdDetail);
    }
    if (url === "/api/v1/tenants/7/prompts/templates/32/draft" && method === "PUT") {
      const body = JSON.parse(String(init?.body)) as {
        system_prompt_template: string;
        instruction_prompt_template: string;
        tool_instruction_prompt_template: string | null;
      };
      const saved: PromptTemplateVersion = {
        ...promptDraft,
        ...body,
        prompt_template_version_id: 100,
        prompt_template_id: 32,
        prompt_template_version_number: 1,
        prompt_template_digest: digestA,
        created_at: "2026-08-24T13:05:00Z",
        updated_at: "2026-08-24T13:05:00Z",
      };
      createdDetail = {
        ...createdDetail,
        template: {
          ...createdDetail.template,
          latest_version_id: 100,
          latest_version_number: 1,
          latest_version_status: "draft",
          latest_version_digest: digestA,
          latest_version_updated_at: saved.updated_at,
          updated_at: saved.updated_at,
        },
        versions: [saved],
      };
      return jsonResponse(saved);
    }
    if (url === "/api/v1/tenants/7/prompts/templates/31" && method === "GET") {
      return jsonResponse(detail);
    }
    if (url === "/api/v1/tenants/7/prompts/templates/31" && method === "PUT") {
      const body = JSON.parse(String(init?.body)) as {
        prompt_template_name: string;
        prompt_template_description: string | null;
        is_active: boolean;
      };
      detail.template = {
        ...detail.template,
        prompt_template_name: body.prompt_template_name,
        prompt_template_description: body.prompt_template_description,
        is_active: body.is_active,
        updated_at: "2026-08-24T12:30:00Z",
      };
      return jsonResponse({ ...newPromptHeader, prompt_template_id: 31, ...body });
    }
    if (url === "/api/v1/tenants/7/prompts/templates/31/draft" && method === "PUT") {
      const body = JSON.parse(String(init?.body)) as {
        system_prompt_template: string;
        instruction_prompt_template: string;
        tool_instruction_prompt_template: string | null;
      };
      const current = detail.versions.find((version) => (
        version.prompt_template_version_id === 91
      )) ?? promptDraft;
      const saved = {
        ...current,
        ...body,
        updated_at: "2026-08-24T12:30:00Z",
      };
      detail.versions = [saved, ...detail.versions.filter((version) => (
        version.prompt_template_version_id !== 91
      ))];
      detail.template = {
        ...detail.template,
        latest_version_updated_at: saved.updated_at,
        updated_at: saved.updated_at,
      };
      return jsonResponse(saved);
    }
    if (url === "/api/v1/tenants/7/prompts/templates/31/versions/91/publish" && method === "POST") {
      const version = transitionVersion(detail, "published");
      return jsonResponse(version);
    }
    if (url === "/api/v1/tenants/7/prompts/templates/31/versions/91/retire" && method === "POST") {
      const version = transitionVersion(detail, "retired");
      return jsonResponse(version);
    }
    if (url === "/api/v1/tenants/7/prompts/models/18/assignments" && method === "GET") {
      return jsonResponse({ tenant_id: 7, model_id: 18, items: [modelAssignment] });
    }
    if (url === "/api/v1/tenants/7/prompts/models/18/assignments/4" && method === "PUT") {
      const body = JSON.parse(String(init?.body)) as { prompt_template_version_id: number | null };
      modelAssignment = body.prompt_template_version_id === null
        ? {
            ...modelAssignment,
            model_assignment: null,
            effective_source: "global_default",
            effective_assignment: globalAssignment,
          }
        : modelAssignment;
      return jsonResponse(modelAssignment);
    }
    return new Response(null, { status: 404 });
  });
}

function transitionVersion(
  detail: PromptTemplateDetail,
  status: "published" | "retired",
): PromptTemplateVersion {
  const current = detail.versions.find((version) => (
    version.prompt_template_version_id === 91
  )) ?? promptDraft;
  const transitioned: PromptTemplateVersion = {
    ...current,
    prompt_template_version_status: status,
    published_at: status === "published" ? "2026-08-24T12:40:00Z" : current.published_at,
    retired_at: status === "retired" ? "2026-08-24T12:50:00Z" : null,
    updated_at: status === "published" ? "2026-08-24T12:40:00Z" : "2026-08-24T12:50:00Z",
  };
  detail.versions = [transitioned, ...detail.versions.filter((version) => (
    version.prompt_template_version_id !== 91
  ))];
  detail.template = {
    ...detail.template,
    latest_version_status: status,
    latest_version_updated_at: transitioned.updated_at,
    updated_at: transitioned.updated_at,
  };
  return transitioned;
}

async function waitForCall(
  fetcher: ReturnType<typeof vi.fn<typeof fetch>>,
  matches: (input: string, init: RequestInit | undefined) => boolean,
) {
  await vi.waitFor(() => {
    expect(fetcher.mock.calls.some(([input, init]) => matches(String(input), init))).toBe(true);
  });
  const call = fetcher.mock.calls.find(([input, init]) => matches(String(input), init));
  if (!call) throw new Error("Expected request was not observed");
  return call;
}

function templateListCalls(fetcher: ReturnType<typeof vi.fn<typeof fetch>>) {
  return fetcher.mock.calls.filter(([input]) => String(input).includes("/prompts/templates?"));
}

function libraryFailure(status: number): Response {
  if (status === 403) return jsonResponse({ error: { code: "authorization_denied" } }, 403);
  return new Response("secret persisted Prompt and physical row", {
    status,
    headers: { "content-type": "text/plain" },
  });
}

function jsonResponse(value: unknown, status = 200): Response {
  return new Response(JSON.stringify(value), {
    status,
    headers: { "content-type": "application/json" },
  });
}

const digestA = "a".repeat(64);
const digestB = "b".repeat(64);
const digestC = "c".repeat(64);

const tenantHome = {
  tenant: {
    tenant_id: 7,
    tenant_code: "NWA",
    tenant_name: "Northwind Analytics",
    tenant_description: null,
    tenant_visibility: "private",
    effective_role: "tenant_admin",
  },
  lock: {
    is_locked: true,
    owner_display_name: "Maaz",
    owned_by_current_principal: true,
    purpose: "Model settings",
    acquired_at: "2026-08-24T11:00:00Z",
    expires_at: "2026-08-24T13:00:00Z",
  },
  lock_actions: { can_acquire: false, can_renew: true, can_release: true, can_override: false },
  systems: [],
};

const modelDetail = {
  model_id: 18,
  tenant_id: 7,
  model_name: "Customer 360",
  model_description: "Governed customer model",
  model_revision: 18,
  model_scope_object_count: 4,
  silver_model_naming_instructions: null,
  silver_model_audit_columns_template: null,
  gold_model_naming_instructions: null,
  gold_model_technical_columns_template: null,
  gold_model_audit_columns_template: null,
  default_agent_sdk_code: null,
  default_agent_provider_code: null,
  default_agent_model_code: null,
  default_reasoning_effort_code: null,
  default_max_turns: null,
  default_validation_retry_count: null,
  is_active: true,
  updated_at: "2026-08-24T11:00:00Z",
};

const promptStageCatalog: PromptStageCatalog = {
  tenant_id: 7,
  items: [{
    workflow_stage_id: 4,
    model_workflow: "logical",
    workflow_execution_mode: "tool_assisted",
    workflow_stage_code: "entity_review",
    workflow_stage_name: "Entity review",
    workflow_stage_description: "Review modeled Entities",
    workflow_stage_order: 1,
    allowed_variables: [{
      name: "entity_name",
      resolver_key: "logical.entity.name",
      data_type: "text",
      is_required: true,
      description: "Canonical Entity name",
      example: "Customer",
      order: 1,
    }],
  }],
};

const tenantTemplateSummary: PromptTemplateSummary = {
  prompt_template_id: 31,
  workflow_stage_id: 4,
  model_workflow: "logical",
  workflow_execution_mode: "tool_assisted",
  workflow_stage_code: "entity_review",
  workflow_stage_name: "Entity review",
  prompt_template_ownership_scope: "tenant",
  owner_tenant_id: 7,
  prompt_template_code: "logical.entity_review",
  prompt_template_name: "Tenant entity review",
  prompt_template_description: "Northwind Entity review",
  is_active: true,
  latest_version_id: 91,
  latest_version_number: 2,
  latest_version_status: "draft",
  latest_version_digest: digestB,
  latest_version_updated_at: "2026-08-24T12:00:00Z",
  updated_at: "2026-08-24T12:00:00Z",
};

const globalTemplateSummary: PromptTemplateSummary = {
  ...tenantTemplateSummary,
  prompt_template_id: 30,
  prompt_template_ownership_scope: "global",
  owner_tenant_id: null,
  prompt_template_code: "global.logical.entity_review",
  prompt_template_name: "Global entity review",
  prompt_template_description: "Workbench default",
  latest_version_id: 81,
  latest_version_number: 1,
  latest_version_status: "published",
  latest_version_digest: digestA,
};

const promptDraft: PromptTemplateVersion = {
  prompt_template_version_id: 91,
  prompt_template_id: 31,
  workflow_stage_id: 4,
  prompt_template_version_number: 2,
  system_prompt_template: "Treat <script> as literal Prompt text.",
  instruction_prompt_template: "Review the modeled Entity.",
  tool_instruction_prompt_template: null,
  prompt_template_digest: digestB,
  prompt_template_version_status: "draft",
  published_at: null,
  retired_at: null,
  created_at: "2026-08-24T12:00:00Z",
  updated_at: "2026-08-24T12:00:00Z",
};

const promptPublished: PromptTemplateVersion = {
  ...promptDraft,
  prompt_template_version_id: 90,
  prompt_template_version_number: 1,
  system_prompt_template: "Review Entity structure.",
  prompt_template_digest: digestC,
  prompt_template_version_status: "published",
  published_at: "2026-08-23T12:00:00Z",
  created_at: "2026-08-23T11:00:00Z",
  updated_at: "2026-08-23T12:00:00Z",
};

const promptDetail: PromptTemplateDetail = {
  tenant_id: 7,
  template: tenantTemplateSummary,
  allowed_variables: promptStageCatalog.items[0]?.allowed_variables ?? [],
  versions: [promptDraft, promptPublished],
};

const newPromptHeader: PromptTemplateHeader = {
  prompt_template_id: 32,
  workflow_stage_id: 4,
  prompt_template_ownership_scope: "tenant",
  owner_tenant_id: 7,
  prompt_template_code: "logical.new_review",
  prompt_template_name: "New review prompt",
  prompt_template_description: "Tenant review instructions",
  is_active: true,
  created_at: "2026-08-24T13:00:00Z",
  updated_at: "2026-08-24T13:00:00Z",
};

const newPromptDetail: PromptTemplateDetail = {
  tenant_id: 7,
  template: {
    ...tenantTemplateSummary,
    ...newPromptHeader,
    latest_version_id: null,
    latest_version_number: null,
    latest_version_status: null,
    latest_version_digest: null,
    latest_version_updated_at: null,
  },
  allowed_variables: promptStageCatalog.items[0]?.allowed_variables ?? [],
  versions: [],
};

const globalAssignment: PromptAssignmentTarget = {
  prompt_assignment_id: 401,
  prompt_assignment_scope: "global_default",
  prompt_template_version_id: 81,
  prompt_template_version_number: 1,
  prompt_template_digest: digestA,
  prompt_template_id: 30,
  prompt_template_ownership_scope: "global",
  owner_tenant_id: null,
  prompt_template_code: "global.logical.entity_review",
  prompt_template_name: "Global entity review",
  assigned_at: "2026-08-20T10:00:00Z",
};

const tenantAssignment: PromptAssignmentTarget = {
  prompt_assignment_id: 501,
  prompt_assignment_scope: "model_default",
  prompt_template_version_id: 90,
  prompt_template_version_number: 1,
  prompt_template_digest: digestC,
  prompt_template_id: 31,
  prompt_template_ownership_scope: "tenant",
  owner_tenant_id: 7,
  prompt_template_code: "logical.entity_review",
  prompt_template_name: "Tenant entity review",
  assigned_at: "2026-08-24T10:00:00Z",
};

const modelAssignmentState: ModelPromptAssignmentState = {
  workflow_stage_id: 4,
  model_workflow: "logical",
  workflow_execution_mode: "tool_assisted",
  workflow_stage_code: "entity_review",
  workflow_stage_name: "Entity review",
  workflow_stage_order: 1,
  model_assignment: tenantAssignment,
  global_assignment: globalAssignment,
  effective_source: "model_default",
  effective_assignment: tenantAssignment,
};
