import { createHash } from "node:crypto";
import { Server } from "@modelcontextprotocol/sdk/server/index.js";
import { CallToolRequestSchema, ListToolsRequestSchema, type Tool } from "@modelcontextprotocol/sdk/types.js";
import type { ResolvedStageProfile } from "../profile.js";
import { exportReceipt, failureReceipt } from "../receipt.js";
import { stageApprovedManifest, StageRunnerError, type McpToolClient, type StageApprovedManifestInput } from "../stage-runner.js";

// Review new backend tools before making them available. Payload transport is private
// to Stage Runner; models cannot call begin/put/commit or direct Stage through this proxy.
export const REMOTE_TOOLS = new Set([
  "list_tenants", "get_tenant_details", "list_models", "get_model_input_scope",
  "check_tenant_lock", "acquire_tenant_lock", "renew_tenant_lock", "release_tenant_lock", "override_tenant_lock",
  "create_metadata_change_set", "get_metadata_change_set", "get_metadata_change_set_fingerprint",
  "validate_metadata_change_set", "apply_metadata_change_set", "archive_metadata_change_set",
  "create_model_change_set", "get_model_change_set", "get_model_change_set_fingerprint",
  "validate_model_change_set", "apply_model_change_set", "archive_model_change_set",
  "start_profiling_run", "get_profiling_run_status", "cancel_profiling_run",
  "inspect_metadata", "read_model_section", "read_mapping_context", "execute_databricks_sql",
  "describe_model_dataset", "create_model_snapshot", "describe_metadata_dataset", "create_metadata_snapshot",
]);

export const LOCAL_TOOLS: Tool[] = [
  { name: "atlas_checkStageRunner", description: "Read-only Atlas readiness check. Exports a small receipt if requested. If disconnected or sign-in is required, run Atlas: Start Codex Bridge in VS Code.",
    annotations: { readOnlyHint: true, openWorldHint: true },
    inputSchema: { type: "object", additionalProperties: false, properties: {
      outputFile: { type: "string", description: "New absolute .json path in the current workspace .atlas/temp directory." },
    } } },
  { name: "atlas_stageApprovedManifest", description: "Stage the exact local Atlas manifest after user acknowledgement and local Accept. Read files directly; return only a receipt. Never Apply. Use recoverOnly after an uncertain Stage; do not replay writes.",
    annotations: { readOnlyHint: false, destructiveHint: true, idempotentHint: false, openWorldHint: true },
    inputSchema: { type: "object", additionalProperties: false, required: ["manifestPath"], properties: {
      manifestPath: { type: "string", description: "Absolute stage_manifest_path from Atlas prepare-stage-request." },
      expectedDigest: { type: "string", pattern: "^[0-9a-f]{64}$" },
      recoverOnly: { type: "boolean" }, outputFile: { type: "string" },
    } } },
];

export interface ConnectorClient extends McpToolClient { listTools(): Promise<Tool[]> }

export async function checkConnector(mcp: McpToolClient, profile: ResolvedStageProfile) {
  const result = await mcp.callTool("list_tenants", { page_size: 1 });
  if (result === null || typeof result !== "object" || !Array.isArray((result as Record<string, unknown>).tenants)) {
    throw new StageRunnerError("MCP_RESPONSE_INVALID", "Atlas check returned no tenant list.");
  }
  return { schema_version: "1.0", status: "ready", backend: {
    profile: profile.name, endpoint_sha256: createHash("sha256").update(profile.endpoint.href).digest("hex"),
  } };
}

export function createConnectorServer(mcp: ConnectorClient, profile: ResolvedStageProfile, workspaceRoot: string, isAllowed: () => boolean = () => true) {
  const server = new Server({ name: "atlas-vscode-bridge", version: "0.2.0" }, { capabilities: { tools: {} } });
  const roots = [workspaceRoot];
  let catalog: Tool[] = [];
  let busy = false;
  server.setRequestHandler(ListToolsRequestSchema, async () => {
    if (!isAllowed()) return { tools: [] };
    if (!busy) {
      busy = true;
      try { catalog = (await mcp.listTools()).filter(tool => REMOTE_TOOLS.has(tool.name)); }
      catch { catalog = []; } // Keep Check visible so the user can obtain a safe recovery instruction.
      finally { busy = false; }
    }
    return { tools: [...LOCAL_TOOLS, ...catalog] };
  });
  server.setRequestHandler(CallToolRequestSchema, async (request, extra) => {
    let stageStarted = false;
    if (busy) return result(failureReceipt(new StageRunnerError("CONNECTOR_BUSY", "Wait for the current Atlas operation to finish."), false), true);
    busy = true;
    try {
      const { name, arguments: input = {} } = request.params;
      if (!isAllowed()) throw new StageRunnerError("BRIDGE_CLOSED", "Restart Atlas: Start Codex Bridge in the trusted VS Code working folder.");
      if (extra.signal.aborted) throw new StageRunnerError("CANCELLED", "Atlas operation was cancelled.");
      if (name === "atlas_checkStageRunner") {
        if (Object.keys(input).some(key => key !== "outputFile") ||
            (input.outputFile !== undefined && typeof input.outputFile !== "string")) {
          throw new StageRunnerError("INVALID_INPUT", "Atlas check input is invalid.");
        }
        const receipt = await checkConnector(mcp, profile);
        return result(await exportReceipt(receipt, input.outputFile, roots));
      }
      if (name === "atlas_stageApprovedManifest") {
        // The engine enforces containment, exact approved bytes, backend binding,
        // owners, locks, revision fencing, cancellation and uncertain-write recovery.
        const receipt = await stageApprovedManifest(input as unknown as StageApprovedManifestInput, {
          mcp, workspaceRoots: roots,
          backend: { profile: profile.name, endpoint_sha256: createHash("sha256").update(profile.endpoint.href).digest("hex") },
          isCancellationRequested: () => extra.signal.aborted || !isAllowed(),
          onWriteStart: () => { stageStarted = true; },
        });
        return result(await exportReceipt(receipt, input.outputFile, roots));
      }
      if (!REMOTE_TOOLS.has(name) || !catalog.some(tool => tool.name === name)) {
        throw new StageRunnerError("TOOL_NOT_AVAILABLE", "This Atlas tool is not available. Use the approved Stage Runner for file transfer.");
      }
      const value = await mcp.callTool(name, input);
      if (!value || typeof value !== "object" || Array.isArray(value)) throw new StageRunnerError("MCP_RESPONSE_INVALID", "Atlas returned an invalid result.");
      return result(value);
    } catch (error) {
      const receipt = { ...failureReceipt(error, stageStarted), legacy_fallback_allowed: false };
      return result(await exportReceipt(receipt, request.params.arguments?.outputFile,
        isAllowed() && request.params.name.startsWith("atlas_") ? roots : []), true);
    } finally { busy = false; }
  });
  return server;
}

function result(value: object, isError = false) {
  return { isError, structuredContent: value as Record<string, unknown>,
    content: [{ type: "text" as const, text: JSON.stringify(value) }] };
}
