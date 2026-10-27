// THROWAWAY prototype: options for showing Atlas information with less drill-down.
// Synthetic data from fixture.js. No production imports, API calls or persistence.
import {
  analysisFindings, contextRecords, entities, inputObjects, lock, project,
  relationshipBasis, runs, stages, subjectAreas, systems, tenant,
} from "./fixture.js";

const OPTIONS = {
  a: {
    label: "A · Inspector", nav: "ribbon", overview: "table", detail: "inspector",
    tagline: "Keep today's layout. Click any row and its full details open beside the list.",
    changes: [
      "A details panel opens beside every list. ↑ and ↓ move through records without leaving the page.",
      "Lists show what you open pages for today: attribute counts, keys, relationships, mapping coverage and SQL state.",
      "Project name, revision and lock move into the header. Stage tabs shrink to one row with status dots.",
      "Analysis reads as one sentence per relationship instead of 18 columns.",
    ],
    keeps: "Blue side navigation, horizontal stage tabs, current pages and addresses. Full detail pages stay available.",
    effort: "Low to medium. Mostly frontend. List endpoints add a few counts (attributes, keys, mapping coverage).",
    rules: "Detail pages become optional (Open full page) instead of the only way to see details.",
  },
  b: {
    label: "B · Cockpit", nav: "rail", overview: "board", detail: "expand",
    tagline: "Project stages move into the blue side rail. The Overview shows real numbers and the next step.",
    changes: [
      "Stage navigation moves from the horizontal ribbon to the side rail, grouped Setup → Evidence → Model → Deliver, with counts. Pages start about 150px higher.",
      "Overview becomes a pipeline board: each stage shows its numbers, warnings and last run, plus one Next step.",
      "Pages open with a summary strip (KPIs). Rows expand in place to show attributes, relationships and sources.",
      "Mapping becomes a coverage matrix: entities × Systems. Select a cell to see its attribute mappings.",
    ],
    keeps: "Blue rail, white header and working surfaces, ledgers and record pages.",
    effort: "Medium. Needs one Project summary endpoint with counts and warnings per stage.",
    rules: "Changes the approved horizontal Project ribbon to rail navigation inside a Project.",
  },
  c: {
    label: "C · Explorer", nav: "tree", overview: "matrix", detail: "page",
    tagline: "Organize around the model. One Entity page shows that entity across every stage.",
    changes: [
      "An explorer tree (Subject Area → Entity) sits beside the content, like a file tree.",
      "One Entity page shows definition, attributes with sources, mapping logic and profiling, relationships, and its path through Mapping, SQL and Validation.",
      "Model map: a diagram of entities and relationships, parents above children.",
      "Overview is a progress matrix: every entity against every delivery stage.",
    ],
    keeps: "Stage pages and governed actions; the tree adds a second way in.",
    effort: "High. New entity lineage read endpoints and a diagram component.",
    rules: "Adds a third navigation layer; Entity pages become the main review surface.",
  },
  rec: {
    label: "★ Recommended", nav: "rail", overview: "board", detail: "inspector", lineage: true,
    tagline: "B's navigation and Overview, A's details panel, and C's lineage strip.",
    changes: [
      "Side-rail stage navigation and the pipeline Overview from B: you see where the Project stands and what to do next.",
      "The details panel from A for every list: review records quickly without losing your place.",
      "The lineage strip from C inside the panel: each entity's progress through Mapping, SQL and Validation at a glance.",
      "Readable Analysis rows, coverage bars and summary strips everywhere.",
    ],
    keeps: "Current colors, fonts, governed actions and record pages.",
    effort: "Medium. Project summary endpoint plus small list additions; build it one screen at a time.",
    rules: "Replaces the horizontal Project ribbon; detail pages become optional.",
  },
};

const SCREENS = [["overview", "Overview"], ["logical", "Logical"], ["mapping", "Mapping"], ["analysis", "Analysis"]];
const STAGE_SCREEN = { overview: "overview", logical: "logical", mapping: "mapping", analysis: "analysis" };
const AUDIT = [
  ["SourceSystemID", "BIGINT"], ["IsCurrentRecord", "BOOLEAN"], ["RecordStartTime", "TIMESTAMP"],
  ["RecordEndTime", "TIMESTAMP"], ["IsDataValid", "BOOLEAN"], ["HashKey", "STRING"], ["IsActive", "BOOLEAN"],
  ["GDSBatchID", "BIGINT"], ["PipelineRunID", "STRING"], ["CreatedDate", "TIMESTAMP"],
  ["UpdatedDate", "TIMESTAMP"], ["CreatedBy", "STRING"], ["UpdatedBy", "STRING"],
];
const RESULTS = {
  supported: ["Supported", "is-good"], inconclusive: ["Inconclusive", "is-warn"],
  unsupported: ["Unsupported", "is-bad"], none: ["Not validated", "is-idle"],
};
const RUN_LABEL = { running: ["Running", "is-run"], completed: ["Completed", "is-good"], failed: ["Failed", "is-bad"] };
const TYPE_SHORT = { core: "Core", reference: "Ref", transaction: "Txn", event: "Event", history: "Hist" };
const SCHEMA_SYSTEM = { bronze_crm: "CRM", bronze_erp: "ERP", bronze_ecom: "ECOM" };
const LOGO = '<svg viewBox="0 0 32 32" aria-hidden="true"><path fill="currentColor" fill-rule="evenodd" d="M30 16a14 14 0 1 1-28 0 14 14 0 0 1 28 0ZM16 7 9 23l7-3.8 7 3.8-7-16Z"/></svg>';
const ICONS = {
  home: '<path d="M4 11.5 12 5l8 6.5V20h-5.5v-5h-5v5H4z"/>',
  database: '<ellipse cx="12" cy="6" rx="7" ry="3"/><path d="M5 6v6c0 1.7 3.1 3 7 3s7-1.3 7-3V6M5 12v6c0 1.7 3.1 3 7 3s7-1.3 7-3v-6"/>',
  layers: '<path d="m12 4 8 4-8 4-8-4 8-4Z"/><path d="m4 12 8 4 8-4M4 16l8 4 8-4"/>',
  prompt: '<path d="M5 5h14v10H9l-4 4z"/>',
  grid: '<rect x="4.5" y="4.5" width="6" height="6" rx="1"/><rect x="13.5" y="4.5" width="6" height="6" rx="1"/><rect x="4.5" y="13.5" width="6" height="6" rx="1"/><rect x="13.5" y="13.5" width="6" height="6" rx="1"/>',
  search: '<circle cx="11" cy="11" r="6"/><path d="m20 20-4.5-4.5"/>',
  chevronDown: '<path d="m7 10 5 5 5-5"/>',
  chevronRight: '<path d="m10 7 5 5-5 5"/>',
  chevronLeft: '<path d="m14 7-5 5 5 5"/>',
  arrowRight: '<path d="M5 12h14M13 6l6 6-6 6"/>',
  lock: '<rect x="5" y="11" width="14" height="9" rx="2"/><path d="M8 11V8a4 4 0 0 1 8 0v3"/>',
  alert: '<path d="M12 4 2.8 20h18.4z"/><path d="M12 10v4.5M12 17.2v.3"/>',
  x: '<path d="M6 6l12 12M18 6 6 18"/>',
  clock: '<circle cx="12" cy="12" r="8"/><path d="M12 7.5V12l3 2"/>',
  refresh: '<path d="M19 8a7.5 7.5 0 1 0 .8 6M19 4v4h-4"/>',
  external: '<path d="M14 5h5v5M19 5l-8 8M17 14v5H5V7h5"/>',
  info: '<circle cx="12" cy="12" r="8.5"/><path d="M12 11v5M12 8v.3"/>',
  diagram: '<rect x="8.5" y="3.5" width="7" height="5" rx="1"/><rect x="3.5" y="15.5" width="7" height="5" rx="1"/><rect x="13.5" y="15.5" width="7" height="5" rx="1"/><path d="M12 8.5v3.5M7 15.5V12h10v3.5"/>',
};

const root = document.getElementById("root");
const toastHost = document.getElementById("toast");

// ---------- Derived data ----------

const byOrder = (left, right) => left.order - right.order || left.name.localeCompare(right.name);
const entityById = new Map(entities.map((entity) => [entity.id, entity]));
const entityByName = new Map(entities.map((entity) => [entity.name, entity]));
const areaById = new Map(subjectAreas.map((area) => [area.id, area]));
const systemName = Object.fromEntries(systems.map((system) => [system.code, system.name]));

const relationships = entities.flatMap((child) => child.attrs.filter((attr) => attr.fk).map((attr) => {
  const parent = entityByName.get(attr.fk);
  return {
    child, attr, parent,
    parentKey: parent.attrs.find((key) => key.nk && !key.fk) ?? parent.attrs[0],
    basis: relationshipBasis[`${child.name}.${attr.name}`] ?? "Matching code values in both Objects (Profiling and Analysis).",
  };
}));

const coverageById = new Map(entities.map((entity) => {
  const pairs = entity.systems.map((system) => {
    const missing = entity.attrs.filter((attr) => !attr.map[system]).map((attr) => attr.name);
    const total = entity.attrs.length;
    const mapped = total - missing.length;
    return { key: `${entity.id}:${system}`, entity, system, mapped, total, missing, state: coverageState(mapped, total) };
  });
  const mapped = pairs.reduce((sum, pair) => sum + pair.mapped, 0);
  const total = pairs.reduce((sum, pair) => sum + pair.total, 0);
  return [entity.id, { pairs, mapped, total, state: coverageState(mapped, total) }];
}));
const mappingPairs = [...entities].sort(byOrder).flatMap((entity) => coverageById.get(entity.id).pairs);

function coverageState(mapped, total) {
  return mapped === 0 ? "none" : mapped === total ? "complete" : "partial";
}

const totals = {
  entities: entities.length,
  attributes: entities.reduce((sum, entity) => sum + entity.attrs.length, 0),
  relationships: relationships.length,
  locked: entities.filter((entity) => entity.locked).length,
  usedObjects: new Set(entities.flatMap((entity) => entity.sources.map((source) => source.object))).size,
  objects: inputObjects.length,
  mapped: entities.filter((entity) => coverageById.get(entity.id).state !== "none").length,
  complete: entities.filter((entity) => coverageById.get(entity.id).state === "complete").length,
  slotsMapped: mappingPairs.reduce((sum, pair) => sum + pair.mapped, 0),
  slots: mappingPairs.reduce((sum, pair) => sum + pair.total, 0),
  sqlFiles: entities.filter((entity) => entity.sql.file).length,
  sqlStale: entities.filter((entity) => entity.sql.state === "stale").length,
  sqlPlaceholders: entities.filter((entity) => entity.sql.state === "placeholders").length,
  result: (result) => analysisFindings.filter((finding) => (finding.result ?? "none") === result).length,
};

// Logical provenance: physical columns behind an Attribute, separate from Mapping logic.
function provenance(attr) {
  const mapped = Object.entries(attr.map)
    .filter(([, [column]]) => !column.startsWith("("))
    .map(([system, [column]]) => ({ system, column }));
  return mapped.length ? mapped : attr.src.map((column) => ({ system: SCHEMA_SYSTEM[column.split(".")[0]], column }));
}

function entityHealth(entity) {
  const coverage = coverageById.get(entity.id);
  if (coverage.state === "none") return { state: "notrun", label: "Not mapped yet" };
  if (coverage.state === "partial") return { state: "attention", label: "Mapping incomplete" };
  if (entity.sql.state !== "current") return { state: "attention", label: "SQL needs regeneration" };
  return { state: "complete", label: "Mapped; SQL current" };
}

// ---------- State ----------

const params = new URLSearchParams(location.search);
const state = {
  option: Object.hasOwn(OPTIONS, params.get("option") ?? "") ? params.get("option") : "rec",
  screen: SCREENS.some(([id]) => id === params.get("screen")) ? params.get("screen") : "overview",
  entityId: params.has("entity") ? Number(params.get("entity")) || null : 7,
  mapKey: "7:ERP",
  mapSystem: null,
  findingId: "F-4",
  logicalView: "entities",
  expanded: new Set(["logical:4", "mapping:7:ERP", "analysis:F-4"]),
  openAttrs: new Set(["7:3"]),
  checked: new Set(),
  showAudit: false,
  query: "", area: "all", type: "all",
  pairFilter: "all", resultFilter: "all",
  treeLayer: "logical", treeClosed: new Set(), mapArea: "all",
  notesOpen: params.get("notes") === "1",
  focusKey: null, revealKey: null,
};
let lastView = "";

// ---------- Small helpers ----------

const esc = (value) => String(value ?? "").replace(/[&<>"']/g, (character) => (
  { "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;", "'": "&#39;" }[character]));
