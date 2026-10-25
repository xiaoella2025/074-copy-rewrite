# RH 币生图独立入口实施计划

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:executing-plans to implement task-by-task. 本次在用户指定工作区实施，候选安装资源、临时数据与正式运行分离；不改动其他开发者已有改动。

**Goal:** 增加默认关闭的独立单图实验入口，接入消费级会员工作流，可靠查询原任务并保存结果。
**Architecture:** 新模块负责白名单工作流核对、单图参数及独立持久任务；server 只接鉴权路由，前端复用实验页。固定审查后的完整图提交，不执行远端随后修改的图。
**Tech Stack:** Python 3.14、现有 HTTPServer、原生 HTML/JS、unittest、Node test。
**Spec:** docs/superpowers/specs/2026-10-25-rh-coins-image-experiment-design.md

## Global Constraints

- 默认关闭；独立 Key、独立数据；原有 G2、模型设置、任务数据不变。
- 只用模拟平台验收，不提交真实生图。
- 第一版面向手册指定国内站；仅预选已找到的 Qwen 原生候选，不把同 ID 推断为国际站通用。
- 没有完整图/未经审查的节点不能生成；平台不公开 Key 类型枚举，显示原始 apiType，不虚构“已自动验证会员 Key”；要求用户从消费级会员页取 Key。
- 任何提交不明不自动重发；取图失败只恢复下载；保存本地结果须返回实际路径。
- 候选包保护安装版独立修复；需要关闭软件才安装，不强退、不打开正式软件。

## Review Focus

- 检查失败后不得继续使用旧的成功校验；Key 改变使工作流校验失效。
- 远端图带未知节点/额外输出/循环不能进入提交。
- 重复点击、HTTP 响应丢失、关闭网页和重启后不能产生重复购买。
- 已返回 taskId 即使伴随报错仍要保存，未知状态不得变成可重提。
- 另存失败保留原结果；同名文件不覆盖；Key 不出现在 GET、错误、日志或任务记录。

### Task 1: 工作流及独立任务后端

Files: 新增 `rh_coins_workflow.py`、`rh_coins_experiment.py`、`tests/test_rh_coins_experiment.py`。
Interfaces: `audit_graph(graph)`/`build_graph(graph,prompt,ratio,seed)`；实验模块 `state/configure/check/submit/query/media/export_image(backend,...)`。
- [x] 先写并运行失败测试：默认关闭、图审查、单图参数、配置隔离、重复提交、未知状态、关闭后查询、另存。
- [x] 实现最小后端，真实运输只复用现有 HTTP 方法。
- [x] 运行后端测试，记录结果。

### Task 2: 页面、导航与鉴权路由

Files: 新增 `rh-coins-experiment.html`、`assets/rh_coins_experiment.js`、`tests/rh_coins_experiment.test.cjs`；修改 `server.py` 和 `assets/app_nav.js`。
Interfaces: `/api/rh-coins-experiment` GET；POST `/config /check /generate /query /export`；GET `/image/<operationId>`。
- [x] 先写失败页面测试：只在点击生成时调用 generate、丢失响应保留 operation ID、历史查询与导出。
- [x] 实现页面及导航；输入 Key 不回显、不自动复用旧模型 Key；修改配置使检查失效。
- [x] 测试鉴权、实际页面和既有独立实验。

### Task 3: 候选打包、验收与交付

Files: 新增 `scripts/deploy-rh-coins-experiment.py`、`scripts/verify-rh-coins-experiment-entry.py`，审计 `docs/audit/2026-10-25-rh-coins-experiment*`。
- [x] 固定开始前快照，以局部字节码/文本补丁创建候选包；包含已准备未安装的封面首次错误诊断修复。
- [x] 跑候选 Python/Node、真实 desktop entry 临时数据与模拟平台验收。
- [x] IAB 验证独立页：默认关闭、配置核对、单图生成、原任务查询、导出，记录模拟和真实请求数量。
- [x] 最后审查；任务所属新文件与现有文件的精确 delta 分开提交。
- [ ] 若 074 仍运行，请求正常关闭；关闭后安装并复核。未实跑的计费和画质明确留待单张付费验收。

## 执行记录

- 2026-10-25：Task 1/2 完成；Task 3 候选通过69 Python /25 Node及实际桌面后端入口、IAB隔离验收。无真实平台请求。
- 独立审查唯一重要问题（非2xx正文中的taskId丢失）已补失败测试并修复；另补805终态二次确认和账户预检未提交判断。
- 正式074仍在运行，尚未安装；不能称真实Qwen工作流或扣费已验收。
