import test from 'node:test';
import assert from 'node:assert/strict';
import {createRequire} from 'node:module';
const require = createRequire(import.meta.url);
const {planProfiling, validateBatchType} = require('../../atlas/atlas-plugin/scripts/profiling.js');
const {planAnalysis} = require('../../atlas/atlas-plugin/scripts/analysis.js');

function fixture(count = 3) {
  const object = {tenant_code:'OWNER',system_code:'CRM',connection_code:'SRC',object_schema:'dbo',object_name:'Customer',source_tenant_code:'OWNER',zone_code:'source',fc_object_schema:'remote',fc_object_name:'Customer',batch_attribute_name:'Batch'};
  return {object, metadata:{source_object:[object], source_attribute:Array.from({length:count}, (_,i) => ({...object, attribute_name:i === 0 ? 'Batch' : `Value${i}`,fc_attribute_name:i === 0 ? 'Batch' : `Value${i}`,attribute_ordinal_position:i+1,attribute_data_type:'STRING'})),tenant:[{tenant_code:'OWNER',tenant_catalog:'owner'}],connection:[{tenant_code:'OWNER',system_code:'CRM',connection_code:'SRC',foreign_catalog:'foreign'}]}};
}

function sharedStoreFixture() {
  const {metadata} = fixture();
  const object = {tenant_code:'STORE',system_code:'GDS',connection_code:'LAKE',object_schema:'bronze`crm',object_name:'Cust`omer',source_tenant_code:'OWNER',zone_code:'bronze',batch_attribute_name:null};
  metadata.tenant[0].tenant_catalog = 'target`catalog';
  metadata.tenant.push({tenant_code:'STORE',tenant_catalog:'wrong_store_catalog'});
  metadata.connection.push({tenant_code:'STORE',system_code:'GDS',connection_code:'LAKE',is_global_data_store:true});
  metadata.bronze_object = [object];
  metadata.bronze_attribute = [{...object,attribute_name:'CustomerID',attribute_ordinal_position:1,attribute_data_type:'BIGINT'}];
  const key = Object.fromEntries(['tenant_code','system_code','connection_code','object_schema','object_name'].map(field => [field,object[field]]));
  return {object,metadata,plan:{batches:{},probes:[{id:'customer_key',kind:'key',object:key,columns:['CustomerID']}]}};
}
const batch = {systems:[{source_tenant_code:'OWNER',system_code:'CRM',batch_ids:['11','10','10']}]};

test('Bronze queries use the source owner target catalog and quote every physical component', () => {
  const {object,metadata,plan} = sharedStoreFixture();
  const relation = '`target``catalog`.`bronze``crm`.`Cust``omer`';
  const profile = planProfiling(metadata,[object],{}).queries[0];
  const [analysis] = planAnalysis(metadata,[object],plan);
  assert.equal(profile.relation,relation);
  for (const query of [profile,analysis]) {
    assert.ok(query.sql.includes(`FROM ${relation}`));
    assert.ok(!query.sql.includes('wrong_store_catalog'));
  }
  assert.equal(profile.object.tenant_code,'STORE');
  assert.equal(analysis.endpoints[0].object.tenant_code,'STORE');
});

for (const invalid of ['missing owner','inactive owner','missing owner code','null catalog','empty catalog','blank catalog']) {
  test(`Bronze queries reject ${invalid} instead of using the GDS placement catalog`, () => {
    const {object,metadata,plan} = sharedStoreFixture();
    if (invalid === 'missing owner') metadata.tenant.shift();
    else if (invalid === 'inactive owner') metadata.tenant[0].is_active = false;
    else if (invalid === 'missing owner code') delete object.source_tenant_code;
    else metadata.tenant[0].tenant_catalog = {'null catalog':null,'empty catalog':'','blank catalog':'  '}[invalid];
    assert.throws(() => planProfiling(metadata,[object],{}), /catalog|owner|Tenant|coordinate/i);
    assert.throws(() => planAnalysis(metadata,[object],plan), /catalog|owner|Tenant|coordinate/i);
  });
}

