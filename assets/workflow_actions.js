// ============== 任务工作流：重跑 / 改参数 ==============
// 供 index.html（运行/结果页）和 result.html 共用。

const STEP_LABELS_074 = {"0":"文案预审", "1":"智能改写与封面", "2":"影视分镜分句", "5":"TTS 配音", "3":"生成绘图提示词", "4":"批量生图", "6":"生成剪映草稿"};
const STEP_KEY_ORDER = ["0", "1", "2", "5", "3", "4", "6"];
const STEP_DESCRIPTIONS = {
  "0":"AI 预审会清理广告词、敏感词、错别字，并给出质量评级。",
  "1":"改写 + 生成标题/标签/评论/封面。保存后重跑本步及后续步骤，可能产生平台费用。",
  "2":"按字数/镜头数切分原文。",
  "3":"为每个分镜写画面描述。",
  "4":"调用绘图 API 批量出图。",
  "5":"逐镜生成音频或切分上传音频。",
  "6":"打包素材与字幕，生成剪映草稿。",
};

// 每一步对应的表单字段（直接复用首页「新建任务」表单里的字段）
// selector = 表单里的 CSS 选择器；path = 在 client_config 里的写入路径
const STEP_FIELDS = {
  "0": [
    {label:"原文 / 待改写文案", selector:"#reference-section textarea, textarea#reference, [data-step-field='reference']", path:["generate","reference"], type:"textarea"},
    {label:"处理模式（全流程）",selector:"#process-mode",path:["mode"],type:"chips"},
    {label:"视频形态",selector:"#video-form",path:["scriptFormat"],type:"chips",help:"双人播客需要重新生成对话与分镜；主播音色在 TTS 配音里设置。"},
    {label:"暂停确认（全流程）",selector:"#pause-mode",path:["pauseMode"],type:"chips"},
    {label:"自定义暂停节点",selector:"#pause-custom",path:["pauseStages"],type:"checks",help:"仅在暂停确认为自定义时生效。"},
  ],
  "1": [
    {label:"带货模式", selector:"#toggle-keep", path:["generate","keep_mode"], type:"switch", help:"开启时保留商品名称、价格和固定句子内容。保存后从改写开始重跑后续步骤。"},
    {label:"文案模型（跟随系统）",selector:"#model-pick",path:["generate","profile_id"],type:"select",catalog:"profiles"},
    {label:"提示词模板",selector:"#prompt-template",path:["generate","prompt_template_id"],type:"select",catalog:"prompts",help:"系统默认跟随内容赛道；此模板的绘图规则也用于后续提示词步骤。"},
    {label:"故事线 / 钩子线", selector:"#lines", path:["generate","line"], type:"chips"},
    {label:"改写等级", selector:"#levels-story", path:["generate","level"], type:"chips"},
    {label:"叙事视角", selector:"#viewpoints", path:["generate","viewpoint"], type:"chips"},
    {label:"内容赛道", selector:"#tracks", path:["generate","track"], type:"chips"},
    {label:"数据源（多选）",selector:"#sources",path:["generate","sources"],type:"chips-multi"},
    {label:"生成短标题",path:["generate","publish","short_title"],type:"switch"},
    {label:"生成发布文案",path:["generate","publish","summary"],type:"switch"},
    {label:"生成话题标签",path:["generate","publish","tags"],type:"switch"},
    {label:"生成种子评论",path:["generate","publish","comments"],type:"switch"},
    {label:"开头钩子（多选）", selector:"#hooks", path:["generate","hooks"], type:"chips-multi"},
    {label:"改写轮次", selector:"#rounds", path:["generate","rounds"], type:"chips"},
    {label:"标题", selector:"#title", path:["generate","title"], type:"text"},
    {label:"选题", selector:"#topic", path:["generate","topic"], type:"text"},
    {label:"关键词", selector:"#keywords", path:["generate","keywords"], type:"text"},
    {label:"带货商品", selector:"#product", path:["generate","product"], type:"text"},
    {label:"固定开头", selector:"#fixed-opening", path:["generate","fixed_opening"], type:"text"},
    {label:"结尾引导", selector:"#tail-guide", path:["generate","tail_guide"], type:"text"},
    {label:"额外指令", selector:"#extra", path:["generate","extra"], type:"text"},
  ],
  "2": [
    {label:"目标分镜数", selector:"#shots", path:["generate","targets","shots"], type:"number", help:"留空为自动；填写 10 即目标 10 个分镜。按目标分镜数切分时，每镜字数自动计算。"},
    {label:"每镜最少字数", selector:"#words-min", path:["generate","targets","words_min"], type:"number"},
    {label:"每镜最多字数", selector:"#words", path:["generate","targets","words"], type:"number"},
  ],
  "3": [
    {label:"画面风格", selector:"#style", path:["generate","style"], type:"chips",custom:"自定义",help:"选择自定义后填写画面风格描述。"},
  ],
  "4": [
    {label:"素材来源", selector:"#img-source", path:["image","source"], type:"chips"},
    {label:"绘图引擎", selector:"#img-engine", path:["image","provider"], type:"select",options:[['gpt_image','全能绘图'],['modelscope','魔搭 ModelScope'],['jimeng','即梦'],['runninghub','RunningHub 钱包绘图（不选工作流）'],['custom','自定义绘图'],['runninghub_workflow','RH币工作流（选候选）']]},
    {label:"内页RH币工作流",path:["image","workflow"],type:"select",options:[],catalog:'rhworkflows'},
    {label:"画幅比例", selector:"#img-ratio", path:["image","ratio"], type:"chips"},
    {label:"出图分辨率",path:["image","resolution"],type:"select",options:[['1k','1K'],['2k','2K'],['4k','4K']]},
    {label:"出图并发数",path:["image","concurrency"],type:"number",min:1,max:20},
    {label:"素材组筛选",selector:"#materials-group",path:["image","materials","group"],type:"select",catalog:"groups",help:"筛选可选素材；实际使用勾选的素材。"},
    {label:"素材选择（多选）",path:["image","materials","selected"],type:"materials",help:"仅在素材来源为素材库时生效；按所选顺序循环分配。"},
    {label:"素材分配镜头",selector:"#materials-assign-idxs",path:["image","materials","indices"],type:"text"},
    {label:"未分配素材的镜头",selector:"#materials-fallback",path:["image","materials","fallback"],type:"chips"},
    {label:"替换产品参考图",selector:"#prod-file",path:["image","referenceFile"],type:"file",upload:"/api/reference_upload",help:"未选文件保留已有参考图。"},
    {label:"动态分镜", selector:"#dynamic-shots", path:["dynamic","mode"], type:"chips"},
    {label:"视频生成方式", selector:"#dynamic-engine", path:["dynamic","engine"], type:"chips"},
    {label:"自定义动态镜头", selector:"#dynamic-custom-idxs", path:["dynamic","custom_idxs"], type:"indices"},
    {label:"单图失败自动重试", selector:"#toggle-retry", path:["image","autoRetry"], type:"switch",help:"普通失败只重试1次，可能消耗单张额度；超时先查原任务，成功图片不重画。"},
  ],
  "5": [
    {label:"配音模式", selector:"#tts-mode", path:["tts","mode"], type:"chips"},
    {label:"TTS 引擎", selector:"#tts-provider", path:["tts","provider"], type:"chips"},
    {label:"发音人", selector:"#voice", path:["tts","speaker"], type:"select"},
    {label:"主播 A 音色",selector:"#podcast-speaker-a",path:["tts","podcast","speaker_a"],type:"select",help:"仅双人播客生效。"},
    {label:"主播 B 音色",selector:"#podcast-speaker-b",path:["tts","podcast","speaker_b"],type:"select",help:"仅双人播客生效。"},
    {label:"语速", selector:"#tts-speed", path:["tts","speed"], type:"chips"},
    {label:"替换整段配音",selector:"#tts-upload-file",path:["tts","file"],type:"file",upload:"/api/upload_voice",help:"上传配音模式使用；未选文件保留已上传的配音。"},
  ],
  "6": [
    {label:"草稿模板",selector:"#draft-templates",path:["image","templateId"],type:"chips"},
    {label:"背景音乐",path:["image","bgmPath"],type:"bgm",help:"可批量导入常用音乐、逐首试听，选择一首用于本任务；更换音乐只需重新打包。"},
    {label:"封面模式", selector:"#cover-mode", path:["cover","mode"], type:"chips"},
    {label:"封面绘图引擎", selector:"#cover-engine", path:["cover","provider"], type:"select",options:[['','跟随内页绘图引擎'],['gpt_image','全能绘图'],['modelscope','魔搭 ModelScope'],['jimeng','即梦'],['runninghub','RunningHub 钱包绘图（不选工作流）'],['custom','自定义绘图'],['runninghub_workflow','RH币工作流（选候选）']]},
    {label:"封面RH币工作流",path:["cover","workflow"],type:"select",options:[],catalog:'rhworkflows'},
    {label:"封面模版", selector:"#cover-template", path:["cover","template"], type:"chips",custom:"custom",help:"选择自定义后填写构图描述。"},
    {label:"封面比例", selector:"#cover-ratio", path:["cover","ratio"], type:"chips"},
    {label:"封面标题",selector:"#cover-title",path:["cover","title"],type:"textarea",help:"可回车换行，按填写的行顺序排版。"},
    {label:"封面副标题",selector:"#cover-subtitle",path:["cover","subtitle"],type:"textarea"},
    {label:"封面构图方向",path:["cover","direction"],type:"number",min:0,max:2,help:"0 / 1 / 2 分别为所选模板的第 1 / 2 / 3 个方向。"},
    {label:"本地封面",path:["cover","dataUrl"],type:"file",accept:"image/*",help:"本地上传封面模式使用；未选文件保留原封面。"},
  ],
};

