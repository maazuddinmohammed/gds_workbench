import { useEffect, useRef } from "react";
import { useForm, useStore } from "@tanstack/react-form";
import { useMutation } from "@tanstack/react-query";

import { ApiError } from "../../core/http";
import type {
  PromptOwnershipScope,
  PromptStage,
  PromptTemplateSummary,
  PromptTemplateVersion,
  PromptsApi,
} from "./api";

export function CreatePromptDialog({
  api,
  tenantId,
  stages,
  isSuperAdmin,
  hasTenantLock,
  onClose,
  onCreated,
}: {
  api: PromptsApi;
  tenantId: number;
  stages: PromptStage[];
  isSuperAdmin: boolean;
  hasTenantLock: boolean;
  onClose: () => void;
  onCreated: (promptTemplateId: number) => Promise<void>;
}) {
  const closeButton = useRef<HTMLButtonElement>(null);
  const mutation = useMutation({
    mutationFn: (command: Parameters<PromptsApi["createPromptTemplate"]>[1]) => (
      api.createPromptTemplate(tenantId, command)
    ),
    onSuccess: async (created) => onCreated(created.prompt_template_id),
  });
  const form = useForm({
    defaultValues: {
      workflowStageId: stages[0] ? String(stages[0].workflow_stage_id) : "",
      ownershipScope: "tenant" as PromptOwnershipScope,
      code: "",
      name: "",
      description: "",
    },
    onSubmit: ({ value }) => {
      mutation.mutate({
        workflow_stage_id: Number(value.workflowStageId),
        prompt_template_ownership_scope: isSuperAdmin ? value.ownershipScope : "tenant",
        prompt_template_code: value.code.trim().toLocaleLowerCase(),
        prompt_template_name: value.name.trim(),
        prompt_template_description: value.description.trim() || null,
        is_active: true,
      });
    },
  });
  const values = useStore(form.store, (state) => state.values);
  const isValid = Number(values.workflowStageId) > 0
    && /^[a-z][a-z0-9_.-]{0,99}$/.test(values.code.trim().toLocaleLowerCase())
    && values.name.trim().length > 0
    && values.name.trim().length <= 200
    && values.description.trim().length <= 2000
    && (values.ownershipScope === "global" || hasTenantLock);

  useEffect(() => closeButton.current?.focus(), []);

  return (
    <div className="dialog-scrim prompt-dialog-scrim" role="presentation">
      <section
        className="run-configuration-dialog prompt-dialog"
        role="dialog"
        aria-modal="true"
        aria-labelledby="create-prompt-heading"
        onKeyDown={(event) => {
          if (event.key === "Escape") onClose();
        }}
      >
        <header className="drawer-header">
          <div>
            <small>Governed Prompt Library</small>
            <h2 id="create-prompt-heading">Create Prompt Template</h2>
          </div>
          <button
            ref={closeButton}
            className="panel-close"
            type="button"
            aria-label="Close Prompt Template creation"
            onClick={onClose}
          >
            <span aria-hidden="true">×</span>
          </button>
        </header>
        <form
          className="prompt-dialog-form"
          onSubmit={(event) => {
            event.preventDefault();
            event.stopPropagation();
            void form.handleSubmit();
          }}
        >
          <p className="prompt-dialog-intro">
            Stage, visibility, and code become the Template identity. They cannot be edited later.
          </p>
          <form.Field name="workflowStageId">
            {(field) => (
              <label>
                <span>Workflow stage</span>
                <select
                  aria-label="Workflow stage"
                  value={field.state.value}
                  onChange={(event) => field.handleChange(event.target.value)}
                >
                  {stages.map((stage) => (
                    <option key={stage.workflow_stage_id} value={stage.workflow_stage_id}>
                      {stageLabel(stage)}
                    </option>
                  ))}
                </select>
              </label>
            )}
          </form.Field>
          {isSuperAdmin ? (
            <form.Field name="ownershipScope">
              {(field) => (
                <fieldset className="prompt-ownership-options">
                  <legend>Visibility</legend>
                  {(["tenant", "global"] as const).map((scope) => (
                    <label key={scope}>
                      <input
                        type="radio"
                        name={field.name}
                        value={scope}
                        checked={field.state.value === scope}
                        onChange={() => field.handleChange(scope)}
                      />
                      <span>
                        <strong>{scope === "tenant" ? "This Tenant" : "Global"}</strong>
                        <small>
                          {scope === "tenant"
                            ? "Visible only inside this Tenant"
                            : "Visible to every authorized Tenant"}
                        </small>
                      </span>
                    </label>
                  ))}
                </fieldset>
              )}
            </form.Field>
          ) : (
            <p className="prompt-fixed-identity"><strong>Visibility</strong> · This Tenant</p>
          )}
          {values.ownershipScope === "tenant" && !hasTenantLock ? (
            <p className="inline-error" role="status">
              Tenant Lock is required to create a Tenant Prompt Template.
            </p>
          ) : null}
          <form.Field name="code">
            {(field) => (
              <label>
                <span>Template code</span>
                <input
                  aria-label="Template code"
                  autoComplete="off"
                  maxLength={100}
                  placeholder="logical.entity_review"
                  value={field.state.value}
                  onBlur={field.handleBlur}
                  onChange={(event) => field.handleChange(event.target.value)}
                />
                <small>Lowercase letters, digits, dot, dash, or underscore.</small>
              </label>
            )}
          </form.Field>
          <form.Field name="name">
            {(field) => (
              <label>
                <span>Template name</span>
                <input
                  aria-label="Template name"
                  maxLength={200}
                  value={field.state.value}
                  onBlur={field.handleBlur}
                  onChange={(event) => field.handleChange(event.target.value)}
                />
              </label>
            )}
          </form.Field>
          <form.Field name="description">
            {(field) => (
              <label>
                <span>Description (optional)</span>
                <textarea
                  aria-label="Description (optional)"
                  maxLength={2000}
                  rows={3}
                  value={field.state.value}
                  onBlur={field.handleBlur}
                  onChange={(event) => field.handleChange(event.target.value)}
                />
              </label>
            )}
          </form.Field>
          {mutation.isError ? (
            <p className="inline-error" role="alert">
              {mutation.error instanceof ApiError && mutation.error.status === 403
                ? "You do not have permission to create this Prompt Template."
                : "The Prompt Template could not be created. Review current Library state."}
            </p>
          ) : null}
          <footer className="dialog-actions">
            <p>The backend rechecks Tenant Lock, ownership, and authoring permission.</p>
            <div>
              <button className="button button-secondary button-small" type="button" onClick={onClose}>
                Cancel
              </button>
              <button
                className="button button-primary button-small"
                type="submit"
                disabled={!isValid || mutation.isPending}
              >
                {mutation.isPending ? "Creating…" : "Create Template"}
              </button>
            </div>
          </footer>
        </form>
      </section>
    </div>
  );
}

