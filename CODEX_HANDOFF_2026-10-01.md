# 给 CODEX 的 074 交接文案（2026-10-01）

接手 `D:\1Leida-shipinhao\074-copy-rewrite`。本轮我用 STORY 1.24.0 参考包把 LLM 配置编辑器对齐了"live auto-save + chip 多选模型池"，但**没动**一个相邻的二级 bug（脱敏 apiKey 被回写），留给 CODEX 接着改。

## 当前基线

- master 最新：`64cec0b`（本轮两批共 5 个新提交，与远端同步，已 push）。
- 工作树干净，无未提交改动。
- 本轮改动文件：`server.py`（+11 行 / -7 行）、`settings.html`（+239 / -43）。
- 用户本机的 18801 `pythonw.exe` 服务**仍跑旧代码**（server.py 改过必须重启才生效）。

本轮 commit 链：

```
64cec0b 修真 bug：草稿 profile 允许空 Key + 备选模型 chip 多选对齐 STORY
bf1aeff 修复 LLM 配置编辑：live auto-save + 设为当前/删除按钮接线
a247e23 补充 VS Code 图文验收交接（VS Code 接手图文真实 API 测试用）
```

## 本轮做了什么 + 为什么

### 1. 真 bug：列表永远 0 个配置（server.py）

用户报：点"+ 新建配置" → 填表 → 返回 → 列表还是"已保存 0 个配置"。

**真因**：之前的 `openNewProfile` 立即 POST 一个 `enabled:false` 的空草稿；server `/api/profiles` 校验里有这段：

```python
if not any(p.get("enabled") for p in incoming):
    incoming[0]["enabled"] = True            # 没启用 → 自动启用第一个
active = next((p for p in incoming if p.get("enabled")), None)
if active and not (active.get("apiKey") or "").strip():
    raise ValueError("当前激活的 profile 必须填写 API Key")
```

→ server 自动启用空草稿 → 空 Key → 400 拒绝 → 前端 toast "创建失败" → **表单根本没显示出来** → 列表自然 0。

修复（server.py:2731-2739）：只校验真正 enabled 的 profile 必有 Key；草稿允许空。已用 curl 在 18802 临时端口三段验证过：

```
enabled:false, apiKey:""     → 200 ok（auto-enable 后存盘）
enabled:true,  apiKey:""     → 400 已启用的 profile 必须填写 API Key
enabled:true,  apiKey:"sk-…" → 200 ok
```

### 2. UI 对齐 STORY Settings-XLgSTp15.js

对照 STORY 截图（用户给的图 3：`Settings-XLgSTp15.js:739-848` 的 wa 组件），发现差距：

| 项 | 旧 074 | 新 074（已合） |
|---|---|---|
| 编辑器头部 | ← 返回 / ✓ 设为当前 / 🗑 删除 | 一样 |
| 默认模型 | chips 缺 `+ 自定义` | chips + 末尾 `+ 自定义`（prompt 输入 model id → 写进 `profile.models` 常驻） |
| 备选模型 | `<textarea>` 一个一行 | **chip 多选 toggle**，与默认模型共享同一 chip 池 |
| 默认 vs 备选 | 互不感知 | **互斥**：默认模型从备选 chip 自动隐藏 |

字段名 bug 顺手修了：JS 用 `fallbacks`（复数）写，server 的 `public_profiles` 读 `fallback`（单数），reload 后备选列表丢空。已对齐成 `fallback`（单数），`proxy` → `proxyUrl` 同理。

### 3. Live auto-save

参考 STORY `Settings-XLgSTp15.js:974-984` 的 `k(v)` 模式——每个 onChange 立即 POST（防抖 300ms）。已实现：

- `scheduleAutoSaveEdit()` 300ms 防抖
- `persistEditProfile()` 串行化避免乱序
- `closeEditProfile()` 关闭前 flush 挂起 save

`saveProfileFromEdit()` 留作兼容旧调用入口（不再被任何 UI 触发，但代码仍在）。

## 还**没改**、留给 CODEX 的 bug

### Bug：脱敏 apiKey 被回写

`public_profiles()` 把 apiKey 脱敏返回（server.py:411-413：`sk-a•••••••••••••••-z`）。前端 `profilesCache[i].apiKey` 拿到的是脱敏串。

