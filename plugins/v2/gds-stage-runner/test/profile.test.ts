import { readFileSync } from "node:fs";

import { describe, expect, test } from "vitest";

import {
  PRODUCTION_MCP_URL,
  resolveStageProfile,
  StageProfileError,
} from "../src/profile.js";

describe("resolveStageProfile", () => {
  test("uses the same production endpoint as the packaged GDS plugin", () => {
    const plugin = JSON.parse(
      readFileSync(new URL("../../gds/mcp.json", import.meta.url), "utf8"),
    ) as { mcpServers: { "gds-workbench": { url: string } } };

    expect(PRODUCTION_MCP_URL).toBe(plugin.mcpServers["gds-workbench"].url);
  });

  test("pins production to the packaged MCP endpoint and requires Microsoft auth", () => {
    expect(resolveStageProfile("production", "http://127.0.0.1:8000/mcp")).toEqual({
      name: "production",
      endpoint: new URL(PRODUCTION_MCP_URL),
      authentication: "microsoft",
    });
  });

  test("supports the temporary Azure local-mode deployment without authentication", () => {
    expect(resolveStageProfile("azureLocalTest", "http://127.0.0.1:8000/mcp")).toEqual({
      name: "azureLocalTest",
      endpoint: new URL(PRODUCTION_MCP_URL),
      authentication: "none",
    });
  });

  test("allows no-auth local mode only on an exact loopback /mcp URL", () => {
    expect(resolveStageProfile("local", "http://localhost:8123/mcp")).toEqual({
      name: "local",
      endpoint: new URL("http://localhost:8123/mcp"),
      authentication: "none",
    });
    expect(() => resolveStageProfile("local", "https://example.com/mcp")).toThrowError(
      StageProfileError,
    );
    expect(() => resolveStageProfile("local", "http://127.0.0.1:8123/not-mcp")).toThrowError(
      StageProfileError,
    );
  });
});
