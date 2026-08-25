import { useEffect, useRef, useState } from "react";
import { useForm, useStore } from "@tanstack/react-form";
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { Link } from "@tanstack/react-router";

import { ApiError } from "../../core/http";
import { formatRequiredDateTime as formatDateTime } from "../../shared/presentation";
import {
  promptQueryKeys,
  type PromptStageVariable,
  type PromptTemplateVersion,
  type PromptsApi,
} from "./api";
import {
  EditPromptHeaderDialog,
  PromptTransitionDialog,
} from "./PromptTemplateDialogs";
import { humanize, modeLabel, shortDigest } from "./PromptsLedger";

interface PendingTransition {
  action: "publish" | "retire";
  version: PromptTemplateVersion;
}

export function PromptTemplateDetailPage({
  api,
  tenantId,
  promptTemplateId,
  canAuthorPrompts,
  isSuperAdmin,
  hasTenantLock,
}: {
  api: PromptsApi;
  tenantId: number;
  promptTemplateId: number;
  canAuthorPrompts: boolean;
  isSuperAdmin: boolean;
  hasTenantLock: boolean;
}) {
  const heading = useRef<HTMLHeadingElement>(null);
  const queryClient = useQueryClient();
  const [selectedVersionId, setSelectedVersionId] = useState<number | null>(null);
  const [draftSeed, setDraftSeed] = useState<PromptTemplateVersion | "blank" | null>(null);
  const [editHeaderOpen, setEditHeaderOpen] = useState(false);
  const [pendingTransition, setPendingTransition] = useState<PendingTransition | null>(null);
  const query = useQuery({
    queryKey: promptQueryKeys.template(tenantId, promptTemplateId),
    queryFn: () => api.readPromptTemplate(tenantId, promptTemplateId),
  });
  const transitionMutation = useMutation({
    mutationFn: ({ action, version }: PendingTransition) => action === "publish"
      ? api.publishPromptVersion(tenantId, promptTemplateId, version.prompt_template_version_id)
      : api.retirePromptVersion(tenantId, promptTemplateId, version.prompt_template_version_id),
    onSuccess: async () => {
      setPendingTransition(null);
      await invalidatePromptQueries(queryClient, tenantId, promptTemplateId);
    },
  });

  useEffect(() => {
    if (query.data) heading.current?.focus();
  }, [query.data]);

  if (query.isPending) {
    return <main className="workspace prompt-detail-workspace"><div className="surface-state" aria-busy="true">Loading Prompt Template…</div></main>;
  }
  if (query.error instanceof ApiError && query.error.status === 403) {
    return (
      <main className="workspace prompt-detail-workspace">
        <div className="surface-state is-error" role="alert">
          You do not have permission to view this Prompt Template.
        </div>
      </main>
    );
  }
  if (query.isError) {
    return (
      <main className="workspace prompt-detail-workspace">
        <div className="surface-state is-error" role="alert">
          The Prompt Template could not be loaded.
        </div>
      </main>
    );
  }

  const detail = query.data;
  const { template } = detail;
  const draft = detail.versions.find((version) => (
    version.prompt_template_version_status === "draft"
  )) ?? null;
  const selected = detail.versions.find((version) => (
    version.prompt_template_version_id === selectedVersionId
  )) ?? draft ?? detail.versions[0] ?? null;
  const canMutate = template.prompt_template_ownership_scope === "global"
    ? isSuperAdmin
    : canAuthorPrompts && hasTenantLock;
  const authoringLabel = canMutate
    ? template.prompt_template_ownership_scope === "global"
      ? "Super Admin authoring"
      : "Tenant Lock held · Tenant Prompt authoring"
    : template.prompt_template_ownership_scope === "global"
      ? "Super Admin permission required"
      : !canAuthorPrompts
        ? "Architect permission required"
        : "Tenant Lock required for Tenant Prompt authoring";

  return (
    <main className="workspace prompt-detail-workspace page-enter">
      <header className="prompt-detail-commandbar">
        <div>
          <Link
            className="text-action"
            aria-label="Back to Prompts"
            to="/tenants/$tenantId/prompts"
            params={{ tenantId: String(tenantId) }}
          >
            ← Back to Prompts
          </Link>
          <p className="eyebrow">{template.prompt_template_code}</p>
          <h1 ref={heading} tabIndex={-1}>{template.prompt_template_name}</h1>
          <p>{template.prompt_template_description ?? "No description provided."}</p>
        </div>
        <div className="prompt-detail-actions">
          <span className={canMutate ? "lock-context is-held" : "lock-context"}>
            {authoringLabel}
          </span>
          <button
            className="button button-secondary button-small"
            type="button"
            disabled={query.isFetching}
            onClick={() => void query.refetch()}
          >
            {query.isFetching ? "Refreshing…" : "Refresh"}
          </button>
          <button
            className="button button-secondary button-small"
            type="button"
            disabled={!canMutate}
            title={authoringLabel}
            onClick={() => setEditHeaderOpen(true)}
          >
            Edit details
          </button>
        </div>
      </header>

      <section className="prompt-identity-strip" aria-label="Prompt Template identity">
        <Fact label="Visibility" value={template.prompt_template_ownership_scope === "global" ? "Global" : "This Tenant"} />
        <Fact label="Workflow" value={humanize(template.model_workflow)} />
        <Fact label="Execution mode" value={modeLabel(template.workflow_execution_mode)} />
        <Fact label="Stage" value={`${template.workflow_stage_name} · ${template.workflow_stage_code}`} />
        <Fact label="Template" value={template.is_active ? "Active" : "Inactive"} />
        <Fact label="Updated" value={formatDateTime(template.updated_at)} />
      </section>

      <div className="prompt-detail-layout">
        <aside className="prompt-history-panel" aria-labelledby="prompt-history-heading">
          <header>
            <div>
              <p className="eyebrow">Immutable record</p>
              <h2 id="prompt-history-heading">Version history</h2>
            </div>
            <span>{detail.versions.length}</span>
          </header>
          {detail.versions.length ? (
            <ol>
              {detail.versions.map((version) => (
                <li key={version.prompt_template_version_id}>
                  <button
                    className={selected?.prompt_template_version_id === version.prompt_template_version_id
                      ? "is-active"
                      : ""}
                    type="button"
                    aria-pressed={selected?.prompt_template_version_id === version.prompt_template_version_id}
                    onClick={() => {
                      setSelectedVersionId(version.prompt_template_version_id);
                      setDraftSeed(null);
                    }}
                  >
                    <span>
                      <strong>Version {version.prompt_template_version_number}</strong>
                      <small>{formatDateTime(version.updated_at)}</small>
                    </span>
                    <VersionState status={version.prompt_template_version_status} />
                    <code>{shortDigest(version.prompt_template_digest)}</code>
                  </button>
                </li>
              ))}
            </ol>
          ) : (
            <div className="empty-state compact">No versions saved yet.</div>
          )}
          {!draft && canMutate ? (
            <button
              className="button button-secondary button-small prompt-start-draft"
              type="button"
              onClick={() => setDraftSeed(selected ?? "blank")}
            >
              {selected ? `Start draft from v${selected.prompt_template_version_number}` : "Start first draft"}
            </button>
          ) : null}
        </aside>

        <section className="prompt-version-panel" aria-labelledby="prompt-version-heading">
          {draftSeed ? (
            <PromptBodyEditor
              key={draftSeed === "blank" ? "blank-draft" : `seed-${draftSeed.prompt_template_version_id}`}
              api={api}
              tenantId={tenantId}
              promptTemplateId={promptTemplateId}
              version={null}
              seed={draftSeed === "blank" ? null : draftSeed}
              onCancel={() => setDraftSeed(null)}
              onSaved={async (versionId) => {
                setDraftSeed(null);
                setSelectedVersionId(versionId);
                await invalidatePromptQueries(queryClient, tenantId, promptTemplateId);
              }}
            />
          ) : selected ? (
            <>
              <header className="prompt-version-header">
                <div>
                  <p className="eyebrow">Stored Prompt bodies</p>
                  <h2 id="prompt-version-heading">Version {selected.prompt_template_version_number}</h2>
                </div>
                <div>
                  <VersionState status={selected.prompt_template_version_status} />
                  {selected.prompt_template_version_status === "published" ? (
                    <button
                      className="button button-secondary button-small"
                      type="button"
                      disabled={!canMutate}
                      title={authoringLabel}
                      onClick={() => setPendingTransition({ action: "retire", version: selected })}
                    >
                      Retire version
                    </button>
                  ) : null}
                </div>
              </header>
              <VersionProvenance version={selected} />
              {selected.prompt_template_version_status === "draft" && canMutate ? (
                <PromptBodyEditor
                  key={`draft-${selected.prompt_template_version_id}-${selected.updated_at}`}
                  api={api}
                  tenantId={tenantId}
                  promptTemplateId={promptTemplateId}
                  version={selected}
                  seed={selected}
                  onCancel={null}
                  onPublish={() => setPendingTransition({ action: "publish", version: selected })}
                  onSaved={async (versionId) => {
                    setSelectedVersionId(versionId);
                    await invalidatePromptQueries(queryClient, tenantId, promptTemplateId);
                  }}
                />
              ) : (
                <PromptBodiesReadOnly version={selected} />
              )}
            </>
          ) : (
            <div className="empty-state">
              <h2 id="prompt-version-heading">No Prompt version</h2>
              <strong>No Prompt version exists.</strong>
              <span>Create the first draft to begin this Template history.</span>
            </div>
          )}
        </section>
      </div>

      <AllowedVariables variables={detail.allowed_variables} />

      <section className="prompt-assignment-gap" aria-labelledby="assignment-usage-heading">
        <div>
          <p className="eyebrow">Assignment visibility</p>
          <h2 id="assignment-usage-heading">Model assignment usage</h2>
          <p>The current API does not expose which Models use this Prompt Template.</p>
        </div>
        <button className="button button-secondary button-small" type="button" disabled>
          Usage list unavailable
        </button>
      </section>

      {editHeaderOpen ? (
        <EditPromptHeaderDialog
          api={api}
          tenantId={tenantId}
          template={template}
          onClose={() => setEditHeaderOpen(false)}
          onSaved={async () => {
            setEditHeaderOpen(false);
            await invalidatePromptQueries(queryClient, tenantId, promptTemplateId);
          }}
        />
      ) : null}
      {pendingTransition ? (
        <PromptTransitionDialog
          action={pendingTransition.action}
          template={template}
          version={pendingTransition.version}
          isPending={transitionMutation.isPending}
          isError={transitionMutation.isError}
          onClose={() => {
            if (!transitionMutation.isPending) {
              transitionMutation.reset();
              setPendingTransition(null);
            }
          }}
          onConfirm={() => transitionMutation.mutate(pendingTransition)}
        />
      ) : null}
    </main>
  );
}