const icon = (name, className = "") => `<svg class="icon ${className}" viewBox="0 0 24 24" aria-hidden="true">${ICONS[name]}</svg>`;
const num = (value) => value.toLocaleString("en-US");
const pct = (part, whole) => Math.round((part / whole) * 100);
const plural = (count, word) => `${word}${count === 1 ? "" : "s"}`;
const shortColumn = (column) => column.split(".").slice(1).join(".");
const chip = (text, tone = "", iconName = "") => `<span class="chip ${tone}">${iconName ? icon(iconName) : ""}${esc(text)}</span>`;
const typeChip = (type) => `<span class="type type-${type}">${esc(type[0].toUpperCase() + type.slice(1))}</span>`;
const areaChips = (entity) => entity.areas.map((id) => `<span class="area-chip">${esc(areaById.get(id).name)}</span>`).join("");
const sys = (code) => `<span class="sys" title="${esc(systemName[code])}">${esc(code)}</span>`;

function fmtPct(value) {
  if (value === 0) return "0%";
  if (value < 0.01) return "<0.01%";
  if (value < 1) return `${value.toFixed(2)}%`;
  if (value < 10) return `${value.toFixed(1)}%`;
  return `${Math.round(value)}%`;
}

function highlight(text) {
  const query = state.query.trim();
  const index = query ? text.toLowerCase().indexOf(query.toLowerCase()) : -1;
  if (index < 0) return esc(text);
  return `${esc(text.slice(0, index))}<mark>${esc(text.slice(index, index + query.length))}</mark>${esc(text.slice(index + query.length))}`;
}

function stateMark(name) {
  const glyph = name === "complete" ? '<path d="m6.5 12.5 3.5 3.5 7.5-8"/>'
    : name === "attention" ? '<path d="M12 7v6M12 16.6v.2"/>'
      : name === "failed" ? '<path d="m8.5 8.5 7 7M15.5 8.5l-7 7"/>' : "";
  return `<span class="mark is-${name}" aria-hidden="true">${glyph ? `<svg viewBox="0 0 24 24">${glyph}</svg>` : ""}</span>`;
}

function bar(value, total, { tone, target } = {}) {
  const width = total ? (value / total) * 100 : 0;
  const color = tone ?? (value === total || (target && width >= target) ? "is-good" : value === 0 ? "is-empty" : "is-warn");
  return `<span class="bar ${color}" aria-hidden="true"><span style="width:${width}%"></span>${target ? `<i style="left:${target}%"></i>` : ""}</span>`;
}

function stackBar(parts) {
  const total = parts.reduce((sum, [count]) => sum + count, 0);
  return `<span class="stack" aria-hidden="true">${parts.map(([count, tone]) => `<span class="${tone}" style="flex:${count / total}"></span>`).join("")}</span>`;
}

function mappingCell(coverage) {
  return `<span class="cov" title="${coverage.mapped} of ${coverage.total} attribute mappings">${bar(coverage.mapped, coverage.total)}<span class="cov-text">${coverage.state === "none" ? "Not mapped" : `${coverage.mapped}/${coverage.total}`}</span></span>`;
}

function sqlChip(sql) {
  if (sql.state === "current") return chip("Current", "is-good");
  if (sql.state === "stale") return `<span title="${esc(sql.note)}">${chip("Stale", "is-warn")}</span>`;
  if (sql.state === "placeholders") return `<span title="${esc(sql.note)}">${chip("Placeholders", "is-warn")}</span>`;
  return chip("No SQL", "is-idle");
}

function keyBadges(attr) {
  const badges = [];
  if (attr.nk) badges.push('<span class="key key-nk" title="Natural key">NK</span>');
  if (attr.sk) badges.push('<span class="key key-sk" title="Surrogate key">SK</span>');
  if (attr.fk) badges.push(`<span class="key key-fk" title="Foreign key to ${esc(attr.fk)}">FK ${icon("arrowRight")}${esc(attr.fk)}</span>`);
  if (attr.pii) badges.push('<span class="key key-pii" title="Personally identifiable information">PII</span>');
  return badges.join("") || '<span class="muted">—</span>';
}

function noSourceLabel(attr) {
  const columns = Object.values(attr.map).map(([column]) => column);
  return columns.includes("(derived)") ? "Derived" : columns.includes("(constant)") ? "Constant" : "No physical source";
}

function statusPill(stage) {
  const tone = { complete: "is-good", attention: "is-warn", running: "is-run", failed: "is-bad" }[stage.state] ?? "is-idle";
  return chip(stage.status, tone);
}

// ---------- Shell ----------

function render() {
  const option = OPTIONS[state.option];
  const view = `${state.option}:${state.screen}`;
  const entering = view !== lastView;
  const saved = captureView();
  root.innerHTML = `
    <div class="app nav-${option.nav}">
      ${renderRail(option)}
      ${option.nav === "tree" ? renderExplorer() : ""}
      <div class="main">
        ${renderTopbar()}
        ${option.nav === "rail" ? "" : renderRibbon()}
        ${renderScreen(option)}
      </div>
    </div>
    ${renderSwitcher()}
    ${state.notesOpen ? renderNotes(option) : ""}`;
  if (entering) root.querySelector(".page")?.classList.add("page-enter");
  lastView = view;
  restoreView(saved);
  drawDiagram();
  const query = new URLSearchParams({ option: state.option, screen: state.screen, entity: String(state.entityId ?? 0) });
  history.replaceState(null, "", `?${query}`);
}

function captureView() {
  const active = document.activeElement;
  return {
    scroll: [...root.querySelectorAll("[data-scroll-key]")].map((element) => [element.dataset.scrollKey, element.scrollTop, element.scrollLeft]),
    focus: state.focusKey ?? active?.dataset?.focusKey ?? null,
    caret: active?.matches?.("input") ? active.selectionStart : null,
  };
}

function restoreView(saved) {
  for (const [key, top, left] of saved.scroll) {
    const element = root.querySelector(`[data-scroll-key="${CSS.escape(key)}"]`);
    if (element) { element.scrollTop = top; element.scrollLeft = left; }
  }
  if (state.revealKey) {
    root.querySelector(`[data-focus-key="${CSS.escape(state.revealKey)}"]`)?.scrollIntoView({ block: "start" });
  }
  if (saved.focus) {
    const element = root.querySelector(`[data-focus-key="${CSS.escape(saved.focus)}"]`);
    if (element) {
      element.focus({ preventScroll: true });
      if (saved.caret !== null && element.setSelectionRange) element.setSelectionRange(saved.caret, saved.caret);
      if (state.focusKey) element.scrollIntoView({ block: "nearest" });
    }
  }
  state.focusKey = null;
  state.revealKey = null;
}

function renderRail(option) {
  const compact = option.nav === "tree";
  const items = [["Home", "home"], ["Metadata", "database"], ["Projects", "layers"], ["Prompts", "prompt"]];
  return `<aside class="rail${compact ? " is-compact" : ""}" aria-label="Workspace navigation">
    <div class="rail-brand">${LOGO}<strong>ATLAS</strong></div>
    <nav class="rail-nav" aria-label="Workspace">
      ${items.map(([label, name]) => {
        const projects = label === "Projects";
        const className = projects ? (option.nav === "rail" ? " is-parent" : " is-active") : "";
        return `<a href="#" class="rail-item${className}" title="${label}" data-focus-key="nav-${label}"
          data-action="${projects ? "screen" : "toast"}" data-screen="overview" data-msg="${label} is unchanged in this prototype."
          ${projects && option.nav !== "rail" ? 'aria-current="page"' : ""}>${icon(name)}<span class="rail-label">${label}</span></a>`;
      }).join("")}
    </nav>
    ${option.nav === "rail" ? `<div class="rail-project">
      <div class="rail-project-id">
        <span class="rail-eyebrow">Project</span>
        <strong>${esc(project.name)}</strong>
        <span>Revision ${project.revision}</span>
      </div>
      <nav class="rail-stages" aria-label="Project sections">
        ${stageLink(stages[0], "rail")}
        ${["Setup", "Evidence", "Model", "Deliver"].map((group) => `<div class="rail-group" role="group" aria-label="${group}">
          <span class="rail-group-label" aria-hidden="true">${group}</span>
          ${stages.filter((stage) => stage.group === group).map((stage) => stageLink(stage, "rail")).join("")}
        </div>`).join("")}
      </nav>
    </div>` : ""}
  </aside>`;
}

function stageLink(stage, variant) {
  const screen = STAGE_SCREEN[stage.id];
  const active = screen === state.screen;
  const label = variant === "ribbon" ? stage.short ?? stage.label : stage.label;
  const title = stage.status ? `${stage.label}: ${stage.status}` : stage.label;
  return `<a href="#" class="${variant}-stage${active ? " is-active" : ""}" title="${esc(title)}"
    data-action="${screen ? "screen" : "toast"}" data-screen="${screen ?? ""}" data-focus-key="${variant}-${stage.id}"
    data-msg="${esc(stage.label)} keeps its current page in this prototype." ${active ? 'aria-current="page"' : ""}>
    ${stage.group ? stateMark(stage.state) : icon("grid", "stage-home")}
    <span class="${variant}-stage-label">${esc(label)}</span>${stage.status ? `<span class="sr-only">, ${esc(stage.status)}</span>` : ""}
    ${variant === "rail" && stage.count ? `<span class="rail-count">${esc(stage.count)}</span>` : ""}
  </a>`;
}

function renderRibbon() {
  const parts = [];
  let group;
  for (const stage of stages) {
    if (parts.length && stage.group !== group) parts.push('<span class="ribbon-sep" aria-hidden="true"></span>');
    group = stage.group;
    parts.push(stageLink(stage, "ribbon"));
  }
  return `<nav class="ribbon" aria-label="Project sections">${parts.join("")}</nav>`;
}

function renderTopbar() {
  const section = SCREENS.find(([id]) => id === state.screen)[1];
  const running = runs.find((run) => run.state === "running");
  const separator = icon("chevronRight", "crumb-sep");
  return `<header class="topbar">
    <nav class="crumbs" aria-label="Breadcrumb">
      <a href="#" class="crumb-tenant" data-action="toast" data-msg="Tenant Home is unchanged in this prototype.">${esc(tenant.name)}</a>${separator}
      <a href="#" class="crumb-projects" data-action="toast" data-msg="The Projects ledger is unchanged in this prototype.">Projects</a>${separator}
      <a href="#" class="crumb-project" data-action="screen" data-screen="overview">${esc(project.name)}</a>
      <span class="rev" title="Project revision">r${project.revision}</span>
      ${state.screen === "overview" ? "" : `${separator}<span class="crumb-current" aria-current="page">${section}</span>`}
    </nav>
    <div class="topbar-status">
      ${running ? `<button type="button" class="run-chip" data-action="toast" data-msg="Opens Dimensional activity: run ${running.id}, ${esc(running.detail)}.">
        <span class="pulse" aria-hidden="true"></span>${esc(running.workflow)} ${esc(running.operation)} running<span class="run-chip-detail">&nbsp;· ${esc(running.detail)}</span></button>` : ""}
      <span class="lock-chip" title="Tenant Lock">${icon("lock")}<span>Lock held by you<span class="lock-chip-detail"> · ${lock.minutesLeft} min left</span></span></span>
      <span class="avatar" title="${esc(tenant.user)} · ${esc(tenant.role)}">${esc(tenant.initials)}</span>
    </div>
  </header>`;
}

function renderExplorer() {
  const mapActive = state.screen === "logical" && !state.entityId;
  return `<aside class="explorer" aria-label="Model explorer">
    <div class="explorer-head">
      <div class="explorer-title"><span class="eyebrow">Project model</span><strong>${esc(project.name)}</strong></div>
      ${segmented("Layer", [["logical", "Logical"], ["dimensional", "Dimensional"]], state.treeLayer, "tree-layer", "seg-small seg-full")}
      <button type="button" class="explorer-map${mapActive ? " is-active" : ""}" data-action="model-map" data-area="all" data-focus-key="model-map">
        ${icon("diagram")}Model map<span>${totals.entities} entities</span></button>
    </div>
    <div class="tree" data-scroll-key="tree">
      ${state.treeLayer === "logical" ? subjectAreas.map(treeArea).join("") : `<p class="tree-note">Dimensional entities use the same tree and pages. This prototype shows the Logical layer.</p>`}
    </div>
  </aside>`;
}

function treeArea(area) {
  const members = entities.filter((entity) => entity.areas.includes(area.id)).sort(byOrder);
  const open = !state.treeClosed.has(area.id);
  return `<div class="tree-group">
    <button type="button" class="tree-area" aria-expanded="${open}" data-action="tree-toggle" data-area="${area.id}" data-focus-key="tree-${area.id}">
      ${icon(open ? "chevronDown" : "chevronRight")}<span>${esc(area.name)}</span><span class="tree-count">${members.length}</span>
    </button>
    ${open ? `<ul class="tree-list">${members.map((entity) => {
      const selected = state.entityId === entity.id && state.screen !== "overview";
      const health = entityHealth(entity);
      const coverage = coverageById.get(entity.id);
      return `<li><button type="button" class="tree-entity${selected ? " is-selected" : ""}" data-action="open-entity" data-entity="${entity.id}"
        data-focus-key="tree-${area.id}-${entity.id}" title="${esc(health.label)}" ${selected ? 'aria-current="true"' : ""}>
        ${stateMark(health.state)}<span class="tree-name">${esc(entity.name)}</span>
        <span class="tree-meta">${state.screen === "mapping" ? `${coverage.mapped}/${coverage.total}` : TYPE_SHORT[entity.type]}</span>
        ${entity.areas.length > 1 ? '<span class="tree-shared" title="Also in another Subject Area">2</span>' : ""}
      </button></li>`;
    }).join("")}</ul>` : ""}
  </div>`;
}

