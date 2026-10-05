import { mkdtemp, mkdir, readFile, writeFile } from "node:fs/promises";
import { tmpdir } from "node:os";
import { join } from "node:path";
import { Client } from "@modelcontextprotocol/sdk/client/index.js";
import { InMemoryTransport } from "@modelcontextprotocol/sdk/inMemory.js";
import { expect, test, vi } from "vitest";
import { createConnectorServer, REMOTE_TOOLS } from "../src/connector/server.js";
import { resolveStageProfile } from "../src/profile.js";
import { StageAuthenticationError } from "../src/auth.js";

async function connect() {
  const root = await mkdtemp(join(tmpdir(), "atlas-connector-"));
  await mkdir(join(root, ".atlas", "temp"), { recursive: true });
  const mcp = { callTool: vi.fn(async (_name: string, _input: Record<string, unknown>): Promise<unknown> => ({ tenants: [{ private_fixture: true }] })),
    listTools: vi.fn(async () => ["list_tenants", "apply_model_change_set", "stage_model_change_set", "arbitrary_sql"].map(name => ({
      name, inputSchema: { type: "object" as const },
    }))) };
  const server = createConnectorServer(mcp, resolveStageProfile("local", "http://127.0.0.1:8000/mcp"), root);
  const client = new Client({ name: "test", version: "1" });
  const [clientSide, serverSide] = InMemoryTransport.createLinkedPair();
  await server.connect(serverSide); await client.connect(clientSide); await client.listTools();
  return { client, mcp, root, close: async () => { await client.close(); await server.close(); } };
}

test("only reviewed remote tools and the two local tools are exposed", async () => {
  const f = await connect();
  try {
    const names = (await f.client.listTools()).tools.map(tool => tool.name);
    expect(names).toEqual(["atlas_checkStageRunner", "atlas_stageApprovedManifest", "list_tenants", "apply_model_change_set"]);
    expect([...REMOTE_TOOLS].some(name => /^(stage|begin|put|commit)_/.test(name))).toBe(false);
    const rejected = await f.client.callTool({ name: "stage_model_change_set", arguments: { records: [] } });
    expect(rejected.isError).toBe(true); expect(f.mcp.callTool).not.toHaveBeenCalled();
  } finally { await f.close(); }
});
test("check exports its bounded backend receipt without tenant records", async () => {
  const f = await connect();
  try {
    const outputFile = join(f.root, ".atlas", "temp", "check.json");
    const result = await f.client.callTool({ name: "atlas_checkStageRunner", arguments: { outputFile } });
    expect(result.structuredContent).toMatchObject({ status: "ready", backend: { profile: "local" } });
    expect(JSON.stringify(result)).not.toContain("private_fixture");
    expect(JSON.parse(await readFile(outputFile, "utf8"))).toEqual(result.structuredContent);
    expect((await f.client.callTool({ name: "atlas_checkStageRunner", arguments: { outputFile } })).structuredContent).toMatchObject({
      status: "ready", receipt_export: { status: "failed" },
    });
  } finally { await f.close(); }
});
test("a manifest outside the session folder fails before any remote request", async () => {
  const f = await connect();
  try {
    const outside = await mkdtemp(join(tmpdir(), "atlas-outside-")), manifestPath = join(outside, "manifest.json");
    await writeFile(manifestPath, "{}");
    const result = await f.client.callTool({ name: "atlas_stageApprovedManifest", arguments: { manifestPath } });
    expect(result.isError).toBe(true); expect(result.structuredContent).toMatchObject({ code: "WORKSPACE_BOUNDARY", stage_started: false });
    expect(f.mcp.callTool).not.toHaveBeenCalled();
  } finally { await f.close(); }
});
test("missing sign-in keeps Check available and returns a safe recovery instruction", async () => {
  const f = await connect();
  try {
    const error = new StageAuthenticationError("AUTHENTICATION_REQUIRED", "Run Atlas: Start Codex Bridge in VS Code.");
    f.mcp.listTools.mockRejectedValue(error); f.mcp.callTool.mockRejectedValue(error);
    expect((await f.client.listTools()).tools).toHaveLength(2);
    expect((await f.client.callTool({ name: "atlas_checkStageRunner" })).structuredContent).toMatchObject({ code: "AUTHENTICATION_REQUIRED" });
  } finally { await f.close(); }
});
test("remote requests preserve arguments and structured results, without leaking thrown errors", async () => {
  const f = await connect();
  try {
    f.mcp.callTool.mockResolvedValue({ status: "applied", draft_revision: 3 });
    const input = { model_id: 7, expected_draft_revision: 3 };
    const result = await f.client.callTool({ name: "apply_model_change_set", arguments: input });
    expect(f.mcp.callTool).toHaveBeenCalledWith("apply_model_change_set", input);
    expect(result.structuredContent).toEqual({ status: "applied", draft_revision: 3 });
    f.mcp.callTool.mockRejectedValue(new Error("private-provider-diagnostic"));
    const failure = await f.client.callTool({ name: "list_tenants" });
    expect(failure.isError).toBe(true); expect(JSON.stringify(failure)).not.toContain("private-provider-diagnostic");
  } finally { await f.close(); }
});

test("profiling run tools are forwarded without exposing internal worker operations", async () => {
  const f = await connect();
  try {
    const tools = ["start_profiling_run", "get_profiling_run_status", "cancel_profiling_run"];
    f.mcp.listTools.mockResolvedValue([...tools, "mcp_profiling_worker"].map(name => ({ name, inputSchema: { type: "object" as const } })));
    const names = (await f.client.listTools()).tools.map(tool => tool.name);
    expect(names).toEqual(["atlas_checkStageRunner", "atlas_stageApprovedManifest", ...tools]);
    f.mcp.callTool.mockResolvedValue({ run_id: 7, state: "running", saved_profile_count: 0 });
    const result = await f.client.callTool({ name: "get_profiling_run_status", arguments: { run_id: 7 } });
    expect(f.mcp.callTool).toHaveBeenCalledWith("get_profiling_run_status", { run_id: 7 });
    expect(result.structuredContent).toMatchObject({ run_id: 7, state: "running" });
  } finally { await f.close(); }
});
