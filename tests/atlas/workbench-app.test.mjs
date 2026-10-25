import assert from 'node:assert/strict';
import test from 'node:test';
import { readFile } from 'node:fs/promises';
import { createRequire } from 'node:module';
import { webcrypto } from 'node:crypto';
import { workspace, snapshot, state, dataset } from './workbench-fixture.mjs';
const require=createRequire(import.meta.url),{JSDOM}=require('jsdom');
const location=new URL('../../atlas/atlas-plugin/workbench/',import.meta.url);
async function app(root) {
 const html=await readFile(new URL('index.html',location),'utf8');
 const dom=new JSDOM(html,{runScripts:'outside-only',url:'file:///atlas/workbench/index.html'}),win=dom.window;
 win.TextEncoder=TextEncoder;win.TextDecoder=TextDecoder;Object.defineProperty(win,'crypto',{value:webcrypto});
 win.HTMLDialogElement.prototype.showModal=function(){this.open=true;};
 win.HTMLDialogElement.prototype.close=function(){this.open=false;this.dispatchEvent(new win.Event('close'));};
 for(const script of win.document.querySelectorAll('script[src]')) win.eval(await readFile(new URL(script.getAttribute('src'),location),'utf8'));
 await win.AtlasWorkbenchApp.connectDirectoryHandle(root);
 return {dom,win,document:win.document,api:win.AtlasWorkbenchApp};
}
function metadata(){const root=workspace();snapshot(root,'metadata',[dataset('source_object',['tenant_code','object_name'],[{tenant_code:'T',object_name:'Customer',description:'Customer master',empty:'',nothing:null,is_active:true}])]);return root;}