function PromptBodyEditor({
  api,
  tenantId,
  promptTemplateId,
  version,
  seed,
  onCancel,
  onPublish,
  onSaved,
}: {
  api: PromptsApi;
  tenantId: number;
  promptTemplateId: number;
  version: PromptTemplateVersion | null;
  seed: PromptTemplateVersion | null;
  onCancel: (() => void) | null;
  onPublish?: () => void;
  onSaved: (versionId: number) => Promise<void>;
}) {
  const mutation = useMutation({
    mutationFn: ({ system, instruction, tool }: {
      system: string;
      instruction: string;
      tool: string;
    }) => api.savePromptDraft(tenantId, promptTemplateId, {
      expected_prompt_template_version_id: version?.prompt_template_version_id ?? null,
      expected_updated_at: version?.updated_at ?? null,
      system_prompt_template: system,
      instruction_prompt_template: instruction,
      tool_instruction_prompt_template: tool.trim() ? tool : null,
    }),
    onSuccess: async (saved) => onSaved(saved.prompt_template_version_id),
  });
  const form = useForm({
    defaultValues: {
      system: seed?.system_prompt_template ?? "",
      instruction: seed?.instruction_prompt_template ?? "",
      tool: seed?.tool_instruction_prompt_template ?? "",
    },
    onSubmit: ({ value }) => mutation.mutate(value),
  });
  const values = useStore(form.store, (state) => state.values);
  const isDirty = useStore(form.store, (state) => state.isDirty);
  const isValid = values.system.trim().length > 0
    && values.instruction.trim().length > 0
    && bodyBytes(values.system) <= 262_144
    && bodyBytes(values.instruction) <= 262_144
    && bodyBytes(values.tool) <= 262_144;
  const newDraft = version === null;

  return (
    <form
      className="prompt-body-editor"
      onSubmit={(event) => {
        event.preventDefault();
        event.stopPropagation();
        void form.handleSubmit();
      }}
    >
      {newDraft ? (
        <header className="prompt-version-header">
          <div>
            <p className="eyebrow">Unsaved working copy</p>
            <h2 id="prompt-version-heading">New draft</h2>
          </div>
          <span className="status-badge is-warning">Not yet stored</span>
        </header>
      ) : null}
      <p className="prompt-editor-note">
        Only variables in the reference below are accepted by this stage. Prompt bodies remain server-governed.
      </p>
      <form.Field name="system">
        {(field) => (
          <label>
            <span>System Prompt</span>
            <textarea
              aria-label="System Prompt"
              autoComplete="off"
              spellCheck={false}
              value={field.state.value}
              onBlur={field.handleBlur}
              onChange={(event) => field.handleChange(event.target.value)}
            />
            <small>{bodyBytes(field.state.value).toLocaleString()} / 262,144 UTF-8 bytes</small>
          </label>
        )}
      </form.Field>
      <form.Field name="instruction">
        {(field) => (
          <label>
            <span>Instruction Prompt</span>
            <textarea
              aria-label="Instruction Prompt"
              autoComplete="off"
              spellCheck={false}
              value={field.state.value}
              onBlur={field.handleBlur}
              onChange={(event) => field.handleChange(event.target.value)}
            />
            <small>{bodyBytes(field.state.value).toLocaleString()} / 262,144 UTF-8 bytes</small>
          </label>
        )}
      </form.Field>
      <form.Field name="tool">
        {(field) => (
          <label>
            <span>Tool instructions (optional)</span>
            <textarea
              aria-label="Tool instructions (optional)"
              autoComplete="off"
              spellCheck={false}
              value={field.state.value}
              onBlur={field.handleBlur}
              onChange={(event) => field.handleChange(event.target.value)}
            />
            <small>{bodyBytes(field.state.value).toLocaleString()} / 262,144 UTF-8 bytes</small>
          </label>
        )}
      </form.Field>
      {!isValid ? (
        <p className="prompt-validation-note">
          System and Instruction Prompts are required. Each body is limited to 262,144 UTF-8 bytes.
        </p>
      ) : null}
      {mutation.isError ? (
        <p className="inline-error" role="alert">
          The draft could not be saved. Refresh before retrying; another editor may have changed it.
        </p>
      ) : null}
      <footer className="prompt-editor-actions">
        <span>
          {version
            ? `Editing stored draft v${version.prompt_template_version_number} with timestamp fencing`
            : seed
              ? `New draft seeded from immutable v${seed.prompt_template_version_number}`
              : "New blank draft"}
        </span>
        <div>
          {onCancel ? (
            <button className="button button-secondary button-small" type="button" onClick={onCancel}>
              Cancel
            </button>
          ) : null}
          {onPublish ? (
            <button
              className="button button-secondary button-small"
              type="button"
              disabled={isDirty || mutation.isPending}
              title={isDirty ? "Save draft edits before publishing" : "Publish this saved draft"}
              onClick={onPublish}
            >
              Publish version
            </button>
          ) : null}
          <button
            className="button button-primary button-small"
            type="submit"
            disabled={!isValid || !isDirty || mutation.isPending}
          >
            {mutation.isPending ? "Saving…" : newDraft ? "Save new draft" : "Save draft"}
          </button>
        </div>
      </footer>
    </form>
  );
}

