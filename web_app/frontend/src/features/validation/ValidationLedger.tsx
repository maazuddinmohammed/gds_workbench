import type { ModelReviewSelection } from "../model_record_review/selection";
import { useEffect, useRef } from "react";
import { Link } from "@tanstack/react-router";

import { ApiError } from "../../core/http";
import type { ValidationValidationCheck, ValidationValidationGroup } from "./api";

export function ValidationLedger({
  tenantId, modelId, groupId, checkId, selection, groups,
  modelRevision, loadedModelRevision, isLoading, error,
}: {
  tenantId: number;
  modelId: number;
  groupId?: number | undefined;
  checkId?: number | undefined;
  selection?: ModelReviewSelection & { dataset: "validation_group" | "validation_check" };
  groups: ValidationValidationGroup[];
  modelRevision: number;
  loadedModelRevision: number | undefined;
  isLoading: boolean;
  error: Error | null;
}) {
  const heading = useRef<HTMLHeadingElement>(null);
  const group = groups.find((item) => item.validation_group_id === groupId);
  const check = group?.checks.find((item) => item.validation_check_id === checkId);
  const revisionMismatch = loadedModelRevision !== undefined && loadedModelRevision !== modelRevision;
  const ready = !isLoading && !error && !revisionMismatch;
  useEffect(() => {
    if (ready) heading.current?.focus();
  }, [ready, groupId, checkId]);
  const params = { tenantId: String(tenantId), modelId: String(modelId) };
  const title = checkId !== undefined ? check?.validation_check_name ?? "Validation Check"
    : groupId !== undefined ? group?.validation_group_name ?? "Validation Group" : "Validation Groups";
  const select = (id: number, checked: boolean) => {
    if (!selection) return;
    const ids = new Set(selection.selectedIds);
    if (checked) ids.add(id); else ids.delete(id);
    selection.onSelectionChange(ids);
  };

  return (
    <section className="workflow-surface validation-surface" aria-labelledby="validation-ledger-heading">
      <header className="validation-ledger-heading">
        <div>
          <p className="eyebrow">{checkId !== undefined ? "Applied check definition" : "Applied check definitions"}</p>
          <h2 id="validation-ledger-heading" ref={heading} tabIndex={-1}>{title}</h2>
        </div>
        {ready ? <span>{group ? `${group.system_code} · ${group.checks.length} Checks`
          : `${groups.length} Groups · ${groups.reduce((total, item) => total + item.checks.length, 0)} Checks`}</span> : null}
      </header>
      <p className="detail-empty-note">Authored checks · execution results are not recorded here.</p>
      {isLoading ? (
        <div className="surface-state" aria-busy="true">Loading applied Validation definitions…</div>
      ) : error instanceof ApiError && error.status === 403 ? (
        <div className="surface-state is-error" role="alert">You do not have permission to view applied Validation definitions.</div>
      ) : error ? (
        <div className="surface-state is-error" role="alert">Applied Validation definitions could not be loaded. Refresh to try again.</div>
      ) : revisionMismatch ? (
        <div className="surface-state is-error" role="alert">The Model changed while the Validation ledger was loading. Refresh before authoring Validation.</div>
      ) : groupId !== undefined && !group ? (
        <div className="surface-state is-error" role="alert">This Validation Group is not available in this Model.</div>
      ) : checkId !== undefined && !check ? (
        <div className="surface-state is-error" role="alert">This Validation Check is not available in this Group.</div>
      ) : check ? (
        <>
          <p>{check.validation_check_description ?? "No description provided."}</p>
          <div className="validation-group-statuses">
            <StateBadge value={check.is_locked ? "Locked" : "Open"} tone="neutral" />
            <StateBadge value={check.is_active ? "Active" : "Inactive"} tone={check.is_active ? "success" : "neutral"} />
            <SeverityBadge severity={check.validation_severity} />
            <code>{check.validation_category_code}</code>
          </div>
          <CheckDetail check={check} />
        </>
      ) : group ? (
        <>
          <p>{group.validation_group_description ?? "No description provided."}</p>
          <GroupStatus group={group} />
          {group.checks.length === 0 ? <div className="empty-state compact">This Validation Group has no Checks.</div> : (
            <div className="table-scroll validation-check-table-scroll">
              <table aria-label={`${group.validation_group_name} Validation Checks`}>
                <thead><tr>
                  {selection ? <th>Select</th> : null}
                  <th>Validation Check</th><th>Category</th><th>Severity</th><th>Assertion</th><th>Status</th><th>Details</th>
                </tr></thead>
                <tbody>{group.checks.map((item) => (
                  <tr key={item.validation_check_id}>
                    {selection ? <td><input type="checkbox" aria-label={`Select Validation Check ${item.validation_check_id}`}
                      checked={selection.selectedIds.has(item.validation_check_id)}
                      onChange={(event) => select(item.validation_check_id, event.target.checked)} /></td> : null}
                    <td><span className="validation-check-name"><strong>{item.validation_check_name}</strong>
                      <span>{item.validation_check_description ?? "No description provided"}</span></span></td>
                    <td><code>{item.validation_category_code}</code></td>
                    <td><SeverityBadge severity={item.validation_severity} /></td>
                    <td>{assertionLabel(item)}</td>
                    <td><StateBadge value={item.is_locked ? "Locked" : "Open"} tone="neutral" />
                      <StateBadge value={item.is_active ? "Active" : "Inactive"} tone={item.is_active ? "success" : "neutral"} /></td>
                    <td><Link className="text-action"
                      to="/tenants/$tenantId/validation/models/$modelId/groups/$groupId/checks/$checkId"
                      params={{ ...params, groupId: String(group.validation_group_id), checkId: String(item.validation_check_id) }}
                      aria-label={`Show details for ${item.validation_check_name}`}>Show details</Link></td>
                  </tr>
                ))}</tbody>
              </table>
            </div>
          )}
        </>
      ) : groups.length === 0 ? (
        <div className="empty-state compact">No Validation Groups are applied to this Model. Run Validation to author the first draft.</div>
      ) : (
        <div className="table-scroll validation-check-table-scroll">
          <table aria-label="Validation Groups">
            <thead><tr>{selection ? <th>Select</th> : null}<th>Group</th><th>System</th><th>Checks</th><th>Status</th><th>Details</th></tr></thead>
            <tbody>{groups.map((item) => (
              <tr key={item.validation_group_id}>
                {selection ? <td><input type="checkbox" aria-label={`Select Validation Group ${item.validation_group_id}`}
                  checked={selection.selectedIds.has(item.validation_group_id)}
                  onChange={(event) => select(item.validation_group_id, event.target.checked)} /></td> : null}
                <td><span className="validation-check-name"><strong>{item.validation_group_name}</strong>
                  <span>{item.validation_group_description ?? "No description provided."}</span></span></td>
                <td>{item.system_code}</td><td>{item.checks.length}</td>
                <td><GroupStatus group={item} /></td>
                <td><Link className="text-action"
                  to="/tenants/$tenantId/validation/models/$modelId/groups/$groupId"
                  params={{ ...params, groupId: String(item.validation_group_id) }}
                  aria-label={`Show details for ${item.validation_group_name}`}>Show details</Link></td>
              </tr>
            ))}</tbody>
          </table>
        </div>
      )}
    </section>
  );
}

