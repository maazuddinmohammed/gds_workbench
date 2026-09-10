import type * as Vscode from "vscode";
import { afterEach, beforeEach, describe, expect, test, vi } from "vitest";
import type { StageRunnerDependencies } from "../src/stage-runner.js";
import { PRODUCTION_MCP_URL } from "../src/profile.js";

const mocks = vi.hoisted(() => ({
  registerTool: vi.fn(), registerCommand: vi.fn(),
  createClient: vi.fn(), stage: vi.fn(), close: vi.fn(),
  callTool: vi.fn(), information: vi.fn(), error: vi.fn(),
  getSession: vi.fn(), profile: "local",
  workspace: { isTrusted: true, workspaceFolders: [{ uri: { fsPath: "/workspace" } }] },
}));
vi.mock("vscode", () => ({
  workspace: {
    get isTrusted() { return mocks.workspace.isTrusted; },
    get workspaceFolders() { return mocks.workspace.workspaceFolders; },
    getConfiguration: () => ({ get: (key: string, fallback: unknown) => key === "profile" ? mocks.profile : fallback }),
  },
  authentication: { getSession: mocks.getSession },
  lm: { registerTool: mocks.registerTool },
  commands: { registerCommand: mocks.registerCommand },
  window: { showInformationMessage: mocks.information, showErrorMessage: mocks.error },
  LanguageModelDataPart: { json: (value: unknown) => value },
  LanguageModelToolResult: class { constructor(public content: unknown[]) {} },
}));
vi.mock("../src/mcp-client.js", async (original) => ({
  ...await original<typeof import("../src/mcp-client.js")>(),
  createStageMcpClient: mocks.createClient,
}));
vi.mock("../src/stage-runner.js", async (original) => ({
  ...await original<typeof import("../src/stage-runner.js")>(),
  stageApprovedManifest: mocks.stage,
}));

import { activate } from "../src/extension.js";
import { StageMcpError } from "../src/mcp-client.js";

beforeEach(() => {
  vi.resetAllMocks();
  mocks.profile = "local";
  mocks.workspace.isTrusted = true;
  mocks.workspace.workspaceFolders = [{ uri: { fsPath: "/workspace" } }];
  mocks.createClient.mockResolvedValue({ callTool: mocks.callTool, close: mocks.close });
  mocks.close.mockResolvedValue(undefined);
});

afterEach(() => vi.unstubAllGlobals());

function activatedTool() {
  const subscriptions: Vscode.Disposable[] = [];
  activate({ subscriptions } as Vscode.ExtensionContext);
  expect(mocks.registerTool.mock.calls[0]?.[0]).toBe("gds_stageApprovedManifest");
  expect(mocks.registerCommand.mock.calls[0]?.[0]).toBe("gdsStageRunner.check");
  expect(subscriptions).toHaveLength(2);
  return mocks.registerTool.mock.calls[0]![1] as Vscode.LanguageModelTool<object>;
}

const input = { manifestPath: "/workspace/tasks/01.stage-request.json", expectedDigest: "0".repeat(64) };
const token = (cancelled = false) => ({ isCancellationRequested: cancelled }) as Vscode.CancellationToken;