function renderSwitcher() {
  return `<div class="switcher" role="region" aria-label="Prototype controls">
    <span class="switcher-tag">Prototype</span>
    ${segmented("Design option", Object.entries(OPTIONS).map(([key, option]) => [key, option.label]), state.option, "option", "seg-dark")}
    ${segmented("Screen", SCREENS, state.screen, "screen", "seg-dark")}
    <button type="button" class="switcher-notes${state.notesOpen ? " is-active" : ""}" aria-expanded="${state.notesOpen}" data-action="notes" data-focus-key="notes">${icon("info")}Notes</button>
  </div>`;
}

function renderNotes(option) {
  return `<aside class="notes" aria-label="About ${esc(option.label)}">
    <header><div><span class="eyebrow">${state.option === "rec" ? "Recommended mix" : "Design option"}</span><h2>${esc(option.label)}</h2></div>
      <button type="button" class="btn btn-icon" aria-label="Close notes" data-action="notes">${icon("x")}</button></header>
    <p class="notes-tagline">${esc(option.tagline)}</p>
    <h3>What changes</h3><ul>${option.changes.map((change) => `<li>${esc(change)}</li>`).join("")}</ul>
    <h3>What stays</h3><p>${esc(option.keeps)}</p>
    <h3>Effort</h3><p>${esc(option.effort)}</p>
    <h3>Design rules affected</h3><p>${esc(option.rules)}</p>
    <p class="notes-hint">← → switch options · ↑ ↓ move through records · Esc closes panels</p>
  </aside>`;
}

// ---------- Shared building blocks ----------

function segmented(label, items, current, action, className = "") {
  return `<div class="seg ${className}" role="group" aria-label="${esc(label)}">${items.map(([id, text, count]) => `<button type="button"
    class="${id === current ? "is-active" : ""}" aria-pressed="${id === current}" data-action="${action}" data-value="${id}" data-screen="${id}"
    data-focus-key="${action}-${id}">${esc(text)}${count === undefined ? "" : `<span class="seg-count">${count}</span>`}</button>`).join("")}</div>`;
}

function pageHead(title, description, actions = "") {
  return `<header class="page-head${actions ? " page-head-row" : ""}"><div><h1>${title}</h1>${description ? `<p>${description}</p>` : ""}</div>
    ${actions ? `<div class="page-actions">${actions}</div>` : ""}</header>`;
}

function toolbar(...parts) {
  return `<div class="toolbar">${parts.join("")}</div>`;
}

function searchBox(placeholder) {
  return `<label class="search">${icon("search")}<span class="sr-only">Search</span>
    <input type="search" placeholder="${placeholder}" value="${esc(state.query)}" data-input="query" data-focus-key="search"></label>`;
}

function selectFilter(label, key, choices) {
  return `<label class="select-chip"><span>${label}</span><select data-filter="${key}" data-focus-key="filter-${key}">
    ${choices.map(([value, text]) => `<option value="${value}"${state[key] === value ? " selected" : ""}>${esc(text)}</option>`).join("")}
  </select>${icon("chevronDown")}</label>`;
}

// Page commands sit in the page head when there is one, otherwise at the end of the toolbar.
function commands(runLabel) {
  return `<button type="button" class="btn btn-ghost" data-action="toast" data-msg="Opens run history in a side panel.">${icon("clock")}Activity</button>
    <button type="button" class="btn btn-ghost" data-action="toast" data-msg="More: export, lock and lifecycle actions.">More${icon("chevronDown")}</button>
    <button type="button" class="btn btn-icon" aria-label="Refresh" title="Refresh" data-action="toast" data-msg="Refresh reloads this view. Nothing refreshes automatically.">${icon("refresh")}</button>
    <button type="button" class="btn btn-primary" data-action="toast" data-msg="Runs wait while the Dimensional Build runs (one run per Tenant).">${runLabel}${icon("chevronDown")}</button>`;
}

function kpis(items) {
  return `<dl class="kpis">${items.map(([label, value, note, tone = ""]) => `<div class="kpi ${tone}"><dt>${label}</dt>
    <dd><strong>${value}</strong>${note ? `<span>${note}</span>` : ""}</dd></div>`).join("")}</dl>`;
}

function entityFacts(entity) {
  return `<dl class="facts">
    <div><dt>Grain</dt><dd>${esc(entity.grain)}</dd></div>
    <div><dt>Subject Areas</dt><dd>${areaChips(entity)}</dd></div>
    <div><dt>Dependency order</dt><dd>${entity.order}</dd></div>
    <div><dt>Updated</dt><dd>${esc(entity.updated)}</dd></div>
  </dl>`;
}

function auditToggle(entity) {
  return `<button type="button" class="btn btn-ghost btn-small" data-action="audit" aria-pressed="${state.showAudit}" data-focus-key="audit-${entity.id}">
    ${state.showAudit ? "Hide" : "Show"} ${AUDIT.length} audit columns</button>`;
}

function attributeTable(entity, mode) {
  const headers = mode === "e360" ? ["Attribute", "Type", "Keys", "Source", "Mapping logic", "Source profile"] : ["Attribute", "Type", "Keys", mode === "wide" ? "Sources" : "Source"];
  const audit = state.showAudit ? AUDIT.map(([name, type]) => `<tr class="is-audit">
      <td><span class="attr-name">${name}</span></td><td><code>${type}</code></td><td><span class="key key-audit">Audit</span></td>
      <td colspan="${headers.length - 3}" class="muted">Added by the Project audit template</td></tr>`).join("") : "";
  return `<table class="grid attr-grid is-${mode}">
    <thead><tr>${headers.map((header) => `<th>${header}</th>`).join("")}</tr></thead>
    <tbody>${entity.attrs.map((attr, index) => attributeRow(entity, attr, index, mode)).join("")}${audit}</tbody>
  </table>`;
}

function attributeRow(entity, attr, index, mode) {
  const key = `${entity.id}:${index}`;
  const expandable = mode === "inspector";
  const open = expandable && state.openAttrs.has(key);
  const sources = provenance(attr);
  const typeCell = `<td><code>${esc(attr.type)}</code>${attr.nullable ? '<span class="cell-sub">Nullable</span>' : ""}</td>`;
  const sourceCell = !sources.length ? `<td><span class="muted">${noSourceLabel(attr)}</span></td>`
    : mode === "inspector" ? `<td><code class="src" title="${esc(sources.map((source) => source.column).join("\n"))}">${esc(sources[0].column.split(".").at(-1))}</code>${sources.length > 1 ? `<span class="more-count">+${sources.length - 1}</span>` : ""}</td>`
      : `<td>${sources.map((source) => `<span class="src-line">${entity.systems.length > 1 ? sys(source.system) : ""}<code class="src">${esc(shortColumn(source.column))}</code></span>`).join("")}</td>`;
  const extra = mode === "e360" ? `<td>${logicLines(entity, attr)}</td><td>${attr.profile ? profileBars(attr.profile, true) : '<span class="muted">Not profiled</span>'}</td>` : "";
  return `<tr class="${expandable ? "is-clickable" : ""}${open ? " is-open" : ""}"${expandable
    ? ` data-action="toggle-attr" data-key="${key}" tabindex="0" aria-expanded="${open}" data-focus-key="attr-${key}"` : ""}>
      <td><span class="attr-name">${expandable ? icon(open ? "chevronDown" : "chevronRight", "attr-chevron") : ""}${highlight(attr.name)}</span>
        <span class="attr-def">${esc(attr.definition)}</span></td>
      ${typeCell}<td>${keyBadges(attr)}</td>${sourceCell}${extra}
    </tr>${open ? `<tr class="attr-detail"><td colspan="4">
      <div class="attr-detail-grid">
        <div><h4>Sources</h4>${sources.length ? sources.map((source) => `<p>${sys(source.system)}<code>${esc(source.column)}</code></p>`).join("") : `<p class="muted">${noSourceLabel(attr)}</p>`}</div>
        <div><h4>Mapping logic</h4>${logicLines(entity, attr)}</div>
        <div><h4>Source profile</h4>${attr.profile ? profileBars(attr.profile) : '<p class="muted">Not profiled</p>'}</div>
      </div></td></tr>` : ""}`;
}

function logicLines(entity, attr) {
  return entity.systems.map((system) => {
    const mapping = attr.map[system];
    return `<span class="logic-line">${entity.systems.length > 1 ? sys(system) : ""}${mapping ? esc(mapping[1]) : '<span class="missing">Not mapped</span>'}</span>`;
  }).join("");
}

function profileBars(profile, compact = false) {
  const rows = [["Null", profile.nullPct], ["Distinct", profile.distinctPct]];
  return `<span class="profile${compact ? " is-compact" : ""}">${rows.map(([label, value]) => `<span class="profile-row">
    <span>${label}</span>${bar(value, 100, { tone: label === "Null" && value > 20 ? "is-warn" : "is-ink" })}<b>${fmtPct(value)}</b></span>`).join("")}</span>`;
}

function relationshipBlock(entity) {
  const parents = relationships.filter((relationship) => relationship.child === entity);
  const children = relationships.filter((relationship) => relationship.parent === entity && relationship.child !== entity);
  const link = (target) => target === entity ? `<span class="rel-self">${esc(target.name)}</span>`
    : `<button type="button" class="link-button" data-action="select-entity" data-entity="${target.id}">${esc(target.name)}</button>`;
  const item = (relationship, direction) => `<li class="rel">
    <div class="rel-line">${direction === "parent"
      ? `<span class="rel-attr">${esc(relationship.attr.name)}</span>${icon("arrowRight", "rel-arrow")}${link(relationship.parent)}<span class="rel-key">.${esc(relationship.parentKey.name)}</span>`
      : `${link(relationship.child)}<span class="rel-key">.${esc(relationship.attr.name)}</span>${icon("arrowRight", "rel-arrow")}<span class="rel-attr">${esc(relationship.parentKey.name)}</span>`}
      <span class="rel-card">Many to one</span></div>
    <p class="rel-basis">${esc(relationship.basis)}</p></li>`;
  return `<div class="rel-groups">
    <div><h4>Parents <span class="count">${parents.length}</span></h4>${parents.length ? `<ul>${parents.map((relationship) => item(relationship, "parent")).join("")}</ul>` : '<p class="muted">None. This entity does not reference others.</p>'}</div>
    <div><h4>Children <span class="count">${children.length}</span></h4>${children.length ? `<ul>${children.map((relationship) => item(relationship, "child")).join("")}</ul>` : '<p class="muted">None. No entity references this one.</p>'}</div>
  </div>`;
}

function sourcesBlock(entity) {
  return `<ul class="sources">${entity.sources.map((source) => `<li>
    <span class="source-id">${sys(source.system)}<code>${esc(source.object)}</code></span><p>${esc(source.rationale)}</p></li>`).join("")}</ul>`;
}

function contextBlock(entity) {
  if (!entity.context.length) return '<p class="muted">No Context records cite this entity.</p>';
  return `<ul class="context-list">${entity.context.map((id) => {
    const record = contextRecords[id];
    return `<li><span class="chip is-outline">${esc(record.kind)}</span><p>${esc(record.text)}</p><span class="cell-sub">${id} · ${esc(record.group)}</span></li>`;
  }).join("")}</ul>`;
}

function lineageStrip(entity, large = false) {
  const coverage = coverageById.get(entity.id);
  const sqlValue = { current: "Current", stale: "Stale", placeholders: "Placeholders", none: "Not generated" }[entity.sql.state];
  const nodes = [
    { label: "Sources", value: `${entity.sources.length} ${plural(entity.sources.length, "Object")}`, sub: [...new Set(entity.sources.map((source) => source.system))].join(" · "), state: "complete" },
    { label: "Logical", value: `${entity.attrs.length} attributes`, sub: entity.locked ? "Locked" : "Active, open", state: "complete" },
    { label: "Mapping", value: coverage.state === "none" ? "Not mapped" : `${coverage.mapped}/${coverage.total} mapped`, sub: coverage.pairs.map((pair) => `${pair.system} ${pair.mapped}/${pair.total}`).join(" · "),
      state: { complete: "complete", partial: "attention", none: "notrun" }[coverage.state], action: "go-mapping" },
    { label: "SQL", value: sqlValue, sub: entity.sql.file ?? "Needs Mapping first", state: entity.sql.state === "current" ? "complete" : entity.sql.state === "none" ? "notrun" : "attention" },
    { label: "Validation", value: entity.checks ? `${entity.checks} ${plural(entity.checks, "check")}` : "No checks", sub: entity.checks ? "Definitions saved" : "Needs SQL first", state: entity.checks ? "complete" : "notrun" },
    { label: "Feeds", value: entity.feeds[0], sub: entity.feeds.length > 1 ? `+ ${entity.feeds.slice(1).join(", ")}` : "Dimensional", state: "neutral" },
  ];
  return `<ol class="lineage${large ? " is-large" : ""}" aria-label="${esc(entity.name)} across stages">${nodes.map((node) => {
    const body = `<span class="lineage-label">${stateMark(node.state)}${node.label}</span><strong>${esc(node.value)}</strong><span class="lineage-sub">${esc(node.sub)}</span>`;
    return `<li class="lineage-node is-${node.state}">${node.action
      ? `<button type="button" data-action="${node.action}" data-entity="${entity.id}" title="Open ${node.label}">${body}</button>`
      : `<div>${body}</div>`}</li>`;
  }).join("")}</ol>`;
}

