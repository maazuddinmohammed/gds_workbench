import assert from 'node:assert/strict';
import test from 'node:test';
import {createRequire} from 'node:module';
const require = createRequire(import.meta.url);
const validation = require('../../atlas/atlas-plugin/workbench/validation/common.js');
const schema = rule => ({type:'object','x-gds-record-validation':{version:'1.0',rules:[rule]}});

test('modeled relationship identity includes schema for both endpoint comparisons', () => {
  for (const layer of ['logical','dimensional']) {
    const record = {[`from_${layer}_entity_schema_name`]:'one',[`to_${layer}_entity_schema_name`]:'two',[`from_${layer}_entity_name`]:'Customer',[`to_${layer}_entity_name`]:'Customer',[`from_${layer}_attribute_name`]:'ID',[`to_${layer}_attribute_name`]:'ID'};
    assert.deepEqual(validation.validateSchema(record,schema(`${layer}_relationship`)),[]);
    record[`to_${layer}_entity_schema_name`]=' ONE ';
    assert.ok(validation.validateSchema(record,schema(`${layer}_relationship`)).some(issue=>issue.includes('endpoints must be different')));
  }
});

test('Dimensional source uniqueness distinguishes complete Logical Entity and Attribute keys', () => {
  for (const kind of ['entity','attribute']) {
    const reference = {logical_entity_schema_name:'one',logical_entity_name:'Customer',...(kind==='attribute'?{logical_attribute_name:'ID'}:{})};
    const first = {support_source_type:`logical_${kind}`,[`source_logical_${kind}`]:reference};
    const second = {support_source_type:`logical_${kind}`,[`source_logical_${kind}`]:{...reference,logical_entity_schema_name:'two'}};
    const record = {sources:[first,second],submodels:[],dimensional_entity_type:'dimension',dimensional_fact_type:null,dimensional_attribute_is_natural_key:false,dimensional_attribute_is_surrogate_key:false,dimensional_attribute_is_audit_column:false};
    assert.deepEqual(validation.validateSchema(record,schema(`dimensional_${kind}`)),[]);
    second[`source_logical_${kind}`].logical_entity_schema_name=' ONE ';
    assert.ok(validation.validateSchema(record,schema(`dimensional_${kind}`)).some(issue=>issue.includes('sources must be unique')));
  }
});

test('Project schema configuration preserves normalized uniqueness and bounded UTF-8 size', () => {
  const record = {logical_schemas:[{schema_name:'Straße',description:null},{schema_name:'STRASSE',description:'different description'}],dimensional_schemas:[],silver_model_naming_instructions:null,gold_model_naming_instructions:null,silver_model_audit_columns_template:null,gold_model_technical_columns_template:null,gold_model_audit_columns_template:null};
  assert.ok(validation.validateSchema(record,schema('project_details_policy')).some(issue=>issue.includes('schema names must be unique')));
  record.logical_schemas = Array.from({length:100},(_,index)=>({schema_name:`schema${index}`,description:'界'.repeat(2000)}));
  assert.ok(validation.validateSchema(record,schema('project_details_policy')).some(issue=>issue.includes('262,144 JSON bytes')));
  record.logical_schemas = [{schema_name:'one',description:null},{schema_name:'two',description:null}];
  assert.deepEqual(validation.validateSchema(record,schema('project_details_policy')),[]);
});


test('modeled key flags reject dual identity and nullable keys in both layers', () => {
  for (const layer of ['logical', 'dimensional']) {
    const record = {sources: [], [`${layer}_attribute_is_natural_key`]: false, [`${layer}_attribute_is_surrogate_key`]: false, [`${layer}_attribute_is_nullable`]: true};
    assert.deepEqual(validation.validateSchema(record, schema(`${layer}_attribute`)), []);
    for (const key of ['natural', 'surrogate']) {
      record[`${layer}_attribute_is_${key}_key`] = true;
      assert.ok(validation.validateSchema(record, schema(`${layer}_attribute`)).some(issue => issue.includes('cannot be nullable')));
      record[`${layer}_attribute_is_nullable`] = false;
      assert.deepEqual(validation.validateSchema(record, schema(`${layer}_attribute`)), []);
      record[`${layer}_attribute_is_${key}_key`] = false;
      record[`${layer}_attribute_is_nullable`] = true;
    }
    record[`${layer}_attribute_is_natural_key`] = true;
    record[`${layer}_attribute_is_surrogate_key`] = true;
    record[`${layer}_attribute_is_nullable`] = false;
    assert.ok(validation.validateSchema(record, schema(`${layer}_attribute`)).some(issue => issue.includes('both natural and surrogate')));
  }
});