function _getInPath(obj, path) { return path.reduce((acc, k) => acc != null ? acc[k] : null, obj); }
function _setInPath(obj, path, val) { let o = obj; for (let i = 0; i < path.length - 1; i++) o = (o[path[i]] ||= {}); o[path[path.length - 1]] = val; }
function _escapeHtml(s) { return String(s ?? "").replace(/[&<>"']/g, c => ({"&":"&amp;","<":"&lt;",">":"&gt;","\"":"&quot;","'":"&#39;"}[c])); }

function rhWorkflowActive(scope,cfg) {
  const provider=scope==='cover'?(cfg.cover?.provider||cfg.image?.provider):cfg.image?.provider;
  return provider==='runninghub_workflow';
}
function clearInactiveRhWorkflow(scope,cfg) {
  if(!rhWorkflowActive(scope,cfg)&&cfg[scope])cfg[scope].workflow='';
}

function _coverReplacementPlan(info,cfg) {
  const job=info?.job||{},cover=cfg.cover||{};
  const normalize=value=>value==='custom'?'custom_image':value||'';
  const provider=normalize(cover.provider||cfg.image?.provider||info?.provider);
  const mode=cover.mode||info?.mode;
  const localCoverAvailable=typeof info?.localCoverAvailable==='boolean'?info.localCoverAvailable:!!info?.cover?.url;
  if(!['unknown','submitting'].includes(job.status)||job.taskId||job.result||!job.provider||localCoverAvailable||cover.dataUrl||!['title','titled','plain','blank'].includes(mode))return '';
  return provider&&provider!==normalize(job.provider)?provider:'';
}

