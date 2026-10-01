import assert from 'node:assert/strict';
import test from 'node:test';
import { createRequire } from 'node:module';
const require=createRequire(import.meta.url);
const {validate,AUDIT}=require('../../atlas/atlas-plugin/workbench/validation/model-policy.js');
const run=require('../../atlas/atlas-plugin/workbench/validation/run.js').run;
const loaded=(name,keys,pending=[],baseline=[])=>[name,{definition:{name,canonical_key:keys},schema:{type:'object','x-gds-change-set-eligible':true,properties:{}},pending,baseline,effective:[...baseline,...pending]}];
const phys={tenant_code:'T',system_code:'CRM',connection_code:'C',object_schema:'bronze',object_name:'Customer'};
function graph(layer='logical'){
 const entity={[`${layer}_entity_schema_name`]:'silver',[`${layer}_entity_name`]:'Customer',[`${layer}_entity_status`]:'active',sources:[],submodels:[]};
 const column=(name,ordinal,audit=false)=>({[`${layer}_entity_schema_name`]:'silver',[`${layer}_entity_name`]:'Customer',[`${layer}_attribute_name`]:name,[`${layer}_attribute_status`]:'active',[`${layer}_attribute_data_type`]:'BIGINT',[`${layer}_attribute_ordinal_position`]:ordinal,[`${layer}_attribute_is_nullable`]:false,[`${layer}_attribute_is_audit_column`]:audit,sources:[]});
 const surrogate={...column(layer==='logical'?'CustomerID':'CustomerKey',1),...(layer==='logical'?{logical_attribute_is_surrogate_key:true,logical_attribute_is_natural_key:false}:{dimensional_attribute_key_role:'surrogate'})};
 const attributes=[surrogate,...AUDIT.map((name,index)=>column(name,index+2,true))];
 return new Map([loaded(`${layer}_entity`,[`${layer}_entity_schema_name`,`${layer}_entity_name`],[entity]),loaded(`${layer}_attribute`,[`${layer}_entity_schema_name`,`${layer}_entity_name`,`${layer}_attribute_name`],attributes)]);
}
const codes=result=>result.filter(issue=>issue.severity!=='warning').map(issue=>issue.code);
test('Model Change Sets preserve the web-owned Logical SCD setting', () => {
  for (const original of [null, 'type_1', 'type_2']) {
    for (const proposed of [null, 'type_1', 'type_2']) {
      const baseline = {model_name: 'Sales', logical_entity_scd_type: original};
      const pending = {...baseline, model_purpose: 'Updated purpose', logical_entity_scd_type: proposed};
      const value = new Map([loaded('model_details', [], [pending], [baseline])]);
      assert.equal(codes(validate(value)).includes('model_policy_read_only'), original !== proposed);
    }
  }
  const baseline = {model_name: 'Sales'};
  const value = new Map([loaded('model_details', [], [{...baseline, logical_entity_scd_type: null}], [baseline])]);
  assert.deepEqual(codes(validate(value)), []);
});
test('new Logical and Dimensional entities share first generated surrogate and audit policy',()=>{
 for(const layer of ['logical','dimensional']){const value=graph(layer);assert.deepEqual(codes(validate(value)),[]);value.get(`${layer}_attribute`).pending[0][`${layer}_attribute_ordinal_position`]=3;assert.ok(codes(validate(value)).includes('model.own-surrogate'));}
});
test('audit completeness and framework-owned lineage have separate explicit findings',()=>{
 const value=graph();value.get('logical_attribute').effective.pop();value.get('logical_attribute').pending[2].sources=[{support_source_type:'attribute',source_attribute:{...phys,attribute_name:'Flag'},status:'active'}];
 const result=codes(validate(value));assert.ok(result.includes('model.audit-order'));assert.ok(result.includes('model.framework-source'));assert.ok(result.includes('model.parent-source'));
});
test('new names honor default and retain explicit override for review',()=>{
 const value=graph();value.get('logical_attribute').pending[0].logical_attribute_name='customer_id';assert.ok(codes(validate(value)).includes('model.naming-policy'));
 value.set(...loaded('model_details',['model_name'],[{model_name:'Sales',silver_model_naming_instructions:'Use snake_case for this approved model.'}]));
 const result=validate(value);assert.equal(codes(result).includes('model.naming-policy'),false);assert.ok(result.some(issue=>issue.code==='model.naming-review'));
});
test('unchanged historical layout is not rewritten to the new table defaults',()=>{
 const entity={logical_entity_schema_name: "silver", logical_entity_name:'legacy_table',logical_entity_status:'active',sources:[],submodels:[]};
 const value=new Map([loaded('logical_entity',['logical_entity_name'],[],[entity])]);assert.deepEqual(codes(validate(value)),[]);
});
test('inactive submodel and missing parent Object source have distinct checks',()=>{
 const value=graph();value.get('logical_entity').pending[0].submodels=[{submodel_name:'Sales',membership_status:'active'}];
 value.set(...loaded('logical_submodel',['logical_submodel_name'],[{logical_submodel_name:'Sales',logical_submodel_status:'inactive'}]));
 assert.ok(codes(validate(value)).includes('model.membership-state'));
});

