import assert from 'node:assert/strict';
import test from 'node:test';
import { createRequire } from 'node:module';
const require = createRequire(import.meta.url);
const graph = require('../../atlas/atlas-plugin/workbench/validation/model.js');
const policy = require('../../atlas/atlas-plugin/workbench/validation/model-policy.js');
const dbml = require('../../atlas/atlas-plugin/workbench/dbml.js');
const state = (records, pending = []) => ({ records, effective: records, baseline: records.filter(record => !pending.includes(record)), pending, definition: {name: 'fixture', canonical_key: []} });
const entity = schema => ({logical_entity_schema_name: schema, logical_entity_name: 'Customer', logical_entity_status: 'active', logical_entity_dependency_order: 1, submodels: []});
const attribute = schema => ({logical_entity_schema_name: schema, logical_entity_name: 'Customer', logical_attribute_name: 'CustomerID', logical_attribute_status: 'active', logical_attribute_data_type: 'BIGINT', logical_attribute_ordinal_position: 1, logical_attribute_is_nullable: false});
const mapping = schema => ({modeled_entity_type: 'logical_entity', modeled_entity_schema_name: schema, modeled_entity_name: 'Customer', source_system_code: 'CRM', object_mapping_status: 'active', mapping_transformation_document: {source_objects: [], steps: ['Use generated values.']}});

test('Mapping coverage and Code assignment cannot borrow a same-name Entity in another schema', () => {
  const branch = mapping('silver_a');
  const column = {...branch, modeled_attribute_name: 'CustomerID', attribute_mapping_status: 'active', attribute_mapping_transformation_document: {source_attributes: [], transformation: 'Generated identity.'}};
  const code = {...branch, artifact_name: 'customer.sql', generated_code_status: 'active'};
  const assignment = {...code, generated_code_source_system_status: 'active'};
  const loaded = new Map([
    ['logical_entity', state([entity('silver_a'), entity('silver_b')])],
    ['logical_attribute', state([attribute('silver_a'), attribute('silver_b')])],
    ['mapping_object', state([branch])], ['mapping_attribute', state([column])],
    ['generated_code', state([code], [code])], ['generated_code_source_system', state([assignment])],
  ]);
  assert.deepEqual(graph.validateBackendReferences(loaded), []);
  assert.deepEqual(graph.validateActiveDependencies(loaded), []);
  column.modeled_entity_schema_name = 'silver_b';
  assert.ok(graph.validateBackendReferences(loaded).some(issue => issue.dataset === 'mapping_attribute'));
  assert.ok(graph.validateActiveDependencies(loaded).some(issue => issue.message.includes('cover every')));
  column.modeled_entity_schema_name = 'silver_a';
  assignment.modeled_entity_schema_name = 'silver_b';
  assert.ok(graph.validateActiveDependencies(loaded).some(issue => issue.message.includes('exactly one')));
});

test('every Entity/System branch needs complete Attributes and exactly one Code assignment', () => {
  const systems = ['CRM', 'ERP', 'BILLING', 'SUPPORT', 'DEFAULT'];
  const entities = [entity('silver_a'), entity('silver_b')];
  const attributes = entities.flatMap(record => ['CustomerID', 'CustomerName'].map(logical_attribute_name => ({...attribute(record.logical_entity_schema_name), logical_attribute_name})));
  const objects = entities.flatMap(record => systems.map(source_system_code => ({...mapping(record.logical_entity_schema_name), source_system_code})));
  const columns = objects.flatMap(record => ['CustomerID', 'CustomerName'].map(modeled_attribute_name => ({...record, modeled_attribute_name, attribute_mapping_status:'active', attribute_mapping_transformation_document:{transformation:'Use the evidenced value or explicit generation rule.', source_attributes:[]}})));
  const artifacts = objects.map(record => ({...record, artifact_name:`${record.source_system_code}.sql`, generated_code_status:'active'}));
  const assignments = artifacts.map(record => ({...record, generated_code_source_system_status:'active'}));
  const loaded = new Map([
    ['logical_entity',state(entities)],['logical_attribute',state(attributes)],
    ['mapping_object',state(objects,objects)],['mapping_attribute',state(columns,columns)],
    ['generated_code',state(artifacts,artifacts)],['generated_code_source_system',state(assignments,assignments)],
    ['validation_group',state(systems.map(system_code=>({tenant_code:'T',system_code,validation_group_name:'Release',is_active:true})))],
    ['validation_check',state(systems.map(system_code=>({tenant_code:'T',system_code,validation_group_name:'Release',validation_check_name:'RequiredValues',is_active:true})))],
  ]);
  assert.deepEqual(graph.validateActiveDependencies(loaded), []);
  const lastColumn = columns.pop();
  assert.ok(graph.validateActiveDependencies(loaded).some(issue=>issue.message.includes('cover every')));
  columns.push(lastColumn);
  const lastAssignment = assignments.pop();
  assert.ok(graph.validateActiveDependencies(loaded).some(issue=>issue.message.includes('exactly one')));
  assignments.push(lastAssignment);
  assignments.push({...lastAssignment,artifact_name:artifacts[0].artifact_name});
  assert.ok(graph.validateActiveDependencies(loaded).some(issue=>issue.message.includes('exactly one')));
  assignments.pop();
  loaded.get('validation_group').records[0].system_code='UNMAPPED';
  assert.ok(graph.validateActiveDependencies(loaded).some(issue=>issue.dataset==='validation_group'));
  assert.ok(graph.validateActiveDependencies(loaded).some(issue=>issue.dataset==='validation_check'));
});

