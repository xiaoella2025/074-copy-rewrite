const test=require('node:test'),assert=require('node:assert/strict'),fs=require('node:fs'),vm=require('node:vm');
function fixture(){
 class Element{
  constructor(){this.children=[];this.files=[];this.value='';this.checked=false;this.disabled=false;this.style={};this.textContent='';}
  append(...nodes){this.children.push(...nodes);}replaceChildren(...nodes){this.children=nodes;}
 }
 const ids=['enabled','account','generate','reference','prompt','status','jobs','refresh','preview'],nodes=Object.fromEntries(ids.map(id=>['experiment-'+id,new Element()]));
 let enabled=false,jobs=[],scheduled,generateCalls=0,queryCalls=0;
 const calls=[],context={document:{getElementById:id=>nodes[id],createElement:()=>new Element()},window:{addEventListener(){}},crypto:{randomUUID:()=>String(generateCalls+1).padStart(32,'a')},URL:{createObjectURL:()=>'/fixture.png',revokeObjectURL(){}},
  setTimeout:fn=>(scheduled=fn,1),clearTimeout:()=>scheduled=null,
  FileReader:class{readAsDataURL(){this.result='data:image/png;base64,fixture';this.onload();}},
  fetch:async(url,options={})=>{const body=options.body?JSON.parse(options.body):null;calls.push({url,body});let result;
   if(url.endsWith('/config')){enabled=body.enabled;result={enabled,configured:true,jobs};}
   else if(url.endsWith('/generate')){generateCalls++;jobs=[{operationId:body.operation_id,status:'pending',taskId:'fixture-id',prompt:body.prompt}];result=jobs[0];}
   else if(url.endsWith('/query')){queryCalls++;jobs[0]={...jobs[0],status:'ok',url:'/fixture-result.png'};result=jobs[0];}
   else result={enabled,configured:true,jobs};
   return {ok:true,json:async()=>result};}};
 vm.runInNewContext(fs.readFileSync('assets/modelscope_reference_experiment.js','utf8'),context);
 return {nodes,calls,tick:async()=>{for(let i=0;i<12;i++)await Promise.resolve();},counts:()=>({generateCalls,queryCalls}),poll:()=>scheduled?.()};
}
test('standalone experiment stays off and never submits on load, enable or disable',async()=>{
 const f=fixture();await f.tick();assert.equal(f.nodes['experiment-enabled'].checked,false);assert.equal(f.nodes['experiment-generate'].disabled,true);
 f.nodes['experiment-enabled'].checked=true;await f.nodes['experiment-enabled'].onchange();assert.equal(f.counts().generateCalls,0);
 f.nodes['experiment-enabled'].checked=false;await f.nodes['experiment-enabled'].onchange();assert.equal(f.counts().generateCalls,0);
 assert.ok(f.calls.every(c=>c.url.startsWith('/api/ms-reference-experiment')));
});
test('explicit single-image test is independent and pending result blocks duplicate submission',async()=>{
 const f=fixture();await f.tick();f.nodes['experiment-enabled'].checked=true;await f.nodes['experiment-enabled'].onchange();
 f.nodes['experiment-reference'].files=[{name:'fixture.png',size:20,type:'image/png'}];f.nodes['experiment-reference'].onchange();
 f.nodes['experiment-prompt'].value='keep the product';f.nodes['experiment-prompt'].oninput();
 assert.equal(f.nodes['experiment-generate'].disabled,false);await f.nodes['experiment-generate'].onclick();
 assert.equal(f.counts().generateCalls,1);assert.equal(f.nodes['experiment-generate'].disabled,true);
 await f.nodes['experiment-generate'].onclick();assert.equal(f.counts().generateCalls,1);
 const query=f.nodes['experiment-jobs'].children[0].children.find(n=>n.textContent==='查询原任务（不重新生成）');await query.onclick();
 assert.equal(f.counts().queryCalls,1);assert.equal(f.counts().generateCalls,1);
 f.nodes['experiment-enabled'].checked=false;await f.nodes['experiment-enabled'].onchange();assert.equal(f.nodes['experiment-generate'].disabled,true);
});
test('settings adds a separate link while leaving normal provider selectors intact',()=>{
 const html=fs.readFileSync('settings.html','utf8');assert.match(html,/href="\/ms-reference-experiment.html"/);
 const page=fs.readFileSync('ms-reference-experiment.html','utf8');assert.match(page,/默认关闭/);assert.match(page,/生成1张测试图/);
 assert.match(page,/不接入任务流水线/);
 const js=fs.readFileSync('assets/modelscope_reference_experiment.js','utf8');
 assert.doesNotMatch(js,/\/api\/generate|\/api\/task\/|\/api\/settings|\/api\/image_lab/);
});
