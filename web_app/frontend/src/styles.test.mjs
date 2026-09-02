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
        '@import "./styles/tenant-entry.css";',
        '@import "./styles/tenant-workspace.css";',
        '@import "./styles/model-workspace-overrides.css";',
        '@import "./styles/code-generation.css";',
        '@import "./styles/validation.css";',
        '@import "./styles/prompts.css";',
        '@import "./styles/workflow-runs.css";',
        "",
      ].join("\n"),
    );
    expect(stylesheetManifest).not.toContain("{");
  });
});
