import { readFileSync } from "node:fs";

import { describe, expect, it } from "vitest";

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
        "",
      ].join("\n"),
    );
    expect(stylesheetManifest).not.toContain("{");
  });
});


describe("Workflow draft confirmation styling", () => {
  it("gives the portal card an opaque, scrollable surface and visible action", () => {
    const style = document.createElement("style");
    let css = [...readFileSync("src/styles.css", "utf8").matchAll(/@import "\.\/(.*?)";/g)]
      .map((match) => readFileSync(`src/${match[1]}`, "utf8")).join("\n");
    // jsdom does not resolve inherited custom properties in computed colors.
    const variables = new Map([...css.matchAll(/(--[a-z-]+):\s*([^;{}]+);/g)]
      .map((match) => [match[1], match[2]]));
    style.textContent = css.replace(/var\((--[a-z-]+)\)/g,
      (value, name) => variables.get(name) ?? value);
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
