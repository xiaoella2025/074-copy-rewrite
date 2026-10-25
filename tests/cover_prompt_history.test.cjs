const test=require('node:test'),assert=require('node:assert/strict'),fs=require('node:fs'),vm=require('node:vm');
function setup(info,post){
 class El{constructor(tag){this.tag=tag;this.children=[];this.isConnected=true;this.className='';this.textContent='';this.value='';this.classList={toggle(){},add(){}};}append(...x){this.children.push(...x);}prepend(...x){this.children.unshift(...x);}replaceChildren(...x){this.children=x;}setAttribute(){}focus(){}querySelector(selector){return this.all().find(e=>e.className?.split(' ').includes(selector.slice(1)))||null;}all(){return this.children.flatMap(c=>[c,...(c.all?.()||[])]);}remove(){this.isConnected=false;}}
 const host=new El('host'),calls=[],copied=[];const context={window:{location:{href:''},crypto:{randomUUID:()=> 'fixed-operation'}},document:{createElement:t=>new El(t),body:new El('body')},navigator:{clipboard:{writeText:async text=>copied.push(text)}},Date,fetch:async(path,options={})=>{calls.push({path,body:options.body?JSON.parse(options.body):null});return options.method==='POST'?post(JSON.parse(options.body),path):{ok:true,json:async()=>info};}};
 vm.runInNewContext(fs.readFileSync('assets/task_cover.js','utf8'),context);let control=context.window.app074TaskCover.render(host,{taskId:'fixture'});
 return {host,calls,copied,location:context.window.location,refresh:()=>control.refresh(),remount:()=>{control.dispose();control=context.window.app074TaskCover.render(host,{taskId:'fixture'});},button:label=>host.all().find(e=>e.tag==='button'&&e.textContent===label)};
}
function info(extra={}){return {title:'title',subtitle:[],template:'template',templates:[{id:'template',name:'模板',directions:[{label:'正面'}]}],directions:['scene'],direction:0,ratio:'3:4',withTitle:true,mode:'titled',cover:{},prompt:'stored original prompt',provider:'',job:{},...extra};}
const tick=async()=>{for(let i=0;i<8;i++)await Promise.resolve();};


test('expired prompt is visible and copyable but cannot be submitted unchanged',async()=>{
 const state=info({prompt:'',lastPrompt:'上次的旧标题提示词'}),s=setup(state,async()=>({ok:true,json:async()=>state}));await tick();
 assert.equal(s.button('复制提示词').disabled,false);await s.button('复制提示词').onclick();assert.equal(s.copied[0],state.lastPrompt);
 s.button('编辑提示词').onclick();const text=s.host.all().find(e=>e.tag==='textarea');assert.equal(text.value,state.lastPrompt);
 assert.ok(s.host.all().some(e=>e.textContent.includes('上次保存')));const submit=s.button('出图（用修改的提示词）');assert.equal(submit.disabled,true);
 assert.equal(s.button('生成封面').disabled,true);assert.equal(s.calls.filter(c=>c.body).length,0);
 text.value='修改为正确标题后的提示词';text.oninput();assert.equal(submit.disabled,false);await submit.onclick();assert.equal(s.calls.find(c=>c.body).body.prompt,'修改为正确标题后的提示词');
});
test('pending prompt can be inspected and copied but cannot be edited or repurchased',async()=>{
 const state=info({prompt:'',lastPrompt:'正在生成的原提示词',job:{status:'pending',taskId:'paid-id'}}),s=setup(state,()=>{throw Error('no submission');});await tick();
 assert.equal(s.button('编辑提示词').disabled,false);s.button('编辑提示词').onclick();const text=s.host.all().find(e=>e.tag==='textarea');assert.equal(text.readOnly,true);assert.equal(s.button('出图（用修改的提示词）').disabled,true);assert.equal(s.calls.filter(c=>c.body).length,0);
});

test('completed cover edit navigates to returned new task instead of overwriting history',async()=>{
 const state=info(),s=setup(state,async()=>({ok:true,json:async()=>({...state,task_id:'new_cover_revision',source_task_id:'fixture'})}));await tick();
 s.button('编辑封面文字').onclick();await s.button('保存').onclick();assert.equal(s.location.href,'/result.html?task=new_cover_revision');
});
test('paid failure in a new cover version navigates to that version for recovery',async()=>{
 const state=info(),s=setup(state,async()=>({ok:false,json:async()=>({error:'timeout',task_id:'new_pending_revision'})}));await tick();
 await s.button('生成封面').onclick();assert.equal(s.location.href,'/result.html?task=new_pending_revision');
});
