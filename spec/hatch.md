# 孵化协议（Hatch Protocol）· v1.0

> 从一颗蛋到一个个体。同样输入，必须得到同样的结果。

## 输入

| 参数 | 必需 | 说明 |
|---|---|---|
| 蛋路径 | 是 | `<breed>.egg/` 目录 |
| 名字 | 是 | 个体名，用户起的，不改变物种身份 |
| 目标路径 | 是 | 生命包放在这，名字是 `<name>.life/` |
| `--seed` | 否 | 熵输入（字符串）。给了就可以复现同一个个体 |
| `--time` | 否 | 出生时间（ISO 8601）。未给则用当前时间 |
| 时钟 | 否 | 1.7.1 起固定按真实的一天走，出生证里保留 `clock` 字段只作历史记录 |

```bash
python tools/seed/seed.py hatch eggs/dafeiyu.egg ~/fish/小蓝.life
python tools/seed/seed.py hatch eggs/dafeiyu.egg /tmp/alpha.life --seed conformance-v1 --time 2026-01-01T00:00:00Z
```

## 步骤

1. **校验蛋**：必需文件齐全；`species.json` 的 `format` 为 `seedbank/seed@1`；`deps.lock`、`genome/traits.json` 可解析。
2. **计算蛋哈希**：对所有文件按路径排序后做 sha256。这是蛋的身份证。
3. **计算熵**：`seed = sha256("seedbank/v1:" + 熵输入)`。熵输入要么是用户给的 `--seed`，要么是 `uuid4 + 纳秒时间`。
   从 seed 派生确定性随机流（mulberry32）。
4. **抽特征**：从 `genome/traits.json` 的池子里无放回地抽 `pick` 个（默认 3），确定初始心情与体力。
5. **建目录**：在目标同级的临时目录里建好生命包（避免失败时留下半成品）。
6. **冻结那部分她**：复制 `genome/`、`world/`、`species.json`、`genesis.md`、`deps.lock` 进生命包。
7. **写出生证**：`birth.json`（见下）。
8. **写第 1 天**：`life/0001-<出生本机日期>.md`。内容是 genesis（作为当天的「今天」），且**这一天已经结束**：
   文件里已经含 `## 今天` 段与收尾心情。她还带着出生时就有的感官记录（`## 感知`：`- 光：光很亮，有点暖。`）。
   所以她第一次和你说话是**第 2 天**。
9. **初始化 mind/**：`self.md`、`traits.json`（抽中的特征）、`beliefs.md`、`mood.json`、`brain.json`（默认 stub）、
   `memory.json`（记忆卫生默认值）、`memories.jsonl`（第一条 = 出生记忆，`kind: feeling`，`runner: hatch`）。
10. **自检 + 原子落盘**：在临时目录上算哈希、写 `birth.json`，然后把临时目录 rename 成 `<name>.life/`。

## 出生证（birth.json）

```json
{
  "format": "seedbank/life@1",
  "name": "小蓝",
  "born_at": "2026-10-30T08:00:00Z",
  "local_date": "2026-10-30",
  "seed": "<64 位十六进制>",
  "species": { "id": "dafeiyu", "name": "大肥鱼", "version": "0.1.0" },
  "egg": { "id": "dafeiyu", "version": "0.1.0", "sha256": "<蛋的内容哈希>" },
  "deps": { "format": "seedbank/deps@1", "runtime": { "name": "python", "version": ">=3.10" }, "dependencies": [], "network_required": false },
  "requires": { "python": ">=3.10" },
  "genome": { "identity": "genome/identity.md", "values": "genome/values.md", "quirks": "genome/quirks.md", "traits": "genome/traits.json" },
  "genesis": { "file": "life/0001-2026-10-30.md", "day": 1 },
  "clock": "realtime",
  "hashes": { "pack": "<sha256>", "genome": "<sha256>", "deps": "<sha256>" },
  "ethics": "one-life-pack-one-fish",
  "birth_hash": "<上面全部字段规范化 JSON 的 sha256>"
}
```

- `deps.lock` 是**快照**：蛋可能消失，但生命包永远知道自己出生时依赖什么。
- `requires` 是 `deps.lock.runtime` 的展开，`check` 用它判断「依赖是否还可得」。
- `local_date` 是出生时刻在**本机时区**的日期，用于第 1 天的文件名；跨时区复现时请使用同一时区。

## 可复现性

```
seed       = sha256("seedbank/v1:" + 熵输入)
eggHash    = sha256(蛋的全部文件)
birthHash  = sha256(canonical(birth.json 去掉 birth_hash))
```

同样的 `seed + name + born_at + eggHash` → 同样的 `birthHash` → 同样的特征、心情、第一条记忆、第 1 天文件。

`check` 会重新计算这个 `birthHash` 并与出生证里的值比对：名字、种子、出生时间被改过都会被发现。
（`hashes.pack` 是出生那一刻整棵树的哈希，只作谱系记录——她活过之后树就会变，所以不能用来校验当前状态。）

> 随机只发生在两处：熵输入（用户可指定）和时间（用户可指定）。
> 其余一切都必须是确定的。

**协议向量**：`spec/vectors/hatch-dafeiyu.json` 记录了参考实现的标准结果
（`seed=conformance-v1`、`time=2026-01-01T00:00:00Z`、`name=alpha`）。任何实现都应与它逐字段一致；CI 每天验算一次。
蛋内内容或孵化逻辑变化导致哈希变化时，用 `python tools/seed/make_vector.py` 重新生成。

## 失败回滚

任何一步失败：删除临时目录、不写出生证、返回非零退出码。
**不允许出现"半条命"。**

## 与 CI 的关系

CI 每天用干净容器从蛋孵一条新鱼，跑 `check`、说话、走 3 天，再验算协议向量。
它回答的问题不是"她今天活着吗"，而是：

> **今天这颗蛋还能孵出来吗？**

## 版本记录

- v0.1：初稿。
- v1.0：`--seed` / `--time` 落地；`deps.lock` 快照与 `requires` 写入出生证；第 1 天闭合；协议向量；
  第 1 天自带 `## 感知`（新生儿的第一次光感，见 [senses.md](senses.md)）。
- v1.3：`mind/memory.json`（记忆卫生默认值）随生命包一起写入。
- v1.3.1（1.8.1）：名字允许中间带空格（首尾与中文标点仍拒绝）；孵化遇到非法路径时给中文错误而不是 traceback；`seed check` 同步变严格（见 [life-pack.md](life-pack.md) v0.8）。