test('Source queries retain registered foreign catalog coordinates instead of the target catalog', () => {
  const {object,metadata} = fixture();
  object.batch_attribute_name = null;
  object.fc_object_schema = 'remote`schema';
  object.fc_object_name = 'Cust`omer';
  metadata.connection[0].foreign_catalog = 'foreign`catalog';
  const key = Object.fromEntries(['tenant_code','system_code','connection_code','object_schema','object_name'].map(field => [field,object[field]]));
  const plan = {batches:{},probes:[{id:'source_key',kind:'key',object:key,columns:['Value1']}]};
  const profile = planProfiling(metadata,[object],{}).queries[0];
  const [analysis] = planAnalysis(metadata,[object],plan);
  const relation = '`foreign``catalog`.`remote``schema`.`Cust``omer`';
  assert.equal(profile.relation,relation);
  for (const query of [profile,analysis]) assert.ok(query.sql.includes(`FROM ${relation}`));
  metadata.connection[0].foreign_catalog = '';
  assert.throws(() => planProfiling(metadata,[object],{}), /catalog|coordinate/i);
  assert.throws(() => planAnalysis(metadata,[object],plan), /catalog|coordinate/i);
});

test('batch lists stay complete across bounded groups and produce deterministic SQL', () => {
  const {object,metadata} = fixture(71);
  const a = planProfiling(metadata,[object],batch);
  const b = planProfiling(metadata,[object],{systems:[{source_tenant_code:'OWNER',system_code:'CRM',batch_ids:['10','11']}]});
  assert.deepEqual(a,b);
  assert.equal(a.queries.length,2);
  for (const query of a.queries) {
    assert.deepEqual(query.batch_ids,['10','11']);
    assert.match(query.sql,/WHERE `Batch` IN \(/);
    assert.match(query.sql,/X'3130'/);
    assert.match(query.sql,/X'3131'/);
    assert.ok(query.attributes.length <= 50);
  }
});

test('missing batches fail; truly unbatched Objects omit the filter', () => {
  const {object,metadata} = fixture();
  assert.throws(() => planProfiling(metadata,[object],{}), /Batch IDs are required/);
  assert.throws(() => planProfiling(metadata,[object],{systems:[{source_tenant_code:'OWNER',system_code:'CRM',batch_ids:[]}]}), /nonempty list/);
  object.batch_attribute_name = null;
  assert.doesNotMatch(planProfiling(metadata,[object],{}).queries[0].sql,/WHERE/);
});

test('SQL-literal batch text is encoded and analysis uses identical batch scope', () => {
  const {object,metadata} = fixture();
  const value = "x') OR 1=1 --";
  const batches = {systems:[{source_tenant_code:'OWNER',system_code:'CRM',batch_ids:[value]}]};
  const keys = Object.fromEntries(['tenant_code','system_code','connection_code','object_schema','object_name'].map((key) => [key,object[key]]));
  const [query] = planAnalysis(metadata,[object],{batches,probes:[{id:'customer_key',kind:'key',object:keys,columns:['Value1']}]});
  assert.match(query.sql,/WHERE `Batch` IN \(/);
  assert.ok(!query.sql.includes(value));
  assert.match(query.sql,new RegExp(Buffer.from(value).toString('hex')));
  assert.equal(query.scope,'selected_batches');
});

test('physical batch values reject overflow, rounding, invalid dates and ambiguous timestamp zones', () => {
  for (const [type, accepted, rejected] of [
    ['BIGINT',['9223372036854775807','-9223372036854775808'],['9223372036854775808','-9223372036854775809','1.0']],
    ['TINYINT',['127','-128'],['128','-129']],
    ['DECIMAL(5,2)',['999.99','0001.2300'],['1000.00','1.001']],
    ['DECIMAL(38,0)',['9'.repeat(38)],['9'.repeat(39)]],
    ['DATE',['2024-02-29','2000-02-29'],['2023-02-29','1900-02-29','2024-04-31','0000-01-01']],
    ['TIMESTAMP',['2024-02-29T12:30:59.123456Z'],['2024-02-29 12:30:59','2024-02-29T24:00:00Z','2024-02-29T00:00:00.1234567Z']],
    ['TIMESTAMP_NTZ',['2024-02-29 12:30:59'],['2024-02-29T12:30:59Z']],
    ['VARCHAR(2)',['ab','😀😀'],['abc']],
    ['BOOLEAN',['true','FALSE'],['1','yes']],
    ['DOUBLE',[],['0.1','1']],
  ]) {
    for (const value of accepted) assert.doesNotThrow(() => validateBatchType([value],type), `${type}: ${value}`);
    for (const value of rejected) assert.throws(() => validateBatchType([value],type), /converted exactly/, `${type}: ${value}`);
  }
  const {object,metadata} = fixture();
  metadata.source_attribute[0].attribute_data_type = 'TINYINT';
  assert.throws(() => planProfiling(metadata,[object],{systems:[{source_tenant_code:'OWNER',system_code:'CRM',batch_ids:['128']}]}), /converted exactly/);
});

test('Bronze with protected Source lineage is excluded even when mapping is empty or custom code renames it', () => {
  const {object,metadata} = fixture();
  metadata.source_attribute[1].is_masking_required = true;
  metadata.source_attribute[1].attribute_custom_code = 'Value1 AS Renamed';
  const bronze = {...object, connection_code:'STORE', zone_code:'bronze', object_schema:'bronze', batch_attribute_name:null};
  metadata.bronze_object = [bronze];
  metadata.bronze_attribute = [{...bronze, attribute_name:'Renamed',attribute_data_type:'STRING',attribute_ordinal_position:1}];
  metadata.connection.push({tenant_code:'OWNER',system_code:'CRM',connection_code:'STORE'});
  const mapping = Object.fromEntries(['tenant_code','system_code','connection_code','object_schema','object_name'].flatMap(field => [[`source_${field}`,object[field]],[`target_${field}`,bronze[field]]]));
  for (const mappings of [[],[mapping],[{...mapping,is_active:false}]]) {
    metadata.ingestion_object_mapping = mappings;
    const result = planProfiling(metadata,[bronze],{});
    assert.equal(result.queries.length,0);
    assert.equal(result.coverage[0].excluded[0].reason,'unproven_masking_lineage');
    const key = Object.fromEntries(['tenant_code','system_code','connection_code','object_schema','object_name'].map(field => [field,bronze[field]]));
    assert.throws(() => planAnalysis(metadata,[bronze],{batches:{},probes:[{id:'protected',kind:'key',object:key,columns:['Renamed']}]}), /Masked Attributes/);
  }
});

test('join endpoints retain independent batches and unbatched scope', () => {
  const {object,metadata} = fixture();
  const orders = {...object,object_name:'Orders',fc_object_name:'Orders',batch_attribute_name:null};
  metadata.source_object.push(orders);
  metadata.source_attribute.push({...orders,attribute_name:'CustomerID',fc_attribute_name:'CustomerID',attribute_data_type:'STRING',attribute_ordinal_position:1});
  const key = row => Object.fromEntries(['tenant_code','system_code','connection_code','object_schema','object_name'].map(field => [field,row[field]]));
  const plan = {batches:batch, probes:[{id:'customer_orders',kind:'join',
    from:{object:key(orders),columns:['CustomerID']},to:{object:key(object),columns:['Value1']}}]};
  const [query] = planAnalysis(metadata,[orders,object],plan);
  assert.equal(query.endpoints[0].batch,null);
  assert.deepEqual(query.endpoints[1].batch.values,['10','11']);
  assert.equal(query.sql.match(/WHERE `Batch` IN/g).length,1);
  assert.deepEqual(planProfiling(metadata,[orders,object],batch),planProfiling(metadata,[object,orders],batch));
});
