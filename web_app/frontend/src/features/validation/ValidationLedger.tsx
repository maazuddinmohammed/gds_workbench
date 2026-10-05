import type { ModelLayer } from "../../shared/ModelLayerTabs";
import type { ModelReviewSelection } from "../model_record_review/selection";
import { useEffect, useId, useRef } from "react";
import { Link } from "@tanstack/react-router";

import { ApiError } from "../../core/http";
import type { ValidationValidationCheck, ValidationValidationGroup } from "./api";

export function ValidationLedger({
  tenantId, modelId, groupId, checkId, selection, groups, layer, isFiltered = false,
  modelRevision, loadedModelRevision, isLoading, error, onShowDetails,
}: {
  layer?: ModelLayer;
  onShowDetails?: ((groupId: number, checkId?: number) => void) | undefined;
  isFiltered?: boolean;
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
  const headingId = useId();
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
  const checkCount = group?.checks.length ?? groups.reduce((total, item) => total + item.checks.length, 0);
  const select = (id: number, checked: boolean) => {
    if (!selection) return;
    const ids = new Set(selection.selectedIds);
    if (checked) ids.add(id); else ids.delete(id);
    selection.onSelectionChange(ids);
  };

  return (
    <section className="workflow-surface validation-surface" aria-labelledby={headingId}>
      <header className="validation-ledger-heading">
        <div>
          <h2 id={headingId} ref={heading} tabIndex={-1}>{title}</h2>
        </div>
        {ready && !check ? <span>{group ? "" : `${groups.length} ${groups.length === 1 ? "Group" : "Groups"} · `}
          {checkCount} {checkCount === 1 ? "Check" : "Checks"}</span> : null}
      </header>
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
      ) : check && group ? (
        <CheckDetail check={check} group={group} />
      ) : group ? (
        <>
          {group.validation_group_description ? <p className="validation-description" aria-label="Group description">{group.validation_group_description}</p> : null}
          {group.checks.length === 0 ? <div className="empty-state compact">This Validation Group has no Checks.</div> : (
            <div className="table-scroll validation-check-table-scroll validation-check-grid ledger-grid" role="region" aria-label="Validation table" tabIndex={0}>
              <table aria-label={`${group.validation_group_name} Validation Checks`}>
                <thead><tr>
                  {selection ? <th className="validation-selection-column">Select</th> : null}
                  <th className="validation-name-column">Check</th><th className="validation-description-column">Description</th><th className="validation-category-column">Category</th><th className="validation-state-column">Severity</th><th className="validation-assertion-column">Assertion</th><th className="validation-state-column">Status</th><th className="validation-state-column">Lock</th><th>Actions</th>
                </tr></thead>
                <tbody>{group.checks.map((item) => (
                  <tr key={item.validation_check_id}>
                    {selection ? <td className="validation-selection-column"><input type="checkbox" aria-label={`Select Validation Check ${item.validation_check_id}`}
                      checked={selection.selectedIds.has(item.validation_check_id)}
                      onChange={(event) => select(item.validation_check_id, event.target.checked)} /></td> : null}
                    <td>{item.validation_check_name}</td>
                    <td className="validation-description-column">{item.validation_check_description ?? "—"}</td>
                    <td>{humanize(item.validation_category_code)}</td>
                    <td><SeverityBadge severity={item.validation_severity} /></td>
                    <td className="validation-assertion-column">{assertionLabel(item)}</td>
                    <td>{item.is_active ? "Active" : "Inactive"}</td>
                    <td>{group.is_locked ? "Group locked" : item.is_locked ? "Locked" : "Open"}</td>
                    <td>{onShowDetails ? <button className="text-action" type="button"
                      aria-label={`Show details for ${item.validation_check_name}`}
                      onClick={() => onShowDetails(group.validation_group_id, item.validation_check_id)}>Show details</button> : <Link search={{ layer: layer ?? "logical" }} className="text-action"
                      to="/tenants/$tenantId/validation/models/$modelId/groups/$groupId/checks/$checkId"
                      params={{ ...params, groupId: String(group.validation_group_id), checkId: String(item.validation_check_id) }}
                      aria-label={`Show details for ${item.validation_check_name}`}>Show details</Link>}</td>
                  </tr>
                ))}</tbody>
              </table>
            </div>
          )}
          <GroupStatus group={group} />
        </>
      ) : groups.length === 0 ? (
        <div className="empty-state compact">{isFiltered ? "No Validation Groups match these filters." : "No Validation Groups are applied to this Model. Run Validation to author the first draft."}</div>
      ) : (
        <div className="table-scroll validation-check-table-scroll validation-group-grid ledger-grid" role="region" aria-label="Validation table" tabIndex={0}>
          <table aria-label="Validation Groups">
            <thead><tr>{selection ? <th className="validation-selection-column">Select</th> : null}<th className="validation-system-column">System</th><th className="validation-name-column">Group</th><th className="validation-description-column">Group description</th><th className="validation-count-column">Checks</th><th className="validation-state-column">Definition</th><th className="validation-state-column">Status</th><th className="validation-state-column">Lock</th><th>Actions</th></tr></thead>
            <tbody>{groups.map((item) => (
              <tr key={item.validation_group_id}>
                {selection ? <td className="validation-selection-column"><input type="checkbox" aria-label={`Select Validation Group ${item.validation_group_id}`}
                  checked={selection.selectedIds.has(item.validation_group_id)}
                  onChange={(event) => select(item.validation_group_id, event.target.checked)} /></td> : null}
                <td>{item.system_code}</td><td>{item.validation_group_name}</td>
                <td className="validation-description-column">{item.validation_group_description ?? "—"}</td><td>{item.checks.length}</td>
                <td>{item.validation_group_is_current ? "Current" : "Stale"}</td>
                <td>{item.is_active ? "Active" : "Inactive"}</td><td>{item.is_locked ? "Locked" : "Open"}</td>
                <td><Link search={{ layer: layer ?? "logical" }} className="text-action"
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
  return <details className="validation-context-details">
    <summary>Group details</summary>
    <dl className="validation-context-facts" aria-label={`${group.validation_group_name} status`}>
      <div><dt>System</dt><dd>{group.system_code}</dd></div>
      <div><dt>Definition</dt><dd>{group.validation_group_is_current ? "Current" : "Stale"}</dd></div>
      <div><dt>Mapping</dt><dd>{group.mapping_context_is_current ? "Current" : "Stale"}</dd></div>
      <div><dt>Code</dt><dd>{group.code_context_is_current ? "Current" : "Stale"}</dd></div>
      <div><dt>Availability</dt><dd>{group.is_active ? "Active" : "Inactive"}</dd></div>
      <div><dt>Lock</dt><dd>{group.is_locked ? "Locked" : "Open"}</dd></div>
    </dl>
  </details>;
}

function SeverityBadge({ severity }: { severity: ValidationValidationCheck["validation_severity"] }) {
  const tone = severity === "blocking" ? "danger" : severity === "warning" ? "warning" : "neutral";
  return <span className={`status-badge is-${tone}`}>{humanize(severity)}</span>;
}

function CheckDetail({ check, group }: { check: ValidationValidationCheck; group: ValidationValidationGroup }) {
  const executionOnly = check.validation_comparison_operator === "executes_successfully";
  return (
    <section className="validation-check-detail" id={`validation-check-${check.validation_check_id}-detail`}
      aria-label={`${check.validation_check_name} details`}>
      <section className="validation-purpose" aria-label="Check purpose">
        {check.validation_check_description ? <p>{check.validation_check_description}</p> : null}
      </section>
      <dl className="validation-criteria" aria-label="Pass and fail criteria">
        <div><dt>Pass when</dt><dd>{assertionLabel(check)}.</dd></div>
        <div><dt>Fail when</dt><dd>{executionOnly
          ? "Query A produces an execution error."
          : `${assertionLabel(check, true)}.`}</dd></div>
        <div><dt>Expected result</dt><dd>{executionOnly ? "Successful execution; returned values are ignored."
          : `One row and one column (${check.validation_result_data_type ?? "type not recorded"})${check.validation_comparison_value_type === "query" ? " from each query" : " from Query A"}.`}
          {!executionOnly ? " Query errors or an invalid result shape cannot pass." : null}</dd></div>
      </dl>
      <div className="validation-query-grid">
        <section className="workspace-sql"><header><h3>Query A</h3><span>{executionOnly ? "Execution check" : "Measured value"}</span></header>
          <pre tabIndex={0} aria-label="Query A SQL"><code>{check.validation_query_sql}</code></pre>
        </section>
        {check.validation_comparison_query_sql ? (
          <section className="workspace-sql"><header><h3>Query B</h3><span>Comparison value</span></header>
            <pre tabIndex={0} aria-label="Query B SQL"><code>{check.validation_comparison_query_sql}</code></pre>
          </section>
        ) : null}
      </div>
      <details className="validation-context-details"><summary>Definition details</summary>
        <dl className="validation-context-facts">
          <div><dt>System</dt><dd>{group.system_code}</dd></div>
          <div><dt>Group</dt><dd>{group.validation_group_name}</dd></div>
          <div><dt>Category</dt><dd>{humanize(check.validation_category_code)}</dd></div>
          <div><dt>Severity</dt><dd><SeverityBadge severity={check.validation_severity} /></dd></div>
          <div><dt>Status</dt><dd>{check.is_active ? "Active" : "Inactive"}</dd></div>
          <div><dt>Lock</dt><dd>{group.is_locked ? "Group locked" : check.is_locked ? "Locked" : "Open"}</dd></div>
          <div><dt>Operator</dt><dd><code>{check.validation_comparison_operator}</code></dd></div>
          <div><dt>Comparison type</dt><dd>{humanize(check.validation_comparison_value_type)}</dd></div>
          {check.validation_comparison_value_type === "literal" || check.validation_comparison_value_type === "literal_list" ?
            <div><dt>Comparison value</dt><dd><code>{comparisonValue(check.validation_comparison_value)}</code></dd></div> : null}
        </dl>
      </details>
    </section>
  );
}

function assertionLabel(check: ValidationValidationCheck, fails = false): string {
  const operator = check.validation_comparison_operator;
  if (operator === "executes_successfully") return "Query A completes without an execution error";
  const labels: Record<string, string> = fails ? {
    is_null: "is not null", is_not_null: "is null", is_true: "is not true", is_false: "is not false",
    equal: "does not equal", not_equal: "equals", greater_than: "is not greater than",
    greater_than_or_equal: "is not greater than or equal to", less_than: "is not less than",
    less_than_or_equal: "is not less than or equal to", in: "is not in", not_in: "is in",
  } : {
    is_null: "is null", is_not_null: "is not null", is_true: "is true", is_false: "is false",
    equal: "equals", not_equal: "does not equal", greater_than: "is greater than",
    greater_than_or_equal: "is greater than or equal to", less_than: "is less than",
    less_than_or_equal: "is less than or equal to", in: "is in", not_in: "is not in",
  };
  const operand = check.validation_comparison_value_type === "query" ? "the result of Query B"
    : check.validation_comparison_value_type === "none" ? "" : comparisonValue(check.validation_comparison_value);
  return `Query A’s result ${labels[operator] ?? humanize(operator)}${operand ? ` ${operand}` : ""}`;
}

function comparisonValue(value: unknown): string {
  if (value === undefined) return "Not recorded";
  if (typeof value === "string") return value === "" ? '""' : value;
  return JSON.stringify(value);
}

function humanize(value: string): string {
  return value.replaceAll("_", " ").replace(/^./, (character) => character.toLocaleUpperCase());
}
