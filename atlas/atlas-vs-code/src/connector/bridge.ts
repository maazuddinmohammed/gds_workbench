import { createHash, randomBytes, timingSafeEqual } from "node:crypto";
import { execFile } from "node:child_process";
import { chmod, lstat, mkdir, readFile, realpath, unlink, writeFile } from "node:fs/promises";
import { createConnection, createServer, type Socket } from "node:net";
import { homedir } from "node:os";
import { join } from "node:path";
import { promisify } from "node:util";
import type { Transport } from "@modelcontextprotocol/sdk/shared/transport.js";
import { ReadBuffer, serializeMessage } from "@modelcontextprotocol/sdk/shared/stdio.js";
import type { JSONRPCMessage } from "@modelcontextprotocol/sdk/types.js";
import { StageRunnerError } from "../stage-runner.js";

const LIMIT = 8 * 1024 * 1024;
const UNAVAILABLE = "Open the same working folder in VS Code and run Atlas: Start Codex Bridge.";
export const bridgeDirectory = () => join(homedir(), ".atlas-bridge");

// Both the launcher and the extension resolve the real folder, including Windows casing.
export async function bridgeKey(workspace: string) {
  const root = await realpath(workspace);
  return createHash("sha256").update(process.platform === "win32" ? root.toLowerCase() : root).digest("hex");
}

// Per-message bounds and protocol validation apply in both directions. Never log frames.
export class SocketTransport implements Transport {
  onclose?: () => void;
  onerror?: (error: Error) => void;
  onmessage?: (message: JSONRPCMessage) => void;
  constructor(private readonly socket: Socket) {}
  async start() {
    const buffer = new ReadBuffer({ maxBufferSize: LIMIT });
    this.socket.on("data", chunk => {
      try {
        buffer.append(chunk);
        let message;
        while ((message = buffer.readMessage()) !== null) this.onmessage?.(message);
      } catch {
        this.onerror?.(new Error("Invalid Atlas bridge message."));
        this.socket.destroy();
      }
    });
    this.socket.on("error", () => this.onerror?.(new Error("Atlas bridge disconnected.")));
    this.socket.once("close", () => this.onclose?.());
    this.socket.resume();
  }
  async send(message: JSONRPCMessage) {
    const data = serializeMessage(message);
    if (Buffer.byteLength(data) > LIMIT) throw new Error("Atlas bridge response exceeds its limit.");
    await new Promise<void>((resolve, reject) => this.socket.write(data, error => error ? reject(new Error("Atlas bridge disconnected.")) : resolve()));
  }
  async close() { this.socket.destroy(); }
}

interface Descriptor { version: 1; pid: number; endpoint: string; capability: string }

// Secrets here are short-lived local pairing capabilities, never Microsoft tokens.
// Windows mode bits do not enforce ACLs: explicitly restrict the directory first.
async function privateDirectory(directory: string) {
  await mkdir(directory, { mode: 0o700, recursive: true });
  const info = await lstat(directory);
  if (!info.isDirectory() || info.isSymbolicLink() ||
      (process.platform !== "win32" && ((info.mode & 0o077) !== 0 || info.uid !== process.getuid?.()))) {
    throw new StageRunnerError("BRIDGE_STORAGE_UNSAFE", "Atlas bridge storage must be private to your operating-system user.");
  }
  if (process.platform === "win32") {
    const encoded = Buffer.from(directory).toString("base64");
    const script = `$ErrorActionPreference='Stop'; $p=[Text.Encoding]::UTF8.GetString([Convert]::FromBase64String('${encoded}')); ` +
      "$sid=[Security.Principal.WindowsIdentity]::GetCurrent().User; $acl=Get-Acl -LiteralPath $p; " +
      "if ($acl.GetOwner([Security.Principal.SecurityIdentifier]).Value -ne $sid.Value) { throw 'owner' }; " +
      "$acl.SetAccessRuleProtection($true,$false); foreach($r in @($acl.Access)) { [void]$acl.RemoveAccessRuleSpecific($r) }; " +
      "$rule=New-Object Security.AccessControl.FileSystemAccessRule($sid,'FullControl','ContainerInherit,ObjectInherit','None','Allow'); " +
      "$acl.AddAccessRule($rule); Set-Acl -LiteralPath $p -AclObject $acl";
    try { await promisify(execFile)("powershell.exe", ["-NoProfile", "-NonInteractive", "-Command", script], { timeout: 15_000, windowsHide: true }); }
    catch { throw new StageRunnerError("BRIDGE_STORAGE_UNSAFE", "Atlas could not secure its local bridge storage."); }
  }
}

async function readDescriptor(file: string): Promise<Descriptor> {
  const info = await lstat(file);
  if (!info.isFile() || info.isSymbolicLink() || info.size > 2048 ||
      (process.platform !== "win32" && ((info.mode & 0o077) !== 0 || info.uid !== process.getuid?.()))) throw new Error("unsafe descriptor");
  const value = JSON.parse(await readFile(file, "utf8"));
  if (value.version !== 1 || !Number.isSafeInteger(value.pid) || value.pid < 1 ||
      typeof value.endpoint !== "string" || !/^[a-f0-9]{64}$/.test(value.capability)) throw new Error("invalid descriptor");
  return value as Descriptor;
}