function emptyState(text) {
  return `<div class="empty">${esc(text)} <button type="button" class="link-button" data-action="clear-filters">Clear filters</button></div>`;
}

// ---------- Screens ----------

function renderScreen(option) {
  if (state.screen === "overview") {
    return option.overview === "table" ? overviewTable() : option.overview === "board" ? overviewBoard() : overviewMatrix();
  }
  if (state.screen === "logical") {
    if (option.detail === "page") return state.entityId ? entityPage(entityById.get(state.entityId)) : modelMap();
    return logicalList(option);
  }
  if (state.screen === "mapping") {
    if (option.detail === "page") return mappingPage(entityById.get(state.entityId) ?? entityById.get(7));
    return option.detail === "expand" ? mappingMatrix() : mappingList(option);
  }
  return analysisList(option);
}

// Overview ------------------------------------------------------------------

function stageFacts() {
  const supported = totals.result("supported");
  const inconclusive = totals.result("inconclusive");
  const unsupported = totals.result("unsupported");
  const current = totals.sqlFiles - totals.sqlStale - totals.sqlPlaceholders;
  return {
    settings: { metric: "", lines: [`Schemas <code>${project.logicalSchema}</code> and <code>${project.dimensionalSchema}</code>`, `SCD ${project.scd} · coverage targets 70% / 60%`] },
    scope: { metric: totals.objects, unit: "Objects", lines: ["Customer CRM 4 · Order ERP 7 · Web store 3"] },
    context: { metric: 11, unit: "records", lines: ["3 groups · 6 cited by the model"] },
    profiling: { metric: 131, unit: "columns profiled", lines: ["14 of 14 Objects · all rows"], bar: [14, 14], run: "Run 208 · Oct 22 · 3m 12s" },
    enrichment: { metric: 14, unit: "Objects described", lines: ["131 columns · 4 PII · 3 human edits"], run: "Run 207 · Oct 22 · 6m 40s" },
    analysis: { metric: analysisFindings.length, unit: "findings", lines: [`${supported} supported · ${inconclusive} inconclusive · ${unsupported} unsupported`],
      stack: [[supported, "is-good"], [inconclusive, "is-warn"], [unsupported, "is-bad"]], warn: `${inconclusive + unsupported} findings need review`, run: "Run 209 · Oct 22 · 9m 51s" },
    "subject-areas": { metric: subjectAreas.length, unit: "areas", lines: ["14 of 14 Objects assigned · 4 shared"] },
    logical: { metric: totals.entities, unit: "entities", lines: [`${totals.attributes} attributes · ${totals.relationships} relationships`],
      bar: [totals.usedObjects, totals.objects], target: 70, barLabel: `Source coverage ${pct(totals.usedObjects, totals.objects)}% · target 70%`, run: "Optimize 213 · today 8:15 · 14m" },
    dimensional: { metric: 8, unit: "entities", lines: ["54 attributes · 9 relationships"], bar: [2, 4], barTone: "is-run", barLabel: "Build: area 2 of 4 (Sales)", run: "Build 214 · started 10:02 AM" },
    mapping: { metric: `${totals.mapped}<small>/${totals.entities}</small>`, unit: "entities mapped", lines: [`${totals.slotsMapped} of ${totals.slots} attribute mappings`],
      bar: [totals.slotsMapped, totals.slots], warn: "Payment and Web Session not mapped", run: "Run 212 failed · yesterday 5:40 PM", runTone: "is-bad" },
    code: { metric: totals.sqlFiles, unit: "SQL files", lines: [`${current} current · ${totals.sqlStale} stale · ${totals.sqlPlaceholders} with placeholders`],
      stack: [[current, "is-good"], [totals.sqlStale, "is-warn"], [totals.sqlPlaceholders, "is-warn-soft"]], warn: "2 files are older than their Mapping", run: "Run 205 · Oct 24 · 11m" },
    validation: { metric: 14, unit: "checks", lines: ["4 groups · cover 9 entities"], run: "Run 206 · Oct 24 · 8m" },
  };
}

function projectHero() {
  return `<header class="hero">
    <div class="hero-text"><h1>${esc(project.name)}</h1><p>${esc(project.description)}</p></div>
    <dl class="hero-meta">
      <div><dt>Logical schema</dt><dd><code>${project.logicalSchema}</code></dd></div>
      <div><dt>Dimensional schema</dt><dd><code>${project.dimensionalSchema}</code></dd></div>
      <div><dt>SCD policy</dt><dd>${project.scd}</dd></div>
      <div><dt>Project lock</dt><dd>Unlocked</dd></div>
      <div><dt>Updated</dt><dd>${project.updated}</dd></div>
    </dl>
  </header>`;
}

function nextStep() {
  return `<section class="next-step" aria-labelledby="next-step-title">
    <span class="next-step-icon">${icon("arrowRight")}</span>
    <div><h2 id="next-step-title">Next: map Payment and Web Session</h2>
      <p>They have no Attribute mappings, so Code generation and Validation skip them. Mapping can run after the Dimensional Build finishes (one run per Tenant).</p></div>
    <div class="next-step-actions">
      <button type="button" class="btn btn-secondary" data-action="screen" data-screen="mapping">Open Mapping</button>
      <button type="button" class="btn btn-primary" disabled title="Available after the running Dimensional Build finishes">Run Mapping</button>
    </div>
  </section>`;
}

function attentionPanel() {
  const items = [
    ["attention", "2 SQL files are stale", "Sales Order and Invoice changed in Mapping after their SQL was generated.", "Review SQL", "toast"],
    ["attention", "2 entities are not mapped", "Payment and Web Session have no Attribute mappings.", "Open Mapping", "mapping"],
    ["attention", "2 mappings are incomplete", "Sales Order (Order ERP) has no Channel Code. Sales Order Line (Web store) has no Discount Amount.", "Review", "mapping"],
    ["attention", "3 Analysis findings need review", "2 inconclusive and 1 unsupported relationship.", "Review Analysis", "analysis"],
    ["failed", "Mapping run 212 failed", "Repair attempts exhausted · stage 2, attempt 3 · yesterday 5:40 PM.", "View run", "toast"],
  ];
  return `<section class="panel attention" aria-labelledby="attention-title">
    <header class="panel-head"><h2 id="attention-title">Needs attention <span class="count">${items.length}</span></h2></header>
    <ul>${items.map(([tone, title, text, action, screen]) => `<li>${stateMark(tone)}<div><strong>${title}</strong><p>${text}</p></div>
      <a href="#" class="text-link" data-action="${screen === "toast" ? "toast" : "screen"}" data-screen="${screen}" data-msg="${action} opens a page outside this prototype.">${action}</a></li>`).join("")}</ul>
  </section>`;
}

function recentRuns() {
  return `<section class="panel" aria-labelledby="runs-title">
    <header class="panel-head"><h2 id="runs-title">Recent runs</h2><a href="#" class="text-link" data-action="toast" data-msg="Opens the complete run history.">All runs</a></header>
    <ol class="timeline">${runs.slice(0, 6).map((run) => `<li class="is-${run.state}">
      <span class="timeline-dot" aria-hidden="true"></span>
      <div><strong>${run.workflow} ${run.operation}</strong> ${chip(RUN_LABEL[run.state][0], RUN_LABEL[run.state][1])}<p>${esc(run.detail)}</p></div>
      <div class="timeline-meta"><span>${run.when}</span><span>${run.duration ?? "In progress"} · ${esc(run.actor)}</span></div>
    </li>`).join("")}</ol>
  </section>`;
}

function overviewBoard() {
  const facts = stageFacts();
  const groups = [["Setup", "What goes in"], ["Evidence", "What the data says"], ["Model", "What we design"], ["Deliver", "What gets built"]];
  return `<main class="page page-scroll" data-scroll-key="${state.option}-overview">
    <div class="overview">
      ${projectHero()}
      ${nextStep()}
      <section class="board" aria-label="Project pipeline">
        ${groups.map(([group, caption]) => `<div class="board-col">
          <header class="board-col-head"><h2>${group}</h2><span>${caption}</span></header>
          ${stages.filter((stage) => stage.group === group).map((stage) => stageCard(stage, facts[stage.id])).join("")}
        </div>`).join("")}
      </section>
      <div class="overview-lower">${attentionPanel()}${recentRuns()}</div>
    </div>
  </main>`;
}

function stageCard(stage, fact) {
  const screen = STAGE_SCREEN[stage.id];
  return `<article class="stage-card is-${stage.state}">
    <a href="#" class="stage-card-link" data-action="${screen ? "screen" : "toast"}" data-screen="${screen ?? ""}" data-focus-key="card-${stage.id}"
      data-msg="${esc(stage.label)} keeps its current page in this prototype.">
      <header><h3>${esc(stage.label)}</h3>${stage.status ? statusPill(stage) : ""}</header>
      ${fact.metric !== "" ? `<p class="metric"><strong>${fact.metric}</strong><span>${fact.unit}</span></p>` : ""}
      ${fact.lines.map((line) => `<p class="stage-line">${line}</p>`).join("")}
      ${fact.bar ? `<span class="stage-bar">${bar(fact.bar[0], fact.bar[1], { tone: fact.barTone, target: fact.target })}${fact.barLabel ? `<span>${fact.barLabel}</span>` : ""}</span>` : ""}
      ${fact.stack ? stackBar(fact.stack) : ""}
      ${fact.warn ? `<p class="stage-warn">${icon("alert")}${fact.warn}</p>` : ""}
      ${fact.run ? `<footer class="${fact.runTone ?? ""}">${icon("clock")}${fact.run}</footer>` : ""}
    </a>
  </article>`;
}

function overviewTable() {
  const facts = stageFacts();
  return `<main class="page page-scroll" data-scroll-key="a-overview">
    <div class="overview">
      ${projectHero()}
      ${nextStep()}
      <section class="panel">
        <header class="panel-head"><h2>Workflow</h2><span class="muted small">Numbers come from saved results. Select a stage to review it.</span></header>
        <div class="table-wrap"><table class="grid overview-grid">
          <thead><tr><th>Stage</th><th>State</th><th>Output</th><th>Needs attention</th><th>Latest run</th><th><span class="sr-only">Open</span></th></tr></thead>
          <tbody>${stages.filter((stage) => stage.group).map((stage) => {
            const fact = facts[stage.id];
            const screen = STAGE_SCREEN[stage.id];
            return `<tr>
              <td><strong>${esc(stage.label)}</strong><span class="cell-sub">${stage.group}</span></td>
              <td>${stage.status ? statusPill(stage) : '<span class="muted">Setup</span>'}</td>
              <td>${fact.metric !== "" ? `<span class="output-metric">${fact.metric} ${fact.unit}</span>` : ""}<span class="cell-sub">${fact.lines[0]}</span></td>
              <td>${fact.warn ? `<span class="warn-text">${icon("alert")}${fact.warn}</span>` : '<span class="muted">—</span>'}</td>
              <td class="${fact.runTone === "is-bad" ? "bad-text" : ""}">${fact.run ?? '<span class="muted">—</span>'}</td>
              <td class="cell-action"><a href="#" class="text-link" data-action="${screen ? "screen" : "toast"}" data-screen="${screen ?? ""}"
                data-msg="${esc(stage.label)} keeps its current page in this prototype.">Review</a></td>
            </tr>`;
          }).join("")}</tbody>
        </table></div>
      </section>
      <div class="overview-lower">${attentionPanel()}${recentRuns()}</div>
    </div>
  </main>`;
}

function overviewMatrix() {
  const legend = [["complete", "Done"], ["attention", "Needs review"], ["notrun", "Not started"]];
  return `<main class="page page-scroll" data-scroll-key="c-overview">
    <div class="overview">
      ${projectHero()}
      ${nextStep()}
      <section class="panel">
        <header class="panel-head"><div><h2>Model progress</h2><p>Every Logical entity across the delivery stages. Select a row to open the entity.</p></div>
          <span class="legend">${legend.map(([name, label]) => `<span>${stateMark(name)}${label}</span>`).join("")}</span></header>
        <div class="table-wrap"><table class="grid matrix">
          <thead><tr><th>Entity</th><th>Sources</th><th>Logical</th><th>Mapping</th><th>SQL</th><th>Validation</th><th>Feeds Dimensional</th></tr></thead>
          <tbody>${[...entities].sort(byOrder).map((entity) => {
            const coverage = coverageById.get(entity.id);
            const sqlState = entity.sql.state === "current" ? "complete" : entity.sql.state === "none" ? "notrun" : "attention";
            return `<tr class="is-clickable" data-action="open-entity" data-entity="${entity.id}" tabindex="0" data-focus-key="matrix-${entity.id}">
              <td><span class="entity-cell"><span class="entity-name">${esc(entity.name)}</span>${typeChip(entity.type)}</span></td>
              <td><span class="nowrap">${entity.sources.length} ${plural(entity.sources.length, "Object")}</span><span class="cell-sub">${[...new Set(entity.sources.map((source) => source.system))].map(sys).join("")}</span></td>
              <td><span class="mark-text">${stateMark("complete")}${entity.attrs.length} attributes${entity.locked ? icon("lock", "inline-lock") : ""}</span></td>
              <td><span class="mark-text">${stateMark({ complete: "complete", partial: "attention", none: "notrun" }[coverage.state])}${mappingCell(coverage)}</span></td>
              <td><span class="mark-text">${stateMark(sqlState)}${sqlChip(entity.sql)}</span></td>
              <td><span class="mark-text">${stateMark(entity.checks ? "complete" : "notrun")}${entity.checks ? `${entity.checks} ${plural(entity.checks, "check")}` : '<span class="muted">None</span>'}</span></td>
              <td>${entity.feeds.map((name) => `<code class="code-chip">${name}</code>`).join("")}</td>
            </tr>`;
          }).join("")}</tbody>
        </table></div>
      </section>
    </div>
  </main>`;
}

