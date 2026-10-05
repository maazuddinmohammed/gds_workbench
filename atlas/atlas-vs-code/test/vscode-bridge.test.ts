import type * as Vscode from "vscode";
import { beforeEach, expect, test, vi } from "vitest";
const f = vi.hoisted(() => ({
  commands: new Map<string, (...args: never[]) => unknown>(),
  events: new Map<string, (...args: any[]) => void>(),
  trusted: true, remote: undefined as string | undefined, profile: "production", folders: ["/fixture"],
  session: vi.fn(), startBridge: vi.fn(), closeBridge: vi.fn(), createClient: vi.fn(), closeClient: vi.fn(),
  connect: vi.fn(), server: vi.fn(), info: vi.fn(), error: vi.fn(),
}));
vi.mock("node:fs/promises", () => ({ realpath: async (path: string) => path }));
vi.mock("vscode", () => ({
  env: { get remoteName() { return f.remote; } },
  commands: { registerCommand: (name: string, action: (...args: never[]) => unknown) => { f.commands.set(name, action); return {}; } },
  workspace: {
    get isTrusted() { return f.trusted; }, get workspaceFolders() { return f.folders.map(fsPath => ({ uri: { fsPath } })); },
    getConfiguration: () => ({ get: (key: string, fallback: string) => key === "profile" ? f.profile : fallback }),
    onDidChangeWorkspaceFolders: (fn: () => void) => { f.events.set("folders", fn); return {}; },
    onDidChangeConfiguration: (fn: () => void) => { f.events.set("config", fn); return {}; },
  },
  authentication: { getSession: f.session, onDidChangeSessions: (fn: () => void) => { f.events.set("session", fn); return {}; } },
  window: { showInformationMessage: f.info, showErrorMessage: f.error },
}));
vi.mock("../src/auth.js", async original => ({ ...await original<typeof import("../src/auth.js")>(),
  discoverMicrosoftResource: async () => ({ scope: "fixture.scope", tenantId: "fixture-tenant" }),
}));
vi.mock("../src/connector/bridge.js", () => ({ startBridge: f.startBridge }));
vi.mock("../src/mcp-client.js", async original => ({ ...await original<typeof import("../src/mcp-client.js")>(), createStageMcpClient: f.createClient }));
vi.mock("../src/connector/server.js", () => ({ checkConnector: async () => ({ status: "ready" }), createConnectorServer: f.server }));
import { registerCodexBridge } from "../src/vscode-bridge.js";
beforeEach(() => {
  vi.resetAllMocks(); f.commands.clear(); f.events.clear();
  f.trusted = true; f.remote = undefined; f.profile = "production"; f.folders = ["/fixture"];
  f.session.mockResolvedValue({ account: { id: "account-one" }, accessToken: "synthetic-private-token" });
  f.startBridge.mockResolvedValue({ close: f.closeBridge });
  f.createClient.mockResolvedValue({ close: f.closeClient });
  f.closeClient.mockResolvedValue(undefined); f.closeBridge.mockResolvedValue(undefined);
  f.server.mockReturnValue({ connect: f.connect });
  registerCodexBridge({ subscriptions: [] } as unknown as Vscode.ExtensionContext);
});

test("only the start command signs in; background requests are silent and pinned to one account", async () => {
  // VS Code notification promises resolve only when dismissed. Startup must not wait.
  f.info.mockReturnValue(new Promise(() => undefined));
  expect(f.session).not.toHaveBeenCalled();
  expect(await f.commands.get("atlasBridge.start")!()).toEqual({ status: "ready" });
  expect(f.session).toHaveBeenCalledWith("microsoft", ["fixture.scope", "VSCODE_TENANT:fixture-tenant"], { createIfNone: true });
  const supplier = f.createClient.mock.calls[0]![1];
  expect(await supplier(false)).toBe("synthetic-private-token");
  expect(f.session).toHaveBeenLastCalledWith("microsoft", expect.any(Array), { silent: true });
  f.session.mockResolvedValueOnce({ account: { id: "account-one" }, accessToken: "renewed-private-token" });
  expect(await supplier(true)).toBe("renewed-private-token");
  expect(f.session).toHaveBeenLastCalledWith("microsoft", expect.any(Array), { silent: true });
  expect(JSON.stringify([...f.info.mock.calls, ...f.error.mock.calls])).not.toContain("synthetic-private-token");
});

test("an account switch fails before a new backend connection can use another identity", async () => {
  await f.commands.get("atlasBridge.start")!();
  const supplier = f.createClient.mock.calls[0]![1];
  f.session.mockResolvedValue({ account: { id: "account-two" }, accessToken: "other-private-token" });
  await expect(supplier(false)).rejects.toMatchObject({ code: "ACCOUNT_CHANGED" });
});

test.each(["untrusted", "remote", "no workspace"])("rejects %s before authentication", async reason => {
  if (reason === "untrusted") f.trusted = false;
  if (reason === "remote") f.remote = "ssh";
  if (reason === "no workspace") f.folders = [];
  expect(await f.commands.get("atlasBridge.start")!()).toMatchObject({ status: "failed" });
  expect(f.session).not.toHaveBeenCalled(); expect(f.startBridge).not.toHaveBeenCalled();
});

test.each(["folders", "config", "session"])("stops the bridge after %s changes", async event => {
  await f.commands.get("atlasBridge.start")!();
  f.session.mockResolvedValue(undefined);
  f.events.get(event)!({ provider: { id: "microsoft" }, affectsConfiguration: () => true });
  await vi.waitFor(() => expect(f.closeBridge).toHaveBeenCalledOnce());
});

test("configuration changes during sign-in cannot publish a bridge", async () => {
  f.session.mockImplementation(async () => {
    f.events.get("config")!({ affectsConfiguration: () => true });
    return { account: { id: "account-one" }, accessToken: "synthetic" };
  });
  expect(await f.commands.get("atlasBridge.start")!()).toMatchObject({ status: "failed" });
  expect(f.startBridge).not.toHaveBeenCalled();
});
