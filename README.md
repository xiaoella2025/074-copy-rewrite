# 074-copy-rewrite · 文案改写（图文1号线 + 图文2号线）

两个并行改写体系，一条复刻 Storybound 1.24.0，一条给你自定义。

## 启动

双击 `Start074.cmd`，浏览器自动打开 http://127.0.0.1:18801

首次使用先点右上角「⚙ 设置」填 API Key（**只保存在 074-copy-rewrite/data/settings.json**，不会读取 071/072/073）。

## 两条线

### 图文1号线（STORY 原版，从 1.24.0 复刻）
- 标准改写（差异化 ~40%）
- 深度改写（差异化 ~60%）
- 高度原创（差异化 ~80%）

### 图文2号线（你的自定义）
- 改表层（差异化 ≥ 50%）
- 创意改表层（差异化 ≥ 70%）
- 改骨架（差异化 ≥ 80%）
- 原创（独立创作）

## 公共开关
- **叙事视角**：保持原文 / 第一人称 / 第三人称
- **黄金 3 秒钩子**：5 种钩子类型（颠覆认知/扎心共鸣/代价悬念/内幕揭秘/反差独白）
- **补充要求**：在「补充要求」框内输入任意指令（如「再口语一点」）

## 目录结构

```
074-copy-rewrite/
├── server.py                 # 后端（自带 HTTP server）
├── index.html                # 前端（单页）
├── prompts/
│   ├── hook.py               # 黄金 3 秒钩子（公共）
│   ├── story/                # 图文1号线提示词（从 STORY 复制）
│   │   ├── base_rewrite.py       # P010 通用改写规则
│   │   ├── track_rewrite.py      # P014 对标文案改写
│   │   ├── technique_standard.py # P043 标准改写技法
│   │   ├── technique_deep.py     # P044 深度改写技法
│   │   ├── technique_original.py # P045 高度原创技法
│   │   ├── viewpoint_first.py    # P046 第一人称
│   │   └── viewpoint_third.py    # P047 第三人称
│   └── user/                 # 图文2号线提示词（你的方法论）
│       ├── surface.py            # 改表层（占位骨架）
│       ├── creative_surface.py   # 创意改表层（占位骨架）
│       ├── skeleton.py           # 改骨架（占位骨架）
│       └── original.py           # 原创（占位骨架）
├── data/
│   └── settings.json         # 用户填的 API Key（首次运行后产生）
├── Start074.cmd
└── README.md
```

## 扩展点（为以后预留）

1. **`prompts/user/`** —— 你把方法论直接填进对应文件，文件名固定就自动加载
2. **`prompts/story/`** —— STORY 出新版直接替换文件即可
3. **`data/`** —— 以后加历史记录/模板库/查重库都有地方

## 不做的事
- ❌ 不做封面、不出图、不配音、不出视频
- ❌ 不做反向查重
- ❌ 不做历史记录库
- ❌ 不接 071/072/073 数据
- ❌ 不动 071/072/073 任何文件
- ❌ 不读 071 的 API Key

## 端口
- 18801（不与 073 的 18773 冲突）

## 技术栈
- 后端：Python 标准库（http.server + urllib，无第三方依赖）
- 前端：原生 HTML/JS（无框架）
- 启动：双击 `Start074.cmd`
