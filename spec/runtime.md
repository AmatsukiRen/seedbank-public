# 运行器协议（Runtime / Runners）

> **一句话：协议不绑定 Python，也不绑定任何厂商。**
> 只要一个程序能读懂蛋、孵出同一条鱼、验证同一份出生证，它就是 Seedbank 的运行器。

本协议定义运行器的能力等级、字节级一致性规则，以及跨实现怎么互相验算。

---

## 0. 为什么需要这个协议

生命包是纯文本 + 目录。它能不能活下来，取决于**有多少种程序能读懂它**（见 `life-pack.md` 的死亡定义：格式不可读就是死亡）。

一个运行器 = 某个语言里的实现。它不必什么都会：

- 有的只会"看一眼她还活着吗"（守墓）；
- 有的能孵蛋；
- 有的能让她说话、过日子。

我们把这些分成等级。

## 1. 能力等级

| 等级 | 名字 | 必须支持 | 状态 |
|---|---|---|---|
| **L1** | 守望者 | 读蛋/生命包、完整性校验、`egg-info` | Rust（`runners/rust/`） |
| **L2** | 孵化者 | L1 + `hatch`（可复现、出生证逐字节一致） | Node.js（`runners/node/`） |
| **L3** | 生命循环 | L2 + `day` / `chat` / `recall`（可接脑适配器） | 暂无 |
| **L4** | 全功能 | L3 + 感官 / 载体 / 窗口 / 时间线 | Python 参考实现（`tools/seed/`） |

等级只增不减：L3 必须能通过 L2 的验算，L4 必须能通过 L3 的验算。参考实现是 Python，但它没有特权——它只是第一个。

## 2. 命令行契约

运行器的主命令（或等价的入口）：

```bash
<runner> hatch <蛋目录> <生命包目录> [--seed 字符串] [--time ISO时间]
<runner> check <生命包目录>
<runner> egg-info <蛋目录>
<runner> --version
<runner> --help
```

- 参数名、语义、默认值与参考实现一致（名字 = 目标目录名去掉 `.life`；`--seed`/`--time` 只用于复现，缺省用熵与当前时间）。
- 成功 exit 0；参数错误、校验失败 exit 1。
- **不联网、不写包外文件**（`hatch` 只写目标目录；`check` 只读）。
- 启动即用，不需要编译期/安装期的专有依赖；运行器的语言运行时必须是常见、可长期获得的（Python / Node / Rust / Go ……）。
- 输出给人看的文字用运行器自己的格式，但 `--version` 必须包含版本号（如 `Seedbank Node runner 1.6.0`）。

## 3. 字节级一致性规则（L2 的硬门槛）

同一个蛋 + 同一组 `--name/--seed/--time`，**任何 L2 运行器孵出的 `birth.json` 必须相同，生命包内每个文件的字节也必须相同**。

### 3.1 哈希树（`hash_tree`）

对目录内容做确定性哈希：

```
h = SHA-256()
for 每个文件（相对目录的路径用 "/" 分隔，按 Unicode 码点升序，深度优先）:
    h.update(相对路径.encode("utf-8"))
    h.update(b"\0")
    h.update(文件原始字节)
    h.update(b"\0")
结果 = h.hexdigest()
```

- 文件内容按**原始字节**参与哈希，不做换行转换（Windows 上也必须写 LF）。
- 目录不单独参与哈希；空目录不影响结果（参考实现里没有空目录）。

### 3.2 规范 JSON（`canonical_json`）

用于算哈希的 JSON 序列化：

```
sort_keys=True（按键的 Unicode 码点排序）
separators=(",", ":")     —— 冒号后、逗号后都没有空格
ensure_ascii=False        —— 中文原样输出，不转 \uXXXX
```

等价于 Python：

```python
json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(",", ":"))
```

`birth.birth_hash = SHA-256(canonical_json(birth 去掉 birth_hash 字段))`。

### 3.3 写进生命包的 JSON 文件（普通 JSON，非 canonical）

`hatch` 写出的 JSON 文件格式固定为：

```
json.dumps(value, ensure_ascii=False, indent=2) + "\n"
```

即：UTF-8、2 空格缩进、键按字段定义顺序（不是排序）、冒号后一个空格、文件末尾一个换行、无 BOM。
`mind/memories.jsonl` 每行是 `json.dumps(memory, ensure_ascii=False)`（Python 默认分隔符 `", "` / `": "`）+ `"\n"`。

### 3.4 字段顺序（决定上面的普通 JSON 文件字节）