function PromptBodiesReadOnly({ version }: { version: PromptTemplateVersion }) {
  return (
    <div className="prompt-bodies-readonly">
      <ReadOnlyBody label="System Prompt" value={version.system_prompt_template} />
      <ReadOnlyBody label="Instruction Prompt" value={version.instruction_prompt_template} />
      <ReadOnlyBody
        label="Tool instructions"
        value={version.tool_instruction_prompt_template ?? "No tool instructions stored."}
      />
    </div>
  );
}

function ReadOnlyBody({ label, value }: { label: string; value: string }) {
  return (
    <label>
      <span>{label} · immutable</span>
      <textarea aria-label={`${label} immutable`} readOnly spellCheck={false} value={value} />
    </label>
  );
}

function VersionProvenance({ version }: { version: PromptTemplateVersion }) {
  return (
    <dl className="prompt-version-provenance">
      <Fact label="Digest" value={version.prompt_template_digest} code />
      <Fact label="Created" value={formatDateTime(version.created_at)} />
      <Fact label="Updated" value={formatDateTime(version.updated_at)} />
      <Fact
        label="Published"
        value={version.published_at ? formatDateTime(version.published_at) : "Not published"}
      />
      <Fact
        label="Retired"
        value={version.retired_at ? formatDateTime(version.retired_at) : "Not retired"}
      />
    </dl>
  );
}

