import { describe, expect, test } from "vitest";

import { StageMcpError } from "../src/mcp-client.js";
import { failureReceipt } from "../src/receipt.js";

describe("failureReceipt", () => {
  test("allows legacy fallback only before the deterministic runner starts a write", () => {
    const failure = new StageMcpError(
      "MCP_OUTCOME_UNKNOWN",
      "The Stage operation outcome is unknown; verify before retrying.",
    );

    expect(failureReceipt(failure, false)).toMatchObject({
      status: "failed",
      stageStarted: false,
      legacyFallbackAllowed: true,
    });
    expect(failureReceipt(failure, true)).toEqual({
      schemaVersion: "1.0",
      status: "failed",
      code: "MCP_OUTCOME_UNKNOWN",
      message: "The Stage operation outcome is unknown; verify before retrying.",
      stageStarted: true,
      legacyFallbackAllowed: false,
    });
  });

  test("redacts unexpected exception text", () => {
    const receipt = failureReceipt(new Error("raw response and bearer value"), false);

    expect(receipt.code).toBe("INTERNAL_ERROR");
    expect(JSON.stringify(receipt)).not.toContain("raw response");
    expect(JSON.stringify(receipt)).not.toContain("bearer");
  });
});