test('DBML renders same-name Entities with independent columns and qualified relationships', () => {
  const loaded = new Map([
    ['logical_entity', state([entity('silver_a'), entity('silver_b')])],
    ['logical_attribute', state([attribute('silver_a'), {...attribute('silver_b'), logical_attribute_name: 'ExternalID'}])],
    ['logical_relationship', state([{logical_relationship_name: 'ExternalCustomer', logical_relationship_status: 'active', logical_relationship_cardinality: 'many_to_one', from_logical_entity_schema_name: 'silver_b', from_logical_entity_name: 'Customer', from_logical_attribute_name: 'ExternalID', to_logical_entity_schema_name: 'silver_a', to_logical_entity_name: 'Customer', to_logical_attribute_name: 'CustomerID'}])],
  ]);
  const doc = dbml.render(loaded, {model_id: 42, model_revision: 1, model_name: 'Customers'}).find(doc => doc.path === 'logical_complete.dbml');
  assert.equal(doc.table_count, 2);
  assert.match(doc.content, /Table "silver_a"\."Customer"/);
  assert.match(doc.content, /Table "silver_b"\."Customer"/);
  assert.match(doc.content, /"silver_b"\."Customer"\."ExternalID" > "silver_a"\."Customer"\."CustomerID"/);
});

test('partial Mapping retains real transformations, rejects new empty pairs and keeps Code gated', () => {
  for (const shape of ['object-only', 'attribute-only', 'empty', 'existing-empty']) {
    const branch = {...mapping('silver_a'), mapping_transformation_document: shape === 'object-only' ? {steps:['Read source rows.']} : null};
    const column = {...branch, modeled_attribute_name:'CustomerID', attribute_mapping_status:'active', attribute_mapping_transformation_document: shape === 'attribute-only' ? {transformation:'Use evidenced customer ID.'} : null};
    const loaded = new Map([
      ['logical_entity', state([entity('silver_a')])],
      ['logical_attribute', state([attribute('silver_a'), {...attribute('silver_a'), logical_attribute_name:'Name'}])],
      ['mapping_object', state([branch], shape === 'existing-empty' ? [] : [branch])],
      ['mapping_attribute', state([column], [column])],
    ]);
    const issues = graph.validateActiveDependencies(loaded);
    assert.equal(issues.some(issue => issue.dataset === 'mapping_object'), shape === 'empty');
    assert.equal(issues.some(issue => issue.dataset === 'mapping_attribute'), false);
    const code = {...branch, artifact_name:'customer.sql', generated_code_status:'active'};
    loaded.set('generated_code', state([code], [code]));
    assert.ok(graph.validateActiveDependencies(loaded).some(issue => issue.dataset === 'mapping_attribute'));
  }
});

test('empty newly authored Mapping documents require null without rewriting historical or custom values', () => {
  const empty = [{}, {steps:[],source_objects:[]}, {nested:[null,{},[],' \t\n\u001c\u0085']}];
  const meaningful = [{custom:false}, {custom:0}, {custom:'\ufeff'}];
  for (const [dataset, field] of [['mapping_object','mapping_transformation_document'],['mapping_attribute','attribute_mapping_transformation_document']]) {
    for (const document of [...empty,...meaningful]) {
      const branch = {...mapping('silver_a'),output_template_code:'custom_template'};
      const column = {...branch,modeled_attribute_name:'CustomerID',attribute_mapping_status:'active',attribute_mapping_transformation_document:{custom:'real rule'}};
      const changed = {...(dataset === 'mapping_object' ? branch : column),[field]:document};
      const loaded = new Map([
        ['logical_entity',state([entity('silver_a')])],['logical_attribute',state([attribute('silver_a')])],
        ['mapping_object',state([branch])],['mapping_attribute',state([column])],
        [dataset,state([changed],[changed])],
      ]);
      const before = JSON.stringify(changed);
      assert.equal(graph.validateActiveDependencies(loaded).some(issue=>issue.code==='mapping_document_empty'),empty.includes(document));
      assert.equal(JSON.stringify(changed),before);
      loaded.get(dataset).baseline=[structuredClone(changed)];
      assert.equal(graph.validateActiveDependencies(loaded).some(issue=>issue.code==='mapping_document_empty'),false);
      assert.equal(JSON.stringify(changed),before);
    }
  }
});

