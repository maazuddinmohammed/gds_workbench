// macOS/Linux runner: requires an installed VS Code and unzip; never downloads a host.
import assert from 'node:assert/strict';
import { spawn, spawnSync } from 'node:child_process';
import { mkdtempSync, mkdirSync, readFileSync, writeFileSync } from 'node:fs';
import { tmpdir } from 'node:os';
import path from 'node:path';
import { fileURLToPath } from 'node:url';

const root = path.resolve(path.dirname(fileURLToPath(import.meta.url)), '..');
const version = JSON.parse(readFileSync(path.join(root, 'package.json'), 'utf8')).version;
const vsix = path.resolve(process.argv[2] ?? path.join(root, '../dist', `gds-stage-runner-${version}.vsix`));
const fixture = mkdtempSync(path.join(tmpdir(), 'gds-stage-host-'));
const workspace = path.join(fixture, 'workspace');
const user = path.join(fixture, 'user');
mkdirSync(workspace);
mkdirSync(path.join(user, 'User'), { recursive: true });
writeFileSync(path.join(user, 'User/settings.json'), JSON.stringify({
  'chat.tools.global.autoApprove': true,
  'gds.stageRunner.profile': 'local',
  'telemetry.telemetryLevel': 'off',
  'update.mode': 'none',
  'extensions.autoCheckUpdates': false,
  'extensions.autoUpdate': false,
}));
const extraction = spawnSync('unzip', ['-q', vsix, '-d', path.join(fixture, 'candidate')]);
assert.equal(extraction.status, 0, 'VSIX extraction failed');
const code = process.env.GDS_STAGE_TEST_CODE ?? (process.platform === 'darwin'
  ? '/Applications/Visual Studio Code.app/Contents/Resources/app/bin/code' : 'code');
const child = spawn(code, [workspace, '--wait', '--new-window', '--user-data-dir', user,
  '--extensions-dir', path.join(fixture, 'extensions'),
  `--extensionDevelopmentPath=${path.join(fixture, 'candidate/extension')}`,
  `--extensionTestsPath=${path.join(root, 'test/vscode-host.cjs')}`,
  '--disable-extensions', '--disable-workspace-trust', '--skip-welcome', '--skip-release-notes'], {
  env: { ...process.env, GDS_STAGE_HOST_FIXTURE_ROOT: fixture },
  stdio: ['ignore', 'ignore', 'ignore'],
});
const timeout = setTimeout(() => child.kill(), 120_000);
try {
  await new Promise((resolve, reject) => { child.once('error', reject); child.once('close', resolve); });
  // A successful CLI exit alone does not prove the extension-host tests ran.
  const result = JSON.parse(readFileSync(path.join(workspace, 'host-test-result.json'), 'utf8'));
  console.log(JSON.stringify({ ...result, fixture, vsix }));
  assert.equal(result.status, 'passed', `Packaged tool failed: ${result.check}`);
} finally {
  clearTimeout(timeout);
}
