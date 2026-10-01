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

test('上传配音模式先调 /api/upload_voice 再以 mode=upload 切片', async () => {
  const calls = [];
  const file = new Blob([new Uint8Array(2048)], {type: 'audio/mpeg'});
  const replies = [
    firstGeneration(),
    {ok: true, task_id: 'task_1', path: '/tmp/seg_001.mp3', size: 2048, duration: 4.0},
    {results: [
      {idx:1,ok:true,path:'/tmp/seg_001.mp3',duration:2,text:'第一镜',duration_source:'upload_slice'},
    ], provider: 'upload'},
    {steps:{'3':[{idx:1,desc_prompt:'画面'}]}},
    {results:[{idx:1,ok:true,url:'/covers/a.png'}]},
    {draft_dir:'draft'},
  ];
  await runImagePipeline({
    request: async (path, body) => { calls.push({path,body}); return replies.shift(); },
    generate:{reference:'原文'}, tts:{mode:'upload', file},
    image:{provider:'gpt_image',ratio:'9:16',resolution:'1k',concurrency:1},
  });
  assert.deepEqual(calls.map(c => c.path),
    ['/api/generate','/api/upload_voice','/api/step5_tts','/api/generate',
     '/api/step4_generate_images','/api/step6_jianying_draft']);
  assert.ok(calls[1].body instanceof FormData, 'upload_voice 必须用 FormData');
  assert.equal(calls[2].body.mode, 'upload');
  assert.equal(calls[2].body.provider, undefined);
});

test('上传配音模式缺文件立即报错，不发起付费调用', async () => {
  const calls = [];
  await assert.rejects(runImagePipeline({
    request: async (path) => { calls.push(path); return firstGeneration(); },
    generate:{reference:'原文'}, tts:{mode:'upload'},  // file 缺失
    image:{provider:'gpt_image',ratio:'9:16'},
  }), /需要选择本地音频文件/);
  assert.deepEqual(calls, ['/api/generate']);  // generate 已调，但 upload_voice 没调
});

test('动态分镜 off 时不调用 step4_intro_video，step6 拿不到 videos', async () => {
  const calls = [];
  const replies = [firstGeneration(),
    {results:[{idx:1,ok:true,path:'audio.mp3',duration:2}]},
    {steps:{'3':[{idx:1,desc_prompt:'画面'}]}},
    {results:[{idx:1,ok:true,url:'/covers/a.png'}]},
    {draft_dir:'draft'}];
  await runImagePipeline({
    request: async (path, body) => { calls.push({path,body}); return replies.shift(); },
    generate:{reference:'原文'}, tts:{provider:'aura'},
    image:{provider:'gpt_image',ratio:'9:16'},
    dynamic:{mode:'off'},
  });
  const paths = calls.map(c => c.path);
  assert.ok(!paths.includes('/api/step4_intro_video'));
  const draft = calls.find(c => c.path === '/api/step6_jianying_draft');
  assert.deepEqual(draft.body.videos, []);
});

