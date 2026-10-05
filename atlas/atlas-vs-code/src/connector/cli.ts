import { parseArgs } from "node:util";
import { dirname, join, resolve } from "node:path";
import { realpath } from "node:fs/promises";
import { Client } from "@modelcontextprotocol/sdk/client/index.js";
import { connectBridge, SocketTransport } from "./bridge.js";
import { prepareCodexPlugin } from "./setup.js";
import { failureReceipt } from "../receipt.js";
import { StageRunnerError } from "../stage-runner.js";

async function main() {
  const { values, positionals } = parseArgs({ allowPositionals: true, options: {
    plugin: { type: "string" }, help: { type: "boolean" },
  } });
  const command = positionals[0], installation = dirname(await realpath(process.argv[1]!));
  if (values.help || !command) {
    process.stdout.write("Atlas VS Code Bridge\nnpm run setup   Install or refresh Atlas in Codex.\nsetup [--plugin <Atlas folder>]   Refresh local plugin files.\ncheck   Run from your working folder after starting the bridge in VS Code.\nserve   Private local relay launched by Codex.\n");
    return;
  }
  if (positionals.length !== 1 || !["setup", "check", "serve"].includes(command)) throw new Error("invalid command");
  if (command === "setup") {
    await prepareCodexPlugin(resolve(values.plugin ?? join(installation, "..", "atlas")), installation);
    process.stdout.write("Atlas setup is complete. Codex files are in ../codex-atlas.\n");
    return;
  }
  if (values.plugin) throw new Error("setup-only option");
  const socket = await connectBridge(await realpath(process.cwd()));
  if (command === "check") {
    const client = new Client({ name: "atlas-bridge-check", version: "0.2.0" });
    try {
      await client.connect(new SocketTransport(socket));
      const result = await client.callTool({ name: "atlas_checkStageRunner", arguments: {} });
      if (result.isError || (result.structuredContent as Record<string, unknown> | undefined)?.status !== "ready") throw new StageRunnerError("BRIDGE_NOT_READY", "Run Atlas: Start Codex Bridge in VS Code and complete sign-in.");
      process.stdout.write("Atlas bridge is ready. Keep VS Code open.\n");
    } finally { await client.close(); socket.destroy(); }
    return;
  }
  // This process has no Microsoft credentials or remote network client. MCP,
  // including cancellation, passes over one authenticated local socket only.
  process.stdin.pipe(socket); socket.pipe(process.stdout); socket.resume();
  socket.on("error", () => undefined);
  socket.once("close", () => {
    process.stderr.write("BRIDGE_DISCONNECTED: Atlas bridge closed. Restart it in VS Code. Inspect unfinished operation status before retrying writes.\n");
    process.stdin.unpipe(socket); process.stdin.pause(); process.exitCode = 1;
  });
  process.stdin.once("end", () => socket.destroy());
  process.once("SIGINT", () => socket.destroy());
  process.once("SIGTERM", () => socket.destroy());
}

main().catch(error => {
  const receipt = failureReceipt(error, false);
  process.stderr.write(`${receipt.code}: ${receipt.message}\n`);
  process.exitCode = 1;
});
