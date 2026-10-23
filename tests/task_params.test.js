const test = require('node:test'), assert = require('node:assert/strict');
const fs = require('node:fs'), vm = require('node:vm');
const view = require('../assets/workflow_view.js');

class Element {
  constructor(tag) {this.tag=tag;this.children=[];this.dataset={};this.className='';this.textContent='';this.classList={add:n=>this.className+=' '+n,toggle:()=>{}};}
  append(...items) {for (const item of items) {this.children.push(item);if(item instanceof Element)item.parent=this;}}
  prepend(item) {this.children.unshift(item);item.parent=this;}
  replaceChildren(...items) {this.children=[];this.append(...items);}
  setAttribute(name,value) {this[name]=value;}
  addEventListener() {}
  focus() {}
  remove() {if(this.parent)this.parent.children=this.parent.children.filter(x=>x!==this);}
  querySelectorAll(selector) {return this.children.flatMap(x=>x instanceof Element?[...(x.className.split(' ').includes(selector.slice(1))?[x]:[]),...x.querySelectorAll(selector)]:[]);}
}

const saved = {info:{task_id:'isolated_parameters'}, steps:{}, client_config:{
  mode:'half',generate:{track:'folk-tale',line:'story',level:'deep',rounds:'fast',profile_id:'saved_profile',api_key:'should_not_be_displayed',extra:'保留原来的开头。\n结尾加一个问题，不要添加人名。'},
  image:{ratio:'1:1',style:'中国水墨',source:'ai',provider:'runninghub',templateSnapshot:{name:'保存的草稿模板'}},
  tts:{provider:'aura',speaker:'saved_voice',speed:.85},cover:{mode:'titled',ratio:'3:4',title:'保存的标题'},
  dynamic:{mode:'all',engine:'local-panzoom'},bgm_choice:'builtin'}, request:{level:'standard',style:'旧画风'}};

test('saved task parameters override request fallbacks and never expose credential fields',()=>{
  const groups=view.taskParameterGroups(saved);
  assert.deepEqual(groups.map(x=>x.title),['创作','画面','配音','封面','其他']);
  const text=JSON.stringify(groups);
  assert.match(text,/半自动/);assert.match(text,/中国水墨/);assert.match(text,/1:1/);
  assert.match(text,/saved_voice/);assert.match(text,/0.85x/);assert.match(text,/图片推拉/);
  assert.match(text,/保存的草稿模板/);assert.doesNotMatch(text,/should_not_be_displayed|旧画风/);
});

test('saved cover provider is shown independently from inner image provider',()=>{
  const groups=view.taskParameterGroups({client_config:{image:{provider:'modelscope'},cover:{mode:'title',provider:'runninghub'}}});
  assert.ok(groups[1].items.some(x=>x.label==='绘图引擎'&&/魔搭/.test(x.value)));
  assert.ok(groups[3].items.some(x=>x.label==='封面绘图引擎'&&x.value==='RunningHub'));
});

