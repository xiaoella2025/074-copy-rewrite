const test = require('node:test');
const assert = require('node:assert/strict');
const { runImagePipeline, assignMaterialsToShots } = require('../assets/image_pipeline.js');

test('素材未填写镜头号时按已选素材循环分配到全部镜头', () => {
  assert.deepEqual(assignMaterialsToShots(['m1', 'm2'], '', [1, 2, 3]),
    {1:'m1', 2:'m2', 3:'m1'});
  assert.deepEqual(assignMaterialsToShots(['m1', 'm2'], '2,4', [1, 2, 3, 4]),
    {2:'m1', 4:'m2'});
});

test('编辑改写稿创建的新版本从元信息与分镜续跑，不再次改写', async () => {
  const calls = [];
  const resume = {info:{task_id:'task_revision'}, steps:{rewrite:'人工改好的文案'}};
  const replies = [
    {task_id:'task_revision', steps:{'1':{text:'人工改好的文案'},meta:{title:'标题'},
      '2':{shots:[{idx:1,text:'一镜'}]}}},
    {results:[{idx:1,ok:true,duration:2,path:'audio.mp3'}]},
    {steps:{'3':[{idx:1,desc_prompt:'画面'}]}},
    {results:[{idx:1,ok:true,url:'/covers/a.png'}]},
    {draft_dir:'draft'},
  ];
  await runImagePipeline({
    request: async (path, body) => { calls.push({path,body}); return replies.shift(); },
    resume, generate:{reference:''}, tts:{provider:'aura'}, image:{provider:'gpt_image'},
  });
  assert.deepEqual(calls[0].body.run_steps, ['meta','2']);
  assert.equal(calls[0].body.rewritten, '人工改好的文案');
  assert.equal(calls[0].body.task_id, 'task_revision');
});

test('素材库未分配且禁止 AI 兜底时阻断草稿生成', async () => {
  const calls = [];
  const replies = [firstGeneration(),
    {results:[{idx:1,ok:true,duration:2,path:'audio.mp3'}]},
    {steps:{'3':[{idx:1,desc_prompt:'画面'}]}}];
  await assert.rejects(runImagePipeline({
    request: async (path) => { calls.push(path); return replies.shift(); },
    generate:{reference:'原文'}, tts:{provider:'aura'},
    image:{source:'mine', materials:{picks:{},fallback:'skip'}},
  }), /未分配素材/);
  assert.ok(!calls.includes('/api/step6_jianying_draft'));
});

test('动态分镜失败时阻断草稿生成并保留任务供续跑', async () => {
  const calls = [];
  const replies = [firstGeneration(),
    {results:[{idx:1,ok:true,duration:2,path:'audio.mp3'}]},
    {steps:{'3':[{idx:1,desc_prompt:'画面'}]}},
    {results:[{idx:1,ok:true,url:'/covers/a.png',task_local:'/api/task_image/task_1/1.png'}]},
    {results:[{idx:1,ok:false,error:'ffmpeg 找不到素材'}]}];
  await assert.rejects(runImagePipeline({
    request: async (path) => { calls.push(path); return replies.shift(); },
    generate:{reference:'原文'}, tts:{provider:'aura'},
    image:{provider:'gpt_image',ratio:'9:16'}, dynamic:{mode:'3'},
  }), /ffmpeg 找不到素材/);
  assert.ok(!calls.includes('/api/step6_jianying_draft'));
});

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

