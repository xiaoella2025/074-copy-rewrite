const test=require('node:test'),assert=require('node:assert/strict'),fs=require('node:fs'),vm=require('node:vm');
function fixture(keep=false,shots=10,status="pausing"){
 let poll;
 class Node{
  constructor(tag){this.tagName=tag.toUpperCase();this.children=[];this.dataset={};this.style={};this.events={};this.value='';this.checked=false;this.disabled=false;this.textContent='';}
  appendChild(node){this.children.push(node);return node;}get lastChild(){return this.children.at(-1);}
  addEventListener(name,fn){this.events[name]=fn;}remove(){this.removed=true;}
  cloneNode(){const n=new Node(this.tagName);n.id=this.id;n.type=this.type;n.min=this.min;return n;}
  setAttribute(key,value){this[key]=value;}
  set innerHTML(html){this.hosts=new Map([...html.matchAll(/data-host="([^"]+)"/g)].map(m=>[m[1],new Node('div')]));this.help=new Map([...html.matchAll(/id="(field-help-[^"]+)"/g)].map(m=>[m[1],new Node('div')]));this.buttons=new Map(['close','cancel','save'].map(k=>['step-editor-'+k,new Node('button')]));this.html=html;}
  querySelector(selector){if(selector.startsWith('[data-host='))return this.hosts.get(selector.match(/"([^"]+)"/)[1]);if(selector.startsWith('#'))return this.help?.get(selector.slice(1))||this.buttons?.get(selector.slice(1));return this.children.flatMap(x=>[x,...x.children]).find(x=>selector.includes('input')&&x.tagName==='INPUT');}
 }
 const body=new Node('body'),number=new Node('input');number.id='shots';number.type='number';number.min='3';
 let config={mode:'full',generate:{keep_mode:keep,targets:{shots,words:100,words_min:50},product:'保留的商品信息'},image:{},tts:{}};
 const calls=[],alerts=[],context={document:{body,createElement:tag=>new Node(tag),createTextNode:text=>Object.assign(new Node('#text'),{textContent:text}),querySelector:()=>null},DOMParser:class{parseFromString(){return{querySelector:s=>s==='#shots'?number:null};}},
  setInterval:fn=>{poll=fn;return 1;},clearInterval:()=>{poll=null;},fetch:async path=>path==='/index.html'?{ok:true,text:async()=>'<form>'}:{json:async()=>({client_config:JSON.parse(JSON.stringify(config)),info:{queue:{status}}})},
  api:async(path,method,value)=>{calls.push({path,value:JSON.parse(JSON.stringify(value))});if(path.endsWith('/config'))config=JSON.parse(JSON.stringify(value));return{};},alert:text=>alerts.push(text),location:{href:''}};
 vm.createContext(context);vm.runInContext(fs.readFileSync('assets/workflow_actions.js','utf8'),context);
 return{context,setStatus:s=>status=s,poll:()=>poll?.(),open:key=>context.openStepEditor('isolated_editor',key),body,calls,alerts,config:()=>config,dialog:()=>body.children.at(-1)};
}
test('parameters are editable while pausing but saving waits for paused and clears polling on close',async()=>{
 const f=fixture();await f.open('2');const dialog=f.dialog(),save=dialog.buttons.get('step-editor-save');
 assert.equal(save.disabled,true);dialog.hosts.get('generate.targets.shots').querySelector('input').value='12';
 await save.onclick();assert.equal(f.calls.length,0);
 f.setStatus('paused');await f.poll();assert.equal(save.disabled,false);
 await save.onclick();assert.equal(f.config().generate.targets.shots,12);assert.equal(f.calls[1].value.from_step,'2');
});
test('closing an editor stops its pause polling without saving',async()=>{
 const f=fixture();await f.open('2');f.dialog().buttons.get('step-editor-cancel').onclick();
 f.setStatus('paused');assert.equal(f.poll(),undefined);assert.equal(f.calls.length,0);
});

test('a task restarted elsewhere cannot save or enqueue from the old editor',async()=>{
 const f=fixture(false,10,'paused');await f.open('2');const save=f.dialog().buttons.get('step-editor-save');
 f.setStatus('running');await save.onclick();assert.equal(f.calls.length,0);assert.equal(save.disabled,true);
 f.setStatus('paused');await f.poll();assert.equal(save.disabled,false);
});
test('failed status refresh blocks saving and keeps the edited value',async()=>{
 const f=fixture(false,10,'paused');await f.open('2');const dialog=f.dialog(),input=dialog.hosts.get('generate.targets.shots').querySelector('input');input.value='12';
 f.context.fetch=async()=>({ok:false});await dialog.buttons.get('step-editor-save').onclick();
 assert.equal(f.calls.length,0);assert.equal(input.value,'12');assert.equal(dialog.buttons.get('step-editor-save').disabled,true);
 dialog.buttons.get('step-editor-cancel').onclick();
});
test('late status reply cannot reactivate a closed editor',async()=>{
 const f=fixture();await f.open('2');const dialog=f.dialog();let resolve;
 f.context.fetch=()=>new Promise(r=>resolve=r);const pending=f.poll();dialog.buttons.get('step-editor-cancel').onclick();
 resolve({ok:true,json:async()=>({info:{queue:{status:'paused'}}})});await pending;
 assert.equal(f.poll(),undefined);assert.equal(f.calls.length,0);assert.equal(dialog.buttons.get('step-editor-save').disabled,true);
});

test('draft editor opened during pausing resumes instead of invalidating existing outputs',async()=>{
 const f=fixture();vm.runInContext("STEP_FIELDS['6']=[]",f.context);await f.open('6');
 f.setStatus('paused');await f.poll();const save=f.dialog().buttons.get('step-editor-save');
 assert.equal(save.textContent,'保存并从断点续跑');await save.onclick();
 assert.equal(f.calls[1].path,'/api/task/isolated_editor/confirm');
 assert.equal(f.calls.some(c=>c.value?.from_step),false);
});
