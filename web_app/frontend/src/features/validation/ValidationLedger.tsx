import { useState } from "react";

import { ApiError } from "../../core/http";
import type { ValidationValidationCheck, ValidationValidationGroup } from "./api";

export function ValidationLedger({
  groups,
  modelRevision,
  loadedModelRevision,
  isLoading,
  error,
}: {
  groups: ValidationValidationGroup[];
  modelRevision: number;
  loadedModelRevision: number | undefined;
  isLoading: boolean;
  error: Error | null;
}) {
  const [expandedGroupIds, setExpandedGroupIds] = useState<Set<number>>(() => new Set());
  const [selectedCheckId, setSelectedCheckId] = useState<number | null>(null);
  const checkCount = groups.reduce((total, group) => total + group.checks.length, 0);
  const revisionMismatch = loadedModelRevision !== undefined
    && loadedModelRevision !== modelRevision;

  return (
    <section className="workflow-surface validation-surface" aria-labelledby="validation-ledger-heading">
      <header className="validation-ledger-heading">
        <div>
          <p className="eyebrow">Applied Validation ledger</p>
          <h2 id="validation-ledger-heading">Validation Groups and Checks</h2>
        </div>
        <span>{groups.length} Groups · {checkCount} Checks</span>
      </header>
      {isLoading ? (
        <div className="surface-state" aria-busy="true">Loading applied Validation definitions…</div>
      ) : error instanceof ApiError && error.status === 403 ? (
        <div className="surface-state is-error" role="alert">
          You do not have permission to view applied Validation definitions.
        </div>
      ) : error ? (
        <div className="surface-state is-error" role="alert">
          Applied Validation definitions could not be loaded. Refresh to try again.
        </div>
      ) : revisionMismatch ? (
        <div className="surface-state is-error" role="alert">
          The Model changed while the Validation ledger was loading. Refresh before authoring Validation.
        </div>
      ) : groups.length === 0 ? (
        <div className="empty-state compact">
          No Validation Groups are applied to this Model. Run Validation to author the first draft.
        </div>
      ) : (
        <div className="validation-group-ledger">
          {groups.map((group) => {
            const expanded = expandedGroupIds.has(group.validation_group_id);
            const panelId = `validation-group-${group.validation_group_id}-checks`;
            return (
              <article className="validation-group" key={group.validation_group_id}>
                <header className="validation-group-summary">
                  <button
                    type="button"
                    aria-expanded={expanded}
                    aria-controls={panelId}
                    onClick={() => {
                      setExpandedGroupIds((current) => {
                        const next = new Set(current);
                        if (expanded) next.delete(group.validation_group_id);
                        else next.add(group.validation_group_id);
                        return next;
                      });
                    }}
                  >
                    <span aria-hidden="true">{expanded ? "−" : "+"}</span>
                    <span>
                      <strong>{group.validation_group_name}</strong>
                      <small>{group.system_code} · {group.checks.length} Check{group.checks.length === 1 ? "" : "s"}</small>
                    </span>
                  </button>
                  <div className="validation-group-statuses" aria-label={`${group.validation_group_name} status`}>
                    <StateBadge value={group.is_active ? "Active" : "Inactive"} tone={group.is_active ? "success" : "neutral"} />
                    <StateBadge value={group.validation_group_is_current ? "Current" : "Stale"} tone={group.validation_group_is_current ? "success" : "stale"} />
                    <StateBadge
                      value={group.mapping_context_is_current
                        ? "Mapping current"
                        : "Mapping stale"}
                      tone={group.mapping_context_is_current ? "success" : "stale"}
                    />
                    <StateBadge {...codeContextBadge(group)} />
                  </div>
                </header>
                <div className="validation-group-description">
                  <p>{group.validation_group_description ?? "No description provided."}</p>
                </div>
                {expanded ? (
                  <div id={panelId} className="validation-check-panel">
                    {group.checks.length === 0 ? (
                      <div className="empty-state compact">This Validation Group has no Checks.</div>
                    ) : (
                      <div className="table-scroll validation-check-table-scroll">
                        <table aria-label={`${group.validation_group_name} Validation Checks`}>
                          <thead>
                            <tr>
                              <th>Validation Check</th>
                              <th>Category</th>
                              <th>Severity</th>
                              <th>Assertion</th>
                              <th>Status</th>
                              <th>Review</th>
                            </tr>
                          </thead>
                          <tbody>
                            {group.checks.map((check) => (
                              <tr key={check.validation_check_id}>
                                <td>
                                  <span className="validation-check-name">
                                    <strong>{check.validation_check_name}</strong>
                                    <span>{check.validation_check_description ?? "No description provided"}</span>
                                  </span>
                                </td>
                                <td><code>{check.validation_category_code}</code></td>
                                <td><SeverityBadge severity={check.validation_severity} /></td>
                                <td>{assertionLabel(check)}</td>
                                <td><StateBadge value={check.is_active ? "Active" : "Inactive"} tone={check.is_active ? "success" : "neutral"} /></td>
                                <td>
                                  <button
                                    className="generation-text-action"
                                    type="button"
                                    aria-expanded={selectedCheckId === check.validation_check_id}
                                    onClick={() => setSelectedCheckId((current) => (
                                      current === check.validation_check_id
                                        ? null
                                        : check.validation_check_id
                                    ))}
                                  >
                                    {selectedCheckId === check.validation_check_id ? "Hide details" : "Show details"}
                                  </button>
                                </td>
                              </tr>
                            ))}
                          </tbody>
                        </table>
                      </div>
                    )}
                    {selectedCheck(group.checks, selectedCheckId) ? (
                      <CheckDetail check={selectedCheck(group.checks, selectedCheckId)!} />
                    ) : null}
                  </div>
                ) : null}
              </article>
            );
          })}
        </div>
      )}
    </section>
  );
}

