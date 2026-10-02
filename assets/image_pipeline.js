function assignMaterialsToShots(selectedIds, idxText, shotIndices) {
  const ids = selectedIds.filter(Boolean);
  const target = idxText.trim()
    ? idxText.split(',').map(value => Number(value.trim())).filter(Number.isInteger)
    : shotIndices;
  const valid = new Set(shotIndices);
  const picks = {};
  if (!ids.length) return picks;
  target.filter(idx => valid.has(idx) && idx > 0).forEach((idx, i) => {
    picks[idx] = ids[i % ids.length];
  });
  return picks;
}

async function runImagePipeline({ request, generate, tts, image, cover, resume, dynamic, mode = 'full',
  scriptFormat = 'narrator',
  pauseMode = 'never', pauseStages = [], onPause = async () => true, onStage = () => {} }) {
  const makeFormData = (fields) => {
    const fd = new FormData();
    for (const [k, v] of Object.entries(fields)) {
      if (v === undefined || v === null) continue;
      if (k === 'file' && !(v instanceof Blob)) continue;
      fd.append(k, v);
    }
    return fd;
  };
  const prior = resume?.steps || {};
  const resumeReady = !!(resume?.info?.task_id && prior.rewrite && prior.meta && prior.shots?.length);
  const resumeRewrite = !!(resume?.info?.task_id && prior.rewrite && !resumeReady);
  if (!resumeReady && !resumeRewrite && mode !== 'full' && !generate.reference?.trim()) {
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
    ...(resumeRewrite ? {reference: '', rewritten: prior.rewrite}
      : mode === 'full' ? {} : { rewritten: generate.reference }),
    ...(scriptFormat ? { script_format: scriptFormat } : {}),
    run_steps: resumeRewrite ? ['meta', '2'] : mode === 'full' ? ['0', '1', 'meta', '2'] : ['meta', '2'],
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
  let podcastResult = prior.podcast?.podcast_path ? {
    path: prior.podcast.podcast_path,
    url: prior.podcast.podcast_url || '',
    rounds: prior.podcast.rounds || [],
    speakers: prior.podcast.speakers || {},
  } : null;
  if (missingSpeech.length) {
    let response;
    if (tts.mode === 'upload') {
      if (!tts.file && !prior.uploaded_voice) throw new Error('上传配音模式需要选择本地音频文件');
      if (tts.file) {
        const uploaded = await request('/api/upload_voice', makeFormData({
          task_id: taskId, file: tts.file,
        }));
        if (!uploaded?.ok) throw new Error('音频上传失败');
      }
      response = await call('tts', '/api/step5_tts', {
        task_id: taskId, mode: 'upload',
        segments: shots.map(shot => ({ idx: shot.idx, text: shot.text })),
        only_idxs: missingSpeech.map(shot => Number(shot.idx)),
      });
    } else if (scriptFormat === 'podcast') {
      response = await call('tts', '/api/step5_tts', {
        task_id: taskId, mode: 'podcast',
        segments: missingSpeech.map(shot => ({ idx: shot.idx, text: shot.text,
                                               speaker: shot.speaker || 'A' })),
        speed: tts.speed,
        provider: tts.provider || 'volcengine',
        podcast: tts.podcast || {},
      });
    } else {
      response = await call('tts', '/api/step5_tts', {
        task_id: taskId,
        segments: missingSpeech.map(shot => ({ idx: shot.idx, text: shot.text })),
        speed: tts.speed, provider: tts.provider, speaker: tts.speaker,
      });
    }
    requireResults('tts', response?.results, missingSpeech.length);
    newSpeech = response.results;
    if (scriptFormat === 'podcast' && response?.podcast_path) {
      podcastResult = { path: response.podcast_path,
                        url: response.podcast_url,
                        rounds: response.rounds || [],
                        speakers: response.speakers || {} };
    }
  }
  const speechByIdx = new Map([...savedSpeech.values(), ...newSpeech].map(item => [Number(item.idx), item]));
  const step5 = {results: shots.map(shot => speechByIdx.get(Number(shot.idx)))};
  requireResults('tts', step5.results, shots.length);
  if (scriptFormat === 'podcast' && !podcastResult?.path) {
    const error = new Error('双人播客合成音频缺失，无法生成草稿');
    onStage('tts', 'failed', error);
    throw error;
  }
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
    const imageSource = image.source || 'ai';
    const externalProvider = imageSource === 'external' ? 'custom' : image.provider;
    let endpoint = '/api/step4_generate_images';
    let payload;
    if (imageSource === 'mine') {
      const picked = {...(image.materials?.picks || {}), ...assignMaterialsToShots(
        image.materials?.selected || [], image.materials?.indices || '',
        missingImages.map(item => Number(item.idx)))};
      const fallbackToAi = (image.materials?.fallback || 'ai') === 'ai';
      if (!fallbackToAi && missingImages.some(item => !picked[item.idx])) {
        throw new Error('有分镜未分配素材；请补选素材或开启 AI 兜底');
      }
      payload = {
        task_id: taskId, ratio: image.ratio, resolution: image.resolution,
        fallback_to_ai: fallbackToAi, provider: externalProvider,
        assignments: missingImages.map(item => {
          const mid = picked[item.idx] || '';
          const assignment = { idx: item.idx, material_id: mid };
          if (fallbackToAi && !mid) assignment.desc_prompt = item.desc_prompt;
          return assignment;
        }).filter(a => a.material_id || fallbackToAi),
      };
      if (!payload.assignments.length) payload = null;
      else endpoint = '/api/step4_from_materials';
    } else if (imageSource === 'web') {
      endpoint = '/api/step4_web_search';
      payload = {
        task_id: taskId, ratio: image.ratio,
        queries: missingImages.map(item => ({ idx: item.idx, query: item.desc_prompt })),
      };
    } else {
      payload = {
        prompts: missingImages.map(item => ({ idx: item.idx, desc_prompt: item.desc_prompt })),
        ratio: image.ratio, resolution: image.resolution, concurrency: image.concurrency,
        provider: externalProvider, retry: !!image.retry, task_id: taskId,
      };
    }
    if (payload) {
      const response = await call('images', endpoint, payload);
      requireResults('images', response?.results, missingImages.length);
      newImages = response.results;
    }
  }
  const imageByIdx = new Map([...savedImages.values(), ...newImages].map(item => [Number(item.idx), item]));
  const step4 = {results: shots.map(shot => imageByIdx.get(Number(shot.idx)))};
  requireResults('images', step4.results, shots.length);
  if (!missingImages.length) onStage('images', 'done', step4);
  else await pauseAfter('images', step4);

  const dynamicMode = dynamic?.mode || 'off';
  const dynamicResults = prior.videos || [];
  let newVideos = [];
  const expectedVideos = dynamicMode === '3' ? Math.min(3, shots.length)
    : dynamicMode === 'custom' ? shots.filter(shot => (dynamic.custom_idxs || []).includes(Number(shot.idx))).length
    : shots.length;
  const savedVideoIndices = new Set(dynamicResults.filter(item => item?.ok).map(item => Number(item.idx)));
  const selectedVideoIndices = dynamicMode === '3' ? shots.slice(0, 3).map(shot => Number(shot.idx))
    : dynamicMode === 'custom' ? (dynamic.custom_idxs || []).map(Number)
    : shots.map(shot => Number(shot.idx));
  const videosReady = dynamicMode !== 'off' && selectedVideoIndices.length === expectedVideos &&
    selectedVideoIndices.every(idx => savedVideoIndices.has(idx));
  if (dynamicMode !== 'off' && taskId && !videosReady) {
    const videoResp = await call('videos', '/api/step4_intro_video', {
      task_id: taskId, mode: dynamicMode,
      custom_idxs: dynamicMode === 'custom' ? (dynamic.custom_idxs || []) : [],
      ratio: image.ratio,
      shots: step4.results.map((result, i) => ({
        idx: result?.idx ?? shots[i]?.idx,
        image_path: result?.task_local || result?.url || '',
        audio_path: step5.results.find(seg => seg.idx === result?.idx)?.path || '',
        duration: step5.results.find(seg => seg.idx === result?.idx)?.duration || 0,
      })).filter(item => item.image_path && item.audio_path && item.duration > 0),
    });
    newVideos = videoResp?.results || [];
    requireResults('videos', newVideos, expectedVideos);
  }
  const videoByIdx = new Map(dynamicResults.concat(newVideos)
    .filter(item => item?.ok).map(item => [Number(item.idx), item]));
  const step4WithVideo = {results: step4.results, videos: [...videoByIdx.values()]};
  if (dynamicMode !== 'off' && newVideos.length) onStage('videos', 'done', step4WithVideo);

  const title = meta.title || generate.title || '未命名任务';
  const step6 = prior.draft?.draft_dir ? prior.draft : await call('draft', '/api/step6_jianying_draft', {
    task_id: taskId,
    shots: timedShots,
    images: step4.results,
    videos: step4WithVideo.videos,
    segments: step5.results,
    podcast_path: podcastResult?.path || '',
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
      task_id: taskId, provider: image.provider, title: cover.title || title,
      subtitle: cover.subtitle || '', content: rewritten,
      style: cover.style || generate.style, hooks: generate.hooks || [],
      cover_mode: cover.mode, cover_template: cover.template || 'movie',
      ratio: cover.ratio || '3:4',
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
  module.exports = { runImagePipeline, assignMaterialsToShots };
}
