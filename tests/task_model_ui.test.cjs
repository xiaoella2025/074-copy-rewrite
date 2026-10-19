const test=require('node:test'),assert=require('node:assert/strict'),fs=require('node:fs'),vm=require('node:vm');
test('new task footer shows the active system profile as a read-only selection',()=>{
 const html=fs.readFileSync('index.html','utf8');
 const code=html.slice(html.indexOf('    // 模型下拉填充'),html.indexOf('    if (active?.has_key)'));
 const select={replaceChildren(...options){this.options=options;}};
 const context={$:()=>select,profiles:[{id:'old',name:'旧模型'},{id:'current',name:'当前',model:'model'}],active:{id:'current',name:'当前',model:'model'},Option:function(text,value){this.text=text;this.value=value;},escapeHtml:x=>x};
 vm.runInNewContext(code,context);
 assert.equal(select.options.length,1);assert.equal(select.options[0].value,'current');
 assert.match(select.options[0].text,/跟随系统/);
 assert.match(html,/<select[^>]*id="model-pick"[^>]*disabled/);
});
test('reuse cannot overwrite the current system model with a historical profile',()=>{
 const code=fs.readFileSync('assets/task_reuse.js','utf8');
 assert.doesNotMatch(code,/model\.value\s*=\s*g\.profile_id/);
 const html=fs.readFileSync('index.html','utf8');
 assert.doesNotMatch(html,/setText\("model-pick", req\.profile_id\)/);
 assert.match(html,/id === "model-pick"/,'old saved form profile is also ignored');
});