test('default Mapping documents require real inputs, aliases, steps and field rules',()=>{
 const branch={modeled_entity_type:'logical_entity',modeled_entity_schema_name: "silver", modeled_entity_name:'Customer',source_system_code:'CRM'};
 const object={...branch,object_mapping_status:'active',output_template_code:'mapping_object_default',mapping_transformation_document:{source_objects:[{...phys,alias:'c'},{...phys,alias:'c'}],steps:[]}};
 const attribute={...branch,modeled_attribute_name:'Name',attribute_mapping_status:'active',attribute_mapping_transformation_document:{source_attributes:[],transformation:''}};
 const value=new Map([loaded('mapping_object',Object.keys(branch),[object]),loaded('mapping_attribute',[...Object.keys(branch),'modeled_attribute_name'],[attribute])]);
 const result=codes(validate(value));assert.ok(result.includes('mapping.object-steps'));assert.ok(result.includes('mapping.attribute-rule'));
 object.mapping_transformation_document.steps=['Read c and preserve one row per customer.'];assert.ok(codes(validate(value)).includes('mapping.source-alias'));
});
test('partial Mapping policy accepts explicit blanks and validates returned Attribute evidence', () => {
  const branch={modeled_entity_type:'logical_entity',modeled_entity_schema_name:'silver',modeled_entity_name:'Customer',source_system_code:'CRM'};
  const object={...branch,object_mapping_status:'active',mapping_transformation_document:null};
  const attribute={...branch,modeled_attribute_name:'ID',attribute_mapping_status:'active',attribute_mapping_transformation_document:{source_attributes:[{...phys,attribute_name:'CustomerID'}],transformation:'Use source CustomerID.'}};
  const value=new Map([loaded('mapping_object',Object.keys(branch),[object]),loaded('mapping_attribute',[...Object.keys(branch),'modeled_attribute_name'],[attribute])]);
  const metadata=new Map([loaded('source_attribute',[],[],[{...phys,attribute_name:'CustomerID'}])]);
  assert.deepEqual(codes(validate(value,metadata)),[]);
  attribute.attribute_mapping_transformation_document.source_attributes[0].attribute_name='Missing';
  assert.ok(codes(validate(value,metadata)).includes('mapping.attribute-exists'));
  attribute.attribute_mapping_transformation_document=null;
  assert.deepEqual(codes(validate(value,metadata)),[]);
  object.mapping_transformation_document={steps:['Read customer rows.'],source_objects:[]};
  assert.deepEqual(codes(validate(value,metadata)),[]);
});
test('shared run reports skipped evidence and server-only checks without claiming business proof',()=>{
 const result=run('model',new Map(),null,{includeQuality:false});assert.equal(result.valid,true);
 assert.ok(result.checks.some(check=>check.id==='local.evidence'&&check.status==='not_run'));
 assert.ok(result.checks.some(check=>check.id==='local.meaning'&&check.status==='review_required'));
 assert.ok(result.checks.some(check=>check.id==='server.authorization'&&check.status==='server_only'));
});

test('Logical Mapping combines physical input and schema-qualified Logical lookup with distinct aliases', () => {
  const lookup = {logical_entity_schema_name:'silver',logical_entity_name:'Customer'};
  const branch = {modeled_entity_type:'logical_entity',modeled_entity_schema_name:'silver',modeled_entity_name:'Order',source_system_code:'CRM'};
  const object = {...branch,object_mapping_status:'active',mapping_transformation_document:{source_objects:[{...phys,alias:'src'}],source_logical_entities:[{...lookup,alias:'customer'}],steps:['Resolve the surrogate from Customer using source customer ID.']}};
  const attribute = {...branch,modeled_attribute_name:'CustomerID',attribute_mapping_status:'active',attribute_mapping_transformation_document:{source_attributes:[{...phys,attribute_name:'CustomerID'}],source_logical_attributes:[{...lookup,logical_attribute_name:'CustomerID'}],transformation:'Return customer.CustomerID.'}};
  const value = new Map([
    loaded('logical_entity',Object.keys(lookup),[],[{...lookup,logical_entity_status:'active'}]),
    loaded('logical_attribute',[...Object.keys(lookup),'logical_attribute_name'],[],[{...lookup,logical_attribute_name:'CustomerID',logical_attribute_status:'active'}]),
    loaded('mapping_object',Object.keys(branch),[object]),
    loaded('mapping_attribute',[...Object.keys(branch),'modeled_attribute_name'],[attribute]),
  ]);
  assert.deepEqual(codes(validate(value)),[]);
  object.mapping_transformation_document.source_logical_entities[0].alias = 'src';
  assert.ok(codes(validate(value)).includes('mapping.source-alias'));
  object.mapping_transformation_document.source_logical_entities[0].alias = 'customer';
  attribute.attribute_mapping_transformation_document.source_logical_attributes[0].logical_entity_schema_name = 'other';
  assert.ok(codes(validate(value)).includes('mapping.attribute-exists'));
  assert.ok(codes(validate(value)).includes('mapping.parent-input'));
  attribute.attribute_mapping_transformation_document.source_logical_attributes[0].logical_entity_schema_name = 'silver';
  object.modeled_entity_type = attribute.modeled_entity_type = 'dimensional_entity';
  object.mapping_transformation_document.source_objects = null;
  attribute.attribute_mapping_transformation_document.source_attributes = null;
  assert.deepEqual(codes(validate(value)),[]);
});

