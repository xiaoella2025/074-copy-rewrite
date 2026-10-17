# 074 Benchmark Batch Recovery Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking. Default recommendation: execute in the current chat; delegate only if the user selects delegation.

**Goal:** 让现有对标批量操作关页后继续、重开可见进度、软件中断后显式续跑，并保护手改文案和收费回执。

**Architecture:** 对标批次使用独立原子 JSON 作业记录和后台线程，复用已有对标处理函数、选品作业模式及带货回执。新增接口由小型路由适配器接入现有会话鉴权，作品列表原按钮提交和展示批次；不改变视频队列。

**Tech Stack:** Python 3.14、标准库 threading/JSON、现有 SQLite 带货回执、原生 JavaScript、unittest、Node test、现有 Windows CPython 安装运行时。

**Spec:** `docs/superpowers/specs/2026-10-17-benchmark-batch-recovery-design.md`（用户已于 2026-10-17 确认）。

## Global Constraints

- 仅修改 `D:/1Leida-shipinhao/074-copy-rewrite` 及其已安装资源；不改 071/072/073。
- 操作仍从原有作品列表批量按钮发起，保持紧凑布局。
- 软件重启后不自动启动旧作业；成功项不重做，结果未确认的收费判定不自动重发。
- 不保存 API Key；不复制整篇文案作为批次配置；昵称和标题不参与身份判断。
- 复用现有本地 ASR、原视频下载、文案导出、编辑与带货回执，不新增提供商或自动换模型。
- 开发使用独立数据和模拟提供商；不启动真实采集、识别、模型请求或用户的旧任务。
- 保留现有修改和未跟踪文件；提交只含本次可独立归属的文件，其他修改留差异证据；不推送。

## Review Focus

- 同请求 ID、不同作品列表：拒绝冲突，不能返回另一批为“已提交”（Task 2）。
- 请求已提交但浏览器没收到响应：同 ID 查询/重交不另起作业（Task 2、4）。
- ASR 期间用户改稿或删除作品：保留新稿，不恢复被删除作品（Task 1）。
- 刷新后作品筛选为空或换到另一账号：仍显示原批次真实进度，不扩大处理范围（Task 4）。
- 旧作业文件损坏、供应商结果未知：保留记录并说明原因，不清空、不自动重试（Task 2、3）。

## File Structure and Contracts

| 文件 | 责任 |
|---|---|
| `benchmark.py` | 在原 `transcribe` 保存识别结果前校验文案快照 |
| `benchmark_ai_receipts.py` | 为原有“未确认”拒绝提供兼容 ValueError 的明确异常类型，保持账本格式 |
| `benchmark_batch_actions.py`（新） | 单条操作执行、文本指纹检查及既有回执复用 |
| `benchmark_batch_jobs.py`（新） | 作业验证、原子保存、后台执行、停止、恢复和公共状态 |
| `benchmark_batch_http.py`（新） | 三个新接口及会话/Origin/体积校验，不替换原对标业务接口 |
| `story1245_runtime.py` | 在已有安装初始化中接入新路由，保持幂等 |
| `assets/benchmark_batch.js`、`assets/benchmark.js` | 原按钮提交批次、利用已有轮询显示进度和恢复入口 |
| `tests/test_benchmark_batch_*.py`、`tests/benchmark_batch*.test.js` | 独立数据的执行、并发、恢复、HTTP 和页面验证 |
| `scripts/deploy-benchmark-batch-recovery.py` | 有备份和哈希保护的准备、候选验收、安装及复核 |

公共作业格式：`id` 为 32 位十六进制请求 ID；`kind` 为 `extract/download/mark/promo`；`rows` 保留输入顺序，每条含 `accountId/feedId/status/error/result`，promo 另含 `source_fingerprint`。不得持久化密钥或完整文案。批次状态和逐条状态严格使用设计中的枚举。

