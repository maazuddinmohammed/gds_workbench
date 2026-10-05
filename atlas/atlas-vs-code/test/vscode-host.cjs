const assert = require('node:assert/strict');
const fs = require('node:fs');
const path = require('node:path');
const vscode = require('vscode');
const { Client } = require('@modelcontextprotocol/sdk/client/index.js');
const { StdioClientTransport } = require('@modelcontextprotocol/sdk/client/stdio.js');
const { StreamableHTTPClientTransport } = require('@modelcontextprotocol/sdk/client/streamableHttp.js');
const { createRequest, serveFixture, ID } = require('./host-fixture.cjs');

exports.run = async () => {
  const fixtureRoot = process.env.ATLAS_STAGE_HOST_FIXTURE_ROOT;
  const workspace = vscode.workspace.workspaceFolders?.[0]?.uri.fsPath;
  assert.ok(fixtureRoot && workspace === path.join(fixtureRoot, 'workspace'),
    'Run through test:host using its disposable workspace and isolated profile');
  const resultPath = path.join(workspace, 'host-test-result.json');
  const checks = [];
  let latency;
  let check = 'activation';
  const record = status => fs.writeFileSync(resultPath, JSON.stringify({
    status, vscodeVersion: vscode.version, check, checks, latency,
  }));
  const invoke = async (input, name = 'atlas_stageApprovedManifest') => {
    const result = await vscode.lm.invokeTool(name, {
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
    const extension = vscode.extensions.getExtension('gds-workbench.atlas-stage-runner');
    assert.ok(extension, 'Stage Runner was not discovered');
    assert.equal(extension.extensionPath, path.join(fixtureRoot, 'candidate', 'extension'));
    await extension.activate();
    assert.ok(extension.isActive);
    assert.ok((await vscode.commands.getCommands()).includes('atlasStageRunner.check'));
    const tool = vscode.lm.tools.find(item => item.name === 'atlas_stageApprovedManifest');
    assert.ok(tool, 'Stage tool was not registered');
    assert.ok(vscode.lm.tools.find(item => item.name === 'atlas_checkStageRunner'), 'Check tool was not registered');
    assert.deepEqual(tool.inputSchema.required, ['manifestPath']);
    checks.push(check);
    // VS Code's own API tests use this context key for confirmation-free fixture invocations.
    // Only the disposable profile created by run-vscode-host.mjs has global auto-approve enabled.
    await vscode.commands.executeCommand('setContext', 'vscode.chat.tools.global.autoApprove.testMode', true);
    check = 'missing manifest text receipt';
    assert.deepEqual(await invoke({ manifestPath: path.join(workspace, 'missing.stage-request.json'),
      expectedDigest: '0'.repeat(64) }), {
      schema_version: '1.0', status: 'failed', code: 'MANIFEST_NOT_FOUND',
      message: 'Stage request manifest was not found.', stage_started: false, legacy_fallback_allowed: true,
    });
    checks.push(check);
    for (const viaBridge of [false, true]) for (const scenario of ['direct', 'chunked', 'changed-digest', 'lost-write', 'bad-fingerprint']) {
      check = `${viaBridge ? "bridge" : "copilot"}: ${scenario}`;
      record("running");
      let bridgeClient;
      const server = await serveFixture(scenario);
      const fixture = createRequest(workspace, scenario === 'chunked', server.endpoint);
      try {
        await vscode.workspace.getConfiguration('atlas.stageRunner').update(
          'localUrl', server.endpoint, vscode.ConfigurationTarget.Global);
        if (viaBridge) {
          assert.equal((await vscode.commands.executeCommand('atlasBridge.start')).status, 'ready');
          bridgeClient = new Client({ name: 'packaged-relay-test', version: '1' });
          await bridgeClient.connect(new StdioClientTransport({
            command: process.env.ATLAS_STAGE_TEST_NODE,
            args: [path.resolve(__dirname, '../../atlas-connector/atlas-connector.cjs'), 'serve'],
            cwd: workspace, stderr: 'pipe',
          }));
          const tools = (await bridgeClient.listTools()).tools.map(tool => tool.name);
          assert.ok(tools.includes('atlas_stageApprovedManifest'));
          assert.ok(!tools.includes('stage_metadata_change_set'));
          server.state.calls.length = 0;
        }
        const call = viaBridge
          ? async (input, name = 'atlas_stageApprovedManifest') => (await bridgeClient.callTool({ name, arguments: input })).structuredContent
          : invoke;
        if (viaBridge && scenario === 'direct') {
          const direct = new Client({ name: 'latency-baseline', version: '1' });
          await direct.connect(new StreamableHTTPClientTransport(new URL(server.endpoint)));
          try {
            const baseline = [], bridged = [];
            await call({}, 'atlas_checkStageRunner');
            for (let i = 0; i < 30; i++) {
              let start = performance.now();
              await direct.callTool({ name: 'list_tenants', arguments: { page_size: 1 } });
              baseline.push(performance.now() - start);
              start = performance.now();
              await call({}, 'atlas_checkStageRunner');
              bridged.push(performance.now() - start);
            }
            baseline.sort((a,b) => a-b); bridged.sort((a,b) => a-b);
            latency = { samples: 30, directMedianMs: baseline[15], bridgeMedianMs: bridged[15], bridgeP95Ms: bridged[28] };
          } finally { await direct.close(); }
        }
        const input = { ...fixture.input };
        if (scenario === 'direct') {
          const temporary = path.join(workspace, '.atlas/temp');
          fs.mkdirSync(temporary, { recursive: true });
          const outputFile = path.join(temporary, `${viaBridge ? 'bridge-' : ''}ready.json`);
          const ready = await call({ outputFile }, 'atlas_checkStageRunner');
          assert.deepEqual(ready, { schema_version: '1.0', status: 'ready', backend: fixture.backend });
          assert.deepEqual(JSON.parse(fs.readFileSync(outputFile, 'utf8')), ready);
          checks.push('readiness tool and one-document export');
          delete input.expectedDigest;
          input.outputFile = path.join(temporary, `${viaBridge ? 'bridge-' : ''}stage.json`);
        }
        if (scenario === 'changed-digest') input.expectedDigest = '0'.repeat(64);
        const receipt = await call(input);
        assert.deepEqual(server.state.errors, []);
        if (scenario === 'changed-digest') {
          assert.equal(receipt.status, 'failed');
          assert.equal(receipt.code, 'DIGEST_MISMATCH');
          assert.equal(receipt.stage_started, false);
          assert.equal(server.state.calls.length, 0, 'Changed approval must not contact MCP');
        } else {
          assert.equal(server.state.revision, 2);
          assert.ok(JSON.stringify(server.state.records) === JSON.stringify(fixture.records),
            'Transferred records must exactly match the synthetic approved files');
          if (scenario === 'lost-write' || scenario === 'bad-fingerprint') {
            assert.equal(receipt.status, 'failed');
            assert.equal(receipt.stage_started, true);
            assert.equal(receipt.legacy_fallback_allowed, false);
            if (scenario === 'lost-write') {
              assert.equal(receipt.code, 'MCP_OUTCOME_UNKNOWN');
              assert.equal(server.state.calls.filter(name => name === 'stage_metadata_change_set').length, 1);
            } else {
              assert.equal(receipt.code, 'FINGERPRINT_MISMATCH');
            }
          } else {
            assert.deepEqual(receipt, {
              task_id:fixture.task,operation_id:fixture.operation,owner_tenant_id:17,owner_root:'.',backend:fixture.backend,
              schema_version: '1.0', status: 'staged', area: 'metadata', change_set_id: ID,
              starting_revision: 1, draft_revision: 2, accepted_digest: fixture.input.expectedDigest,
              stage_fingerprint: server.state.fingerprint, fingerprint_verified: true,
              datasets: [{ dataset: 'source_object', record_count: fixture.records.length }],
            });
            assert.ok(!JSON.stringify(receipt).includes('Fixture_'), 'Payload rows must stay out of the receipt');
            if (scenario === 'direct') {
              assert.deepEqual(JSON.parse(fs.readFileSync(input.outputFile, 'utf8')), receipt);
              checks.push('operation digest and Stage export');
            }
            const chunkCalls = server.state.calls.filter(name => name === 'put_metadata_stage_chunk');
            assert.equal(chunkCalls.length, scenario === 'chunked' ? 2 : 0);
          }
        }
        checks.push(check);
      } finally {
        await bridgeClient?.close();
        await vscode.commands.executeCommand("atlasBridge.stop");
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
