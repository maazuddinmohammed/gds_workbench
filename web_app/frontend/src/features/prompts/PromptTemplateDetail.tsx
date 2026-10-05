import { useEffect, useRef, useState } from "react";
import { useForm, useStore } from "@tanstack/react-form";
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { Link, useBlocker } from "@tanstack/react-router";

import { Fact } from "../../shared/ui";
import { ApiError } from "../../core/http";
import { formatRequiredDateTime as formatDateTime } from "../../shared/presentation";
import {
  promptQueryKeys,
  type PromptStageVariable,
  type PromptTool,
  type PromptTemplateVersion,
  type PromptsApi,
} from "./api";
import {
  EditPromptHeaderDialog,
  PromptTransitionDialog,
} from "./PromptTemplateDialogs";
import { humanize, modeLabel } from "./PromptsLedger";
import { PromptVariables } from "./PromptVariables";
import { PromptTextEditor } from "./PromptTextEditor";
import { PromptTools } from "./PromptTools";

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
  const [editorDirty, setEditorDirty] = useState(false);
  const [editorGeneration, setEditorGeneration] = useState(0);
  const [pendingAction, setPendingAction] = useState<(() => void) | null>(null);
  const navigation = useBlocker({
    shouldBlockFn: () => editorDirty,
    enableBeforeUnload: editorDirty,
    withResolver: true,
  });
  const confirmDiscard = (action: () => void) => {
    if (editorDirty) setPendingAction(() => action);
    else action();
  };
  const query = useQuery({
    queryKey: promptQueryKeys.template(tenantId, promptTemplateId),
    queryFn: () => api.readPromptTemplate(tenantId, promptTemplateId),
    refetchOnWindowFocus: false,
    refetchOnReconnect: false,
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
          <p className="prompt-context-line">{template.prompt_template_ownership_scope === "global" ? "Global" : "This Tenant"} · {humanize(template.model_workflow)} · {modeLabel(template.workflow_execution_mode)} · {template.workflow_stage_name}{!template.is_active ? " · Inactive" : ""}</p>
          <h1 ref={heading} tabIndex={-1}>{template.prompt_template_name}</h1>
          {template.prompt_template_description ? <p>{template.prompt_template_description}</p> : null}
        </div>
        <div className="prompt-detail-actions">
          <span className={canMutate ? "lock-context is-held" : "lock-context"}>
            {canMutate ? "Editing available" : "Read-only"}
          </span>
          <button
            className="button button-secondary button-small"
            type="button"
            disabled={query.isFetching}
            onClick={() => confirmDiscard(() => { setEditorGeneration((value) => value + 1); void query.refetch(); })}
          >
            {query.isFetching ? "Refreshing…" : "Refresh"}
          </button>
          <button
            className="button button-secondary button-small"
            type="button"
            disabled={!canMutate}
            title={authoringLabel}
            onClick={() => confirmDiscard(() => { setEditorGeneration((value) => value + 1); setEditHeaderOpen(true); })}
          >
            Edit details
          </button>
        </div>
      </header>

      {pendingAction || navigation.status === "blocked" ? <div className="prompt-discard-confirmation" role="alert">
        <span>Discard unsaved prompt edits?</span>
        <button className="button button-secondary button-small" type="button" onClick={() => { setPendingAction(null); navigation.reset?.(); }}>Keep editing</button>
        <button className="button button-primary button-small" type="button" onClick={() => {
          setEditorDirty(false);
          const action = pendingAction;
          setPendingAction(null);
          if (action) action();
          else navigation.proceed?.();
        }}>Discard edits</button>
      </div> : null}

      <div className="prompt-detail-layout">
        <aside className="prompt-history-panel" aria-label="Version history">
          <details><summary>Version history <span>{detail.versions.length}</span></summary>
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
                    onClick={() => confirmDiscard(() => {
                      setSelectedVersionId(version.prompt_template_version_id);
                      setDraftSeed(null);
                      setEditorGeneration((value) => value + 1);
                    })}
                  >
                    <span>
                      <strong>Version {version.prompt_template_version_number}</strong>
                      <small>{formatDateTime(version.updated_at)}</small>
                    </span>
                    <VersionState status={version.prompt_template_version_status} />
                  </button>
                </li>
              ))}
            </ol>
          ) : (
            <div className="empty-state compact">No versions saved yet.</div>
          )}
          </details>
          {!draft && !draftSeed && canMutate ? (
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
              key={`${draftSeed === "blank" ? "blank-draft" : `seed-${draftSeed.prompt_template_version_id}`}-${editorGeneration}`}
              api={api}
              tenantId={tenantId}
              promptTemplateId={promptTemplateId}
              availableTools={detail.available_tools ?? []}
              variables={detail.allowed_variables}
              version={null}
              seed={draftSeed === "blank" ? null : draftSeed}
              onDirtyChange={setEditorDirty}
              onCancel={() => confirmDiscard(() => setDraftSeed(null))}
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
              {selected.prompt_template_version_status === "draft" && canMutate ? (
                <PromptBodyEditor
                  key={`draft-${selected.prompt_template_version_id}-${selected.updated_at}-${editorGeneration}`}
                  api={api}
                  tenantId={tenantId}
                  promptTemplateId={promptTemplateId}
                  availableTools={detail.available_tools ?? []}
                  variables={detail.allowed_variables}
                  version={selected}
                  seed={selected}
                  onDirtyChange={setEditorDirty}
                  onCancel={null}
                  onPublish={() => setPendingTransition({ action: "publish", version: selected })}
                  onSaved={async (versionId) => {
                    setSelectedVersionId(versionId);
                    await invalidatePromptQueries(queryClient, tenantId, promptTemplateId);
                  }}
                />
              ) : (
                <>
                <PromptBodiesReadOnly key={selected.prompt_template_version_id} version={selected} />
                {(detail.available_tools?.length ?? 0) > 0 || (selected.agent_tool_names?.length ?? 0) > 0 ? (
                  <details className="prompt-version-details"><summary>Enabled tools</summary>{selected.agent_tool_names?.length === 0 ? <p className="prompt-editor-note">No tools enabled for this version.</p> : <ul>{(selected.agent_tool_names ?? (detail.available_tools ?? []).map((tool) => tool.name)).map((name) => <li key={name}><code>{name}</code></li>)}</ul>}</details>
                ) : null}
                </>
              )}
              <details className="prompt-version-details"><summary>Version details</summary><VersionProvenance version={selected} /></details>
            </>
          ) : (
            <div className="empty-state">
              <h2 id="prompt-version-heading">No Prompt version</h2>
              <span>Start the first draft to add instructions.</span>
            </div>
          )}
        </section>
      </div>

      {!draftSeed && !(selected?.prompt_template_version_status === "draft" && canMutate) ? <AllowedVariables variables={detail.allowed_variables} /> : null}


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
  availableTools,
  variables,
  seed,
  onCancel,
  onPublish,
  onSaved,
  onDirtyChange,
}: {
  api: PromptsApi;
  tenantId: number;
  promptTemplateId: number;
  version: PromptTemplateVersion | null;
  availableTools: PromptTool[];
  variables: PromptStageVariable[];
  seed: PromptTemplateVersion | null;
  onCancel: (() => void) | null;
  onPublish?: () => void;
  onSaved: (versionId: number) => Promise<void>;
  onDirtyChange: (dirty: boolean) => void;
}) {
  const editorRefs = useRef<Partial<Record<"system" | "instruction" | "tool", HTMLTextAreaElement>>>({});
  const [activePrompt, setActivePrompt] = useState<"system" | "instruction" | "tool">("instruction");
  const preview = useMutation({
    mutationFn: (command: Parameters<PromptsApi["previewPrompt"]>[2]) => api.previewPrompt(tenantId, promptTemplateId, command),
  });
  const mutation = useMutation({
    mutationFn: ({ system, instruction, tool, toolNames }: {
      system: string;
      instruction: string;
      tool: string;
      toolNames: string[] | null;
    }) => api.savePromptDraft(tenantId, promptTemplateId, {
      expected_prompt_template_version_id: version?.prompt_template_version_id ?? null,
      expected_updated_at: version?.updated_at ?? null,
      system_prompt_template: system,
      instruction_prompt_template: instruction,
      tool_instruction_prompt_template: tool.trim() ? tool : null,
      agent_tool_names: toolNames,
    }),
    onSuccess: async (saved) => {
      onDirtyChange(false);
      await onSaved(saved.prompt_template_version_id);
    },
  });
  const form = useForm({
    defaultValues: {
      system: seed?.system_prompt_template ?? "",
      instruction: seed?.instruction_prompt_template ?? "",
      tool: seed?.tool_instruction_prompt_template ?? "",
      toolNames: seed?.agent_tool_names ?? null as string[] | null,
    },
    onSubmit: ({ value }) => mutation.mutate(value),
  });
  const values = useStore(form.store, (state) => state.values);
  const isDirty = useStore(form.store, (state) => state.isDirty);
  useEffect(() => { onDirtyChange(isDirty); }, [isDirty, onDirtyChange]);
  useEffect(() => () => onDirtyChange(false), [onDirtyChange]);
  const isValid = values.system.trim().length > 0
    && values.instruction.trim().length > 0;
  const newDraft = version === null;
  const previewCommand = {
    system_prompt_template: values.system,
    instruction_prompt_template: values.instruction,
    tool_instruction_prompt_template: values.tool.trim() ? values.tool : null,
    agent_tool_names: values.toolNames,
  };
  const previewIsCurrent = JSON.stringify(preview.variables) === JSON.stringify(previewCommand);

  const insertVariable = (name: string) => {
    const textarea = editorRefs.current[activePrompt];
    const body = values[activePrompt];
    const start = textarea?.selectionStart ?? body.length;
    const end = textarea?.selectionEnd ?? start;
    const placeholder = `{{ ${name} }}`;
    form.setFieldValue(activePrompt, `${body.slice(0, start)}${placeholder}${body.slice(end)}`);
    requestAnimationFrame(() => {
      textarea?.focus();
      textarea?.setSelectionRange(start + placeholder.length, start + placeholder.length);
    });
  };

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
            <h2 id="prompt-version-heading">New draft</h2>
          </div>
          <span className="status-badge is-warning">Not yet stored</span>
        </header>
      ) : null}
      <div className="prompt-body-tabs" role="group" aria-label="Prompt content">
        {([ ["instruction", "Instructions"], ["system", "System"], ["tool", "Tool instructions"] ] as const).map(([field, label]) => (
          <button key={field} type="button" aria-pressed={activePrompt === field} onClick={() => setActivePrompt(field)}>{label}</button>
        ))}
      </div>
      {([ ["system", "System Prompt"], ["instruction", "Instruction Prompt"], ["tool", "Tool instructions (optional)"] ] as const).map(([name, label]) => (
        <div key={name} hidden={activePrompt !== name}>
          <form.Field name={name}>{(field) => <PromptTextEditor label={label} value={field.state.value}
            disabled={mutation.isPending} onChange={field.handleChange} onBlur={field.handleBlur}
            onFocus={() => setActivePrompt(name)} editorRef={(element) => { editorRefs.current[name] = element; }} />}</form.Field>
        </div>
      ))}
      <AllowedVariables variables={variables} onInsert={insertVariable} activePrompt={activePrompt} disabled={mutation.isPending} />
      {availableTools.length > 0 ? <details className="prompt-version-details prompt-tools-disclosure"><summary>Enabled tools <span>{(values.toolNames ?? availableTools).length}</span></summary>
        <form.Field name="toolNames">
          {(field) => <PromptTools tools={availableTools} selected={field.state.value ?? availableTools.map((tool) => tool.name)} disabled={mutation.isPending} onChange={field.handleChange} />}
        </form.Field>
      </details> : null}
      <details className="prompt-rendering-help">
        <summary>How to use variables</summary>
        <p>Insert a whole value with <code>{"{{ variable_name }}"}</code>, or select a field or list item. Use Jinja conditions and loops to shape the context. Python execution is not supported.</p>
        <pre>{"{{ object_context }}\n{{ object_context[0].object_name }}\n{% for object in object_context %}\n{{ object.object_name }}\n{% endfor %}"}</pre>
        <p>Use only variables and fields in this workflow’s reference. Missing data is null. Unknown names or invalid expressions fail validation. Values are rendered once; braces inside their data remain literal.</p>
      </details>
      {!isValid ? (
        <p className="prompt-validation-note">
          System and Instruction Prompts are required.
        </p>
      ) : null}
      {mutation.isError ? (
        <p className="inline-error" role="alert">
          {mutation.error instanceof ApiError && mutation.error.status === 409
            ? "This draft changed after you opened it. Your edits are still here; copy them before refreshing to inspect the newer version."
            : mutation.error instanceof ApiError && [400, 422].includes(mutation.error.status)
              ? "The draft failed validation. Check variable names, expressions, and tool choices. Your edits are still here."
              : "The draft could not be saved. Your edits are still here. Check your permission and Tenant Lock, then retry."}
        </p>
      ) : null}
      <section className="prompt-preview-section" aria-label="Prompt preview">
        <div className="prompt-preview-heading"><p className="prompt-editor-note">Preview uses example values and makes no model call.</p>
          <button className="button button-secondary button-small" type="button" disabled={!isValid || preview.isPending || mutation.isPending} onClick={() => preview.mutate(previewCommand)}>{preview.isPending ? "Rendering preview…" : "Preview prompts"}</button>
        </div>
        {preview.isError && previewIsCurrent ? <p className="inline-error" role="alert">Preview could not be rendered. Check variable names, fields, and Jinja syntax against the reference. Your edits are unchanged.</p> : null}
        {preview.data && !previewIsCurrent ? <p className="prompt-editor-note" role="status">Prompts or tools changed. Preview again to see the current text.</p> : null}
        {preview.data && previewIsCurrent ? <div className="prompt-preview-results"><p className="prompt-editor-note" role="status">Preview rendered successfully with synthetic data.</p>{[
          ["System Prompt", preview.data.rendered_system_prompt],
          ["Instruction Prompt", preview.data.rendered_instruction_prompt],
          ["Tool instructions", preview.data.rendered_tool_instruction_prompt],
        ].map(([label, value]) => value ? <details className="prompt-input-shape" key={label} open><summary>{label} preview</summary><pre>{value}</pre></details> : null)}</div> : null}
      </section>
      <footer className="prompt-editor-actions">
        <span>
          {version
            ? isDirty ? "Unsaved changes" : `Draft v${version.prompt_template_version_number} saved`
            : seed
              ? `New draft from v${seed.prompt_template_version_number}`
              : "New blank draft"}
        </span>
        <div>
          <button className="button button-secondary button-small" type="button" disabled={!isDirty || mutation.isPending} onClick={() => { form.reset(); mutation.reset(); preview.reset(); }}>Reset edits</button>
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
  const [selectedBody, setSelectedBody] = useState("Instruction Prompt");
  const bodies: [string, string][] = [
    ["Instruction Prompt", version.instruction_prompt_template],
    ["System Prompt", version.system_prompt_template],
    ...(version.tool_instruction_prompt_template ? [["Tool instructions", version.tool_instruction_prompt_template] as [string, string]] : []),
  ];
  return <div className="prompt-bodies-readonly">
    <div className="prompt-body-tabs" role="group" aria-label="Prompt content">
      {bodies.map(([label]) => <button key={label} type="button" aria-pressed={selectedBody === label} onClick={() => setSelectedBody(label!)}>{label === "Instruction Prompt" ? "Instructions" : label === "System Prompt" ? "System" : label}</button>)}
    </div>
    {bodies.map(([label, value]) => <div key={label} hidden={selectedBody !== label}><PromptTextEditor label={label!} value={value!} readOnly /></div>)}
  </div>;
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

function AllowedVariables({ variables, onInsert, activePrompt, disabled }: {
  variables: PromptStageVariable[];
  onInsert?: (name: string) => void;
  activePrompt?: "system" | "instruction" | "tool";
  disabled?: boolean;
}) {
  return (
    <details className="prompt-detail-variables" aria-labelledby="prompt-detail-variables-heading">
      <summary><h2 id="prompt-detail-variables-heading">Allowed variables</h2><span>{variables.length}</span></summary>
      {onInsert ? <p className="prompt-editor-note">Insert into: <strong>{activePrompt === "system" ? "System Prompt" : activePrompt === "tool" ? "Tool instructions" : "Instruction Prompt"}</strong>. Select text in a prompt to replace it.</p> : null}
      <PromptVariables variables={variables} onInsert={onInsert} disabled={disabled} />
    </details>
  );
}

function VersionState({ status }: { status: PromptTemplateVersion["prompt_template_version_status"] }) {
  const tone = status === "published" ? "is-success" : status === "draft" ? "is-warning" : "is-neutral";
  return <span className={`status-badge ${tone}`}>{humanize(status)}</span>;
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
