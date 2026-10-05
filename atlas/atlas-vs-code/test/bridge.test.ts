import { chmod, mkdtemp, mkdir, readFile, readdir, rm, writeFile } from "node:fs/promises";
import { tmpdir } from "node:os";
import { join } from "node:path";
import { createConnection } from "node:net";
import { Client } from "@modelcontextprotocol/sdk/client/index.js";
import { Server } from "@modelcontextprotocol/sdk/server/index.js";
import { CallToolRequestSchema } from "@modelcontextprotocol/sdk/types.js";
import { afterEach, expect, test, vi } from "vitest";
import { bridgeKey, connectBridge, SocketTransport, startBridge } from "../src/connector/bridge.js";
import { createConnectorServer } from "../src/connector/server.js";
import { resolveStageProfile } from "../src/profile.js";

const cleanup: Array<() => Promise<void>> = [];
afterEach(async () => { for (const close of cleanup.splice(0).reverse()) await close(); });
async function fixture() {
  const root = await mkdtemp(join(tmpdir(), "ab-"));
  cleanup.push(() => rm(root, { recursive: true, force: true }));
  const workspace = join(root, "work"), directory = join(root, "ipc");
  await mkdir(workspace);
  const callTool = vi.fn(async () => ({ tenants: [] }));
  const listTools = vi.fn(async () => [{ name: "list_tenants", inputSchema: { type: "object" as const } }]);
  const bridge = await startBridge(workspace, async transport => {
    const server = createConnectorServer({ callTool, listTools }, resolveStageProfile("local", "http://127.0.0.1:8000/mcp"), workspace);
    await server.connect(transport);
  }, directory);
  cleanup.push(() => bridge.close());
  return { root, workspace, directory, callTool, listTools, bridge };
}

test("one persistent private connection carries governed calls and Stage stays in the extension", async () => {
  const f = await fixture();
  const client = new Client({ name: "fixture", version: "1" });
  await client.connect(new SocketTransport(await connectBridge(f.workspace, f.directory)));
  cleanup.push(() => client.close());
  expect((await client.listTools()).tools.map(tool => tool.name)).toEqual(["atlas_checkStageRunner", "atlas_stageApprovedManifest", "list_tenants"]);
  for (let i = 0; i < 10; i++) expect((await client.callTool({ name: "list_tenants" })).structuredContent).toEqual({ tenants: [] });
  expect(f.callTool).toHaveBeenCalledTimes(10);
  const result = await client.callTool({ name: "stage_metadata_change_set", arguments: {} });
  expect(result.structuredContent).toMatchObject({ code: "TOOL_NOT_AVAILABLE" });
  expect(f.callTool).toHaveBeenCalledTimes(10);
});

test("wrong workspace and wrong capability cannot reach tool dispatch", async () => {
  const f = await fixture();
  const other = join(f.root, "other"); await mkdir(other);
  await expect(connectBridge(other, f.directory)).rejects.toMatchObject({ code: "BRIDGE_UNAVAILABLE" });
  const descriptor = JSON.parse(await readFile(join(f.directory, `${await bridgeKey(f.workspace)}.json`), "utf8"));
  for (const request of [{ version: 1, workspace: await bridgeKey(f.workspace), capability: "0".repeat(64) },
    { version: 1, workspace: "0".repeat(64), capability: descriptor.capability }]) {
    await new Promise<void>(resolve => {
      const socket = createConnection(descriptor.endpoint, () => socket.write(JSON.stringify(request) + "\n"));
      socket.on("error", () => undefined); socket.on("close", resolve);
    });
  }
  expect(f.callTool).not.toHaveBeenCalled(); expect(f.listTools).not.toHaveBeenCalled();
});

test("active workspace cannot be hijacked; stop removes discovery and disconnects clients", async () => {
  const f = await fixture();
  await expect(startBridge(f.workspace, async () => undefined, f.directory)).rejects.toMatchObject({ code: "BRIDGE_ALREADY_RUNNING" });
  const socket = await connectBridge(f.workspace, f.directory);
  const closed = new Promise<void>(resolve => { socket.on("close", resolve); socket.resume(); });
  await f.bridge.close(); await closed;
  expect((await readdir(f.directory)).filter(name => name.endsWith(".json"))).toEqual([]);
  await expect(connectBridge(f.workspace, f.directory)).rejects.toMatchObject({ code: "BRIDGE_UNAVAILABLE" });
});

test("discovery cannot redirect the launcher to arbitrary endpoints", async () => {
  const f = await fixture();
  const file = join(f.directory, `${await bridgeKey(f.workspace)}.json`);
  const descriptor = JSON.parse(await readFile(file, "utf8"));
  await writeFile(file, JSON.stringify({ ...descriptor, endpoint: "https://example.invalid" }));
  await expect(connectBridge(f.workspace, f.directory)).rejects.toMatchObject({ code: "BRIDGE_UNAVAILABLE" });
});

test("oversized frames disconnect before any tool can run", async () => {
  const f = await fixture();
  const socket = await connectBridge(f.workspace, f.directory);
  const closed = new Promise<void>(resolve => socket.once("close", resolve));
  socket.on("error", () => undefined); socket.resume();
  socket.write(Buffer.alloc(8 * 1024 * 1024 + 1, 32));
  await closed;
  expect(f.callTool).not.toHaveBeenCalled();
});

test.skipIf(process.platform === "win32")("refuses discovery readable by other OS users", async () => {
  const f = await fixture();
  const file = join(f.directory, `${await bridgeKey(f.workspace)}.json`);
  await chmod(file, 0o644);
  await expect(connectBridge(f.workspace, f.directory)).rejects.toMatchObject({ code: "BRIDGE_UNAVAILABLE" });
});

test.each(["cancel", "disconnect"])("%s reaches an in-flight request without replaying it", async action => {
  const root = await mkdtemp(join(tmpdir(), "ab-"));
  cleanup.push(() => rm(root, { recursive: true, force: true }));
  const received = vi.fn(), cancelled = vi.fn();
  const bridge = await startBridge(root, async transport => {
    const server = new Server({ name: "cancellation-fixture", version: "1" }, { capabilities: { tools: {} } });
    server.setRequestHandler(CallToolRequestSchema, async (_request, extra) => {
      received();
      await new Promise<void>(resolve => extra.signal.addEventListener("abort", () => { cancelled(); resolve(); }, { once: true }));
      return { content: [] };
    });
    await server.connect(transport);
  }, join(root, "ipc"));
  cleanup.push(() => bridge.close());
  const client = new Client({ name: "fixture", version: "1" });
  await client.connect(new SocketTransport(await connectBridge(root, join(root, "ipc"))));
  cleanup.push(() => client.close());
  const abort = new AbortController();
  const result = client.callTool({ name: "fixture" }, undefined, { signal: abort.signal }).then(() => "completed", () => "interrupted");
  await vi.waitFor(() => expect(received).toHaveBeenCalledOnce());
  if (action === "cancel") abort.abort(); else await bridge.close();
  expect(await result).toBe("interrupted");
  await vi.waitFor(() => expect(cancelled).toHaveBeenCalledOnce());
  expect(received).toHaveBeenCalledOnce();
});
