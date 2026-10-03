# 074 剩余差距清单（2026-10-03）

按 Codex 标记的 8 大块 + 用户最新截图痛点拆成具体可勾选项。每条标注：优先级（高/中/低）+ 是否需要付费接口 + 状态。

## A. 用户截图痛点（本轮已修，commit 82a7e3f）

| # | 痛点 | 改动 | 文件 | 状态 |
|---|------|------|------|------|
| A1 | 删除按钮太小看不见 | 24×24 opacity:0 → 28×28 默认可见 + 红边 hover | tasks.html | ✅ 已修 |
| A2 | 配音员/配音引擎混在一起 | label 拆成「配音引擎」+「音色」两层 | voice-lab.html | ✅ 已修 |
| A3 | 6 套封面规则只在终端文本展示 | cover-template-rules panel（3 方向 + titleLayout + subtitleLayout + plainHint）+ legend.svg | index.html + assets/cover-previews/legend.svg | ✅ 已修 |
| A4 | legend chip 缺预览图 | data-preview="legend" + 新建 legend.svg（深底金字+黑白人像左字右人） | index.html + assets/cover-previews/legend.svg | ✅ 已修 |

## B. Codex 本轮标记剩余差距（VSCODE_HANDOFF_20261003.md:27-35）

### B1. 新建任务/结果页细节 — 中优先级

- [ ] B1.1 任务分组位置（按日期/状态分组 vs 当前平铺）— index.html / tasks.html
- [ ] B1.2 字体/间距像素对齐 STORY 真值
- [x] B1.3 结果页「重生成」按钮（单镜/全局）—— commit f3b95a7（运行页 ↻ 重画 + ✎ 改 prompt + 失败镜批量重画），commit 5bf654f（结果页 wv-shot-redraw）
- [ ] B1.4 结果页「原文对比」并排显示改写前后
- [x] B1.5 创建参数卡片完整复原（处理模式/暂停/改写强度/视角）—— commit 2eba23e
- [x] B1.6 发布素材卡片完整复原（开关横排）—— commit 2eba23e

### B2. 分镜与图片引擎 — 高优先级（影响画面质量）

- [ ] B2.1 step2_split 完整移植 X4/aS/rS/iS 校验与重试
- [ ] B2.2 提示词批次并发调度（原版并发、当前串行）
- [ ] B2.3 元信息异常回退摘要（避免失败被误报完成）

### B3. 画图/封面工作台 — 高优先级

- [ ] B3.1 多张参考图（原版支持多张、当前仅 1 张）— image_lab.py + image-lab.html
- [x] B3.2 3 个封面构图方向规划/选择（build_cover_prompt 当前只取方向 1）—— commit 00f1214
- [x] B3.3 金句字段接入（subtitleLayout 已留位，但 UI 未暴露）—— commit f50b5c6（cover-subtitle 模板智能提示：legend 必填金句、emotional 推荐钩子）
- [x] B3.4 封面裁切（用户选好图后裁成 3:4/9:16 等）—— commit 0bd749f
- [ ] B3.5 封面版本（多版本对比/切换）
- [x] B3.6 单图重生成（image-grid 已留 data-redraw-idx，但重画流程未通）—— commit 5bf654f + f3b95a7（单镜重画 + 改 prompt 重画 + 失败镜批量重画 + 结果页 wv-shot-redraw）

### B4. 文案工作台 — 中优先级

- [ ] B4.1 多会话管理（当前仅单会话持久化）— workbench.py
- [ ] B4.2 技能选择（原 8 赛道 24 提示词已接入，但用户技能未做下拉）
- [ ] B4.3 引用导入（IMA/Obsidian 已接，但工作台内引用未做面板）
- [ ] B4.4 diff/版本浏览（版本文件已存，UI 未列版本）
- [ ] B4.5 流式/压缩/多模态

### B5. 提示词助手 — 中优先级

- [ ] B5.1 取消请求中断后台/provider（当前只断客户端等待）— prompt_assistant.py
- [ ] B5.2 远端系统模板增量
- [ ] B5.3 原助手紧凑布局逐项对照
- [ ] B5.4 失败提示（占位符校验/重试反馈）

### B6. 素材库 — 中优先级

- [ ] B6.1 完整分类/标签（原 PersonAssets）
- [ ] B6.2 资料卡/编辑流程
- [ ] B6.3 系统设置继续比原页面交互

### B7. 真实验收 — 必须由用户完成（需付费）

- [ ] B7.1 跑付费生成（任意赛道）— 验证 6 套封面规则真的影响出图
- [ ] B7.2 验证剪映实际草稿（打开 .drafts 看字幕/媒体/特效）
- [ ] B7.3 ASR 真实调用（火山）
- [ ] B7.4 TTS 真实调用（火山/MiniMax/Aura）
- [x] B7.5 重画流程验证（不会误用旧产物）—— commit 5f3eaf3（rerunFrom 步骤失效语义）+ f3b95a7（单图重画保存到 task_dir/covers）

### B8. 原版尚未开通侧栏 — 低优先级（需新设计）

- [ ] B8.1 选品入口
- [ ] B8.2 对标入口
- [ ] B8.3 市场入口
- [ ] B8.4 账号入口

## C. 本轮 commit 列表（截至 f3b95a7）

```
f3b95a7 fix B3.6 增强：失败镜批量重画
2eba23e fix B1.5/B1.6 结果页参数卡片完整复原
5bf654f fix B3.6 单图重生成（运行页 + 结果页都接通）
f50b5c6 fix 封面副字段随模板智能提示：legend 必填、emotional 推荐讲人物钩子
5f3eaf3 fix 从任意步骤重跑 + 分镜图片 viewer + app-nav 全站整合
43ac8ec fix tasks.html active 视图用 StoryHistory + cover-template 自定义面板
daba807 fix 配音/画图实验室 chip active 视觉强化
29ea51c fix voice-lab 加「添加自定义音色」入口
06f8a4f fix sidebar 加「进行中」入口
a610d05 fix tasks.html 默认视图改为「全部」
0bd749f fix 上传封面按选中比例自动中心裁切
00f1214 fix 封面构图方向选择：build_cover_prompt 支持 cover_direction
60eddfe fix tasks.html 任务卡片紧凑化对齐 STORY queue-row
82a7e3f fix 图1/2 截图痛点 + 6 套封面规则落到 UI
e9a0f4e fix 图12 从这里重跑回填表单 + 跳过已完成步骤
e9aebbc fix 图10/11 chip 描述对齐 Story 参考
eed312e fix 任务列表/历史任务分离 + 重跑按钮 + 产物预览实时刷新
a870e28 style-chip 预览图改为 9:16 显示全图
8f5062e 图文链路：运行页 + 结果页接入 7 节点工作流 + 表单紧凑化
```

## D. 下一步建议

按当前额度状态，已修：B1.3/B1.5/B1.6/B3.2/B3.3/B3.4/B3.6/B7.5。
未做（B1.1/B1.2/B1.4 / B2.* / B3.1/B3.5 / B4.* / B5.* / B6.* / B8.*）：
- B1.x 多为视觉打磨，可下个 PR 一起做
- B3.1/B3.5 需要 provider 能力扩展（多张参考图/多版本切换）
- B2/B4/B5/B6 是后端工作（高优先级但需要专门阶段）
- B8 是新业务（需新设计）
- B7.1~B7.4 必须用户授权才能跑

B7.1 跑付费生成会消耗用户额度，需要用户授权。
