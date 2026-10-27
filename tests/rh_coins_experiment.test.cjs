const test=require('node:test'),assert=require('node:assert/strict'),fs=require('node:fs'),vm=require('node:vm');
function fixture({lost=false,reject=false,savedConfig={}}={}){
 class Element{constructor(){this.children=[];this.value='';this.checked=false;this.disabled=false;this.style={};this.textContent='';}append(...nodes){this.children.push(...nodes);}replaceChildren(...nodes){this.children=nodes;}}
 const ids=['enabled','key','member','web','preset','save','check','account','workflow','workflow-link','prompt','ratio','generate','refresh','status','jobs','directory','choose','stage','next','check-hint'],nodes=Object.fromEntries(ids.map(id=>['rh-'+id,new Element()]));
 nodes['rh-ratio'].value='9:16';let state={enabled:false,configured:false,checked:false,preset:'qwen-simple',candidates:[{key:'qwen-simple',name:'Qwen',url:'https://www.runninghub.cn/post/1955160402595233794'}],jobs:[],exportDirectory:'D:/fixture',...savedConfig},counter=0,storage=new Map(),calls=[],scheduled;
 const context={document:{getElementById:id=>nodes[id],createElement:()=>new Element()},window:{addEventListener(){}},sessionStorage:{getItem:key=>storage.get(key)||null,setItem:(key,value)=>storage.set(key,value),removeItem:key=>storage.delete(key)},crypto:{randomUUID:()=>String(++counter).padStart(32,'a')},setTimeout:fn=>(scheduled=fn,1),clearTimeout:()=>scheduled=null,
 fetch:async(url,options={})=>{const body=options.body?JSON.parse(options.body):null;calls.push({url,body});let result=state;
  if(url.endsWith('/config')){state={...state,...body,live_tested:!!body.web_tested,configured:!!body.api_key||state.configured,checked:false};delete state.api_key;result=state;}
  if(url.endsWith('/check')){state={...state,checked:true,live_tested:!!state.web_tested,account:{remainCoins:'73100',remainMoney:'0.001',apiType:'NORMAL'},workflow:{nodes:9}};result=state;}
  if(url.endsWith('/generate')){if(reject)return {ok:false,status:400,json:async()=>({error:'请先核对账户'})};if(lost)throw Error('response lost');state.jobs=[{operationId:body.operation_id,prompt:body.prompt,status:'pending',taskId:'fixture-id'}];result=state.jobs[0];}
  if(url.endsWith('/query')){state.jobs[0]={...state.jobs[0],status:'ok',url:'/fixture.png'};result=state.jobs[0];}
  if(url.endsWith('/export'))result={path:'D:/fixture/result.png'};
  return {ok:true,json:async()=>result};}};
 vm.runInNewContext(fs.readFileSync('assets/rh_coins_experiment.js','utf8'),context);
 return {nodes,calls,storage,tick:async()=>{for(let i=0;i<16;i++)await Promise.resolve();},poll:()=>scheduled?.()};
}
async function ready(f){await f.tick();f.nodes['rh-enabled'].checked=true;f.nodes['rh-member'].checked=true;f.nodes['rh-web'].checked=true;f.nodes['rh-key'].value='fixture-member-key';await f.nodes['rh-save'].onclick();await f.nodes['rh-check'].onclick();f.nodes['rh-prompt'].value='旧书房，不露脸';f.nodes['rh-prompt'].oninput();}
test('default off, saving and checking do not submit generation or expose saved key',async()=>{
 const f=fixture();await f.tick();assert.equal(f.nodes['rh-generate'].disabled,true);await ready(f);
 assert.equal(f.nodes['rh-key'].value,'');assert.equal(f.calls.filter(c=>c.url.endsWith('/generate')).length,0);
 assert.equal(f.nodes['rh-generate'].disabled,false);
});
test('explicit one image, repeated click blocked, original query and export use separate routes',async()=>{
 const f=fixture();await ready(f);await f.nodes['rh-generate'].onclick();await f.nodes['rh-generate'].onclick();
 assert.equal(f.calls.filter(c=>c.url.endsWith('/generate')).length,1);
 let buttons=f.nodes['rh-jobs'].children[0].children;await buttons.find(n=>n.textContent==='查询原任务').onclick();
 buttons=f.nodes['rh-jobs'].children[0].children;await buttons.find(n=>n.textContent==='另存图片').onclick();
 assert.equal(f.calls.filter(c=>c.url.endsWith('/generate')).length,1);assert.match(f.nodes['rh-status'].textContent,/D:\/fixture\/result.png/);
});
test('lost response keeps operation in session and blocks buying a new request',async()=>{
 const f=fixture({lost:true});await ready(f);await f.nodes['rh-generate'].onclick();const first=f.calls.find(c=>c.url.endsWith('/generate')).body.operation_id;
 assert.ok([...f.storage.values()].some(value=>value.includes(first)));
 assert.equal(f.nodes['rh-generate'].disabled,true);f.nodes['rh-prompt'].value='edited';f.nodes['rh-prompt'].oninput();await f.nodes['rh-generate'].onclick();
 assert.equal(f.calls.filter(c=>c.url.endsWith('/generate')).length,1);
});
test('page and sidebar expose independent entry without replacing existing providers',()=>{
 const html=fs.readFileSync('rh-coins-experiment.html','utf8'),nav=fs.readFileSync('assets/app_nav.js','utf8'),js=fs.readFileSync('assets/rh_coins_experiment.js','utf8');
 assert.match(html,/默认关闭/);assert.match(html,/消费级会员/);assert.match(nav,/\/rh-coins-experiment.html/);assert.match(html,/生成1张（消耗RH币）/);
 assert.doesNotMatch(js,/\/api\/settings|\/api\/task\/|\.download\s*=/);
});
test('known preflight rejection permits correcting configuration without a false uncertain lock',async()=>{
 const f=fixture({reject:true});await ready(f);await f.nodes['rh-generate'].onclick();
 assert.equal(f.storage.size,0);assert.equal(f.nodes['rh-generate'].disabled,false);
});
test('saved key with missing member confirmation explains the exact disabled check and next step',async()=>{
 const f=fixture({savedConfig:{enabled:true,configured:true,member_key_confirmed:false,web_tested:true}});await f.tick();
 assert.equal(f.nodes['rh-check'].disabled,true);
 assert.match(f.nodes['rh-check-hint'].textContent,/勾选.*消费级会员/);
 assert.match(f.nodes['rh-next'].textContent,/勾选.*消费级会员/);
 assert.match(f.nodes['rh-stage'].textContent,/未提交生成/);
 f.nodes['rh-member'].checked=true;f.nodes['rh-member'].onchange();
 assert.match(f.nodes['rh-next'].textContent,/保存配置/);
 await f.nodes['rh-save'].onclick();assert.match(f.nodes['rh-next'].textContent,/核对配置/);
 assert.equal(f.calls.filter(c=>c.url.endsWith('/generate')).length,0);
});
test('visible stage distinguishes ready, submitted and completed without inventing progress',async()=>{
 const f=fixture();await ready(f);assert.match(f.nodes['rh-next'].textContent,/开始生成/);
 await f.nodes['rh-generate'].onclick();assert.match(f.nodes['rh-stage'].textContent,/已受理/);
 assert.equal(f.nodes['rh-generate'].disabled,true);
 let buttons=f.nodes['rh-jobs'].children[0].children;await buttons.find(n=>n.textContent==='查询原任务').onclick();
 assert.match(f.nodes['rh-stage'].textContent,/已完成/);assert.equal(f.calls.filter(c=>c.url.endsWith('/generate')).length,1);
});
test('account display distinguishes the last interface balance from per-image fees and hides missing money',async()=>{
 const f=fixture({savedConfig:{configured:true,checked:true,workflow:{nodes:11},account:{remainCoins:'949',remainMoney:'None',currency:'None',apiType:'NORMAL'}}});await f.tick();
 assert.match(f.nodes['rh-account'].textContent,/上次核对.*949.*不是单张/);
 assert.match(f.nodes['rh-account'].textContent,/runninghub\.cn/);
 assert.match(f.nodes['rh-account'].textContent,/钱包余额.*未返回/);
 assert.doesNotMatch(f.nodes['rh-account'].textContent,/None/);
});