test('all retained Entity schemas and unchanged Attribute support remain validated', () => {
  const value = new Map([
    loaded('model_details',['model_name'],[],[{model_name:'Model',logical_schemas:[],dimensional_schemas:[]}]),
    loaded('logical_entity',['logical_entity_schema_name','logical_entity_name'],[],[{logical_entity_schema_name:'retired',logical_entity_name:'Customer',logical_entity_status:'inactive'}]),
  ]);
  assert.ok(codes(validate(value)).includes('model.entity-schema'));
  delete value.get('model_details').effective[0].logical_schemas;
  assert.ok(codes(validate(value)).includes('model.entity-schema'));
  const source = {logical_entity_schema_name:'retired',logical_entity_name:'Customer'};
  value.set(...loaded('dimensional_entity',['dimensional_entity_schema_name','dimensional_entity_name'],[],[{dimensional_entity_schema_name:'gold',dimensional_entity_name:'Customer',dimensional_entity_status:'active',sources:[{support_source_type:'logical_entity',source_logical_entity:source,status:'inactive'}]}]));
  value.set(...loaded('dimensional_attribute',['dimensional_entity_schema_name','dimensional_entity_name','dimensional_attribute_name'],[],[{dimensional_entity_schema_name:'gold',dimensional_entity_name:'Customer',dimensional_attribute_name:'CustomerKey',dimensional_attribute_status:'active',sources:[{support_source_type:'logical_attribute',source_logical_attribute:{...source,logical_attribute_name:'CustomerID'},status:'active'}]}]));
  assert.ok(codes(validate(value)).includes('model.parent-source'));
});

test('Dimensional Mapping resolves peer Dimensional key lookups without physical IDs', () => {
  const upstream = {logical_entity_schema_name:'silver',logical_entity_name:'Order'};
  const peer = {dimensional_entity_schema_name:'gold',dimensional_entity_name:'Customer'};
  const branch = {modeled_entity_type:'dimensional_entity',modeled_entity_schema_name:'gold',modeled_entity_name:'SalesFact',source_system_code:'CRM'};
  const object = {...branch,object_mapping_status:'active',mapping_transformation_document:{source_objects:null,source_logical_entities:[{...upstream,alias:'orders'}],source_dimensional_entities:[{...peer,alias:'customer'}],steps:['Resolve CustomerKey from the peer Dimension.']}};
  const attribute = {...branch,modeled_attribute_name:'CustomerKey',attribute_mapping_status:'active',attribute_mapping_transformation_document:{source_attributes:null,source_logical_attributes:[],source_dimensional_attributes:[{...peer,dimensional_attribute_name:'CustomerKey'}],transformation:'Return customer.CustomerKey.'}};
  const value = new Map([
    loaded('logical_entity',Object.keys(upstream),[],[{...upstream,logical_entity_status:'active'}]),
    loaded('dimensional_entity',Object.keys(peer),[],[{...peer,dimensional_entity_status:'active'}]),
    loaded('dimensional_attribute',[...Object.keys(peer),'dimensional_attribute_name'],[],[{...peer,dimensional_attribute_name:'CustomerKey',dimensional_attribute_status:'active'}]),
    loaded('mapping_object',Object.keys(branch),[object]),loaded('mapping_attribute',[...Object.keys(branch),'modeled_attribute_name'],[attribute]),
  ]);
  assert.deepEqual(codes(validate(value)),[]);
  attribute.attribute_mapping_transformation_document.source_dimensional_attributes[0].dimensional_entity_schema_name='other_gold';
  assert.ok(codes(validate(value)).includes('mapping.attribute-exists'));
  assert.ok(codes(validate(value)).includes('mapping.parent-input'));
  object.modeled_entity_type = attribute.modeled_entity_type = 'logical_entity';
  assert.ok(codes(validate(value)).includes('mapping.source-kind'));
});

test('Model Change Sets preserve the web-owned Dimensional SCD setting', () => {
  for (const original of [null, 'type_1', 'type_2']) {
    for (const proposed of [null, 'type_1', 'type_2']) {
      const baseline = {model_name: 'Sales', dimensional_entity_scd_type: original};
      const pending = {...baseline, model_purpose: 'Updated purpose', dimensional_entity_scd_type: proposed};
      const value = new Map([loaded('model_details', [], [pending], [baseline])]);
      assert.equal(codes(validate(value)).includes('model_policy_read_only'), original !== proposed);
    }
  }
  const baseline = {model_name: 'Sales'};
  const value = new Map([loaded('model_details', [], [{...baseline, dimensional_entity_scd_type: null}], [baseline])]);
  assert.deepEqual(codes(validate(value)), []);
});
