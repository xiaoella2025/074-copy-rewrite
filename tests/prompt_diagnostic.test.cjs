const test=require('node:test'),assert=require('node:assert/strict'),fs=require('node:fs'),vm=require('node:vm');
class Element{
 constructor(tag){this.tag=tag;this.children=[];this.dataset={};this.className='';this.textContent='';this.classList={add:n=>this.className+=' '+n,toggle(){}};}
 append(...x){this.children.push(...x);}prepend(...x){this.children.unshift(...x);}replaceChildren(...x){this.children=x;}setAttribute(){}addEventListener(){}
 all(){return this.children.flatMap(x=>[x,...(x.all?.()||[])]);}querySelectorAll(s){return this.all().filter(x=>x.className?.split(' ').includes(s.slice(1)));}
}
function render(diagnostic){const host=new Element('div'),win={};vm.runInNewContext(fs.readFileSync('assets/workflow_view.js','utf8'),{window:win,document:{createElement:t=>new Element(t)}});win.WorkflowView.mount(host,{}).renderTask({info:{task_id:'fixture'},steps:{shots:[{idx:1,text:'fixture'}],prompts:[{idx:1,desc_prompt:'备用画面',diagnostic}]}});return host;}
function text(host){return host.all().map(x=>x.textContent).join(' ');}
test('saved invalid JSON explains format failure, attempts and fallback without exposing response body',()=>{
 const host=render({fellBackToSkeleton:true,attempts:[1,2,3].map(attempt=>({attempt,reason:'LLM 返回值不是合法 JSON: [{"cap":"他说"你好" PRIVATE_BODY"}]'}))});
 const value=text(host);assert.match(value,/JSON.*格式/);assert.match(value,/3 次/);assert.match(value,/备用画面/);assert.match(value,/第 1 次/);assert.match(value,/第 3 次/);assert.doesNotMatch(value,/PRIVATE_BODY/);assert.ok(host.all().some(x=>x.tag==='details'));
});
test('each saved retry distinguishes availability, missing field and visual-rule failures',()=>{
 const value=text(render({fellBackToSkeleton:true,attempts:[{attempt:1,reason:'LLM 调用失败 HTTP 503: No available accounts: SECRET'},{attempt:2,reason:'每项必须有非空字符串 desc_prompt'},{attempt:3,reason:'引号包裹文字 PRIVATE_DIALOGUE；改成具体动作和神情，不得引用台词'}]}));
 assert.match(value,/503.*无可用账号/);assert.match(value,/缺少.*画面描述/);assert.match(value,/台词/);assert.doesNotMatch(value,/SECRET|PRIVATE_DIALOGUE/);
});
test('unknown cause is honest and old diagnostic without attempts remains readable',()=>{
 assert.match(text(render({fellBackToSkeleton:true})),/未记录具体原因/);
 const value=text(render({fellBackToSkeleton:true,attempts:[{attempt:1,reason:'opaque https://private.invalid/?api_key=secret'}]}));
 assert.match(value,/无法确定/);assert.doesNotMatch(value,/private.invalid|secret/);
 assert.equal(render(undefined).querySelectorAll('.wv-prompt-warning').length,0);
});
