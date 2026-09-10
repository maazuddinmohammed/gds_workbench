const assert = require('node:assert/strict');
const fs = require('node:fs');
const path = require('node:path');
const vscode = require('vscode');
const { createRequest, serveFixture, ID } = require('./host-fixture.cjs');

exports.run = async () => {
  const fixtureRoot = process.env.GDS_STAGE_HOST_FIXTURE_ROOT;
  const workspace = vscode.workspace.workspaceFolders?.[0]?.uri.fsPath;
  assert.ok(fixtureRoot && workspace === path.join(fixtureRoot, 'workspace'),
    'Run through test:host using its disposable workspace and isolated profile');
  const resultPath = path.join(workspace, 'host-test-result.json');
  const checks = [];
  let check = 'activation';
  const record = status => fs.writeFileSync(resultPath, JSON.stringify({
    status, vscodeVersion: vscode.version, check, checks,
  }));
  const invoke = async input => {
    const result = await vscode.lm.invokeTool('gds_stageApprovedManifest', {
      input, toolInvocationToken: undefined,
    });
    assert.equal(result.content.length, 1);
    assert.ok(result.content[0] instanceof vscode.LanguageModelTextPart,
      'Receipt must be readable text, not an attachment');
    assert.ok(result.content[0].value.length < 4096, 'Receipt must stay bounded');
    return JSON.parse(result.content[0].value);
  };
  record('running');
  try {
    const extension = vscode.extensions.getExtension('gds-workbench.gds-stage-runner');
    assert.ok(extension, 'Stage Runner was not discovered');
    assert.equal(extension.extensionPath, path.join(fixtureRoot, 'candidate', 'extension'));
    await extension.activate();
    assert.ok(extension.isActive);
    assert.ok((await vscode.commands.getCommands()).includes('gdsStageRunner.check'));
    const tool = vscode.lm.tools.find(item => item.name === 'gds_stageApprovedManifest');
    assert.ok(tool, 'Stage tool was not registered');
    assert.deepEqual(tool.inputSchema.required, ['manifestPath', 'expectedDigest']);
    checks.push(check);
    // VS Code's own API tests use this context key for confirmation-free fixture invocations.
    // Only the disposable profile created by run-vscode-host.mjs has global auto-approve enabled.
    await vscode.commands.executeCommand('setContext', 'vscode.chat.tools.global.autoApprove.testMode', true);
    check = 'missing manifest text receipt';
    assert.deepEqual(await invoke({ manifestPath: path.join(workspace, 'missing.stage-request.json'),
      expectedDigest: '0'.repeat(64) }), {
      schemaVersion: '1.0', status: 'failed', code: 'MANIFEST_NOT_FOUND',
      message: 'Stage request manifest was not found.', stageStarted: false, legacyFallbackAllowed: true,
    });
    checks.push(check);
    for (const scenario of ['direct', 'chunked', 'changed-digest', 'lost-write', 'bad-fingerprint']) {
      check = scenario;
      const fixture = createRequest(workspace, scenario === 'chunked');
      const server = await serveFixture(scenario);
      try {
        await vscode.workspace.getConfiguration('gds.stageRunner').update(
          'localUrl', server.endpoint, vscode.ConfigurationTarget.Global);
        const input = { ...fixture.input };
        if (scenario === 'changed-digest') input.expectedDigest = '0'.repeat(64);
        const receipt = await invoke(input);
        assert.deepEqual(server.state.errors, []);
        if (scenario === 'changed-digest') {
          assert.equal(receipt.status, 'failed');
          assert.equal(receipt.code, 'DIGEST_MISMATCH');
          assert.equal(receipt.stageStarted, false);
          assert.equal(server.state.calls.length, 0, 'Changed approval must not contact MCP');
        } else {
          assert.equal(server.state.revision, 2);
          assert.ok(JSON.stringify(server.state.records) === JSON.stringify(fixture.records),
            'Transferred records must exactly match the synthetic approved files');
          if (scenario === 'lost-write' || scenario === 'bad-fingerprint') {
            assert.equal(receipt.status, 'failed');
            assert.equal(receipt.stageStarted, true);
            assert.equal(receipt.legacyFallbackAllowed, false);
            if (scenario === 'lost-write') {
              assert.equal(receipt.code, 'MCP_OUTCOME_UNKNOWN');
              assert.equal(server.state.calls.filter(name => name === 'stage_metadata_change_set').length, 1);
            } else {
              assert.equal(receipt.code, 'FINGERPRINT_MISMATCH');
            }
          } else {
            assert.deepEqual(receipt, {
              schemaVersion: '1.0', status: 'staged', area: 'metadata', changeSetId: ID,
              startingRevision: 1, resultingRevision: 2, acceptedDigest: input.expectedDigest,
              stageFingerprint: server.state.fingerprint, fingerprintVerified: true,
              datasets: [{ dataset: 'source_object', recordCount: fixture.records.length }],
            });
            assert.ok(!JSON.stringify(receipt).includes('Fixture_'), 'Payload rows must stay out of the receipt');
            const chunkCalls = server.state.calls.filter(name => name === 'put_metadata_stage_chunk');
            assert.equal(chunkCalls.length, scenario === 'chunked' ? 2 : 0);
          }
        }
        checks.push(check);
      } finally {
        await server.close();
      }
    }
    record('passed');
    console.log(`STAGE_HOST_PASS: ${checks.length} packaged-tool checks in VS Code ${vscode.version}`);
  } catch (error) {
    record('failed');
    throw error;
  } finally {
    await vscode.commands.executeCommand('setContext', 'vscode.chat.tools.global.autoApprove.testMode', undefined);
  }
};
