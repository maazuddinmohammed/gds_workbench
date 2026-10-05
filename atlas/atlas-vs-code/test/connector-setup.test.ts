import { cp, mkdir, mkdtemp, readFile, rm, symlink, writeFile } from "node:fs/promises";
import { tmpdir } from "node:os";
import { join, resolve } from "node:path";
import { expect, test } from "vitest";
import { prepareCodexPlugin } from "../src/connector/setup.js";

const plugin = resolve("../atlas-plugin");

test("setup preserves the Copilot source and makes Codex wiring independent of the working folder", async () => {
  const installation = join(await mkdtemp(join(tmpdir(), "Atlas installation with spaces ")), "atlas-connector");
  await mkdir(installation);
  const original = await readFile(join(plugin, "mcp.json"));
  const generated = await prepareCodexPlugin(plugin, installation);
  expect(await readFile(join(plugin, "mcp.json"))).toEqual(original);
  const mcp = JSON.parse(await readFile(join(generated, "mcp.json"), "utf8")).mcpServers["gds-workbench"];
  expect(mcp).toEqual({ type: "stdio", command: process.execPath,
    args: [join(installation, "atlas-connector.cjs"), "serve"] });
  await expect(readFile(join(generated, "connector.json"))).rejects.toMatchObject({ code: "ENOENT" });
  expect(await readFile(join(generated, "skills/atlas/SKILL.md"))).toEqual(await readFile(join(plugin, "skills/atlas/SKILL.md")));
  expect(await readFile(join(generated, "templates/validation-summary.md"))).toEqual(await readFile(join(plugin, "templates/validation-summary.md")));
  expect(await prepareCodexPlugin(plugin, installation)).toBe(generated);
  await expect(readFile(join(generated, "connector.json"))).rejects.toMatchObject({ code: "ENOENT" });
});
test("unknown files and symbolic links are not copied into the installed plugin", async () => {
  const installation = join(await mkdtemp(join(tmpdir(), "atlas-install-test-")), "atlas-connector"), fixture = join(installation, "source");
  await mkdir(installation);
  await cp(plugin, fixture, { recursive: true });
  await writeFile(join(fixture, "unreviewed.txt"), "fixture");
  await expect(prepareCodexPlugin(fixture, installation)).rejects.toMatchObject({ code: "SETUP_FAILED" });
  await symlink(fixture, join(installation, "linked"), "junction");
  await expect(prepareCodexPlugin(join(installation, "linked"), installation)).rejects.toMatchObject({ code: "SETUP_FAILED" });
});
test("template support does not allow executable files in that family", async () => {
  const installation = join(await mkdtemp(join(tmpdir(), "atlas-template-install-")), "atlas-connector"), fixture = join(installation, "source");
  await mkdir(installation);
  await cp(plugin, fixture, { recursive: true });
  await writeFile(join(fixture, "templates/unreviewed.js"), "throw new Error('fixture');");
  await expect(prepareCodexPlugin(fixture, installation)).rejects.toMatchObject({ code: "SETUP_FAILED" });
});
test("updates replace removed files without storing authentication configuration", async () => {
  const parent = await mkdtemp(join(tmpdir(), "atlas-update-")), installation = join(parent, "atlas-connector"), source = join(parent, "atlas");
  await mkdir(installation);
  await cp(plugin, source, { recursive: true });
  await writeFile(join(source, "docs/removed.md"), "previous release");
  const generated = await prepareCodexPlugin(source, installation);
  const oldMcp = JSON.parse(await readFile(join(generated, "mcp.json"), "utf8"));
  oldMcp.mcpServers["gds-workbench"].args.push("--config", join(generated, "connector.json"));
  await writeFile(join(generated, "mcp.json"), JSON.stringify(oldMcp));
  await writeFile(join(generated, "connector.json"), "discard without parsing");
  await rm(source, { recursive: true });
  await cp(plugin, source, { recursive: true });
  await writeFile(join(source, "docs/added.md"), "new release");
  await prepareCodexPlugin(source, installation);
  await expect(readFile(join(generated, "docs/removed.md"))).rejects.toMatchObject({ code: "ENOENT" });
  expect(await readFile(join(generated, "docs/added.md"), "utf8")).toBe("new release");
  await expect(readFile(join(generated, "connector.json"))).rejects.toMatchObject({ code: "ENOENT" });
});

test("a rejected update preserves the installed version and never replaces a workspace or symlink", async () => {
  const parent = await mkdtemp(join(tmpdir(), "atlas-rejected-update-")), installation = join(parent, "atlas-connector"), source = join(parent, "atlas");
  await mkdir(installation);
  await cp(plugin, source, { recursive: true });
  const generated = await prepareCodexPlugin(source, installation);
  const original = await readFile(join(generated, "plugin.json"));
  await writeFile(join(source, "templates/unsafe.js"), "fixture");
  await expect(prepareCodexPlugin(source, installation)).rejects.toMatchObject({ code: "SETUP_FAILED" });
  expect(await readFile(join(generated, "plugin.json"))).toEqual(original);
  await rm(join(source, "templates/unsafe.js"));
  await mkdir(join(generated, ".atlas"));
  await writeFile(join(generated, ".atlas/draft.json"), "fixture");
  await expect(prepareCodexPlugin(source, installation)).rejects.toMatchObject({ code: "SETUP_FAILED" });
  expect(await readFile(join(generated, ".atlas/draft.json"), "utf8")).toBe("fixture");
  await rm(generated, { recursive: true });
  await symlink(source, generated, "junction");
  await expect(prepareCodexPlugin(source, installation)).rejects.toMatchObject({ code: "SETUP_FAILED" });
  expect(await readFile(join(source, "plugin.json"))).toEqual(original);
});

test("setup refuses concurrent updates and interrupted replacement state", async () => {
  const parent = await mkdtemp(join(tmpdir(), "atlas-update-lock-")), installation = join(parent, "atlas-connector");
  await mkdir(installation);
  await writeFile(join(parent, ".atlas-setup.lock"), "fixture");
  await expect(prepareCodexPlugin(plugin, installation)).rejects.toMatchObject({ code: "SETUP_BUSY" });
  expect(await readFile(join(parent, ".atlas-setup.lock"), "utf8")).toBe("fixture");
  await rm(join(parent, ".atlas-setup.lock"));
  await mkdir(join(parent, "codex-atlas.previous"));
  await expect(prepareCodexPlugin(plugin, installation)).rejects.toMatchObject({ code: "SETUP_RECOVERY_REQUIRED" });
});
