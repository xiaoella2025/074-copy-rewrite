(function (root) {
  const NODES = [
    {key: "0", label: "文案预审", description: "清理广告与敏感词"},
    {key: "1", label: "智能改写与封面", description: "正文、标题与发布文案"},
    {key: "2", label: "影视分镜分句", description: "拆成可配图的单元"},
    {key: "5", label: "TTS 配音", description: "逐镜生成或切分音频"},
    {key: "3", label: "生成绘图提示词", description: "为每个分镜写画面描述"},
    {key: "4", label: "批量生图", description: "生成或匹配镜头图片"},
    {key: "6", label: "生成剪映草稿", description: "打包素材与字幕"},
  ];
  const STAGE_KEYS = {generate: ["0", "1", "2"], tts: ["5"], prompts: ["3"],
    images: ["4"], videos: ["4"], draft: ["6"], cover: ["6"]};
  const TAB_NAMES = {preview: "▤ 产物预览", audio: "♫ 配音试听", gallery: "▧ 分镜画廊", captions: "☷ 字幕断行"};

  function node(tag, className, value) {
    const item = document.createElement(tag);
    if (className) item.className = className;
    if (value !== undefined && value !== null) item.textContent = String(value);
    return item;
  }
  function append(parent, ...children) { parent.append(...children); return parent; }
  function card(parent, title) {
    const box = node("section", "wv-card wv-preview-card");
    box.append(node("div", "wv-card-title", title));
    parent.append(box);
    return box;
  }
  function field(parent, title, value, wide = false) {
    const box = node("div", "wv-field" + (wide ? " wide" : ""));
    const head=node("div","wv-field-head"),copy=node("button","wv-field-copy","复制");copy.type="button";
    copy.onclick=async()=>{try{await navigator.clipboard.writeText(String(value??""));copy.textContent="已复制";}catch(e){alert(e.message);}};
    append(head,node("label","",title),copy);
    append(box,head,node("div", "wv-field-value", value ?? ""));
    parent.append(box);
  }
  function numbered(value) {
    return Array.isArray(value) ? value.map((part, index) => `${index + 1}. ${typeof part === "string" ? part : JSON.stringify(part)}`).join("\n") : String(value || "");
  }
  function empty(parent, text) { parent.append(node("div", "wv-empty", text)); }

  function mount(container, options) {
    const handlers = {
      onRetry: (options && options.onRetry) || null,
      onEditStep: (options && options.onEditStep) || null,
      onTaskUpdated: (options && options.onTaskUpdated) || null,
      onRedraw: (options && options.onRedraw) || null,
    };
    container.classList.add("wv");
    const left = node("div", "wv-left"), right = node("div", "wv-right");
    const summary = node("section", "wv-card wv-summary");
    const timelineCard = node("section", "wv-card");
    const timeline = node("div", "wv-timeline");
    append(timelineCard, node("div", "wv-timeline-head", "7 步流水线"), timeline);
    append(left, summary, timelineCard);
    const tabs = node("nav", "wv-tabs");
    tabs.setAttribute("aria-label", "任务产物");
    const panels = {};
    Object.entries(TAB_NAMES).forEach(([key, name]) => {
      const tab = node("button", "wv-tab", name);
      tab.type = "button";
      tab.dataset.tab = key;
      tabs.append(tab);
      const panel = node("div", "wv-panel");
      panel.dataset.panel = key;
      panels[key] = panel;
      right.append(panel);
    });
    right.prepend(tabs);
    append(container, left, right);

    let detail = null, taskId = "", activeTab = "preview", notice = "任务正在运行，已完成的产物会显示在这里。";
    const overrides = new Map(), started = new Map();
    const selectTab = key => {
      activeTab = key;
      tabs.querySelectorAll(".wv-tab").forEach(tab => {
        const chosen = tab.dataset.tab === key;
        tab.classList.toggle("active", chosen);
        tab.setAttribute("aria-selected", chosen ? "true" : "false");
      });
      Object.entries(panels).forEach(([name, panel]) => panel.hidden = name !== key);
    };
    tabs.addEventListener("click", event => {
      const tab = event.target.closest(".wv-tab");
      if (tab) selectTab(tab.dataset.tab);
    });
    selectTab("preview");

    // Story Task Bi viewer: same-page overlay, scene caption, arrows and Escape.
    function openViewer(items,startIndex) {
      let current=startIndex;
      const overlay=node('div','wv-viewer');overlay.setAttribute('role','dialog');overlay.setAttribute('aria-modal','true');overlay.setAttribute('aria-label','分镜图片预览');
      const close=node('button','wv-viewer-close','×'),previous=node('button','wv-viewer-prev','‹'),next=node('button','wv-viewer-next','›');
      close.setAttribute('aria-label','关闭图片预览');previous.setAttribute('aria-label','上一张');next.setAttribute('aria-label','下一张');
      const count=node('div','wv-viewer-count'),img=node('img','wv-viewer-image'),caption=node('div','wv-viewer-caption');
      const render=()=>{const item=items[current],idx=Number(item.name?.split('.')[0]||current+1);img.src=item.url;img.alt='#'+idx;count.textContent=`#${idx} · ${current+1}/${items.length}`;caption.textContent=detail?.steps?.shots?.find(s=>Number(s.idx)===idx)?.text||'';previous.disabled=current===0;next.disabled=current===items.length-1;};
      const key=e=>{if(e.key==='Escape')finish();if(e.key==='ArrowLeft'&&current>0){current--;render();}if(e.key==='ArrowRight'&&current<items.length-1){current++;render();}};
      const finish=()=>{window.removeEventListener('keydown',key);overlay.remove();};
      overlay.onclick=finish;img.onclick=caption.onclick=e=>e.stopPropagation();close.onclick=finish;
      previous.onclick=e=>{e.stopPropagation();if(current>0){current--;render();}};next.onclick=e=>{e.stopPropagation();if(current<items.length-1){current++;render();}};
      append(overlay,close,count,previous,img,caption,next);document.body.append(overlay);window.addEventListener('keydown',key);render();close.focus();
    }

    function renderSummary() {
      const info = detail?.info || {};
      const steps = detail?.steps || {};
      const completed = info.completed_steps || [];
      summary.replaceChildren();
      summary.append(node("div", "wv-summary-id", taskId || info.task_id || "生成中 · 等待任务编号"));
      summary.append(node("div", "wv-summary-title", info.title || steps.meta?.title || "图文任务"));
      summary.append(node("div", "wv-summary-id", info.created_at || ""));
      const stats = node("div", "wv-stats");
      [[info.elapsed_sec!=null ? `${Math.floor(Math.round(info.elapsed_sec)/60)}:${String(Math.round(info.elapsed_sec)%60).padStart(2,'0')}` : "—", "总耗时"],
        [`${NODES.filter(item => completed.map(String).includes(item.key)).length}/7`, "当前步骤"], [info.shot_count ?? steps.shots?.length ?? 0, "分镜数"]]
        .forEach(([value, label]) => {
          const stat = node("div", "wv-stat");
          append(stat, node("strong", "", value), node("small", "", label));
          stats.append(stat);
        });
      summary.append(stats);
    }

    function renderTimeline() {
      const info = detail?.info || {};
      const completed = new Set((info.completed_steps || []).map(String));
      timeline.replaceChildren();
      NODES.forEach((item, index) => {
        const over = overrides.get(item.key);
        const persisted=info.stage_timings?.[item.key];
        const status = over?.status || (info.progress?.step===item.key&&['running','failed'].includes(info.progress.status)?info.progress.status:completed.has(item.key) ? "done" :
          item.key === "0" && completed.has("1") ? "skipped" : "pending");
        const row = node("div", "wv-node " + status);
        row.dataset.step = item.key;
        const mark = status === "done" ? "✓" : status === "failed" ? "!" : status === "skipped" ? "–" : String(index + 1);
        const text = node("div");
        append(text, node("div", "wv-node-title", item.label),
          node("div", "wv-node-note", over?.note || (status === "skipped" ? "已跳过" : status === "done" ? `已完成${persisted?.elapsed_sec!=null?' · '+persisted.elapsed_sec+'s':''}` : status==='running'?'运行中…':status==='failed'?'此步骤失败':item.description)));
        const retry = node("button", "wv-node-retry", "↻ 从这里重跑");
        retry.type = "button";
        retry.title = `从「${item.label}」继续执行后续步骤（沿用上次参数）`;
        retry.onclick = event => {
          event.stopPropagation();
          const id = taskId || info.task_id;
          if (!id) return;
          if (handlers.onRetry) handlers.onRetry(item.key, id);
          else location.href = "/result.html?task=" + encodeURIComponent(id) + "&resume=" + encodeURIComponent(item.key);
        };
        const edit = node("button", "wv-node-edit", "✎ 改参数");
        edit.type = "button";
        edit.title = `只编辑「${item.label}」这一步骤的参数`;
        edit.onclick = event => {
          event.stopPropagation();
          const id = taskId || info.task_id;
          if (!id) return;
          if (handlers.onEditStep) handlers.onEditStep(item.key, id);
        };
        const actions = node("div", "wv-node-actions");
        append(actions, retry, edit);
        append(row, node("span", "wv-dot", mark), text, actions);
        timeline.append(row);
      });
    }

    function renderPreview() {
      const panel = panels.preview, steps = detail?.steps || {};
      panel.replaceChildren();
      if (steps.review) {
        const box = card(panel, "文案预审");
        const review = steps.review;
        if (review.reviewed_text) box.append(node("div", "wv-text", review.reviewed_text));
        else if (review.suggestion) box.append(node("div", "wv-text", review.suggestion));
        else box.append(node("div", "wv-text", review.passed ? "已通过预审" : "预审记录已保存"));
      }
      if (steps.rewrite) {
        const box = card(panel, "改写产物");
        box.append(node("div", "wv-text", steps.rewrite));
      }
      if (steps.meta) {
        const box = card(panel, "封面与发布文案"), fields = node("div", "wv-fields"), meta = steps.meta;
        field(fields, "封面主标题", meta.title);
        field(fields, "副标题", numbered(meta.subtitle), true);
        field(fields, "短标题（≤16字）", meta.short_title);
        field(fields, "发布文案", meta.summary, true);
        field(fields, "话题标签", numbered(meta.tags), true);
        field(fields, "种子评论", numbered(meta.comments), true);
        field(fields, "封面构图方向", numbered(meta.cover_image_prompts), true);
        box.append(fields);
      }
      if (steps.shots?.length) {
        const box = card(panel, `分镜与画面提示词 · ${steps.shots.length} 镜`);
        const prompts = new Map((steps.prompts || []).map(item => [Number(item.idx), item]));
        steps.shots.forEach((shot, index) => {
          const row = node("div", "wv-shot"), head = node("div", "wv-shot-head");
          append(head, node("span", "wv-shot-no", String(shot.idx ?? index + 1).padStart(2, "0")), node("span", "", shot.text || ""));
          row.append(head);
          const picture = (steps.images || []).find(x => Number(x.name?.split('.')[0]) === Number(shot.idx ?? index + 1));
          if (picture) {
            const img = node("img", "wv-preview-image");
            img.src = picture.url; img.alt = `第 ${index + 1} 镜`; img.loading = "lazy";
            const link = node("a"); link.href = picture.url; link.target = "_blank"; link.append(img);
            link.onclick=e=>{e.preventDefault();e.stopPropagation();openViewer(steps.images,steps.images.indexOf(picture));};
            row.prepend(link);
          }
          const promptItem = prompts.get(Number(shot.idx));
          if (picture && promptItem && handlers.onRedraw) {
            const shotIdx = Number(shot.idx ?? index + 1);
            const redrawWrap = node("div", "wv-shot-actions");
            const redrawBtn = node("button", "wv-shot-redraw", "↻ 重画");
            redrawBtn.type = "button";
            redrawBtn.title = "用同 prompt 重新生成该镜图片";
            redrawBtn.onclick = async (e) => {
              e.stopPropagation();
              redrawBtn.disabled = true;
              const old = redrawBtn.textContent;
              redrawBtn.textContent = "⏳ 重画中…";
              try {
                const newImg = await handlers.onRedraw(shotIdx, promptItem.desc_prompt, picture);
                if (newImg) {
                  img.src = newImg + "?t=" + Date.now();
                  picture.url = newImg;
                  redrawBtn.textContent = "✓ 已重画";
                } else {
                  throw new Error("重画返回为空");
                }
              } catch (err) {
                alert("重画失败：" + err.message);
                redrawBtn.textContent = old;
              } finally {
                setTimeout(() => { redrawBtn.disabled = false; redrawBtn.textContent = old; }, 1500);
              }
            };
            redrawWrap.append(redrawBtn);
            row.append(redrawWrap);
          }
          const prompt = prompts.get(Number(shot.idx));
          if (prompt) {
            row.append(node("div", "wv-prompt", "→ " + prompt.desc_prompt));
            if(prompt.diagnostic?.fellBackToSkeleton)row.append(node('div','wv-prompt-warning','AI 提示词未通过校验，当前使用赛道兜底画面；可从绘图提示词步骤重跑。'));
          }
          box.append(row);
        });
      }
      if (steps.draft?.draft_dir) {
        const d = steps.draft;
        const box = node("div", "wv-draft");
        append(box, node("div", "wv-draft-title", "✓ 剪映草稿已生成"));
        const folderName = String(d.draft_dir).split(/[\\/]/).pop();
        const pathWrap = node("div", "wv-draft-path-wrap");
        const pathSpan = node("span", "wv-draft-path", folderName);
        const copyBtn = node("button", "wv-draft-path-copy", "复制");
        copyBtn.type = "button";
        copyBtn.title = "复制草稿路径";
        copyBtn.onclick = () => navigator.clipboard.writeText(d.draft_dir).catch(err => alert(err.message));
        append(pathWrap, pathSpan, copyBtn);
        box.append(pathWrap);
        const actions = node("div", "wv-draft-actions");
        const templateSelect = node("select", "wv-draft-select");templateSelect.setAttribute("aria-label","草稿模板");
        const currentTemplate=d.template_snapshot||detail?.client_config?.image?.templateSnapshot;
        templateSelect.append(new Option(currentTemplate?.name||"当前草稿模板", d.template_id||currentTemplate?.id||""));
        const bgmSelect=node("select","wv-draft-select");bgmSelect.setAttribute("aria-label","背景音乐");
        bgmSelect.append(new Option(d.bgm_path?"🎵 "+String(d.bgm_path).split(/[\\/]/).pop():"无背景音乐",d.bgm_path||""));
        let availableTemplates=[];
        Promise.all([fetch('/api/templates/drafts').then(r=>r.json()),fetch('/api/settings').then(r=>r.json())]).then(([library,settings])=>{
          if(!templateSelect.isConnected)return;
          availableTemplates=library.templates||[];
          for(const t of availableTemplates)if(![...templateSelect.options].some(o=>o.value===t.id))templateSelect.append(new Option(t.name,t.id));
          if(![...bgmSelect.options].some(o=>o.value===''))bgmSelect.append(new Option('无背景音乐',''));
          const bgm=settings.jianying?.bgm_path;
          if(bgm&&![...bgmSelect.options].some(o=>o.value===bgm))bgmSelect.append(new Option('🎵 内置 BGM',bgm));
        }).catch(()=>{});
        append(actions,templateSelect,bgmSelect);
        const repack = node("button", "wv-draft-repack", "重新打包");
        repack.type = "button";
        repack.title = "按当前断行重新打包剪映草稿（不重配音、不重出图）";
        repack.onclick = async () => {
          repack.disabled = true; repack.textContent = "打包中…";
          try {
            const selected=availableTemplates.find(t=>t.id===templateSelect.value);
            await postTask("repack", {bgm_path:bgmSelect.value,
              ...(selected?{template_id:selected.id,template_snapshot:selected}:{})});
            if (handlers.onTaskUpdated) await handlers.onTaskUpdated();
          } catch (err) { alert(err.message); }
          finally { repack.disabled = false; repack.textContent = "重新打包"; }
        };
        const open = node("button", "wv-draft-open-jianying", "在剪映打开");
        open.type = "button";
        open.title = "在剪映中打开该草稿；未检测到剪映则打开草稿目录";
        open.onclick = async () => {
          const originalText = open.textContent;
          open.disabled = true; open.textContent = "打开中…";
          try {
            const res = await fetch("/api/open_jianying", {method:"POST",headers:{"Content-Type":"application/json"},body:JSON.stringify({task_id:taskId, draft_dir:d.draft_dir})});
            const value = await res.json();
            if (!res.ok) throw new Error(value.error || `HTTP ${res.status}`);
          } catch (err) { alert(err.message); }
          finally { open.disabled = false; open.textContent = originalText; }
        };
        append(actions, repack, open);
        box.append(actions);
        panel.append(box);
      }
      if (!panel.children.length) empty(panel, notice);
    }

    function renderAudio() {
      const panel = panels.audio, audios = detail?.steps?.audios || [];
      panel.replaceChildren();
      if (!audios.length) return empty(panel, "配音尚未完成。");
      const box = card(panel, `配音试听 · ${audios.length} 段`);
      audios.forEach((item, index) => {
        const row = node("div", "wv-audio-row"), audio = node("audio");
        audio.controls = true;
        audio.preload = "none";
        audio.src = item.url;
        append(row, node("span", "wv-shot-no", index + 1), audio);
        box.append(row);
      });
    }

    function renderGallery() {
      const panel = panels.gallery, images = detail?.steps?.images || [];
      panel.replaceChildren();
      if (!images.length) return empty(panel, "分镜图片尚未完成。");
      const box = card(panel, `分镜画廊 · ${images.length} 张`), grid = node("div", "wv-gallery");
      images.forEach((item,index) => {
        const link = node("a"), img = node("img");
        link.href = item.url;
        link.target = "_blank";
        link.rel = "noopener";
        link.onclick=e=>{e.preventDefault();e.stopPropagation();openViewer(images,index);};
        img.src = item.url;
        img.alt = item.name || "分镜图片";
        img.loading = "lazy";
        append(link, img, node("small", "", item.name || ""));
        grid.append(link);
      });
      box.append(grid);
    }

    async function postTask(action, body) {
      const res = await fetch(`/api/task/${encodeURIComponent(taskId)}/${action}`, {method:"POST",headers:{"Content-Type":"application/json"},body:JSON.stringify(body)});
      const value = await res.json(); if (!res.ok) throw new Error(value.error || "操作失败"); return value;
    }
    async function refreshDetail() {
      const res = await fetch(`/api/task/${encodeURIComponent(taskId)}`);
      if (!res.ok) throw new Error("无法刷新任务");
      detail = await res.json(); render();
    }
    function renderCaptions() {
      const panel = panels.captions, items = detail?.steps?.captions?.items || [];
      panel.replaceChildren();
      if (!items.length) return empty(panel, "配音完成后显示字幕断行。");
      const box = card(panel, `字幕断行 · ${items.reduce((n,x) => n+x.lines.length,0)} 条短字幕`);
      const controls = node("div", "wv-draft-actions"), editors = [];
      const save = node("button", "", "保存断行");
      const pack = node("button", "", "保存并重新打包");
      const estimated=items.some(part=>(part.cues||[]).some(cue=>cue.timing_source==='estimated'));
      const hint = node("small", "", `每行一条字幕，最多 ${detail?.steps?.captions?.max_chars||12} 字；${estimated?'包含按配音时长估算的时间点':'使用已保存的识别时间轴'}。可调整换行，保留原文。` );
      const submit = async rebuild => {
        save.disabled = pack.disabled = true;
        try {
          await postTask("captions", {items:editors.map(x => ({id:x.id,lines:x.input.value.split(/\r?\n/).map(s=>s.trim()).filter(Boolean)}))});
          if (rebuild) await postTask("repack", {});
          await refreshDetail(); selectTab("captions");
        } catch (e) { alert(e.message); }
        finally { save.disabled = pack.disabled = false; }
      };
      save.onclick = () => submit(false); pack.onclick = () => submit(true);
      append(controls, save, pack, hint); box.append(controls);
      let offset = 0;
      items.forEach((part,index) => {
        const row = node("div", "wv-caption-row");
        row.append(node("strong", "", `第 ${part.id} 镜 · ${part.lines.length} 条`));
        const input = node("textarea", "wv-caption-editor"); input.value = part.lines.join("\n"); input.rows = Math.min(12,Math.max(3,part.lines.length));
        input.setAttribute("aria-label", `第 ${part.id} 镜字幕断行`); editors.push({id:part.id,input});
        const timings = node("div", "wv-caption-timings");
        (part.cues || []).forEach(cue => {
          const line = node("div", "wv-caption-cue");
          const ts = node("span", "wv-caption-time", `${(offset + cue.start).toFixed(2)}–${(offset + cue.end).toFixed(2)}s`);
          const text = node("span", "wv-caption-text", cue.text);
          if (cue.timing_source === "estimated") text.dataset.estimated = "1";
          append(line, ts, text);
          timings.append(line);
        });
        append(row, input, timings); box.append(row);
        offset += Number(detail?.steps?.segments?.find(s=>Number(s.index??s.idx)===Number(part.id))?.duration || 0);
      });
    }

    function render() {
      renderSummary();
      renderTimeline();
      renderPreview();
      renderAudio();
      renderGallery();
      renderCaptions();
      selectTab(activeTab);
    }

    render();
    return {
      renderTask(value) {
        detail = value;
        taskId = value?.info?.task_id || taskId;
        render();
      },
      setTaskId(value) { taskId = value || ""; renderSummary(); },
      setNotice(value) { notice = value || ""; renderPreview(); },
      setStage(stage, status, note = "") {
        const generateKeys = ["0", "1", "2"];
        const keys = stage === "generate" && status === "running" ? ["0"] :
          stage === "generate" && status === "failed" ? [generateKeys.find(key => overrides.get(key)?.status !== "done") || "2"] :
          STAGE_KEYS[stage] || [];
        if (status === "running") started.set(stage, Date.now());
        const duration = started.has(stage) ? Math.max(0, Math.round((Date.now() - started.get(stage)) / 1000)) : null;
        const message = note || (status === "running" ? "运行中…" : status === "paused" ? "等待确认" :
          status === "failed" ? "此步骤失败" : status === "done" && duration != null ? `已完成 · ${duration}s` : "已完成");
        keys.forEach(key => overrides.set(key, {status, note: message}));
        renderTimeline();
      },
      setStep(step, status, note = "") {
        const key = step === "meta" ? "1" : String(step);
        if (NODES.some(item => item.key === key)) {
          overrides.set(key, {status, note: note || (status === "running" ? "运行中…" : status === "failed" ? "此步骤失败" : "已完成")});
          renderTimeline();
        }
      },
      selectTab,
      getTaskId() { return taskId; },
      beginRerun(step) {const first=NODES.findIndex(n=>n.key===String(step));NODES.slice(first).forEach(n=>overrides.delete(n.key));},
    };
  }

  root.WorkflowView = {mount, NODES};
  if (typeof module !== "undefined" && module.exports) module.exports = {NODES};
})(typeof window !== "undefined" ? window : globalThis);
