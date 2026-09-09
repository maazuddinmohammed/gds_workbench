import assert from 'node:assert/strict';
import test from 'node:test';
import {createRequire} from 'node:module';
const require = createRequire(import.meta.url);
const {planProfiling} = require('../../plugins/v2/gds/skills/gds/scripts/profiling.js');

function fixture(count = 2) {
  const source = {tenant_code:'OWNER', system_code:'CRM', connection_code:'SRC',
    object_schema:'dbo', object_name:'Customer', source_tenant_code:'OWNER', zone_code:'source',
    fc_object_schema:'remote', fc_object_name:'Customers', batch_attribute_name:'Batch', is_active:true};
  const bronze = {...source, tenant_code:'STORE', system_code:'GDS', connection_code:'LAKE',
    object_schema:'bronze', object_name:'customer', zone_code:'bronze'};
  const keys = ['tenant_code','system_code','connection_code','object_schema','object_name'];
  const attrs = (object) => Array.from({length:count}, (_,i) => ({...object,
    attribute_name:i === 0 ? 'Batch' : `Column${i}`, fc_attribute_name:i === 0 ? 'Batch Value' : `Remote${i}`,
    attribute_ordinal_position:i + 1, attribute_data_type:'STRING'}));
  const mapping = Object.fromEntries(keys.flatMap((key) => [['source_'+key,source[key]],['target_'+key,bronze[key]]]));
  return {source, bronze, metadata:{source_object:[source], bronze_object:[bronze],
    source_attribute:attrs(source), bronze_attribute:attrs(bronze),
    tenant:[{tenant_code:'OWNER',tenant_catalog:'owner'},{tenant_code:'STORE',tenant_catalog:'lake'}],
    connection:[{tenant_code:'OWNER',system_code:'CRM',connection_code:'SRC',foreign_catalog:'foreign'},
      {tenant_code:'STORE',system_code:'GDS',connection_code:'LAKE'}], ingestion_object_mapping:[mapping]}};
}

test('plans Source foreign coordinates and Bronze origin-system batches without leaking batch SQL syntax', () => {
  const {source,bronze,metadata} = fixture();
  const batch = "a' OR 1=1 --\\b";
  const queries = planProfiling(metadata,[source,bronze],{default_batch_id:null,
    systems:[{source_tenant_code:'OWNER',system_code:'CRM',batch_id:batch}]});
  assert.equal(queries.length,2);
  assert.match(queries[0].sql,/`foreign`\.`remote`\.`Customers`/);
  assert.match(queries[0].sql,/WHERE `Batch Value`/);
  assert.match(queries[1].sql,/`lake`\.`bronze`\.`customer`/);
  assert.match(queries[1].sql,/WHERE `Batch`/);
  for (const query of queries) {
    assert.equal(query.batch_id,batch);
    assert.ok(!query.sql.includes(batch));
    assert.ok(query.sql.includes(Buffer.from(batch).toString('hex')));
    assert.deepEqual(query.source_system_codes,['crm']);
    assert.equal(query.attributes[1].attribute_name,'Column1');
  }
});

test('explicit all-rows overrides batches; absent batch column omits predicate', () => {
  const {source,bronze,metadata} = fixture();
  source.batch_attribute_name = null;
  const object = Object.fromEntries(['tenant_code','system_code','connection_code','object_schema','object_name'].map(k => [k,bronze[k]]));
  const queries = planProfiling(metadata,[source,bronze],{default_batch_id:'123',objects:[{...object,batch_id:null}]});
  assert.ok(queries.every(q => q.batch_id === null && !q.sql.includes(' WHERE ')));
});

test('large scope is batched without losing Attribute identity', () => {
  const {source,metadata} = fixture(71);
  const queries = planProfiling(metadata,[source],{default_batch_id:null});
  assert.deepEqual(queries.map(q => q.attributes.length),[50,21]);
  assert.equal(queries[1].attributes[0].attribute_index,51);
  assert.equal(queries[1].attributes.at(-1).attribute_name,'Column70');
  assert.ok(queries.every(q => q.sql.length <= 100000));
});

test('ambiguous assignments and missing coordinates fail before generating evidence', () => {
  const {source,metadata} = fixture();
  const assignment = {source_tenant_code:'OWNER',system_code:'CRM',batch_id:'x'};
  assert.throws(() => planProfiling(metadata,[source],{default_batch_id:null,systems:[assignment,assignment]}),/Duplicate/);
  assert.throws(() => planProfiling(metadata,[source],{}),/default_batch_id/);
  assert.throws(() => planProfiling(metadata,[source],{default_batch_id:null,
    systems:[{...assignment,system_code:'misspelled'}]}),/Unknown batch assignment/);
  source.fc_object_name = null;
  assert.throws(() => planProfiling(metadata,[source],{default_batch_id:null}),/coordinate/);
});
