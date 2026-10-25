# Cover Gallery Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:executing-plans to implement this plan task-by-task.

**Goal:** 在分镜画廊旁提供封面画廊，展示准确提示词并复用图片编辑交互。
**Architecture:** 封面版本模块管理独立槽位、不可变图片和可恢复提交；现有封面提交统一接入。分镜编辑弹窗接受封面API地址，不复制裁剪/参考图UI。已完成任务在修改前分版本。
**Tech Stack:** Python、PIL、原生JavaScript/HTML/CSS，沿用现有接口鉴权。
**Spec:** docs/superpowers/specs/2026-10-25-cover-gallery-design.md

## Global Constraints
- 已完成原任务只读，修改另建新任务；未完成任务仍在本任务修改。
- 保留最近5个图片版本，槽位独立；查看不建立快照或调用供应商。
- 不自动切换平台，不提交真实收费生成；在途回执不可覆盖。

## Review Focus
- 参数更改不能把待生成提示词冒充旧图来源。
- 重复参考图请求、结果下载失败、响应丢失不能重复购买。
- 裁剪应针对原图；历史恢复须连同来源/提示词恢复。
- 两张封面和分镜索引不能串用。
- 旧任务查看不能写文件；修改完成任务必须先fork。

### Task 1: 封面图片版本和编辑接口
Files: cover_images.py, task_cover.py, task_versions.py, server.py, tests/test_cover_gallery.py
Interfaces: view(backend,tid,slot), media(backend,tid,slot,key), action(backend,tid,slot,name,data), commit(backend,tid,slot,raw,extra).
- [x] 添加并运行失败用例：只读查看、两槽隔离、裁剪/替换/恢复、5版本限制、并发版本冲突、完成任务原文件不变、参考图重复提交/不支持引擎/下载失败。
- [x] 实现可恢复图片和元信息提交，接入全部封面生成/上传；新增GET/POST /api/cover-image/<task>/<slot>。
- [x] 运行封面及已完成任务回归。

### Task 2: 同级封面画廊和编辑组件复用
Files: assets/workflow_view.js, assets/task_cover.js, assets/task_cover.css, assets/scene_image_editor.js, tests/cover_gallery.test.cjs
- [x] 添加并运行失败用例：页签顺序、提示词直接可见/当前图来源分离、第二槽条件显示、编辑弹窗调用封面路径、完成任务跳新版本。
- [x] 复用封面卡/分镜弹窗，增加画廊模式与常显提示词；保留原预览入口。
- [x] 运行相关Node回归并在隔离桌面入口验证交互和原任务哈希。

### Task 3: 候选安装包及审查
Files: scripts/deploy-cover-gallery.py, scripts/verify-cover-gallery-entry.py, docs/audit/2026-10-25-cover-gallery/
- [x] 以安装版为基线合并此前待安装历史保护修复；只替换受检函数/资源，校验独立修复未丢失。
- [x] 运行候选后端/前端测试、实际隔离入口和界面验证；独立审查。
- [ ] 074正常退出后安装、校验，再完成已授权南怀瑾历史恢复；不自动打开软件或执行任务。未退出则明确待安装。
