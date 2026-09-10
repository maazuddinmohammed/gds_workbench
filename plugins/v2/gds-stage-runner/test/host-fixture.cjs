// Synthetic, in-memory MCP fixture. Never connects to Azure or a database.
const assert = require('node:assert/strict');
const { createHash, randomUUID } = require('node:crypto');
const fs = require('node:fs');
const path = require('node:path');
const { createMcpExpressApp } = require('@modelcontextprotocol/sdk/server/express.js');
const { Server } = require('@modelcontextprotocol/sdk/server/index.js');
const { StreamableHTTPServerTransport } = require('@modelcontextprotocol/sdk/server/streamableHttp.js');
const { CallToolRequestSchema, ListToolsRequestSchema } = require('@modelcontextprotocol/sdk/types.js');

const ID = '30000000-0000-4000-8000-000000000050';
const SNAPSHOT = '10000000-0000-4000-8000-000000000001';
const KEY = ['tenant_code', 'system_code', 'connection_code', 'object_schema', 'object_name'];
const DATASETS = ['source_object', 'source_attribute', 'bronze_object', 'bronze_attribute',
  'silver_object', 'silver_attribute', 'gold_object', 'gold_attribute', 'ingestion_object_mapping',
  'ingestion_attribute_mapping', 'copy_group', 'member_group', 'copy_group_control', 'copy', 'process_group', 'process'];
const target = { tenant_id: 17, metadata_change_set_id: ID };
const common = { schema_version: '1.0', ...target, expires_at: '2099-01-01T00:00:00Z' };
const sha = value => createHash('sha256').update(value).digest('hex');
// Fixture keys are ASCII and numbers are integers; general serialization is covered by Python digest vectors.
const canonical = value => JSON.stringify(value, (_key, item) =>
  item && typeof item === 'object' && !Array.isArray(item)
    ? Object.fromEntries(Object.keys(item).sort().map(key => [key, item[key]])) : item);

function createRequest(workspace, large) {
  const session = path.join(workspace, 'GDS', 'DEMO', randomUUID());
  const write = (relative, value) => {
    const bytes = JSON.stringify(value) + '\n';
    const file = path.join(session, relative);
    fs.mkdirSync(path.dirname(file), { recursive: true });
    fs.writeFileSync(file, bytes);
    return { file, bytes, hash: sha(bytes) };
  };
  const records = Array.from({ length: large ? 2 : 1 }, (_, i) => ({
    tenant_code: 'DEMO', system_code: 'CRM', connection_code: 'MAIN', object_schema: 'sales',
    object_name: `Fixture_${i}_é_😀${large ? 'x'.repeat(40000) : ''}`, is_active: true,
  }));
  const payload = write('metadata-change-set/source_object.json', records);
  const digest = sha(Buffer.concat([Buffer.from(`source_object.json\0${Buffer.byteLength(payload.bytes)}\0`),
    Buffer.from(payload.bytes)]));
  const catalog = write('metadata/catalog.json', { snapshot_kind: 'metadata',
    sections: [{ name: 'fixture', datasets: [{ name: 'source_object', canonical_key: KEY }] }] });
  const snapshot = write('metadata/manifest.json', { schema_version: '2.0', snapshot_kind: 'metadata',
    snapshot_id: SNAPSHOT, tenant_code: 'DEMO', catalog: { path: 'catalog.json', sha256: catalog.hash },
    members: [{ path: 'catalog.json', size_bytes: Buffer.byteLength(catalog.bytes), sha256: catalog.hash }] });
  write('session.json', { current: '01', tasks: [['01', 'metadata', 'Fixture', 'ready']],
    cs: { metadata: [ID, 1, 'active', '01', digest] } });
  write('tasks/01.accept.json', [digest, 'valid', SNAPSHOT, null]);
  const manifest = write('tasks/01.stage-request.json', { schema_version: '2.0', kind: 'gds-stage-request',
    area: 'metadata', task: '01', accepted_digest: digest, failed_retry: false,
    snapshot: { snapshot_id: SNAPSHOT, manifest_sha256: snapshot.hash },
    target: { tenant_code: 'DEMO', change_set_id: ID, starting_revision: 1 },
    datasets: [{ dataset: 'source_object', canonical_key: KEY, record_count: records.length,
      payload_file: payload.file, sha256: payload.hash }] });
  return { input: { manifestPath: manifest.file, expectedDigest: digest }, records };
}