function GroupStatus({ group }: { group: ValidationValidationGroup }) {
  return <div className="validation-group-statuses" aria-label={`${group.validation_group_name} status`}>
    <StateBadge value={group.is_locked ? "Locked" : "Open"} tone="neutral" />
    <StateBadge value={group.is_active ? "Active" : "Inactive"} tone={group.is_active ? "success" : "neutral"} />
    <StateBadge value={group.validation_group_is_current ? "Definition current" : "Definition stale"}
      tone={group.validation_group_is_current ? "success" : "stale"} />
    <StateBadge value={group.mapping_context_is_current ? "Mapping current" : "Mapping stale"}
      tone={group.mapping_context_is_current ? "success" : "stale"} />
    <StateBadge {...codeContextBadge(group)} />
  </div>;
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
    <section className="validation-check-detail" id={`validation-check-${check.validation_check_id}-detail`}
      aria-label={`${check.validation_check_name} details`}
    >
      <p className="validation-assertion-summary"><strong>Expected:</strong> Query A {assertionLabel(check)}</p>

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
      <details className="support-record-details"><summary>Comparison details</summary>
      <dl className="validation-check-facts">
        <div><dt>Operator</dt><dd><code>{check.validation_comparison_operator}</code></dd></div>
        <div><dt>Query result type</dt><dd>{check.validation_result_data_type ?? "Not recorded"}</dd></div>
        <div><dt>Operand type</dt><dd><code>{check.validation_comparison_value_type}</code></dd></div>
        {check.validation_comparison_value_type === "literal" || check.validation_comparison_value_type === "literal_list" ? (
          <div><dt>Comparison value</dt><dd><code>{comparisonValue(check.validation_comparison_value)}</code></dd></div>
        ) : null}
      </dl>
      </details>

    </section>
  );
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
  if (value === undefined) return "Not recorded";
  if (typeof value === "string") return value === "" ? '""' : value;
  return JSON.stringify(value);
}

function humanize(value: string): string {
  return value.replaceAll("_", " ").replace(/^./, (character) => character.toLocaleUpperCase());
}
