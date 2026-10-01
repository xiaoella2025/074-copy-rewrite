async function runImagePipeline({ request, generate, tts, image, cover, resume, mode = 'full',
  pauseMode = 'never', pauseStages = [], onPause = async () => true, onStage = () => {} }) {
  const prior = resume?.steps || {};
  const resumeReady = !!(resume?.info?.task_id && prior.rewrite && prior.meta && prior.shots?.length);
  if (!resumeReady && mode !== 'full' && !generate.reference?.trim()) {
    throw new Error('半自动和直播出片模式需要先填写完整口播文案');
  }
  const call = async (stage, path, body) => {
    onStage(stage, 'running');
    try {
      const result = await request(path, body);
      onStage(stage, 'done', result);
      return result;
    } catch (error) {
      onStage(stage, 'failed', error);
      throw error;
    }
  };
  const requireResults = (stage, results, expected) => {
    const failed = Array.isArray(results) ? results.find(item => !item || !item.ok) : null;
    if (!Array.isArray(results) || results.length !== expected || failed) {
      const error = new Error(`${stage}未完成：${failed?.error || '结果数量不完整'}`);
      onStage(stage, 'failed', error);
      throw error;
    }
  };
  const pauseAfter = async (stage, payload) => {
    const shouldPause = pauseMode === 'every' ||
      (pauseMode === 'key' && stage === 'generate') ||
      (pauseMode === 'custom' && pauseStages.includes(stage));
    if (shouldPause) {
      onStage(stage, 'paused', payload);
      if (!await onPause(stage, payload)) throw new Error(`${stage} 后已暂停，已完成产物保留在任务目录`);
    }
  };

  const gen = resumeReady ? {
    task_id: resume.info.task_id,
    steps: {'1': {text: prior.rewrite}, meta: prior.meta, '2': {shots: prior.shots}},
  } : await call('generate', '/api/generate', {
    ...generate, ...(resume?.info?.task_id ? {task_id: resume.info.task_id} : {}),
    ...(mode === 'full' ? {} : { rewritten: generate.reference }),
    run_steps: mode === 'full' ? ['0', '1', 'meta', '2'] : ['meta', '2'],
  });
  if (resumeReady) onStage('generate', 'done', gen);
  const taskId = gen?.task_id;
  const steps = gen?.steps || {};
  const shots = steps['2']?.shots || [];
  const rewritten = steps['1']?.text || '';
  const meta = steps.meta || {};
  if (!taskId || !rewritten || !shots.length) {
    throw new Error('文案和分镜尚未生成完整，无法继续配音');
  }
  if (!resumeReady) await pauseAfter('generate', gen);

  const audioNames = new Set((prior.audios || []).map(item => item.name));
  const savedSpeech = new Map((prior.segments || [])
    .filter(item => audioNames.has(`seg_${String(item.index).padStart(3, '0')}.mp3`))
    .map(item => [Number(item.index), {idx: Number(item.index), ok: true,
      path: item.path, duration: item.duration, text: item.text,
      url: `/api/audio/${taskId}/seg_${String(item.index).padStart(3, '0')}.mp3`}]));
  const missingSpeech = shots.filter(shot => !savedSpeech.has(Number(shot.idx)));
  let newSpeech = [];
  if (missingSpeech.length) {
    const response = await call('tts', '/api/step5_tts', {
      task_id: taskId,
      segments: missingSpeech.map(shot => ({ idx: shot.idx, text: shot.text })),
      speed: tts.speed, provider: tts.provider, speaker: tts.speaker,
    });
    requireResults('tts', response?.results, missingSpeech.length);
    newSpeech = response.results;
  }
  const speechByIdx = new Map([...savedSpeech.values(), ...newSpeech].map(item => [Number(item.idx), item]));
  const step5 = {results: shots.map(shot => speechByIdx.get(Number(shot.idx)))};
  requireResults('tts', step5.results, shots.length);
  if (!missingSpeech.length) onStage('tts', 'done', step5);
  else await pauseAfter('tts', step5);
  const durations = new Map(step5.results.map(item => [item.idx, item.duration]));
  const timedShots = shots.map(shot => ({ ...shot, duration: durations.get(shot.idx) }));

  const savedPrompts = prior.prompts || [];
  const promptsReady = savedPrompts.length === shots.length && savedPrompts.every(item => item.desc_prompt);
  const promptRun = promptsReady ? {steps:{'3':savedPrompts}} : await call('prompts', '/api/generate', {
    ...generate, reference: '', rewritten, shots: timedShots, meta,
    task_id: taskId, run_steps: ['3'],
  });
  if (promptsReady) onStage('prompts', 'done', promptRun);
  const prompts = promptRun?.steps?.['3'] || [];
  if (prompts.length !== shots.length || prompts.some(item => !item.desc_prompt)) {
    throw new Error('Step 3 绘图提示词未生成完整');
  }
  gen.steps['3'] = prompts;
  if (!promptsReady) await pauseAfter('prompts', promptRun);

  const savedImages = new Map((prior.images || []).map(item => {
    const match = item.name?.match(/^(\d+)\.(png|jpe?g|webp)$/i);
    return match ? [Number(match[1]), {idx:Number(match[1]), ok:true, url:item.url,
      task_local:item.url}] : [null, null];
  }).filter(([idx]) => idx !== null));
  const missingImages = prompts.filter(item => !savedImages.has(Number(item.idx)));
  let newImages = [];
  if (missingImages.length) {
    const response = await call('images', '/api/step4_generate_images', {
      prompts: missingImages.map(item => ({ idx: item.idx, desc_prompt: item.desc_prompt })),
      ratio: image.ratio, resolution: image.resolution, concurrency: image.concurrency,
      provider: image.provider, retry: !!image.retry, task_id: taskId,
    });
    requireResults('images', response?.results, missingImages.length);
    newImages = response.results;
  }
  const imageByIdx = new Map([...savedImages.values(), ...newImages].map(item => [Number(item.idx), item]));
  const step4 = {results: shots.map(shot => imageByIdx.get(Number(shot.idx)))};
  requireResults('images', step4.results, shots.length);
  if (!missingImages.length) onStage('images', 'done', step4);
  else await pauseAfter('images', step4);

  const title = meta.title || generate.title || '未命名任务';
  const step6 = prior.draft?.draft_dir ? prior.draft : await call('draft', '/api/step6_jianying_draft', {
    task_id: taskId,
    shots: timedShots,
    images: step4.results,
    segments: step5.results,
    title,
    ratio: image.ratio,
    cover_title: meta,
  });
  if (prior.draft?.draft_dir) onStage('draft', 'done', step6);
  if (!step6?.draft_dir) throw new Error('Step 6 没有返回剪映草稿目录');
  let coverResult = prior.cover?.url ? prior.cover : null;
  if (coverResult) onStage('cover', 'done', coverResult);
  else if (cover && ['ai', 'title', 'blank'].includes(cover.mode)) {
    coverResult = await call('cover', '/api/cover', {
      task_id: taskId, provider: image.provider, title, content: rewritten,
      style: cover.style || generate.style, hooks: generate.hooks || [],
      cover_mode: cover.mode,
    });
    if (!coverResult?.url) throw new Error('封面生成未返回图片地址');
  } else if (cover?.mode === 'upload') {
    coverResult = await call('cover', '/api/cover_upload', {
      task_id: taskId, data_url: cover.dataUrl,
    });
    if (!coverResult?.url) throw new Error('本地封面上传未返回地址');
  }
  return { gen, step4, step5, step6, cover: coverResult, taskId, title };
}

if (typeof window !== 'undefined') window.runImagePipeline = runImagePipeline;
if (typeof module !== 'undefined' && module.exports) {
  module.exports = { runImagePipeline };
}
