const test=require('node:test'),assert=require('node:assert/strict'),fs=require('node:fs');
const {runImagePipeline}=require('../assets/image_pipeline.js');
test('legacy tasks default to recovery while the new explicit opt-out is honored',async()=>{
 for(const [image,expected] of [[{},true],[{retry:false},true],[{autoRetry:false},false],[{autoRetry:true},true]]){
  const calls=[];
  await runImagePipeline({image,generate:{},tts:{},
   resume:{info:{task_id:'fixture'},steps:{rewrite:'fixture',meta:{title:'fixture'},shots:[{idx:1,text:'fixture'}],prompts:[{idx:1,desc_prompt:'fixture'}],segments:[{index:1,path:'fixture.mp3',duration:2}],audios:[{name:'seg_001.mp3'}]}},
   request:async(path,body)=>{calls.push({path,body});if(path==='/api/step4_generate_images')return{results:[{idx:1,ok:true,url:'/fixture.png'}]};if(path==='/api/step6_jianying_draft')return{draft_dir:'fixture'};throw Error('unexpected '+path);}});
  assert.equal(calls.find(x=>x.path==='/api/step4_generate_images').body.retry,expected);
 }
});
test('creation and parameter editor default to one retry and disclose per-image cost',()=>{
 const html=fs.readFileSync('index.html','utf8'),actions=fs.readFileSync('assets/workflow_actions.js','utf8'),reuse=fs.readFileSync('assets/task_reuse.js','utf8');
 assert.match(html,/class="toggle-row on" id="toggle-retry"/);assert.match(html,/可能消耗单张额度/);
 assert.match(actions,/path:\["image","autoRetry"\]/);assert.match(reuse,/i\.autoRetry!==false/);
});