test('提示词与草稿模板快照传到实际生成请求，素材选择沿用', async () => {
  const calls = [];
  const prompt = {id:'saved-prompt',name:'提示词',step3SystemPrompt:'选定提示词'};
  const draft = {id:'saved-draft',name:'草稿',config:{canvas:{width:720,height:1280}}};
  const replies = [firstGeneration(),
    {results:[{idx:1,ok:true,duration:2,path:'audio.mp3'}]},
    {steps:{'3':[{idx:1,desc_prompt:'画面'}]}},
    {results:[{idx:1,ok:true,url:'/covers/one.png'}]},
    {draft_dir:'draft'}];
  await runImagePipeline({
    request: async (path,body)=>{calls.push({path,body});return replies.shift();},
    generate:{reference:'原文',prompt_template_id:prompt.id,prompt_template:prompt},
    tts:{provider:'aura'},
    image:{source:'mine',templateId:draft.id,templateSnapshot:draft,
      materials:{selected:['material-1'],fallback:'off'}}});
  assert.deepEqual(calls[0].body.prompt_template,prompt);
  assert.deepEqual(calls[2].body.prompt_template,prompt);
  assert.equal(calls[3].path,'/api/step4_from_materials');
  assert.equal(calls[3].body.assignments[0].material_id,'material-1');
  assert.deepEqual(calls[4].body.template_snapshot,draft);
});

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
    image:{provider:'modelscope',ratio:'9:16'},
    cover:{mode:'title',style:'写实',title:'封面题字',subtitle:'副标题',template:'emotional',ratio:'3:4'},
  });
  assert.equal(calls.at(-1).path, '/api/cover');
  assert.equal(calls.at(-1).body.provider, 'modelscope');
  assert.equal(calls.at(-1).body.title, '封面题字');
  assert.equal(calls.at(-1).body.subtitle, '副标题');
  assert.equal(calls.at(-1).body.cover_template, 'emotional');
  assert.equal(calls.at(-1).body.ratio, '3:4');
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

test('上传配音续跑按完整分镜时间轴只补缺失镜头', async () => {
  const calls = [];
  const resume = {info:{task_id:'task_upload',shot_count:2},steps:{
    rewrite:'改写稿',meta:{title:'标题'},shots:[{idx:1,text:'甲甲甲'},{idx:2,text:'乙乙乙'}],
    audios:[{name:'seg_001.mp3'}],
    segments:[{index:1,path:'saved.mp3',duration:2,text:'甲甲甲'}],
    uploaded_voice:true,
    prompts:[{idx:1,desc_prompt:'画一'},{idx:2,desc_prompt:'画二'}],
    images:[{name:'1.png',url:'/api/task_image/task_upload/1.png'},
      {name:'2.png',url:'/api/task_image/task_upload/2.png'}],
  }};
  const replies = [{results:[{idx:2,ok:true,path:'new.mp3',duration:4,text:'乙乙乙'}]},
    {draft_dir:'draft'}];
  await runImagePipeline({
    request: async (path, body) => { calls.push({path,body}); return replies.shift(); },
    resume, generate:{}, tts:{mode:'upload'}, image:{provider:'gpt_image'},
  });
  assert.deepEqual(calls.map(item => item.path), ['/api/step5_tts','/api/step6_jianying_draft']);
  assert.deepEqual(calls[0].body.segments.map(item => item.idx), [1,2]);
  assert.deepEqual(calls[0].body.only_idxs, [2]);
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
    image:{provider:'gpt_image',ratio:'1:1',templateId:'builtin-knowledge-card'},
    dynamic:{mode:'off'},
  });
  const paths = calls.map(c => c.path);
  assert.ok(!paths.includes('/api/step4_intro_video'));
  const draft = calls.find(c => c.path === '/api/step6_jianying_draft');
  assert.deepEqual(draft.body.videos, []);
  assert.equal(draft.body.template_id, 'builtin-knowledge-card');
});

