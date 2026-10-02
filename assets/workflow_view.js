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
    append(box, node("label", "", title), node("div", "wv-field-value", value ?? ""));
    parent.append(box);
  }
  function numbered(value) {
    return Array.isArray(value) ? value.map((part, index) => `${index + 1}. ${typeof part === "string" ? part : JSON.stringify(part)}`).join("\n") : String(value || "");
  }
  function empty(parent, text) { parent.append(node("div", "wv-empty", text)); }

  function mount(container) {
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

    function renderSummary() {
      const info = detail?.info || {};
      const steps = detail?.steps || {};
      const completed = info.completed_steps || [];
      summary.replaceChildren();
      summary.append(node("div", "wv-summary-id", taskId || info.task_id || "生成中 · 等待任务编号"));
      summary.append(node("div", "wv-summary-title", info.title || steps.meta?.title || "图文任务"));
      summary.append(node("div", "wv-summary-id", info.created_at || ""));
      const stats = node("div", "wv-stats");
      [[info.total_duration_sec ? `${Math.round(info.total_duration_sec)}s` : "—", "总时长"],
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
        const status = over?.status || (completed.has(item.key) ? "done" :
          item.key === "0" && completed.has("1") ? "skipped" : "pending");
        const row = node("div", "wv-node " + status);
        row.dataset.step = item.key;
        const mark = status === "done" ? "✓" : status === "failed" ? "!" : status === "skipped" ? "–" : String(index + 1);
        const text = node("div");
        append(text, node("div", "wv-node-title", item.label),
          node("div", "wv-node-note", over?.note || (status === "skipped" ? "已跳过" : status === "done" ? "已完成" : item.description)));
        const retry = node("button", "wv-node-retry", "↻ 从这里重跑");
        retry.type = "button";
        retry.title = `从「${item.label}」重新执行后续步骤`;
        retry.onclick = event => {
          event.stopPropagation();
          const id = taskId || info.task_id;
          if (!id) return;
          location.href = "/index.html?resume=" + encodeURIComponent(id) + "&from=" + encodeURIComponent(item.key);
        };
        append(row, node("span", "wv-dot", mark), text, retry);
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
        field(fields, "短标题", meta.short_title);
        field(fields, "发布文案", meta.summary, true);
        field(fields, "话题标签", numbered(meta.tags), true);
        field(fields, "种子评论", numbered(meta.comments), true);
        field(fields, "封面构图方向", numbered(meta.cover_image_prompts), true);
        box.append(fields);
      }
      if (steps.shots?.length) {
        const box = card(panel, `分镜与画面提示词 · ${steps.shots.length} 镜`);
        const prompts = new Map((steps.prompts || []).map(item => [Number(item.idx), item.desc_prompt]));
        steps.shots.forEach((shot, index) => {
          const row = node("div", "wv-shot"), head = node("div", "wv-shot-head");
          append(head, node("span", "wv-shot-no", String(shot.idx ?? index + 1).padStart(2, "0")), node("span", "", shot.text || ""));
          row.append(head);
          const prompt = prompts.get(Number(shot.idx));
          if (prompt) row.append(node("div", "wv-prompt", "→ " + prompt));
          box.append(row);
        });
      }
      if (steps.draft?.draft_dir) {
        const box = node("div", "wv-draft");
        append(box, node("strong", "", "✓ 剪映草稿已生成"), node("small", "", steps.draft.draft_dir));
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
      images.forEach(item => {
        const link = node("a"), img = node("img");
        link.href = item.url;
        link.target = "_blank";
        link.rel = "noopener";
        img.src = item.url;
        img.alt = item.name || "分镜图片";
        img.loading = "lazy";
        append(link, img, node("small", "", item.name || ""));
        grid.append(link);
      });
      box.append(grid);
    }

    function renderCaptions() {
      const panel = panels.captions, segments = detail?.steps?.segments || [];
      panel.replaceChildren();
      if (!segments.length) return empty(panel, "尚无逐句时间轴；配音完成后会显示可用的字幕文本。");
      const box = card(panel, `字幕文本与时间轴 · ${segments.length} 段`);
      segments.forEach((part, index) => {
        const row = node("div", "wv-shot"), head = node("div", "wv-shot-head");
        append(head, node("span", "wv-shot-no", index + 1), node("span", "", part.text || ""));
        row.append(head);
        if (part.duration != null) row.append(node("div", "wv-prompt", `时长 ${Number(part.duration).toFixed(1)} 秒`));
        box.append(row);
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
    };
  }

  root.WorkflowView = {mount, NODES};
  if (typeof module !== "undefined" && module.exports) module.exports = {NODES};
})(typeof window !== "undefined" ? window : globalThis);