function AllowedVariables({ variables }: { variables: PromptStageVariable[] }) {
  return (
    <section className="prompt-detail-variables" aria-labelledby="prompt-detail-variables-heading">
      <header>
        <div>
          <p className="eyebrow">Stage contract</p>
          <h2 id="prompt-detail-variables-heading">Allowed variables</h2>
        </div>
        <span>{variables.length}</span>
      </header>
      {variables.length ? (
        <div className="table-scroll">
          <table aria-label="Allowed Prompt variables">
            <thead><tr><th>Variable</th><th>Type</th><th>Resolver</th><th>Description</th></tr></thead>
            <tbody>
              {variables.map((variable) => (
                <tr key={variable.name}>
                  <td><code>{`{{${variable.name}}}`}</code>{variable.is_required ? <small>Required</small> : null}</td>
                  <td>{humanize(variable.data_type)}</td>
                  <td><code>{variable.resolver_key}</code></td>
                  <td>{variable.description}</td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      ) : (
        <div className="empty-state compact">This stage allows no variables.</div>
      )}
    </section>
  );
}

function VersionState({ status }: { status: PromptTemplateVersion["prompt_template_version_status"] }) {
  const tone = status === "published" ? "is-success" : status === "draft" ? "is-warning" : "is-neutral";
  return <span className={`status-badge ${tone}`}>{humanize(status)}</span>;
}

function Fact({ label, value, code = false }: { label: string; value: string; code?: boolean }) {
  return <div><dt>{label}</dt><dd>{code ? <code title={value}>{value}</code> : value}</dd></div>;
}

async function invalidatePromptQueries(
  queryClient: ReturnType<typeof useQueryClient>,
  tenantId: number,
  promptTemplateId: number,
) {
  await Promise.all([
    queryClient.invalidateQueries({ queryKey: promptQueryKeys.template(tenantId, promptTemplateId) }),
    queryClient.invalidateQueries({ queryKey: ["prompt-templates", tenantId] }),
    queryClient.invalidateQueries({ queryKey: ["assignable-prompt-versions", tenantId] }),
    queryClient.invalidateQueries({ queryKey: ["model-prompt-assignments", tenantId] }),
  ]);
}

function bodyBytes(value: string): number {
  return new TextEncoder().encode(value).byteLength;
}
