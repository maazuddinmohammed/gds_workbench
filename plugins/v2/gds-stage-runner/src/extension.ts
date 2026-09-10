import * as vscode from "vscode";

import {
  acquireMicrosoftAccessToken,
  type MicrosoftSessionGetter,
} from "./auth.js";
import { createStageMcpClient } from "./mcp-client.js";
import { resolveStageProfile } from "./profile.js";
import { failureReceipt } from "./receipt.js";
import {
  stageApprovedManifest,
  StageRunnerError,
  type StageApprovedManifestInput,
} from "./stage-runner.js";

const TOOL_NAME = "gds_stageApprovedManifest";

const getMicrosoftSession: MicrosoftSessionGetter = async (
  providerId,
  scopes,
  options,
) => {
  if (options.forceNewSession !== undefined) {
    return vscode.authentication.getSession(providerId, scopes, {
      forceNewSession: options.forceNewSession,
    });
  }
  return vscode.authentication.getSession(providerId, scopes, {
    createIfNone: options.createIfNone ?? true,
  });
};

function configuredProfile() {
  const configuration = vscode.workspace.getConfiguration("gds.stageRunner");
  return resolveStageProfile(
    configuration.get<string>("profile", "production"),
    configuration.get<string>("localUrl", "http://127.0.0.1:8000/mcp"),
  );
}

function workspaceRoots(): string[] {
  return (vscode.workspace.workspaceFolders ?? []).map((folder) => folder.uri.fsPath);
}

class StageApprovedManifestTool
  implements vscode.LanguageModelTool<StageApprovedManifestInput>
{
  prepareInvocation(): vscode.PreparedToolInvocation {
    return {
      invocationMessage: "Staging the approved GDS Change Set…",
      confirmationMessages: {
        title: "Stage approved GDS Change Set",
        message:
          "This replaces pending GDS data from the exact acknowledged local digest. " +
          "It does not Apply the Change Set.",
      },
    };
  }

  async invoke(
    options: vscode.LanguageModelToolInvocationOptions<StageApprovedManifestInput>,
    token: vscode.CancellationToken,
  ): Promise<vscode.LanguageModelToolResult> {
    let stageStarted = false;
    let mcp: Awaited<ReturnType<typeof createStageMcpClient>> | undefined;
    try {
      if (!vscode.workspace.isTrusted) {
        throw new StageRunnerError(
          "WORKSPACE_UNTRUSTED",
          "Trust the GDS workspace before Stage.",
        );
      }
      if (token.isCancellationRequested) {
        throw new StageRunnerError("CANCELLED", "Stage was cancelled before it started.");
      }
      const roots = workspaceRoots();
      if (roots.length === 0) {
        throw new StageRunnerError("INVALID_INPUT", "Open the GDS workspace before Stage.");
      }
      const profile = configuredProfile();
      const tokenSupplier =
        profile.authentication === "microsoft"
          ? (forceNewSession: boolean) =>
              acquireMicrosoftAccessToken(
                profile.endpoint,
                getMicrosoftSession,
                fetch,
                forceNewSession,
              )
          : undefined;
      mcp = await createStageMcpClient(profile, tokenSupplier);
      const receipt = await stageApprovedManifest(options.input, {
        mcp,
        workspaceRoots: roots,
        isCancellationRequested: () => token.isCancellationRequested,
        onWriteStart: () => {
          stageStarted = true;
        },
      });
      return new vscode.LanguageModelToolResult([
        vscode.LanguageModelDataPart.json(receipt),
      ]);
    } catch (error) {
      return new vscode.LanguageModelToolResult([
        vscode.LanguageModelDataPart.json(failureReceipt(error, stageStarted)),
      ]);
    } finally {
      // Cleanup cannot replace the authoritative Stage receipt or trigger a retry.
      await mcp?.close().catch(() => undefined);
    }
  }
}

async function checkStageRunner(): Promise<void> {
  let mcp: Awaited<ReturnType<typeof createStageMcpClient>> | undefined;
  let profile: ReturnType<typeof configuredProfile> | undefined;
  try {
    profile = configuredProfile();
    const endpoint = profile.endpoint;
    const tokenSupplier =
      profile.authentication === "microsoft"
        ? (forceNewSession: boolean) =>
            acquireMicrosoftAccessToken(
              endpoint,
              getMicrosoftSession,
              fetch,
              forceNewSession,
            )
        : undefined;
    mcp = await createStageMcpClient(profile, tokenSupplier);
    const result = await mcp.callTool("list_tenants", { page_size: 1 });
    if (
      result === null ||
      typeof result !== "object" ||
      !Array.isArray((result as Record<string, unknown>).tenants)
    ) {
      throw new StageRunnerError("MCP_RESPONSE_INVALID", "GDS MCP check returned no tenant list.");
    }
    await vscode.window.showInformationMessage(
      `GDS Stage Runner is ready (${profile.name}).`,
    );
  } catch (error) {
    const receipt = failureReceipt(error, false);
    await vscode.window.showErrorMessage(
      `GDS Stage Runner${profile === undefined ? "" : ` (${profile.name})`}: ${receipt.code}. ${receipt.message}`,
    );
  } finally {
    // The connection check has already reported its result.
    await mcp?.close().catch(() => undefined);
  }
}

export function activate(context: vscode.ExtensionContext): void {
  context.subscriptions.push(
    vscode.lm.registerTool(TOOL_NAME, new StageApprovedManifestTool()),
    vscode.commands.registerCommand("gdsStageRunner.check", checkStageRunner),
  );
}

export function deactivate(): void {}