// Logical --------------------------------------------------------------------

function visibleEntities() {
  const query = state.query.trim().toLowerCase();
  return [...entities].sort(byOrder).filter((entity) => (state.area === "all" || entity.areas.includes(state.area))
    && (state.type === "all" || entity.type === state.type)
    && (!query || entity.name.toLowerCase().includes(query) || entity.attrs.some((attr) => attr.name.toLowerCase().includes(query))));
}

function logicalToolbar(option) {
  const views = segmented("Logical views", [["areas", "Subject Areas", subjectAreas.length], ["entities", "Entities", totals.entities], ["relationships", "Relationships", totals.relationships]], state.logicalView, "logical-view");
  const filters = state.logicalView === "entities" ? searchBox("Search entities and attributes")
    + selectFilter("Subject Area", "area", [["all", "All"], ...subjectAreas.map((area) => [area.id, area.name])])
    + selectFilter("Type", "type", [["all", "All"], ["core", "Core"], ["reference", "Reference"], ["transaction", "Transaction"], ["event", "Event"], ["history", "History"]]) : "";
  const allOpen = visibleEntities().every((entity) => state.expanded.has(`logical:${entity.id}`));
  const expandAll = option.detail === "expand" && state.logicalView === "entities"
    ? `<button type="button" class="btn btn-ghost" data-action="expand-all" data-focus-key="expand-all">${allOpen ? "Collapse all" : "Expand all"}</button>` : "";
  if (option.nav !== "rail") {
    return toolbar(views, '<span class="toolbar-spacer"></span>', commands("Run Logical")) + (filters ? toolbar(filters) : "");
  }
  return toolbar(views, filters, expandAll ? `<span class="toolbar-spacer"></span>${expandAll}` : "");
}

function logicalKpis() {
  return kpis([
    ["Entities", totals.entities, `${totals.locked} locked`],
    ["Attributes", totals.attributes, `plus ${AUDIT.length} audit columns each`],
    ["Relationships", totals.relationships, "all Many to one"],
    ["Source coverage", `${pct(totals.usedObjects, totals.objects)}%`, `${totals.usedObjects} of ${totals.objects} Objects · target 70%`],
    ["Last run", "Optimize", "today 8:15 AM · 14m 02s"],
  ]);
}

function entityCells(entity, wideClass) {
  const coverage = coverageById.get(entity.id);
  const parents = relationships.filter((relationship) => relationship.child === entity).length;
  const children = relationships.filter((relationship) => relationship.parent === entity && relationship.child !== entity).length;
  const naturalKeys = entity.attrs.filter((attr) => attr.nk).length;
  const foreignKeys = entity.attrs.filter((attr) => attr.fk).length;
  const query = state.query.trim().toLowerCase();
  const attrHit = query && !entity.name.toLowerCase().includes(query) ? entity.attrs.find((attr) => attr.name.toLowerCase().includes(query)) : null;
  return `<td><span class="entity-cell"><span class="entity-name">${highlight(entity.name)}</span>${typeChip(entity.type)}</span>
      <span class="entity-def">${attrHit ? `Attribute: ${highlight(attrHit.name)}` : esc(entity.definition)}</span></td>
    <td class="${wideClass}">${areaChips(entity)}</td>
    <td class="num">${entity.attrs.length}</td>
    <td class="${wideClass}"><span class="nowrap">${naturalKeys} NK${foreignKeys ? ` · ${foreignKeys} FK` : ""}</span></td>
    <td class="${wideClass}"><span class="nowrap">${parents} ${parents === 1 ? "parent" : "parents"} · ${children} ${children === 1 ? "child" : "children"}</span></td>
    <td>${mappingCell(coverage)}</td>
    <td class="${wideClass}">${sqlChip(entity.sql)}</td>
    <td class="col-status">${entity.locked ? `<span class="lock-icon" title="Locked">${icon("lock")}<span class="sr-only">Locked</span></span>` : ""}</td>`;
}

const ENTITY_HEADERS = (wideClass) => `<th>Entity</th><th class="${wideClass}">Subject Areas</th><th class="num">Attributes</th>
  <th class="${wideClass}">Keys</th><th class="${wideClass}">Relationships</th><th>Mapping</th><th class="${wideClass}">SQL</th>
  <th class="col-status"><span class="sr-only">Lock</span></th>`;

function logicalList(option) {
  const list = visibleEntities();
  const inspector = option.detail === "inspector";
  const selected = inspector && state.logicalView === "entities" ? entityById.get(state.entityId) : null;
  const head = option.nav === "rail" ? pageHead("Logical", `Normalized entities in <code>${project.logicalSchema}</code>, built one Subject Area at a time.`, commands("Run Logical")) : '<h1 class="sr-only">Logical</h1>';
  const summary = option.nav === "rail" ? logicalKpis() : "";
  let body;
  if (state.logicalView === "relationships") body = relationshipList();
  else if (state.logicalView === "areas") body = areaCards();
  else if (!list.length) body = emptyState("No entities match these filters.");
  else if (inspector) {
    body = `<div class="table-card"><table class="grid entity-grid${selected ? " is-compact" : ""}">
      <thead><tr><th class="col-check"><input type="checkbox" aria-label="Select all entities" data-action="check-all"${list.every((entity) => state.checked.has(entity.id)) ? " checked" : ""}></th>${ENTITY_HEADERS("col-wide")}</tr></thead>
      <tbody>${list.map((entity) => {
        const isSelected = selected?.id === entity.id;
        return `<tr class="is-clickable${isSelected ? " is-selected" : ""}" data-action="select-entity" data-entity="${entity.id}" tabindex="0"
          aria-selected="${isSelected}" data-focus-key="logical-row-${entity.id}">
          <td class="col-check" data-action="check" data-id="${entity.id}"><input type="checkbox" tabindex="-1" aria-label="Select ${esc(entity.name)}"${state.checked.has(entity.id) ? " checked" : ""}></td>
          ${entityCells(entity, "col-wide")}</tr>`;
      }).join("")}</tbody></table></div>
      ${state.checked.size ? `<div class="selection-bar"><strong>${state.checked.size} selected</strong><button type="button" class="btn btn-secondary btn-small" data-action="toast" data-msg="Lock, unlock, deactivate or export the selected entities.">Review selected</button><button type="button" class="btn btn-ghost btn-small" data-action="clear-checked">Clear</button></div>` : ""}`;
  } else {
    body = `<div class="table-card"><table class="grid entity-grid is-expandable">
      <thead><tr><th class="col-toggle"><span class="sr-only">Expand</span></th>${ENTITY_HEADERS("")}</tr></thead>
      <tbody>${list.map((entity) => {
        const open = state.expanded.has(`logical:${entity.id}`);
        return `<tr class="is-clickable${open ? " is-open" : ""}" data-action="toggle-row" data-key="logical:${entity.id}" tabindex="0"
          aria-expanded="${open}" data-focus-key="logical-row-${entity.id}">
          <td class="col-toggle">${icon(open ? "chevronDown" : "chevronRight")}</td>${entityCells(entity, "")}</tr>
          ${open ? `<tr class="row-detail"><td colspan="9">${expandedEntity(entity)}</td></tr>` : ""}`;
      }).join("")}</tbody></table></div>`;
  }
  if (inspector) {
    return `<main class="page page-split${selected ? " has-inspector" : ""}">
      ${head}${logicalToolbar(option)}${summary}
      <div class="split">
        <section class="list-pane" data-scroll-key="${state.option}-logical-${state.logicalView}" aria-label="Logical ${state.logicalView}">${body}</section>
        ${selected ? entityInspector(selected, list, option) : ""}
      </div>
    </main>`;
  }
  return `<main class="page page-scroll" data-scroll-key="${state.option}-logical">${head}${logicalToolbar(option)}${summary}<div class="page-pad">${body}</div></main>`;
}

function expandedEntity(entity) {
  return `<div class="expanded">
    <div class="expanded-main">
      <p class="definition">${esc(entity.definition)}</p>
      <p class="grain"><span>Grain</span>${esc(entity.grain)}</p>
      <header class="section-head"><h3>Attributes <span class="count">${entity.attrs.length}</span></h3>${auditToggle(entity)}</header>
      ${attributeTable(entity, "wide")}
    </div>
    <div class="expanded-side">
      <section><h3>Relationships</h3>${relationshipBlock(entity)}</section>
      <section><h3>Sources</h3>${sourcesBlock(entity)}</section>
      <div class="expanded-actions">
        <button type="button" class="btn btn-secondary btn-small" data-action="toast" data-msg="Edit definition opens the existing dialog.">Edit</button>
        <button type="button" class="btn btn-ghost btn-small" data-action="toast" data-msg="More: Lock, Deactivate, Export DDL.">More${icon("chevronDown")}</button>
        <a href="#" class="text-link" data-action="toast" data-msg="The full Entity page keeps its current address.">Open full page ${icon("external")}</a>
      </div>
    </div>
  </div>`;
}

function inspectorBar(position, total, previousAttrs, nextAttrs, tools) {
  return `<div class="inspector-bar">
    <div class="pager">
      <button type="button" class="btn btn-icon btn-small" aria-label="Previous" ${previousAttrs ?? "disabled"}>${icon("chevronLeft")}</button>
      <span>${position ? `${position} of ${total}` : "Not in current filter"}</span>
      <button type="button" class="btn btn-icon btn-small" aria-label="Next" ${nextAttrs ?? "disabled"}>${icon("chevronRight")}</button>
      <span class="kbd-hint" title="Use the arrow keys to move through the list">↑ ↓</span>
    </div>
    <div class="inspector-tools">${tools}
      <button type="button" class="btn btn-icon btn-small" aria-label="Close details" title="Close (Esc)" data-action="close-inspector">${icon("x")}</button>
    </div>
  </div>`;
}

function entityInspector(entity, list, option) {
  const index = list.findIndex((item) => item.id === entity.id);
  const previous = list[index - 1];
  const next = index >= 0 ? list[index + 1] : undefined;
  const step = (target) => target ? `data-action="select-entity" data-entity="${target.id}"` : null;
  return `<aside class="inspector" aria-label="${esc(entity.name)} details" data-scroll-key="inspector-${entity.id}">
    ${inspectorBar(index + 1, list.length, step(previous), step(next), `
      <button type="button" class="btn btn-secondary btn-small" data-action="toast" data-msg="Edit definition opens the existing dialog.">Edit</button>
      <button type="button" class="btn btn-ghost btn-small" data-action="toast" data-msg="More: Lock, Deactivate, Export DDL.">More${icon("chevronDown")}</button>
      <button type="button" class="btn btn-icon btn-small" aria-label="Open full page" title="Open full page" data-action="toast" data-msg="The full Entity page keeps its current address.">${icon("external")}</button>`)}
    <header class="inspector-head">
      <code class="schema">${project.logicalSchema}</code>
      <h2>${esc(entity.name)}</h2>
      <div class="chip-row">${typeChip(entity.type)}${chip("Active", "is-good")}${entity.locked ? chip("Locked", "", "lock") : chip("Open", "is-outline")}</div>
    </header>
    ${option.lineage ? lineageStrip(entity) : ""}
    <section class="inspector-section"><p class="definition">${esc(entity.definition)}</p>${entityFacts(entity)}</section>
    <section class="inspector-section">
      <header class="section-head"><h3>Attributes <span class="count">${entity.attrs.length}</span></h3>${auditToggle(entity)}</header>
      <p class="hint">Select an attribute to see its sources, mapping logic and profile.</p>
      ${attributeTable(entity, "inspector")}
    </section>
    <section class="inspector-section"><header class="section-head"><h3>Relationships</h3></header>${relationshipBlock(entity)}</section>
    <section class="inspector-section"><header class="section-head"><h3>Sources <span class="count">${entity.sources.length}</span></h3></header>${sourcesBlock(entity)}</section>
    <section class="inspector-section"><header class="section-head"><h3>Context</h3></header>${contextBlock(entity)}</section>
  </aside>`;
}