当用户**编辑现有 profile 但不重输 Key** 时：
1. 打开编辑 → `$("llm-edit-key").value = ""`（显示空）
2. 用户改了别的字段（名字 / 模型），没碰 Key
3. `persistEditProfile`：`if (apiKey) p.apiKey = apiKey;` → apiKey 为空 → **不覆盖**
4. POST 把 `p.apiKey`（脱敏串）发出去
5. server 把它当真 Key 写盘
6. 下次调 LLM：`resolve_active_llm_settings` 拿到的 `api_key` 是脱敏串 → 鉴权失败

修法二选一（你定）：

**方案 A（server 端 merge，推荐）**：POST `/api/profiles` 时如果某 profile 的 `apiKey` 是脱敏格式（匹配 `^[^*•]{0,4}[•]+[^*•]{0,4}$` 或包含 `•`），就**不覆盖**磁盘上的旧值。需要在 server 维护"当前哪些 id 是脱敏回显的"或者在请求里加个 `preserveApiKey: true` 标志。

**方案 B（前端剥离）**：`persistEditProfile` 里如果用户没填新 Key，把 `p.apiKey` 字段从 POST body 里整个删掉。前提是 server 把"字段缺失"和"字段为空字符串"区分对待（目前 server 把两者都当成"无 Key"）。

方案 A 更稳，因为：
- 方案 B 改不动"用户想清空 Key"这个场景（清空 Key 也要发空串）
- 方案 A 把判断责任放在 server，前端不用知道脱敏规则

参考点：`server.py:404-426`（`public_profiles`）、`server.py:2711-2740`（POST 处理）。

### 其他可选优化（不在本轮，但 CODEX 可以顺手做）

- 打开编辑视图时把已激活 profile 的 `✓ 设为当前` 按钮改成 `✓ 当前配置中`（disabled 状态），更明确告诉用户为什么没这按钮。STORY 也是隐藏，但用户报怨过。
- `provider` chip 切换时如果新 provider 的 baseUrl 和旧的不同，应该问用户要不要覆盖（而不是默默清空）。
- `jimeng` / `modelscope` / `runninghub` / `custom` 几个出图通道完全没碰，不在本轮范围。

## 关键参考文件

| 用途 | 路径 |
|---|---|
| STORY 拆解（已解压，504MB） | `D:\1Leida-shipinhao\tmp\story-1.24.0-extract\Storybound-1.24.0-完整拆解-便携版-20261001\` |
| STORY LLM 编辑器（readable） | 上述目录 `analysis/readable/assets/Settings-XLgSTp15.js:619-1078` |
| STORY 拆解索引（AGENT 入口） | 上述目录 `AGENT_ENTRY.md` |
| 旧 1.21.0 拆解记录 | `D:\1Leida-shipinhao\074-copy-rewrite\_reverse\_ui\INDEX.md` |
| VS Code 图文验收交接（背景） | `D:\1Leida-shipinhao\074-copy-rewrite\VSCODE_HANDOFF_2026-10-01.md` |

## CODEX 接手顺序建议

1. 先核对 `git status`、HEAD、`server.py:2711-2740` 现状；不要覆盖别人提交。
2. 修脱敏 apiKey 回写 bug（方案 A 或 B，自己定）。
3. 跑 `python -m unittest discover -s tests -q`（50）+ `node --test tests/image_pipeline.test.js`（24）确认没破回归。
4. 在临时端口（cp server.py.bak 改 PORT=18802）启 server，curl 验证三种 case：保存现有 profile 不重输 Key / 重输 Key / 清空 Key。
5. commit + push（每修一批就推，别攒半拉子，参考 `feedback-074-push-each-fix`）。

## 操作红线（参考 `feedback-do-not-impact-073`）

- **不要** unzip 任何 `D:\1Leida-shipinhao\软件\` 下的大 zip（已解压的 STORY 在 tmp 里够用）。
- **不要** 后台启动 `server.py` 占用 18801 端口（用户本机已有一个），用临时端口测。
- **不要** 读 071 / 072 / 073 任何文件或 API Key（074 走自己的 `data/settings.json` + `data/profiles.json`）。
- 074 UI 里**不要**出现 STORY / Storybound / "原版" 等品牌名（参考 `no-brand-name-leak-in-ui`）。

## 汇报时请包含

- 用了哪种方案修脱敏 bug，以及为什么
- 修了哪些字段名 / 形状不一致问题
- 回归测试结果（Python 50 + Node 24）
- 新增的临时端口测试用例
- 截图或日志（**必须**遮掉 apiKey 明文，参考 `feedback-074-push-each-fix`）