外部接口：`GET /api/benchmark/batch-jobs` 返回 `{jobs:[...]}`；`POST /api/benchmark/batch-start` 接收 `{id,kind,items:[{accountId,feedId}],mark?}` 返回 `{job:...}`；`POST /api/benchmark/batch-control` 接收 `{id,action:'stop'|'resume'}` 返回 `{job:...}`。条数限制为 1–100，重复作品身份、无效操作、路径式 ID 拒绝，冲突返回 409。

### Task 1: 保护本地识别期间的手动文案

**Files:** Modify `benchmark.py:transcribe`; Create `tests/test_benchmark_asr_race.py`。

**Interfaces:** 保持 `transcribe(backend,data)->feed`；只在已有 `LOCK` 内记录/比较 `transcript`、`transcriptReviewed`，修改或删除时抛出 ValueError，不覆盖用户修改。

- [ ] 写失败测试：模拟识别期间改稿，断言 `transcribe` 报冲突、最终文案仍为手改内容；删除作品不被重建；仅更新点赞等指标不阻断结果保存。
- [ ] 运行 `.desktop-tools/python/Scripts/python.exe -B -m unittest discover -s tests -p test_benchmark_asr_race.py`，确认失败点是旧结果覆盖手改文案。
- [ ] 实现锁内快照校验，保持原上传临时文件清理、ASR_RUNNING 释放及其他作品字段。
- [ ] 重跑新测试与 `test_benchmark_video.py`、`test_benchmark.py`，要求全部通过。
- [ ] 记录来源文件前后哈希/差异；只提交本项新测试和可独立归属的增量。

### Task 2: 持久批次和单条操作执行

**Files:** Create `benchmark_batch_jobs.py`、`benchmark_batch_actions.py`、`tests/test_benchmark_batch_jobs.py`；Modify `benchmark_ai_receipts.py`。

**Interfaces:** `BatchJobs(backend,executor=None)` 提供 `submit(data)->job`、`list()->list[job]`、`control(id,action)->job`。`get_manager(backend)->BatchJobs` 按数据根目录隔离；`execute_item(backend,kind,row,mark=None)->dict` 返回导出引用或复用标记；`UnconfirmedReceiptError(ValueError)` 保持原调用者兼容。

- [ ] 写失败测试：请求 ID 幂等及内容冲突；一次一个活动批次；相同 feedId 不同账号分别执行；刷新式多次 list 不二次执行；损坏作业文件保留；空目录 list 不创建文件。
- [ ] 运行 `.desktop-tools/python/Scripts/python.exe -B -m unittest discover -s tests -p test_benchmark_batch_jobs.py`，确认缺少作业模块/接口导致失败。
- [ ] 复用 `task_queue.atomic_json` 写 `benchmark/batch-jobs/<id>.json`；验证身份后落盘再起线程；每条领取前、完成后保存状态。启动读取旧 running/queued/stopping 作业时转 interrupted，不自动起线程。停止等当前条返回；resume 跳过 succeeded/unconfirmed，只重试明确允许的未完成/失败项。
- [ ] 补并通过操作测试：缓存文案不再 ASR、标记值固定、已完成导出保留、promo 指纹变化不发请求、已完成回执复用、未确认异常不调用模型第二次；软件中断时已写业务结果但未写批次结果也能安全回读。重跑 `test_benchmark_promo_receipts.py` 和 `test_benchmark_backup.py`。
- [ ] 提交本项新模块与测试，保留既有回执文件修改的独立差异证据。

### Task 3: 鉴权 HTTP 接口与初始化

**Files:** Create `benchmark_batch_http.py`、`tests/test_benchmark_batch_http.py`；Modify `story1245_runtime.py:install`。

**Interfaces:** `install(backend)->None` 幂等包装现有 Handler，仅匹配上述三个新接口；使用原 `_desktop_authorized()`。新接口 JSON body 上限 128 KiB；无效 JSON/参数 400、冲突 409、过大 413。导出引用只使用现有导出接口返回值，不提供任意路径读写。

