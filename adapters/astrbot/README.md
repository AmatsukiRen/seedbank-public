# SeedBank → AstrBot 桥接插件

研发实现 0.0.1，尚未进行离线或真实平台验收；没有发布到插件市场。

将本目录放到 AstrBot 的 `data/plugins/seedbank_bridge/`，直接包含 `main.py`、`metadata.yaml`、`_conf_schema.json`。重载插件。AstrBot 与 SeedBank 必须在同机同一网络命名空间，默认 Docker / 远端部署不能直接访问这个仅监听 127.0.0.1 的入口。

1. 两个进程使用相同的、自己生成的随机 `SEEDBANK_ASTRBOT_TOKEN` 环境变量，之后重新打开它们。不要提交实际令牌。
2. 在 AstrBot 已连接的平台发送 `/seedid`；复制完整主人 ID 与会话 ID。
3. 在 SeedBank「设置 → 聊天渠道 → AstrBot」填主人 ID、需要的群会话白名单、令牌变量名和端口（默认 8791），保存并启动。
4. 使用 `/seed 想说的话`。先用独立人工生命包验收；模型请求可能计费。

插件只把该指令的文字交给 SeedBank，不调用 AstrBot 的模型，不导入人设或旧聊天。多词、换行文字会保留；最多 2000 字。`/seedid` 只展示平台 ID，不连接 SeedBank。若修改了 AstrBot 命令前缀，使用对应前缀。

私聊仅允许绑定的主人，群内需精确会话白名单；同一平台不要同时使用 SeedBank 原生连接和本插件，以免事件走两次。令牌代表信任此本地插件传入的平台身份，不是对互联网开放的用户认证 API。

失败或超时不自动重试：SeedBank 可能已经记录该次经历。桌面计数表示交给插件，不代表 AstrBot 最终发信成功。停用/卸载插件或停止 SeedBank 的 AstrBot 连接即可断开；它不会自动设置开机启动。

完整指南：[聊天渠道与身份范围](https://github.com/AmatsukiRen/seedbank-public/blob/main/docs/channels.md)。仓库当前仍为私有，仅协作者可访问。

源码按研发仓库 MIT 许可使用；AstrBot 本体和所接平台遵循各自许可与服务规则。