// 读取 chip 组的当前选中值（单选）
function _readChips(root) {
  const active = root.querySelector(".chip.active");
  return active ? (active.dataset.val || active.dataset[Object.keys(active.dataset)[0]] || active.textContent.trim()) : null;
}
// 读取 chip 组的当前选中值（多选）
function _readChipsMulti(root) {
  return [...root.querySelectorAll(".chip.active")].map(c => c.dataset.val || c.textContent.trim());
}
// 写入 chip 组的选中状态
function _writeChips(root, val, multi) {
  const wanted = new Set((Array.isArray(val) ? val : val != null ? [val] : []).map(String));
  root.querySelectorAll(".chip").forEach(c => {
    const v = c.dataset.val || c.textContent.trim();
    c.classList.toggle("active", wanted.has(v));
  });
}

// 默认从这一步重跑（沿用上次参数，不打开表单）
const TASK_RESUME_OPERATIONS_074=new Map();
async function resumeTaskFromStep(taskId, fromKey) {
  const detail = await fetch("/api/task/" + encodeURIComponent(taskId), {cache:"no-store"}).then(r => r.json());
  const cfg = detail?.client_config;
  if (!cfg) throw new Error("未找到该任务的客户端配置；请从首页创建新任务");
  const label = STEP_LABELS_074[fromKey] || fromKey;
  const intentKey=taskId+':'+fromKey;
  if(!TASK_RESUME_OPERATIONS_074.has(intentKey))TASK_RESUME_OPERATIONS_074.set(intentKey,globalThis.crypto?.randomUUID?.()||'resume-'+Date.now()+'-'+Math.random().toString(16).slice(2));
  const job=await api(`/api/task/${encodeURIComponent(taskId)}/enqueue`, "POST", {from_step:String(fromKey),operation_id:TASK_RESUME_OPERATIONS_074.get(intentKey)});
  TASK_RESUME_OPERATIONS_074.delete(intentKey);
  if (typeof showRunScreen === 'function') showRunScreen(`已排队，从「${label}」继续执行后续步骤`);
  location.href = "/result.html?task=" + encodeURIComponent(job.task_id||taskId);
  return job;
}

