import { mkdir, mkdtemp, readFile, readdir, rm, symlink } from "node:fs/promises";
import { tmpdir } from "node:os";
import { join } from "node:path";
import { describe, expect, test } from "vitest";

import { StageMcpError } from "../src/mcp-client.js";
import { exportReceipt, failureReceipt } from "../src/receipt.js";

describe("failureReceipt", () => {
  test("allows legacy fallback only before the deterministic runner starts a write", () => {
    const failure = new StageMcpError(
      "MCP_OUTCOME_UNKNOWN",
      "The Stage operation outcome is unknown; verify before retrying.",
    );

    expect(failureReceipt(failure, false)).toMatchObject({
      status: "failed",
      stage_started: false,
      legacy_fallback_allowed: true,
    });
    expect(failureReceipt(failure, true)).toEqual({
      schema_version: "1.0",
      status: "failed",
      code: "MCP_OUTCOME_UNKNOWN",
      message: "The Stage operation outcome is unknown; verify before retrying.",
      stage_started: true,
      legacy_fallback_allowed: false,
    });
  });

  test("redacts unexpected exception text", () => {
    const receipt = failureReceipt(new Error("raw response and bearer value"), false);

    expect(receipt.code).toBe("INTERNAL_ERROR");
    expect(JSON.stringify(receipt)).not.toContain("raw response");
    expect(JSON.stringify(receipt)).not.toContain("bearer");
  });
});

describe("receipt JSON export", () => {
  test("writes one bounded JSON document atomically without replacing existing evidence", async () => {
    const root = await mkdtemp(join(tmpdir(), "atlas-export-"));
    try {
      await mkdir(join(root, ".atlas/temp"), { recursive: true });
      const file = join(root, ".atlas/temp/check.json");
      const receipt = { schema_version: "1.0", status: "ready", backend: { profile: "local", endpoint_sha256: "a".repeat(64) } };
      expect(await exportReceipt(receipt, file, [root])).toEqual(receipt);
      expect(JSON.parse(await readFile(file, "utf8"))).toEqual(receipt);
      const staged = { schema_version: "1.0", status: "staged" };
      expect(await exportReceipt(staged, file, [root])).toMatchObject({ status: "staged", receipt_export: { code: "RECEIPT_EXPORT_FAILED" } });
      expect(JSON.parse(await readFile(file, "utf8"))).toEqual(receipt);
      expect(await readdir(join(root, ".atlas/temp"))).toEqual(["check.json"]);
      await mkdir(join(root, "nested/.atlas/temp"), { recursive: true });
      const nested = join(root, "nested/.atlas/temp/check.json");
      expect(await exportReceipt(receipt, nested, [root])).toEqual(receipt);
      expect(JSON.parse(await readFile(nested, "utf8"))).toEqual(receipt);
    } finally { await rm(root, { recursive: true, force: true }); }
  });

  test("rejects workspace evidence paths, symlink parents, dangling destinations and oversized receipts", async () => {
    const root = await mkdtemp(join(tmpdir(), "atlas-export-"));
    const outside = await mkdtemp(join(tmpdir(), "atlas-export-outside-"));
    try {
      await mkdir(join(root, ".atlas/temp"), { recursive: true });
      await symlink(outside, join(root, ".atlas/temp/escape"), "junction");
      await symlink(join(outside, "not-created.json"), join(root, ".atlas/temp/dangling.json"));
      for (const file of [join(root, ".atlas/session.json"), join(outside, "receipt.json"),
        join(root, ".atlas/temp/escape/receipt.json"), join(root, ".atlas/temp/dangling.json")]) {
        expect(await exportReceipt({ status: "staged" }, file, [root])).toMatchObject({ status: "staged", receipt_export: { status: "failed" } });
      }
      expect(await exportReceipt({ data: "x".repeat(33 * 1024) }, join(root, ".atlas/temp/large.json"), [root])).toHaveProperty("receipt_export");
      expect(await readdir(outside)).toEqual([]);
    } finally { await rm(root, { recursive: true, force: true }); await rm(outside, { recursive: true, force: true }); }
  });
});
