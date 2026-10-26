const test=require('node:test');
const assert=require('node:assert/strict');
const fs=require('node:fs');
const vm=require('node:vm');

const context={};
vm.createContext(context);
vm.runInContext(fs.readFileSync('assets/workflow_actions.js','utf8')+';this.rhWorkflowActive=rhWorkflowActive;this.clearInactiveRhWorkflow=clearInactiveRhWorkflow;',context);

test('cover RH workflow follows the effective cover engine',()=>{
  const cfg={cover:{provider:'modelscope',workflow:'qwen-simple'},image:{provider:'runninghub_workflow'}};
  assert.equal(context.rhWorkflowActive('cover',cfg),false);
  cfg.cover.provider='';
  assert.equal(context.rhWorkflowActive('cover',cfg),true);
  cfg.cover.provider='runninghub_workflow';
  assert.equal(context.rhWorkflowActive('cover',cfg),true);
});

test('switching to ModelScope clears only the irrelevant workflow choice',()=>{
  const cfg={cover:{provider:'modelscope',workflow:'qwen-simple',ratio:'9:16'},image:{provider:'runninghub_workflow',workflow:'flux-native'}};
  context.clearInactiveRhWorkflow('cover',cfg);
  assert.equal(cfg.cover.workflow,'');
  assert.equal(cfg.cover.provider,'modelscope');
  assert.equal(cfg.cover.ratio,'9:16');
  assert.equal(cfg.image.workflow,'flux-native');
});

test('scene workflow choice is hidden for non RH drawing engines',()=>{
  const cfg={image:{provider:'modelscope',workflow:'flux-native'},cover:{provider:'runninghub_workflow',workflow:'qwen-simple'}};
  assert.equal(context.rhWorkflowActive('image',cfg),false);
  context.clearInactiveRhWorkflow('image',cfg);
  assert.equal(cfg.image.workflow,'');
  assert.equal(cfg.cover.workflow,'qwen-simple');
});
