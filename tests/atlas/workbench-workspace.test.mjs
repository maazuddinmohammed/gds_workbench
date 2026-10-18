import assert from 'node:assert/strict';
import test from 'node:test';
import { createRequire } from 'node:module';
import { workspace, state, snapshot, dataset, Directory } from './workbench-fixture.mjs';
const require = createRequire(import.meta.url);
const {connect,validateSession} = require('../../atlas/atlas-plugin/workbench/workspace.js');
const dbml = require('../../atlas/atlas-plugin/workbench/dbml.js');
const common = require('../../atlas/atlas-plugin/workbench/validation/common.js');
const source = dataset('source_object',['tenant_code','object_name'],[{tenant_code:'T',object_name:'Customer',description:'Before',is_active:true}]);
const projectFixture = root => { state(root,{project:{id:7,name:'Sales'}}); return snapshot(root,'project',[dataset('conceptual_object',['conceptual_object_name'],[{conceptual_object_name:'Customer',conceptual_object_status:'active',conceptual_object_type:'party'}])]); };

test('opening Atlas is read-only and missing optional areas are valid',async()=>{
 const root=workspace(), file=root.entries.get('.atlas').entries.get('session.json'), before=file.text;
 const ws=await connect(root); assert.equal(file.text,before); assert.equal(ws.area('project').manifest,null); assert.equal(ws.task.outcome,'Review synthetic changes');
 await assert.rejects(connect(new Directory()),/not initialized/);
});
test('invalid owner path, SQL policy and active task paths are rejected',()=>{
 const base={schema_version:'2.0',tenant:{id:1,code:'T'},project:null};
 for(const update of [{active_task:'../x'},{sql:{policy:'always'}},{metadata_owners:{2:{id:2,code:'OTHER',root:'../other'}}}]) assert.throws(()=>validateSession({...base,...update}));
});
test('sub-agent policy loads without changes and rejects ambiguous or invalid saved choices',async()=>{
 for(const policy of [{mode:'current'},{mode:'auto'},{mode:'custom',model:'Provider/Model-A:1'}]){
  const root=workspace();state(root,{subagent_policy:policy});
  const file=root.entries.get('.atlas').entries.get('session.json'),before=file.text;
  const ws=await connect(root);assert.deepEqual(ws.state.subagent_policy,policy);assert.equal(file.text,before);
 }
 const base={schema_version:'2.0',tenant:{id:1,code:'T'},project:null};
 for(const policy of [null,[],{},'auto',{mode:'AUTO'},{mode:'custom'},{mode:'current',model:null},
  {mode:'auto',fallback:'current'},{mode:'custom',model:' A'},{mode:'custom',model:'\ufeffA'},
  {mode:'custom',model:'A\nB'},{mode:'custom',model:'A'.repeat(201)}]){
  assert.throws(()=>validateSession({...base,subagent_policy:policy}),/sub-agent policy/);
 }
});
test('a conflicting Snapshot disables its area without rewriting session context',async()=>{
 const root=workspace();snapshot(root,'metadata',[source],'WRONG');projectFixture(root);
 const ws=await connect(root);assert.equal(ws.area('metadata').manifest,null);assert.match(ws.areaErrors.get('metadata'),/Tenant/);assert.equal(ws.area('project').manifest.project_id,7);
});
test('owner selection keeps Project and primary Tenant and drafts separate',async()=>{
 const root=workspace();snapshot(root,'metadata',[source]);projectFixture(root);
 const owner=root.directory('metadata-owners').directory('tenant-2');snapshot(owner,'metadata',[dataset('source_object',['tenant_code','object_name'],[{tenant_code:'OTHER',object_name:'Order'}])],'OTHER');
 state(root,{metadata_owners:{1:{id:1,code:'T',root:'.'},2:{id:2,code:'OTHER',root:'metadata-owners/tenant-2'}}});
 const ws=await connect(root);await ws.selectOwner(2);assert.equal(ws.state.tenant.id,1);assert.equal(ws.state.project.id,7);
 const loaded=await ws.loadDataset('metadata','source_object');await ws.saveDataset('metadata','source_object',JSON.stringify([{...loaded.baseline[0],description:'Added'}]),null);
 assert.equal(root.entries.has('metadata-change-set'),false);assert.equal(owner.entries.get('metadata-change-set').entries.has('source_object.json'),true);
});
test('saved edits preserve immutable snapshot and external conflicts retain newer disk content',async()=>{
 const root=workspace(), snap=snapshot(root,'metadata',[source]);const ws=await connect(root);const loaded=await ws.loadDataset('metadata','source_object');
 await ws.saveDataset('metadata','source_object',JSON.stringify([{...loaded.baseline[0],description:'Proposed'}]),null);
 const pending=root.entries.get('metadata-change-set').entries.get('source_object.json');const previous=pending.text;
 await assert.rejects(ws.saveDataset('metadata','source_object','[]',null),/external-edit conflict/);assert.equal(pending.text,previous);
 assert.match(snap.entries.get('data').entries.get('source_object.jsonl').text,/Before/);
});
test('known stale state and locked records block edits without changing the draft',async()=>{
 const root=workspace();snapshot(root,'metadata',[dataset('source_object',['tenant_code','object_name'],[{...source.rows[0],is_locked:true}])]);const ws=await connect(root);const row=(await ws.loadDataset('metadata','source_object')).baseline[0];
 await assert.rejects(ws.saveDataset('metadata','source_object',JSON.stringify([{...row,description:'Changed'}]),null),/Locked/);
 state(root,{refresh_required:[{area:'metadata',owner_tenant_id:1,reason:'Applied upstream'}]});await ws.refresh();await assert.rejects(ws.captureInputs('metadata'),/stale/);
});
test('reports bind owner, actual inputs, and retained note hashes',async()=>{
 const root=workspace();snapshot(root,'metadata',[source]);const ws=await connect(root),binding=await ws.captureInputs('metadata');
 const result=await ws.saveValidationReport('metadata',{binding,digest:binding.inputs[0].draft_digest,valid:true,issues:[],issueCount:0,truncated:false,checks:[{id:'local.schema',status:'ran'}]});
 assert.equal(result.owner_tenant_id,1);assert.match(result.path,/\.atlas\/tasks\/00000000-0000-4000-8000-000000000001.evidence\/metadata-1-validation.json/);assert.equal((await ws.loadValidationReport('metadata')).stale,false);
 root.directory('metadata-change-set').file('source_object.json','[]');assert.equal((await ws.loadValidationReport('metadata')).stale,true);
});
test('a concurrently changed draft cannot be stamped by a validation report',async()=>{
 const root=workspace();snapshot(root,'metadata',[source]);const ws=await connect(root),binding=await ws.captureInputs('metadata');root.directory('metadata-change-set').file('source_object.json','[]');
 await assert.rejects(ws.saveValidationReport('metadata',{binding,digest:binding.inputs[0].draft_digest,valid:true,issues:[],issueCount:0,truncated:false}),/changed during/);
});
test('effective DBML contains unchanged snapshot concepts and newly proposed concepts',async()=>{
 const root=workspace();projectFixture(root);root.directory('project-change-set').file('conceptual_object.json',JSON.stringify([{conceptual_object_name:'Order',conceptual_object_status:'active',conceptual_object_type:'event'}]));
 const ws=await connect(root),binding=await ws.captureInputs('project'),loaded=await ws.loadArea('project');const docs=dbml.render(loaded,ws.area('project').catalog.project);const concept=docs.find(doc=>doc.path==='conceptual.dbml');
 assert.match(concept.content,/Customer/);assert.match(concept.content,/Order/);const result=await ws.saveDbmlDocuments(docs,{binding});assert.equal(result.draft_digest,binding.inputs[0].draft_digest);
});
test('duplicate pending keys are blocking structural findings before DBML',async()=>{
 const root=workspace();projectFixture(root);const row={conceptual_object_name:'Order',conceptual_object_status:'active'};root.directory('project-change-set').file('conceptual_object.json',JSON.stringify([row,row]));
 const ws=await connect(root);assert.ok(common.validateLoaded('project',await ws.loadArea('project')).some(issue=>issue.code==='duplicate_canonical_key'));
});
test('DBML refuses changed saved inputs and missing input binding',async()=>{
 const root=workspace();projectFixture(root);const ws=await connect(root),binding=await ws.captureInputs('project');const docs=dbml.render(await ws.loadArea('project'),ws.area('project').catalog.project);
 await assert.rejects(ws.saveDbmlDocuments(docs),/captured/);root.directory('project-change-set').file('conceptual_object.json','[]');await assert.rejects(ws.saveDbmlDocuments(docs,{binding}),/changed during/);assert.equal(root.entries.has('project-dbml'),false);
});
test('DBML restores the previous export when inputs change during publication',async()=>{
 const root=workspace();projectFixture(root);const ws=await connect(root),binding=await ws.captureInputs('project');
 const docs=dbml.render(await ws.loadArea('project'),ws.area('project').catalog.project);await ws.saveDbmlDocuments(docs,{binding});
 const output=root.entries.get('project-dbml'),manifest=output.entries.get('manifest.json').text,old=output.entries.get('conceptual.dbml'),oldText=old.text;
 const writable=old.createWritable.bind(old);let changed=false;
 old.createWritable=async()=>{const stream=await writable(),close=stream.close;stream.close=async()=>{await close();if(!changed){changed=true;root.directory('project-change-set').file('conceptual_object.json','[]');}};return stream;};
 await assert.rejects(ws.saveDbmlDocuments(docs.map(doc=>({...doc,content:doc.content+'\n// changed export'})),{binding}),/changed during/);
 assert.equal(old.text,oldText);assert.equal(output.entries.get('manifest.json').text,manifest);
});
test('unknown conceptual cardinality has an annotation, never a false one-to-one connector',()=>{
 const row=name=>({conceptual_object_name:name,conceptual_object_status:'active'});
 const docs=dbml.render(new Map([['conceptual_object',{effective:[row('Customer'),row('Order')]}],['conceptual_relationship',{effective:[{from_conceptual_object_name:'Customer',to_conceptual_object_name:'Order',conceptual_relationship_name:'Places',conceptual_relationship_status:'active',conceptual_relationship_cardinality:'unknown'}]}]]),{project_id:7,project_name:'Sales',project_revision:1});
 assert.match(docs[0].content,/Connector omitted/);assert.doesNotMatch(docs[0].content,/Ref conceptual_relationship/);
});