test('本地背景音乐上传后写入草稿请求', async () => {
  const calls = [];
  const replies = [firstGeneration(),
    {results:[{idx:1,ok:true,path:'audio.mp3',duration:2}]},
    {steps:{'3':[{idx:1,desc_prompt:'画面'}]}},
    {results:[{idx:1,ok:true,url:'/covers/a.png'}]},
    {path:'task-bgm.mp3'}, {draft_dir:'draft'}];
  await runImagePipeline({
    request: async (path, body) => { calls.push({path,body}); return replies.shift(); },
    generate:{reference:'原文'}, tts:{provider:'aura'},
    image:{provider:'gpt_image',ratio:'9:16',bgmFile:new Blob(['ID3mock'])},
  });
  assert.ok(calls.find(item => item.path === '/api/bgm_upload')?.body instanceof FormData);
  assert.equal(calls.find(item => item.path === '/api/step6_jianying_draft').body.bgm_path, 'task-bgm.mp3');
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

test('双人播客 script_format=podcast 时 /api/generate 带 script_format，step5_tts mode=podcast 传 speaker', async () => {
  const calls = [];
  const replies = [
    {task_id:'task_p', steps:{
      '1':{text:'原文'}, 'meta':{title:'播客标题'},
      '2':{shots:[
        {idx:1,text:'你好',speaker:'A'},
        {idx:2,text:'今天聊 AI',speaker:'B'},
        {idx:3,text:'没错',speaker:'A'},
      ]},
    }},
    {results:[
      {idx:1,ok:true,path:'/p/1.mp3',duration:2,speaker:'A'},
      {idx:2,ok:true,path:'/p/2.mp3',duration:2,speaker:'B'},
      {idx:3,ok:true,path:'/p/3.mp3',duration:2,speaker:'A'},
    ], podcast_path:'/p/podcast.mp3', podcast_url:'/api/audio/task_p/podcast.mp3',
       speakers:{A:'voiceA',B:'voiceB'}, rounds:[{index:1,speaker:'A'}]},
    {steps:{'3':[
      {idx:1,desc_prompt:'p1'},{idx:2,desc_prompt:'p2'},{idx:3,desc_prompt:'p3'},
    ]}},
    {results:[
      {idx:1,ok:true,url:'/i/1.png'},{idx:2,ok:true,url:'/i/2.png'},{idx:3,ok:true,url:'/i/3.png'},
    ]},
    {draft_dir:'draft'},
  ];
  const result = await runImagePipeline({
    request: async (path, body) => { calls.push({path,body}); return replies.shift(); },
    generate:{}, tts:{provider:'volcengine', podcast:{speaker_a:'voiceA',speaker_b:'voiceB'}},
    image:{provider:'gpt_image',ratio:'9:16',resolution:'1k',concurrency:3},
    scriptFormat:'podcast',
  });
  const generate = calls.find(c => c.path === '/api/generate');
  assert.equal(generate.body.script_format, 'podcast');
  const tts = calls.find(c => c.path === '/api/step5_tts');
  assert.equal(tts.body.mode, 'podcast');
  assert.equal(tts.body.podcast.speaker_a, 'voiceA');
  assert.equal(tts.body.podcast.speaker_b, 'voiceB');
  assert.deepEqual(tts.body.segments.map(s => s.speaker), ['A','B','A']);
  const draft = calls.find(c => c.path === '/api/step6_jianying_draft');
  assert.equal(draft.body.podcast_path, '/p/podcast.mp3');
});

test('双人播客 step5 失败时阻断，不继续出图', async () => {
  const calls = [];
  const replies = [
    {task_id:'task_pf', steps:{
      '1':{text:'原文'}, 'meta':{title:'播客标题'},
      '2':{shots:[{idx:1,text:'你好',speaker:'A'}]},
    }},
    {results:[{idx:1,ok:false,error:'火山 API Key 未填'}]},
  ];
  await assert.rejects(runImagePipeline({
    request: async (path, body) => { calls.push({path,body}); return replies.shift(); },
    generate:{}, tts:{provider:'volcengine'},
    image:{provider:'gpt_image',ratio:'9:16',resolution:'1k',concurrency:3},
    scriptFormat:'podcast',
  }), /火山 API Key 未填/);
  assert.deepEqual(calls.map(c => c.path), ['/api/generate', '/api/step5_tts']);
});

test('双人播客缺合成音频时不生成草稿', async () => {
  const calls = [];
  const replies = [firstGeneration(),
    {results:[{idx:1,ok:true,path:'seg.mp3',duration:2}] }];
  await assert.rejects(runImagePipeline({
    request: async (path) => { calls.push(path); return replies.shift(); },
    generate:{reference:'原文'}, tts:{provider:'volcengine'},
    image:{provider:'gpt_image'}, scriptFormat:'podcast',
  }), /合成音频缺失/);
  assert.deepEqual(calls, ['/api/generate','/api/step5_tts']);
});

test('素材来源=mine 调 step4_from_materials 带 assignments + picks，未分配走 AI 兜底', async () => {
  const calls = [];
  const gen = {
    task_id: 'task_m', line: 'story', level: 'standard',
    steps: {
      '0': { reviewed_text: '原文' },
      '1': { text: '改写稿' },
      meta: { title: '标题', characters: [] },
      '2': { shots: [{ idx: 1, text: '第一镜' }, { idx: 2, text: '第二镜' }] },
      '3': [],
    },
  };
  const replies = [
    gen,
    {results:[{idx:1,ok:true,duration:2},{idx:2,ok:true,duration:2}]},
    {steps:{'3':[{idx:1,desc_prompt:'p1'},{idx:2,desc_prompt:'p2'}]}},
    {results:[
      {idx:1,ok:true,url:'/api/material/m1.png',task_local:'/api/task_image/x/1.png',source:'material'},
      {idx:2,ok:true,url:'/covers/fallback.png',task_local:'/api/task_image/x/2.png',source:'ai_fallback'},
    ]},
    {draft_dir:'draft'},
  ];
  await runImagePipeline({
    request: async (path, body) => { calls.push({path,body}); return replies.shift(); },
    generate:{reference:'原文'}, tts:{provider:'aura'},
    image:{provider:'gpt_image',ratio:'9:16',resolution:'1k',concurrency:3,
           source:'mine', materials:{picks:{1:'m1'}, fallback:'ai'}},
  });
  const mat = calls.find(c => c.path === '/api/step4_from_materials');
  assert.ok(mat, 'should call step4_from_materials');
  assert.equal(mat.body.fallback_to_ai, true);
  const a1 = mat.body.assignments.find(a => a.idx === 1);
  assert.equal(a1.material_id, 'm1');
  assert.ok(!a1.desc_prompt, '已分配素材的不传 desc_prompt');
  const a2 = mat.body.assignments.find(a => a.idx === 2);
  assert.ok(!a2.material_id, '未分配的不带 material_id');
  assert.equal(a2.desc_prompt, 'p2', '未分配时带 desc_prompt 用于 AI 兜底');
  const draft = calls.find(c => c.path === '/api/step6_jianying_draft');
  assert.equal(draft.body.images.length, 2);
});

test('素材来源=web 调 step4_web_search 把 desc_prompt 当 query', async () => {
  const calls = [];
  const replies = [
    firstGeneration(),
    {results:[{idx:1,ok:true,duration:2}]},
    {steps:{'3':[{idx:1,desc_prompt:'古风 山水'}]}},
    {results:[{idx:1,ok:true,url:'/api/task_image/x/1.jpg',task_local:'/api/task_image/x/1.jpg',source:'web'}]},
    {draft_dir:'draft'},
  ];
  await runImagePipeline({
    request: async (path, body) => { calls.push({path,body}); return replies.shift(); },
    generate:{reference:'原文'}, tts:{provider:'aura'},
    image:{provider:'gpt_image',ratio:'9:16',resolution:'1k',concurrency:3, source:'web'},
  });
  const web = calls.find(c => c.path === '/api/step4_web_search');
  assert.ok(web, 'should call step4_web_search');
  assert.equal(web.body.queries[0].query, '古风 山水');
  assert.equal(web.body.ratio, '9:16');
  // 不应该再调 step4_generate_images
  assert.ok(!calls.some(c => c.path === '/api/step4_generate_images'));
});

test('素材来源=external 把 provider 强制成 custom', async () => {
  const calls = [];
  const replies = [
    firstGeneration(),
    {results:[{idx:1,ok:true,duration:2}]},
    {steps:{'3':[{idx:1,desc_prompt:'p1'}]}},
    {results:[{idx:1,ok:true,url:'/covers/x.png',task_local:'/api/task_image/x/1.png'}]},
    {draft_dir:'draft'},
  ];
  await runImagePipeline({
    request: async (path, body) => { calls.push({path,body}); return replies.shift(); },
    generate:{reference:'原文'}, tts:{provider:'aura'},
    image:{provider:'gpt_image',ratio:'9:16',source:'external'},
  });
  const gen = calls.find(c => c.path === '/api/step4_generate_images');
  assert.equal(gen.body.provider, 'custom');
});

for (const [step,expected] of Object.entries({
  '0':['/api/generate','/api/step5_tts','/api/generate','/api/step4_generate_images','/api/step6_jianying_draft'],
  '1':['/api/generate','/api/step5_tts','/api/generate','/api/step4_generate_images','/api/step6_jianying_draft'],
  '2':['/api/generate','/api/step5_tts','/api/generate','/api/step4_generate_images','/api/step6_jianying_draft'],
  '5':['/api/step5_tts','/api/generate','/api/step4_generate_images','/api/step6_jianying_draft'],
  '3':['/api/generate','/api/step4_generate_images','/api/step6_jianying_draft'],
  '4':['/api/step4_generate_images','/api/step6_jianying_draft'],
  '6':['/api/step6_jianying_draft'],
})) test(`从第 ${step} 步重跑使该步及后续产物失效，上游产物保持`,async()=>{
  const calls=[];
  const resume={info:{task_id:'task_1'},steps:{rewrite:'改写稿',meta:{title:'标题'},
    shots:[{idx:1,text:'第一镜'}],prompts:[{idx:1,desc_prompt:'保存提示词'}],
    audios:[{name:'seg_001.mp3'}],segments:[{index:1,path:'a.mp3',duration:2}],
    images:[{name:'1.png',url:'/api/task_image/task_1/1.png'}],draft:{draft_dir:'旧草稿'}}};
  const original=JSON.stringify(resume);
  await runImagePipeline({resume,rerunFrom:step,mode:'half',generate:{reference:'原文'},
    tts:{provider:'aura'},image:{provider:'gpt_image'},
    request:async(path,body)=>{calls.push({path,body});
      if(path==='/api/generate')return body.run_steps.includes('3')?{steps:{'3':[{idx:1,desc_prompt:'新提示词',use_reference:false}]}}:firstGeneration();
      if(path==='/api/step5_tts')return {results:[{idx:1,ok:true,duration:2,path:'new.mp3'}]};
      if(path==='/api/step4_generate_images')return {results:[{idx:1,ok:true,url:'/covers/new.png'}]};
      return {draft_dir:'新草稿'};}});
  assert.deepEqual(calls.map(x=>x.path),expected);
  assert.equal(JSON.stringify(resume),original,'保留原任务产物对象');
  if(step==='0'||step==='1')assert.equal(calls[0].body.rewritten,undefined,'显式重跑改写不沿用半自动原文');
  if(step==='2'){assert.deepEqual(calls[0].body.run_steps,['2']);assert.deepEqual(calls[0].body.meta,resume.steps.meta);}
  const images=calls.find(x=>x.path==='/api/step4_generate_images');
  if(images&&step!=='4')assert.equal(images.body.prompts[0].use_reference,false,'参考图判断传入出图');
});

test('重新打包保留上传的 BGM，默认新任务不覆盖全局 BGM',async()=>{
  const resume={info:{task_id:'task_1'},steps:{rewrite:'改写稿',meta:{title:'标题'},
    shots:[{idx:1,text:'第一镜'}],prompts:[{idx:1,desc_prompt:'p'}],
    audios:[{name:'seg_001.mp3'}],segments:[{index:1,path:'a.mp3',duration:2}],
    images:[{name:'1.png',url:'/api/task_image/task_1/1.png'}],
    draft:{draft_dir:'old',bgm_path:'saved-bgm.mp3'}}};
  let payload;
  await runImagePipeline({resume,rerunFrom:'6',generate:{},tts:{},image:{},
    request:async(path,body)=>{payload=body;return {draft_dir:'new'};}});
  assert.equal(payload.bgm_path,'saved-bgm.mp3');
  const replies=[firstGeneration(),{results:[{idx:1,ok:true,duration:2}]},
    {steps:{'3':[{idx:1,desc_prompt:'p'}]}},{results:[{idx:1,ok:true,url:'/a.png'}]},
    {draft_dir:'new'}];
  await runImagePipeline({generate:{reference:'原文'},tts:{},image:{},
    request:async(path,body)=>{if(path==='/api/step6_jianying_draft')payload=body;return replies.shift();}});
  assert.equal(Object.hasOwn(payload,'bgm_path'),false);
});
