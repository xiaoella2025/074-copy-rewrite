const test=require('node:test'),assert=require('node:assert/strict'),fs=require('node:fs'),vm=require('node:vm');
function setup(info,post,options={}){
 class El{constructor(tag){this.tag=tag;this.children=[];this.isConnected=true;this.className='';this.textContent='';this.value='';this.classList={toggle(){},add(){}};}append(...x){this.children.push(...x);}prepend(...x){this.children.unshift(...x);}replaceChildren(...x){this.children=x;}setAttribute(){}focus(){}querySelector(selector){return this.all().find(e=>e.className?.split(' ').includes(selector.slice(1)))||null;}all(){return this.children.flatMap(c=>[c,...(c.all?.()||[])]);}remove(){this.isConnected=false;}}
 const host=new El('host'),calls=[],copied=[];const context={window:{location:{href:''},crypto:{randomUUID:()=> 'fixed-operation'}},document:{createElement:t=>new El(t),body:new El('body')},navigator:{clipboard:{writeText:async text=>copied.push(text)}},Date,fetch:async(path,options={})=>{calls.push({path,body:options.body?JSON.parse(options.body):null});return options.method==='POST'?post(JSON.parse(options.body),path):{ok:true,json:async()=>info};}};
 vm.runInNewContext(fs.readFileSync('assets/task_cover.js','utf8'),context);const edits=[];context.window.app074SceneImages=Object.fromEntries(['open','history','reference','replace'].map(name=>[name,async value=>edits.push({name,value})]));let control=context.window.app074TaskCover.render(host,{taskId:'fixture',gallery:true,...options});
 return {host,calls,copied,edits,location:context.window.location,refresh:()=>control.refresh(),remount:()=>{control.dispose();control=context.window.app074TaskCover.render(host,{taskId:'fixture'});},button:label=>host.all().find(e=>e.tag==='button'&&e.textContent===label)};
}
function info(extra={}){return {title:'title',subtitle:[],template:'template',templates:[{id:'template',name:'模板',directions:[{label:'正面'}]}],directions:['scene'],direction:0,ratio:'3:4',withTitle:true,mode:'titled',cover:{},prompt:'stored original prompt',provider:'',job:{},...extra};}
const tick=async()=>{for(let i=0;i<8;i++)await Promise.resolve();};



test('gallery displays exact image prompt and new generation prompt separately without click',async()=>{
 const state=info({cover:{url:'/old.png'},imageInfo:{actualPrompt:'旧图实际文字\n第二行',provider:'runninghub_workflow'},prompt:'准备新生成的提示词'}),s=setup(state);await tick();
 const text=s.host.all().filter(e=>e.tag==='pre').map(e=>e.textContent);assert.deepEqual(text,['旧图实际文字\n第二行','准备新生成的提示词']);assert.equal(s.calls.filter(c=>c.body).length,0);
});

test('gallery without a platform receipt explains disabled query and still refreshes without generation',async()=>{
 const state=info({job:{status:'failed',error:'original failure'}}),s=setup(state,()=>{throw Error('must not submit')});await tick();
 assert.equal(s.button('查图取回').disabled,true);assert.ok(s.button('刷新状态'));
 assert.ok(s.host.all().some(e=>e.textContent.includes('没有平台任务编号或结果')));
 await s.button('刷新状态').onclick();assert.equal(s.calls.filter(c=>c.body).length,0);
});
test('gallery crop history and reference reuse scene dialogs with cover namespace and correct slot',async()=>{
 const s=setup(info({cover:{url:'/cover2.png'},imageInfo:{actualPrompt:'完整内容'}}),null,{slot:2});await tick();
 for(const name of ['裁剪','图片历史','参考图编辑'])await s.button(name).onclick();
 assert.deepEqual(s.edits.map(e=>e.name),['open','history','reference']);for(const e of s.edits){assert.equal(e.value.index,2);assert.equal(e.value.coverSlot,2);assert.equal(e.value.taskId,'fixture');}
});
test('local uploaded cover still has gallery operations and visible upload provenance',async()=>{
 const s=setup(info({mode:'local',cover:{url:'/local.png'},imageInfo:{actualPrompt:'(本地上传)',provider:'upload'}}));await tick();assert.ok(s.button('裁剪'));assert.ok(s.button('图片历史'));assert.ok(s.host.all().some(e=>e.tag==='pre'&&e.textContent==='(本地上传)'));
});
test('pending reference retains visible prompt and query dialog but blocks local pixel changes',async()=>{
 const s=setup(info({cover:{url:'/cover.png'},imageInfo:{actualPrompt:'原图提示词',referenceJob:{status:'pending',taskId:'paid'}}}));await tick();assert.equal(s.button('裁剪').disabled,true);assert.equal(s.button('参考图编辑').disabled,false);assert.equal(s.button('重新生成封面').disabled,true);
});
test('missing saved prompt is explicit and is not fabricated from edited options',async()=>{
 const s=setup(info({cover:{url:'/old.png'},imageInfo:{actualPrompt:''},prompt:'new prompt'}));await tick();assert.ok(s.host.all().some(e=>e.textContent==='这张封面未保存出图提示词。'));
});
test('cover gallery is adjacent to scene gallery and scene dialogs support separate API namespace',()=>{
 const workflow=fs.readFileSync('assets/workflow_view.js','utf8'),editor=fs.readFileSync('assets/scene_image_editor.js','utf8');assert.match(workflow,/gallery: "▧ 分镜画廊", covers: "▧ 封面画廊", captions:/);assert.match(editor,/options.coverSlot\?'\/api\/cover-image\/':'\/api\/scene-image\/'/);assert.match(workflow,/!info.available/);
});

test('legacy covers without meta URL render and edit through the cover media endpoint',async()=>{
 const s=setup(info({cover:{path:'legacy-owned-file'},imageInfo:{current:'/api/cover-image/fixture/1/current.png',actualPrompt:'legacy prompt'}}));await tick();
 assert.ok(s.host.all().some(e=>e.tag==='img'&&String(e.src).startsWith('/api/cover-image/fixture/1/current.png')));assert.equal(s.button('裁剪').disabled,false);
});

test('cover tiles expose all six scene-gallery actions and the exact prompt',async()=>{
 const s=setup(info({cover:{url:'/image.png'},imageInfo:{current:'/api/cover-image/fixture/1/current.png',actualPrompt:'实际封面提示词'}}));await tick();
 for(const label of ['裁剪','参考图编辑','图片历史','替换图片','生成动画版视频','生成 AI 图生视频'])assert.ok(s.button(label),label);
 assert.ok(s.host.all().some(e=>e.tag==='pre'&&e.textContent==='实际封面提示词'));await s.button('替换图片').onclick();assert.equal(s.edits[0].name,'replace');assert.equal(s.edits[0].value.coverSlot,1);
});