test('Project context aggregates all owners and never uses their pending Metadata',async()=>{
 const root=workspace();snapshot(root,'metadata',[source]);projectFixture(root);
 const owner=root.directory('metadata-owners').directory('tenant-2');snapshot(owner,'metadata',[dataset('source_object',['tenant_code','object_name'],[{tenant_code:'OTHER',object_name:'Order'}])],'OTHER');
 owner.directory('metadata-change-set').file('source_object.json',JSON.stringify([{tenant_code:'OTHER',object_name:'PendingOnly'}]));
 state(root,{metadata_owners:{1:{id:1,code:'T',root:'.'},2:{id:2,code:'OTHER',root:'metadata-owners/tenant-2'}}});
 const ws=await connect(root);await ws.selectOwner(2);const context=await ws.loadProjectMetadata();
 assert.deepEqual(context.loaded.get('source_object').baseline.map(row=>row.object_name),['Customer','Order']);assert.equal(context.inputs.length,2);
 assert.ok(context.inputs.some(input=>input.manifest_path.startsWith('metadata-owners/tenant-2/')));
 const binding=await ws.captureInputs('project');binding.inputs.push(...context.inputs);await ws.assertInputsUnchanged(binding);
});
test('Metadata work binds its declared Project selection and detects changed task context',async()=>{
 const root=workspace();snapshot(root,'metadata',[source]);projectFixture(root);const ws=await connect(root);
 const projectBinding=ws.inputBinding('project',ws.owner('project'),ws.area('project'));
 const task=root.entries.get('.atlas').entries.get('tasks').entries.get('00000000-0000-4000-8000-000000000001.json');
 task.text=JSON.stringify({schema_version:'2.0',outcome:'Enrich Project scope',inputs:{snapshots:[projectBinding]}});
 const binding=await ws.captureInputs('metadata');assert.equal(binding.inputs.length,2);assert.deepEqual(binding.inputs[1],projectBinding);
 task.text=JSON.stringify({schema_version:'2.0',outcome:'Changed scope'});await assert.rejects(ws.assertInputsUnchanged(binding),/Task context changed/);
 task.text=JSON.stringify({schema_version:'2.0',outcome:'Enrich Project scope',inputs:{snapshots:[{...projectBinding,manifest_sha256:'0'.repeat(64)}]}});
 await assert.rejects(ws.captureInputs('metadata'),/Task Snapshot input changed/);
});
test('shared physical-record conflicts and stale owners block Project context',async()=>{
 const root=workspace();snapshot(root,'metadata',[source]);projectFixture(root);const owner=root.directory('metadata-owners').directory('tenant-2');
 snapshot(owner,'metadata',[dataset('source_object',['tenant_code','object_name'],[{...source.rows[0],description:'Conflicting owner copy'}])],'OTHER');
 state(root,{metadata_owners:{2:{id:2,code:'OTHER',root:'metadata-owners/tenant-2'}}});const ws=await connect(root);await assert.rejects(ws.loadProjectMetadata(),/disagree on a shared record/);
 state(root,{refresh_required:[{area:'metadata',owner_tenant_id:2,reason:'Applied upstream'}]});await ws.refresh();await assert.rejects(ws.loadProjectMetadata(),/needs refresh/);
});
test('operation pointer survives task switch and keeps uncertain Stage visible',async()=>{
 const root=workspace();snapshot(root,'metadata',[source]);const evidence=root.entries.get('.atlas').entries.get('tasks').directory('00000000-0000-4000-8000-000000000002.evidence');
 const operationPath='.atlas/tasks/00000000-0000-4000-8000-000000000002.evidence/00000000-0000-4000-8000-000000000003.json';evidence.file('00000000-0000-4000-8000-000000000003.json',JSON.stringify({schema_version:'2.0',id:'00000000-0000-4000-8000-000000000003',task_id:'00000000-0000-4000-8000-000000000002',area:'metadata',owner:{id:1,code:'T',root:'.'},local_digest:'0'.repeat(64),stage_attempt:{status:'unknown'}}));
 state(root,{operations:{metadata:{1:operationPath}}});const ws=await connect(root),operation=await ws.loadOperation('metadata');assert.equal(operation.uncertain,true);assert.equal(operation.historical,true);assert.match(operation.status,/unknown/);
});


