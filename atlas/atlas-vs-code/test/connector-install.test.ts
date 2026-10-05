import { createRequire } from "node:module";
import { join, resolve } from "node:path";
import { expect, test, vi } from "vitest";

const require = createRequire(import.meta.url);
const { installConnector } = require("../../atlas-connector/install.cjs") as {
  installConnector: (installation: string, args: string[], run: ReturnType<typeof vi.fn>, platform: string, npm: string) => void;
};

test.each(["darwin", "win32"])("one command sets up, registers and checks in order on %s", platform => {
  const run = vi.fn().mockReturnValue({ status: 0 });
  const installation = resolve("Atlas with spaces/atlas-connector");
  installConnector(installation, ["--plugin", "fixture-plugin"], run, platform, "/fixture/npm-cli.js");
  expect(run.mock.calls).toHaveLength(3);
  expect(run.mock.calls[0]![1]).toEqual([join(installation, "atlas-connector.cjs"), "setup", "--plugin", "fixture-plugin"]);
  expect(run.mock.calls[1]![0]).toBe(platform === "win32" ? "cmd.exe" : "codex");
  expect(run.mock.calls[1]![1]).toEqual(platform === "win32" ? ["/d", "/s", "/c", "codex plugin marketplace add ."] : ["plugin", "marketplace", "add", "."]);
  expect(run.mock.calls[1]![2].cwd).toBe(resolve(installation, "..", "codex-atlas"));
  expect(JSON.stringify(run.mock.calls)).not.toContain("npm-cli");
});

test("a failed setup stops before dependencies, registration, or sign-in; raw command output is hidden", () => {
  const run = vi.fn().mockReturnValue({ status: 1, stderr: "fixture private command output" });
  expect(() => installConnector("/fixture", [], run, "darwin", "/fixture/npm-cli.js")).toThrow("Preparing Atlas files failed");
  expect(run).toHaveBeenCalledTimes(1);
});
