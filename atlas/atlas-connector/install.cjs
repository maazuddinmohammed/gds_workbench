// User-run local installation. The connector has no runtime npm dependencies.
const { spawnSync } = require("node:child_process");
const { join, resolve } = require("node:path");

function installConnector(installation, args, run = spawnSync, platform = process.platform, npm = process.env.npm_execpath) {
  if (!npm) throw new Error("Run npm run setup from the atlas-connector folder.");
  const steps = [
    { label: "Preparing Atlas files", program: process.execPath, args: [join(installation, "atlas-connector.cjs"), "setup", ...args], cwd: installation, visible: true },
    { label: "Registering Atlas with Codex", args: ["plugin", "marketplace", "add", "."], cwd: resolve(installation, "..", "codex-atlas") },
    { label: "Refreshing the Codex plugin", args: ["plugin", "add", "atlas@gds-workbench"], cwd: resolve(installation, "..", "codex-atlas") },
  ];
  for (const step of steps) {
    process.stdout.write(`${step.label}...\n`);
    // Only fixed Codex arguments enter cmd.exe; no paths, IDs, or user input are
    // interpolated. cwd carries paths with spaces. Other programs use no shell.
    const program = step.program ?? (platform === "win32" ? "cmd.exe" : "codex");
    const commandArgs = !step.program && platform === "win32" ? ["/d", "/s", "/c", `codex ${step.args.join(" ")}`] : step.args;
    const result = run(program, commandArgs, { cwd: step.cwd, stdio: step.visible ? "inherit" : "pipe", windowsHide: true });
    if (result.error || result.status !== 0) {
      // npm/Codex output can include machine configuration. Keep failure details local.
      throw new Error(`${step.label} failed. Check the setup guide, then rerun npm run setup. Login and working files are retained.`);
    }
  }
  process.stdout.write("Atlas installation is ready. In VS Code, open your working folder and run Atlas: Start Codex Bridge. Then start Codex in that same folder.\n");
}

module.exports = { installConnector };
if (require.main === module) {
  try { installConnector(__dirname, process.argv.slice(2)); }
  catch (error) { process.stderr.write(`${error.message}\n`); process.exitCode = 1; }
}