test('Dimensional Mapping resolves Logical inputs with aliases and schema-qualified Attribute parents', () => {
  const branch = {...mapping('gold'), modeled_entity_type: 'dimensional_entity', mapping_transformation_document: {source_logical_entities: [{logical_entity_schema_name: 'silver_a', logical_entity_name: 'Customer', alias: 'c'}], steps: ['Read c at one row per CustomerID.']}};
  const source = {logical_entity_schema_name: 'silver_a', logical_entity_name: 'Customer', logical_attribute_name: 'CustomerID'};
  const column = {...branch, modeled_attribute_name: 'CustomerKey', attribute_mapping_status: 'active', attribute_mapping_transformation_document: {source_logical_attributes: [source], transformation: 'Return c.CustomerID.'}};
  const loaded = new Map([
    ['logical_entity', state([entity('silver_a'), entity('silver_b')])],
    ['logical_attribute', state([attribute('silver_a'), attribute('silver_b')])],
    ['mapping_object', state([branch], [branch])], ['mapping_attribute', state([column], [column])],
  ]);
  assert.deepEqual(policy.validate(loaded), []);
  source.logical_entity_schema_name = 'silver_b';
  assert.ok(policy.validate(loaded).some(issue => issue.code === 'mapping.parent-input'));
  source.logical_entity_schema_name = 'missing';
  assert.ok(policy.validate(loaded).some(issue => issue.code === 'mapping.attribute-exists'));
  source.logical_entity_schema_name = 'silver_a';
  branch.mapping_transformation_document.source_objects = [];
  assert.ok(policy.validate(loaded).some(issue => issue.code === 'mapping.source-kind'));
});

test('Entity schema remains configured when Model schemas change', () => {
  const loaded = new Map([['logical_entity', state([entity('silver_a')])], ['model_details', state([{logical_schemas: [{schema_name: 'SILVER_A', description: null}], dimensional_schemas: []}])]]);
  assert.deepEqual(policy.validate(loaded), []);
  loaded.get('model_details').effective[0].logical_schemas = [];
  assert.ok(policy.validate(loaded).some(issue => issue.code === 'model.entity-schema'));
});

test('legacy Model catalogs are rejected despite the retained archive envelope version', () => {
  const {isEntityOwnedModelCatalog} = require('../../atlas/atlas-plugin/workbench/core.js');
  const catalog = datasets => ({schema_version: '2.0', sections: [{name: 'model', datasets}]});
  assert.equal(isEntityOwnedModelCatalog(catalog([{name: 'logical_entity', canonical_key: ['logical_entity_schema_name', 'logical_entity_name']}])) , true);
  for (const layer of ['logical', 'dimensional']) {
    for (const suffix of ['entity', 'attribute', 'relationship']) assert.equal(isEntityOwnedModelCatalog(catalog([{name: `${layer}_${suffix}`, canonical_key: [`${layer}_entity_name`]}])), false);
  }
  for (const name of ['mapping_object', 'mapping_attribute', 'generated_code', 'generated_code_source_system']) assert.equal(isEntityOwnedModelCatalog(catalog([{name, canonical_key: ['modeled_entity_type', 'modeled_entity_name']}])), false);
  for (const name of ['model_object_binding', 'model_attribute_binding']) assert.equal(isEntityOwnedModelCatalog(catalog([{name, canonical_key: []}])), false);
  assert.equal(isEntityOwnedModelCatalog({sections: [{name: 'model_binding', datasets: []}]}), false);
});

test('inactive Entities reserve their schema and absent schema configuration defaults empty', () => {
  const retired = {...entity('silver_a'), logical_entity_status: 'inactive'};
  const loaded = new Map([['logical_entity', state([retired])], ['model_details', state([{logical_schemas: [], dimensional_schemas: []}])]]);
  assert.ok(policy.validate(loaded).some(issue => issue.code === 'model.entity-schema'));
  delete loaded.get('model_details').effective[0].logical_schemas;
  assert.ok(policy.validate(loaded).some(issue => issue.code === 'model.entity-schema'));
});

test('source support retirement rechecks unchanged Dimensional Attributes', () => {
  const key = {logical_entity_schema_name: 'silver_a', logical_entity_name: 'Customer'};
  const dim = {dimensional_entity_schema_name: 'gold', dimensional_entity_name: 'Customer', dimensional_entity_status: 'active', sources: [{support_source_type: 'logical_entity', source_logical_entity: key, status: 'inactive'}]};
  const col = {dimensional_entity_schema_name: 'gold', dimensional_entity_name: 'Customer', dimensional_attribute_name: 'CustomerKey', dimensional_attribute_status: 'active', sources: [{support_source_type: 'logical_attribute', source_logical_attribute: {...key, logical_attribute_name: 'CustomerID'}, status: 'active'}]};
  const loaded = new Map([['dimensional_entity', state([dim], [dim])], ['dimensional_attribute', state([col])]]);
  assert.ok(policy.validate(loaded).some(issue => issue.code === 'model.parent-source'));
});
