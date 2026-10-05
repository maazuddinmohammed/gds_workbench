import { readFileSync } from "node:fs";

import { describe, expect, it } from "vitest";

function workspaceStyles(overrides = {}) {
  const css = [...readFileSync("src/styles.css", "utf8").matchAll(/@import "\.\/(.*?)";/g)]
    .map((match) => readFileSync(`src/${match[1]}`, "utf8")).join("\n");
  // jsdom does not resolve inherited custom properties in computed styles.
  const variables = new Map([...css.matchAll(/(--[a-z-]+):\s*([^;{}]+);/g)]
    .map((match) => [match[1], match[2]]));
  for (const [name, value] of Object.entries(overrides)) variables.set(name, value);
  return css.replace(/var\((--[a-z-]+)\)/g, (value, name) => variables.get(name) ?? value);
}

describe("stylesheet Module manifest", () => {
  it("keeps the feature Modules in cascade order without catch-all declarations", () => {
    const stylesheetManifest = readFileSync("src/styles.css", "utf8");

    expect(stylesheetManifest).toBe(
      [
        '@import "./styles/foundation.css";',
        '@import "./styles/models-scope.css";',
        '@import "./styles/analysis-assertions-modeled.css";',
        '@import "./styles/profiling.css";',
        '@import "./styles/metadata.css";',
        '@import "./styles/metadata-catalog.css";',
        '@import "./styles/tenant-entry.css";',
        '@import "./styles/tenant-workspace.css";',
        '@import "./styles/model-workspace-overrides.css";',
        '@import "./styles/code-generation.css";',
        '@import "./styles/validation.css";',
        '@import "./styles/prompts.css";',
        '@import "./styles/workflow-runs.css";',
        '@import "./styles/model-targets.css";',
        '@import "./shared/select-controls.css";',
        '@import "./styles/workflow-command-center.css";',
        '@import "./styles/ledger-grid.css";',
        '@import "./styles/workspace-design.css";',
        "",
      ].join("\n"),
    );
    expect(stylesheetManifest).not.toContain("{");
  });
});


describe("Workflow draft confirmation styling", () => {
  it("gives the portal card an opaque, scrollable surface and visible action", () => {
    const style = document.createElement("style");
    style.textContent = workspaceStyles();
    const portal = document.createElement("div");
    portal.innerHTML = '<section class="prompt-dialog workflow-draft-confirmation"><button class="button button-accent">Apply exact draft</button></section>';
    document.head.append(style);
    document.body.append(portal);
    try {
      expect(getComputedStyle(portal.firstChild).backgroundColor).toBe("rgb(255, 255, 255)");
      expect(getComputedStyle(portal.firstChild).overflow).toBe("auto");
      expect(getComputedStyle(portal.querySelector("button")).backgroundColor).toBe("rgb(183, 92, 39)");
    } finally {
      portal.remove();
      style.remove();
    }
  });
});

describe("Shared workspace design", () => {
  it.each(["400", "450"])("controls typography centrally across pages and dialogs at weight %s", (weight) => {
    const style = document.createElement("style");
    style.textContent = workspaceStyles({ "--workspace-font-weight": weight });
    const surface = document.createElement("div");
    surface.innerHTML = `<div class="app-shell">
      <div class="brand"><strong>ATLAS</strong></div>
      <aside class="sidebar"><a class="nav-item is-active" data-check>Home</a></aside>
      <main class="workspace workspace-model"><div class="model-workspace">
        <div class="model-overview"><strong data-check>Overview</strong></div>
        <div class="model-settings-page"><label data-check>Name</label>
          <nav class="workspace-tabs"><a class="is-active" data-check>Definition</a></nav></div>
        <div class="scope-page"><label data-check>Zone</label></div>
        <div class="workflow-command-center"><nav class="workflow-tabs"><button class="is-active" data-check>Entities</button></nav></div>
        <div class="ledger-grid"><table><thead><tr><th data-check>Column</th></tr></thead></table></div>
        <div class="prompts-workspace"><h1 data-check>Prompts</h1></div>
      </div></main>
      <main class="metadata-catalog"><header class="metadata-catalog-titlebar"><h1 data-check>Metadata</h1></header>
        <button class="button button-small" data-check>Reference</button></main>
    </div><div class="dialog-scrim"><section class="prompt-dialog"><h2 data-check>Edit details</h2></section></div>`;
    document.head.append(style);
    document.body.append(surface);
    try {
      for (const element of surface.querySelectorAll("[data-check]")) {
        expect(getComputedStyle(element).fontWeight, element.textContent).toBe(weight);
      }
      expect(getComputedStyle(surface.querySelector(".brand strong")).fontWeight).not.toBe(weight);
      const settingsTab = getComputedStyle(surface.querySelector(".workspace-tabs a"));
      const workflowTab = getComputedStyle(surface.querySelector(".workflow-tabs button"));
      for (const property of ["fontSize", "padding", "borderColor", "backgroundColor", "minHeight"]) {
        expect(settingsTab[property], property).toBe(workflowTab[property]);
      }
    } finally {
      surface.remove();
      style.remove();
    }
  });
});
