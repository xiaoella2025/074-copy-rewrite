const test=require('node:test'),assert=require('node:assert/strict');
const recovery=require('../assets/task_form_recovery.js');

test('unchanged autosave timestamps do not invalidate the matching attachment cache',()=>{
 const first=JSON.stringify({fields:{title:'same',shots:15},savedAt:'old'}),next=JSON.stringify({fields:{title:'same',shots:15},savedAt:'new'});
 assert.equal(recovery.draftRevision(first),recovery.draftRevision(next));
 assert.notEqual(recovery.draftRevision(first),recovery.draftRevision(JSON.stringify({fields:{title:'changed',shots:15},savedAt:'old'})));
});
test('removing or replacing only a file invalidates the old cached attachment',()=>{
 const value={fields:{title:'same'},attachments:{'prod-file':[{token:'file-A'}]}};
 const first=recovery.draftRevision(JSON.stringify(value));
 value.attachments={'prod-file':[]};assert.notEqual(recovery.draftRevision(JSON.stringify(value)),first);
 value.attachments={'prod-file':[{token:'file-B'}]};assert.notEqual(recovery.draftRevision(JSON.stringify(value)),first);
 const fs=require('node:fs'),html=fs.readFileSync('index.html','utf8');
 const capture=html.slice(html.indexOf('function saveFormDraft('),html.indexOf('async function restoreFormDraft('));
 assert.match(capture,/attachments:.*app074DraftAttachments/,'actual saved form includes file identities');
});
test('restoration applies saved image ratio after library template defaults',()=>{
 const fs=require('node:fs'),vm=require('node:vm'),html=fs.readFileSync('index.html','utf8');
 const code=html.slice(html.indexOf('async function restoreFormDraft('),html.indexOf('document.querySelectorAll(".save-form-draft")'));
 let active=0;
 const chips=[0,1].map(index=>({classList:{contains:()=>active===index},click:()=>active=index}));
 const nodes={'img-ratio':{querySelectorAll:()=>chips},'task-editor':{querySelectorAll:()=>[]},'draft-message':{},'draft-banner':{}};
 const context={formLibrariesReady:Promise.resolve(),FORM_DRAFT_KEY:'fixture',localStorage:{getItem:()=>JSON.stringify({fields:{},chips:{'img-ratio':[1]},style:0,libraryChoices:{templateId:'portrait'},toggles:[]})},
  document:{querySelector:()=>null,querySelectorAll:()=>[]},$:id=>nodes[id],restoreLibraryChoices:()=>active=0,updateShotHint(){},syncVoiceOptions(){},updateImageFallbackHint(){},syncTargetControls(){}};
 vm.createContext(context);vm.runInContext(code,context);
 return context.restoreFormDraft().then(()=>assert.equal(active,1,'manual wide ratio must survive portrait template restoration'));
});

test('reference preflight names the conflicting inner image engine even when AI drawing is selected',()=>{
 assert.match(recovery.referenceIssue({hasReference:true,source:'ai',provider:'modelscope'}),/魔搭.*产品参考图/);
 assert.match(recovery.referenceIssue({hasReference:true,source:'ai',provider:'modelscope'}),/封面/);
 assert.equal(recovery.referenceIssue({hasReference:true,source:'ai',provider:'gpt_image'}),'');
 assert.equal(recovery.referenceIssue({hasReference:true,source:'external',provider:'custom'}),'');
 assert.equal(recovery.referenceIssue({hasReference:false,source:'ai',provider:'modelscope'}),'');
 assert.match(recovery.referenceIssue({hasReference:true,source:'mine',provider:'gpt_image'}),/素材来源/);
});
test('explicit restoration waits for settings and templates, then subsequent edits are saved',async()=>{
 let complete,restores=0,saves=0,scheduled;
 const state=recovery.createRecovery({initialize:new Promise(r=>complete=r),shouldRestore:true,restore:async()=>restores++,save:async()=>saves++,schedule:fn=>(scheduled=fn,1),cancel:()=>scheduled=null});
 assert.equal(restores,0);complete();await state.ready;assert.equal(restores,1);
 state.changed();assert.equal(saves,0);await scheduled();assert.equal(saves,1);
 await state.flush();assert.equal(saves,1);
 await state.flush({force:true});assert.equal(saves,2);
});
test('typing while settings load cannot be overwritten by the old draft',async()=>{
 let complete,restores=0,saves=0;
 const state=recovery.createRecovery({initialize:new Promise(r=>complete=r),restore:async()=>restores++,save:async()=>saves++});
 state.changed();complete();await state.ready;assert.equal(restores,0);assert.equal(saves,1);
});
test('restoration events cannot save defaults over a partially restored draft',async()=>{
 let state,saves=0;
 state=recovery.createRecovery({initialize:Promise.resolve(),shouldRestore:true,restore:async()=>state.changed(),save:async()=>saves++});
 await state.ready;assert.equal(saves,0);
});

test('opening or leaving a fresh task neither restores nor overwrites the previous draft',async()=>{
 let restores=0,saves=0;
 const state=recovery.createRecovery({initialize:Promise.resolve(),restore:async()=>restores++,save:async()=>saves++});
 await state.ready;await state.flush();
 assert.equal(restores,0);assert.equal(saves,0);
 await state.restore();assert.equal(restores,1);assert.equal(saves,0);
});

test('start saves the filled form before a failed launch and a fresh page can recover it explicitly',async()=>{
 let form='filled text',stored='older text',submissions=0;
 const state=recovery.createRecovery({initialize:Promise.resolve(),restore:async()=>form=stored,save:async()=>{stored=form;return {textSaved:true};}});
 await state.ready;
 await state.flush({force:true});submissions++;
 assert.equal(stored,'filled text');assert.equal(submissions,1);
 form='';const next=recovery.createRecovery({initialize:Promise.resolve(),restore:async()=>form=stored,save:async()=>stored=form});
 await next.ready;await next.flush();assert.equal(form,'');assert.equal(stored,'filled text');
 await next.restore();assert.equal(form,'filled text');
});

test('the actual start wrapper finishes saving before sending a request that can fail',async()=>{
 const fs=require('node:fs'),vm=require('node:vm'),html=fs.readFileSync('index.html','utf8');
 const code=html.slice(html.indexOf('let taskLaunchInProgress = false;'),html.indexOf('async function runRewrite()'));
 const events=[];
 const context={window:{formDraftReady:Promise.resolve(),app074FormDraft:{flush:async options=>{assert.equal(options.force,true);events.push('saved');}}},taskImportsReady:async()=>true};
 vm.createContext(context);vm.runInContext(code,context);
 context.launch=async()=>{events.push('request');throw Error('fixture failure');};
 await assert.rejects(vm.runInContext('withTaskImports(launch)',context),/fixture failure/);
 assert.deepEqual(events,['saved','request']);
});
test('resume or explicit imports are not overwritten by a generic new-task draft',async()=>{
 let restores=0;
 const state=recovery.createRecovery({initialize:Promise.resolve(),shouldRestore:false,restore:async()=>restores++,save:async()=>{}});
 await state.ready;assert.equal(restores,0);
});
