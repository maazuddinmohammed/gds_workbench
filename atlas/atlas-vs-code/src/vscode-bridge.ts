import * as vscode from "vscode";
import { realpath } from "node:fs/promises";
import { discoverMicrosoftResource, StageAuthenticationError } from "./auth.js";
import { createStageMcpClient } from "./mcp-client.js";
import { resolveStageProfile } from "./profile.js";
import { failureReceipt } from "./receipt.js";
import { StageRunnerError } from "./stage-runner.js";
import { startBridge } from "./connector/bridge.js";
import { checkConnector, createConnectorServer } from "./connector/server.js";

// Only an explicit VS Code command can authorize the bridge and open sign-in.
// Background Codex requests use silent sessions pinned to that account.
export function registerCodexBridge(context: vscode.ExtensionContext) {
  let active = false, starting = false, epoch = 0;
  let selectedAccount: string | undefined;
  let scopes: string[] = [];
  const bridges: Awaited<ReturnType<typeof startBridge>>[] = [];
  const clients = new Set<Awaited<ReturnType<typeof createStageMcpClient>>>();
  const stop = async () => {
    active = false; epoch++;
    await Promise.all(bridges.splice(0).map(bridge => bridge.close()));
    await Promise.all([...clients].map(client => client.close().catch(() => undefined)));
    clients.clear(); selectedAccount = undefined;
  };
  const start = async () => {
    if (starting) return { status: "failed", code: "BRIDGE_BUSY" };
    starting = true;
    try {
      await stop();
      const generation = epoch;
      if (!vscode.workspace.isTrusted) throw new StageRunnerError("WORKSPACE_UNTRUSTED", "Trust the working folder before starting the Codex bridge.");
      if (vscode.env.remoteName) throw new StageRunnerError("BRIDGE_LOCAL_ONLY", "Open a local VS Code window on the same computer as Codex.");
      const folders = vscode.workspace.workspaceFolders ?? [];
      if (!folders.length) throw new StageRunnerError("WORKSPACE_REQUIRED", "Open the same working folder used by Codex.");
      const roots = new Map(await Promise.all(folders.map(async folder =>
        [await realpath(folder.uri.fsPath), folder.uri.fsPath] as const)));
      const configuration = vscode.workspace.getConfiguration("atlas.stageRunner");
      const profile = resolveStageProfile(configuration.get("profile", "production"), configuration.get("localUrl", "http://127.0.0.1:8000/mcp"));
      if (profile.name === "azureLocalTest") throw new StageRunnerError("PROFILE_INVALID", "The Codex bridge requires authenticated production or a disposable loopback test.");
      if (profile.authentication === "microsoft") {
        const resource = await discoverMicrosoftResource(profile.endpoint);
        scopes = [resource.scope, `VSCODE_TENANT:${resource.tenantId}`];
        const session = await vscode.authentication.getSession("microsoft", scopes, { createIfNone: true });
        selectedAccount = session.account.id;
      }
      if (generation !== epoch) throw new StageRunnerError("BRIDGE_CLOSED", "Configuration changed. Start the bridge again.");
      active = true;
      const tokenSupplier = profile.authentication === "microsoft" ? async (_refresh: boolean) => {
        if (!active || generation !== epoch) throw new StageAuthenticationError("AUTHENTICATION_REQUIRED", "Restart Atlas: Start Codex Bridge in VS Code to renew sign-in.");
        // VS Code can silently renew an expired token. Even after a backend 401,
        // never use forceNewSession or open a sign-in prompt from a Codex request.
        const session = await vscode.authentication.getSession("microsoft", scopes, { silent: true });
        if (!session || session.account.id !== selectedAccount) {
          active = false;
          throw new StageAuthenticationError("ACCOUNT_CHANGED", "Atlas sign-in changed. Restart the bridge in VS Code and use the same account for existing drafts.");
        }
        return session.accessToken;
      } : undefined;
      const check = await createStageMcpClient(profile, tokenSupplier);
      try { await checkConnector(check, profile); } finally { await check.close().catch(() => undefined); }
      if (!active || generation !== epoch) throw new StageRunnerError("BRIDGE_CLOSED", "Atlas setup changed while starting. Start the bridge again.");
      for (const root of roots.values()) {
        const bridge = await startBridge(root, async transport => {
          if (!active || generation !== epoch || !vscode.workspace.isTrusted) throw new Error("bridge closed");
          const client = await createStageMcpClient(profile, tokenSupplier);
          clients.add(client);
          const server = createConnectorServer(client, profile, root, () => active && generation === epoch && vscode.workspace.isTrusted);
          server.onclose = () => { clients.delete(client); void client.close().catch(() => undefined); };
          try { await server.connect(transport); }
          catch { clients.delete(client); await client.close().catch(() => undefined); throw new Error("bridge unavailable"); }
        });
        if (!active || generation !== epoch) { await bridge.close(); throw new StageRunnerError("BRIDGE_CLOSED", "Configuration changed. Start the bridge again."); }
        bridges.push(bridge);
      }
      void vscode.window.showInformationMessage("Atlas Codex Bridge is ready. Keep this VS Code window open and start Codex in the same working folder.");
      return { status: "ready" };
    } catch (error) {
      await stop();
      const receipt = failureReceipt(error, false);
      void vscode.window.showErrorMessage(`Atlas Codex Bridge: ${receipt.code}. ${receipt.message}`);
      return receipt;
    } finally { starting = false; }
  };
  context.subscriptions.push(
    vscode.commands.registerCommand("atlasBridge.start", start),
    vscode.commands.registerCommand("atlasBridge.stop", stop),
    vscode.workspace.onDidChangeWorkspaceFolders(() => { void stop(); }),
    vscode.workspace.onDidChangeConfiguration(event => { if (event.affectsConfiguration("atlas.stageRunner")) void stop(); }),
    vscode.authentication.onDidChangeSessions(event => {
      if (active && selectedAccount && event.provider.id === "microsoft") {
        void vscode.authentication.getSession("microsoft", scopes, { silent: true }).then(session => {
          if (!session || session.account.id !== selectedAccount) void stop();
        }, () => { void stop(); });
      }
    }),
    { dispose: () => { void stop(); } },
  );
  return stop;
}