test('readable table opens a side comparison without losing table context',async()=>{
 const root=metadata();root.directory('metadata-change-set').file('source_object.json',JSON.stringify([{tenant_code:'T',object_name:'Customer',description:'Customer identity used for billing',empty:'',nothing:null,is_active:true}]));
 const {document,dom}=await app(root);
 assert.equal(document.title,'ATLAS Local Workbench');assert.equal(document.querySelector('.brand').textContent,'ATLAS');assert.equal(document.querySelectorAll('.data-table tbody tr').length,1);
 document.querySelector('[data-row-action]').click();assert.equal(document.querySelectorAll('.data-table tbody tr').length,1);
 assert.match(document.querySelector('.comparison-panel').textContent,/Customer master/);assert.match(document.querySelector('.comparison-panel').textContent,/Customer identity used for billing/);
 assert.match(document.querySelector('.comparison-panel').textContent,/Empty string/);assert.match(document.querySelector('.comparison-panel').textContent,/null/);
 assert.ok(document.querySelector('.comparison-field.is-changed'));document.querySelector('[data-action="back-to-ledger"]').click();assert.equal(document.querySelector('.comparison-panel'),null);dom.window.close();
});
test('saved sub-agent policy is visible without changing the active Project',async()=>{
 const root=metadata();state(root,{project:{id:7,name:'Sales'},subagent_policy:{mode:'custom',model:'Provider <Model-A>'}});
 const {document,dom}=await app(root);
 assert.equal(document.querySelector('.subagent-policy').textContent,'Sub-agents: Specified model only · Provider <Model-A>');
 assert.match(document.querySelector('.session-line').textContent,/Sales/);
 assert.equal(document.querySelector('.subagent-policy model-a'),null);
 dom.window.close();
 const legacy=await app(metadata());assert.equal(legacy.document.querySelector('.subagent-policy').textContent,'Sub-agents: Not set');legacy.dom.window.close();
});
test('editor asks Save Discard Cancel and preserves an unsaved conflict',async()=>{
 const root=metadata();const pending=root.directory('metadata-change-set').file('source_object.json',JSON.stringify([{tenant_code:'T',object_name:'Customer',description:'Before',is_active:true}]));
 const {document,win,dom}=await app(root);document.querySelector('[data-source="changeset"]').click();document.querySelector('[data-row-action]').click();document.querySelector('[data-action="edit-detail-draft"]').click();
 const input=document.querySelector('[data-row-field="description"]');input.value='My unsaved value';document.getElementById('close-row-editor').click();assert.equal(document.getElementById('unsaved-dialog').open,true);
 document.getElementById('unsaved-cancel').click();assert.equal(document.getElementById('row-editor-dialog').open,true);assert.equal(input.value,'My unsaved value');
 const message=document.getElementById('row-editor-message');
 const reported=new Promise((resolve,reject)=>{const observer=new win.MutationObserver(()=>{if(message.textContent){observer.disconnect();clearTimeout(timeout);resolve();}});const timeout=setTimeout(()=>{observer.disconnect();reject(new Error('Editor did not report save result.'));},3000);observer.observe(message,{childList:true,subtree:true,characterData:true});});
 pending.text='[]';document.getElementById('row-editor-form').dispatchEvent(new win.Event('submit',{cancelable:true}));await reported;
 assert.match(document.getElementById('row-editor-message').textContent,/external-edit conflict/);assert.equal(input.value,'My unsaved value');assert.equal(document.getElementById('row-editor-dialog').open,true);dom.window.close();
});
test('columns preserve identity and draft labels never claim staging',async()=>{
 const {document,dom}=await app(metadata());assert.ok(document.querySelector('.columns-menu'));assert.equal(document.querySelector('[data-column="tenant_code"]').disabled,true);
 assert.ok([...document.querySelectorAll('button')].some(button=>button.textContent==='Reload local files'));
 assert.equal([...document.querySelectorAll('button')].some(button=>['Apply','Stage'].includes(button.textContent.trim())),false);dom.window.close();
});
test('Project settings owned by the web app remain visible and read-only in the editor', async () => {
 const root=workspace();state(root,{project:{id:7,name:'Sales'}});
 const row={project_name:'Sales',project_purpose:'Customer reporting',logical_entity_scd_type:'type_2',dimensional_entity_scd_type:'type_1'};
 const definition=dataset('project_details',[],[row]);
 definition.schema={type:'object','x-gds-change-set-eligible':true,properties:{project_name:{type:'string'},project_purpose:{type:'string'},logical_entity_scd_type:{anyOf:[{type:'string',enum:['type_1','type_2']},{type:'null'}]},dimensional_entity_scd_type:{anyOf:[{type:'string',enum:['type_1','type_2']},{type:'null'}]}}};
 snapshot(root,'project',[definition]);root.directory('project-change-set').file('project_details.json',JSON.stringify([row]));
 const {api,document,dom}=await app(root);await api.switchArea('project','project_details');
 document.querySelector('[data-source="changeset"]').click();document.querySelector('[data-row-action]').click();document.querySelector('[data-action="edit-detail-draft"]').click();
 const scd=document.querySelector('[data-row-field="logical_entity_scd_type"]');
 assert.equal(scd.value,'"type_2"');assert.equal(scd.disabled,true);
 const dimensional=document.querySelector('[data-row-field="dimensional_entity_scd_type"]');
 assert.equal(dimensional.value,'"type_1"');assert.equal(dimensional.disabled,true);
 assert.match(scd.closest('.row-editor-field').textContent,/Project settings/);
 assert.equal(document.querySelector('[data-row-field="project_purpose"]').disabled,false);
 dom.window.close();
});
test('Mapping sheets expose System first and filter complete Entity/System branches', async () => {
 const root=workspace();state(root,{project:{id:7,name:'Sales'}});
 const key=['modeled_entity_type','modeled_entity_schema_name','modeled_entity_name','source_system_code'];
 const branches=['CRM','ERP'].map(source_system_code=>({modeled_entity_type:'logical_entity',modeled_entity_schema_name:'silver',modeled_entity_name:'Customer',source_system_code}));
 snapshot(root,'project',[
  dataset('mapping_object',key,branches),
  dataset('mapping_attribute',[...key,'modeled_attribute_name'],branches.map(row=>({...row,modeled_attribute_name:'CustomerID'}))),
 ]);
 const {api,document,win,dom}=await app(root);
 for(const name of ['mapping_object','mapping_attribute']){
  await api.switchArea('project',name);
  const filters=document.querySelectorAll('.multi-filter');
  assert.equal(filters[0].querySelector('summary span').textContent,'Source system');
  const crm=filters[0].querySelector('input[value="CRM"]');crm.checked=true;crm.dispatchEvent(new win.Event('change',{bubbles:true}));
  assert.equal(document.querySelectorAll('.data-table tbody tr').length,1);
  assert.match(document.querySelector('.data-table tbody').textContent,/CRM/);
  assert.doesNotMatch(document.querySelector('.data-table tbody').textContent,/ERP/);
 }
 dom.window.close();
});
test('DBML displays the complete effective Project despite record view filters',async()=>{
 const entity=name=>({logical_entity_schema_name:'silver',logical_entity_name:name,logical_entity_status:'active',submodels:[]});
 const root=workspace();state(root,{project:{id:7,name:'Sales'}});snapshot(root,'metadata',[]);snapshot(root,'project',[dataset('logical_entity',['logical_entity_schema_name','logical_entity_name'],[entity('Customer'),entity('Order')])]);
 root.directory('project-change-set').file('logical_entity.json',JSON.stringify([{...entity('Order'),logical_entity_definition:'Orders placed by customers'}]));
 const {api,document,dom}=await app(root);api.state.filters['project:logical_entity:logical_entity_name']=['Customer'];await api.generateDbml();
 assert.equal(api.state.screen,'dbml',api.state.message);const file=document.getElementById('dbml-file');file.value='logical_complete.dbml';file.dispatchEvent(new dom.window.Event('change'));
 assert.match(document.querySelector('.dbml-text').textContent,/Customer/);assert.match(document.querySelector('.dbml-text').textContent,/Orders placed by customers/);
 assert.ok(document.getElementById('copy-dbml'));assert.ok(document.getElementById('download-dbml'));dom.window.close();
});
test('DBML duplicate and locked edit findings stop export and open validation',async()=>{
 const root=workspace();state(root,{project:{id:7,name:'Sales'}});const row={subject_area_name:'Sales',subject_area_definition:'Customer orders.',subject_area_status:'active',subject_area_is_locked:true};snapshot(root,'project',[dataset('subject_area',['subject_area_name'],[row])]);
 root.directory('project-change-set').file('subject_area.json',JSON.stringify([{...row,subject_area_definition:'Orders.'},{...row,subject_area_definition:'Orders.'}]));
 const {api,document,dom}=await app(root);await api.generateDbml();assert.equal(api.state.screen,'validation');assert.match(document.querySelector('.issue-table').textContent,/duplicates a canonical key/);assert.equal(root.entries.has('project-dbml'),false);dom.window.close();
});

