# RunningHub 官方手册与 RH 币独立入口核查

日期：2026-10-25。状态：已读取官方材料，尚未实现新入口、提交生成或更改安装版。

## 读取来源

- 用户提供的[官方手册](https://runninghub.feishu.cn/wiki/Vc77w5EaUirOY5kyTQNcrr7GnUd)。通过 `lark-cli docs +fetch --api-version v2 --as user` 只读取得；文档 `LtXudAPtQoAFwvxpqVvcPasQnDh`，revision `3705`。
- 手册章节：`LRAadsIleoaIXFx57tncWA8RnPd`（RH 币与钱包）；`AjJIdZ2nsoeb2VxSflJcJI0Fnkd`（API 开放平台）；`Lr1sdfsRvo276CxMCt0cRKn2nZe`（ComfyUI 工作流）。
- [读取完整工作流 API JSON](https://www.runninghub.ai/runninghub-api-doc-en/api-425761094)。
- [提交 ComfyUI 工作流高级接口](https://www.runninghub.ai/runninghub-api-doc-en/api-425761093)。
- [查询账户资料](https://www.runninghub.ai/runninghub-api-doc-en/api-425761030)。
- [消费级会员 API](https://www.runninghub.ai/enterprise-api/consumerApi)。

## 已确认及对 074 的实际影响

1. 手册区分 RH 币运行开源模型/工作流和钱包调用闭源模型 API。不能把现有 G2 接口仅改一个计费字段，就声称改成扣 RH 币。
2. 走 RH 币应使用消费级会员 API Key，和现有 G2 的配置分开保存。新入口不默默读取、覆盖或更换原配置。
3. 工作流 API 与模型 API 是不同通道；工作流内若包含第三方收费 API 节点，仍可能另扣钱包。需要取得完整图，不能只看标题、模型名或可编辑节点列表就保证只扣币。
4. 手册要求网页先实际运行一次并正常出图，再对接 API。静态可读取、代码单元测试通过均不能替代这次实际验收。
5. 手册的 API 小节将应用与工作流流程合并简述。实现时使用接口参考中的精确路径与字段，不照抄简述路径。
6. 地区、账户、工作流 ID、Key 须一致；不自动切站，不使用旧 Key 尝试其他域名。

## 精确接口对应

| 目的 | POST 路径 | 关键内容 |
|---|---|---|
| 读取完整 API 图 | `/api/openapi/getJsonApiFormat` | `apiKey`、`workflowId`；返回 `data.prompt` JSON 字符串 |
| 提交工作流 | `/task/openapi/create` | `apiKey`、`workflowId`、`nodeInfoList`；可用 `workflow` 字符串提交固定完整图 |
| 查询原任务结果 | `/task/openapi/outputs` | `apiKey`、`taskId`；只查询，不另提交 |
| 核对账户 | `/uc/openapi/accountStatus` | 请求字段是小写 `apikey`；返回 `remainCoins`、`remainMoney`、`apiType` 等 |

高级提交文档明确支持 `workflow` 完整图覆盖。适合在审查完整图后固定该图提交，避免作者后来更换节点；仍须真实验证当前账户和平台是否支持。

## 工作流筛选进度

优先方向：原生 Qwen 文生图，适合中文场景描述。第一版只需要文生图和保存图片；不选带人脸细化、反推提示词、批量多风格、闭源 API 或隐藏节点的复杂流程。

| 候选 | 当前证据 | 尚欠什么 |
|---|---|---|
| [Qwen 文生图，Dr.生姜](https://www.runninghub.cn/post/1955160402595233794) | 国内站公开页面可读取；介绍为开源文生图，更新日 2026-03-20 | 取得完整图并核对节点、用户账户可访问性和网页实际单张运行 |
| [Qwen-Image ComfyUI 原生工作流](https://www.runninghub.cn/post/2027264283821744129) | 搜索得到原生 Qwen 文生图介绍 | 同上；不根据名称直接宣布通过 |
| [RH 官方 Qwen-Image 2.1 节点及示例](https://github.com/RH-RunningHub/ComfyUI-RH-Qwen-Image-2-1-diffusers) | 最小 API JSON 确实只有 `RH_QwenImage21Diffusers` 和 `SaveImage` 两节点 | 尚未确定一个当前平台中已经运行通过、与该示例一致的工作流 ID；不作为已接通默认项 |

国内站候选的同 ID 国际站页面未确认可访问，不宣称两站通用。未取得完整图前，只能叫候选，不能叫已验证的 RH 币通道。

## 本次边界

- 只读访问文档和公开页面；未打开 Story、074 主程序或安装包。
- 未读取/输出用户 RH Key，未发送账户私有 API 请求，未提交付费生成。
- 未改旧任务、现有图片、模型、计费配置或安装版。
- 先前封面初次提交的原始错误未留存；钱包不足仍是结合余额和账单的推断，不能倒推为已确认的平台原始报错。

后续独立入口设计见 `docs/superpowers/specs/2026-10-25-rh-coins-image-experiment-design.md`。
