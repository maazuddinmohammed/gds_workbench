import { createHash } from "node:crypto";
import * as vscode from "vscode";

import {
  acquireMicrosoftAccessToken,
  type MicrosoftSessionGetter,
} from "./auth.js";
import { createStageMcpClient } from "./mcp-client.js";
import { resolveStageProfile } from "./profile.js";
import { exportReceipt, failureReceipt } from "./receipt.js";
import {
  stageApprovedManifest,
  StageRunnerError,
  type StageApprovedManifestInput,
} from "./stage-runner.js";

const TOOL_NAME = "atlas_stageApprovedManifest";
interface CheckInput { outputFile?: string }

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
  const configuration = vscode.workspace.getConfiguration("atlas.stageRunner");
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
  prepareInvocation(options: vscode.LanguageModelToolInvocationPrepareOptions<StageApprovedManifestInput>): vscode.PreparedToolInvocation {
    if (options.input.recoverOnly === true) return { invocationMessage: "Verifying the uncertain Atlas Stage against the server draft…" };
    return {
      invocationMessage: "Staging the approved Atlas Change Set…",
      confirmationMessages: {
        title: "Stage approved Atlas Change Set",
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
    let receipt: Awaited<ReturnType<typeof stageApprovedManifest>> | ReturnType<typeof failureReceipt>;
    let mcp: Awaited<ReturnType<typeof createStageMcpClient>> | undefined;
    try {
      if (!vscode.workspace.isTrusted) {
        throw new StageRunnerError(
          "WORKSPACE_UNTRUSTED",
          "Trust the Atlas workspace before Stage.",
        );
      }
      if (token.isCancellationRequested) {
        throw new StageRunnerError("CANCELLED", "Stage was cancelled before it started.");
      }
      const roots = workspaceRoots();
      if (roots.length === 0) {
        throw new StageRunnerError("INVALID_INPUT", "Open the Atlas workspace before Stage.");
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
      receipt = await stageApprovedManifest(options.input, {
        mcp,
        workspaceRoots: roots,
        backend: { profile: profile.name, endpoint_sha256: createHash("sha256").update(profile.endpoint.href).digest("hex") },
        isCancellationRequested: () => token.isCancellationRequested,
        onWriteStart: () => {
          stageStarted = true;
        },
      });
    } catch (error) {
      receipt = failureReceipt(error, stageStarted);
    } finally {
      // Cleanup cannot replace the authoritative Stage receipt or trigger a retry.
      await mcp?.close().catch(() => undefined);
    }
    return new vscode.LanguageModelToolResult([new vscode.LanguageModelTextPart(JSON.stringify(
      await exportReceipt(receipt, options.input?.outputFile, vscode.workspace.isTrusted ? workspaceRoots() : []),
    ))]);
  }
}

async function checkStageRunner(input: CheckInput = {}, token?: vscode.CancellationToken) {
  let mcp: Awaited<ReturnType<typeof createStageMcpClient>> | undefined;
  let receipt: { schema_version: "1.0"; status: "ready"; backend: { profile: string; endpoint_sha256: string } } | ReturnType<typeof failureReceipt>;
  try {
    if (!vscode.workspace.isTrusted) throw new StageRunnerError("WORKSPACE_UNTRUSTED", "Trust the Atlas workspace before checking Stage Runner.");
    if (!workspaceRoots().length) throw new StageRunnerError("INVALID_INPUT", "Open the Atlas workspace before checking Stage Runner.");
    if (token?.isCancellationRequested) throw new StageRunnerError("CANCELLED", "Stage Runner check was cancelled.");
    if (input === null || typeof input !== "object" || Array.isArray(input) ||
        Object.keys(input).some(key => key !== "outputFile") ||
        (input.outputFile !== undefined && typeof input.outputFile !== "string")) {
      throw new StageRunnerError("INVALID_INPUT", "Stage Runner check input is invalid.");
    }
    const profile = configuredProfile();
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
    const identity = { profile: profile.name, endpoint_sha256: createHash("sha256").update(endpoint.href).digest("hex") };
    receipt = { schema_version: "1.0", status: "ready", backend: identity };
  } catch (error) {
    receipt = failureReceipt(error, false);
  } finally {
    // Cleanup cannot replace a readiness or failure result.
    await mcp?.close().catch(() => undefined);
  }
  return exportReceipt(receipt, input?.outputFile, vscode.workspace.isTrusted ? workspaceRoots() : []);
}

class CheckStageRunnerTool implements vscode.LanguageModelTool<CheckInput> {
  prepareInvocation(): vscode.PreparedToolInvocation {
    return { invocationMessage: "Checking Atlas Stage Runner readiness…" };
  }
  async invoke(options: vscode.LanguageModelToolInvocationOptions<CheckInput>, token: vscode.CancellationToken) {
    return new vscode.LanguageModelToolResult([new vscode.LanguageModelTextPart(
      JSON.stringify(await checkStageRunner(options.input, token)),
    )]);
  }
}

export function activate(context: vscode.ExtensionContext): void {
  context.subscriptions.push(
    vscode.lm.registerTool(TOOL_NAME, new StageApprovedManifestTool()),
    vscode.lm.registerTool("atlas_checkStageRunner", new CheckStageRunnerTool()),
    vscode.commands.registerCommand("atlasStageRunner.check", async () => {
      const receipt = await checkStageRunner();
      if (receipt.status === "ready") {
        await vscode.window.showInformationMessage(`Atlas Stage Runner is ready (${receipt.backend.profile}). Backend: ${receipt.backend.endpoint_sha256}`);
      } else {
        await vscode.window.showErrorMessage(`Atlas Stage Runner: ${receipt.code}. ${receipt.message}`);
      }
      return receipt;
    }),
  );
}

export function deactivate(): void {}
