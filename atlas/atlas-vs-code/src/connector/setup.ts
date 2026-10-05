import { cp, lstat, mkdir, readFile, readdir, rename, rm, writeFile } from "node:fs/promises";
import { basename, dirname, extname, join, relative, resolve, sep } from "node:path";
import { randomUUID } from "node:crypto";
import { StageRunnerError } from "../stage-runner.js";
// Build a fresh copy before replacing only the recognized generated installation.
// The portable Copilot source, VS Code sign-in, and working folders are never edited.
export async function prepareCodexPlugin(plugin: string, installation: string, node = process.execPath) {
  const root = resolve(plugin), parent = resolve(installation, ".."), destination = join(parent, "codex-atlas");
  const temporary = join(parent, `.atlas-install-${randomUUID()}`), backup = join(parent, "codex-atlas.previous");
  const lock = join(parent, ".atlas-setup.lock");
  let locked = false, moved = false;
  const families: Record<string, string[]> = { skills: [".md"], references: [".md"], templates: [".md"], docs: [".md", ".png"],
    scripts: [".js", ".ps1", ".sh", ".py"], contracts: [".json"], workbench: [".js", ".html", ".css", ".json", ".md"], assets: [".json"] };
  async function inspect(path: string, tree: string, generated = false, family = "") {
    const entry = await lstat(path);
    if (entry.isSymbolicLink()) throw new Error("plugin symlink");
    const name = relative(tree, path).split(sep).join("/");
    if (entry.isDirectory()) {
      for (const child of await readdir(path)) {
        // The exported catalog is generated below; it is not another source of files.
        if (path === tree && child === ".agents" && !generated) continue;
        if (child.startsWith(".") && !(generated && path === tree && child === ".agents")) throw new Error("hidden plugin file");
        await inspect(join(path, child), tree, generated, family || child);
      }
    } else if (!entry.isFile() || (!["plugin.json", "mcp.json"].includes(name) &&
        !(generated && [".agents/plugins/marketplace.json", "connector.json"].includes(name)) &&
        !families[family]?.includes(extname(path)))) throw new Error("unreviewed plugin file");
  }
  try {
    await writeFile(lock, "Atlas setup in progress\n", { flag: "wx", mode: 0o600 }).catch(() => {
      throw new StageRunnerError("SETUP_BUSY", "Another Atlas setup may be running. See the installation guide before retrying.");
    });
    locked = true;
    // lstat also detects dangling links; only absence is treated as a new install.
    const previous = await lstat(backup).catch(error => { if (error.code === "ENOENT") return undefined; throw error; });
    if (previous) throw new StageRunnerError("SETUP_RECOVERY_REQUIRED", "A previous Atlas update needs recovery. See the installation guide.");
    if (root === destination || root.startsWith(destination + sep) || destination.startsWith(root + sep)) throw new Error("overlapping installation");
    await inspect(root, root);
    const manifest = JSON.parse(await readFile(join(root, "plugin.json"), "utf8"));
    if (manifest.name !== "atlas" || typeof manifest.version !== "string") throw new Error("invalid plugin");
    const existing = await lstat(destination).catch(error => { if (error.code === "ENOENT") return undefined; throw error; });
    if (existing) {
      if (!existing.isDirectory() || existing.isSymbolicLink()) throw new Error("invalid destination");
      await inspect(destination, destination, true);
      const oldManifest = JSON.parse(await readFile(join(destination, "plugin.json"), "utf8"));
      const oldMcp = JSON.parse(await readFile(join(destination, "mcp.json"), "utf8"));
      const oldCatalog = JSON.parse(await readFile(join(destination, ".agents/plugins/marketplace.json"), "utf8"));
      const server = oldMcp.mcpServers?.["gds-workbench"];
      // Recognize the previous generated wiring solely to discard it on update.
      // Its configuration is never loaded or copied into the bridge installation.
      const args = server?.args;
      const recognizedArgs = Array.isArray(args) && args[1] === "serve" &&
        (args.length === 2 || (args.length === 4 && args[2] === "--config" && args[3] === join(destination, "connector.json")));
      if (oldManifest.name !== "atlas" || oldCatalog.name !== "gds-workbench" || server?.type !== "stdio" ||
          args?.[0] !== join(installation, "atlas-connector.cjs") || !recognizedArgs) throw new Error("unrecognized installation");
    }
    await mkdir(temporary);
    await cp(root, temporary, { recursive: true, filter: source => basename(source) !== ".agents", dereference: false });
    await writeFile(join(temporary, "mcp.json"), JSON.stringify({
      $schema: "https://agent-plugins.org/schemas/1.0.0/mcp.schema.json",
      mcpServers: { "gds-workbench": { type: "stdio", command: node,
        args: [join(installation, "atlas-connector.cjs"), "serve"] } },
    }, null, 2) + "\n");
    const catalog = join(temporary, ".agents", "plugins", "marketplace.json");
    await mkdir(dirname(catalog), { recursive: true });
    await writeFile(catalog, JSON.stringify({ name: "gds-workbench", interface: { displayName: "Atlas Local Workbench" }, plugins: [{
      name: "atlas", source: { source: "local", path: "./" },
      policy: { installation: "AVAILABLE", authentication: "ON_INSTALL" }, category: "Productivity",
    }] }, null, 2) + "\n");
    if (existing) { await rename(destination, backup); moved = true; }
    try { await rename(temporary, destination); }
    catch (error) {
      if (moved) { await rename(backup, destination); moved = false; }
      throw error;
    }
    // Only the validated generated copy is disposable; never a user workspace.
    if (moved) { await rm(backup, { recursive: true }); moved = false; }
    return destination;
  } catch (error) {
    if (error instanceof StageRunnerError) throw error;
    throw new StageRunnerError("SETUP_FAILED", "Atlas setup failed. Check the supplied plugin and installation folders, then retry. See the installation guide for recovery.");
  } finally {
    // Only this attempt's generated temporary files; never user work or earlier installs.
    await rm(temporary, { recursive: true, force: true });
    if (locked) await rm(lock, { force: true });
  }
}
