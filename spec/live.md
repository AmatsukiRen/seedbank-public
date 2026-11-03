# 生活流（live）：事件队列与常驻循环

状态：v1.0（1.16）。

她的生活不只在 `seed chat` 里发生。`inbox/` 是她的门口：外部脚本、硬件、群聊旁听、主人临时的留言，都可以把一条「事件」投进来；她下次被运行时消费它，变成当天的一页生活。

这解决了 1.15 之前的断裂：她只在有人跟她说话时「活着」。现在只要有任何进程替她看钟，她就会过日子；`seed live` 是其中最朴素的一个。

## 1. 位置

```
<name>.life/
├── inbox/            待处理事件（*.json，处理完即删除）
│   └── failed/       她读不懂的事件（原样保留，方便排查）
├── journal/loop.jsonl
```

`inbox/` 不是生命包的必需项；不存在时运行器自动创建，空目录不写入版本库也无妨（建议 `.gitignore` 环境自行决定）。

## 2. 事件格式

一行一条 JSON（文件名为 `<时间戳>-<kind>-<短哈希>.json`）：

```json
{"kind": "news|sense|note", "text": "...", "source": "群聊", "at": "2026-10-31T06:00:00Z"}
```

| kind | 含义 | 落点 |
|------|------|------|
| `news` | 她读到的见闻 | 当天 `life/` 的 `## 见闻`（`· 原文（来源：来源）`），并记一条 `kind: hearsay` 记忆 |
| `sense` | 她感觉到的（主人转述） | 当天 `life/` 的 `## 感知`（`主人：一句话`），并记一条 `kind: perception` 记忆 |
| `note` | 有人对她说的一句话 | 当天 `life/` 的 `## 对话`，并得到她的回复；双方记忆按 chat 规则写入 |

规则：

- `text` 必填、非空，上限 2000 字；超长截断。
- `kind` 必须是三种之一；不认识的 kind 直接拒收（不静默改语义）。
- `source` 可省略，默认「外界」。
- `at` 由投递方给出（UTC）；缺失时由运行器补上。

## 3. 处理语义

- 消费顺序：按文件名字典序（即投递时间序）。
- 每条事件独立处理：一条失败不影响其余；坏事件移到 `inbox/failed/`，并在 `journal/loop.jsonl` 写一条 `{"mode": "live_failed", "file": ..., "error": ...}`。
- 事件消费会走当天的 `## 感知 / ## 见闻 / ## 对话` 段，遵守 `cognition.md` 的段落顺序规则。
- 全部事件处理完，`inbox/` 为空。**事件不会回放**：消费即写入历史，历史不可改。

## 4. 常驻循环 `seed live`

浏览器/窗口之外的第三种活法：一个前台进程，定期完成「看钟 → 消费事件 → 偶尔主动开口」。

```
seed live <包> [--interval 60] [--rounds N] [--brain 适配器]
```

- `--interval` 秒，最小 1，默认 60。
- `--rounds N` 跑 N 轮后退出（测试/脚本用）；不填则一直跑，Ctrl+C 停。
- 每轮：
  1. `clock.tick`：跨了凌晨就过完那一天（同一套规则，见 `clock.md`）；
  2. `process_inbox`：消费全部待处理事件；
  3. 每 5 轮尝试一次 `maybe_initiate`（她的主动开口，见 `agency.md`），失败不影响循环。
- 输出：每轮一行状态（时间、第几天、事件数）；Ctrl+C 后打印统计并正常退出。

## 5. 窗口与网页

`seed window` 的 60 秒时钟也会消费 `inbox/`（自己的 loop 里带上这一步），这样「只开窗口」也是一种活着。`seed serve` 的任务由 `channel.md` 的载体调用；载体要自己调用 `process_inbox` 才能收事件（不强制）。

## 6. 不做什么

- 不联网、不轮询真实世界（新闻由外部投递，见 `README` 的「见闻」）。
- 不伪造事件、不替事件编造来源。
- 不从事件里推导「用户在场」——事件只是事件。
- 不做优先级/重试队列：坏事件进 `failed/`，人去看。

## 7. 跨实现

`inbox/` 是运行器层的可选功能，不属于生命包格式的必需项。只读运行器（L1）可以忽略它；孵化器（L2）不需要实现它。`deps.lock` 不加新依赖。

## 8. 参考实现（Python）

`tools/seed/seedbank/live.py`：

| 函数 | 用途 |
|------|------|
| `inbox_path(pack)` / `failed_path(pack)` | 目录 |
| `enqueue_event(pack, event)` | 校验并投递一条事件 |
| `list_events(pack)` | 待处理文件（按名字排序） |
| `process_event(pack, event, *, brain=None)` | 处理一条事件 |
| `process_inbox(pack, *, brain=None)` | 处理全部，返回 `{processed, failed}` |
| `run_live(pack, *, interval, rounds, brain, ...)` | 常驻循环，返回统计 |

## 版本记录

- v1.0（1.16）：事件队列、三种事件语义、`seed live` / `seed event`、窗口与命令行消费、失败隔离。