test('动态分镜=3 时调 step4_intro_video 把前 3 镜转视频，step6 优先 video material', async () => {
  const calls = [];
  const replies = [
    {task_id:'task_dyn', steps:{
      '1':{text:'原文'}, 'meta':{title:'标题'},
      '2':{shots:[
        {idx:1,text:'一'},{idx:2,text:'二'},{idx:3,text:'三'},{idx:4,text:'四'},
      ]},
    }},
    {results:[
      {idx:1,ok:true,path:'/a/seg_001.mp3',duration:2,text:'一'},
      {idx:2,ok:true,path:'/a/seg_002.mp3',duration:2,text:'二'},
      {idx:3,ok:true,path:'/a/seg_003.mp3',duration:2,text:'三'},
      {idx:4,ok:true,path:'/a/seg_004.mp3',duration:2,text:'四'},
    ]},
    {steps:{'3':[
      {idx:1,desc_prompt:'p1'},{idx:2,desc_prompt:'p2'},
      {idx:3,desc_prompt:'p3'},{idx:4,desc_prompt:'p4'},
    ]}},
    {results:[
      {idx:1,ok:true,url:'/i/1.png',task_local:'/tmp/1.png'},
      {idx:2,ok:true,url:'/i/2.png',task_local:'/tmp/2.png'},
      {idx:3,ok:true,url:'/i/3.png',task_local:'/tmp/3.png'},
      {idx:4,ok:true,url:'/i/4.png',task_local:'/tmp/4.png'},
    ]},
    {results:[
      {idx:1,ok:true,video_path:'/v/1.mp4',video_url:'/v/1.mp4',duration:2},
      {idx:2,ok:true,video_path:'/v/2.mp4',video_url:'/v/2.mp4',duration:2},
      {idx:3,ok:true,video_path:'/v/3.mp4',video_url:'/v/3.mp4',duration:2},
    ]},
    {draft_dir:'draft'},
  ];
  await runImagePipeline({
    request: async (path, body) => { calls.push({path,body}); return replies.shift(); },
    generate:{}, tts:{provider:'aura'},
    image:{provider:'gpt_image',ratio:'9:16',resolution:'1k',concurrency:3},
    dynamic:{mode:'3'},
  });
  const paths = calls.map(c => c.path);
  assert.ok(paths.includes('/api/step4_intro_video'));
  const intro = calls.find(c => c.path === '/api/step4_intro_video');
  assert.equal(intro.body.mode, '3');
  assert.equal(intro.body.shots.length, 4);  // 传全部让它自己裁前 3
  const draft = calls.find(c => c.path === '/api/step6_jianying_draft');
  assert.equal(draft.body.videos.length, 3);
  assert.deepEqual(draft.body.videos.map(v => v.idx), [1, 2, 3]);
});

test('动态分镜=custom 时只对指定 idx 出视频', async () => {
  const calls = [];
  const replies = [
    {task_id:'task_c', steps:{
      '1':{text:'原文'}, 'meta':{title:'标题'},
      '2':{shots:[
        {idx:1,text:'一'},{idx:2,text:'二'},{idx:3,text:'三'},{idx:4,text:'四'},
      ]},
    }},
    {results:[
      {idx:1,ok:true,path:'/a/1.mp3',duration:2},
      {idx:2,ok:true,path:'/a/2.mp3',duration:2},
      {idx:3,ok:true,path:'/a/3.mp3',duration:2},
      {idx:4,ok:true,path:'/a/4.mp3',duration:2},
    ]},
    {steps:{'3':[
      {idx:1,desc_prompt:'p1'},{idx:2,desc_prompt:'p2'},
      {idx:3,desc_prompt:'p3'},{idx:4,desc_prompt:'p4'},
    ]}},
    {results:[
      {idx:1,ok:true,url:'/i/1.png',task_local:'/tmp/1.png'},
      {idx:2,ok:true,url:'/i/2.png',task_local:'/tmp/2.png'},
      {idx:3,ok:true,url:'/i/3.png',task_local:'/tmp/3.png'},
      {idx:4,ok:true,url:'/i/4.png',task_local:'/tmp/4.png'},
    ]},
    {results:[
      {idx:2,ok:true,video_path:'/v/2.mp4',video_url:'/v/2.mp4',duration:2},
      {idx:4,ok:true,video_path:'/v/4.mp4',video_url:'/v/4.mp4',duration:2},
    ]},
    {draft_dir:'draft'},
  ];
  await runImagePipeline({
    request: async (path, body) => { calls.push({path,body}); return replies.shift(); },
    generate:{}, tts:{provider:'aura'},
    image:{provider:'gpt_image',ratio:'9:16',resolution:'1k',concurrency:3},
    dynamic:{mode:'custom', custom_idxs:[2,4]},
  });
  const intro = calls.find(c => c.path === '/api/step4_intro_video');
  assert.equal(intro.body.mode, 'custom');
  assert.deepEqual(intro.body.custom_idxs, [2, 4]);
  const draft = calls.find(c => c.path === '/api/step6_jianying_draft');
  assert.deepEqual(draft.body.videos.map(v => v.idx), [2, 4]);
});