// 打开聚焦式「改参数」对话框：复用新建任务表单里与本步骤相关的字段
async function openStepEditor(taskId, stepKey) {
  const detail = await fetch("/api/task/" + encodeURIComponent(taskId), {cache:"no-store"}).then(r => r.json());
  const cfg = detail?.client_config;
  if (!cfg) throw new Error("未找到该任务的客户端配置");
  let revisionCreated=false;
  const revisionOperation=globalThis.crypto?.randomUUID?.()||'revision-'+Date.now()+'-'+Math.random().toString(16).slice(2);
  const fields = STEP_FIELDS[stepKey];
  if (!fields) { alert("未知步骤：" + stepKey); return; }
  const label = STEP_LABELS_074[stepKey] || stepKey;
  const desc = STEP_DESCRIPTIONS[stepKey] || "";
  const isPausedDraft=value=>stepKey==='6'&&value.info?.queue?.status==='paused'&&
    !value.info?.completed_steps?.includes(6)&&!value.steps?.draft?.draft_dir;
  let resumePausedDraft=isPausedDraft(detail);
  // Detail is a separate page. Load the real creation controls without running its scripts.
  const formResponse = await fetch('/index.html', {cache:'no-store'});
  if (!formResponse.ok) throw new Error('无法读取任务参数表单');
  const formDocument = new DOMParser().parseFromString(await formResponse.text(), 'text/html');
  const control = selector => selector ? document.querySelector(selector) || formDocument.querySelector(selector) : null;
  const resources = {};
  const resourcePaths = {profiles:'/api/profiles',prompts:'/api/templates/prompts',drafts:'/api/templates/drafts',materials:'/api/materials',settings:'/api/settings',voices:'/assets/story_voice_reference.json',cover:'/api/task-cover/'+encodeURIComponent(taskId)+'?slot=1'};
  const needed = stepKey==='1'?['profiles','prompts']:stepKey==='4'?['materials','settings']:stepKey==='5'?['settings','voices']:stepKey==='6'?['drafts','cover','settings']:[];
  const loaded = await Promise.allSettled(needed.map(async key => {
    const response=await fetch(resourcePaths[key],{cache:'no-store'});
    if(response.ok===false)throw Error(`无法加载${key}`);
    resources[key]=await response.json();
  }));
  const loadError=loaded.find(r=>r.status==='rejected');if(loadError)throw loadError.reason;

  // 渲染字段：从 client_config 读值，复用首页表单的 chip / input / select 控件
  const overlay = document.createElement("div");
  overlay.style.cssText = "position:fixed;inset:0;background:rgba(0,0,0,.55);z-index:9999;display:grid;place-items:center;padding:20px";
  const publishFields = fields.filter(f => f.path[1] === 'publish');
  const renderField = f => {
    const compact = f.path[1] === 'publish';
    const wide = compact || ['chips','chips-multi','checks','materials','textarea','file','bgm','switch'].includes(f.type) || ['generate.product','generate.extra'].includes(f.path.join('.'));
    const helpId = `field-help-${f.path.join("-")}`;
    return `
      <div class="wv-edit-field${compact ? ' wv-edit-toggle' : wide ? ' wv-edit-wide' : ''}" data-path="${f.path.join(".")}">
        ${compact ? '' : `<div class="wv-edit-label">${_escapeHtml(f.label)}</div>`}
        <div data-host="${f.path.join(".")}"></div>
        <div id="${helpId}" class="wv-edit-help"></div>
      </div>`;
  };
  const fieldsHtml = fields.map(f => f.path[1] !== 'publish' ? renderField(f) : f === publishFields[0] ?
    `<fieldset class="wv-edit-publish wv-edit-wide"><legend>发布素材（勾选生成）</legend><div class="wv-edit-toggle-row">${publishFields.map(renderField).join('')}</div></fieldset>` : '').join('');
  overlay.innerHTML = `
    <div class="wv-editor-dialog">
      <div style="display:flex;align-items:center;justify-content:space-between;margin-bottom:6px">
        <h3 style="margin:0;font-size:15px">✎ ${_escapeHtml(label)} 相关参数</h3>
        <button id="step-editor-close" style="background:transparent;border:0;color:var(--muted);cursor:pointer;font-size:18px">×</button>
      </div>
      <p style="font-size:12px;color:var(--muted);margin:0 0 16px">${_escapeHtml(desc)}</p>
      <div class="wv-edit-fields">${fieldsHtml}</div>
      ${stepKey==='6'?`<div id="cover-replacement-notice" role="status" hidden style="margin-top:14px;padding:12px;border:1px solid var(--warning);border-radius:6px">
        <p id="cover-replacement-message" style="margin:0 0 10px"></p>
        <label style="display:flex;gap:8px;align-items:flex-start"><input type="checkbox" id="cover-replacement-ack">我确认保留旧单，并使用所选新平台生成缺失封面，可能产生新平台费用。</label>
        <p id="cover-replacement-error" aria-live="polite" style="color:var(--warning);margin:8px 0 0"></p>
      </div>`:''}
      <div style="display:flex;gap:8px;justify-content:flex-end;margin-top:18px">
        <button id="step-editor-cancel" style="padding:8px 16px;border:1px solid var(--border);background:var(--panel-2);color:var(--text);border-radius:6px;cursor:pointer">取消</button>
        <button id="step-editor-save" style="padding:8px 18px;border:0;background:var(--accent);color:var(--bg);border-radius:6px;cursor:pointer;font-weight:600">保存并从这一步重跑</button>
      </div>
    </div>`;
  document.body.appendChild(overlay);
  let musicEditor=null,closed=false,saving=false,pausePoll=null,pauseRequest=null,waitingForPause=false;
  const saveControl=overlay.querySelector('#step-editor-save');
  const updateSaveControl=()=>{
    if(closed)return;
    saveControl.disabled=saving||waitingForPause;
    saveControl.textContent=waitingForPause?'暂停完成后可保存':resumePausedDraft?'保存并从断点续跑':((detail.info?.completed_steps||[]).map(String).includes('6')||detail.steps?.draft?.draft_dir)?'保存为新任务并重跑':'保存并从这一步重跑';
    saveControl.title=waitingForPause?'参数可以先修改；当前请求保存并暂停后，才会应用修改和重跑':'';
  };
  const syncPauseState=info=>{
    waitingForPause=['queued','running','pausing','cancelling'].includes(info?.queue?.status)||(!info?.queue&&!!info?.running);
    if(waitingForPause&&pausePoll===null)pausePoll=setInterval(()=>checkPauseState(),800);
    if(!waitingForPause&&pausePoll!==null){clearInterval(pausePoll);pausePoll=null;}
    updateSaveControl();
  };
  const checkPauseState=()=>{
    if(closed)return Promise.resolve();
    if(pauseRequest)return pauseRequest;
    pauseRequest=(async()=>{
      try{
        const response=await fetch('/api/task/'+encodeURIComponent(taskId),{cache:'no-store'});
        if(response.ok===false)throw Error('无法确认任务暂停状态');
        const current=await response.json();
        if(!closed){resumePausedDraft=isPausedDraft(current);syncPauseState(current.info);}
      }catch(error){
        if(!closed){syncPauseState({queue:{status:'pausing'}});saveControl.title='无法确认任务已暂停，正在重新检查；输入的参数保留';}
      }finally{pauseRequest=null;}
    })();
    return pauseRequest;
  };
  const close = () => {closed=true;if(pausePoll!==null)clearInterval(pausePoll);pausePoll=null;musicEditor?.destroy();overlay.remove();};
  overlay.querySelector("#step-editor-close").onclick = close;
  overlay.querySelector("#step-editor-cancel").onclick = close;
  syncPauseState(detail.info);
  overlay.addEventListener("click", e => { if (e.target === overlay) close(); });

  // 为每个字段填充控件
  for (const f of fields) {
    let v = _getInPath(cfg, f.path);
    if(f.path.join('.')==='tts.mode'&&v==='upload')v='custom';
    if(cfg.scriptFormat==='podcast'&&f.path.join('.')==='tts.mode')v='system';
    if(cfg.scriptFormat==='podcast'&&f.path.join('.')==='tts.provider')v='volcengine';
    const host = overlay.querySelector(`[data-host="${f.path.join(".")}"]`);
    const helpEl = overlay.querySelector(`#field-help-${f.path.join("-")}`);
    if (f.type === "chips" || f.type === "chips-multi") {
      // 渲染 chips（直接构造，复用 .chip 样式）
      const origChips = control(f.selector==="#levels-story"&&cfg.generate?.line==="user"?"#levels-user":f.selector);
      if (!origChips) { helpEl.textContent = `（表单里没找到 ${f.selector}，已跳过）`; continue; }
      const cloned = origChips.cloneNode(true);
      cloned.id = cloned.id + "-edit";
      cloned.style.display='';
      cloned.dataset.editFor = f.path.join(".");
      // 标记数据值：第一个 data-* 属性当作值
      cloned.querySelectorAll(".chip,.style-chip").forEach(c => {
        if (c.classList.contains('style-chip')) {c.classList.add('chip');c.dataset.val=c.dataset.style==='custom'?'自定义':c.textContent.trim();}
        const ds = Object.values(c.dataset).filter(v => v);
        if (ds.length && !c.dataset.val) c.dataset.val = ds[0];
        if (f.path.join('.')==='image.ratio') c.dataset.val={'916':'9:16','43':'4:3','11':'1:1','169':'16:9'}[c.dataset.ratio]||c.dataset.ratio;
        if (f.path.join('.')==='tts.speed') c.dataset.val=String(Number(c.dataset.speed)/(c.dataset.speed.length>=3?100:10));
      });
      if(f.path.join('.')==='image.templateId')for(const t of resources.drafts?.templates||[]){if([...cloned.querySelectorAll('.chip')].some(c=>c.dataset.val===t.id))continue;const chip=document.createElement('span');chip.className='chip';chip.dataset.val=t.id;chip.textContent=t.name;cloned.appendChild(chip);}
      if(v==null)v=f.type==='chips-multi'?_readChipsMulti(cloned):_readChips(cloned);
      // 设值
      for(const missing of (Array.isArray(v)?v:v!=null?[v]:[]).filter(value=>![...cloned.querySelectorAll('.chip')].some(c=>c.dataset.val===String(value)))) {
        const saved=document.createElement('span');saved.className='chip';saved.dataset.val=String(v);
        saved.dataset.val=String(missing);saved.textContent=f.path.join('.')==='image.templateId'?(cfg.image?.templateSnapshot?.name||String(missing)):String(missing);
        cloned.append(saved);
      }
      _writeChips(cloned, v, f.type === "chips-multi");
      // 事件：单击切换 active（多选可同时高亮多个）
      cloned.addEventListener("click", e => {
        const chip = e.target.closest(".chip");
        if (!chip) return;
        if (f.type === "chips-multi") chip.classList.toggle("active");
        else { cloned.querySelectorAll(".chip").forEach(c => c.classList.toggle("active", c === chip)); }
      });
      host.appendChild(cloned);
    } else if (f.type === "checks" || f.type === "materials") {
      const choices=f.type==='materials'?(resources.materials?.materials||resources.materials?.items||[]).map(x=>[x.id,x.name||x.filename||x.id,x.group||'']):[['generate','文案与分镜后'],['tts','配音后'],['prompts','绘图提示词后'],['images','出图后']];
      const saved=new Set(v||[]);
      for(const id of saved)if(!choices.some(x=>x[0]===id))choices.push([id,`已保存素材 ${id}`,'']);
      for(const [id,name,group] of choices){const row=document.createElement('label');row.style.cssText='display:block;padding:5px 0';row.dataset.group=group||'';const input=document.createElement('input');input.type='checkbox';input.value=id;input.checked=saved.has(id);row.appendChild(input);row.appendChild(document.createTextNode(' '+name));host.appendChild(row);}
    } else if (f.type === 'file') {
      const input=document.createElement('input');input.type='file';input.accept=f.accept||control(f.selector)?.accept||'';input.setAttribute('aria-label',f.label);host.appendChild(input);
    } else if (f.type === 'bgm') {
      musicEditor=BgmLibrary.mount(host,{current:cfg.image,taskId});
    } else if (f.type === "select") {
      const origSel = control(f.selector);
      if (!origSel&&!f.options) { helpEl.textContent = `（表单里没找到 ${f.selector}，已跳过）`; continue; }
      const cloned=origSel?origSel.cloneNode(true):document.createElement('select');
      cloned.id=(origSel?.id||f.path.join('-'))+'-edit';cloned.setAttribute('aria-label',f.label);
      let choices=f.options;
      if(f.catalog==='profiles'){
        const profiles=resources.profiles?.profiles||[],current=profiles.find(p=>p.enabled)||profiles[0];
        choices=[[current?.id||'','跟随系统 · '+(current?.name||'未配置模型')]];v=current?.id||'';cloned.disabled=true;
        const link=document.createElement('a');link.href='/settings.html';link.textContent='到系统设置切换；后续文字请求立即跟随';helpEl.appendChild(link);
      }
      if(f.catalog==='rhworkflows')choices=[['','跟随系统工作流'],...(resources.settings?.runninghub_workflow?.candidates||[]).map(x=>[x.key,x.name+(x.checked?' · 已核对':' · 待核对')])];
      if(f.catalog==='prompts')choices=[['','系统默认（跟随赛道）'],...(resources.prompts?.templates||[]).map(x=>[x.id,x.name])];
      if(f.catalog==='groups')choices=[['','全部素材'],...[...new Set((resources.materials?.materials||resources.materials?.items||[]).map(x=>x.group).filter(Boolean))].map(x=>[x,x])];
      if(choices){cloned.replaceChildren();for(const [id,name] of choices)cloned.appendChild(new Option(name,id));}
      if(v!=null && ![...cloned.options].some(o=>o.value===String(v)))cloned.append(new Option(String(v),String(v)));
      // 设值
      if (v != null) cloned.value = String(v);
      host.appendChild(cloned);
      if(f.catalog==='prompts')cloned.addEventListener('change',()=>{const t=resources.prompts?.templates?.find(x=>x.id===cloned.value),tracks=overlay.querySelector('#tracks-edit');if(t?.baseTrack&&tracks)_writeChips(tracks,t.baseTrack,false);});
    } else if (f.type === "switch") {
      const wrap = document.createElement("label");
      wrap.className = 'wv-edit-switch';
      const cb = document.createElement("input");
      cb.type = "checkbox";
      cb.setAttribute('aria-label', f.label);
      if(v==null&&f.path[1]==='publish')v=true;
      if(v==null&&f.path.join('.')==='image.autoRetry')v=true;
      cb.checked = !!v;
      cb.dataset.switchFor = f.path.join(".");
      wrap.appendChild(cb);
      const compact = f.path[1] === 'publish';
      wrap.appendChild(document.createTextNode(compact ? f.label.replace(/^生成/, '') : v ? "已开启" : "未开启"));
      if (!compact) cb.addEventListener("change", () => wrap.lastChild.textContent = cb.checked ? "已开启" : "未开启");
      host.appendChild(wrap);
    } else {
      // text / textarea
      const orig=control(f.selector)||(f.type==='number'&&!f.selector?document.createElement('input'):null);
      if (!orig) { helpEl.textContent = `（表单里没找到 ${f.selector}，已跳过）`; continue; }
      const isTextarea = orig.tagName === "TEXTAREA" || f.type === "textarea";
      const cloned = orig.cloneNode(false);
      cloned.id = (orig.id || "x") + "-edit";
      cloned.value = f.type === "indices" ? (v||[]).join(',') : v ?? "";
      cloned.disabled = false;
      cloned.setAttribute('aria-label',f.label);
      if(f.type==='number'){cloned.type='number';cloned.step='1';if(f.min!=null)cloned.min=String(f.min);if(f.max!=null)cloned.max=String(f.max);}
      if (f.path.join('.') === 'generate.targets.shots') cloned.placeholder = '自动（留空），或填写分镜数';
      if (isTextarea) cloned.style.cssText = "width:100%;min-height:90px;background:var(--code);color:var(--text);border:1px solid var(--border);border-radius:6px;padding:8px;font-family:inherit;resize:vertical";
      else cloned.style.cssText = "width:100%;background:var(--code);color:var(--text);border:1px solid var(--border);border-radius:6px;padding:8px";
      host.appendChild(cloned);
    }
    const chipControl=f.type==='chips'?host.children[0]:null;
    if(cfg.scriptFormat==='podcast'&&['tts.mode','tts.provider'].includes(f.path.join('.'))&&chipControl){chipControl.style.pointerEvents='none';chipControl.setAttribute('aria-disabled','true');helpEl.textContent='双人播客固定使用火山系统配音；视频形态在文案预审参数里调整。';}
    if(f.custom&&chipControl){
        const input=document.createElement('input');input.type='text';input.setAttribute('aria-label',f.label+'自定义描述');input.placeholder='填写自定义描述';input.style.cssText='width:100%;margin-top:6px';
        input.hidden=_readChips(chipControl)!==f.custom;chipControl.addEventListener('click',()=>input.hidden=_readChips(chipControl)!==f.custom);host.appendChild(input);
    }
    if (f.help) helpEl.textContent = f.help;
    if(f.type==='materials'&&!host.children.length)helpEl.textContent='素材库暂无图片，请先到素材库添加。';
  }

  const fieldControl=path=>overlay.querySelector(`[data-host="${path}"]`)?.querySelector('select, input');
  const syncRhWorkflow=()=>{
    const scope=stepKey==='6'?'cover':stepKey==='4'?'image':'';
    if(!scope)return;
    const effective={image:{...cfg.image},cover:{...cfg.cover}};
    const selected=fieldControl(scope+'.provider');if(selected)effective[scope].provider=selected.value;
    const row=overlay.querySelector(`[data-path="${scope}.workflow"]`);
    if(row)row.hidden=!rhWorkflowActive(scope,effective);
  };
  if(stepKey==='4'||stepKey==='6'){
    overlay.addEventListener('change',syncRhWorkflow);
    syncRhWorkflow();
  }
  let replacementProvider='',replacementOperation='';
  const replacementAck=overlay.querySelector('#cover-replacement-ack');
  const syncCoverReplacement=nextCfg=>{
    if(stepKey!=='6')return '';
    if(!nextCfg){nextCfg=JSON.parse(JSON.stringify(cfg));nextCfg.cover ||= {};
      const select=fieldControl('cover.provider');if(select)nextCfg.cover.provider=select.value;
      const group=overlay.querySelector('[data-host="cover.mode"]')?.querySelector('.chips, [id$="-edit"]');if(group)nextCfg.cover.mode=_readChips(group);
      if(overlay.querySelector('[data-host="cover.dataUrl"]')?.querySelector('input')?.files?.[0])nextCfg.cover.dataUrl='local upload';
    }
    const provider=_coverReplacementPlan(resources.cover,nextCfg);
    if(provider!==replacementProvider){replacementAck.checked=false;replacementOperation='';replacementProvider=provider;}
    const notice=overlay.querySelector('#cover-replacement-notice');if(notice)notice.hidden=!provider;
    if(provider){const names={runninghub:'RunningHub',modelscope:'魔搭',runninghub_workflow:'RH币工作流',custom_image:'自定义绘图',gpt_image:'全能绘图',jimeng:'即梦'};
      overlay.querySelector('#cover-replacement-message').textContent=`旧${names[resources.cover.job.provider]||resources.cover.job.provider}提交结果仍待核对，没有平台任务编号或结果；此次会用${names[provider]||provider}新生成一张封面，旧记录保留，可能产生新平台费用。已有成功图片和配音保留。`;
    }
    return provider;
  };
  if(stepKey==='6'){
    overlay.addEventListener('change',()=>syncCoverReplacement());overlay.addEventListener('click',()=>syncCoverReplacement());syncCoverReplacement();
    if(replacementAck)replacementAck.onchange=()=>overlay.querySelector('#cover-replacement-error').textContent='';
  }
  if(stepKey==='1'){
    const line=overlay.querySelector('#lines-edit'),level=overlay.querySelector('#levels-story-edit, #levels-user-edit');
    line?.addEventListener('click',()=>{
      const value=_readChips(line),original=control(value==='user'?'#levels-user':'#levels-story');if(!level||!original)return;
      level.replaceChildren(...[...original.querySelectorAll('.chip')].map(c=>{const clone=c.cloneNode(true);clone.dataset.val=c.dataset.key;return clone;}));
    });
  }
  if(stepKey==='4'){
    const group=fieldControl('image.materials.group'),list=overlay.querySelector('[data-host="image.materials.selected"]');
    const filter=()=>list?.querySelectorAll('label').forEach(row=>row.hidden=!!group?.value&&row.dataset.group!==group.value&&!row.querySelector('input').checked);
    group?.addEventListener('change',filter);filter();
  }
  if(stepKey==='5'){
    const providerGroup=overlay.querySelector('#tts-provider-edit');
    const syncVoices=preserve=>{
      const provider=_readChips(providerGroup)||cfg.tts?.provider||'volcengine',s=resources.settings?.tts||{};
      const list=[...(resources.voices?.voices?.[provider]||[])];
      for(const voice of s[provider+'_custom_voices']||[])if(!list.some(x=>x.id===voice.id))list.push(voice);
      const defaultId=s[provider==='aura'?'aura_voice_id':provider==='minimax'?'minimax_voice_id':'volcengine_speaker'];
      if(defaultId&&!list.some(x=>x.id===defaultId))list.push({id:defaultId,name:'已配置默认音色'});
      for(const path of ['tts.speaker','tts.podcast.speaker_a','tts.podcast.speaker_b']){
        const select=fieldControl(path);if(!select)continue;const saved=preserve?_getInPath(cfg,path.split('.')):null;
        const options=path==='tts.speaker'?list:[...(resources.voices?.voices?.volcengine||[])];
        const podcast=s.podcast||{},bound=path==='tts.podcast.speaker_a'?podcast.speaker_a:path==='tts.podcast.speaker_b'?podcast.speaker_b:null;
        select.replaceChildren();for(const v of options)select.appendChild(new Option(v.name||v.id,v.id));
        for(const id of [saved,bound])if(id&&![...select.options].some(o=>o.value===id))select.appendChild(new Option('已保存音色 · '+id,id));
        select.value=saved||bound||defaultId||options[0]?.id||'';
      }
    };
    syncVoices(true);providerGroup?.addEventListener('click',()=>syncVoices(false));
  }
  const countInput = overlay.querySelector('[data-host="generate.targets.shots"]')?.querySelector('input');
  const syncCount = () => {
    for (const path of ['generate.targets.words','generate.targets.words_min']) {
      const input = overlay.querySelector(`[data-host="${path}"]`)?.querySelector('input');
      if (input) input.disabled = Number(countInput?.value) > 0;
    }
  };
  if (countInput) {countInput.addEventListener('input', syncCount);syncCount();}
  overlay.querySelector("#step-editor-save").onclick = async () => {
    const saveButton=overlay.querySelector('#step-editor-save');
    if(saveButton.disabled)return;
    if (countInput && String(countInput.value).trim() && (!Number.isInteger(Number(countInput.value)) || Number(countInput.value) < Number(countInput.min || 1))) {
      alert(`目标分镜数请填写不小于 ${countInput.min || 1} 的整数，或留空使用自动。`);
      return;
    }
    for(const f of fields.filter(f=>f.type==='number')){
      const input=fieldControl(f.path.join('.'));if(!input||input.disabled||!String(input.value).trim())continue;
      const value=Number(input.value);if(!Number.isInteger(value)||(input.min&&value<Number(input.min))||(input.max&&value>Number(input.max))){alert(`${f.label}请填写有效整数。`);return;}
    }
    const words=fieldControl('generate.targets.words'),minWords=fieldControl('generate.targets.words_min');
    if(words&&!words.disabled&&words.value&&minWords?.value&&Number(minWords.value)>Number(words.value)){alert('每镜最少字数不能大于每镜最多字数。');return;}
    const nextCfg=JSON.parse(JSON.stringify(cfg));
    for (const f of fields) {
      if(f.catalog==='profiles')continue; // The saved ID is history, not a task override.
      const host = overlay.querySelector(`[data-host="${f.path.join(".")}"]`);
      if (!host || !host.children.length) continue;
      let val;
      if(f.type==='file'||f.type==='bgm')continue;
      if(f.type==='checks'||f.type==='materials')val=[...host.querySelectorAll('input:checked')].map(input=>input.value);
      else if (f.type === "chips") val = _readChips(host.querySelector(".chips, [id$='-edit']"));
      else if (f.type === "chips-multi") val = _readChipsMulti(host.querySelector(".chips, [id$='-edit']"));
      else if (f.type === "select") val = host.querySelector("select")?.value || null;
      else if (f.type === "switch") val = host.querySelector("input[type=checkbox]")?.checked || false;
      else {
        const input = host.querySelector("textarea, input");
        val = input?.value ?? "";
        if (f.type === "indices") val = [...new Set(val.split(',').map(s=>Number(s.trim())).filter(n=>Number.isInteger(n)&&n>0))];
        if (f.type === "number" || f.path[f.path.length - 1] === "shots" || f.path[f.path.length - 1] === "words") {
          val = val === "" ? null : Number(val);
        }
      }
      if(f.custom&&val===f.custom){val=host.querySelector('input')?.value.trim();if(!val){alert('请填写'+f.label+'的自定义描述。');return;}}
      _setInPath(nextCfg, f.path, val);
      if(f.path.join('.')==='tts.speed')_setInPath(nextCfg,f.path,Number(val));
    }
    if (countInput && Number(countInput.value) > 0) {
      _setInPath(nextCfg,['generate','targets','words'],null);
      _setInPath(nextCfg,['generate','targets','words_min'],null);
    }
    const replaceProvider=syncCoverReplacement(nextCfg);
    if(replaceProvider&&!replacementAck.checked){overlay.querySelector('#cover-replacement-error').textContent='请先勾选确认新平台生成与费用，再保存并重跑。';replacementAck.focus();return;}
    if(replaceProvider&&!replacementOperation)replacementOperation=globalThis.crypto?.randomUUID?.()||'xxxxxxxx-xxxx-4xxx-yxxx-xxxxxxxxxxxx'.replace(/[xy]/g,c=>{const r=Math.random()*16|0;return(c==='x'?r:(r&3|8)).toString(16);});
    saving=true;updateSaveControl();
    try {
      await checkPauseState();
      if(closed||waitingForPause)return;
      if(stepKey==='1'){
        const id=nextCfg.generate.prompt_template_id||nextCfg.generate.track||'character-story';
        const unchanged=id===cfg.generate.prompt_template_id;
        const snapshot=unchanged&&cfg.generate.prompt_template||resources.prompts?.templates?.find(t=>t.id===id);
        if(snapshot){nextCfg.generate.prompt_template_id=id;nextCfg.generate.prompt_template=snapshot;}
        else if(id!==cfg.generate.prompt_template_id&&fieldControl('generate.prompt_template_id'))throw Error('提示词模板已不存在，请重新选择');
      }
      if(stepKey==='3'&&nextCfg.cover)nextCfg.cover.style=nextCfg.generate.style;
      if(stepKey==='4'&&nextCfg.image?.source==='external')nextCfg.image.provider='custom';
      if(stepKey==='4')clearInactiveRhWorkflow('image',nextCfg);
      if(stepKey==='6')clearInactiveRhWorkflow('cover',nextCfg);
      if(stepKey==='5'){
        if(nextCfg.tts.mode==='custom')nextCfg.tts.mode='upload';
        if(nextCfg.scriptFormat==='podcast'){nextCfg.tts.mode='system';nextCfg.tts.provider='volcengine';}
      }
      if(stepKey==='6'&&nextCfg.image?.templateId!==cfg.image?.templateId){
        const selected=resources.drafts?.templates?.find(t=>t.id===nextCfg.image.templateId);
        if(!selected)throw Error('草稿模板已不存在，请重新选择');nextCfg.image.templateSnapshot=selected;
      }
      if(!revisionCreated&&((detail.info?.completed_steps||[]).map(String).includes('6')||detail.steps?.draft?.draft_dir)){
        const revision=await api('/api/task/fork','POST',{task_id:taskId,field:'pipeline',value:{operation_id:revisionOperation}});
        if(!revision.task_id)throw Error('未取得新版本任务编号');taskId=revision.task_id;revisionCreated=true;
      }
      for(const f of fields.filter(f=>f.type==='file'||f.type==='bgm')){
        const host=overlay.querySelector(`[data-host="${f.path.join('.')}"]`),file=host?.querySelector('input[type=file]')?.files?.[0];
        if(f.type==='bgm'){
          await musicEditor.apply(taskId,nextCfg.image);continue;
        }
        if(!file)continue;
        if(f.path.join('.')==='cover.dataUrl'){nextCfg.cover.dataUrl=await new Promise((resolve,reject)=>{const reader=new FileReader();reader.onload=()=>resolve(reader.result);reader.onerror=()=>reject(Error('封面读取失败'));reader.readAsDataURL(file);});}
        else {const body=new FormData();body.append('task_id',taskId);body.append('file',file);const result=await api(f.upload||'/api/bgm_upload','POST',body);if(f.type==='bgm')nextCfg.image.bgmPath=result.path;}
      }
      const savedConfig=await api(`/api/task/${encodeURIComponent(taskId)}/config`, "POST", nextCfg);
      if(savedConfig.task_id)taskId=savedConfig.task_id;
      if(replaceProvider)await api(`/api/task-cover/${encodeURIComponent(taskId)}/replace-unknown`, 'POST', {slot:1,provider:replaceProvider,operation_id:replacementOperation,acknowledge_unknown:true});
      if(resumePausedDraft){
        await api(`/api/task/${encodeURIComponent(taskId)}/confirm`, 'POST', {});
        close();location.href='/result.html?task='+encodeURIComponent(taskId);
      }else{
        await resumeTaskFromStep(taskId, stepKey);close();
      }
    } catch (e) {
      alert("保存失败：" + e.message);
    }finally{saving=false;updateSaveControl();}
  };
}
