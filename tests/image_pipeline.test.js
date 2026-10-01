const test = require('node:test');
const assert = require('node:assert/strict');
const { runImagePipeline } = require('../assets/image_pipeline.js');

function firstGeneration() {
  return {
    task_id: 'task_1', line: 'story', level: 'standard',
    steps: {
      '0': { reviewed_text: '原文' },
      '1': { text: '改写稿' },
      meta: { title: '标题', characters: [] },
      '2': { shots: [{ idx: 1, text: '第一镜' }] },
      '3': [],
    },
  };
}

test('图文全链路按 0/1/2 → 5 → 3 → 4 → 6 运行并沿用任务 ID', async () => {
  const calls = [];
  const replies = [
    firstGeneration(),
    { results: [{ idx: 1, ok: true, text: '第一镜', duration: 2.4, path: 'audio.mp3' }] },
    { steps: { '3': [{ idx: 1, desc_prompt: '画面提示词' }] } },
    { results: [{ idx: 1, ok: true, url: '/covers/one.png' }] },
    { draft_dir: 'draft', shot_count: 1 },
  ];
  const result = await runImagePipeline({
    request: async (path, body) => { calls.push({ path, body }); return replies.shift(); },
    generate: { reference: '原文', title: '标题', track: 'character-story', style: '现代电影' },
    tts: { provider: 'minimax', speed: 1 },
    image: { ratio: '9:16', resolution: '1k', concurrency: 3 },
  });

  assert.deepEqual(calls.map(c => c.path), [
    '/api/generate', '/api/step5_tts', '/api/generate',
    '/api/step4_generate_images', '/api/step6_jianying_draft',
  ]);
  assert.deepEqual(calls[0].body.run_steps, ['0', '1', 'meta', '2']);
  assert.equal(calls[2].body.task_id, 'task_1');
  assert.equal(calls[2].body.shots[0].duration, 2.4);
  assert.equal(calls[4].body.task_id, 'task_1');
  assert.equal(result.gen.steps['3'][0].desc_prompt, '画面提示词');
});

test('配音部分失败时停止，不继续出图或声称完成', async () => {
  const calls = [];
  const replies = [
    firstGeneration(),
    { results: [{ idx: 1, ok: false, error: '账户未配置' }] },
  ];
  await assert.rejects(runImagePipeline({
    request: async (path, body) => { calls.push(path); return replies.shift(); },
    generate: { reference: '原文', title: '标题' },
    tts: { provider: 'minimax', speed: 1 },
    image: { ratio: '9:16', resolution: '1k', concurrency: 3 },
  }), /账户未配置/);
  assert.deepEqual(calls, ['/api/generate', '/api/step5_tts']);
});

test('半自动模式直接把原文作为分镜稿，不调用改写步骤', async () => {
  const calls = [];
  const replies = [
    { task_id: 'task_2', steps: { '1': {text:'原文'}, meta:{title:'标题'},
      '2':{shots:[{idx:1,text:'原文'}]} } },
    {results:[{idx:1,ok:true,duration:2,path:'audio.mp3'}]},
    {steps:{'3':[{idx:1,desc_prompt:'画面'}]}},
    {results:[{idx:1,ok:true,url:'/covers/a.png'}]},
    {draft_dir:'draft'},
  ];
  await runImagePipeline({
    request: async (path, body) => { calls.push({path,body}); return replies.shift(); },
    generate: {reference:'原文', title:'标题'}, mode:'half',
    tts:{provider:'aura', speaker:'voice_1', speed:1},
    image:{provider:'custom', ratio:'9:16', resolution:'1k', concurrency:2},
  });
  assert.deepEqual(calls[0].body.run_steps, ['meta','2']);
  assert.equal(calls[0].body.rewritten, '原文');
  assert.equal(calls[1].body.speaker, 'voice_1');
  assert.equal(calls[3].body.provider, 'custom');
});

test('关键节点暂停确认在配音前执行，取消后不触发收费步骤', async () => {
  const calls = [];
  await assert.rejects(runImagePipeline({
    request: async (path) => { calls.push(path); return firstGeneration(); },
    generate:{reference:'原文'}, tts:{provider:'aura'}, image:{provider:'gpt_image'},
    pauseMode:'key', onPause: async stage => { assert.equal(stage,'generate'); return false; },
  }), /已暂停/);
  assert.deepEqual(calls, ['/api/generate']);
});

