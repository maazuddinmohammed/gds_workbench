const assert = require("node:assert/strict");
const vscode = require("vscode");

exports.run = async () => {
  const extension = vscode.extensions.getExtension("gds-workbench.gds-stage-runner");
  assert.ok(extension, "Stage Runner was not discovered");
  await extension.activate();
  assert.ok(extension.isActive, "Stage Runner did not activate");
  assert.ok((await vscode.commands.getCommands()).includes("gdsStageRunner.check"));
  const tool = vscode.lm.tools.find((item) => item.name === "gds_stageApprovedManifest");
  assert.ok(tool, "Stage tool was not registered");
  assert.deepEqual(tool.inputSchema.required, ["manifestPath", "expectedDigest"]);
  const receipt = { status: "staged", fingerprintVerified: true };
  const result = new vscode.LanguageModelToolResult([vscode.LanguageModelDataPart.json(receipt)]);
  assert.deepEqual(JSON.parse(Buffer.from(result.content[0].data).toString("utf8")), receipt);
  console.log(`Stage Runner VSIX activation, tool registration, and JSON output passed in VS Code ${vscode.version}.`);
};
