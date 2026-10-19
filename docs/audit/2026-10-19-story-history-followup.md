# Story 中间版本及账户、市场：继续核查

## 本轮实际执行

1. 复用 `Settings-B8ihHphS.js → manual-url-DMK8uq8k.js → https://storybound.top/docs/ → 官方飞书教程`，按 lark-doc v2 只读重取版本章节。当前仍为修订 55，记录停在 1.24.5；教程的安装包已更新至 1.25.0，不代表版本记录也更新。
2. 追活跃入口 `Wt()` 的真实服务常量：主线路 `https://jihuo.52aibot.com`、软件内置备用 `https://api.joy1412.cn`。两条 `/v1/announcements?productId=storybound` 普通匿名读取均为 HTTP 403。没有使用用户身份、授权密钥或伪造设备指纹。
3. 官方站下载入口 `/dl/win` HEAD 跟随到 `https://dl.storybound.top/storybound/win-x64/1.25.0/setup.exe`。站点没有 robots/sitemap 历史索引（均404）；此前同一已确认路径下四个旧版安装包均404。公开搜索未发现中间版本说明，不能把搜索无结果当作未发行证明。
4. 新增离线检查用户已下载的 Mac 1.25.0 DMG（SHA-256 `9bcf3de104292b9737c6d0f9f956f08e6c2bfe6525bb57ac5d1146d8161d6cb3`），只解出 `Info.plist` 与 Mach-O 主程序到隔离目录，没有挂载、安装或运行软件。根据段表和格式6链式重定位读取静态资源，解出79个资源。活跃入口 `index-DUgGuLgF.js` 标识1.25.0，资源中未出现1.24.6–1.24.9字面量，也没有发行说明文件。入口通过 Node `--check` 静态语法检查，未执行脚本。

此前 Windows 包1952资源中保留1.24.6活跃入口，已证实该代码中的启动检查与下一个封面；1.24.7、1.24.8、1.24.9是否作为独立版本发行，当前仍没有来源证明。不能用四个版本号差值编造四份说明。

## 修正此前“三项全依赖服务端”的过度概括

| 能力 | 1.25.0客户端实际代码 | 074当前可确认状态 |
|---|---|---|
| 验证邮箱不再循环确认 | `E0` 保存最后邮箱和已验证邮箱；`Od` 仅在两者一致时作为绑定提示；`zp` 在明确验证成功时记为可信 | 074已有服务确认绑定后的后端持久化，重启继续发送同服务的绑定邮箱；没有同款循环弹窗。新增2项测试复验：重启保留、失败不记住、换服务清除。不是全部服务端逻辑 |
| 重装后设备唯一账户恢复 | 服务器响应携带 `fpExclusive`，客户端仅在没有既有身份且没拒绝过该邮箱时自动接受；普通恢复仍走确认 | 074已有服务明确 `bound:true,email` 的恢复，但未实现与Story完全相同的 `fpExclusive` 归属确认流程；需要明确的管理服务契约，不能在本地推断设备唯一账户 |
| 我的上架下载本机 | `Is` 请求 `/v1/market/detail` 得到本人可读payload，然后 `restoreOwnListing/ms` 按模板/封面/画风恢复；按内容去重，恢复为可继续编辑的本地作品 | 074现有市场是本地内容库，无远端上架列表和所有权服务。恢复内容、去重可以在本地实现，但不能凭空得到用户线上作品，也不能拿074本地导入冒充已经同步Story市场 |

账户相关新增2项与原管理服务10项隔离测试通过，全部mock，不读取正式账户配置，不发送验证码、不绑定、不请求余额、不发生交易。此处复验没有新增账户产品行为。

## 尚未完成

- 四个目标中间版本的完整官方说明仍未取得。
- 设备唯一账户恢复和本人远端上架下载没有真实上游验收，不能标成已补齐。
- 厂商服务端源码不在安装包中。后续实现须分别记录本地可复用逻辑与实际服务端返回条件，不能再把三项笼统归为纯服务端问题。

证据：`.desktop-tools/story1250-audit/manual-history-current.json`、`announcements-current-status.json`、`site-release-discovery.json`、`account-market-current-evidence.json`，及 `.desktop-tools/story1250-mac-audit/frontend/asset-manifest.json`、`history-scan.json`。以上搜索/拆解未打开Story或074原生窗口。
