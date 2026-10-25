# RH工作流目录实施计划

> **For agentic workers:** 使用superpowers:executing-plans在本会话逐项实施，最后作一次独立审查。

**Goal:** Qwen/FLUX/SDXL和用户添加的可兼容工作流可自行选择，并允许封面与内页分别选择。
**Architecture:** 工作流目录与多图快照缓存，严格本地推理图适配器；复用既有会员Key与正式receipt路径。现有图片/未知回执不重置。
**Tech Stack:** Python3.14、原生HTML/JS、unittest、Node、实际desktop入口和IAB。
**Spec:** docs/superpowers/specs/2026-10-25-rh-workflow-catalog-design.md

## Global Constraints

- 不提交真实生图，不修改正式Key、默认选择、任务和成功资产。
- 不开放任意API节点、脚本执行或多输出收费图；不自动在不同引擎间降级。
- 保留旧Qwen及G2、ModelScope等既有路径。
- 原taskId查询与工作流当前选择解耦。

## Review Focus

- 自动节点识别不能接错正负提示词或执行隐藏API。
- 保存/添加失败保留原配置；凭据变化使旧核对失效。
- 独立封面/内页选择不能被系统默认覆写。
- 任务重复点击、下载失败、暂停恢复不能新增提交。
- 没有真实出图与账单证据，不能称真实效果/费用已验收。

### Task 1: 图结构与目录
- [x] 测试真实FLUX/SDXL图归一化、模型/节点/输出限制；先观察失败再实现。
- [x] 新rh_workflow_graphs.py / rh_workflow_catalog.py，扩展旧候选和快照兼容。
- [x] 目录添加/核对接口、公共投影和正式provider支持按key解析。

### Task 2: 各流程独立选择
- [x] 请求透传workflow字段；封面/分镜/创意新配置解析和既有查询保护。
- [x] 设置工作流添加、各选择器、草稿恢复和参数摘要。
- [x] Node与Python离线验证。

### Task 3: 候选与交付
- [x] 精确函数/资源差异组装候选，独立审查并修复重要问题。
- [x] 候选Python/Node、desktop临时入口和IAB，零真实生成。
- [ ] 当前自有代码和精确旧文件delta提交；正常退出后安装及复核。

## Ledger

- 授权：用户“这些工作流你都给我接上我到时候自己选择”。原提案截图明确包含内置、添加与分别选用。
- 只读核对：FLUX与SDXL官方API均code0，已保存原始图；未创建任务。
- Ruling: 复用当前dirty工作区和source-before快照，按函数组装安装候选；不覆盖既有不相关修复。

- 用户后续要求优选数据高者，已添加热门FLUX和Qwen中文海报数据快照，基础SDXL与原Qwen标为备选；未自动切默认。
- 费用询价：未查到工作流固定单张预估，界面标未实测，未新建收费任务。
- 页面恢复原封面模式/标题，同时显示独立工作流，已通过真实IAB与专项回归。
