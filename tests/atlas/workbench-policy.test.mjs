import assert from 'node:assert/strict';
import test from 'node:test';
import { createRequire } from 'node:module';
const require=createRequire(import.meta.url);
const {validate,AUDIT}=require('../../atlas/atlas-plugin/workbench/validation/model-policy.js');
const run=require('../../atlas/atlas-plugin/workbench/validation/run.js').run;
const loaded=(name,keys,pending=[],baseline=[])=>[name,{definition:{name,canonical_key:keys},schema:{type:'object','x-gds-change-set-eligible':true,properties:{}},pending,baseline,effective:[...baseline,...pending]}];
const phys={tenant_code:'T',system_code:'CRM',connection_code:'C',object_schema:'bronze',object_name:'Customer'};
function graph(layer='logical'){
 const entity={[`${layer}_entity_name`]:'Customer',[`${layer}_entity_status`]:'active',sources:[],submodels:[]};
 const column=(name,ordinal,audit=false)=>({[`${layer}_entity_name`]:'Customer',[`${layer}_attribute_name`]:name,[`${layer}_attribute_status`]:'active',[`${layer}_attribute_data_type`]:'BIGINT',[`${layer}_attribute_ordinal_position`]:ordinal,[`${layer}_attribute_is_nullable`]:false,[`${layer}_attribute_is_audit_column`]:audit,sources:[]});
 const surrogate={...column(layer==='logical'?'CustomerID':'CustomerKey',1),...(layer==='logical'?{logical_attribute_is_primary_key:true,logical_attribute_is_surrogate_key:true,logical_attribute_is_natural_key:false}:{dimensional_attribute_key_role:'surrogate'})};
 const attributes=[surrogate,...AUDIT.map((name,index)=>column(name,index+2,true))];
 return new Map([loaded(`${layer}_entity`,[`${layer}_entity_name`],[entity]),loaded(`${layer}_attribute`,[`${layer}_entity_name`,`${layer}_attribute_name`],attributes)]);
}
const codes=result=>result.filter(issue=>issue.severity!=='warning').map(issue=>issue.code);
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
 const entity={logical_entity_name:'legacy_table',logical_entity_status:'active',sources:[],submodels:[]};
 const value=new Map([loaded('logical_entity',['logical_entity_name'],[],[entity])]);assert.deepEqual(codes(validate(value)),[]);
});
test('inactive submodel and missing parent Object source have distinct checks',()=>{
 const value=graph();value.get('logical_entity').pending[0].submodels=[{submodel_name:'Sales',membership_status:'active'}];
 value.set(...loaded('logical_submodel',['logical_submodel_name'],[{logical_submodel_name:'Sales',logical_submodel_status:'inactive'}]));
 assert.ok(codes(validate(value)).includes('model.membership-state'));
});
test('existing bindings cannot silently change physical targets',()=>{
 const old={modeled_entity_type:'logical_entity',modeled_entity_name:'Customer',...phys};
 const value=new Map([loaded('model_object_binding',['modeled_entity_type','modeled_entity_name'],[{...old,object_name:'Other'}],[old])]);
 assert.ok(codes(validate(value)).includes('binding.reassignment-unsupported'));
});
test('default Mapping documents require real inputs, aliases, steps and field rules',()=>{
 const branch={modeled_entity_type:'logical_entity',modeled_entity_name:'Customer',source_system_code:'CRM'};
 const object={...branch,object_mapping_status:'active',output_template_code:'mapping_object_default',mapping_transformation_document:{source_objects:[{...phys,alias:'c'},{...phys,alias:'c'}],steps:[]}};
 const attribute={...branch,modeled_attribute_name:'Name',attribute_mapping_status:'active',attribute_mapping_transformation_document:{source_attributes:[],transformation:''}};
 const value=new Map([loaded('mapping_object',Object.keys(branch),[object]),loaded('mapping_attribute',[...Object.keys(branch),'modeled_attribute_name'],[attribute])]);
 const result=codes(validate(value));assert.ok(result.includes('mapping.object-steps'));assert.ok(result.includes('mapping.attribute-rule'));
 object.mapping_transformation_document.steps=['Read c and preserve one row per customer.'];assert.ok(codes(validate(value)).includes('mapping.source-alias'));
});
test('shared run reports skipped evidence and server-only checks without claiming business proof',()=>{
 const result=run('model',new Map(),null,{includeQuality:false});assert.equal(result.valid,true);
 assert.ok(result.checks.some(check=>check.id==='local.evidence'&&check.status==='not_run'));
 assert.ok(result.checks.some(check=>check.id==='local.meaning'&&check.status==='review_required'));
 assert.ok(result.checks.some(check=>check.id==='server.authorization'&&check.status==='server_only'));
});
