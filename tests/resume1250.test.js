const test=require('node:test'),assert=require('node:assert/strict'),fs=require('node:fs'),vm=require('node:vm');
class Element{
 constructor(tag){this.tag=tag;this.children=[];this.dataset={};this.className='';this.textContent='';this.classList={add:n=>this.className+=' '+n,toggle(){}};}
 append(...items){this.children.push(...items);}prepend(item){this.children.unshift(item);}replaceChildren(...items){this.children=items;}
 setAttribute(k,v){this[k]=v;}addEventListener(){}
 querySelectorAll(selector){const wanted=selector.slice(1);return this.children.flatMap(x=>x instanceof Element?[...(x.className.split(' ').includes(wanted)?[x]:[]),...x.querySelectorAll(selector)]:[]);}
}
const state=(status='failed',id='old-job',task='resume_fixture')=>({info:{task_id:task,progress:{step:'4',status:status==='running'?'running':'failed'},queue:{status,id,position:2,stage:'images'}},steps:{}});
function fixture(control){
 const window={},host=new Element('div');let detail=state(),refreshOk=true;const calls=[];
 vm.runInNewContext(fs.readFileSync('assets/workflow_view.js','utf8'),{window,document:{createElement:t=>new Element(t)},fetch:async path=>{calls.push(path);return{ok:refreshOk,json:async()=>typeof detail==='function'?detail():detail};}});
 let controls=0;const view=window.WorkflowView.mount(host,{onTaskControl:async(...args)=>{controls++;return control?.(...args);}});view.renderTask(detail);
 return{host,view,calls,get controls(){return controls;},set detail(value){detail=value;},set refreshOk(value){refreshOk=value;},buttons:()=>host.querySelectorAll('.wv-summary-control'),resume:()=>host.querySelectorAll('.wv-summary-resume')[0]};
}
test('resume label stays pending after POST resolves and stale failed refresh; duplicate clicks do nothing',async()=>{
 let finish;const f=fixture(()=>new Promise(resolve=>finish=resolve)),original=f.resume(),pending=original.onclick();
 assert.equal(f.resume().textContent,'续跑中…');assert.equal(f.resume().disabled,true);
 await original.onclick();assert.equal(f.controls,1);finish();await pending;
 assert.equal(f.resume().textContent,'续跑中…');assert.equal(f.resume().disabled,true);
 await f.resume().onclick();assert.equal(f.controls,1);
 f.view.renderTask(state('queued','new-job'));assert.ok(f.buttons().some(b=>/排队/.test(b.textContent)&&b.disabled));assert.equal(f.resume(),undefined);
 f.view.renderTask(state('running','new-job'));assert.ok(f.buttons().some(b=>b.textContent==='暂停修改'&&!b.disabled));
});
test('paused confirmation has the same pending state until accepted running detail',async()=>{
 let finish;const f=fixture(()=>new Promise(resolve=>finish=resolve));f.view.renderTask(state('paused'));
 const request=f.resume().onclick();assert.equal(f.resume().textContent,'续跑中…');finish();await request;assert.equal(f.resume().disabled,true);
 f.view.renderTask(state('running','new-job'));assert.equal(f.resume(),undefined);
});
test('rejected resume shows failure and enables an explicit retry',async()=>{
 const f=fixture(()=>{throw Error('fixture rejected');});await f.resume().onclick();assert.equal(f.resume().textContent,'从断点续跑');assert.equal(f.resume().disabled,false);
});
test('accepted resume remains pending when immediate detail refresh fails',async()=>{
 const f=fixture();f.refreshOk=false;await f.resume().onclick();assert.equal(f.resume().textContent,'续跑中…');assert.equal(f.resume().disabled,true);
 await f.resume().onclick();assert.equal(f.controls,1);f.view.renderTask(state('queued','new-job'));assert.ok(f.buttons().some(b=>/排队/.test(b.textContent)));
});
test('a new terminal job clears pending even when it finishes before the first poll',async()=>{
 const f=fixture();await f.resume().onclick();f.view.renderTask(state('failed','new-job'));
 assert.equal(f.resume().textContent,'从断点续跑');assert.equal(f.resume().disabled,false);
});
test('switching task clears old pending and late old response cannot relock new task',async()=>{
 let finish;const f=fixture(()=>new Promise(resolve=>finish=resolve));const request=f.resume().onclick();
 f.view.renderTask(state('failed','different-job','other_fixture'));assert.equal(f.resume().textContent,'从断点续跑');assert.equal(f.resume().disabled,false);
 f.detail=state('failed','different-job','other_fixture');finish();await request;assert.equal(f.resume().disabled,false);
});
test('a delayed old detail response cannot replace the newly selected task',async()=>{
 let finish,entered;const started=new Promise(resolve=>entered=resolve);const f=fixture();f.detail=()=>new Promise(resolve=>{finish=resolve;entered();});const request=f.resume().onclick();
 await started;
 f.view.renderTask(state('failed','different-job','other_fixture'));finish(state('queued','new-job'));await request;
 assert.equal(f.view.getTaskId(),'other_fixture');assert.equal(f.resume().textContent,'从断点续跑');assert.equal(f.resume().disabled,false);
});
