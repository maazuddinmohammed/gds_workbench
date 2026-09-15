(function (root) {
  "use strict";
  function create({state, canValidate}) {
    const { escapeHtml, label } = root.AtlasText;
  function reportButton(area) {
    const report = state.reports[area];
    const status = !report ? "Not run" : report.stale ? "Stale" : report.valid ? "Passed" : `${report.issue_count} issues`;
    const tone = !report ? "" : report.stale ? "is-stale" : report.valid ? "is-valid" : "is-invalid";
    return `<button type="button" class="report-button ${state.validationArea === area ? "is-active" : ""}" data-report="${area}"><span><strong>${label(area)}</strong><small>${report ? `${report.run_by} · ${new Date(report.generated_at).toLocaleString()}` : "No shared report"}</small></span><b class="${tone}">${status}</b></button>`;
  }

  function validationFilter(labelText, field, values) {
    const selected = state.validationFilters[field];
    return `<details class="multi-filter"><summary><span>${labelText}</span><b>${selected.length ? `${selected.length} selected` : "All"}</b></summary><div class="multi-filter-menu">${values.map((value) => `<label><input type="checkbox" data-validation-filter="${field}" value="${escapeHtml(value)}" ${selected.includes(value) ? "checked" : ""}><span>${escapeHtml(value)}</span></label>`).join("")}<button type="button" class="filter-clear" data-clear-validation="${field}" ${selected.length ? "" : "disabled"}>Clear</button></div></details>`;
  }

  function validationWorkspace() {
    const report = state.reports[state.validationArea];
    const issues = report?.issues || [];
    const severities = [...new Set(issues.map((issue) => issue.severity))].sort();
    const datasets = [...new Set(issues.map((issue) => issue.dataset))].sort();
    const visible = issues.map((issue, index) => ({ issue, index })).filter(({ issue }) =>
      (!state.validationFilters.severity.length || state.validationFilters.severity.includes(issue.severity)) &&
      (!state.validationFilters.dataset.length || state.validationFilters.dataset.includes(issue.dataset))
    );
    const summary = report
      ? `<div class="report-summary ${report.stale ? "is-stale" : report.valid ? "is-valid" : "is-invalid"}"><div><span>Status</span><strong>${report.stale ? "Stale—Change Set changed" : report.valid ? "Passed" : `${report.issue_count} corrections`}</strong></div><div><span>Draft digest</span><strong class="mono">${escapeHtml(report.digest)}</strong></div><div><span>Snapshot revision</span><strong>${escapeHtml(report.snapshot.revision ?? "—")}</strong></div><div><span>Run by</span><strong>${escapeHtml(report.run_by)} · ${escapeHtml(new Date(report.generated_at).toLocaleString())}</strong></div></div><div class="report-path"><span>Shared local report</span><code>${escapeHtml(report.path || "Retained task evidence")}</code><span>${report.stale ? "Run again before review." : "Matches its recorded draft digest."}</span></div>`
      : '<div class="report-empty"><strong>Validation has not run.</strong><span>Run the same compiled local checks used by the agent.</span></div>';
    const table = visible.length
      ? `<table class="issue-table"><thead><tr><th>Severity</th><th>Check</th><th>Dataset</th><th>Record</th><th>Message</th><th></th></tr></thead><tbody>${visible.map(({ issue, index }) => `<tr><td><span class="severity ${escapeHtml(issue.severity)}">${escapeHtml(issue.severity)}</span></td><td>${escapeHtml(label(issue.code))}</td><td class="mono">${escapeHtml(issue.dataset)}</td><td>${escapeHtml(issue.record ?? "—")}</td><td>${escapeHtml(issue.message)}</td><td><button type="button" class="text-action" data-open-issue="${index}">Open record</button></td></tr>`).join("")}</tbody></table>`
      : `<div class="empty-state"><strong>${report && !report.stale && report.valid ? "No validation issues." : "No issues to display."}</strong><span>${report ? "Adjust the filters or run validation again." : "Choose an area and run local validation."}</span></div>`;
    return `<main class="validation-layout"><aside class="report-rail"><span class="field-label">Local reports</span>${reportButton("model")}${reportButton("metadata")}<p class="report-help">The agent and Workbench write the same digest-bound report. Refresh reads the newest report from the session.</p></aside><section class="validation-workspace"><div class="validation-heading"><div><span class="eyebrow">Compiled ${label(state.validationArea)} graph</span><h1>Local validation</h1><p>Open an affected record, correct its Change Set draft, then run validation again.</p></div><button type="button" class="button button-primary" data-action="run-report" ${canValidate(state.validationArea) && !state.busy ? "" : "disabled"}>Run ${label(state.validationArea)} validation</button></div>${summary}${report?.checks ? `<details class="checks-performed"><summary>Checks performed and remaining</summary><ul>${report.checks.map(check => `<li><code>${escapeHtml(check.id)}</code> · ${escapeHtml(check.status)}${check.reason ? ` — ${escapeHtml(check.reason)}` : ""}</li>`).join("")}</ul></details>` : ""}<div class="validation-filter-row">${validationFilter("Severity", "severity", severities)}${validationFilter("Dataset", "dataset", datasets)}<span>${issues.length} total issues</span></div><div class="issue-table-scroll">${table}</div></section></main>`;
  }
    return { validationWorkspace };
  }
  root.AtlasValidationUI = { create };
})(globalThis);
