const test=require('node:test'),assert=require('node:assert/strict'),fs=require('node:fs'),vm=require('node:vm');
const read=file=>fs.readFileSync(file,'utf8');
function settingsFixture(){
 class El{constructor(){this.children=[];this.value='';this.checked=false;this.disabled=false;this.textContent='';this.style={};}append(...x){this.children.push(...x);}replaceChildren(...x){this.children=x;}}
 const ids=['key','enabled','member','web','preset','save','default','check','refresh','account','workflow','status','workflow-link'],nodes=Object.fromEntries(ids.map(id=>['rhw-'+id,new El()]));
 let state={enabled:true,configured:true,checked:true,member_key_confirmed:true,web_tested:true,preset:'qwen-simple',candidates:[{key:'qwen-simple',name:'Qwen',url:'https://fixture.invalid/workflow'}],workflow:{nodes:11},account:{remainCoins:'949',remainMoney:null}};
 const calls=[],context={window:{},document:{getElementById:id=>nodes[id],createElement:()=>new El()},fetch:async(path,options={})=>{const body=options.body&&JSON.parse(options.body);calls.push({path,body});if(path.endsWith('/config')){state={...state,...body,checked:false};delete state.api_key;}if(path.endsWith('/check'))state={...state,checked:true};return{ok:true,json:async()=>state};}};
 if(fs.existsSync('assets/rh_workflow_settings.js'))vm.runInNewContext(read('assets/rh_workflow_settings.js'),context);
 return {nodes,calls,api:context.window.app074RhWorkflowSettings,tick:async()=>{for(let i=0;i<12;i++)await Promise.resolve();}};
}
test('formal settings reuse saved member key and do not submit generation or change default while saving',async()=>{
 const f=settingsFixture();assert.ok(f.api,'formal workflow settings controller is available');f.api.mount({onDefault:async()=>f.calls.push({path:'default'})});await f.tick();
 assert.equal(f.nodes['rhw-key'].value,'');assert.equal(f.nodes['rhw-preset'].value,'qwen-simple');assert.match(f.nodes['rhw-account'].textContent,/949.*RH币/);
 f.nodes['rhw-key'].value='new-member-key';await f.nodes['rhw-save'].onclick();assert.equal(f.nodes['rhw-key'].value,'');assert.equal(f.calls.find(c=>c.path.endsWith('/config')).body.api_key,'new-member-key');assert.ok(!f.calls.some(c=>c.path==='default'||c.path.endsWith('/generate')));
 await f.nodes['rhw-check'].onclick();assert.ok(f.calls.some(c=>c.path.endsWith('/check')));await f.nodes['rhw-default'].onclick();assert.equal(f.calls.filter(c=>c.path==='default').length,1);
});
test('provider choices reach creation and task parameters without changing their saved engine',()=>{
 const ctx={};vm.createContext(ctx);vm.runInContext(read('assets/workflow_actions.js')+';this.fields=STEP_FIELDS;',ctx);
 for(const key of ['4','6'])assert.ok(ctx.fields[key].find(f=>f.path.at(-1)==='provider').options.some(x=>x[0]==='runninghub_workflow'));
 const source=read('index.html'),start=source.indexOf('function syncImageOptions()'),end=source.indexOf('function updateImageFallbackHint()',start);
 class El{constructor(){this.children=[];this.value='';this.textContent='';}replaceChildren(){this.children=[];}appendChild(x){this.children.push(x);}cloneNode(){return Object.assign(new El(),this);}addEventListener(){}}
 const nodes={'img-engine':new El(),'cover-engine':new El()};vm.runInNewContext(source.slice(start,end)+';syncImageOptions();',{$:id=>nodes[id],document:{createElement:()=>new El()},settings:{image:{provider:'modelscope'},runninghub_workflow:{configured:true}},updateImageFallbackHint(){}});
 assert.equal(nodes['img-engine'].value,'modelscope');for(const id of ['img-engine','cover-engine'])assert.ok(nodes[id].children.some(x=>x.value==='runninghub_workflow'));
});
test('image lab can display the workflow provider selected as the system default',async()=>{
 class El{constructor(){this.children=[];this.value='';}append(x){this.children.push(x);}}
 const nodes={'lab-provider':new El(),'lab-notice':new El()},ctx={$:id=>nodes[id],api:async path=>path.includes('reference')?{styles:[],coverTemplates:[]}:path.includes('settings')?{image:{provider:'runninghub_workflow'}}:{items:[],folder:'fixture'},Option:function(text,value){return{textContent:text,value};},URLSearchParams,location:{search:''},mode:'text2img',choices(){},render(){}};
 const source=read('assets/image_lab.js');vm.runInNewContext(source.slice(source.lastIndexOf('(async()=>{try{const [r,s,h]')),ctx);for(let i=0;i<10;i++)await Promise.resolve();
 assert.ok(nodes['lab-provider'].children.some(x=>x.value==='runninghub_workflow'));assert.equal(nodes['lab-provider'].value,'runninghub_workflow');
});
test('unknown cover recovery requires a different provider, missing local image and no remote receipt',()=>{
 const ctx={};vm.createContext(ctx);vm.runInContext(read('assets/workflow_actions.js'),ctx);assert.equal(typeof ctx._coverReplacementPlan,'function');
 const info={job:{status:'unknown',provider:'runninghub'},cover:{}},cfg={cover:{mode:'titled',provider:'modelscope'},image:{provider:'gpt_image'}};
 assert.equal(ctx._coverReplacementPlan(info,cfg),'modelscope');
 assert.equal(ctx._coverReplacementPlan(info,{...cfg,cover:{...cfg.cover,mode:'title'}}),'modelscope','creation form stores titled covers as title');
 for(const job of [{status:'pending',provider:'runninghub'},{status:'unknown',provider:'modelscope'},{status:'unknown',provider:'runninghub',taskId:'old-paid-id'},{status:'unknown',provider:'runninghub',result:{url:'https://fixture.invalid/image'}}])assert.equal(ctx._coverReplacementPlan({...info,job},cfg),'');
 assert.equal(ctx._coverReplacementPlan({...info,cover:{url:'/local.png'}},cfg),'');assert.equal(ctx._coverReplacementPlan(info,{...cfg,cover:{...cfg.cover,mode:'local'}}),'');assert.equal(ctx._coverReplacementPlan(info,{...cfg,cover:{...cfg.cover,mode:'off'}}),'');
});
test('cover recovery trusts verified local availability over historical metadata URLs',()=>{
 const ctx={};vm.createContext(ctx);vm.runInContext(read('assets/workflow_actions.js'),ctx);
 const cfg={cover:{mode:'title',provider:'modelscope'},image:{provider:'gpt_image'}},info={job:{status:'unknown',provider:'runninghub'},cover:{url:'/old-metadata.png'}};
 assert.equal(ctx._coverReplacementPlan({...info,localCoverAvailable:false},cfg),'modelscope','historical URL must not hide a missing local cover');
 assert.equal(ctx._coverReplacementPlan({...info,cover:{},localCoverAvailable:true},cfg),'','verified local cover must be reused even without a metadata URL');
 assert.equal(ctx._coverReplacementPlan(info,cfg),'','old API responses retain the conservative URL fallback');
 assert.equal(ctx._coverReplacementPlan({...info,cover:{}},cfg),'modelscope');
});
function editorFixture({rejectReplacement=false}={}){
 class El{
  constructor(tag='div'){this.tagName=tag.toUpperCase();this.children=[];this.dataset={};this.style={};this.value='';this.checked=false;this.disabled=false;this.textContent='';this.events={};}
  append(...items){this.children.push(...items);}appendChild(item){this.append(item);return item;}replaceChildren(...items){this.children=items;}cloneNode(){return new El(this.tagName);}get options(){return this.children;}addEventListener(key,fn){this.events[key]=fn;}setAttribute(key,value){this[key]=value;}focus(){this.focused=true;}remove(){this.removed=true;}
  set innerHTML(html){this.hosts=new Map([...html.matchAll(/data-host="([^"]+)"/g)].map(m=>[m[1],new El()]));this.ids=new Map([...html.matchAll(/id="([^"]+)"/g)].map(m=>[m[1],new El()]));}
  querySelector(selector){if(selector.startsWith('[data-host='))return this.hosts?.get(selector.match(/"([^"]+)"/)[1]);if(selector.startsWith('#'))return this.ids?.get(selector.slice(1));return this.children.find(x=>selector.split(',').some(s=>s.trim().split('[')[0].toUpperCase()===x.tagName));}
 }
 const body=new El('body'),calls=[],gets=[],alerts=[];let config={image:{provider:'gpt_image'},cover:{mode:'titled',provider:'modelscope'},generate:{},tts:{}};
 const cover={mode:'titled',provider:'modelscope',cover:{},job:{status:'unknown',provider:'runninghub'}};
 const context={document:{body,createElement:tag=>new El(tag),querySelector:()=>null},Option:function(name,value){const x=new El('option');x.value=value;x.textContent=name;return x;},DOMParser:class{parseFromString(){return{querySelector:()=>null};}},BgmLibrary:{mount:()=>({apply:async()=>{},destroy(){}})},location:{href:''},alert:message=>alerts.push(message),crypto:{randomUUID:()=> '11111111-2222-4333-8444-555555555555'},
  fetch:async path=>{gets.push(path);if(path==='/index.html')return{ok:true,text:async()=>'<form>'};return{ok:true,json:async()=>path.startsWith('/api/task-cover/')?cover:path.includes('/templates/')?{templates:[]}:{client_config:config,info:{queue:{status:'failed'}}}};},
  api:async(path,method,value)=>{calls.push({path,body:JSON.parse(JSON.stringify(value))});if(path.endsWith('/config'))config=value;if(rejectReplacement&&path.endsWith('/replace-unknown'))throw Error('fixture replacement rejected');return{};}};
 vm.createContext(context);vm.runInContext(read('assets/workflow_actions.js'),context);
 return{open:()=>context.openStepEditor('isolated-cover','6'),body,calls,gets,alerts,dialog:()=>body.children.at(-1)};
}
test('step six requires inline acknowledgement before saving and orders config, recovery, enqueue',async()=>{
 const f=editorFixture();await f.open();const dialog=f.dialog();assert.ok(f.gets.includes('/api/task-cover/isolated-cover?slot=1'));assert.equal(dialog.ids.get('cover-replacement-notice').hidden,false);
 await dialog.ids.get('step-editor-save').onclick();assert.equal(f.calls.length,0);assert.match(dialog.ids.get('cover-replacement-error').textContent,/勾选/);
 dialog.ids.get('cover-replacement-ack').checked=true;await dialog.ids.get('step-editor-save').onclick();assert.deepEqual(f.calls.map(x=>x.path),['/api/task/isolated-cover/config','/api/task-cover/isolated-cover/replace-unknown','/api/task/isolated-cover/enqueue']);
 assert.deepEqual(f.calls[1].body,{slot:1,provider:'modelscope',operation_id:'11111111-2222-4333-8444-555555555555',acknowledge_unknown:true});assert.deepEqual(f.calls[2].body,{from_step:'6'});
});
test('failed recovery never enqueues and retry preserves operation identity',async()=>{
 const f=editorFixture({rejectReplacement:true});await f.open();const dialog=f.dialog();dialog.ids.get('cover-replacement-ack').checked=true;
 await dialog.ids.get('step-editor-save').onclick();await dialog.ids.get('step-editor-save').onclick();assert.equal(f.calls.filter(x=>x.path.endsWith('/enqueue')).length,0);assert.equal(f.calls.filter(x=>x.path.endsWith('/replace-unknown')).length,2);assert.equal(f.calls[1].body.operation_id,f.calls[3].body.operation_id);
});
test('switching the selected replacement provider invalidates an earlier acknowledgement',async()=>{
 const f=editorFixture();await f.open();const dialog=f.dialog();dialog.ids.get('cover-replacement-ack').checked=true;dialog.hosts.get('cover.provider').children[0].value='runninghub_workflow';dialog.events.change();
 assert.equal(dialog.ids.get('cover-replacement-ack').checked,false);assert.match(dialog.ids.get('cover-replacement-message').textContent,/RH币工作流/);await dialog.ids.get('step-editor-save').onclick();assert.equal(f.calls.length,0);
});
