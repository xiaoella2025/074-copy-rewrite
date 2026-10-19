# Story 升级说明定位流程

2026-10-19 按用户要求回看 1.24.5 原始操作记录后固化。目的是复用拆解产物里的定位方法，避免每个版本重新摸索。

## 经记录确认的路径

1. 2026-10-14，先从已解出的 `frontend/index.html` 找活跃入口，搜索“检查更新”、`check_update` 等标记。
2. 在入口脚本中找到 `check_update({currentVersion,fp,proxy,baseUrl})`。原生程序字符串对应 `src/updater.rs` 和 `/v1/update/check`；更新弹窗渲染接口返回的说明。
3. 1.24.5 活跃入口是 `.desktop-tools/story1245-audit/frontend/assets/index-BL1mWGtO.js`；1.25.0 是 `.desktop-tools/story1250-audit/frontend/assets/index-BjfyS2m-.js`。文件名会变，必须从当前 HTML 定位。
4. 原记录还明确记录了匿名接口 403/1010，之后采用用户提供的 1.24.5 原文确定六项范围。不能把“找到读取入口”记成“静态包里已经包含全文”。

## 可直接复用的只读命令

```powershell
node scripts/audit-story-update-entry.cjs .desktop-tools/story1250-audit/frontend
```

输出活跃入口 SHA-256、调用和渲染片段，不执行解出的代码，不连接网络。

脚本还会沿本地模块导入找到 `manual-url-*.js`。本轮从 `Settings-B8ihHphS.js` 追到 `manual-url-DMK8uq8k.js` → `https://storybound.top/docs/`；该网页公开HTML的 `DOC_BASE` 和 `DEFAULT_DOC` 合成官方说明地址 `https://qnc80j2zlx.feishu.cn/docx/Q2Y0d7JzMoV4crxlEcvcYby2nig`。只读命令：

```powershell
lark-cli docs +fetch --api-version v2 --doc Q2Y0d7JzMoV4crxlEcvcYby2nig --scope keyword --keyword '1.24.6|1.24.7|1.24.8|1.24.9|版本更新' --format json
```

当前修订55的“十四、版本更新记录”仅列1.24.5/1.24.4/1.24.3。找到文档不等于中间四版原文已经取全，必须记录缺口。

原有静态解包工具：

- 7-Zip：`D:/1Leida-shipinhao/tmp/story-1.24.1-sales/tools/full/7z.exe`
- PE 前端提取：`D:/1Leida-shipinhao/tmp/story-1.24.0-extract/Storybound-1.24.0-完整拆解-便携版-20261001/tools/extract-assets.cjs`
- 草稿组件提取：同一 `tools/` 中的 `extract-pyinstaller.py`；跨版本字节码只作静态检查。

只在已有解包目录不完整时补提取所需文件。记录安装包 SHA-256，不运行安装程序，不启动已安装或解出的 Story 主程序，不改用户现有 Story 安装。用户已再次明确禁止打开其已安装软件。

## 来源与当前证据

- 原始聊天：`01a0f5a4-a2f0-7233-88e1-ba66e33ce935`，2026-10-14 11:20–11:29 UTC 的工具/消息记录；重点是活跃入口、原生更新接口和失败边界。
- 1.24.5 核对文档：`docs/audit/2026-10-17-story1245-remaining.md`。
- 1.25.0 包来源与哈希：`.desktop-tools/story1250-audit/input-provenance.json`。
- 本轮已经取得的完整 1.25.0 正文：`.desktop-tools/story1250-audit/official-release-notes.txt`；来源是本轮已有 Story 显示的官方更新弹窗，不能伪称为静态提取的全文。用户后续澄清应优先复用拆解路径，后续遵照该要求。

完整说明取得后逐条核对，对已实现项只复验；线上账户、作品托管等厂商服务逻辑不能伪装成本地功能已完成。

## 累计版本不能遗漏中间说明

`check_update` 只提供当前最新版，不能证明涵盖中间各版。拆解的1.25.0活跃入口另有历史公告请求：`/v1/announcements?productId=storybound`，通过原生 `http_request` 读取，成功响应的数据在 `data.announcements`。优先沿这个入口核对每版发布记录。1.24.5到1.25.0的范围包括1.24.6、1.24.7、1.24.8、1.24.9和1.25.0五版。
