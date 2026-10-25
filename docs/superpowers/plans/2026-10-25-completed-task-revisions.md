# Completed Task Revisions Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:executing-plans to implement this plan task-by-task.

**Goal:** 已完成任务保持历史成品，修改后在新ID执行；保留正在修改的南怀瑾版本。

**Architecture:** 新增task_versions负责完成检测、只读克隆和引用重定向。参数保存、队列重跑和封面操作共用它，前端跟随返回的新ID。读取和未完成任务不改变。

**Tech Stack:** Python标准库、现有HTTP/TaskQueue、原生JS。

**Spec:** docs/superpowers/specs/2026-10-25-completed-task-revisions-design.md

## Global Constraints

- 不自动提交真实生图、LLM或重做成功素材。
- 不启动Story，不覆盖其他软件；保留未提交历史代码。
- 原任务文件及剪映草稿保持不变；正式恢复保留可逆备份。
- 未完成任务的原ID续跑、暂停和调序维持现有行为。

## Review Focus

- 已完成封面的文字保存与生成入口同样必须分版本。
- 上传/BGM导入发生在配置保存前，必须先取得新版本ID。
- 克隆不能保留指向旧任务的可写路径，不能修改原任务的图片历史。
- 处理中/未知收费回执不能通过克隆绕过提交保护。
- 恢复历史时当前修改与暂停队列必须保留；不可凭空标成功。

## Task 1: 共用版本助手及完成任务入口

Files: create task_versions.py, tests/test_completed_task_revisions.py; modify server.py (fork/config), task_queue.py(enqueue), task_cover.py(action).

- [x] 写失败测试：源目录全量hash不变、新ID素材独立、原完成标记保留、未完成ID不变。
- [x] 实现完成判定、排除执行态/完成标记的复制和路径重定向。
- [x] 已完成任务参数保存、enqueue和封面写操作改到新ID；保留原job完成记录。
- [x] 跑版本与队列、封面、原有人工编辑回归。

## Task 2: 前端跟随新版本和提示词查看

Files: assets/workflow_actions.js, assets/task_cover.js, task_cover.py(view), tests/cover_prompt_history.test.cjs, relevant node regression.

- [x] 参数保存前先分支，以新ID接收上传/BGM；失败重试复用已创建的新ID。
- [x] 重跑和封面响应返回新任务后导航到新任务，不刷新或覆盖原历史。
- [x] 保留已完成候选的提示词历史查看修复，验证查看/复制不提交。
- [x] 用隔离入口和IAB验收，保存截图和清单hash。

## Task 3: 安装和南怀瑾历史恢复

Files: guarded deploy/entry verification and private recovery script; audit evidence.

- [x] 模拟当前原地重跑归档，在副本中保留新工作版后恢复原成品，确认任务路径和队列。
- [ ] 候选测试全部通过后，请用户正常退出；按精确差异安装，复核运行清单。
- [ ] 正式恢复前验证原成品draft_info文件和归档完整性，备份当前任务/队列/索引；写后读回。
- [ ] 确认原任务回到历史、新任务保留暂停；不启动真实生成；记录本地提交及未推送状态。
