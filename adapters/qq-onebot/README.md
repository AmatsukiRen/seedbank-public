# QQ 载体适配器（OneBot v11）

让 QQ 成为她的一扇窗。她不住在 QQ 里，也不住在服务器里——这个适配器只是把消息翻译成
[载体桥](../../spec/channel.md) 的 JSONL，再把她的回复翻译回一条 QQ 消息。

## 它遵守的三条规则

1. **适配器不直接写生命包**：它只会通过 `seed bridge` 说「她说了什么、感觉到了什么」。
2. **只有翻译后的文字进入生命包**：QQ 里的图片不会保存，只会经过她的感官变成一段文字和 8 位指纹。
3. **默认只听主人的**：私聊只回主人；群聊必须 **@ 她**，而且群要在白名单里（否则群里每句话都会吵到她）。

## 需要什么

- 一个 OneBot v11 实现（如 [NapCat](https://github.com/NapNeko/NapCatQQ)、Lagrange 等），它负责登录 QQ。
- 在 OneBot 实现里打开 **HTTP API**（默认 `http://127.0.0.1:3001`）。
- 在 OneBot 实现里配置 **HTTP 上报**（事件上报地址）到 `http://127.0.0.1:8790/`。

> ⚠️ 第三方 QQ 机器人有被风控的风险。建议用小号、只在朋友群里用；正式产品请走官方 QQ 机器人平台。
> 这个适配器是给「把大肥鱼接到自己 QQ 上」的那类需求做参考的，不是官方登录方案。

## 跑起来

```bash
# 1. 孵化（如果你还没有生命包）
python tools/seed/seed.py hatch eggs/dafeiyu.egg ~/fish/小蓝.life

# 2. 启动适配器（主人 QQ 号必填）
python adapters/qq-onebot/qq_onebot.py --pack ~/fish/小蓝.life --owner 123456789
# 想让她在群里也能被 @ 到：
python adapters/qq-onebot/qq_onebot.py --pack ~/fish/小蓝.life --owner 123456789 --groups 987654321,123123123

# 3. 先用一句话试试（不启动 OneBot 也能验证她在线）
python adapters/qq-onebot/qq_onebot.py --pack ~/fish/小蓝.life --owner 123456789 --once "你好呀"
```

配置也可以走环境变量：`SEEDBANK_PACK`、`SEEDBANK_OWNER`、`SEEDBANK_GROUPS`、
`SEEDBANK_ONEBOT_HTTP`、`SEEDBANK_ONEBOT_TOKEN`、`SEEDBANK_QQ_PORT`、`SEEDBANK_QQ_SELF_ID`。
Token 只从环境变量读，不写进任何文件。

## 想接别的 IM？

不需要改这个文件。任何语言、任何工具都可以直接接载体桥协议（见
[spec/channel.md](../../spec/channel.md)），或者参考 [docs/03-extending.md](../../docs/03-extending.md)
写一个新的适配器。桥的规则很短：一行 JSON 进，一行 JSON 出。

## 测试

```bash
python -m unittest discover -s adapters/qq-onebot -p "test_*.py" -v
```
