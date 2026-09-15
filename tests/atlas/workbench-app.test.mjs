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
 assert.match(document.querySelector('.brand').textContent,/atlas/);assert.equal(document.querySelectorAll('.data-table tbody tr').length,1);
 document.querySelector('[data-row-action]').click();assert.equal(document.querySelectorAll('.data-table tbody tr').length,1);
 assert.match(document.querySelector('.comparison-panel').textContent,/Customer master/);assert.match(document.querySelector('.comparison-panel').textContent,/Customer identity used for billing/);
 assert.match(document.querySelector('.comparison-panel').textContent,/Empty string/);assert.match(document.querySelector('.comparison-panel').textContent,/null/);
 assert.ok(document.querySelector('.comparison-field.is-changed'));document.querySelector('[data-action="back-to-ledger"]').click();assert.equal(document.querySelector('.comparison-panel'),null);dom.window.close();
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
test('DBML displays the complete effective Model despite record view filters',async()=>{
 const root=workspace();state(root,{model:{id:7,name:'Sales'}});snapshot(root,'metadata',[]);snapshot(root,'model',[dataset('conceptual_object',['conceptual_object_name'],[{conceptual_object_name:'Customer',conceptual_object_status:'active',conceptual_object_type:'party'}])]);
 root.directory('model-change-set').file('conceptual_object.json',JSON.stringify([{conceptual_object_name:'Order',conceptual_object_status:'active',conceptual_object_type:'event'}]));
 const {api,document,dom}=await app(root);api.state.filters['model:conceptual_object:conceptual_object_name']=['Customer'];await api.generateDbml();
 assert.equal(api.state.screen,'dbml',api.state.message);assert.match(document.querySelector('.dbml-text').textContent,/Customer/);assert.match(document.querySelector('.dbml-text').textContent,/Order/);
 assert.ok(document.getElementById('copy-dbml'));assert.ok(document.getElementById('download-dbml'));dom.window.close();
});
test('DBML duplicate and locked edit findings stop export and open validation',async()=>{
 const root=workspace();state(root,{model:{id:7,name:'Sales'}});const row={conceptual_object_name:'Customer',conceptual_object_status:'active',conceptual_object_type:'party',conceptual_object_is_locked:true};snapshot(root,'model',[dataset('conceptual_object',['conceptual_object_name'],[row])]);
 root.directory('model-change-set').file('conceptual_object.json',JSON.stringify([{...row,conceptual_object_type:'event'},{...row,conceptual_object_type:'event'}]));
 const {api,document,dom}=await app(root);await api.generateDbml();assert.equal(api.state.screen,'validation');assert.match(document.querySelector('.issue-table').textContent,/duplicates a canonical key/);assert.equal(root.entries.has('model-dbml'),false);dom.window.close();
});
