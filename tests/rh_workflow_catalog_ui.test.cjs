const test=require('node:test'),assert=require('node:assert/strict'),fs=require('node:fs');
const read=name=>fs.readFileSync(name,'utf8');
test('settings provides catalog add and selection status without claiming fixed price',()=>{
 assert.match(read('settings.html'),/rhw-add-name/);assert.match(read('settings.html'),/rhw-add-url/);
 assert.match(read('assets/rh_workflow_settings.js'),/workflows\/add/);assert.match(read('assets/rh_workflow_settings.js'),/未实测/);
});
test('create form persists separate scene and cover workflow fields',()=>{
 const s=read('index.html');assert.match(s,/id="img-workflow"/);assert.match(s,/id="cover-workflow"/);
 assert.match(s,/workflow:.*img-workflow/);assert.match(s,/workflow:.*cover-workflow/);
 assert.match(read('assets/task_reuse.js'),/'workflow'/);
});
test('pipeline propagates workflow selection with each generation request',()=>{
 const s=read('assets/image_pipeline.js');assert.match(s,/workflow: image.workflow/);assert.match(s,/workflow: cover.workflow/);
});
test('existing task and creative selectors can use independent catalog choices',()=>{
 assert.match(read('assets/workflow_actions.js'),/catalog:'rhworkflows'/);
 assert.match(read('assets/task_cover.js'),/RH币工作流选择/);
 assert.match(read('assets/creative.js'),/coverWorkflow/);assert.match(read('assets/creative.js'),/imageWorkflow/);
});

const vm=require('node:vm');
test('resume restores scene and cover workflow from their saved config objects',()=>{
 const source=read('index.html'),start=source.indexOf('function restoreRhWorkflowChoices(');assert.ok(start>=0,'resume restoration helper exists');
 const end=source.indexOf('function syncRhWorkflowOptions(',start),nodes=Object.fromEntries(['img-engine','cover-engine','img-workflow','cover-workflow'].map(id=>[id,{value:'',options:[],append(option){this.options.push(option);}}]));
 class Option{constructor(text,value){this.text=text;this.value=value;}}
 const calls=[];const ctx={$:id=>nodes[id],Option,updateImageFallbackHint(){},setChipsActive(...args){calls.push(args);},syncCoverMode(){calls.push(['visible']);}};vm.createContext(ctx);vm.runInContext(source.slice(start,end),ctx);
 ctx.restoreRhWorkflowChoices({image:{provider:'runninghub_workflow',workflow:'flux-native'},cover:{mode:'title',provider:'runninghub_workflow',workflow:'sdxl-native'}});
 assert.equal(nodes['img-workflow'].value,'flux-native');assert.equal(nodes['cover-workflow'].value,'sdxl-native');assert.ok(calls.some(x=>x[0]==='cover-mode'&&x[1]==='title'));assert.ok(calls.some(x=>x[0]==='visible'));
 assert.match(read('assets/form_libraries.js'),/restoreRhWorkflowChoices\(d.client_config\)/);
});