describe("VS Code tool boundary", () => {
  test.each(["check", "stage"])("production %s uses normal Microsoft sign-in instead of a claimless challenge", async (operation) => {
    const tenant = "11111111-1111-4111-8111-111111111111";
    mocks.profile = "production";
    vi.stubGlobal("fetch", vi.fn(async () => new Response(JSON.stringify({
      resource: PRODUCTION_MCP_URL,
      authorization_servers: [`https://login.microsoftonline.com/${tenant}/v2.0`],
      scopes_supported: [`${PRODUCTION_MCP_URL}/workbench.access`],
      bearer_methods_supported: ["header"],
    }))));
    mocks.getSession.mockImplementation(async (_provider, scopes: unknown) => {
      // Microsoft's getSessionsFromChallenges rejects missing claims before VS Code can prompt.
      if (!Array.isArray(scopes)) throw new Error("No claims found in authentication challenges");
      return { accessToken: "fixture-session" };
    });
    mocks.createClient.mockImplementation(async (_profile, tokenSupplier) => {
      await tokenSupplier(false);
      return { callTool: mocks.callTool, close: mocks.close };
    });
    mocks.callTool.mockResolvedValue({ tenants: [] });
    mocks.stage.mockResolvedValue({ status: "staged", fingerprintVerified: true });
    const tool = activatedTool();

    if (operation === "check") {
      await mocks.registerCommand.mock.calls[0]![1]();
      expect(mocks.error).not.toHaveBeenCalled();
      expect(mocks.information).toHaveBeenCalledWith("GDS Stage Runner is ready (production).");
    } else {
      const result = await tool.invoke({ input, toolInvocationToken: undefined }, token());
      expect(result?.content[0]).toMatchObject({ status: "staged" });
    }
    expect(mocks.getSession).toHaveBeenCalledWith(
      "microsoft",
      [`${PRODUCTION_MCP_URL}/workbench.access`, `VSCODE_TENANT:${tenant}`],
      { createIfNone: { detail: "Sign in with the Microsoft account authorized for GDS Workbench." } },
    );
  });

  test.each(["untrusted", "cancelled", "no workspace"])("rejects %s before connecting", async (reason) => {
    if (reason === "untrusted") mocks.workspace.isTrusted = false;
    if (reason === "no workspace") mocks.workspace.workspaceFolders = [];
    const result = await activatedTool().invoke({ input, toolInvocationToken: undefined }, token(reason === "cancelled"));
    expect(result?.content[0]).toMatchObject({ status: "failed", stageStarted: false });
    expect(mocks.createClient).not.toHaveBeenCalled();
    expect(mocks.stage).not.toHaveBeenCalled();
  });

  test.each([false, true])("allows fallback only before a possible write (started=%s)", async (started) => {
    mocks.stage.mockImplementation(async (_input, dependencies: StageRunnerDependencies) => {
      if (started) dependencies.onWriteStart?.();
      throw new StageMcpError("MCP_OUTCOME_UNKNOWN", "Verify before retrying.");
    });
    const result = await activatedTool().invoke({ input, toolInvocationToken: undefined }, token());
    expect(result?.content[0]).toMatchObject({
      status: "failed", stageStarted: started, legacyFallbackAllowed: !started,
    });
    expect(mocks.stage).toHaveBeenCalledOnce();
    expect(mocks.close).toHaveBeenCalledOnce();
  });

  test("returns only the receipt and closes the connection after success", async () => {
    const receipt = { status: "staged", fingerprintVerified: true };
    mocks.stage.mockResolvedValue(receipt);
    const result = await activatedTool().invoke({ input, toolInvocationToken: undefined }, token());
    expect(result?.content).toEqual([receipt]);
    expect(mocks.close).toHaveBeenCalledOnce();
  });

  test.each([false, true])("preserves the Stage receipt when cleanup fails (staged=%s)", async (staged) => {
    mocks.close.mockRejectedValue(new Error("private cleanup detail"));
    if (staged) mocks.stage.mockResolvedValue({ status: "staged", fingerprintVerified: true });
    else mocks.stage.mockRejectedValue(new StageMcpError("MCP_OUTCOME_UNKNOWN", "Verify before retrying."));

    const result = await activatedTool().invoke({ input, toolInvocationToken: undefined }, token());

    expect(result?.content[0]).toMatchObject({ status: staged ? "staged" : "failed" });
    expect(JSON.stringify(result)).not.toContain("private cleanup detail");
    expect(mocks.close).toHaveBeenCalledOnce();
  });

  test("connection-check cleanup cannot turn confirmed readiness into an exception", async () => {
    mocks.callTool.mockResolvedValue({ tenants: [] });
    mocks.close.mockRejectedValue(new Error("private cleanup detail"));
    activatedTool();

    await expect(mocks.registerCommand.mock.calls[0]![1]()).resolves.toBeUndefined();

    expect(mocks.information).toHaveBeenCalledOnce();
    expect(mocks.error).not.toHaveBeenCalled();
  });

  test("the connection check redacts unexpected failures and closes the connection", async () => {
    mocks.callTool.mockRejectedValue(new Error("private test detail"));
    activatedTool();
    await mocks.registerCommand.mock.calls[0]![1]();
    expect(mocks.information).not.toHaveBeenCalled();
    expect(mocks.error).toHaveBeenCalledWith(expect.stringContaining("INTERNAL_ERROR"));
    expect(mocks.error.mock.calls.flat().join()).not.toContain("private test detail");
    expect(mocks.close).toHaveBeenCalledOnce();
  });

  test("the connection check includes its selected profile and safe network diagnosis", async () => {
    mocks.callTool.mockRejectedValue(new StageMcpError("MCP_DNS_FAILED", "GDS MCP DNS lookup failed."));
    activatedTool();
    await mocks.registerCommand.mock.calls[0]![1]();

    expect(mocks.error).toHaveBeenCalledWith(
      "GDS Stage Runner (local): MCP_DNS_FAILED. GDS MCP DNS lookup failed.",
    );
    expect(mocks.close).toHaveBeenCalledOnce();
  });
});