test('compact dataset navigation preserves groups and supports keyboard focus',async()=>{
 const root=workspace();snapshot(root,'metadata',[
  dataset('system_type',['system_type_code'],[{system_type_code:'CRM'}]),
  dataset('source_object',['tenant_code','object_name'],[{tenant_code:'T',object_name:'Customer'}]),
  dataset('source_attribute',['tenant_code','object_name','attribute_name'],[{tenant_code:'T',object_name:'Customer',attribute_name:'ID'}]),
 ]);
 const {api,document,win,dom}=await app(root);
 const definitions=api.state.workspace.area('metadata').datasets;
 definitions[0].section='Reference';definitions[1].section='Objects';definitions[2].section='Objects';
 await api.switchArea('metadata','source_object');
 assert.equal(document.querySelectorAll('.dataset-groups button').length,2);
 const sheets=document.querySelectorAll('.dataset-list button');assert.equal(sheets.length,2);
 assert.match(document.querySelector('.dataset-group.is-active').textContent,/Objects/);
 sheets[0].focus();sheets[0].dispatchEvent(new win.KeyboardEvent('keydown',{key:'ArrowRight',bubbles:true}));
 assert.equal(document.activeElement,sheets[1]);
 sheets[1].dispatchEvent(new win.KeyboardEvent('keydown',{key:'Home',bubbles:true}));assert.equal(document.activeElement,sheets[0]);
 sheets[0].dispatchEvent(new win.KeyboardEvent('keydown',{key:'ArrowDown',bubbles:true}));assert.equal(document.activeElement,sheets[1]);
 sheets[1].dispatchEvent(new win.KeyboardEvent('keydown',{key:'ArrowUp',bubbles:true}));assert.equal(document.activeElement,sheets[0]);
 assert.equal(document.querySelector('h1').textContent,'Source Object');
 assert.equal(document.querySelector('#workbench-root').getAttribute('aria-busy'),'false');
 assert.ok(document.querySelector('.brand img[src="atlas.svg"]'));dom.window.close();
});

test('Context editor creates one hidden UUID and preserves it after a failed save',async()=>{
 const root=workspace();state(root,{project:{id:7,name:'Sales'}});
 const definition=dataset('context_record',['context_record_id'],[]);
 definition.schema={type:'object','x-gds-change-set-eligible':true,additionalProperties:false,required:['context_record_id','context_group_name','context_text','source_reference','status','is_locked'],properties:{context_record_id:{type:'string',pattern:'^[0-9a-f-]{36}$'},context_group_name:{type:'string'},context_text:{type:'string',minLength:1},source_reference:{type:['string','null'],default:null},status:{type:'string',enum:['active','inactive','deprecated'],default:'active'},is_locked:{type:'boolean'}}};
 snapshot(root,'project',[definition]);const {api,document,win,dom}=await app(root);await api.switchArea('project','context_record');
 document.querySelector('[data-source="changeset"]').click();document.querySelector('[data-action="add-row"]').click();
 const id=api.state.editing.original.context_record_id;assert.match(id,/^[0-9a-f]{8}-[0-9a-f-]{27}$/);assert.equal(document.querySelector('[data-row-field="context_record_id"]'),null);
 document.querySelector('[data-row-field="context_group_name"]').value='Identity';
 const message=document.getElementById('row-editor-message');
 const failure=new Promise(resolve=>{const observer=new win.MutationObserver(()=>{if(message.textContent){observer.disconnect();resolve();}});observer.observe(message,{childList:true,subtree:true});});
 document.getElementById('row-editor-form').dispatchEvent(new win.Event('submit',{cancelable:true}));await failure;
 assert.equal(api.state.editing.original.context_record_id,id);
 document.querySelector('[data-row-field="context_text"]').value='Preserve leading zeros.';
 const saved=new Promise(resolve=>document.getElementById('row-editor-dialog').addEventListener('close',resolve,{once:true}));
 document.getElementById('row-editor-form').dispatchEvent(new win.Event('submit',{cancelable:true}));await saved;
 const records=JSON.parse(root.entries.get('project-change-set').entries.get('context_record.json').text);assert.equal(records.length,1);assert.equal(records[0].context_record_id,id);await new Promise(resolve=>setImmediate(resolve));dom.window.close();
});
