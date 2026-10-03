# 074 → Codex 交接清单（2026-10-03 晚）

## 项目身份（先确认再动手）

- **唯一项目**：`D:\1Leida-shipinhao\074-copy-rewrite`（不是 `073-private-data` / `071` / `072`，三个产品独立，禁止跨产品读写）
- **产品形态**：074 桌面工作台 = Tauri (NSIS) 打包的 Python + HTML/JS 应用，安装在 `%LOCALAPPDATA%\074 创作工作台\`。**不要把网页调试当桌面发布**——必须 PyInstaller + Tauri 全套出安装包。
- **目标**：对照 Story 1.24.0 拆解包（`.desktop-tools/story-reference/` 只读）的所有开通功能，逐项 1:1 复刻（样式、代码、UI、链接都要）。**还没复刻完，不要宣称"完成"**。

## 必读 memory（位于 `C:\Users\Admin\.claude\projects\D--1Leida-shipinhao\memory\`）

开工前先 Read 下列 4 条，违反任何一条会被用户骂：

1. **`074 desktop priority`** —— 工作台=桌面安装包；不要再打补丁式修网页；每个小阶段做完写交接 doc。
2. **`feedback_074_push_each_fix`** —— 每个 bug 修完即 commit+push；不准推半拉子作品。settings.html grid-column bug 是反面教材。
3. **`feedback_do_not-impact-073`** —— 不要 unzip 大 zip 占 IO / 不要后台启动 server.py / 不要访问 073-private-data。
4. **`feedback_074_github_push`** —— 每完成一批可发布工作就 push；明天开工先 `git status` + `git log --oneline -5` + 跟用户确认 remote。

可选了解（不强求）：
- `storybound-1.24.0-asset-extraction` —— `.desktop-tools/story-reference/index-CXUXw7CE.js` 等是 brotli 解出来的真值
- `story_workflow_reference` / `story_prompt_assistant` / `template_editor_reference` 等 JSON 在 `assets/` 下，都是 Story 拆解出来的真值

## 仓库结构

```
074-copy-rewrite/
├── server.py                # 后端 5299 行，113 个 /api/* 端点，单文件 BaseHTTPRequestHandler
├── prompts/                 # Step 0~3 + hook + podcast 拆分的 Python 模块
│   ├── step0_pre_review.py
│   ├── step1_meta.py
│   ├── step2_split.py       # 分镜，支持 narrator/podcast 两种 script_format
│   ├── step3_image_prompt.py # 出图 prompt
│   ├── podcast_dialogue.py
│   ├── hook.py              # hook 钩子（开场/结尾引导）
│   ├── story/               # 从 Story 拆出来的真值 prompt
│   └── user/                # 用户自定义
├── index.html               # 2789 行，图文任务表单 + 运行页 + 7 节点 workflow
├── settings.html            # 系统设置 8 大块（LLM/Image/TTS/ASR/Draft/AI-creation/About）
├── tasks.html               # 任务列表 + StoryHistory 卡片视图
├── result.html              # 任务结果页 + workflow_view
├── voice-lab.html           # 独立配音实验室（不创建任务）
├── image-lab.html           # 独立画图实验室（4 个 mode）
├── prompt-editor.html       # 提示词模板编辑器
├── template-editor.html     # 剪映草稿模板编辑器
├── workbench.html           # 文案工作台（FILE/EDIT 协议，三栏）
├── library.html             # 素材库（按 idx 上传/选用/删除）
├── assets/
│   ├── app_nav.js/css       # 共享侧栏导航（最近合并到所有页）
│   ├── desktop_bridge.js    # 桌面 Tauri bridge（choosePath/revealPath/openInEditor）
│   ├── story_workflow_reference.json  # 6 套封面 + 13 画风 + 7 赛道 + 构图规则
│   ├── story_history.css/js # tasks.html 用的真值样式
│   ├── image_pipeline.js    # 客户端流水线（runImagePipeline，支持 rerunFrom 步骤失效）
│   ├── workflow_view.js/css # 结果页 wv-* 系列组件
│   ├── workflow_actions.js  # 「从这里重跑」逻辑
│   ├── form_libraries.js    # 表单字段（封面/视角/技能）
│   ├── cover-previews/*.svg # 6 个封面模板的 SVG 预览
│   ├── style-previews/*.webp
│   ├── voice_lab.js/css
│   ├── image_lab.js/css
│   ├── workbench.js/css + workbench_transfer.js
│   ├── prompt_editor.js/css + prompt_templates.json + prompt_templates.provenance.json
│   ├── template_editor.js/css + template_editor_reference.json + draft_templates.json
│   └── library.js/css
├── tests/                   # pytest + node:test，回归测试
│   ├── image_pipeline.test.js    # node --test，34/34 通过
│   ├── test_regression_e2e.py    # 完整链路：素材 + AI 兜底 + 动态 + 配音 + 草稿 + 封面
│   ├── test_image_workflow_http.py # /api/step4_* HTTP 测试
│   ├── test_podcast.py           # 双人播客 [A]/[B] 切分
│   ├── test_intro_video.py       # 动态分镜
│   ├── test_knowledge_workflow.py # IMA 检索
│   ├── test_materials.py         # 素材库上传/分配
│   ├── test_settings_no_activation.py
│   └── test_desktop_backend.py
├── src-tauri/               # Tauri Rust shell（src/main.rs + tauri.conf.json）
├── scripts/build-desktop.ps1 # 一键打包：PyInstaller → Tauri build → NSIS
├── .desktop-tools/          # 仅本机用：python / cargo / rustup / BuildTools / story-reference
└── *.md                     # 历史交接 + 差距清单
```

## 当前 git 状态（2026-10-03 19:xx）

最近 8 个 commit（已 push 到 github.com/xiaoella2025/074-copy-rewrite.git）：

```
a228728 docs 2026-10-03 收尾交接：6 commit 落地 + 桌面包升级
3afebdd docs 更新剩余差距清单
f3b95a7 fix B3.6 增强：失败镜批量重画
2eba23e fix B1.5/B1.6 结果页参数卡片完整复原
5bf654f fix B3.6 单图重生成（运行页 + 结果页都接通）
f50b5c6 fix 封面副字段随模板智能提示：legend 必填、emotional 推荐讲人物钩子
5f3eaf3 fix 从任意步骤重跑 + 分镜图片 viewer + app-nav 全站整合
43ac8ec fix tasks.html active 视图用 StoryHistory + cover-template 自定义面板
```

- **工作树干净**，没有未提交改动
- **桌面已升级**：12:44 打的安装包，12:42 已装到 `%LOCALAPPDATA%\074 创作工作台\`
- 安装包路径：`src-tauri\target\release\bundle\nsis\074 创作工作台_0.1.0_x64-setup.exe`（126.69 MiB）

## 用户当前明确要求

- ✅ "你做完了不要停，按你建议走"
- ⏳ 还在等**真实任务验证**（用户授权前不要主动跑付费生成）：
  - 6 套封面规则对出图的影响（选「人物传奇」必填金句看底部金句）
  - 剪映实际草稿（打开 .drafts 看字幕/媒体/特效）
  - ASR/TTS 真实调用（火山）
  - 单图重画 / 任意步骤重跑流程（不会误用旧产物）
- ✅ 用户明确说 "你先给codex写一个交接清单" —— 就是这份文档

## 本轮（10-03）已修的差距项 ✅

| ID | 改动 | commit |
|----|------|--------|
| A1 | tasks.html 删除按钮 24×24 → 28×28 默认可见 + 边框 + 红边 hover | 82a7e3f |
| A2 | voice-lab.html label 拆「配音引擎」+「音色」两层 | 82a7e3f |
| A3 | 6 套封面规则 panel（3 方向 + titleLayout + subtitleLayout + plainHint 可折叠） | 82a7e3f |
| A4 | legend.svg 预览图 | 82a7e3f |
| B3.2 | cover_direction 选择，build_cover_prompt 支持 | 00f1214 |
| B3.4 | Canvas API 中心裁切上传封面 | 0bd749f |
| B3.3 | cover-subtitle 模板智能提示（legend 必填金句等） | f50b5c6 |
| B3.6 | 单图重生成（运行页 + 结果页） | 5bf654f / f3b95a7 |
| B1.5 | 结果页「创建参数」卡片（处理模式/暂停/改写强度/视角/赛道/层级/配音） | 2eba23e |
| B1.6 | 结果页「发布素材」卡片（封面模板/方向/图片来源/出图引擎/动态分镜/BGM/发布渠道） | 2eba23e |
| B1.3 | 任意步骤重跑 + 分镜图片 viewer overlay | 5f3eaf3 |
| B7.5 | 重画不会误用旧产物（rerunFrom 步骤失效 + 单图存到 task_dir/covers） | 5f3eaf3 / f3b95a7 |

## **未做** 的剩余差距（按优先级）

### 高优先级（影响主链路质量）
- **B2.1** `step2_split` 完整移植 X4/aS/rS/iS 校验与重试（`prompts/step2_split.py`）—— 当前还串行
- **B2.2** 提示词批次并发调度（原版并发，当前 image_lab 还是单条串行）
- **B2.3** 元信息异常回退摘要（避免失败被误报完成）

### 中优先级
- **B1.1** 任务分组位置（按日期/状态分组 vs 当前平铺）—— `tasks.html`
- **B1.2** 字体/间距像素对齐 STORY 真值
- **B1.4** 结果页「原文对比」并排显示改写前后
- **B3.1** 多张参考图（原版支持多张、当前 image-lab 仅 1 张）
- **B3.5** 封面多版本对比/切换
- **B4.*** 文案工作台多会话 + 技能下拉 + 引用面板 + 版本浏览（`workbench.html` + `assets/workbench.js`）
- **B5.*** 提示词助手取消请求 + 紧凑布局 + 失败提示（`prompt-editor.html` + `prompts/`）
- **B6.*** 素材库完整分类/标签（`library.html` + `assets/library.js`）

### 低优先级
- **B8.1~B8.4** 选品 / 对标 / 市场 / 账号入口（新业务，需新设计）
- 视频 MV / 音乐 MV 工作流接入（仅占位）

### 必须由用户完成
- **B7.1~B7.4** 跑付费生成 / 剪映实际草稿 / ASR / TTS 真实调用 —— 不能自动跑

完整状态见 `REMAINING_GAPS_20261003.md`。

## 启动/测试/构建命令

### JS 单元测试（不需要 LLM 凭据）
```bash
node tests/image_pipeline.test.js   # 34/34 通过
```

### Python 单元测试（mock 所有外部 API）
```bash
python -m pytest tests/ -x
```

### 启动开发服务器（**别在后台跑**，会占端口和 IO；只在用户验收时临时启动）
```bash
# 不推荐启动！手动验收模式
python server.py
```

### 构建桌面安装包（完整流程 ~3 分钟）
```bash
powershell -NoProfile -ExecutionPolicy Bypass -File scripts/build-desktop.ps1
# 或：npm run desktop:build
# 产物：src-tauri/target/release/bundle/nsis/074 创作工作台_0.1.0_x64-setup.exe
```

### 静默安装到桌面（修改已安装软件，需用户授权）
```bash
powershell -NoProfile -ExecutionPolicy Bypass -Command "& '<setup.exe 路径>' /S"
```

### 关键路径
- 任务产物：`%LOCALAPPDATA%\074 创作工作台\data\tasks\<task_id>\`
- 设置：`%LOCALAPPDATA%\074 创作工作台\data\settings.json`
- 配音实验室输出：`%LOCALAPPDATA%\074 创作工作台\data\voice-lab\`
- 画图实验室输出：`%LOCALAPPDATA%\074 创作工作台\data\image-lab\`

## 关键代码约定（避免踩坑）

1. **`runImagePipeline` 客户端入口** (`assets/image_pipeline.js`)：单一入口，支持 `rerunFrom` 参数（步骤失效语义），必须先按 step key 失效 prior 字段再调对应接口。增加新 step 时务必同步 7 处：`invalidate` 表 + `call('prompts'|'images'|'draft', ...)` 三个 if-else + `onStage` 监听。
2. **`/api/generate` 行为**：根据 `run_steps` 决定跑哪些 sub-step；调用方需保证 `run_steps` 顺序合法。
3. **result.html / index.html 共享**：都用 `assets/workflow_view.js` 渲染 workflow；新增节点请同步两边 mount。
4. **CSS 主题**：共享色板在 `assets/story_theme.css`（emerald + oklch + --brand-hue 168）；新增颜色先用 `--brand` / `--accent` / `--text-muted` 别自创。
5. **app-nav.js 是单一侧栏入口** —— 新页面不要再写自己的 brand 区，复用 `aside#app-nav` + `<script src="/assets/app_nav.js">`。
6. **JS 风格**：单文件单 IIFE / 一行多语句 / `const $=id=>document.getElementById(id)` 是 074 默认风格，不要引入 React/Vue/jQuery。
7. **服务端口**：Tauri 启动时 Python backend 监听 `127.0.0.1:0`（随机端口），通过 `desktop_bridge.js` 转给 Tauri webview。**不要硬编码端口**。
8. **每次改完即 commit+push**：本地保留只是半拉子。

## 已知坑 / 调试技巧

- **PyInstaller COLLECT 阶段慢**（~30s）但实际编译快；不要中断 build 否则下次需要重新 COLLECT。
- **Tauri 增量编译**只看改动的 .rs；改 src-tauri/Cargo.toml 会触发全量重编（~2 分钟）。
- **`tests/image_pipeline.test.js` 找不到 require**：确认在项目根目录跑，里面 `require('../assets/image_pipeline.js')` 是相对路径。
- **`assets/story_workflow_reference.json` 是真值**：6 套封面的 compositionRule / titleLayout / subtitleLayout / plainHint / directions 全在这；改封面逻辑前先 grep 这文件。
- **`step2_split.py` 的 `match_rate`**：锚点匹配率，前两镜上下文靠这个；不要删，渲染侧（`#step2-note` 的 chip）会读。
- **用户的 LLM 凭据**：在 `settings.html → LLM`，profile_id 走 `assets/profiles.json`；后端 `resolve_active_llm_settings` 切换；前端 `$("model-pick")` 是 select。

## 上手顺序建议

1. `git status && git log --oneline -10` 确认仓库干净
2. Read 这份文档 + `REMAINING_GAPS_20261003.md` + `VSCODE_HANDOFF_20261003.md`
3. 跑一次 `node tests/image_pipeline.test.js` 确认基线绿
4. 跟用户确认下一阶段优先级（建议先 B2.* 或 B4.*）
5. 改 → JS 语法 check (`node --check <file>`) → 跑测试 → commit → push → build 桌面（每 3~5 个 commit 一次）

## 紧急联系人

- 用户本人：会在 `claude-code` 终端发指令，按指示走；不要"自主"决定改架构。
- 074-073-072-071 都是独立产品，跨产品问题问用户，**别自己跨产品取数据**。