function relationshipList() {
  return `<div class="table-card"><table class="grid">
    <thead><tr><th>From (child)</th><th><span class="sr-only">Points to</span></th><th>To (parent)</th><th>Cardinality</th><th>Basis</th></tr></thead>
    <tbody>${relationships.map((relationship) => `<tr class="is-clickable" data-action="select-entity" data-entity="${relationship.child.id}" tabindex="0">
      <td><span class="entity-name">${esc(relationship.child.name)}</span><span class="rel-key">.${esc(relationship.attr.name)}</span></td>
      <td>${icon("arrowRight", "rel-arrow")}</td>
      <td><span class="entity-name">${esc(relationship.parent.name)}</span><span class="rel-key">.${esc(relationship.parentKey.name)}</span></td>
      <td><span class="rel-card">Many to one</span></td>
      <td class="basis-cell">${esc(relationship.basis)}</td>
    </tr>`).join("")}</tbody></table></div>`;
}

function areaCards() {
  return `<div class="area-cards">${subjectAreas.map((area) => {
    const members = entities.filter((entity) => entity.areas.includes(area.id)).sort(byOrder);
    return `<article class="area-card">
      <header><h3>${esc(area.name)}</h3><span>${area.objects.length} Objects · ${members.length} entities</span></header>
      <p>${esc(area.description)}</p>
      <div class="area-entities">${members.map((entity) => `<button type="button" class="area-entity" data-action="select-entity" data-entity="${entity.id}">
        ${esc(entity.name)}${typeChip(entity.type)}</button>`).join("")}</div>
    </article>`;
  }).join("")}</div>`;
}

// Explorer pages (C) -----------------------------------------------------------

function entityHeader(entity, crumbs, actions) {
  return `<header class="e360-head">
    <nav class="mini-crumbs" aria-label="Location">${crumbs}</nav>
    <div class="e360-title"><div><code class="schema">${project.logicalSchema}</code><h1>${esc(entity.name)}</h1></div><div class="e360-actions">${actions}</div></div>
    <div class="chip-row">${typeChip(entity.type)}${chip("Active", "is-good")}${entity.locked ? chip("Locked", "", "lock") : chip("Open", "is-outline")}${areaChips(entity)}</div>
  </header>`;
}

function entityPage(entity) {
  const separator = icon("chevronRight", "crumb-sep");
  const area = areaById.get(entity.areas[0]);
  return `<main class="page page-scroll" data-scroll-key="c-entity-${entity.id}">
    <article class="e360">
      ${entityHeader(entity, `<a href="#" data-action="model-map" data-area="all">Logical</a>${separator}<a href="#" data-action="model-map" data-area="${area.id}">${esc(area.name)}</a>${separator}<span>${esc(entity.name)}</span>`,
        `<button type="button" class="btn btn-secondary" data-action="toast" data-msg="Edit definition opens the existing dialog.">Edit</button>
         <button type="button" class="btn btn-ghost" data-action="toast" data-msg="More: Lock, Deactivate, Export DDL.">More${icon("chevronDown")}</button>`)}
      <div class="e360-intro"><p class="definition">${esc(entity.definition)}</p><p class="grain"><span>Grain</span>${esc(entity.grain)}</p></div>
      ${lineageStrip(entity, true)}
      <section class="panel">
        <header class="panel-head"><h2>Attributes <span class="count">${entity.attrs.length}</span></h2>${auditToggle(entity)}</header>
        <div class="table-wrap">${attributeTable(entity, "e360")}</div>
      </section>
      <div class="e360-lower">
        <section class="panel"><header class="panel-head"><h2>Relationships</h2></header><div class="panel-body">${relationMini(entity)}${relationshipBlock(entity)}</div></section>
        <section class="panel"><header class="panel-head"><h2>Sources <span class="count">${entity.sources.length}</span></h2></header><div class="panel-body">${sourcesBlock(entity)}</div></section>
        <section class="panel"><header class="panel-head"><h2>Context and facts</h2></header><div class="panel-body">${contextBlock(entity)}${entityFacts(entity)}</div></section>
      </div>
    </article>
  </main>`;
}

function relationMini(entity) {
  const parents = relationships.filter((relationship) => relationship.child === entity).map((relationship) => relationship.parent);
  const children = relationships.filter((relationship) => relationship.parent === entity && relationship.child !== entity).map((relationship) => relationship.child);
  const node = (target) => target === entity ? `<span class="rel-node is-self">${esc(target.name)}</span>`
    : `<button type="button" class="rel-node" data-action="open-entity" data-entity="${target.id}">${esc(target.name)}</button>`;
  const lines = (count, down) => `<svg class="rel-mini-lines" viewBox="0 0 100 20" preserveAspectRatio="none" aria-hidden="true">${Array.from({ length: count }, (_, index) => {
    const x = ((index + 0.5) / count) * 100;
    return down ? `<line x1="${x}" y1="0" x2="50" y2="20"/>` : `<line x1="50" y1="0" x2="${x}" y2="20"/>`;
  }).join("")}</svg>`;
  return `<div class="rel-mini" aria-label="Relationship map">
    ${parents.length ? `<div class="rel-mini-row">${parents.map(node).join("")}</div>${lines(parents.length, true)}` : ""}
    <div class="rel-mini-row">${node(entity)}</div>
    ${children.length ? `${lines(children.length, false)}<div class="rel-mini-row">${children.map(node).join("")}</div>` : ""}
  </div>`;
}

function modelMap() {
  const members = state.mapArea === "all" ? entities : entities.filter((entity) => entity.areas.includes(state.mapArea));
  const rows = diagramRows(members);
  const choices = [["all", "All areas"], ...subjectAreas.map((area) => [area.id, area.name])];
  return `<main class="page page-scroll" data-scroll-key="c-map-${state.mapArea}">
    <header class="page-head page-head-row"><div><h1>Model map</h1><p>Logical entities by dependency: parents above, children below. Select an entity to open it.</p></div>
      ${segmented("Subject Area", choices, state.mapArea, "map-area", "seg-small")}</header>
    <section class="diagram" aria-label="Logical model diagram">
      <svg class="diagram-lines" aria-hidden="true"></svg>
      ${rows.map((row) => `<div class="diagram-row">${row.map(diagramBox).join("")}</div>`).join("")}
    </section>
  </main>`;
}

function diagramRows(members) {
  const included = new Set(members);
  const links = relationships.filter((relationship) => relationship.child !== relationship.parent
    && included.has(relationship.child) && included.has(relationship.parent));
  const level = new Map();
  const depth = (entity) => {
    if (level.has(entity)) return level.get(entity);
    const parents = links.filter((link) => link.child === entity);
    const value = parents.length ? 1 + Math.max(...parents.map((link) => depth(link.parent))) : 0;
    level.set(entity, value);
    return value;
  };
  const rows = [];
  for (const entity of [...members].sort(byOrder)) (rows[depth(entity)] ??= []).push(entity);
  const ordered = rows.filter(Boolean);
  // Sweep down (order by parents) and up (order by children) to reduce crossing lines.
  for (let pass = 0; pass < 3; pass += 1) {
    for (const direction of ["down", "up"]) {
      const sequence = direction === "down" ? [...ordered.keys()] : [...ordered.keys()].reverse();
      for (const rowIndex of sequence) {
        const position = new Map(ordered.flatMap((row) => row.map((entity, index) => [entity, (index + 0.5) / row.length])));
        const weight = (entity) => {
          const linked = links.filter((link) => (direction === "down" ? link.child : link.parent) === entity)
            .map((link) => position.get(direction === "down" ? link.parent : link.child));
          return linked.length ? linked.reduce((sum, value) => sum + value, 0) / linked.length : position.get(entity);
        };
        ordered[rowIndex] = [...ordered[rowIndex]].sort((left, right) => weight(left) - weight(right) || byOrder(left, right));
      }
    }
  }
  return ordered;
}

function diagramBox(entity) {
  const keys = entity.attrs.filter((attr) => attr.nk || attr.fk).slice(0, 4);
  const more = entity.attrs.length - keys.length;
  return `<button type="button" class="diagram-box type-edge-${entity.type}" data-action="open-entity" data-entity="${entity.id}" data-node="${entity.id}" data-focus-key="node-${entity.id}">
    <span class="diagram-box-head"><strong>${esc(entity.name)}</strong>${typeChip(entity.type)}</span>
    <span class="diagram-attrs">${keys.map((attr) => `<span>${attr.nk ? '<b class="key key-nk">NK</b>' : '<b class="key key-fk">FK</b>'}${esc(attr.name)}</span>`).join("")}
      ${more > 0 ? `<span class="muted">+ ${more} more</span>` : ""}</span>
    <span class="diagram-foot">${mappingCell(coverageById.get(entity.id))}</span>
  </button>`;
}

function drawDiagram() {
  const diagram = root.querySelector(".diagram");
  if (!diagram) return;
  const svg = diagram.querySelector(".diagram-lines");
  const frame = diagram.getBoundingClientRect();
  const boxes = new Map([...diagram.querySelectorAll("[data-node]")].map((element) => [Number(element.dataset.node), element.getBoundingClientRect()]));
  const links = relationships.filter((relationship) => relationship.parent !== relationship.child
    && boxes.has(relationship.child.id) && boxes.has(relationship.parent.id));
  // Spread line ends across each box so several lines stay distinguishable.
  const ends = new Map();
  const slot = (id, side) => {
    const key = `${id}:${side}`;
    const list = ends.get(key) ?? [];
    ends.set(key, list);
    return list;
  };
  links.forEach((link) => { slot(link.child.id, "top").push(link); slot(link.parent.id, "bottom").push(link); });
  const xAt = (id, side, link) => {
    const rect = boxes.get(id);
    const list = slot(id, side).sort((left, right) => {
      const other = (item) => boxes.get(side === "top" ? item.parent.id : item.child.id).left;
      return other(left) - other(right);
    });
    return rect.left - frame.left + (rect.width * (list.indexOf(link) + 1)) / (list.length + 1);
  };
  svg.setAttribute("viewBox", `0 0 ${frame.width} ${frame.height}`);
  svg.innerHTML = `<defs><marker id="arrow" viewBox="0 0 8 8" refX="7" refY="4" markerWidth="8" markerHeight="8" orient="auto-start-reverse">
      <path d="M0 0 8 4 0 8z" fill="#7f93b0"/></marker></defs>${links.map((link) => {
    const child = boxes.get(link.child.id);
    const parent = boxes.get(link.parent.id);
    const x1 = xAt(link.child.id, "top", link);
    const y1 = child.top - frame.top;
    const x2 = xAt(link.parent.id, "bottom", link);
    const y2 = parent.bottom - frame.top;
    const middle = (y1 + y2) / 2;
    return `<path d="M${x1} ${y1} C${x1} ${middle}, ${x2} ${middle}, ${x2} ${y2 + 2}" marker-end="url(#arrow)"><title>${esc(`${link.child.name}.${link.attr.name} → ${link.parent.name}.${link.parentKey.name}`)}</title></path>`;
  }).join("")}`;
}

// Mapping --------------------------------------------------------------------

function visiblePairs() {
  const query = state.query.trim().toLowerCase();
  return mappingPairs.filter((pair) => (state.pairFilter === "all" || pair.state === state.pairFilter)
    && (!query || pair.entity.name.toLowerCase().includes(query)));
}

function mappingKpis() {
  const incomplete = mappingPairs.filter((pair) => pair.state === "partial").length;
  const notMapped = mappingPairs.filter((pair) => pair.state === "none").length;
  return kpis([
    ["Entities mapped", `${totals.mapped}/${totals.entities}`, `${totals.complete} complete`],
    ["Attribute mappings", `${totals.slotsMapped}/${totals.slots}`, `${pct(totals.slotsMapped, totals.slots)}% filled`],
    ["Incomplete", incomplete, "entity and System pairs", "is-warn"],
    ["Not mapped", notMapped, "Payment, Web Session", "is-warn"],
    ["Last run", "Failed", "yesterday 5:40 PM · run 212", "is-bad"],
  ]);
}

function pairFilterControl() {
  const count = (filter) => mappingPairs.filter((pair) => filter === "all" || pair.state === filter).length;
  return segmented("Coverage", [["all", "All", count("all")], ["complete", "Complete", count("complete")], ["partial", "Incomplete", count("partial")], ["none", "Not mapped", count("none")]], state.pairFilter, "pair-filter");
}

function mappingToolbar(option, extra = "") {
  const layer = segmented("Layer", [["logical", "Logical → Silver"], ["dimensional", "Dimensional → Gold"]], "logical", "layer");
  if (option.nav !== "rail") return toolbar(layer, '<span class="toolbar-spacer"></span>', commands("Generate mappings")) + toolbar(searchBox("Search entities"), extra);
  return toolbar(layer, searchBox("Search entities"), extra);
}

function objectLogicBlock(entity, system) {
  const logic = entity.objectLogic[system];
  if (!logic) return `<div class="empty-inline">${icon("alert")}<span>No Object mapping yet. Run Mapping for this entity, or use Edit Object Mapping.</span></div>`;
  const sources = entity.sources.filter((source) => source.system === system);
  return `<dl class="facts">
      <div><dt>Source tables</dt><dd>${sources.map((source) => `<code>${esc(source.object)}</code>`).join("<br>")}</dd></div>
      <div><dt>Filter criteria</dt><dd>${logic.filter ? esc(logic.filter) : '<span class="muted">None</span>'}</dd></div>
    </dl>
    <pre class="sql"><code>${esc(logic.sample)}</code></pre>`;
}

