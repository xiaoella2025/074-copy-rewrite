# RH币正式绘图提供商与封面切换恢复实施计划

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development or superpowers:executing-plans. 本次按文件分工，主代理负责集成和最终验收，工作区旧改动不归本任务。

**Goal:** 系统设置可管理并选择 RH币工作流，用于封面和分镜；明确换引擎重跑可以安全绕开无编号的旧未知封面单。
**Architecture:** 正式 provider `runninghub_workflow` 复用独立配置和完整图快照，新供应商适配器复用标准回执回调及原任务查询。旧封面换引擎使用显式恢复操作，完整归档旧单，先保存新操作意图再由正常队列继续。
**Tech Stack:** Python3.14、现有HTTPServer、原生HTML/JS、unittest、Node、临时数据与模拟供应商。
**Spec:** docs/superpowers/specs/2026-10-25-rh-workflow-provider-and-cover-switch-design.md

## Global Constraints

- 不调用真实供应商，不改正式任务或Key，不启动Story，不自动切换默认模型。
- provider 标识统一 `runninghub_workflow`；国内站会员配置仍存原 RH币独立配置，G2配置分离。
- 正式调用提交前存回执，taskId优先落盘；未知单不重发，已有图片不重做。
- 仅在用户明确确认后调用封面 `replace-unknown` 操作，数据包含 `slot / provider / operation_id / acknowledge_unknown:true`；它只处理无编号、无结果、缺主封面、换了引擎的未知旧单。
- 不覆盖工作区其他改动；安装后端前必须正常退出074。

## Review Focus

- 正式流程不能误用G2企业Key，原任务查图不能误用后来换的Key。
- 带文字封面的完整提示词与补充要求不丢失、不被独立页固定测试prompt替换。
- 不同任务、两个封面、不同分镜的回执和图片不能串用。
- 非2xx/丢失响应/重复点击不能产生第二次提交。
- 旧未知回执归档要在清空原记录前完成；确认本身不调用供应商。

### Task 1: 正式工作流适配器及dispatcher（主代理）

Files: `rh_workflow_provider.py`、`rh_coins_workflow.py`、`server.py` 配置和dispatcher相关函数；新增测试。
- [x] 失败测试：独立配置、固定图与原提示词、回调先于轮询、未知不重发、原任务查询、常用比例。
- [x] 实现 `resolve(backend)`、`generate(backend,cfg,prompt,ratio,resolution,on_task_id)`、`query(backend,cfg,task_id)`；接入公共配置、分镜回执、正式分发。
- [x] 验证测试并记录。

### Task 2: 旧封面明确切换恢复（恢复代理）

Files: `task_cover.py` 与独立测试；不改前端或主代理的server函数。
- [x] 失败测试复现已改魔搭但旧RH未知单拦截。
- [x] 实现 `replace-unknown` 显式操作、旧回执归档、一次性新操作意图；本地封面复用优先；原有普通续跑仍保守。
- [x] 增加 `runninghub_workflow` provider校验和query分支，委托适配器查询。
- [x] 运行封面回归测试。

### Task 3: 设置与各选择入口（前端代理）

Files: `settings.html`、新 `assets/rh_workflow_settings.js`、`index.html`、`assets/workflow_actions.js`、`assets/task_cover.js`、`assets/app_nav.js`、对应Node测试；其他发现的纯前端选择器需报告。
- [x] 系统设置第6个provider面板，复用原RH币配置接口，真实保存/核对，单独测试入口。
- [x] 新建任务和任务参数/封面卡均可选正式provider，主导航移去突出实验入口。
- [x] 第6步参数窗口识别旧未知单与换引擎，显示明确提示及确认，用户提交后先保存参数、调用/api/task-cover/{tid}/replace-unknown，再rerun；失败时不继续排队。
- [x] 运行Node回归测试，报告接口依赖。

### Task 4: 集成与交付（主代理）

- [x] 接口契约互查，修复遗漏的后端白名单和恢复路径。
- [x] 独立审查规格及代码，重要问题按失败测试修复。
- [x] 固定候选清单；候选Python/Node、实际desktop入口和IAB隔离验收；无真实平台请求。
- [x] 本次自有文件和旧文件精确delta留档提交；正常退出074后安装，再做安装后复核。