test('选择 AI 封面时草稿完成后生成封面并沿用所选绘图引擎', async () => {
  const calls = [];
  const replies = [firstGeneration(),
    {results:[{idx:1,ok:true,duration:2,path:'audio.mp3'}]},
    {steps:{'3':[{idx:1,desc_prompt:'画面'}]}},
    {results:[{idx:1,ok:true,url:'/covers/a.png'}]},
    {draft_dir:'draft'},
    {url:'/covers/cover.png',prompt:'封面提示词'},
  ];
  const result = await runImagePipeline({
    request: async (path, body) => { calls.push({path,body}); return replies.shift(); },
    generate:{reference:'原文'}, tts:{provider:'aura'},
    image:{provider:'modelscope',ratio:'9:16'}, cover:{mode:'ai',style:'写实'},
  });
  assert.equal(calls.at(-1).path, '/api/cover');
  assert.equal(calls.at(-1).body.provider, 'modelscope');
  assert.equal(result.cover.url, '/covers/cover.png');
});

test('本地封面上传沿用同一任务 ID', async () => {
  const calls = [];
  const replies = [firstGeneration(),
    {results:[{idx:1,ok:true,duration:2,path:'audio.mp3'}]},
    {steps:{'3':[{idx:1,desc_prompt:'画面'}]}},
    {results:[{idx:1,ok:true,url:'/covers/a.png'}]},
    {draft_dir:'draft'}, {url:'/covers/upload.png'},
  ];
  await runImagePipeline({
    request: async (path, body) => { calls.push({path,body}); return replies.shift(); },
    generate:{reference:'原文'}, tts:{provider:'aura'}, image:{provider:'gpt_image'},
    cover:{mode:'upload',dataUrl:'data:image/png;base64,ZmFrZQ=='},
  });
  assert.equal(calls.at(-1).path, '/api/cover_upload');
  assert.equal(calls.at(-1).body.task_id, 'task_1');
});

test('从已完成的分镜配音绘图产物恢复时只生成缺失草稿', async () => {
  const calls = [];
  const resume = {info:{task_id:'task_1'},steps:{
    rewrite:'改写稿', meta:{title:'标题'}, shots:[{idx:1,text:'第一镜'}],
    segments:[{index:1,path:'audio.mp3',duration:2,text:'第一镜'}],
    audios:[{name:'seg_001.mp3',url:'/api/audio/task_1/seg_001.mp3'}],
    prompts:[{idx:1,desc_prompt:'画面'}],
    images:[{name:'1.png',url:'/api/task_image/task_1/1.png'}],
  }};
  const result = await runImagePipeline({
    request: async (path,body) => { calls.push({path,body}); return {draft_dir:'draft'}; },
    generate:{},tts:{provider:'aura'},image:{provider:'gpt_image',ratio:'9:16'},
    resume,
  });
  assert.deepEqual(calls.map(c => c.path), ['/api/step6_jianying_draft']);
  assert.equal(calls[0].body.images[0].idx, 1);
  assert.equal(result.taskId, 'task_1');
});

test('续跑只补缺失的配音和图片', async () => {
  const calls = [];
  const resume = {info:{task_id:'task_2'},steps:{
    rewrite:'改写稿', meta:{title:'标题'},
    shots:[{idx:1,text:'第一镜'},{idx:2,text:'第二镜'}],
    segments:[{index:1,path:'audio1.mp3',duration:2,text:'第一镜'}],
    audios:[{name:'seg_001.mp3',url:'/api/audio/task_2/seg_001.mp3'}],
    prompts:[{idx:1,desc_prompt:'画面一'},{idx:2,desc_prompt:'画面二'}],
    images:[{name:'1.png',url:'/api/task_image/task_2/1.png'}],
  }};
  const replies = [
    {results:[{idx:2,ok:true,path:'audio2.mp3',duration:3}]},
    {results:[{idx:2,ok:true,url:'/covers/2.png'}]},
    {draft_dir:'draft'},
  ];
  const result = await runImagePipeline({
    request: async (path, body) => { calls.push({path,body}); return replies.shift(); },
    generate:{},tts:{provider:'aura'},image:{provider:'gpt_image',ratio:'9:16'},resume,
  });
  assert.deepEqual(calls.map(c => c.path),
    ['/api/step5_tts','/api/step4_generate_images','/api/step6_jianying_draft']);
  assert.deepEqual(calls[0].body.segments.map(s => s.idx), [2]);
  assert.deepEqual(calls[1].body.prompts.map(p => p.idx), [2]);
  assert.equal(result.step5.results.length, 2);
  assert.equal(result.step4.results.length, 2);
});