function endpointFor(directory: string, capability: string) {
  const id = createHash("sha256").update(directory + capability).digest("hex").slice(0, 32);
  return process.platform === "win32" ? `\\\\.\\pipe\\atlas-${id}` : join(directory, `${id}.sock`);
}

// One bridge per open workspace. Socket/descriptor creation is exclusive. Dead
// extension hosts can be replaced; live hosts are never silently taken over.
export async function startBridge(workspace: string, attach: (transport: Transport) => Promise<void>, directory = bridgeDirectory()) {
  await privateDirectory(directory);
  const key = await bridgeKey(workspace), file = join(directory, `${key}.json`);
  const existing = await lstat(file).catch(error => { if (error.code === "ENOENT") return undefined; throw error; });
  if (existing) {
    try {
      const old = await readDescriptor(file);
      let alive = true;
      try { process.kill(old.pid, 0); } catch (error) { if ((error as NodeJS.ErrnoException).code === "ESRCH") alive = false; }
      if (alive) throw new Error("live host");
      // Unlink only a verified private descriptor and its derived local socket.
      if (old.endpoint === endpointFor(directory, old.capability) && process.platform !== "win32") await unlink(old.endpoint).catch(() => undefined);
      await unlink(file);
    } catch { throw new StageRunnerError("BRIDGE_ALREADY_RUNNING", "A bridge already owns this folder. Stop it in its VS Code window before starting another."); }
  }
  const capability = randomBytes(32).toString("hex"), endpoint = endpointFor(directory, capability);
  const sockets = new Set<Socket>();
  const server = createServer(socket => {
    if (sockets.size >= 8) { socket.destroy(); return; }
    sockets.add(socket);
    socket.once("close", () => sockets.delete(socket));
    socket.on("error", () => undefined);
    socket.setTimeout(5000, () => socket.destroy());
    let input = Buffer.alloc(0);
    const handshake = (chunk: Buffer) => {
      input = Buffer.concat([input, chunk]);
      if (input.length > 1024) { socket.destroy(); return; }
      const newline = input.indexOf(10);
      if (newline < 0) return;
      try {
        const request = JSON.parse(input.subarray(0, newline).toString("utf8"));
        if (newline !== input.length - 1 || request.version !== 1 || request.workspace !== key ||
            typeof request.capability !== "string" || !/^[a-f0-9]{64}$/.test(request.capability) ||
            !timingSafeEqual(Buffer.from(request.capability), Buffer.from(capability))) throw new Error("unauthorized");
      } catch { socket.destroy(); return; }
      socket.pause(); socket.off("data", handshake); socket.setTimeout(0);
      void attach(new SocketTransport(socket)).then(() => { socket.write('{"ready":true}\n'); socket.resume(); }, () => socket.destroy());
    };
    socket.on("data", handshake);
  });
  let published = false;
  try {
    await new Promise<void>((resolve, reject) => { server.once("error", reject); server.listen(endpoint, () => { server.off("error", reject); resolve(); }); });
    server.on("error", () => { for (const socket of sockets) socket.destroy(); });
    if (process.platform !== "win32") await chmod(endpoint, 0o600);
    await writeFile(file, JSON.stringify({ version: 1, pid: process.pid, endpoint, capability }), { flag: "wx", mode: 0o600 });
    published = true;
  } catch {
    server.close();
    throw new StageRunnerError("BRIDGE_START_FAILED", "Atlas could not start its local bridge. Close other Atlas bridge windows and retry.");
  }
  let closing: Promise<void> | undefined;
  return {
    close() {
      return closing ??= (async () => {
      for (const socket of sockets) socket.destroy();
      await new Promise<void>(resolve => server.close(() => resolve()));
      if (published) { await unlink(file).catch(() => undefined); published = false; }
      })();
    },
  };
}

export async function connectBridge(workspace: string, directory = bridgeDirectory()): Promise<Socket> {
  try {
    const info = await lstat(directory);
    if (!info.isDirectory() || info.isSymbolicLink() ||
        (process.platform !== "win32" && ((info.mode & 0o077) !== 0 || info.uid !== process.getuid?.()))) throw new Error("unsafe directory");
    const key = await bridgeKey(workspace), descriptor = await readDescriptor(join(directory, `${key}.json`));
    if (descriptor.endpoint !== endpointFor(directory, descriptor.capability)) throw new Error("invalid endpoint");
    const socket = createConnection(descriptor.endpoint);
    try {
      await new Promise<void>((resolve, reject) => {
        const timeout = setTimeout(() => reject(new Error("timeout")), 5000);
        let input = "";
        const failed = () => { clearTimeout(timeout); reject(new Error("disconnected")); };
        const receive = (chunk: Buffer) => {
          input += chunk.toString("utf8");
          if (input.length > 128) { failed(); return; }
          if (!input.includes("\n")) return;
          clearTimeout(timeout);
          socket.off("data", receive); socket.off("error", failed); socket.off("close", failed);
          if (input !== '{"ready":true}\n') reject(new Error("invalid handshake"));
          else { socket.pause(); resolve(); }
        };
        socket.once("error", failed); socket.once("close", failed); socket.on("data", receive);
        socket.once("connect", () => socket.write(JSON.stringify({ version: 1, workspace: key, capability: descriptor.capability }) + "\n"));
      });
      return socket;
    } catch { socket.destroy(); throw new Error("unavailable"); }
  } catch { throw new StageRunnerError("BRIDGE_UNAVAILABLE", UNAVAILABLE); }
}