function attributeMappingTable(entity, system) {
  return `<table class="grid map-grid"><thead><tr><th>Target attribute</th><th>Source</th><th>Transformation</th></tr></thead><tbody>
    ${entity.attrs.map((attr) => {
      const mapping = attr.map[system];
      const source = !mapping ? '<span class="missing">Not mapped</span>'
        : mapping[0].startsWith("(") ? `<span class="muted">${mapping[0] === "(constant)" ? "Constant" : "Derived"}</span>`
          : `<code class="src">${esc(shortColumn(mapping[0]))}</code>`;
      return `<tr class="${mapping ? "" : "is-missing"}">
        <td><span class="attr-name">${esc(attr.name)}</span><span class="attr-def"><code>${esc(attr.type)}</code></span></td>
        <td>${source}</td>
        <td>${mapping ? esc(mapping[1]) : '<span class="muted">Blank until mapped.</span>'}</td>
      </tr>`;
    }).join("")}</tbody></table>`;
}

function pairState(pair) {
  return pair.state === "complete" ? chip("Complete", "is-good") : pair.state === "partial" ? chip("Incomplete", "is-warn") : chip("Not mapped", "is-idle");
}

function mappingList(option) {
  const pairs = visiblePairs();
  const selected = mappingPairs.find((pair) => pair.key === state.mapKey) ?? null;
  const head = option.nav === "rail" ? pageHead("Mapping", "How each Logical entity is loaded from each contributing System.", commands("Generate mappings")) : '<h1 class="sr-only">Mapping</h1>';
  const table = !pairs.length ? emptyState("No mappings match these filters.") : `<div class="table-card"><table class="grid pair-grid${selected ? " is-compact" : ""}">
    <thead><tr><th>Entity and System</th><th class="col-wide">Source tables</th><th>Attribute mappings</th><th>Missing</th><th class="col-wide">SQL</th></tr></thead>
    <tbody>${pairs.map((pair) => {
      const isSelected = pair.key === state.mapKey;
      return `<tr class="is-clickable${isSelected ? " is-selected" : ""}" data-action="select-pair" data-key="${pair.key}" tabindex="0" aria-selected="${isSelected}" data-focus-key="pair-${pair.key}">
        <td><span class="entity-cell"><span class="entity-name">${highlight(pair.entity.name)}</span>${sys(pair.system)}</span><span class="cell-sub">${esc(systemName[pair.system])}</span></td>
        <td class="col-wide">${pair.entity.sources.filter((source) => source.system === pair.system).map((source) => `<code class="src">${esc(source.object)}</code>`).join("<br>")}</td>
        <td><span class="cov">${bar(pair.mapped, pair.total)}<span class="cov-text">${pair.mapped}/${pair.total}</span></span></td>
        <td>${pair.state === "complete" ? '<span class="muted">—</span>' : pair.state === "none" ? '<span class="missing">All attributes</span>' : `<span class="missing">${esc(pair.missing.join(", "))}</span>`}</td>
        <td class="col-wide">${sqlChip(pair.entity.sql)}</td>
      </tr>`;
    }).join("")}</tbody></table></div>`;
  return `<main class="page page-split${selected ? " has-inspector" : ""}">
    ${head}${mappingToolbar(option, pairFilterControl())}${option.nav === "rail" ? mappingKpis() : ""}
    <div class="split">
      <section class="list-pane" data-scroll-key="${state.option}-mapping-list" aria-label="Mappings">${table}</section>
      ${selected ? mappingInspector(selected, pairs, option) : ""}
    </div>
  </main>`;
}

function mappingInspector(pair, pairs, option) {
  const { entity, system } = pair;
  const index = pairs.findIndex((item) => item.key === pair.key);
  const step = (target) => target ? `data-action="select-pair" data-key="${target.key}"` : null;
  return `<aside class="inspector" aria-label="${esc(entity.name)} mapping from ${esc(systemName[system])}" data-scroll-key="map-${pair.key}">
    ${inspectorBar(index + 1, pairs.length, step(pairs[index - 1]), index >= 0 ? step(pairs[index + 1]) : null, `
      <button type="button" class="btn btn-secondary btn-small" data-action="toast" data-msg="Opens the Edit Object Mapping dialog.">Edit Object</button>
      <button type="button" class="btn btn-secondary btn-small" data-action="toast" data-msg="Opens the Edit Attribute Mapping dialog.">Edit Attributes</button>`)}
    <header class="inspector-head">
      <code class="schema">${project.logicalSchema}</code>
      <h2>${esc(entity.name)} <span class="from-system">from ${esc(systemName[system])}</span></h2>
      <div class="chip-row">${pairState(pair)}${sqlChip(entity.sql)}</div>
    </header>
    ${option.lineage ? lineageStrip(entity) : ""}
    <section class="inspector-section"><header class="section-head"><h3>Object logic</h3></header>${objectLogicBlock(entity, system)}</section>
    <section class="inspector-section"><header class="section-head"><h3>Attribute mappings <span class="count">${pair.mapped}/${pair.total}</span></h3></header>
      ${attributeMappingTable(entity, system)}</section>
  </aside>`;
}

function mappingMatrix() {
  const query = state.query.trim().toLowerCase();
  const list = [...entities].sort(byOrder).filter((entity) => !query || entity.name.toLowerCase().includes(query));
  return `<main class="page page-scroll" data-scroll-key="b-mapping">
    ${pageHead("Mapping", "Coverage of each Logical entity by contributing System. Select a cell to see its attribute mappings.", commands("Generate mappings"))}
    ${mappingToolbar(OPTIONS[state.option])}
    ${mappingKpis()}
    <div class="page-pad"><div class="table-card"><table class="grid coverage-grid">
      <thead><tr><th>Entity</th>${systems.map((system) => `<th>${esc(system.name)}</th>`).join("")}<th>SQL</th><th>Missing</th></tr></thead>
      <tbody>${list.map((entity) => {
        const coverage = coverageById.get(entity.id);
        const open = coverage.pairs.find((pair) => state.expanded.has(`mapping:${pair.key}`));
        const missing = coverage.pairs.filter((pair) => pair.missing.length);
        return `<tr data-focus-key="mapping-row-${entity.id}" class="${open ? "is-open" : ""}">
          <td><span class="entity-cell"><span class="entity-name">${highlight(entity.name)}</span>${typeChip(entity.type)}</span></td>
          ${systems.map((system) => {
            const pair = coverage.pairs.find((item) => item.system === system.code);
            if (!pair) return '<td class="cov-none"><span class="sr-only">Not a source</span><span aria-hidden="true">·</span></td>';
            const isOpen = open === pair;
            return `<td><button type="button" class="cov-pill is-${pair.state}${isOpen ? " is-open" : ""}" data-action="toggle-pair" data-key="${pair.key}"
              aria-expanded="${isOpen}" data-focus-key="pill-${pair.key}" aria-label="${esc(entity.name)} from ${esc(system.name)}: ${pair.mapped} of ${pair.total} mapped">
              ${bar(pair.mapped, pair.total)}<span>${pair.state === "none" ? "Not mapped" : `${pair.mapped}/${pair.total}`}</span>${icon(isOpen ? "chevronDown" : "chevronRight")}</button></td>`;
          }).join("")}
          <td>${sqlChip(entity.sql)}</td>
          <td>${missing.length ? missing.map((pair) => `<span class="missing-line">${sys(pair.system)}${pair.state === "none" ? "All attributes" : esc(pair.missing.join(", "))}</span>`).join("") : '<span class="muted">—</span>'}</td>
        </tr>
        ${open ? `<tr class="row-detail"><td colspan="${systems.length + 3}"><div class="expanded">
          <div class="expanded-main"><header class="section-head"><h3>${esc(entity.name)} from ${esc(systemName[open.system])} <span class="count">${open.mapped}/${open.total}</span></h3>${pairState(open)}</header>${attributeMappingTable(entity, open.system)}</div>
          <div class="expanded-side"><section><h3>Object logic</h3>${objectLogicBlock(entity, open.system)}</section>
            <div class="expanded-actions"><button type="button" class="btn btn-secondary btn-small" data-action="toast" data-msg="Opens the Edit Object Mapping dialog.">Edit Object</button>
            <button type="button" class="btn btn-secondary btn-small" data-action="toast" data-msg="Opens the Edit Attribute Mapping dialog.">Edit Attributes</button></div></div>
        </div></td></tr>` : ""}`;
      }).join("")}</tbody></table></div></div>
  </main>`;
}

function mappingPage(entity) {
  const coverage = coverageById.get(entity.id);
  const system = entity.systems.includes(state.mapSystem) ? state.mapSystem : entity.systems[0];
  const pair = coverage.pairs.find((item) => item.system === system);
  const separator = icon("chevronRight", "crumb-sep");
  return `<main class="page page-scroll" data-scroll-key="c-mapping-${entity.id}">
    <article class="e360">
      ${entityHeader(entity, `<span>Mapping</span>${separator}<span>Logical → Silver</span>${separator}<span>${esc(entity.name)}</span>`,
        `<button type="button" class="btn btn-secondary" data-action="toast" data-msg="Opens the Edit Object Mapping dialog.">Edit Object</button>
         <button type="button" class="btn btn-secondary" data-action="toast" data-msg="Opens the Edit Attribute Mapping dialog.">Edit Attributes</button>`)}
      ${lineageStrip(entity, true)}
      <div class="tabs" role="group" aria-label="Contributing System">${coverage.pairs.map((item) => `<button type="button" class="tab${item.system === system ? " is-active" : ""}"
        aria-pressed="${item.system === system}" data-action="map-system" data-value="${item.system}" data-focus-key="tab-${item.system}">
        ${esc(systemName[item.system])}<span class="cov">${bar(item.mapped, item.total)}<span class="cov-text">${item.mapped}/${item.total}</span></span></button>`).join("")}</div>
      <div class="e360-map">
        <section class="panel"><header class="panel-head"><h2>Attribute mappings <span class="count">${pair.mapped}/${pair.total}</span></h2>${pairState(pair)}</header>
          <div class="table-wrap">${attributeMappingTable(entity, system)}</div></section>
        <section class="panel"><header class="panel-head"><h2>Object logic</h2></header><div class="panel-body">${objectLogicBlock(entity, system)}</div></section>
      </div>
    </article>
  </main>`;
}

// Analysis -------------------------------------------------------------------

function visibleFindings() {
  const query = state.query.trim().toLowerCase();
  return analysisFindings.filter((finding) => (state.resultFilter === "all" || (finding.result ?? "none") === state.resultFilter)
    && (!query || `${finding.from} ${finding.to}`.toLowerCase().includes(query)));
}

function endpoint(path) {
  return `${sys(SCHEMA_SYSTEM[path.split(".")[0]])}<code class="ep" title="${esc(path)}">${esc(shortColumn(path))}</code>`;
}

function matchShare(finding) {
  return ((finding.aDistinct - finding.aMissing) / finding.aDistinct) * 100;
}

function findingSummary(finding) {
  if (!finding.result) return "Not validated yet";
  if (finding.aMissing === 0) return `All ${num(finding.aDistinct)} values found`;
  return `${num(finding.aMissing)} of ${num(finding.aDistinct)} values missing (${fmtPct(100 - matchShare(finding))})`;
}

function evidenceBlock(finding) {
  const differs = finding.observed && finding.observed !== finding.inferred;
  const side = (label, path, rows) => `<div class="endpoint-card"><span class="endpoint-label">${label}</span>
    <span class="endpoint-path">${endpoint(path)}</span><code class="endpoint-full">${esc(path).replaceAll(".", ".<wbr>")}</code>
    <dl>${rows.map(([term, value, tone = ""]) => `<div><dt>${term}</dt><dd class="${tone}">${value}</dd></div>`).join("")}</dl></div>`;
  return `<div class="evidence">
    <div class="evidence-pair">
      ${side("From (A)", finding.from, [["Rows", num(finding.aCount)], ["Distinct values", num(finding.aDistinct)],
        ["Missing in B", `${num(finding.aMissing)} · ${fmtPct(100 - matchShare(finding))}`, finding.aMissing ? "is-warn" : ""]])}
      <div class="evidence-arrow">${icon("arrowRight")}<span>${esc(finding.inferred)}</span></div>
      ${side("To (B)", finding.to, [["Rows", num(finding.bCount)], ["Distinct values", num(finding.bDistinct)],
        ["Not used by A", `${num(finding.bUnused)} · ${fmtPct((finding.bUnused / finding.bDistinct) * 100)}`]])}
    </div>
    <dl class="facts">
      <div><dt>Measured result</dt><dd>${chip(...RESULTS[finding.result ?? "none"])} ${esc(findingSummary(finding))}</dd></div>
      <div><dt>Cardinality</dt><dd>Inferred ${esc(finding.inferred)} · observed ${esc(finding.observed ?? "unavailable")}${differs ? ` ${chip("Differs from inference", "is-warn")}` : ""}</dd></div>
      <div><dt>Basis</dt><dd>${esc(finding.basis)}</dd></div>
    </dl>
    <p class="hint">Measured validation and the inferred reasoning stay separate. Missing values are counted on distinct non-null values.</p>
  </div>`;
}

