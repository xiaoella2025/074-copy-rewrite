const test=require('node:test'),assert=require('node:assert/strict'),fs=require('node:fs'),vm=require('node:vm');
const view=require('../assets/workflow_view.js');
const detail=()=>({info:{task_id:'fixture',completed_steps:[1,2,5,3],progress:{step:'4',status:'failed'},queue:{status:'failed',stage:'images',error:'images未完成：上游已确认出图失败'}},steps:{shots:[{idx:1,text:'one'},{idx:6,text:'six'}],prompts:[{idx:1,desc_prompt:'one'},{idx:6,desc_prompt:'six'}],images:[{name:'1.png',url:'/one.png'}]}});
class Element{constructor(tag){this.tag=tag;this.children=[];this.dataset={};this.className='';this.textContent='';this.classList={add:n=>this.className+=' '+n,toggle(){}};}append(...x){this.children.push(...x);}prepend(...x){this.children.unshift(...x);}replaceChildren(...x){this.children=x;}setAttribute(){}addEventListener(){}all(){return this.children.flatMap(x=>[x,...(x.all?.()||[])]);}querySelectorAll(s){return this.all().filter(x=>x.className?.split(' ').includes(s.slice(1)));}}
function render(value,extra={}){const win={},host=new Element('div');vm.runInNewContext(fs.readFileSync('assets/workflow_view.js','utf8'),{window:win,document:{createElement:t=>new Element(t)},Map,Set,fetch:async()=>({json:async()=>({templates:[]})}),Option:function(t,v){const o=new Element('option');o.textContent=t;o.value=v;return o;},...extra});const renderer=win.WorkflowView.mount(host,{});renderer.renderTask(value);return host;}
test('partial image failure exposes exact missing index and preserves a visible gallery slot',()=>{
 const host=render(detail()),notes=host.querySelectorAll('.wv-node-note').map(x=>x.textContent).join(' ');
 assert.match(notes,/1\s*\/\s*2/);assert.match(notes,/6/);
 const tile=host.all().find(x=>x.dataset?.sceneImageIndex==='6');assert.ok(tile,'missing scene must remain visible');assert.match(tile.all().map(x=>x.textContent).join(' '),/第 6 镜|第6镜/);
});
test('all expected images already present clear only stale image-stage failure, not unrelated failures',()=>{
 const d=detail();d.steps.images.push({name:'6.webp',url:'/six.webp'});let host=render(d);
 assert.equal(host.querySelectorAll('.failed').filter(x=>x.dataset.step==='4').length,0);
 d.info.queue.stage='draft';d.info.progress.step='6';host=render(d);assert.equal(host.querySelectorAll('.failed').filter(x=>x.dataset.step==='6').length,1);
});
test('completeness matches exact expected IDs, ignoring unrelated files and duplicates',()=>{
 const d=detail();d.steps.images.push({name:'01.jpg',url:'/dup.jpg'},{name:'99.png',url:'/other.png'});
 assert.deepEqual(view.imageCompletion(d),{expected:[1,6],completed:1,total:2,missing:[6]});
});
test('zero-byte image stays missing and keeps its retry tile',()=>{
 const d=detail();d.steps.images.push({name:'6.png',url:'/empty.png',size:0});assert.deepEqual(view.imageCompletion(d).missing,[6]);
 assert.ok(render(d).all().some(x=>x.tag==='button'&&x.textContent==='仅补第 6 镜'));
});
test('pipeline failure records total completed including reused images and failed scene number',async()=>{
 const {runImagePipeline}=require('../assets/image_pipeline.js'),d=detail();d.steps.rewrite='fixture';d.steps.meta={title:'fixture'};
 d.steps.audios=[{name:'seg_001.mp3'},{name:'seg_006.mp3'}];d.steps.segments=[{index:1,path:'a.mp3',duration:2},{index:6,path:'b.mp3',duration:2}];
 await assert.rejects(runImagePipeline({resume:d,generate:{},tts:{},image:{},request:async(path)=>{assert.equal(path,'/api/step4_generate_images');return{results:[{idx:6,ok:false,error:'上游确认失败'}]};}}),/1\s*\/\s*2.*第\s*6\s*镜/);
});
test('missing tile retries only its own index with explicit cost confirmation',async()=>{
 const d=detail(),calls=[];let confirmation='';const host=render(d,{confirm:text=>{confirmation=text;return true;},alert:()=>{},fetch:async(path,options)=>{calls.push({path,body:options?.body&&JSON.parse(options.body)});if(options)d.steps.images.push({name:'6.png',url:'/six.png'});return {ok:true,json:async()=>options?{ok:true}:d};}});
 const button=host.all().find(x=>x.tag==='button'&&x.textContent==='仅补第 6 镜');assert.ok(button);await button.onclick();
 assert.match(confirmation,/一次出图额度/);const posts=calls.filter(c=>c.body);assert.equal(posts.length,1);assert.equal(posts[0].path,'/api/task/fixture/retry-image');assert.equal(posts[0].body.index,6);assert.ok(posts[0].body.operation_id);
});
test('confirmed terminal failure permits a new user-confirmed operation on the same page',async()=>{
 const d=detail(),bodies=[];let confirms=0;const host=render(d,{confirm:()=>{confirms++;return true;},alert:()=>{},fetch:async(path,options)=>{
  if(!options)return{ok:true,json:async()=>d};const body=JSON.parse(options.body);bodies.push(body);
  if(bodies.length===1)return{ok:false,json:async()=>({error:'明确拒绝',retryable:true})};
  d.steps.images.push({name:'6.png',url:'/six.png'});return{ok:true,json:async()=>({ok:true})};
 }});
 await host.all().find(x=>x.tag==='button'&&x.textContent==='仅补第 6 镜').onclick();
 await host.all().find(x=>x.tag==='button'&&x.textContent==='仅补第 6 镜').onclick();
 assert.equal(confirms,2);assert.notEqual(bodies[0].operation_id,bodies[1].operation_id);
});
test('repaired image-stage queue badge says ready to continue rather than historical failure',()=>{
 const d=detail();d.steps.images.push({name:'6.png',url:'/six.png'});const nodes=new Map();const doc={getElementById:id=>{if(!nodes.has(id))nodes.set(id,new Element('div'));return nodes.get(id);},createElement:t=>new Element(t)};
 const source=fs.readFileSync('result.html','utf8'),start=source.indexOf('function renderQueue(detail)'),end=source.indexOf('async function api(',start);
 vm.runInNewContext(source.slice(start,end)+';renderQueue(detail);',{document:doc,detail:d,WorkflowView:view,host:{querySelectorAll:()=>[]},QUEUE_LABELS:{failed:'任务执行失败'},workflow:{setNotice(){}},taskId:'fixture'});
 assert.match(nodes.get('status').textContent,/图片已补齐.*待续跑/);
});