async function serveFixture(mode = 'success') {
  const state = { calls: [], records: [], revision: 1, batch: null, errors: [], fingerprint: null };
  const responseFor = (name, args) => {
    if (name === 'list_tenants') return { schema_version: '1.0', next_cursor: null, tenants: [{
      tenant_id: 17, tenant_code: 'DEMO', tenant_name: 'DEMO', tenant_description: null,
      tenant_visibility: 'private', effective_role: 'developer',
    }] };
    assert.equal(args.tenant_id, 17);
    assert.equal(args.metadata_change_set_id, ID);
    if (name === 'get_metadata_change_set') return { ...common, status: 'active',
      draft_revision: state.revision, candidate_digest: null, validation_outcome: null, dataset_counts: [],
      dataset: args.dataset ?? null, records: args.dataset ? state.records : null,
      created_at: '2026-01-01T00:00:00Z', last_activity_at: '2026-01-01T00:00:00Z',
      validated_at: null, applied_at: null, terminal_at: null };
    if (name === 'stage_metadata_change_set') {
      assert.equal(args.expected_draft_revision, state.revision);
      assert.equal(args.changes.length, 1);
      assert.equal(args.changes[0].dataset, 'source_object');
      state.records = args.changes[0].records;
      state.revision++;
      return { ...common, staged: true, status: 'active', draft_revision: state.revision,
        datasets: [{ dataset: 'source_object', record_count: state.records.length }] };
    }
    if (name === 'begin_metadata_stage_batch') {
      assert.equal(args.expected_draft_revision, state.revision);
      assert.equal(args.dataset, 'source_object');
      state.batch = { ...args, id: randomUUID(), chunks: [], hashes: [] };
      return { ...common, stage_batch_id: state.batch.id, dataset: args.dataset, created: true,
        total_record_count: args.total_record_count, total_chunk_count: args.total_chunk_count,
        received_chunk_count: 0, expected_draft_revision: state.revision };
    }
    if (name === 'put_metadata_stage_chunk') {
      assert.equal(args.stage_batch_id, state.batch.id);
      assert.equal(args.chunk_index, state.batch.chunks.length + 1);
      assert.equal(args.chunk_sha256, sha(canonical(args.records)));
      state.batch.chunks.push(args.records);
      state.batch.hashes.push(args.chunk_sha256);
      return { ...common, stage_batch_id: state.batch.id, dataset: args.dataset, accepted: true,
        duplicate: false, chunk_index: args.chunk_index, record_count: args.records.length,
        received_chunk_count: state.batch.chunks.length, total_chunk_count: state.batch.total_chunk_count };
    }
    if (name === 'commit_metadata_stage_batch') {
      assert.equal(args.stage_batch_id, state.batch.id);
      assert.equal(args.expected_draft_revision, state.revision);
      assert.equal(state.batch.chunks.length, state.batch.total_chunk_count);
      assert.equal(sha(state.batch.hashes.join('')), state.batch.batch_sha256);
      state.records = state.batch.chunks.flat();
      assert.equal(state.records.length, state.batch.total_record_count);
      state.revision++;
      return { ...common, stage_batch_id: state.batch.id, dataset: state.batch.dataset,
        committed: true, replayed: false, record_count: state.records.length,
        draft_revision: state.revision, status: 'active' };
    }
    if (name === 'get_metadata_change_set_fingerprint') {
      const datasets = DATASETS.map(dataset => ({ dataset,
        record_count: dataset === 'source_object' ? state.records.length : 0,
        sha256: sha(canonical(dataset === 'source_object' ? state.records : [])) }));
      const fingerprint = sha(JSON.stringify({ area: 'metadata', datasets, fingerprint_version: '1.0' }));
      state.fingerprint = fingerprint;
      return { ...common, fingerprint_version: '1.0', area: 'metadata', status: 'active',
        draft_revision: state.revision, dataset_count: datasets.length, record_count: state.records.length,
        datasets, fingerprint: mode === 'bad-fingerprint' ? '0'.repeat(64) : fingerprint };
    }
    throw new Error('Unexpected fixture tool');
  };
  const app = createMcpExpressApp();
  app.post('/mcp', async (request, response) => {
    const server = new Server({ name: 'stage-host-fixture', version: '1.0.0' }, { capabilities: { tools: {} } });
    server.setRequestHandler(ListToolsRequestSchema, async () => ({ tools: [] }));
    server.setRequestHandler(CallToolRequestSchema, async ({ params }) => {
      state.calls.push(params.name);
      try {
        const result = responseFor(params.name, params.arguments);
        if (mode === 'lost-write' && params.name === 'stage_metadata_change_set') {
          // The write happened, but its acknowledgement never reaches the client.
          response.status(502).end();
        }
        return { content: [], structuredContent: result };
      } catch {
        state.errors.push('Fixture contract mismatch');
        throw new Error('Fixture contract mismatch');
      }
    });
    const transport = new StreamableHTTPServerTransport({ sessionIdGenerator: undefined, enableJsonResponse: true });
    response.on('close', () => { void server.close(); });
    try {
      await server.connect(transport);
      await transport.handleRequest(request, response, request.body);
    } catch {
      if (!response.headersSent) response.status(500).end();
    }
  });
  const listener = app.listen(0, '127.0.0.1');
  await new Promise((resolve, reject) => { listener.once('listening', resolve); listener.once('error', reject); });
  return { state, endpoint: `http://127.0.0.1:${listener.address().port}/mcp`,
    close: () => new Promise((resolve, reject) => listener.close(error => error ? reject(error) : resolve())) };
}
module.exports = { createRequest, serveFixture, ID };
