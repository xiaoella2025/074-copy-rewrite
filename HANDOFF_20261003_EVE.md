# 074 桌面工作台 · 2026-10-03 收尾交接

今天（10-03）从昨天 Stage 10 收尾后，继续按用户"必须细致一比一比对"指示推进。

## 1. 用户截图痛点（commit 82a7e3f 等，已落）

- tasks.html 删除按钮 24×24 → 28×28 默认可见 + 边框 + 阴影 + 红边 hover
- voice-lab.html label 拆成「配音引擎」+「音色」两层
- index.html 加 cover-template-rules panel（3 方向 + titleLayout + subtitleLayout + plainHint 可折叠）
- 新建 legend.svg（深底金字 + 黑白人像左字右人）作为封面模板预览
- index.html 加 cropToRatio()（Canvas API 按 cover-ratio 中心裁切上传封面）
- build_cover_prompt 加 cover_direction 参数支持 3 方向选择
- tasks.html 卡片紧凑化对齐 STORY queue-row（图标分隔 meta + 进度条代替 7 个 pill）
- tasks.html 默认视图改 'all'，filter = active 时复用 StoryHistory.render
- sidebar 加「进行中」入口（/tasks.html?filter=active）
- voice-lab 加「⚙ 添加自定义音色」按钮（跳 /settings.html#tts-section）
- chip active 视觉强化（brand 色背景 + 阴影）

## 2. 本轮新 commit（2026-10-03）

```
3afebdd docs 更新剩余差距清单
f3b95a7 fix B3.6 增强：失败镜批量重画
2eba23e fix B1.5/B1.6 结果页参数卡片完整复原
5bf654f fix B3.6 单图重生成（运行页 + 结果页都接通）
f50b5c6 fix 封面副字段随模板智能提示
5f3eaf3 fix 从任意步骤重跑 + 分镜图片 viewer + app-nav 全站整合
```

每条都已 commit + push 到 https://github.com/xiaoella2025/074-copy-rewrite.git

## 3. 桌面安装包

- 路径：`src-tauri\target\release\bundle\nsis\074 创作工作台_0.1.0_x64-setup.exe`
- 大小：126.69 MiB
- 已在 `%LOCALAPPDATA%\074 创作工作台\` 静默升级安装完成
- 时间：12:44 打包，12:42 落地（安装器自带 assets 在 COLLECT 阶段重打）

## 4. 本轮修复的剩余差距

| 编号 | 内容 | 改动 | commit |
|------|------|------|--------|
| B1.3 | 结果页单镜/全局重生成 | 运行页 ↻ 重画 + ✎ 改 prompt + ↗ 大图 + ↻ 重画全部失败镜(N)；结果页 wv-shot-redraw | f3b95a7 / 5bf654f |
| B1.5 | 创建参数卡片完整复原 | workflow_view renderPreview 加「创建参数」卡（处理模式 / 暂停时机 / 改写强度 / 赛道 / 层级 / 视角 / 配音模式 / 配音引擎） | 2eba23e |
| B1.6 | 发布素材卡片完整复原 | workflow_view renderPreview 加「发布素材」卡（封面模式 / 模板 / 构图方向 / 图片来源 / 出图引擎 / 画幅 / 动态分镜 / BGM / 发布渠道） | 2eba23e |
| B3.3 | 金句字段接入 | index.html 加 updateCoverSubtitleHint(tplKey)，按模板给「💡」提示：legend 必填金句、emotional 推荐钩子、impact 推荐冲击短句、chinese 推荐对仗短句 | f50b5c6 |
| B3.6 | 单图重生成 | 见 B1.3 | f3b95a7 / 5bf654f |
| B7.5 | 重画流程验证（不会误用旧产物） | image_pipeline.js rerunFrom 步骤失效语义；workflow_view.js viewer overlay；单图重画保存到 task_dir/covers/<idx>.png | 5f3eaf3 / f3b95a7 |

## 5. 用户需要做的（不能由 code/codex 自动验证）

- B7.1 跑付费生成：验证 6 套封面规则真的影响出图（注意：选「人物传奇」必填金句才能看到底部金句效果）
- B7.2 验证剪映实际草稿：打开 .drafts 看字幕/媒体/特效
- B7.3 / B7.4 ASR / TTS 真实调用（火山）
- 测试单图重画：到任意已完成任务的 /result.html，hover 到任一分镜图右下角点 ↻ 重画
- 测试任意步骤重跑：到结果页左侧 timeline 节点 hover 出「↻ 从这里重跑」

## 6. 仍未做（VSCODE_HANDOFF_20261003.md 中 B 系列剩下部分）

- B1.1 任务分组位置（按日期/状态）
- B1.2 字体/间距像素对齐 STORY 真值
- B1.4 结果页「原文对比」并排显示改写前后
- B2.1 step2_split X4/aS/rS/iS 校验
- B2.2 提示词批次并发调度
- B2.3 元信息异常回退摘要
- B3.1 多张参考图（provider 能力限制）
- B3.5 封面版本（多版本对比/切换）
- B4.* 文案工作台多会话（workbench.py 尚未建）
- B5.* 提示词助手取消请求（prompt_assistant.py 限制）
- B6.* 素材库完整分类
- B8.* 选品/对标/市场/账号入口（新业务，需新设计）

详情见 `REMAINING_GAPS_20261003.md`。