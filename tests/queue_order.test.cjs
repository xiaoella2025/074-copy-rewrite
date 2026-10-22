const test=require('node:test'),assert=require('node:assert/strict'),fs=require('node:fs'),vm=require('node:vm');
class Element{
 constructor(tag){this.tagName=tag;this.children=[];this.disabled=false;this.dataset={};this.classList={add(){},toggle(){}};}
 append(...nodes){this.children.push(...nodes);}replaceChildren(...nodes){this.children=[...nodes];}setAttribute(k,v){this[k]=v;}
}
const descendants=node=>[node,...(node.children||[]).flatMap(descendants)];
function fixture(){
 const hosts=new Map(),calls=[];const context={window:{loadList:async()=>{}},document:{body:{dataset:{}},activeElement:{},querySelector:()=>null,
 getElementById:id=>{if(!hosts.has(id))hosts.set(id,new Element('div'));return hosts.get(id);},createElement:t=>new Element(t),createTextNode:text=>({textContent:text})},Set,Map,Date,alert:message=>calls.push(['error',message])};
 vm.runInNewContext(fs.readFileSync('assets/queue_controls.js','utf8'),context);vm.runInNewContext(fs.readFileSync('assets/story_history.js','utf8'),context);
 const handlers={api:async(...args)=>{calls.push(args);return {};},select:id=>calls.push(['select',id])};
 const render=tasks=>{context.window.StoryQueueControls.render(tasks,{batches:[]},handlers);context.window.StoryHistory.render(tasks,handlers);};
 return {context,hosts,calls,render};
}

test('queued task exposes explicit start even when a previous manual pause holds the worker',async()=>{
 const f=fixture();f.render([{task_id:'waiting',queue:{status:'queued',position:1}},{task_id:'held',queue:{status:'paused',manual_pause:true}}]);
 const start=descendants(f.hosts.get('list-panel')).find(n=>n.textContent==='开始执行');assert.ok(start);
 await start.onclick({stopPropagation(){}});
 assert.deepEqual(JSON.parse(JSON.stringify(f.calls)),[['/api/task-queue/order','POST',{task_id:'waiting',action:'start'}]]);
});

test('deleting a queued task cancels its queue ownership before deleting files',async()=>{
 const f=fixture();f.context.confirm=()=>true;
 f.render([{task_id:'waiting',queue:{status:'queued',position:1}}]);
 await descendants(f.hosts.get('list-panel')).find(n=>n.textContent==='删除').onclick({stopPropagation(){}});
 assert.deepEqual(JSON.parse(JSON.stringify(f.calls)),[['/api/task/waiting/cancel','POST',{}],['/api/task/waiting','DELETE']]);
});

test('failed queue cancellation prevents deletion, preserving the task files',async()=>{
 const f=fixture();f.context.confirm=()=>true;f.context.window.loadList=async()=>{};
 f.render([{task_id:'waiting',queue:{status:'queued'}}]);
 const api=f.context.window.StoryHistory;
 api.render([{task_id:'waiting',queue:{status:'queued'}}],{api:async(path,method)=>{f.calls.push([path,method]);throw Error('cannot cancel');},select(){}});
 await descendants(f.hosts.get('list-panel')).find(n=>n.textContent==='删除').onclick({stopPropagation(){}});
 assert.equal(f.calls.some(c=>c[1]==='DELETE'),false);
});
test('row has compact queued actions, actual order, and does not open detail on reorder',async()=>{
 const f=fixture();f.render([{task_id:'later',title:'later',created_at:'2026-10-19 12:00:00',queue:{status:'queued',position:2}},
 {task_id:'first',title:'first',created_at:'2026-10-18 12:00:00',queue:{status:'queued',position:1}}]);
 const rows=descendants(f.hosts.get('list-panel')).filter(n=>n.className?.split(' ').includes('history-row'));
 assert.deepEqual(rows.map(n=>descendants(n).find(x=>x.className==='history-row-title').textContent),['first','later']);
 const priority=descendants(rows[1]).find(n=>n.textContent==='优先执行');assert.ok(priority);
 let stopped=false;await priority.onclick({stopPropagation(){stopped=true;}});assert.ok(stopped);
 assert.deepEqual(JSON.parse(JSON.stringify(f.calls)),[['/api/task-queue/order','POST',{task_id:'later',action:'first'}]]);
});
test('running can be deferred, a draining task cannot be resumed, deferred row has restore action',()=>{
 const f=fixture();f.render([{task_id:'running',queue:{status:'running'}},{task_id:'draining',queue:{status:'pausing',deferred:true}},
 {task_id:'held',queue:{status:'paused',deferred:true}}]);
 const controls=descendants(f.hosts.get('list-panel'));
 assert.equal(controls.filter(n=>n.textContent==='暂停修改').length,1);
 assert.equal(controls.filter(n=>n.textContent==='继续任务').length,1);
 assert.equal(controls.filter(n=>n.textContent==='正在暂停').length,1);
 assert.equal(controls.filter(n=>n.textContent==='已暂停').length,1);
});
test('incomplete confirmation is restored without being labelled automatic resume',()=>{
 const f=fixture();f.render([{task_id:'held',queue:{status:'paused',deferred:true,pause_stage:'generate'}}]);
 assert.ok(descendants(f.hosts.get('list-panel')).find(n=>n.textContent==='查看并确认'));
});
test('buttons become usable after list reload finishes during the pending operation',async()=>{
 const f=fixture(),tasks=[{task_id:'first',title:'first',queue:{status:'queued',position:1}}];
 f.render(tasks);f.context.window.loadList=async()=>f.render(tasks);
 await descendants(f.hosts.get('list-panel')).find(n=>n.textContent==='优先执行').onclick({stopPropagation(){}});
 assert.equal(descendants(f.hosts.get('list-panel')).find(n=>n.textContent==='暂停修改').disabled,false);
});


test('each task exposes Story start pause and continue controls without confirming review',async()=>{
 const f=fixture();f.render([{task_id:'run',queue:{status:'running'}},{task_id:'held',queue:{status:'paused',deferred:true}},
 {task_id:'review',queue:{status:'paused',pause_stage:'generate'}},{task_id:'fail',queue:{status:'failed'}}]);
 const nodes=descendants(f.hosts.get('list-panel'));
 assert.ok(nodes.some(n=>n.textContent==='暂停修改'));
 const next=nodes.find(n=>n.textContent==='继续任务');assert.ok(next);await next.onclick({stopPropagation(){}});
 assert.equal(f.calls[0][2].action,'start');assert.equal(f.calls[0][2].task_id,'held');
 assert.ok(descendants(f.hosts.get('list-panel')).some(n=>n.textContent==='查看并确认'));
 assert.ok(descendants(f.hosts.get('list-panel')).some(n=>n.textContent==='从断点续跑'));
});