export function PromptTransitionDialog({
  action,
  template,
  version,
  isPending,
  isError,
  onClose,
  onConfirm,
}: {
  action: "publish" | "retire";
  template: PromptTemplateSummary;
  version: PromptTemplateVersion;
  isPending: boolean;
  isError: boolean;
  onClose: () => void;
  onConfirm: () => void;
}) {
  const closeButton = useRef<HTMLButtonElement>(null);
  const title = action === "publish" ? "Publish immutable version" : "Retire published version";
  useEffect(() => closeButton.current?.focus(), []);

  return (
    <div className="dialog-scrim prompt-dialog-scrim" role="presentation">
      <section
        className="run-configuration-dialog prompt-transition-dialog"
        role="dialog"
        aria-modal="true"
        aria-labelledby="prompt-transition-heading"
        onKeyDown={(event) => {
          if (event.key === "Escape" && !isPending) onClose();
        }}
      >
        <header className="drawer-header">
          <div>
            <small>{template.prompt_template_name} · version {version.prompt_template_version_number}</small>
            <h2 id="prompt-transition-heading">{title}</h2>
          </div>
          <button
            ref={closeButton}
            className="panel-close"
            type="button"
            aria-label={`Close ${title}`}
            disabled={isPending}
            onClick={onClose}
          >
            <span aria-hidden="true">×</span>
          </button>
        </header>
        <div className="prompt-transition-copy">
          <p>
            {action === "publish"
              ? "Publishing freezes these three Prompt bodies and their digest. Future edits require a new draft version."
              : "Retirement prevents new assignments. Active assignments may block this transition."}
          </p>
          <dl className="detail-fact-grid">
            <div><dt>Version</dt><dd>v{version.prompt_template_version_number}</dd></div>
            <div><dt>Digest</dt><dd><code>{shortDigest(version.prompt_template_digest)}</code></dd></div>
            <div><dt>Current state</dt><dd>{humanize(version.prompt_template_version_status)}</dd></div>
          </dl>
          {isError ? (
            <p className="inline-error" role="alert">
              The version could not be {action === "publish" ? "published" : "retired"}. Refresh and inspect current state.
            </p>
          ) : null}
        </div>
        <footer className="dialog-actions">
          <p>This action is explicit and server-validated.</p>
          <div>
            <button
              className="button button-secondary button-small"
              type="button"
              disabled={isPending}
              onClick={onClose}
            >
              Cancel
            </button>
            <button
              className="button button-primary button-small"
              type="button"
              disabled={isPending}
              onClick={onConfirm}
            >
              {isPending ? "Applying…" : action === "publish" ? "Publish version" : "Retire version"}
            </button>
          </div>
        </footer>
      </section>
    </div>
  );
}