test('operation status accepts canonical and legacy Stage proof but never conflicting fields',async()=>{
 const root=workspace();snapshot(root,'metadata',[source]);
 const task='00000000-0000-4000-8000-000000000002',id='00000000-0000-4000-8000-000000000003';
 const evidence=root.entries.get('.atlas').entries.get('tasks').directory(`${task}.evidence`);
 const operationPath=`.atlas/tasks/${task}.evidence/${id}.json`;
 state(root,{operations:{metadata:{1:operationPath}}});const ws=await connect(root);
 for(const [stage,verified] of [
   [{fingerprint_verified:true},true], [{fingerprintVerified:true},true],
   [{fingerprint_verified:true,fingerprintVerified:true},true],
   [{fingerprint_verified:false,fingerprintVerified:true},false],
   [{fingerprint_verified:true,fingerprintVerified:false},false],
   [{fingerprint_verified:true,fingerprintVerified:null},false],
   [{fingerprint_verified:false},false], [{},false],
 ]) {
   evidence.file(`${id}.json`,JSON.stringify({schema_version:'2.0',id,task_id:task,area:'metadata',owner:{id:1,code:'T',root:'.'},local_digest:'0'.repeat(64),stage}));
   assert.equal((await ws.loadOperation('metadata')).status,verified?'Staged receipt recorded':'Local operation');
 }
});
test('local Change Set digest orders files ordinally like PowerShell and Stage Runner',async()=>{
 const root=workspace(),keys=['tenant_code','name'];
 snapshot(root,'metadata',[dataset('copy',keys,[]),dataset('copy_group',keys,[])]);
 const changes=root.directory('metadata-change-set');
 const copy=JSON.stringify([{tenant_code:'T',name:'a'}]),group=JSON.stringify([{tenant_code:'T',name:'b'}]);
 changes.file('copy_group.json',group);changes.file('copy.json',copy);
 const ws=await connect(root);
 const {createHash}=await import('node:crypto');
 // Ordinal: '.' (U+002E) sorts before '_' (U+005F); ICU localeCompare reverses these names.
 const expected=createHash('sha256');
 for(const [name,text] of [['copy.json',copy],['copy_group.json',group]]) expected.update(`${name}\0${Buffer.byteLength(text)}\0`).update(text);
 assert.equal(await ws.localChangeSetDigest('metadata'),expected.digest('hex'));
});