function findingCells(finding, wideClass) {
  const [label, tone] = RESULTS[finding.result ?? "none"];
  const differs = finding.observed && finding.observed !== finding.inferred;
  return `<td><span class="finding-rel">${endpoint(finding.from)}${icon("arrowRight", "rel-arrow")}${endpoint(finding.to)}</span>
      <span class="cell-sub">${finding.id} · Foreign key · inferred ${esc(finding.inferred)}</span></td>
    <td>${chip(label, tone)}<span class="cell-sub">${esc(findingSummary(finding))}</span></td>
    <td class="${wideClass}"><span class="cov">${bar(matchShare(finding), 100, { tone: tone === "is-bad" ? "is-bad" : tone })}<span class="cov-text">${fmtPct(matchShare(finding))} found</span></span></td>
    <td class="${wideClass}">${differs ? chip("Differs from inference", "is-warn") : `<span class="muted">${esc(finding.observed ?? "Unavailable")}</span>`}</td>
    <td class="col-status">${finding.locked ? `<span class="lock-icon" title="Locked">${icon("lock")}<span class="sr-only">Locked</span></span>` : ""}</td>`;
}

function analysisList(option) {
  const list = visibleFindings();
  const inspector = option.detail === "inspector";
  const selected = inspector ? analysisFindings.find((finding) => finding.id === state.findingId) ?? null : null;
  const head = option.nav === "rail" ? pageHead("Analysis", "Inferred relationships between physical Attributes, with measured validation shown separately.", commands("Run Analysis")) : '<h1 class="sr-only">Analysis</h1>';
  const count = (result) => result === "all" ? analysisFindings.length : totals.result(result);
  const filter = segmented("Validation result", [["all", "All", count("all")], ["supported", "Supported", count("supported")], ["inconclusive", "Inconclusive", count("inconclusive")], ["unsupported", "Unsupported", count("unsupported")]], state.resultFilter, "result-filter");
  const commandBar = toolbar(filter, searchBox("Search Objects and Attributes"), option.nav === "rail" ? "" : `<span class="toolbar-spacer"></span>${commands("Run Analysis")}`);
  const headers = (toggle) => `<thead><tr>${toggle ? '<th class="col-toggle"><span class="sr-only">Expand</span></th>' : ""}<th>Relationship</th><th>Measured validation</th>
    <th class="col-wide">Match</th><th class="col-wide">Observed cardinality</th><th class="col-status"><span class="sr-only">Lock</span></th></tr></thead>`;
  if (inspector) {
    const table = !list.length ? emptyState("No findings match.") : `<div class="table-card"><table class="grid finding-grid${selected ? " is-compact" : ""}">${headers(false)}
      <tbody>${list.map((finding) => `<tr class="is-clickable${selected?.id === finding.id ? " is-selected" : ""}" data-action="select-finding" data-id="${finding.id}"
        tabindex="0" aria-selected="${selected?.id === finding.id}" data-focus-key="finding-${finding.id}">${findingCells(finding, "col-wide")}</tr>`).join("")}</tbody></table></div>`;
    const index = list.findIndex((finding) => finding.id === selected?.id);
    const step = (target) => target ? `data-action="select-finding" data-id="${target.id}"` : null;
    return `<main class="page page-split${selected ? " has-inspector" : ""}">${head}${commandBar}
      <div class="split">
        <section class="list-pane" data-scroll-key="${state.option}-analysis-list" aria-label="Analysis findings">${table}</section>
        ${selected ? `<aside class="inspector" aria-label="Finding ${selected.id}" data-scroll-key="finding-${selected.id}">
          ${inspectorBar(index + 1, list.length, step(list[index - 1]), index >= 0 ? step(list[index + 1]) : null, `
            <button type="button" class="btn btn-secondary btn-small" data-action="toast" data-msg="Locks this finding against later runs.">${selected.locked ? "Unlock" : "Lock"}</button>
            <button type="button" class="btn btn-ghost btn-small" data-action="toast" data-msg="More: Deactivate or Reactivate.">More${icon("chevronDown")}</button>`)}
          <header class="inspector-head"><span class="schema">${selected.id} · Foreign key</span>
            <h2 class="finding-title">${endpoint(selected.from)}${icon("arrowRight", "rel-arrow")}${endpoint(selected.to)}</h2>
            <div class="chip-row">${chip(...RESULTS[selected.result ?? "none"])}${chip("Active", "is-good")}${selected.locked ? chip("Locked", "", "lock") : chip("Open", "is-outline")}</div></header>
          <section class="inspector-section">${evidenceBlock(selected)}</section>
        </aside>` : ""}
      </div></main>`;
  }
  const table = !list.length ? emptyState("No findings match.") : `<div class="table-card"><table class="grid finding-grid is-expandable">${headers(true)}
    <tbody>${list.map((finding) => {
      const open = state.expanded.has(`analysis:${finding.id}`);
      return `<tr class="is-clickable${open ? " is-open" : ""}" data-action="toggle-row" data-key="analysis:${finding.id}" tabindex="0" aria-expanded="${open}"
        data-focus-key="analysis-row-${finding.id}"><td class="col-toggle">${icon(open ? "chevronDown" : "chevronRight")}</td>${findingCells(finding, "")}</tr>
        ${open ? `<tr class="row-detail"><td colspan="6">${evidenceBlock(finding)}</td></tr>` : ""}`;
    }).join("")}</tbody></table></div>`;
  return `<main class="page page-scroll" data-scroll-key="${state.option}-analysis">${head}${commandBar}<div class="page-pad">${table}</div></main>`;
}

// ---------- Events ----------

let toastTimer;
function toast(message) {
  toastHost.textContent = message;
  toastHost.classList.add("is-visible");
  clearTimeout(toastTimer);
  toastTimer = setTimeout(() => toastHost.classList.remove("is-visible"), 2800);
}

function toggle(set, key) {
  if (set.has(key)) set.delete(key);
  else set.add(key);
}

function selectEntity(id) {
  const option = OPTIONS[state.option];
  state.logicalView = "entities";
  if (option.detail === "expand") {
    state.expanded.add(`logical:${id}`);
    state.revealKey = `logical-row-${id}`;
  } else {
    state.entityId = id;
    if (option.detail === "inspector") state.focusKey = `logical-row-${id}`;
  }
}

function moveSelection(delta) {
  const option = OPTIONS[state.option];
  if (option.detail !== "inspector") return false;
  const step = (items, current) => {
    const index = items.indexOf(current);
    return items[index < 0 ? 0 : Math.min(items.length - 1, Math.max(0, index + delta))] ?? current;
  };
  if (state.screen === "logical" && state.logicalView === "entities") {
    state.entityId = step(visibleEntities().map((entity) => entity.id), state.entityId);
    state.focusKey = `logical-row-${state.entityId}`;
  } else if (state.screen === "mapping") {
    state.mapKey = step(visiblePairs().map((pair) => pair.key), state.mapKey);
    state.focusKey = `pair-${state.mapKey}`;
  } else if (state.screen === "analysis") {
    state.findingId = step(visibleFindings().map((finding) => finding.id), state.findingId);
    state.focusKey = `finding-${state.findingId}`;
  } else return false;
  return true;
}

root.addEventListener("click", (event) => {
  const target = event.target.closest("[data-action]");
  if (!target || target.disabled) return;
  if (target.matches("a")) event.preventDefault();
  const { action, value } = target.dataset;
  switch (action) {
    case "option": state.option = value; toast(OPTIONS[value].tagline); break;
    case "screen":
      state.screen = target.dataset.screen || "overview";
      state.query = "";
      if (state.screen === "mapping" && !state.entityId) state.entityId = 7;
      break;
    case "notes": state.notesOpen = !state.notesOpen; break;
    case "toast": toast(target.dataset.msg || "Prototype only."); return;
    case "select-entity": selectEntity(Number(target.dataset.entity)); break;
    case "open-entity":
      if (state.screen !== "mapping") state.screen = "logical";
      state.entityId = Number(target.dataset.entity);
      state.logicalView = "entities";
      break;
    case "close-inspector":
      if (state.screen === "logical") state.entityId = null;
      if (state.screen === "mapping") state.mapKey = null;
      if (state.screen === "analysis") state.findingId = null;
      break;
    case "logical-view": state.logicalView = value; break;
    case "toggle-row": toggle(state.expanded, target.dataset.key); break;
    case "expand-all": {
      const keys = visibleEntities().map((entity) => `logical:${entity.id}`);
      const allOpen = keys.every((key) => state.expanded.has(key));
      keys.forEach((key) => (allOpen ? state.expanded.delete(key) : state.expanded.add(key)));
      break;
    }
    case "toggle-attr": toggle(state.openAttrs, target.dataset.key); break;
    case "audit": state.showAudit = !state.showAudit; break;
    case "check": toggle(state.checked, Number(target.dataset.id)); break;
    case "check-all": {
      const ids = visibleEntities().map((entity) => entity.id);
      const all = ids.every((id) => state.checked.has(id));
      ids.forEach((id) => (all ? state.checked.delete(id) : state.checked.add(id)));
      break;
    }
    case "clear-checked": state.checked.clear(); break;
    case "select-pair": state.mapKey = target.dataset.key; state.focusKey = `pair-${state.mapKey}`; break;
    case "toggle-pair": {
      const key = target.dataset.key;
      const open = state.expanded.has(`mapping:${key}`);
      const entityId = key.split(":")[0];
      [...state.expanded].filter((item) => item.startsWith(`mapping:${entityId}:`)).forEach((item) => state.expanded.delete(item));
      if (!open) state.expanded.add(`mapping:${key}`);
      break;
    }
    case "pair-filter": state.pairFilter = value; break;
    case "select-finding": state.findingId = target.dataset.id; state.focusKey = `finding-${state.findingId}`; break;
    case "result-filter": state.resultFilter = value; break;
    case "tree-toggle": toggle(state.treeClosed, target.dataset.area); break;
    case "tree-layer": state.treeLayer = value; break;
    case "model-map": state.screen = "logical"; state.entityId = null; state.mapArea = target.dataset.area ?? "all"; break;
    case "map-area": state.mapArea = value; break;
    case "map-system": state.mapSystem = value; break;
    case "go-mapping": {
      const entity = entityById.get(Number(target.dataset.entity));
      const pairs = coverageById.get(entity.id).pairs;
      const pair = pairs.find((item) => item.state !== "complete") ?? pairs[0];
      state.screen = "mapping";
      state.entityId = entity.id;
      state.mapKey = pair.key;
      state.mapSystem = pair.system;
      state.expanded.add(`mapping:${state.mapKey}`);
      break;
    }
    case "layer":
      if (value === "dimensional") { toast("Dimensional Mapping uses the same layout. This prototype shows Logical."); return; }
      break;
    case "clear-filters":
      Object.assign(state, { query: "", area: "all", type: "all", pairFilter: "all", resultFilter: "all" });
      break;
    default: return;
  }
  render();
});

root.addEventListener("input", (event) => {
  if (event.target.dataset.input === "query") {
    state.query = event.target.value;
    render();
  }
});

root.addEventListener("change", (event) => {
  const key = event.target.dataset.filter;
  if (key) { state[key] = event.target.value; render(); }
});

document.addEventListener("keydown", (event) => {
  const typing = event.target.closest?.("input, select, textarea");
  if (event.key === "Escape") {
    if (state.notesOpen && event.target.closest?.(".notes")) state.notesOpen = false;
    else if (root.querySelector(".inspector")) {
      root.querySelector('.inspector [data-action="close-inspector"]')?.click();
      return;
    } else if (state.notesOpen) state.notesOpen = false;
    else return;
    render();
    return;
  }
  if (typing || event.metaKey || event.ctrlKey || event.altKey) return;
  if ((event.key === "Enter" || event.key === " ") && event.target.matches?.("tr[data-action]")) {
    event.preventDefault();
    event.target.click();
    return;
  }
  if ((event.key === "ArrowDown" || event.key === "ArrowUp") && !event.target.closest?.(".inspector, .notes, .switcher")) {
    if (moveSelection(event.key === "ArrowDown" ? 1 : -1)) { event.preventDefault(); render(); }
    return;
  }
  if ((event.key === "ArrowLeft" || event.key === "ArrowRight") && (event.target === document.body || event.target.closest?.(".switcher"))) {
    const keys = Object.keys(OPTIONS);
    state.option = keys[(keys.indexOf(state.option) + (event.key === "ArrowRight" ? 1 : -1) + keys.length) % keys.length];
    toast(OPTIONS[state.option].tagline);
    state.focusKey = event.target.closest?.(".switcher") ? `option-${state.option}` : null;
    event.preventDefault();
    render();
  }
});

let resizeFrame;
window.addEventListener("resize", () => {
  cancelAnimationFrame(resizeFrame);
  resizeFrame = requestAnimationFrame(drawDiagram);
});

render();
toast(`${OPTIONS[state.option].label}: ${OPTIONS[state.option].tagline} Notes explains each option.`);
document.fonts?.ready.then(drawDiagram);