test('summary entry opens grouped read-only parameters, copies them, and closes without submitting a task',async()=>{
  const listeners=new Map(),win={addEventListener(k,v){listeners.set(k,v);},removeEventListener(k,v){if(listeners.get(k)===v)listeners.delete(k);}},body=new Element('body'),host=new Element('div');
  let copied='',requests=0;
  vm.runInNewContext(fs.readFileSync('assets/workflow_view.js','utf8'),{window:win,
    document:{body,createElement:t=>new Element(t)},navigator:{clipboard:{writeText:async t=>copied=t}},
    fetch:async()=>{requests++;throw new Error('No request should be made');}});
  const renderer=win.WorkflowView.mount(host,{});renderer.renderTask(saved);
  const entry=host.querySelectorAll('.task-params-entry')[0];
  assert.ok(entry,'左侧缺少查看创建参数入口');
  assert.equal(body.querySelectorAll('.task-params-dialog').length,0);
  assert.equal(host.querySelectorAll('.wv-preview-card').some(x=>x.children[0]?.textContent==='创建参数'),false);
  entry.onclick();
  const dialog=body.querySelectorAll('.task-params-dialog')[0];assert.ok(dialog);
  assert.equal(dialog['aria-label'],'创建参数');
  assert.equal(dialog.querySelectorAll('.task-params-group').length,5);
  await dialog.querySelectorAll('.task-params-copy')[0].onclick();
  assert.match(copied,/【创作】/);assert.match(copied,/中国水墨/);assert.doesNotMatch(copied,/should_not_be_displayed/);
  const descendants=item=>[item,...(item.children||[]).flatMap(child=>typeof child==='object'?descendants(child):[])];
  assert.ok(descendants(dialog).some(item=>item.textContent==='补充要求'));
  assert.ok(copied.includes('补充要求：'+saved.client_config.generate.extra));
  dialog.querySelectorAll('.task-params-close')[0].onclick();
  assert.equal(body.querySelectorAll('.task-params-dialog').length,0);assert.equal(listeners.size,0);
  entry.onclick();entry.onclick();assert.equal(body.querySelectorAll('.task-params-dialog').length,1);
  listeners.get('keydown')({key:'Escape'});
  assert.equal(body.querySelectorAll('.task-params-dialog').length,0);assert.equal(listeners.size,0);
  entry.onclick();body.querySelectorAll('.wv-params-overlay')[0].onclick();
  assert.equal(body.querySelectorAll('.task-params-dialog').length,0);assert.equal(requests,0);
});

test('missing saved parameters remain explicitly absent rather than fabricating defaults',()=>{
  assert.deepEqual(view.taskParameterGroups({info:{task_id:'legacy'},steps:{}}),[]);
});

test('extra requirements preserve full saved text, support old requests and respect an intentional clear',()=>{
 const get=value=>view.taskParameterGroups(value)[4].items.find(row=>row.label==='补充要求');
 const extra='不要添加新的人名。\n保留事实和数字。'+'补充细节。'.repeat(60);
 assert.equal(get({client_config:{generate:{extra}},request:{extra:'旧要求'}})?.value,extra);
 assert.equal(get({request:{extra}})?.value,extra);
 assert.equal(get({client_config:{generate:{extra:''}},request:{extra:'已清除'}}),undefined);
 assert.equal(get({client_config:{generate:{}}}),undefined);
});

test('reuse opens a new creation form without submitting or resuming the old task',()=>{
  const body=new Element('body'),host=new Element('div'),location={href:''};
  let requests=0;
  const win={location,addEventListener(){},removeEventListener(){}};
  vm.runInNewContext(fs.readFileSync('assets/workflow_view.js','utf8'),{window:win,
    document:{body,createElement:t=>new Element(t)},fetch:()=>{requests++;throw Error('No mutation allowed');}});
  win.WorkflowView.mount(host,{}).renderTask(saved);
  host.querySelectorAll('.task-params-entry')[0].onclick();
  const dialog=body.querySelectorAll('.task-params-dialog')[0];
  const reuse=dialog.querySelectorAll('.task-params-reuse')[0];
  assert.ok(reuse,'创建参数必须提供能实际使用的入口');
  assert.equal(reuse.textContent,'用此参数新建');
  assert.equal(dialog.querySelectorAll('.task-params-copy')[0].textContent,'复制参数说明');
  reuse.onclick();
  assert.equal(location.href,'/index.html?new=1&reuse=isolated_parameters');
  assert.equal(requests,0);
});

test('saved off, false and uploaded voice choices remain accurate with old request defaults',()=>{
  const groups=view.taskParameterGroups({client_config:{mode:'full',generate:{track:'character-story',keep_mode:false,publish:{}},
    image:{bgmPath:''},tts:{mode:'upload'},cover:{mode:'none'},dynamic:{mode:'off'}},
    request:{keep_mode:true,bgm_choice:'builtin',dynamic_mode:'all',cover_mode:'ai',tts_provider:'aura'}});
  const text=JSON.stringify(groups);
  assert.match(text,/人物故事/);assert.match(text,/本地上传/);assert.match(text,/不生成/);
  assert.ok(groups[4].items.some(x=>x.label==='背景音乐'&&x.value==='无'));
  assert.ok(groups[0].items.some(x=>x.label==='带货模式'&&x.value==='关闭'));
  assert.doesNotMatch(text,/视频生成方式|配音引擎/);
});
