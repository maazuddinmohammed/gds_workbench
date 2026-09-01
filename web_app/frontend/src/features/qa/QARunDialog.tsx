import { useEffect, useMemo, useRef, useState } from "react";
import { createPortal } from "react-dom";
import { useMutation, useQuery } from "@tanstack/react-query";

import { ApiError } from "../../core/http";
import type { ModelDetail } from "../models/api";
import {
  resolveDefaultAgent,
  workflowCreationQueryKeys,
  type CreateWorkflowRunCommand,
} from "../workflows/api";
import {
  isTenantWorkflowConflict,
  TENANT_WORKFLOW_CONFLICT_MESSAGE,
} from "../workflows/presentation";
import type { QAApi, QAEligibleSystem } from "./api";

const QA_AGENT_EXECUTION_MODE = "detailed_coverage" as const;

type QARunSubmission =
  | { kind: "create"; command: CreateWorkflowRunCommand }
  | { kind: "retry"; workflowRunId: number };

export function QARunDialog({
  api,
  tenantId,
  model,
  systems,
  systemsTruncated,
  onClose,
  onStarted,
}: {
  api: QAApi;
  tenantId: number;
  model: ModelDetail;
  systems: QAEligibleSystem[];
  systemsTruncated: boolean;
  onClose: () => void;
  onStarted: (workflowRunId: number) => Promise<void>;
}) {
  const closeButton = useRef<HTMLButtonElement>(null);
  const dialog = useRef<HTMLElement>(null);
  const returnFocus = useRef<HTMLElement | null>(
    document.activeElement instanceof HTMLElement ? document.activeElement : null,
  );
  const portalHost = useRef<HTMLDivElement | null>(null);
  if (portalHost.current === null) {
    portalHost.current = document.createElement("div");
    portalHost.current.dataset.qaModalHost = "true";
  }
  const [selectedSystemIds, setSelectedSystemIds] = useState<Set<number>>(() => new Set());
  const [pendingWorkflowRunId, setPendingWorkflowRunId] = useState<number | null>(null);
  const capabilitiesQuery = useQuery({
    queryKey: workflowCreationQueryKeys.capabilities,
    queryFn: api.readAgentCapabilities,
  });
  const agent = useMemo(() => capabilitiesQuery.data ? resolveDefaultAgent(
    capabilitiesQuery.data,
    QA_AGENT_EXECUTION_MODE,
    {
      sdkCode: model.default_agent_sdk_code,
      providerCode: model.default_agent_provider_code,
      modelCode: model.default_agent_model_code,
      reasoningEffortCode: model.default_reasoning_effort_code,
      maxTurns: model.default_max_turns,
      validationRetryCount: model.default_validation_retry_count,
    },
  ) : null, [capabilitiesQuery.data, model]);
  const selectedSystems = systems.filter((system) => selectedSystemIds.has(system.system_id));
  const selectedCodes = validateSelectedSystemCodes(
    selectedSystems.map((system) => system.system_code),
  );
  const allSelected = systems.length > 0 && selectedSystemIds.size === systems.length;
  const runMutation = useMutation({
    mutationFn: async (submission: QARunSubmission) => {
      if (submission.kind === "retry") {
        await api.executeQARun(
          tenantId,
          model.model_id,
          submission.workflowRunId,
          model.model_revision,
        );
        return submission.workflowRunId;
      }
      const result = await api.createWorkflowRun(
        tenantId,
        model.model_id,
        submission.command,
        globalThis.crypto.randomUUID(),
      );
      setPendingWorkflowRunId(result.workflow_run_id);
      await api.executeQARun(
        tenantId,
        model.model_id,
        result.workflow_run_id,
        model.model_revision,
      );
      return result.workflow_run_id;
    },
    onSuccess: async (workflowRunId) => {
      await onStarted(workflowRunId);
      onClose();
    },
  });

  useEffect(() => {
    const host = portalHost.current;
    if (!host) return;
    document.body.append(host);
    const appRoot = document.getElementById("root");
    const rootWasInert = appRoot?.hasAttribute("inert") ?? false;
    const previousAriaHidden = appRoot?.getAttribute("aria-hidden") ?? null;
    appRoot?.setAttribute("inert", "");
    appRoot?.setAttribute("aria-hidden", "true");
    closeButton.current?.focus();
    return () => {
      if (appRoot) {
        if (!rootWasInert) appRoot.removeAttribute("inert");
        if (previousAriaHidden === null) appRoot.removeAttribute("aria-hidden");
        else appRoot.setAttribute("aria-hidden", previousAriaHidden);
      }
      host.remove();
      globalThis.queueMicrotask(() => returnFocus.current?.focus());
    };
  }, []);

  const modal = (
    <div className="dialog-scrim qa-dialog-scrim" role="presentation">
      <section
        ref={dialog}
        className="run-configuration-dialog qa-run-dialog"
        role="dialog"
        aria-modal="true"
        aria-labelledby="qa-run-heading"
        onKeyDown={(event) => {
          if (event.key === "Escape") {
            if (!runMutation.isPending) onClose();
            return;
          }
          if (event.key !== "Tab") return;
          const focusable = [...(dialog.current?.querySelectorAll<HTMLElement>(
            "button:not([disabled]), [href], input:not([disabled]), select:not([disabled]), "
            + "textarea:not([disabled]), [tabindex]:not([tabindex='-1'])",
          ) ?? [])];
          if (focusable.length === 0) {
            event.preventDefault();
            return;
          }
          const first = focusable[0];
          const last = focusable.at(-1);
          if (event.shiftKey && (
            document.activeElement === first || !dialog.current?.contains(document.activeElement)
          )) {
            event.preventDefault();
            last?.focus();
          } else if (!event.shiftKey && (
            document.activeElement === last || !dialog.current?.contains(document.activeElement)
          )) {
            event.preventDefault();
            first?.focus();
          }
        }}
      >
        <header className="drawer-header">
          <div>
            <small>QA authoring</small>
            <h2 id="qa-run-heading">Configure QA run</h2>
          </div>
          <button
            ref={closeButton}
            className="panel-close"
            type="button"
            aria-label="Close Configure QA run"
            disabled={runMutation.isPending}
            onClick={onClose}
          >
            <span aria-hidden="true">×</span>
          </button>
        </header>
        <form
          onSubmit={(event) => {
            event.preventDefault();
            if (pendingWorkflowRunId !== null) {
              runMutation.mutate({ kind: "retry", workflowRunId: pendingWorkflowRunId });
              return;
            }
            if (!agent || !selectedCodes) return;
            runMutation.mutate({
              kind: "create",
              command: {
                expected_model_revision: model.model_revision,
                model_workflow: "qa",
                workflow_execution_mode: null,
                selected_object_ids: [],
                selected_system_codes: selectedCodes,
                modeled_entity_type: null,
                requested_batch_id: null,
                agent,
                prompt_overrides: {},
              },
            });
          }}
        >
          <section className="qa-run-systems" aria-labelledby="qa-system-selection-heading">
            <header>
              <div>
                <strong id="qa-system-selection-heading">Systems</strong>
                <span>Select one or more exact System codes. Selection is frozen when the run is created.</span>
              </div>
              <div>
                <button
                  className="text-action"
                  type="button"
                  disabled={runMutation.isPending || allSelected}
                  onClick={() => setSelectedSystemIds(new Set(systems.map((system) => system.system_id)))}
                >
                  Select all
                </button>
                <button
                  className="text-action"
                  type="button"
                  disabled={runMutation.isPending || selectedSystemIds.size === 0}
                  onClick={() => setSelectedSystemIds(new Set())}
                >
                  Clear
                </button>
              </div>
            </header>
            <fieldset disabled={runMutation.isPending}>
              <legend className="sr-only">Eligible QA Systems</legend>
              <ul className="qa-system-selection-list">
                {systems.map((system) => (
                  <li key={system.system_id}>
                    <label>
                      <input
                        type="checkbox"
                        checked={selectedSystemIds.has(system.system_id)}
                        onChange={(event) => {
                          setSelectedSystemIds((current) => {
                            const next = new Set(current);
                            if (event.target.checked) next.add(system.system_id);
                            else next.delete(system.system_id);
                            return next;
                          });
                        }}
                      />
                      <span>
                        <strong>{system.system_name}</strong>
                        <code>{system.system_code}</code>
                      </span>
                      <small>
                        {system.mapping_target_count} Mapping targets · {system.current_code_target_count} current Code targets
                      </small>
                      <span className={`status-badge ${system.has_applied_qa ? "is-success" : "is-neutral"}`}>
                        {system.has_applied_qa ? "Applied QA" : "No applied QA"}
                      </span>
                    </label>
                  </li>
                ))}
              </ul>
            </fieldset>
            <p className="qa-selection-summary" role="status">
              {selectedSystemIds.size} of {systems.length} Systems selected
            </p>
            {systemsTruncated ? (
              <p className="inline-error" role="alert">
                The eligible System register is truncated. Only the displayed Systems can be selected.
              </p>
            ) : null}
            {selectedSystemIds.size > 0 && !selectedCodes ? (
              <p className="inline-error" role="alert">
                Selected System codes must be nonempty and unique without regard to case.
              </p>
            ) : null}
          </section>

          <section className="agent-run-configuration qa-agent-profile" aria-labelledby="qa-agent-profile-heading">
            <header>
              <strong id="qa-agent-profile-heading">Internal agent profile</strong>
              <span>QA uses the fixed Detailed coverage profile and the Model's compatible agent defaults.</span>
            </header>
            {capabilitiesQuery.isPending ? (
              <div className="surface-state compact" aria-busy="true">Loading internal agent profile…</div>
            ) : capabilitiesQuery.isError || !agent ? (
              <p className="inline-error" role="alert">A compatible Detailed coverage agent profile is unavailable.</p>
            ) : (
              <dl className="detail-fact-grid">
                <Fact label="Profile" value="Detailed coverage · fixed" />
                <Fact label="Agent SDK" value={agent.sdk_code} />
                <Fact label="Provider" value={agent.provider_code} />
                <Fact label="Model" value={agent.model_code} />
                <Fact label="Reasoning" value={agent.reasoning_effort_code} />
                <Fact label="Limits" value={`${agent.max_turns} turns · ${agent.validation_retry_count} validation retries`} />
              </dl>
            )}
          </section>

          {runMutation.isError ? (
            <p className="inline-error" role="alert">
              {qaRunError(runMutation.error, pendingWorkflowRunId !== null)}
            </p>
          ) : null}
          <footer className="dialog-actions">
            <p>
              The backend rechecks role, Tenant Lock, revision, exact System coverage, and agent compatibility.
            </p>
            <div>
              <button
                className="button button-secondary button-small"
                type="button"
                disabled={runMutation.isPending}
                onClick={onClose}
              >
                Cancel
              </button>
              <button
                className="button button-primary button-small"
                type="submit"
                disabled={runMutation.isPending || (
                  pendingWorkflowRunId === null
                  && (!selectedCodes || !agent || capabilitiesQuery.isPending)
                )}
              >
                {runMutation.isPending
                  ? pendingWorkflowRunId === null ? "Creating and starting…" : "Starting…"
                  : pendingWorkflowRunId === null ? "Create and start QA" : "Retry start"}
              </button>
            </div>
          </footer>
        </form>
      </section>
    </div>
  );
  return createPortal(modal, portalHost.current);
}

export function validateSelectedSystemCodes(codes: string[]): string[] | null {
  const normalized = codes.map((code) => code.trim());
  if (!normalized.length || normalized.some((code) => !code)) return null;
  const folded = normalized.map((code) => code.toLocaleLowerCase("en-US"));
  return new Set(folded).size === folded.length ? normalized : null;
}

function Fact({ label, value }: { label: string; value: string }) {
  return <div><dt>{label}</dt><dd>{value}</dd></div>;
}

function qaRunError(error: Error, runWasCreated: boolean): string {
  if (runWasCreated && isTenantWorkflowConflict(error)) return TENANT_WORKFLOW_CONFLICT_MESSAGE;
  if (runWasCreated) return "The QA run remains queued because it could not be started.";
  if (error instanceof ApiError && error.status === 403) {
    return "You no longer have permission or the required Tenant Lock to run QA.";
  }
  if (error instanceof ApiError && error.status === 409) {
    return "The Model or QA context changed. Refresh before creating another run.";
  }
  return "The QA run could not be created or started.";
}
