import assert from 'node:assert/strict';
import fs from 'node:fs';
import os from 'node:os';
import path from 'node:path';
import test from 'node:test';
import evidence from '../../plugins/v2/gds/skills/gds/scripts/model-quality-files.js';

function session(t) {
  const root = fs.mkdtempSync(path.join(os.tmpdir(), 'gds-evidence-'));
  t.after(() => fs.rmSync(root, {recursive: true, force: true}));
  const put = (name, value) => {
    fs.mkdirSync(path.dirname(path.join(root, name)), {recursive: true});
    fs.writeFileSync(path.join(root, name), typeof value === 'string' ? value : JSON.stringify(value));
  };
  put('session.json', {stale: []});
  put('model/manifest.json', {snapshot_id: 'model-1'});
  put('metadata/manifest.json', {snapshot_id: 'metadata-1'});
  put('working/01/object-analysis/orders.md', 'OrderNumber determines the header; LineNumber distinguishes its lines.');
  put('tasks/01.modeling-decisions.json', {schema_version: '1.0', entities: [{
    evidence: [{note: 'working/01/object-analysis/orders.md'}],
  }], relationships: []});
  const files = evidence.readDecisions(root, '01').files;
  for (const name of ['model/manifest.json', 'metadata/manifest.json']) {
    const file = evidence.readEvidenceFile(root, name);
    files.push({path: name, sha256: file.sha256});
  }
  put('tasks/01.modeling-quality.json', {schema_version: '1.0', task: '01', draft_digest: 'draft', files,
    quality: {required: true, status: 'evidence_present', errors: []}});
  const acceptance = ['draft', 'acknowledged', {modeling_quality: {
    report_sha256: evidence.readEvidenceFile(root, 'tasks/01.modeling-quality.json').sha256,
  }}];
  return {root, put, verify: () => evidence.verifyQualityAcceptance(root, '01', 'draft', acceptance, ['logical_entity'])};
}

test('unchanged model, metadata, decisions and sanitized note remain accepted', t => {
  const fixture = session(t);
  assert.doesNotThrow(fixture.verify);
});

for (const [name, replacement] of [
  ['model/manifest.json', {snapshot_id: 'model-2'}],
  ['metadata/manifest.json', {snapshot_id: 'metadata-2'}],
  ['tasks/01.modeling-decisions.json', {}],
  ['tasks/01.modeling-quality.json', {}],
  ['working/01/object-analysis/orders.md', 'A different decision.'],
]) test(`changing ${name} invalidates acceptance`, t => {
  const fixture = session(t);
  fixture.put(name, replacement);
  assert.throws(fixture.verify, /changed after acknowledgement/);
});

test('stale supporting metadata invalidates acceptance', t => {
  const fixture = session(t);
  fixture.put('session.json', {stale: ['metadata']});
  assert.throws(fixture.verify, /stale Snapshot/);
});

test('notes cannot escape the session or traverse symlinks', t => {
  const fixture = session(t);
  for (const name of ['../outside.md', '/tmp/outside.md', 'working/01/../outside.md', 'working\\outside.md'])
    assert.throws(() => evidence.readEvidenceFile(fixture.root, name), /relative/);
  fs.symlinkSync(path.join(fixture.root, 'metadata'), path.join(fixture.root, 'working/01/object-analysis/link'));
  assert.throws(() => evidence.readEvidenceFile(fixture.root, 'working/01/object-analysis/link/manifest.json'), /regular session files/);
});

test('missing, empty and oversized notes are distinguished', t => {
  const fixture = session(t);
  const note = 'working/01/object-analysis/orders.md';
  fs.unlinkSync(path.join(fixture.root, note));
  assert.equal(evidence.readDecisions(fixture.root, '01').files.at(-1).sha256, null);
  fixture.put(note, '  ');
  assert.throws(() => evidence.readDecisions(fixture.root, '01'), /empty/);
  fixture.put(note, 'a'.repeat(65537));
  assert.throws(() => evidence.readDecisions(fixture.root, '01'), /byte limit/);
});

test('nonmodeling tasks retain existing acceptance contract', t => {
  const fixture = session(t);
  assert.doesNotThrow(() => evidence.verifyQualityAcceptance(fixture.root, '01', 'draft', [], ['profiling_profile']));
});