export function EditPromptHeaderDialog({
  api,
  tenantId,
  template,
  onClose,
  onSaved,
}: {
  api: PromptsApi;
  tenantId: number;
  template: PromptTemplateSummary;
  onClose: () => void;
  onSaved: () => Promise<void>;
}) {
  const closeButton = useRef<HTMLButtonElement>(null);
  const mutation = useMutation({
    mutationFn: ({
      name,
      description,
      isActive,
    }: {
      name: string;
      description: string;
      isActive: boolean;
    }) => api.updatePromptTemplate(tenantId, template.prompt_template_id, {
      prompt_template_name: name.trim(),
      prompt_template_description: description.trim() || null,
      is_active: isActive,
      expected_updated_at: template.updated_at,
    }),
    onSuccess: onSaved,
  });
  const form = useForm({
    defaultValues: {
      name: template.prompt_template_name,
      description: template.prompt_template_description ?? "",
      isActive: template.is_active,
    },
    onSubmit: ({ value }) => mutation.mutate(value),
  });
  const values = useStore(form.store, (state) => state.values);
  const isValid = values.name.trim().length > 0
    && values.name.trim().length <= 200
    && values.description.trim().length <= 2000;

  useEffect(() => closeButton.current?.focus(), []);

  return (
    <div className="dialog-scrim prompt-dialog-scrim" role="presentation">
      <section
        className="run-configuration-dialog prompt-dialog prompt-header-dialog"
        role="dialog"
        aria-modal="true"
        aria-labelledby="edit-prompt-header-heading"
        onKeyDown={(event) => {
          if (event.key === "Escape") onClose();
        }}
      >
        <header className="drawer-header">
          <div>
            <small>{template.prompt_template_code}</small>
            <h2 id="edit-prompt-header-heading">Edit Template details</h2>
          </div>
          <button
            ref={closeButton}
            className="panel-close"
            type="button"
            aria-label="Close Template details editor"
            onClick={onClose}
          >
            <span aria-hidden="true">×</span>
          </button>
        </header>
        <form
          className="prompt-dialog-form"
          onSubmit={(event) => {
            event.preventDefault();
            event.stopPropagation();
            void form.handleSubmit();
          }}
        >
          <p className="prompt-fixed-identity">
            <strong>Immutable identity</strong> · {template.workflow_stage_code} · {template.prompt_template_ownership_scope}
          </p>
          <form.Field name="name">
            {(field) => (
              <label>
                <span>Template name</span>
                <input
                  aria-label="Template name"
                  maxLength={200}
                  value={field.state.value}
                  onBlur={field.handleBlur}
                  onChange={(event) => field.handleChange(event.target.value)}
                />
              </label>
            )}
          </form.Field>
          <form.Field name="description">
            {(field) => (
              <label>
                <span>Description (optional)</span>
                <textarea
                  aria-label="Description (optional)"
                  maxLength={2000}
                  rows={4}
                  value={field.state.value}
                  onBlur={field.handleBlur}
                  onChange={(event) => field.handleChange(event.target.value)}
                />
              </label>
            )}
          </form.Field>
          <form.Field name="isActive">
            {(field) => (
              <label className="prompt-active-toggle">
                <input
                  type="checkbox"
                  checked={field.state.value}
                  onChange={(event) => field.handleChange(event.target.checked)}
                />
                <span>
                  <strong>Template active</strong>
                  <small>Inactive Templates cannot receive new assignments.</small>
                </span>
              </label>
            )}
          </form.Field>
          {mutation.isError ? (
            <p className="inline-error" role="alert">
              The Template details could not be saved. Refresh and inspect current state.
            </p>
          ) : null}
          <footer className="dialog-actions">
            <p>Timestamp fencing prevents an older editor from overwriting newer state.</p>
            <div>
              <button className="button button-secondary button-small" type="button" onClick={onClose}>
                Cancel
              </button>
              <button
                className="button button-primary button-small"
                type="submit"
                disabled={!isValid || mutation.isPending}
              >
                {mutation.isPending ? "Saving…" : "Save details"}
              </button>
            </div>
          </footer>
        </form>
      </section>
    </div>
  );
}

function stageLabel(stage: PromptStage): string {
  return `${humanize(stage.model_workflow)} · ${modeLabel(stage.workflow_execution_mode)} · ${stage.workflow_stage_name}`;
}

function modeLabel(value: PromptStage["workflow_execution_mode"]): string {
  return value ? humanize(value) : "Default mode";
}

function humanize(value: string): string {
  return value.replaceAll("_", " ").replace(/^./, (character) => character.toLocaleUpperCase());
}

function shortDigest(value: string): string {
  return `${value.slice(0, 12)}…${value.slice(-8)}`;
}
