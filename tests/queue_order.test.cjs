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
 assert.equal(controls.filter(n=>n.textContent==='暂缓本条').length,1);
 assert.equal(controls.filter(n=>n.textContent==='恢复排队').length,1);
 assert.equal(controls.filter(n=>n.textContent==='保存后暂缓').length,1);
 assert.equal(controls.filter(n=>n.textContent==='已暂缓').length,1);
});
test('incomplete confirmation is restored without being labelled automatic resume',()=>{
 const f=fixture();f.render([{task_id:'held',queue:{status:'paused',deferred:true,pause_stage:'generate'}}]);
 assert.ok(descendants(f.hosts.get('list-panel')).find(n=>n.textContent==='恢复等待确认'));
});
test('buttons become usable after list reload finishes during the pending operation',async()=>{
 const f=fixture(),tasks=[{task_id:'first',title:'first',queue:{status:'queued',position:1}}];
 f.render(tasks);f.context.window.loadList=async()=>f.render(tasks);
 await descendants(f.hosts.get('list-panel')).find(n=>n.textContent==='优先执行').onclick({stopPropagation(){}});
 assert.equal(descendants(f.hosts.get('list-panel')).find(n=>n.textContent==='暂缓本条').disabled,false);
});