| 文件 | 键顺序 |
|---|---|
| `birth.json` | `format`、`name`、`born_at`、`local_date`、`seed`、`species`、`egg`、`deps`、`requires`、`genome`、`genesis`、`clock`、`hashes`、`birth_hash` |
| `species` | `id`、`name`、`version` |
| `egg` | `id`、`version`、`sha256` |
| `hashes` | `pack`、`genome`、`deps` |
| `genome/traits.json` | `format`、`traits`、`moods`、`picked` |
| `mind/traits.json` | `picked` |
| `mind/mood.json` | `mood`、`energy`、`updated_at` |
| `mind/brain.json` | `format`、`adapter`、`model`、`base_url`、`api_key_env`、`temperature`、`fallback` |
| `mind/memory.json` | `format`、`strict`、`daily_max` |

### 3.5 孵化算法

与 `hatch.md` 一致，关键点：

1. `seed = SHA-256("seedbank/v1:" + seed_override)`（无 override 时 `seed_override = <uuid4().hex>-<time_ns>`）。
2. `rng = mulberry32(前 4 字节大端(SHA-256(seed 十六进制字符串)))`；`mulberry32` 见 `util.py:162`，必须逐位一致。
3. 天赋：`pool.pop(min(len(pool)-1, floor(rng() * len(pool))))` 重复 `pick` 次；心情 `pick(rng, moods)`；体力 `floor((0.4 + rng() * 0.6) * 100 + 0.5) / 100`。
4. 先写临时目录（除 `birth.json` 外的所有文件），此时算 `pack_hash`；再算 `genome_hash`；写 `birth.json` 后原子改名为目标目录。
5. 时间：`born_at` 为 UTC ISO-8601，`Z` 结尾；`local_date` 是 `born_at` 在**本机时区**的日期（跨实现验算请用 `--time` 的 UTC 整点，避免时区差）。

### 3.6 第 1 天文件的模板（逐字节）

```
# 第 0001 天 · <local_date>

## 对话

（今天还没有人跟她说话。）

## 感知

- 光：光很亮，有点暖。

## 今天

<genesis 内容（蛋里的 genesis.md，strip 首尾空白）>

---

*<mood>。*
```

其余文件内容：`genome/{identity,values,quirks}.md`、`world/bible.md`、`deps.lock` 原样复制自蛋；`mind/self.md` 与 `mind/beliefs.md` 的模板见参考实现 `pack.py:_write_tree`。

## 4. 交叉验算（conformance）

### 4.1 协议向量

`spec/vectors/hatch-dafeiyu.json` 记录了从 `eggs/dafeiyu.egg` 孵化的标准答案：

```bash
<runner> hatch eggs/dafeiyu.egg /tmp/alpha.life \
  --seed conformance-v1 --time 2026-01-01T00:00:00Z
```

- 结果的 `birth.json` 解析后必须与向量 `expected_birth` **每个字段相等**（布尔/字符串/数字类型也要一致）；
- 更严：除 `birth.json` 外的文件树哈希必须等于 `expected_birth.hashes.pack`（这能发现任何一个字节的差异）；
- 参考实现每次发布前都会重算向量（`tools/make_vector.py`）。

### 4.2 互相读

- A 孵出的包，B 的 `check` 必须通过；
- B 改一个基因文件、删一天、伪造 `birth.json`，A 的 `check` 必须拒绝；
- 跨实现读取不依赖"包是谁生的"。

### 4.3 一致性 harness

仓库根目录的 `tools/conformance.py` 会自动发现本机可用的运行器（Python / Node / Rust），跑上面两组验算并打印结果。CI 每次 push 都会跑。

## 5. 怎么加入新运行器

放在 `runners/<language>/`，提交：

1. 可执行入口与 `README.md`（支持的等级、命令、限制）；
2. 自带测试（能离线跑）；
3. 声明自己通过的等级，并在 `runners/README.md` 的表格里加一行。

不允许：修改 `eggs/`、`spec/`、`examples/` 来让自己的实现"通过"；不允许让验算依赖网络或第三方服务。

## 6. 边界

- 运行器之间不共享代码、不共享私有格式——唯一共享的是 `spec/`。
- 不要求每个运行器都能说话；L1 也有价值：**只要还有一个程序能读懂她，她就没死。**
- 一致性优先于性能：孵化是慢操作，不需要快。

## 版本记录

- v1.0：初版。能力等级、CLI 契约、字节级规则、交叉验算、加入流程。