function StateBadge({ value, tone }: { value: string; tone: "success" | "neutral" | "stale" }) {
  return <span className={`status-badge is-${tone}`}>{value}</span>;
}

function SeverityBadge({ severity }: { severity: ValidationValidationCheck["validation_severity"] }) {
  const tone = severity === "blocking" ? "danger" : severity === "warning" ? "warning" : "neutral";
  return <span className={`status-badge is-${tone}`}>{humanize(severity)}</span>;
}

function codeContextBadge(group: ValidationValidationGroup): {
  value: string;
  tone: "success" | "neutral" | "stale";
} {
  return group.code_context_is_current
    ? { value: "Code current", tone: "success" }
    : { value: "Code stale", tone: "stale" };
}

function CheckDetail({ check }: { check: ValidationValidationCheck }) {
  return (
    <section className="validation-check-detail" aria-label={`${check.validation_check_name} details`}>
      <header>
        <div>
          <small>Deterministic assertion</small>
          <h4>{check.validation_check_name}</h4>
        </div>
        <span>{assertionLabel(check)}</span>
      </header>
      <div className="validation-query-grid">
        <div>
          <strong>Query A</strong>
          <pre tabIndex={0}><code>{check.validation_query_sql}</code></pre>
        </div>
        {check.validation_comparison_query_sql ? (
          <div>
            <strong>Query B</strong>
            <pre tabIndex={0}><code>{check.validation_comparison_query_sql}</code></pre>
          </div>
        ) : null}
      </div>
      <dl className="validation-check-facts">
        <div><dt>Result type</dt><dd>{check.validation_result_data_type ?? "Not applicable"}</dd></div>
        <div><dt>Operand type</dt><dd>{humanize(check.validation_comparison_value_type)}</dd></div>
        <div><dt>Comparison value</dt><dd><code>{comparisonValue(check.validation_comparison_value)}</code></dd></div>
      </dl>
    </section>
  );
}

function selectedCheck(checks: ValidationValidationCheck[], checkId: number | null) {
  return checks.find((check) => check.validation_check_id === checkId);
}

function assertionLabel(check: ValidationValidationCheck): string {
  const operator = humanize(check.validation_comparison_operator);
  if (check.validation_comparison_value_type === "query") return `${operator} Query B`;
  if (check.validation_comparison_value_type === "literal") {
    return `${operator} ${comparisonValue(check.validation_comparison_value)}`;
  }
  if (check.validation_comparison_value_type === "literal_list") {
    return `${operator} ${comparisonValue(check.validation_comparison_value)}`;
  }
  return operator;
}

function comparisonValue(value: unknown): string {
  if (value === null || value === undefined) return "Not applicable";
  if (typeof value === "string") return value;
  return JSON.stringify(value);
}

function humanize(value: string): string {
  return value.replaceAll("_", " ").replace(/^./, (character) => character.toLocaleUpperCase());
}