- [ ] 写失败测试：未授权 403、错误 Origin 403、合法会话可提交/回读/停止/继续；非法 ID、缺失作品、超大 body 拒绝；旧备份和普通作品接口仍可访问。
- [ ] 运行 `.desktop-tools/python/Scripts/python.exe -B -m unittest discover -s tests -p test_benchmark_batch_http.py`，确认新增路由尚不存在。
- [ ] 接入 Task 2 的 manager；公共返回值屏蔽线程对象、内部根目录及凭据；捕获已知参数/冲突错误，不将损坏记录重置为成功空批次。
- [ ] 重跑新 HTTP、`test_runtime_updates1245.py`、`test_connected_modules_http.py`，全部通过且外部请求为零。
- [ ] 提交新适配器与测试；记录现有初始化模块的最小差异。

### Task 4: 原批量按钮、进度和显式恢复

**Files:** Modify `assets/benchmark_batch.js`、`assets/benchmark.js`；Create `tests/benchmark_batch_jobs.test.js`；Update `tests/benchmark_batch.test.js`。

**Interfaces:** 保留 `create(hooks)` 返回的 `render/pick/run/stop/running/prune`；新增 `sync(jobs)` 接收后端快照、`resume(id)`；由 `benchmark.js` 现有 load/轮询读取作业列表并调用 sync。run 只提交一次，不再在页面执行逐条业务循环。

- [ ] 写失败测试：关页式销毁 controller 后新 controller 回读同一批次；同提交 ID 丢响应后不新建；进度按操作类型展示；过滤为空时活动/中断批次仍可见；UI 读取失败不把任务改为停止或重交。
- [ ] 运行 `node --test tests/benchmark_batch_jobs.test.js`，确认原页面循环不能满足回读断言。
- [ ] 沿用原批量按钮和选择规则；显示真实 n/N、成功/失败/待确认数量、停止和“继续未完成项”。移除只针对旧页面执行循环的 beforeunload 提示；成功后的导出位置由用户点击打开/下载，不在后台主动弹窗。
- [ ] 跑两组批量 Node 测试及 `benchmark_backup.test.js`、`benchmark_radar.test.js`；实际隔离浏览器验证提交后导航离开、返回进度、中断恢复和下载入口，保存截图。
- [ ] 提交本项新测试和可独立归属的页面增量，不扩大选择范围或恢复成功项。

### Task 5: 安装版验收与逐项交付说明

**Files:** Create `scripts/deploy-benchmark-batch-recovery.py`；Update `docs/audit/2026-10-17-story1245-remaining.md`、`docs/audit/current-validation.md`。

**Interfaces:** 部署脚本提供 `prepare/test/apply/verify` 模式；候选模块在安装 CPython 中与独立数据运行。复用 `backend_runtime_manifest.verify/digest`；写入审计目录 `.desktop-tools/benchmark-batch-recovery-20261017/`。

- [ ] 实现准备和验收步骤：备份将更新的资源/模块与清单，确认安装版无无关差异；隔离数据模拟批次全部关键状态，不接真实微信/模型。
- [ ] 用候选运行时跑 Tasks 1–4 测试及带货回执、备份、雷达、视频队列和前六项的定向回归；保存准确测试数和零外部调用证据。
- [ ] 确认视频任务与对标批次都空闲后正常关闭 074，更新最小资源与清单并重新启动；有活动作业时保留，不强杀、不覆盖。
- [ ] 完整校验安装清单；用独立数据启动实际安装入口验证鉴权和后台继续；核对设置、模型档案、视频队列及既有任务产物哈希。目录选择器/剪映/真实供应商未实际验证的部分明确保留。
- [ ] 更新完成范围、实现方式、使用入口、证据和剩余缺口；向用户说明这一项怎么实现，不将整个 07–12 标为完成。只提交本项文件与文档，不推送。

## Execution Handoff

建议在当前聊天顺序实施：五项共用作业格式和恢复规则，顺序完成便于持续核对同一状态链。若用户选择代理分工，再按对应技能安排实现和审查；当前不派生代理。

**Plan review status:** 待用户确认实施计划与执行方式；尚未修改产品代码、测试、安装文件或正式业务数据。
