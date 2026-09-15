import { createHash } from 'node:crypto';
export const hash = text => createHash('sha256').update(text).digest('hex');
export class File {
  constructor(name, text = '') { this.kind = 'file'; this.name = name; this.text = text; }
  async getFile() { const text = this.text; return { arrayBuffer: async () => new TextEncoder().encode(text).buffer }; }
  async createWritable() { let value; return { write: async text => { value = text; }, close: async () => { this.text = value; }, abort: async () => {} }; }
}
export class Directory {
  constructor(name = 'workspace') { this.kind = 'directory'; this.name = name; this.entries = new Map(); }
  directory(name) { const value = new Directory(name); this.entries.set(name, value); return value; }
  file(name, text = '') { const value = new File(name, text); this.entries.set(name, value); return value; }
  async getDirectoryHandle(name, {create} = {}) { const value = this.entries.get(name); if (value?.kind === 'directory') return value; if (create) return this.directory(name); throw new DOMException('Missing directory', 'NotFoundError'); }
  async getFileHandle(name, {create} = {}) { const value = this.entries.get(name); if (value?.kind === 'file') return value; if (create) return this.file(name); throw new DOMException('Missing file', 'NotFoundError'); }
  async *values() { yield* this.entries.values(); }
  async removeEntry(name) { this.entries.delete(name); }
}
export function workspace() {
  const root = new Directory(); const atlas = root.directory('.atlas');
  atlas.file('session.json', JSON.stringify({ schema_version: '1.0', tenant: {id:1, code:'T'}, model:null, active_task:'00000000-0000-4000-8000-000000000001' }));
  atlas.directory('tasks').file('00000000-0000-4000-8000-000000000001.json', JSON.stringify({schema_version:'1.0', outcome:'Review synthetic changes'}));
  return root;
}
export function state(root, update) { const file = root.entries.get('.atlas').entries.get('session.json'); file.text = JSON.stringify({...JSON.parse(file.text), ...update}); }
export function snapshot(root, area, datasets = [], tenant = 'T') {
  let areaDir = root.entries.get(area); if (!areaDir) areaDir = root.directory(area);
  const dir = areaDir.directory(`${area}-snapshot`), data = dir.directory('data'), schemas = dir.directory('schemas');
  const members = [], definitions = [];
  for (const dataset of datasets) {
    const rows = dataset.rows.map(row => JSON.stringify(row)).join('\n') + '\n';
    const schema = JSON.stringify(dataset.schema || {type:'object', 'x-gds-change-set-eligible':true, properties:{}, additionalProperties:true});
    data.file(`${dataset.name}.jsonl`, rows); schemas.file(`${dataset.name}.schema.json`, schema);
    members.push({path:`data/${dataset.name}.jsonl`,size_bytes:Buffer.byteLength(rows),sha256:hash(rows)}, {path:`schemas/${dataset.name}.schema.json`,size_bytes:Buffer.byteLength(schema),sha256:hash(schema)});
    definitions.push({name:dataset.name,record_type:dataset.name,canonical_key:dataset.keys,row_count:dataset.rows.length,rows_file:`data/${dataset.name}.jsonl`,schema_file:`schemas/${dataset.name}.schema.json`});
  }
  const model = area === 'model' ? {model_id:7, model_name:'Sales', model_revision:1,tenant_code:tenant} : undefined;
  const catalog = JSON.stringify({snapshot_kind:area,model,sections:[{name:area,datasets:definitions}]});
  dir.file('catalog.json', catalog); members.unshift({path:'catalog.json',size_bytes:Buffer.byteLength(catalog),sha256:hash(catalog)});
  dir.file('manifest.json', JSON.stringify({snapshot_kind:area,snapshot_id:`${area}-snapshot`,tenant_code:tenant,...model,catalog:{path:'catalog.json',sha256:hash(catalog)},members}));
  return dir;
}
export function dataset(name, keys, rows) { return {name,keys,rows}; }
