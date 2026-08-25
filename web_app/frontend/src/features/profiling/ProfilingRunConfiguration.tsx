import { useEffect, useRef } from "react";
import { useForm, useStore } from "@tanstack/react-form";
import { useMutation, useQuery } from "@tanstack/react-query";

import type { ModelDetail } from "../models/api";
import type { ModelScopeObject } from "../model_scope/api";
import { profilingQueryKeys, type ProfilingApi } from "./api";
import { DrawerHeader } from "./shared";

export function ProfilingRunConfiguration({
  api,
  tenantId,
  model,
  onClose,
  onCreated,
}: {
  api: ProfilingApi;
  tenantId: number;
  model: ModelDetail;
  onClose: () => void;
  onCreated: (workflowRunId: number) => Promise<void>;
}) {
  const closeButton = useRef<HTMLButtonElement>(null);
  const scopeQuery = useQuery({
    queryKey: profilingQueryKeys.scope(tenantId, model.model_id),
    queryFn: () => loadAllBronzeScope(api, tenantId, model.model_id),
  });
  const createMutation = useMutation({
    mutationFn: ({
      objectIds,
      requestedBatchId,
    }: {
      objectIds: number[];
      requestedBatchId: string | null;
    }) => api.createProfilingRun(
      tenantId,
      model.model_id,
      {
        expected_model_revision: model.model_revision,
        model_workflow: "profiling",
        selected_object_ids: objectIds,
        requested_batch_id: requestedBatchId,
      },
      globalThis.crypto.randomUUID(),
    ),
    onSuccess: async (result) => onCreated(result.workflow_run_id),
  });
  const form = useForm({
    defaultValues: {
      scopeMode: "all" as "all" | "selected",
      selectedObjectIds: [] as number[],
      requestedBatchId: "",
    },
    onSubmit: ({ value }) => {
      const objectIds = value.scopeMode === "all"
        ? (scopeQuery.data?.items.map((item) => item.object_id) ?? [])
        : value.selectedObjectIds;
      createMutation.mutate({
        objectIds,
        requestedBatchId: value.requestedBatchId.trim() || null,
      });
    },
  });
  const scopeMode = useStore(form.store, (state) => state.values.scopeMode);
  const selectedObjectIds = useStore(form.store, (state) => state.values.selectedObjectIds);
  const requestedBatchId = useStore(form.store, (state) => state.values.requestedBatchId);
  const effectiveObjects = scopeMode === "all"
    ? (scopeQuery.data?.items ?? [])
    : (scopeQuery.data?.items.filter((item) => selectedObjectIds.includes(item.object_id)) ?? []);
  const selectedSystemIds = new Set(effectiveObjects.map((item) => item.system_id));
  const batchIsIncoherent = Boolean(requestedBatchId.trim()) && selectedSystemIds.size > 1;
  const revisionChanged = scopeQuery.data && scopeQuery.data.modelRevision !== model.model_revision;

  useEffect(() => closeButton.current?.focus(), []);

  return (
    <div className="dialog-scrim" role="presentation">
      <section
        className="run-configuration-dialog"
        role="dialog"
        aria-modal="true"
        aria-labelledby="run-configuration-heading"
        onKeyDown={(event) => {
          if (event.key === "Escape") onClose();
        }}
      >
        <DrawerHeader
          eyebrow="Deterministic execution"
          title="Configure profiling run"
          titleId="run-configuration-heading"
          closeLabel="Close profiling run configuration"
          closeRef={closeButton}
          onClose={onClose}
        />
        <form
          onSubmit={(event) => {
            event.preventDefault();
            event.stopPropagation();
            void form.handleSubmit();
          }}
        >
          <fieldset className="scope-mode-options">
            <legend>Object coverage</legend>
            <form.Field name="scopeMode">
              {(field) => (
                <>
                  <label>
                    <input
                      type="radio"
                      name={field.name}
                      value="all"
                      checked={field.state.value === "all"}
                      onChange={() => field.handleChange("all")}
                    />
                    <span>
                      <strong>All Objects</strong>
                      <small>Every active Bronze Object in Scope</small>
                    </span>
                  </label>
                  <label>
                    <input
                      type="radio"
                      name={field.name}
                      value="selected"
                      checked={field.state.value === "selected"}
                      onChange={() => field.handleChange("selected")}
                    />
                    <span>
                      <strong>Selected Objects</strong>
                      <small>Choose an exact subset</small>
                    </span>
                  </label>
                </>
              )}
            </form.Field>
          </fieldset>

          <section className="run-object-selection" aria-labelledby="run-objects-heading">
            <header>
              <strong id="run-objects-heading">Active Bronze Scope</strong>
              <span>{effectiveObjects.length} selected</span>
            </header>
            {scopeQuery.isPending ? (
              <div className="surface-state compact" aria-busy="true">
                Loading active Scope…
              </div>
            ) : scopeQuery.isError ? (
              <div className="surface-state is-error compact" role="alert">
                Active Scope could not be loaded.
              </div>
            ) : (
              <form.Field name="selectedObjectIds">
                {(field) => (
                  <div className="run-object-list">
                    {scopeQuery.data.items.map((item) => {
                      const checked = scopeMode === "all"
                        || field.state.value.includes(item.object_id);
                      return (
                        <label key={item.object_id}>
                          <input
                            type="checkbox"
                            checked={checked}
                            disabled={scopeMode === "all"}
                            onChange={(event) => {
                              field.handleChange(event.target.checked
                                ? [...field.state.value, item.object_id]
                                : field.state.value.filter((id) => id !== item.object_id));
                            }}
                          />
                          <span>
                            <strong>{item.object_name}</strong>
                            <small>
                              {item.system_code} · {item.source_tenant_code} · {item.attribute_count} attributes
                            </small>
                          </span>
                        </label>
                      );
                    })}
                  </div>
                )}
              </form.Field>
            )}
          </section>

          <form.Field name="requestedBatchId">
            {(field) => (
              <label className="batch-input">
                <span>Batch ID (optional)</span>
                <input
                  aria-label="Batch ID (optional)"
                  value={field.state.value}
                  onBlur={field.handleBlur}
                  onChange={(event) => field.handleChange(event.target.value)}
                />
                <small>When supplied, every selected Object must belong to one System.</small>
              </label>
            )}
          </form.Field>
          {batchIsIncoherent ? (
            <p className="inline-error" role="alert">
              Select Objects from one System when using a Batch ID.
            </p>
          ) : null}
          {revisionChanged ? (
            <p className="inline-error" role="alert">
              The Model changed. Close this dialog and refresh before creating the run.
            </p>
          ) : null}
          {createMutation.isError ? (
            <p className="inline-error" role="alert">The queued run could not be created.</p>
          ) : null}
          <footer className="dialog-actions">
            <p>Creation is separate from execution. The backend revalidates Scope and Tenant Lock.</p>
            <div>
              <button
                className="button button-secondary button-small"
                type="button"
                onClick={onClose}
              >
                Cancel
              </button>
              <button
                className="button button-primary button-small"
                type="submit"
                disabled={
                  createMutation.isPending
                  || scopeQuery.isPending
                  || scopeQuery.isError
                  || effectiveObjects.length === 0
                  || batchIsIncoherent
                  || Boolean(revisionChanged)
                }
              >
                {createMutation.isPending ? "Creating…" : "Create queued run"}
              </button>
            </div>
          </footer>
        </form>
      </section>
    </div>
  );
}

async function loadAllBronzeScope(
  api: ProfilingApi,
  tenantId: number,
  modelId: number,
): Promise<{ modelRevision: number; items: ModelScopeObject[] }> {
  const items: ModelScopeObject[] = [];
  const seenCursors = new Set<string>();
  let cursor: string | undefined;
  let modelRevision: number | null = null;

  for (let page = 0; page < 250; page += 1) {
    const response = await api.listModelScope(
      tenantId,
      modelId,
      { zone: "bronze" },
      200,
      cursor,
    );
    if (modelRevision !== null && modelRevision !== response.model_revision) {
      throw new Error("Model Scope revision changed while loading");
    }
    modelRevision = response.model_revision;
    items.push(...response.items);
    if (!response.next_cursor) return { modelRevision, items };
    if (seenCursors.has(response.next_cursor)) {
      throw new Error("Model Scope cursor repeated");
    }
    seenCursors.add(response.next_cursor);
    cursor = response.next_cursor;
  }
  throw new Error("Active Bronze Scope exceeds the supported bounded selection");
}
