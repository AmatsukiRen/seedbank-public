"""命令行入口 —— 把「孵化、说话、过一天、看一生」串起来。

设计原则：命令行是最低门槛的身体。任何能跑 Python 的机器，都能让她活过来。
"""

from __future__ import annotations

import json
import os
import sys
from pathlib import Path

from .i18n import t

from . import __version__
from .agency import add_boundary, add_interest, clear_boundaries, describe_agency
from .bonds import (
    add_event, add_promise, break_promise, describe_bonds,
    keep_promise as keep_promise_entry,
)
from .brain import ADAPTERS, create_brain
from .bridge import serve as bridge_serve
from .clock import describe_clock, load_clock, tick as clock_tick
from .memorial import (
    add_anniversary, add_farewell, add_regret, describe_memorial, resolve_regret,
)
from .inner import (
    correct_belief, describe_inner, set_silence, silence_state,
)
from .hands import add_reminder, describe_hands, mark_said, sweep_missed
from .live import enqueue_event, run_live
from .cognition import (
    build_context, chat_turn, compose_work, feed_news, forget_memory, list_memories, maybe_initiate,
    open_day, normalize_memory_writes, read_news_lines, recall, run_days, sense_media,
    legacy_letter, mourn, visit, perform_inner,
)
from .localmodels import PROBES as LOCAL_PROBES
from .localmodels import describe_local, discover as local_discover
from .localmodels import first_choice as local_first_choice, probe as local_probe
from .offline import describe_growth, grow as offline_grow
from .onboarding import (
    clean_name, config_path, create_fish, default_pack_parent, find_egg,
    describe_setup, load_config, resolve_pack, save_config,
)
from .pack import build_egg_info, check, hatch, print_check, print_hatch
from .persona import capture as persona_capture, check as persona_check, status as persona_status
from .settings import load_settings, open_pack_folder, save_settings, test_brain
from .timeline import write_timeline
from .works import describe_works, list_works, read_work
from .util import SeedError, append_memories, expand_home, list_days, now_iso, parse_time, round2
from .webui import serve as web_serve

USAGE = """Seedbank —— 一颗蛋，一条命。

用法：
  seed hatch <蛋目录> <生命包目录>
  seed check <生命包>
  seed backup <生命包> [--out 新备份.zip]
  seed backup-info <备份.zip>
  seed restore <备份.zip> <新生命包文件夹>
  seed recover <生命包>
  seed resume <生命包> <未完成请求编号> [--brain stub]
  seed day <生命包> [--days N] [--brain stub|openai-compatible|anthropic]
  seed chat <生命包> [--brain stub|openai-compatible|anthropic] [--once "一句话"]
  seed sense <生命包> [--image 图片] [--sound 声音文件] [--note 一句话]
                       # 看图是自动的：有视觉的脑时她自己看懂（--vision off 可显式跳过）
  seed feed <生命包> [--source 来源] [--file 文件] [--max N]
                       # 让她读一段见闻：文件或 stdin 里一行行摘要（也收 JSONL）
  seed news <生命包> [--day N]
                       # 她那天读到了什么（默认今天）
  seed recall <生命包> [--query 词] [--k N]
  seed semantic status|index|clear <生命包>
  seed facts list|timeline|date-detail|date|entity|add|resolve|forget|retract <生命包> [--query 文本] [--on YYYY-MM-DD] [--target 编号] [--audit] [--data-file JSON文件]
  seed learning list|plan|feedback|strategy|complete|practice <生命包> [--goal ID] [--data-file JSON文件]
  seed relationships list|person|note|issue|boundary|agreement|review|forget <生命包> [--person ID] [--data-file JSON文件]
  seed disclosure list|excerpt|profile|revoke <生命包> [--query 关键词] [--data-file JSON文件]
  seed life-story list|save|forget|export <生命包> [--query 关键词] [--data-file JSON文件] [--out 新文件]
                       # 查看、补充最多 64 个语义片段或清空当前模型缓存（保留原文）
  seed semantic configure <生命包> --model 名称 --base-url 地址 [--enabled=true]
                       # 配置可选嵌入服务；开启后查询和待索引片段会发送给它
  seed memories <生命包> [--day N] [--forgotten] [--history] [--json]
                       # 她的记忆：第几天、什么类型、有多重要
  seed forget <生命包> <记忆id> [--reason 说明]
                       # 忘记不是删除：留一句「我忘了」，历史还在
  seed memory-history <生命包> <记忆id>
                       # 查看这条记忆的来源、修订版本和未完成修改（JSON）
  seed revise <生命包> <记忆id> --text "新内容" --reason "理由"
              [--type correction|change] [--effective-on YYYY-MM-DD] [--request-id 编号]
                       # 显式用户修订，不调用模型；旧版本保留
  seed persona capture <生命包> [--brain 适配器]
                       # 保存固定档案样本，并调用已配置模型记录基线表现
  seed persona check <生命包> [--brain 适配器]
                       # 同样本检查来源、版本与事项状态；不是人格同一性证明
  seed persona status <生命包>
                       # 只读样本与报告摘要，不调用模型
  seed timeline <生命包> [--out 目录] [--title 标题]
  seed clock <生命包>
                       # 她的时间不需要设置：每过一个凌晨她过完一天
  seed tick <生命包> [--now ISO时间] [--brain 适配器]
                       # 手动推一格（脚本/测试用）：跨过凌晨就把那一天过完
  seed agency <生命包> [--interest 兴趣] [--boundary 不想聊的话题] [--clear-boundaries]
  seed agency <生命包> --history [--day 日页] [--limit 20] [--before 记录编号]
                       # 她的意愿：兴趣、边界、今天的计划、主动开口的记录
  seed development <生命包>
                       # 有来源的当前信念、偏好、长期目标和实际行动结果（JSON）
  seed initiate <生命包> [--now ISO时间] [--brain 适配器] [--force]
                       # 她主动先说一句（不用等她被叫）
  seed bond <生命包> [--thank 事] [--sorry 事] [--conflict 事] [--repair 事]
                       # 你们的关系：认识多久、多熟、还有哪些话没说开
  seed promise <生命包> "答应的事" [--due-day N]
  seed promise <生命包> --keep ID | --break ID [--note 备注]
                       # 承诺：她答应过什么、做到了没有
  seed memorial <生命包> [--anniversary 名字 [--day N] [--kind 生日|初见|自定义]]
                       [--regret 事] [--resolve N] [--farewell 名字 [--note 备注]]
                       [--day N]
                       # 有限性：记着的日子、遗憾、告别、睡过去的日子
  seed inner <生命包> [--silence on|off] [--note 原因]
                      [--dream] [--narrate] [--correct 以前的说法] [--now 现在的说法]
                      # 内在：沉默权、做一个梦、给自己写一段叙事、自我更正
  seed works <生命包> [--kind poem|letter|drawing] [--limit N]
                      # 她留下的作品：诗、信、字符画
  seed make <生命包> [--kind poem|letter|drawing] [--title 标题] [--brain 适配器]
                      # 让她现在写一样东西（诗 / 给主人的信 / 字符画）
  seed brain <生命包> [--set 适配器] [--model 模型] [--base-url 地址]
                       [--api-key-env 变量名] [--temperature 0.8]
                       [--strict|--no-strict] [--daily-max 8]
                       [--vision-model 模型] [--test] [--open-folder]
                       # 也可以直接改 mind/brain.json、mind/memory.json 与 mind/vision.json
  seed serve <生命包> [--port 8765] [--host 127.0.0.1] [--open]
                       # 网页窗口：说话、看东西、陪她过一天
  seed window <生命包> [--brain 适配器]
                       # 独立窗口：不打开浏览器、不需要网络，关掉她就停下
  seed bridge <生命包> [--brain 适配器]
                       # 载体桥：一行 JSON 进，一行 JSON 出，任何语言都能接
  seed qq [--pack <生命包>] --owner <QQ号> [--groups 群号,...]
          [--onebot-http http://127.0.0.1:3001] [--token <token>]
          [--port 8790] [--self-id <机器人QQ>] [--once "一句话"] [--test]
                       # 把 QQ 接进来（OneBot v11，需先跑 SnowLuma / NapCat / LLOneBot 之一）
  seed live <生命包> [--interval 60] [--rounds N] [--brain 适配器]
                       # 常驻循环：你不在也会看钟、收事件、偶尔先开口（Ctrl+C 停）
  seed event <生命包> --kind news|sense|note [--text 内容] [--source 来源]
                       # 往 inbox/ 投一条事件：她读到的 / 感觉到的 / 你留的一句话
  seed hands <生命包> [--done ID]
                       # 她替你记着的事：到期的、还没到期的、错过的
  seed remind <生命包> "要提醒的事" --due-on YYYY-MM-DD [--request-id ID]
  seed reminder-change <生命包> list|revise|cancel|cancel-pending [--id ID --expected HASH --reason 原因 --text 内容 --due-on YYYY-MM-DD --request-id ID]
                       # 让她记着：到第 N 天提醒你（今天 = 当前第几天）
  seed visit <生命包> --from <别的生命包> [--note "一句话"]
                       # 让别的鱼来串门：她回一句，来访记进 friends.json
  seed mourn <生命包> --friend <名字> [--letter "想说的话"]
                       # 一条鱼不见了：她送别它（写进告别与记忆）
  seed legacy <生命包> [--out <路径>]
                       # 给后来的人留一封信（默认 <包>/legacy/letter.md）
  seed start
                       # 打开上次那条鱼；还没有鱼就提示先领养一条
  seed setup [--name 名字] [--parent 目录] [--brain stub|local|anthropic|openai-compatible]
             [--model 模型] [--base-url 地址] [--api-key-env 变量名]
                       # 领养第一条鱼：起名字、选她住哪、选脑（不选就离线跑）
  seed local [--probe]
                       # 看看这台电脑上有没有能用的本地模型（Ollama / LM Studio / vLLM）
  seed grow <生命包>
                       # 离线时靠本机整理记忆：把反复在意的事变成「我相信…」
  seed egg-info <蛋目录>
  seed --version
  seed lifecycle <生命包> [status|pause|resume] [--note 说明 --expected 版本 --confirm]
                       # 保留完整档案的休眠与明确恢复；不会按寿命自动触发

例子：
  python tools/seed/seed.py hatch eggs/dafeiyu.egg ~/fish/小蓝.life
  python tools/seed/seed.py check ~/fish/小蓝.life
  python tools/seed/seed.py window ~/fish/小蓝.life
  python tools/seed/seed.py live ~/fish/小蓝.life --interval 60
  python tools/seed/seed.py chat ~/fish/小蓝.life
  python tools/seed/seed.py serve ~/fish/小蓝.life --open
  python tools/seed/seed.py sense ~/fish/小蓝.life --image 窗外的光.png --note 给你看
  echo "今天降温了，海边起风了。" | python tools/seed/seed.py feed ~/fish/小蓝.life --source 群聊
  python tools/seed/seed.py make ~/fish/小蓝.life --kind poem
  python tools/seed/seed.py news ~/fish/小蓝.life
  python tools/seed/seed.py brain ~/fish/小蓝.life --vision-model deepseek-flash
  python tools/seed/seed.py sense ~/fish/小蓝.life --image 窗外的光.png
  python tools/seed/seed.py day ~/fish/小蓝.life --days 7
  python tools/seed/seed.py setup --name 小蓝
  python tools/seed/seed.py local
  python tools/seed/seed.py grow ~/fish/小蓝.life
  python tools/seed/seed.py start
  python tools/seed/seed.py memories ~/fish/小蓝.life
  python tools/seed/seed.py forget ~/fish/小蓝.life m_0003_2 --reason 不重要了
  python tools/seed/seed.py persona check ~/fish/小蓝.life
  python tools/seed/seed.py clock ~/fish/小蓝.life
  python tools/seed/seed.py tick ~/fish/小蓝.life
  python tools/seed/seed.py timeline ~/fish/小蓝.life --out site

她的一生是一个文件夹。不联网也能活；换脑不换种。
"""


def _usage_text() -> str:
    """USAGE 按行翻译：中文原文逐行做 key，缺翻译时整段仍是中文。"""
    return "\n".join(t(line) for line in USAGE.splitlines())


def _init_locale() -> None:
    """按 环境变量 → 用户配置 → 系统语言 的顺序定一次界面语言。"""
    try:
        from .i18n import detect_locale, set_locale
    except Exception:
        return
    code = ""
    try:
        code = os.environ.get("SEEDBANK_LANG") or ""
    except Exception:
        code = ""
    if not code:
        try:
            from .onboarding import load_config

            code = str(load_config().get("language") or "")
        except Exception:
            code = ""
    try:
        set_locale(code or detect_locale())
    except Exception:
        pass


def _ensure_utf8_io() -> None:
    """Windows 上 stdout 被重定向时默认是 GBK，写中文/✓ 会崩。统一用 UTF-8。"""
    for stream in (sys.stdout, sys.stderr):
        try:
            stream.reconfigure(encoding="utf-8", errors="replace")
        except (AttributeError, ValueError):
            pass
    try:
        sys.stdin.reconfigure(encoding="utf-8", errors="replace")
    except (AttributeError, ValueError):
        pass


def _flags(args: list[str]) -> tuple[list[str], dict]:
    positional: list[str] = []
    flags: dict = {}

    def put(key: str, value) -> None:
        # 同一个参数写两次时收集成列表（例如 --boundary 海 --boundary 离开）
        if key in flags:
            current = flags[key]
            flags[key] = current + [value] if isinstance(current, list) else [current, value]
        else:
            flags[key] = value

    i = 0
    while i < len(args):
        arg = args[i]
        if arg.startswith("--"):
            if "=" in arg:
                key, value = arg[2:].split("=", 1)
                put(key, value)
            elif i + 1 < len(args) and not args[i + 1].startswith("--"):
                put(arg[2:], args[i + 1])
                i += 1
            else:
                put(arg[2:], True)
        else:
            positional.append(arg)
        i += 1
    return positional, flags


def _bool_flag(flags: dict, name: str, default: bool | None = None) -> bool | None:
    """把 --strict / --strict=true / --no-strict=true 这类写法都认下来。"""
    value = flags.get(name)
    if value is None:
        return default
    if value is True:
        return True
    if isinstance(value, str):
        text = value.strip().lower()
        if text in ("", "1", "true", "yes", "on"):
            return True
        if text in ("0", "false", "no", "off"):
            return False
        raise SeedError(t("--{value} 只认 true / false。", value=name))
    return bool(value)


def _flag_values(value) -> list[str]:
    """把 --x 值（可能是重复收集的列表）统一成字符串列表。"""
    if value is None or value is True:
        return []
    if isinstance(value, list):
        return [str(item) for item in value if item is not True]
    return [str(value)]


def _ensure_pack(pack_dir) -> None:
    """确认这是一个生命包（有出生证），否则给中文错误，而不是后面莫名退出 0。"""
    path = Path(expand_home(str(pack_dir)))
    if not (path / "birth.json").is_file():
        raise SeedError(t("没有这个生命包：{pack_dir}（先 seed hatch <蛋> <包> 孵一个）", pack_dir=pack_dir))
    from .pack_lock import writer
    with writer(path):
        pass


def _pack_name(pack_path: str) -> str:
    name = Path(pack_path).name
    return name[:-5] if name.endswith(".life") else name


def _tick_before_write(pack_dir) -> None:
    """写入口先看一次钟：跨了天就先闭合昨天，内容才会落到正确的一天。"""
    from .clock import tick

    tick(pack_dir)


def _cmd_hatch(args: list[str]) -> int:
    positional, flags = _flags(args)
    if len(positional) != 2:
        raise SeedError(t("用法：seed hatch <蛋目录> <生命包目录> [--seed 熵] [--time ISO时间]"))
    egg_dir, pack_dir = positional
    result = hatch(
        pack_dir,
        egg_dir,
        _pack_name(pack_dir),
        seed_override=str(flags["seed"]) if flags.get("seed") else None,
        born_at_override=str(flags["time"]) if flags.get("time") else None,
    )
    print_hatch(result)
    return 0


def _cmd_check(args: list[str]) -> int:
    positional, _ = _flags(args)
    if len(positional) != 1:
        raise SeedError(t("用法：seed check <生命包>"))
    result = check(positional[0])
    print_check(result)
    return 0 if result["runtime"]["ok"] else 1


def _cmd_day(args: list[str]) -> int:
    positional, flags = _flags(args)
    if len(positional) != 1:
        raise SeedError(t("用法：seed day <生命包> [--days N]"))
    pack_dir = positional[0]
    try:
        days = int(flags.get("days") or 1)
    except (TypeError, ValueError):
        raise SeedError(t("--days 要一个整数。")) from None
    if days < 1:
        raise SeedError(t("--days 至少是 1。"))
    brain = create_brain(pack_dir, str(flags.get("brain") or ""))
    result = run_days(pack_dir, days=days, brain=brain)
    name = json.loads((Path(expand_home(pack_dir)) / "birth.json").read_text(encoding="utf-8")).get("name")
    print(t("[seed] 过 {value} 天：{value_1}", value=len(result['days']), value_1=name))
    for day in result["days"]:
        print(t("      第 {day:04d} 天 · {date} · 心情：{mood}", day=day['day'], date=day['date'], mood=day['mood']))
        print(t("        记忆 +{memoriesAdded}（共 {totalMemories} 条）· 体力 {energy:.2f}", memoriesAdded=day['memoriesAdded'], totalMemories=day['totalMemories'], energy=day['energy']))
    # 离线（模板脑）时，让本机帮她整理一次：这是她「靠自己长大」的方式。
    if str(getattr(brain, "name", "")).startswith("stub"):
        entry = offline_grow(pack_dir)
        if entry:
            print(t("[seed] 离线长大了一点（第 {day} 天）：{value}", day=entry['day'], value=entry['text']))
    return 0


def _print_chat_turn(result: dict, name: str) -> None:
    print(t("\n她（第 {dayNo:04d} 天）：{reply}", dayNo=result['dayNo'], reply=result['reply']))
    if result["memoriesAdded"]:
        print(t("[seed] 记下了 {memoriesAdded} 条记忆 · 这一天的文件：{file}", memoriesAdded=result['memoriesAdded'], file=result['file']))


def _cmd_chat(args: list[str]) -> int:
    positional, flags = _flags(args)
    if len(positional) != 1:
        raise SeedError(t("用法：seed chat <生命包> [--once \"一句话\"]"))
    pack_dir = positional[0]
    brain = create_brain(pack_dir, str(flags.get("brain") or ""))
    # 她的一天就是真实的一天：聊天前先看钟，跨过凌晨就自动过完/开出新的一天。
    # 但时钟坏掉/配置缺 key 不该挡住说话（spec/clock.md：任何入口的时钟失败都不该挡住她）。
    try:
        clock_tick(pack_dir, brain)
    except Exception:  # noqa: BLE001 —— 时钟是辅助，不是门槛
        pass

    once = flags.get("once")
    if isinstance(once, str) and once:
        result = chat_turn(pack_dir, once, brain, request_id=str(flags.get("request-id") or ""))
        print(t("[seed] 你：{once}", once=once))
        _print_chat_turn(result, _pack_name(pack_dir))
        return 0
    if once is not None:
        raise SeedError(t("--once 后面要跟一句话。"))
    if flags.get("request-id"):
        raise SeedError("--request-id 需要和 --once 一起使用。")

    birth = json.loads((Path(expand_home(pack_dir)) / "birth.json").read_text(encoding="utf-8"))
    name = birth.get("name", "她")
    print(t("[seed] 你正在和「{value}」说话（脑：{value_1}）。输入「退出」结束。", value=name, value_1=brain.name))
    while True:
        try:
            text = input(t("\n你：")).strip()
        except (EOFError, KeyboardInterrupt):
            print(t("\n[seed] 再见。她记得你来过。"))
            return 0
        if text in ("退出", "quit", "exit"):
            print(t("[seed] 再见。她记得你来过。"))
            return 0
        if not text:
            continue
        result = chat_turn(pack_dir, text, brain)
        _print_chat_turn(result, name)


def _vision_line(settings: dict) -> str:
    """设置面板里那一行「看图：自动（模型）」（1.22 起不再有开关）。"""
    model = settings.get("vision_model") or t("跟随脑的模型")
    return t("      看图：自动（有视觉的脑时自己看懂；模型：{model}）", model=model)


def _cmd_sense(args: list[str]) -> int:
    positional, flags = _flags(args)
    if len(positional) != 1:
        raise SeedError(t("用法：seed sense <生命包> [--image 图片] [--sound 声音文件] [--note 一句话]"))
    pack_dir = positional[0]
    image = flags.get("image") if isinstance(flags.get("image"), str) else None
    sound = flags.get("sound") if isinstance(flags.get("sound"), str) else None
    note = flags.get("note") if isinstance(flags.get("note"), str) else None
    # 1.22：看图自动（有视觉的脑就自己看懂）；--vision off 可显式跳过，--vision 本身是兼容旧脚本。
    vision_flag = _bool_flag(flags, "vision")
    vision = None if vision_flag is None else bool(vision_flag)
    request_id = str(flags.get("request-id") or "")
    result = sense_media(pack_dir, image=image, sound=sound, note=note, vision=vision, request_id=request_id,
                         before_process=lambda: _tick_before_write(pack_dir))
    print(t("[seed] 今天的感知（第 {dayNo:04d} 天 · {date}）", dayNo=result['dayNo'], date=result['date']))
    for line in result["lines"]:
        print(f"      {line}")
    if result["memoriesAdded"]:
        print(t("[seed] 记下了 {memoriesAdded} 条记忆", memoriesAdded=result['memoriesAdded']))
    return 0


def _cmd_feed(args: list[str]) -> int:
    positional, flags = _flags(args)
    if len(positional) != 1:
        raise SeedError(t("用法：seed feed <生命包> [--source 来源] [--file 文件] [--max N]"))
    pack_dir = positional[0]
    _tick_before_write(pack_dir)
    source = str(flags.get("source") or "主人")
    path = flags.get("file") if isinstance(flags.get("file"), str) else ""
    if path:
        file = Path(expand_home(path))
        if not file.is_file():
            raise SeedError(t("没有这个文件：{value}", value=path))
        raw = file.read_text(encoding="utf-8")
    else:
        raw = sys.stdin.read()
    items: list = []
    for line in (raw.lstrip("\ufeff")).splitlines():
        line = line.strip().lstrip("\ufeff")
        if not line or line.startswith("#"):
            continue
        if line.startswith("{"):
            try:
                obj = json.loads(line)
            except json.JSONDecodeError:
                raise SeedError(t("这一行见闻的 JSON 坏了：{line}", line=line[:40])) from None
            if isinstance(obj, dict):
                items.append(obj)
                continue
        items.append({"text": line, "source": source})
    max_items = flags.get("max")
    if max_items is not None:
        try:
            limit = int(max_items)
        except (TypeError, ValueError):
            raise SeedError(t("--max 要一个整数。")) from None
        if limit < 1:
            raise SeedError(t("--max 至少是 1。"))
        items = items[:limit]
    result = feed_news(pack_dir, items, source=source)
    print(t("[seed] 今天的见闻（第 {dayNo:04d} 天 · {date}）", dayNo=result['dayNo'], date=result['date']))
    for line in result["lines"]:
        print(f"      · {line}")
    print(t("[seed] 记下了 {memoriesAdded} 条记忆（kind=hearsay：她读到的，不是她经历的）。", memoriesAdded=result['memoriesAdded']))
    return 0


def _cmd_news(args: list[str]) -> int:
    positional, flags = _flags(args)
    if len(positional) != 1:
        raise SeedError(t("用法：seed news <生命包> [--day N]"))
    pack_dir = positional[0]
    _ensure_pack(pack_dir)
    day_flag = flags.get("day")
    if day_flag is not None:
        try:
            day_no = int(day_flag)
        except (TypeError, ValueError):
            raise SeedError(t("--day 要一个整数。")) from None
    else:
        day_no = int(open_day(pack_dir)["dayNo"])
    date = _day_date_map(pack_dir).get(day_no, "")
    lines = read_news_lines(pack_dir, day_no)
    suffix = f"（{date}）" if date else ""
    print(t("[seed] 第 {day_no:04d} 天{suffix}读到的：", day_no=day_no, suffix=suffix))
    if not lines:
        print(t("      （这天她没读到什么。）"))
        return 0
    for line in lines:
        print(f"      · {line}")
    return 0


def _cmd_recall(args: list[str]) -> int:
    positional, flags = _flags(args)
    if len(positional) != 1:
        raise SeedError(t("用法：seed recall <生命包> [--query 词] [--k 5]"))
    try:
        k = int(flags.get("k") or 5)
    except (TypeError, ValueError):
        raise SeedError(t("--k 要一个整数。")) from None
    if k < 1:
        raise SeedError(t("--k 至少是 1。"))
    query = str(flags.get("query") or "")
    results = recall(positional[0], query, k)
    from .semantic import last_status
    if query:
        print("[seed] 检索方式：" + last_status(positional[0])["state"])
    print(t("[seed] 召回（查询：{value}）", value=query or t('（无，只看新近与重要）')))
    if not results:
        print("      没有找到匹配的可回忆记录；这不表示从未发生。")
        return 0
    for index, item in enumerate(results, 1):
        memory = item["memory"]
        text = str(memory.get("text", "")).replace("\n", " ")
        print(t("  {index}. [第 {value:04d} 天] {value_1}（{score:.2f}）", index=index, value=int(memory.get('day', 1)), value_1=text[:60], score=item['score']))
    return 0


_MEMORY_KIND_LABELS = {
    "conversation": "对话",
    "diary": "日记",
    "thought": "想法",
    "feeling": "心情",
    "correction": "纠正",
    "perception": "感知",
    "hearsay": "见闻",
    "forget": "忘记",
}


def _short_text(value, limit: int = 60) -> str:
    text = " ".join(str(value or "").split())
    return text if len(text) <= limit else text[: limit - 1] + "…"


def _fmt_number(value) -> str:
    try:
        number = round2(float(value))
    except (TypeError, ValueError):
        return "0"
    return f"{number:g}"


def _day_date_map(pack_dir) -> dict[int, str]:
    return {int(day["day"]): str(day["date"]) for day in list_days(pack_dir)}


def _cmd_memories(args: list[str]) -> int:
    positional, flags = _flags(args)
    if len(positional) != 1:
        raise SeedError("用法：seed memories <生命包> [--day N] [--forgotten] [--history] [--json]")
    pack_dir = positional[0]
    day_filter = None
    if flags.get("day") not in (None, ""):
        try:
            day_filter = int(flags["day"])
        except (TypeError, ValueError):
            raise SeedError(t("--day 要一个整数。")) from None
    only_forgotten = bool(flags.get("forgotten"))
    dates = _day_date_map(pack_dir)

    # 墓碑本身不是「记得的事」；--forgotten 看的是被墓碑指向的那些原记忆。
    entries = [m for m in list_memories(pack_dir) if m.get("kind") != "forget"]
    if day_filter is not None:
        entries = [m for m in entries if int(m.get("day", 0)) == day_filter]
    forgotten_count = sum(1 for m in entries if m.get("forgotten"))
    rows = [m for m in entries if bool(m.get("forgotten")) == only_forgotten]
    if not only_forgotten and not flags.get("history"):
        rows = [m for m in rows if m.get("recallable")]
    if flags.get("json"):
        print(json.dumps(rows, ensure_ascii=False, indent=2))
        return 0

    print(t("[seed] 她忘掉的事") if only_forgotten else t("[seed] 她的记忆"))
    if not rows:
        print(t("      （她还没有忘掉过什么。）") if only_forgotten else t("      （她还没有记得的事。）"))
    for memory in rows:
        state = "已放下" if memory.get("forgotten") else "已更正" if memory.get("superseded") else "当前版本" if memory.get("recallable") else "仅存档"
        print(f"      ID: {memory.get('id', '')} · {t(state)}")
        day_no = int(memory.get("day", 0))
        date = str(memory.get("date") or dates.get(day_no) or "")
        kind = str(memory.get("kind") or "")
        label = t(_MEMORY_KIND_LABELS.get(kind, kind or "记忆"))
        text = _short_text(memory.get("text"))
        importance = _fmt_number(memory.get("importance"))
        print(t("      第 {day_no} 天 · {date} · [{label}] {value}（重要度 {importance}）", day_no=day_no, date=date, label=label, value=text, importance=importance))
    print(t("      共 {value} 条（已忘记 {forgotten_count} 条）", value=len(entries), forgotten_count=forgotten_count))
    return 0


def _cmd_forget(args: list[str]) -> int:
    positional, flags = _flags(args)
    if len(positional) != 2:
        raise SeedError(t("用法：seed forget <生命包> <记忆id> [--reason 说明]"))
    pack_dir, memory_id = positional
    forget_memory(pack_dir, memory_id, reason=str(flags.get("reason") or ""))
    print(t("她忘掉了 {memory_id}", memory_id=memory_id))
    return 0


def _cmd_memory_history(args: list[str]) -> int:
    from .memory_editor import history
    positional, _ = _flags(args)
    if len(positional) != 2:
        raise SeedError("用法：seed memory-history <生命包> <记忆id>")
    print(json.dumps(history(*positional), ensure_ascii=False, indent=2))
    return 0


def _cmd_revise(args: list[str]) -> int:
    from .memory_editor import revise
    positional, flags = _flags(args)
    if len(positional) != 2 or not isinstance(flags.get("text"), str) or not isinstance(flags.get("reason"), str):
        raise SeedError('用法：seed revise <生命包> <记忆id> --text "新内容" --reason "理由" [--type correction|change]')
    result = revise(*positional, flags["text"], reason=flags["reason"],
                    change_type=str(flags.get("type") or "correction"),
                    effective_on=str(flags.get("effective-on") or ""), request_id=str(flags.get("request-id") or ""))
    print(json.dumps(result, ensure_ascii=False, indent=2))
    return 0


def _cmd_facts(args: list[str]) -> int:
    from .facts import listing, perform
    positional, flags = _flags(args)
    if len(positional) != 2:
        raise SeedError("用法：seed facts list|timeline|date-detail|date|entity|add|resolve|forget|retract <生命包> [--on YYYY-MM-DD] [--target 编号] [--data-file JSON文件]")
    action, pack = positional
    _ensure_pack(pack)
    if action == "date-detail":
        from .fact_dates import detail
        if set(flags) - {"target"} or not isinstance(flags.get("target"), str):
            raise SeedError("date-detail 需要 --target 说法或变化编号。")
        result = detail(pack, flags["target"])
    elif action == "timeline":
        from .fact_time import listing as time_listing
        if set(flags) - {"query", "on", "slot", "limit", "offset", "record-offset"}:
            raise SeedError("timeline 只接受 query / on / slot / limit / offset / record-offset。")
        result = time_listing(pack, str(flags.get("query") or ""), on=flags.get("on", ""),
                              slot=str(flags.get("slot") or ""), limit=int(flags.get("limit", 30)),
                              offset=int(flags.get("offset", 0)), record_offset=int(flags.get("record-offset", 0)))
    elif action == "list":
        if set(flags) - {"query", "audit", "limit", "offset"}:
            raise SeedError("list 只接受 query / audit / limit / offset。")
        result = listing(pack, str(flags.get("query") or ""), audit=_bool_flag(flags, "audit") if "audit" in flags else False,
                         limit=int(flags.get("limit", 100)), offset=int(flags.get("offset", 0)))
    else:
        if set(flags) - {"data-file", "request-id"} or not isinstance(flags.get("data-file"), str):
            raise SeedError("事实修改需要 --data-file JSON文件，可附 --request-id 请求编号。")
        try:
            data = json.loads(Path(flags["data-file"]).read_text(encoding="utf-8-sig"))
        except (OSError, ValueError) as error:
            raise SeedError("无法读取事实修改 JSON 文件。") from error
        if not isinstance(data, dict):
            raise SeedError("事实修改 JSON 必须是对象。")
        if action == "date":
            from .fact_dates import perform as amend
            result = amend(pack, data, request_id=str(flags.get("request-id") or ""))
        else:
            result = perform(pack, action, data, request_id=str(flags.get("request-id") or ""))
    print(json.dumps(result, ensure_ascii=False, indent=2))
    return 0


def _cmd_media(args: list[str]) -> int:
    from .bridge import Bridge
    positional, flags = _flags(args)
    if len(positional) != 2:
        raise SeedError("用法：seed media <list|detail|export|revisit|forget|resume|cancel> <生命包> [--asset-id 编号] [--request-id 请求编号]")
    action, pack = positional
    _ensure_pack(pack)
    allowed = {"request-id"} if action in ("resume", "cancel") else {"query", "offset", "limit"} if action == "list" else ({"asset-id"} if action in ("detail", "export")
              else {"asset-id", "note", "reason", "request-id"})
    if action not in ("list", "detail", "export", "revisit", "forget", "resume", "cancel") or set(flags) - allowed:
        raise SeedError("原始材料操作或参数不支持。")
    request = {"op": "media", "action": action}
    if action in ("resume", "cancel"):
        request.update(action=action + "_intake", request_id=str(flags.get("request-id") or ""))
    elif action == "list":
        request.update(query=str(flags.get("query") or ""), offset=int(flags.get("offset", 0)), limit=int(flags.get("limit", 30)))
    elif action in ("detail", "export"):
        request["asset_id"] = str(flags.get("asset-id") or "")
    else:
        request["data"] = {"asset_id": str(flags.get("asset-id") or ""), "note": str(flags.get("note") or ""),
                           "reason": str(flags.get("reason") or "")}
        request["request_id"] = str(flags.get("request-id") or "")
    result = Bridge(pack, "stub").handle(request)
    print(json.dumps(result, ensure_ascii=False, indent=2))
    return 0 if result.get("ok") else 1


def _cmd_life_story(args: list[str]) -> int:
    from .bridge import Bridge
    positional, flags = _flags(args)
    if len(positional) != 2:
        raise SeedError("用法：seed life-story <操作> <生命包> [--data-file JSON文件] [--out 新文件]")
    action, pack = positional
    _ensure_pack(pack)
    request = {"op": "life_story", "action": action}
    if action == "list":
        if set(flags) - {"query", "offset", "limit", "source-offset", "history"}:
            raise SeedError("list 只接受 query / offset / limit / source-offset / history。")
        request.update(query=str(flags.get("query") or ""), offset=int(flags.get("offset", 0)),
                       source_offset=int(flags.get("source-offset", 0)), limit=int(flags.get("limit", 30)),
                       history=_bool_flag(flags, "history") if "history" in flags else False)
    elif action == "export":
        if set(flags) - {"out"} or ("out" in flags and not isinstance(flags["out"], str)):
            raise SeedError("export 只接受 --out 新文件，不覆盖已有文件。")
        request["destination"] = flags.get("out")
    else:
        if set(flags) - {"data-file", "request-id"} or not isinstance(flags.get("data-file"), str):
            raise SeedError("人生回顾修改需要 --data-file JSON文件，可附 --request-id 请求编号。")
        try:
            request["data"] = json.loads(Path(flags["data-file"]).read_text(encoding="utf-8-sig"))
        except (OSError, ValueError) as error:
            raise SeedError("无法读取人生回顾 JSON 文件。") from error
        request["request_id"] = str(flags.get("request-id") or "")
    result = Bridge(pack, "stub").handle(request)
    print(json.dumps(result, ensure_ascii=False, indent=2))
    return 0 if result.get("ok") else 1


def _cmd_disclosure(args: list[str]) -> int:
    from .bridge import Bridge
    positional, flags = _flags(args)
    if len(positional) != 2:
        raise SeedError("用法：seed disclosure <操作> <生命包> [--query 关键词] [--data-file JSON文件]")
    action, pack = positional
    _ensure_pack(pack)
    request = {"op": "disclosure", "action": action}
    if action == "list":
        if set(flags) - {"query", "offset", "limit", "record-offset", "history"}:
            raise SeedError("list 只接受 query / offset / limit / record-offset / history。")
        request.update(query=str(flags.get("query") or ""), offset=int(flags.get("offset", 0)),
                       limit=int(flags.get("limit", 30)), record_offset=int(flags.get("record-offset", 0)),
                       history=_bool_flag(flags, "history") if "history" in flags else False)
    else:
        if set(flags) - {"data-file", "request-id"} or not isinstance(flags.get("data-file"), str):
            raise SeedError("分享修改需要 --data-file JSON文件，可附 --request-id 请求编号。")
        try:
            request["data"] = json.loads(Path(flags["data-file"]).read_text(encoding="utf-8-sig"))
        except (OSError, ValueError) as error:
            raise SeedError("无法读取分享修改 JSON 文件。") from error
        request["request_id"] = str(flags.get("request-id") or "")
    result = Bridge(pack, "stub").handle(request)
    print(json.dumps(result, ensure_ascii=False, indent=2))
    return 0 if result.get("ok") else 1


def _cmd_relationships(args: list[str]) -> int:
    from .bridge import Bridge
    positional, flags = _flags(args)
    if len(positional) != 2:
        raise SeedError("用法：seed relationships <操作> <生命包> [--person ID] [--data-file JSON文件]")
    action, pack = positional
    _ensure_pack(pack)
    request = {"op": "relationships", "action": action}
    if action == "list":
        if set(flags) - {"person", "offset", "limit", "history"}:
            raise SeedError("list 只接受 person / offset / limit / history。")
        request.update(person_id=str(flags.get("person") or "owner"), offset=int(flags.get("offset", 0)),
                       limit=int(flags.get("limit", 30)), history=_bool_flag(flags, "history") if "history" in flags else False)
    else:
        if set(flags) - {"data-file", "request-id"} or not isinstance(flags.get("data-file"), str):
            raise SeedError("关系修改需要 --data-file JSON文件，可附 --request-id 请求编号。")
        try:
            request["data"] = json.loads(Path(flags["data-file"]).read_text(encoding="utf-8-sig"))
        except (OSError, ValueError) as error:
            raise SeedError("无法读取关系修改 JSON 文件。") from error
        request["request_id"] = str(flags.get("request-id") or "")
    result = Bridge(pack, "stub").handle(request)
    print(json.dumps(result, ensure_ascii=False, indent=2))
    return 0 if result.get("ok") else 1


def _cmd_learning(args: list[str]) -> int:
    from .bridge import Bridge
    positional, flags = _flags(args)
    if len(positional) != 2:
        raise SeedError("用法：seed learning list|plan|feedback|strategy|complete|practice <生命包> [--data-file JSON文件]")
    action, pack = positional
    _ensure_pack(pack)
    request = {"op": "learning", "action": action}
    if action == "list":
        if set(flags) - {"goal", "offset", "limit"}:
            raise SeedError("list 只接受 goal / offset / limit。")
        request.update(goal_id=str(flags.get("goal") or ""), offset=int(flags.get("offset", 0)),
                       limit=int(flags.get("limit", 30)))
    else:
        if set(flags) - {"data-file", "request-id", "brain"} or not isinstance(flags.get("data-file"), str):
            raise SeedError("练习操作需要 --data-file JSON文件，可附 --request-id 和 --brain。")
        try:
            request["data"] = json.loads(Path(flags["data-file"]).read_text(encoding="utf-8-sig"))
        except (OSError, ValueError) as error:
            raise SeedError("无法读取练习操作 JSON 文件。") from error
        request["request_id"] = str(flags.get("request-id") or "")
    result = Bridge(pack, str(flags.get("brain") or "")).handle(request)
    print(json.dumps(result, ensure_ascii=False, indent=2))
    return 0 if result.get("ok") and result.get("succeeded") is not False else 1


def _cmd_semantic(args: list[str]) -> int:
    from .semantic import configure, manage
    positional, flags = _flags(args)
    if len(positional) != 2 or positional[0] not in ("configure", "status", "index", "clear"):
        raise SeedError("用法：seed semantic configure|status|index|clear <生命包>")
    action, pack = positional
    _ensure_pack(pack)
    if action == "configure":
        fields = {key.replace("-", "_"): value for key, value in flags.items() if key != "enabled"}
        if "enabled" in flags:
            fields["enabled"] = _bool_flag(flags, "enabled")
        result = configure(pack, fields)
    else:
        if flags:
            raise SeedError("语义配置参数只能用于 configure。")
        result = manage(pack, action)
    print(json.dumps(result, ensure_ascii=False, indent=2))
    return 0


def _cmd_persona(args: list[str]) -> int:
    positional, flags = _flags(args)
    if len(positional) != 2 or positional[0] not in ("capture", "check", "status"):
        raise SeedError("用法：seed persona capture|check|status <生命包> [--brain 适配器]")
    action, pack_dir = positional
    brain_override = str(flags.get("brain") or "")
    if "threshold" in flags:
        raise SeedError("不再使用文字相似度阈值，请移除 --threshold。")
    if action == "status":
        print(json.dumps(persona_status(pack_dir), ensure_ascii=False, indent=2))
        return 0
    if action == "capture":
        baseline = persona_capture(pack_dir, brain_override)
        print(f"[seed] 连续性样本已保存：{len(baseline['probes'])} 项，旧基线已归档（如存在）。")
        result = baseline["assessment"]
        print(f"基线评估：{result['status']} / {result.get('reason') or ('符合样本' if result['passed'] else '存在差异')}")
        print("只检查样本的读取与引用，不证明人格同一性。")
        return 0
    result = persona_check(pack_dir, brain_override)
    print(f"[seed] 连续性样本检查（基线 {result['captured_at']}）")
    for probe in result["probes"]:
        print(f"  {probe['id']}: {'符合样本' if probe['passed'] else '存在差异'}")
    uncovered = [k for k, v in result.get("coverage", {}).items() if v != "sampled"]
    print("未覆盖：" + (", ".join(uncovered) or "无；仍只代表有限样本"))
    print(f"报告：{Path(expand_home(pack_dir)) / result['report_file']}")
    if result["status"] != "assessed":
        print(f"未评估：{result['reason']}。不能作为模型能力通过。")
        return 2
    print(f"样本符合项：{result['correct']}/{result['total']}；不证明人格同一性。")
    return 0 if result["passed"] else 1


def _cmd_timeline(args: list[str]) -> int:
    positional, flags = _flags(args)
    if len(positional) != 1:
        raise SeedError(t("用法：seed timeline <生命包> [--out 目录] [--title 标题]"))
    pack_dir = positional[0]
    out = str(flags.get("out") or "site")
    title = str(flags.get("title") or "")
    result = write_timeline(pack_dir, out, title=title)
    print(t("[seed] 时间线已写好：{index}", index=result['index']))
    print(t("      天数：{days} · 记忆：{memories} 条", days=result['stats']['days'], memories=result['stats']['memories']))
    print(t("      用浏览器打开它，就是她的一生。"))
    return 0


def _cmd_clock(args: list[str]) -> int:
    positional, flags = _flags(args)
    if len(positional) != 1:
        raise SeedError(t("用法：seed clock <生命包>"))
    if flags:
        raise SeedError(t("seed clock 不接受参数：她的时间没有开关，固定按真实的一天走。"))
    _ensure_pack(positional[0])
    config = load_clock(positional[0])
    print(t("[seed] 她的时间：{value}", value=describe_clock(config)))
    print(t("      她的时间不需要设置：每过一个凌晨，她就过完一天。"))
    print(t("      恢复实际日期，不补写空档；期间经历未知。"))
    return 0


def _cmd_tick(args: list[str]) -> int:
    positional, flags = _flags(args)
    if len(positional) != 1:
        raise SeedError(t("用法：seed tick <生命包> [--now ISO时间] [--brain 适配器]"))
    pack_dir = positional[0]
    _ensure_pack(pack_dir)
    now = str(flags["now"]) if flags.get("now") else None
    if now:
        try:
            parse_time(now)
        except Exception:
            raise SeedError(t("看不懂这个时间：{now}（用 2026-10-31T06:00:00Z 这样的写法）", now=now)) from None
    brain = create_brain(pack_dir, str(flags.get("brain") or ""))
    result = clock_tick(pack_dir, brain, now=now)
    print(f"[seed] {result['reason']}")
    if result.get("day"):
        print(t("      第 {day} 天 · {date}", day=result['day'], date=result['date']))
    return 0


def _cmd_agency(args: list[str]) -> int:
    positional, flags = _flags(args)
    if len(positional) != 1:
        raise SeedError(
            t("用法：seed agency <生命包> [--interest 兴趣] [--boundary 不想聊的话题] [--clear-boundaries]")
        )
    pack_dir = positional[0]
    _ensure_pack(pack_dir)
    if _bool_flag(flags, "history"):
        if set(flags) - {"history", "day", "before", "limit"}:
            raise SeedError("查看计划历史不能同时修改兴趣或边界。")
        from .agency import plan_history
        print(json.dumps(plan_history(pack_dir, day=flags.get("day"), before=flags.get("before", ""),
                                      limit=flags.get("limit", 20)), ensure_ascii=False, indent=2))
        return 0
    if set(flags) & {"day", "before", "limit"}:
        raise SeedError("日页和分页参数需要与 --history 一起使用。")
    for raw in _flag_values(flags.get("interest")):
        topic = raw.strip()
        if not topic:
            raise SeedError(t("--interest 要一句话。"))
        add_interest(pack_dir, topic)
        print(t("[seed] 她记住了自己喜欢：{topic}", topic=topic))
    for raw in _flag_values(flags.get("boundary")):
        topic = raw.strip()
        if not topic:
            raise SeedError(t("--boundary 要一句话。"))
        add_boundary(pack_dir, topic)
        print(t("[seed] 她记住了一条边界：不聊「{topic}」", topic=topic))
    if _bool_flag(flags, "clear-boundaries"):
        clear_boundaries(pack_dir)
        print(t("[seed] 边界都清掉了。"))
    for line in describe_agency(pack_dir):
        print(line)
    return 0


def _cmd_initiate(args: list[str]) -> int:
    positional, flags = _flags(args)
    if len(positional) != 1:
        raise SeedError(t("用法：seed initiate <生命包> [--now ISO时间] [--brain 适配器] [--force]"))
    pack_dir = positional[0]
    _ensure_pack(pack_dir)
    now = str(flags["now"]) if flags.get("now") else None
    if now:
        try:
            parse_time(now)
        except Exception:
            raise SeedError(t("看不懂这个时间：{now}", now=now)) from None
    brain = create_brain(pack_dir, str(flags.get("brain") or ""))
    result = maybe_initiate(pack_dir, brain, now=now, force=bool(_bool_flag(flags, "force")))
    if not result:
        print(
            t(
                "[seed] 她这会儿不想开口。\n"
                "      想想：现在不在她醒着的时段（7~23 点）、今天已经开过口，或者她还没准备好。\n"
                "      想硬试一次可以加 --force。"
            )
        )
        return 0
    print(t("[seed] 她主动说了句（第 {dayNo} 天）：", dayNo=result['dayNo']))
    print(f"      「{result['reply']}」")
    print(t("      今天的计划：{value}", value=result.get('plan') or '（没有）'))
    print(t("      记下了 {memoriesAdded} 条想法。", memoriesAdded=result['memoriesAdded']))
    return 0


_BOND_FLAG_KINDS = {"thank": "thank", "sorry": "apology", "conflict": "conflict", "repair": "repair"}
_BOND_MEMORY = {
    "thank": ("feeling", 0.55, ["关系", "感谢"]),
    "apology": ("feeling", 0.6, ["关系", "道歉"]),
    "conflict": ("feeling", 0.65, ["关系", "争执"]),
    "repair": ("feeling", 0.6, ["关系", "和好"]),
}


def _write_bond_memory(pack_dir, text: str, *, kind: str, importance: float, tags: list[str]) -> int:
    day = open_day(pack_dir)
    writes = normalize_memory_writes(
        pack_dir,
        day_no=day["dayNo"],
        source="关系",
        runner="bond-v1",
        default_kind=kind,
        entries=[{"kind": kind, "text": text, "importance": importance, "tags": tags}],
        at=now_iso(),
    )
    append_memories(pack_dir, writes)
    return len(writes)


def _cmd_bond(args: list[str]) -> int:
    positional, flags = _flags(args)
    if len(positional) != 1:
        raise SeedError(
            t("用法：seed bond <生命包> [--thank 事] [--sorry 事] [--conflict 事] [--repair 事]")
        )
    pack_dir = positional[0]
    _ensure_pack(pack_dir)
    _tick_before_write(pack_dir)
    for flag, event_kind in _BOND_FLAG_KINDS.items():
        for raw in _flag_values(flags.get(flag)):
            text = raw.strip()
            if not text:
                raise SeedError(t("--{flag} 要一句话。", flag=flag))
            day = open_day(pack_dir)
            add_event(pack_dir, event_kind, text, day=day["dayNo"])
            mem_kind, importance, tags = _BOND_MEMORY[event_kind]
            _write_bond_memory(
                pack_dir,
                f"{_BOND_EVENT_LABELS[event_kind]}：{text}",
                kind=mem_kind,
                importance=importance,
                tags=tags,
            )
            print(t("[seed] 记下了一件事（{label}）：{value}", label=t(_BOND_EVENT_LABELS[event_kind]), value=text))
    for line in describe_bonds(pack_dir):
        print(line)
    return 0


_BOND_EVENT_LABELS = {"thank": "感谢", "apology": "道歉", "conflict": "争执", "repair": "和好"}


def _cmd_promise(args: list[str]) -> int:
    positional, flags = _flags(args)
    if not positional:
        raise SeedError(
            t(
                '用法：seed promise <生命包> "答应的事" [--due-day N]\n'
                "      seed promise <生命包> --keep ID | --break ID [--note 备注]"
            )
        )
    pack_dir = positional[0]
    _ensure_pack(pack_dir)
    _tick_before_write(pack_dir)
    keep_id = str(flags.get("keep") or "").strip()
    break_id = str(flags.get("break") or "").strip()
    if keep_id and break_id:
        raise SeedError(t("--keep 和 --break 只能选一个。"))
    if keep_id:
        item = keep_promise_entry(pack_dir, keep_id)
        _write_bond_memory(
            pack_dir,
            f"我把答应过的事做到了：{item['text']}",
            kind="thought",
            importance=0.7,
            tags=["承诺", "守约"],
        )
        print(t("[seed] 她做到了承诺 {id}：{value}", id=item['id'], value=item['text']))
    elif break_id:
        note = str(flags.get("note") or "").strip()
        item = break_promise(pack_dir, break_id, note=note)
        suffix = f"（{note}）" if note else ""
        _write_bond_memory(
            pack_dir,
            f"答应过的事没有做到：{item['text']}{suffix}",
            kind="feeling",
            importance=0.6,
            tags=["承诺", "失约"],
        )
        print(t("[seed] 记下了没做到的承诺 {id}：{value}", id=item['id'], value=item['text']))
    elif len(positional) >= 2:
        text = " ".join(positional[1:]).strip()
        due_day = None
        if flags.get("due-day") not in (None, ""):
            try:
                due_day = int(str(flags["due-day"]))
            except (TypeError, ValueError):
                raise SeedError(t("--due-day 要一个整数天号。")) from None
        day = open_day(pack_dir)
        item = add_promise(pack_dir, text, due_day=due_day, made_day=day["dayNo"])
        _write_bond_memory(
            pack_dir,
            f"我答应了：{item['text']}",
            kind="thought",
            importance=0.6,
            tags=[t("承诺")],
        )
        due = f"，第 {item['due_day']} 天到期" if item.get("due_day") else ""
        print(t("[seed] 她记住了承诺 {id}：{value}（第 {made_day} 天答应{due}）", id=item['id'], value=item['text'], made_day=item['made_day'], due=due))
    for line in describe_bonds(pack_dir):
        print(line)
    return 0


def _cmd_memorial(args: list[str]) -> int:
    positional, flags = _flags(args)
    if len(positional) != 1:
        raise SeedError(
            t(
                "用法：seed memorial <生命包> [--anniversary 名字 [--day N] [--kind 生日|初见|自定义]]\n"
                "      seed memorial <生命包> --regret 事 | --resolve N | --farewell 名字 [--note 备注] | --day N"
            )
        )
    pack_dir = positional[0]
    _ensure_pack(pack_dir)
    _tick_before_write(pack_dir)
    day = open_day(pack_dir)["dayNo"]
    if flags.get("day") not in (None, ""):
        try:
            day = int(str(flags["day"]))
        except (TypeError, ValueError):
            raise SeedError(t("--day 要一个整数天号。")) from None
    changed = False
    if flags.get("anniversary"):
        name = str(flags["anniversary"]).strip()
        kind = str(flags.get("kind") or "custom").strip()
        if kind in ("生日", "birthday"):
            kind = "birthday"
        elif kind in ("初见", "第一次见面", "meet"):
            kind = "first-meet"
        note = str(flags.get("note") or "").strip()
        item = add_anniversary(pack_dir, name, day=day, kind=kind, note=note)
        _write_bond_memory(
            pack_dir,
            f"我把这个日子记住了：{item['name']}",
            kind="thought",
            importance=0.6,
            tags=["纪念日"],
        )
        print(t("[seed] 她记住了这个日子：{value}（第 {day} 天）", value=item['name'], day=item['day']))
        changed = True
    if flags.get("regret"):
        text = str(flags["regret"]).strip()
        item = add_regret(pack_dir, text, day=day)
        _write_bond_memory(
            pack_dir,
            f"有件事我一直没放下：{item['text']}",
            kind="feeling",
            importance=0.55,
            tags=["遗憾"],
        )
        print(t("[seed] 她记下了一件遗憾：{value}", value=item['text']))
        changed = True
    if flags.get("resolve") not in (None, ""):
        try:
            index = int(str(flags["resolve"]))
        except (TypeError, ValueError):
            raise SeedError(t("--resolve 要一个整数序号（从 1 开始）。")) from None
        item = resolve_regret(pack_dir, index, day=day)
        print(t("[seed] 她放下了第 {index} 条遗憾：{value}", index=index, value=item['text']))
        changed = True
    if flags.get("farewell"):
        name = str(flags["farewell"]).strip()
        kind = str(flags.get("kind") or "goodbye").strip()
        note = str(flags.get("note") or "").strip()
        item = add_farewell(pack_dir, name, kind=kind, note=note, day=day)
        _write_bond_memory(
            pack_dir,
            f"我和{name}告别了。" + (f"（{note}）" if note else ""),
            kind="feeling",
            importance=0.7,
            tags=["告别"],
        )
        print(t("[seed] 她记下了一次告别：{value}（第 {day} 天，{kind}）", value=item['name'], day=item['day'], kind=item['kind']))
        changed = True
    _ = changed
    for line in describe_memorial(pack_dir, day):
        print(line)
    return 0


def _cmd_inner(args: list[str]) -> int:
    from .desktop.text import t as inner_text
    failed = False
    positional, flags = _flags(args)
    if len(positional) != 1:
        raise SeedError(
            t(
                "用法：seed inner <生命包> [--silence on|off] [--note 原因]\n"
                "      seed inner <生命包> --dream | --narrate | --correct 以前的说法 --now 现在的说法"
            )
        )
    pack_dir = positional[0]
    _ensure_pack(pack_dir)
    _tick_before_write(pack_dir)
    day = open_day(pack_dir)
    changed = False
    if flags.get("silence") is not None:
        value = str(flags["silence"]).strip().lower()
        if value not in ("on", "off", "true", "false", "1", "0"):
            raise SeedError(t("--silence 只认 on / off。"))
        on = value in ("on", "true", "1")
        note = str(flags.get("note") or "").strip()
        set_silence(pack_dir, on, note=note, day=day["dayNo"])
        _write_bond_memory(
            pack_dir,
            "今天我决定少说一点。" if on else "今天我愿意多说一点。",
            kind="feeling",
            importance=0.5,
            tags=["沉默权"],
        )
        print(t("[seed] 沉默权已打开（第 {dayNo} 天）。", dayNo=day['dayNo']) if on else t("[seed] 沉默权已关掉（第 {dayNo} 天）。", dayNo=day['dayNo']))
        if on and note:
            print(t("      她的说法：{note}", note=note))
        changed = True
    if flags.get("dream"):
        ctx = build_context(pack_dir, day["dayNo"], day["date"])
        brain = create_brain(pack_dir)
        entry = perform_inner(pack_dir, ctx, brain, day, "dream")
        from .inner_attempts import display_lines
        print("\n".join(display_lines(entry["receipt"]["data"])))
        if entry["succeeded"]:
            print(inner_text("已保存梦的记录（第 {day} 页）：{text}", day=entry['day'], text=entry['text']))
        else:
            failed = True
        changed = True
    if flags.get("narrate"):
        ctx = build_context(pack_dir, day["dayNo"], day["date"])
        brain = create_brain(pack_dir)
        written = perform_inner(pack_dir, ctx, brain, day, "narrative")
        from .inner_attempts import display_lines
        print("\n".join(display_lines(written["receipt"]["data"])))
        if written["succeeded"]:
            print(inner_text("已保存自我叙述：{text}", text=written['text']))
        else:
            failed = True
        changed = True
    if flags.get("correct"):
        old = str(flags["correct"]).strip()
        new = str(flags.get("now") or "").strip()
        if not new:
            raise SeedError(t("--correct 需要配一个 --now「现在的说法」。"))
        entry = correct_belief(pack_dir, old, new, day=day["dayNo"])
        print(inner_text("已保存用户补充的更正：{old} → {new}", old=old, new=new))
        changed = True
    _ = changed
    print(describe_inner(pack_dir))
    return 1 if failed else 0


def _cmd_live(args: list[str]) -> int:
    positional, flags = _flags(args)
    if len(positional) != 1:
        raise SeedError(t("用法：seed live <生命包> [--interval 秒] [--rounds N] [--brain 适配器]"))
    pack_dir = positional[0]
    _ensure_pack(pack_dir)
    try:
        interval = float(flags.get("interval", 60))
    except (TypeError, ValueError):
        raise SeedError(t("--interval 要一个数字（秒）")) from None
    rounds = flags.get("rounds")
    if rounds is not None:
        try:
            rounds = int(rounds)
        except (TypeError, ValueError):
            raise SeedError(t("--rounds 要一个整数")) from None
    if interval < 1:
        raise SeedError(t("--interval 至少 1 秒（她的日子按天走，太快没有意义）"))
    if rounds is not None and rounds < 0:
        raise SeedError(t("--rounds 不能是负数"))
    brain = create_brain(pack_dir, str(flags.get("brain") or ""))
    print(t("[seed] 她的常驻循环开始了。Ctrl+C 停。"))
    stats = run_live(pack_dir, interval=interval, rounds=rounds, brain=brain)
    print(
        t(
            "[seed] 循环结束：{rounds} 轮，新的一天 {days} 次，事件 {events} 条，"
            "坏事件 {failed} 条，主动开口 {initiated} 次。",
            rounds=stats["rounds"],
            days=stats["days"],
            events=stats["events"],
            failed=stats["failed"],
            initiated=stats["initiated"],
        )
    )
    return 0


def _cmd_event(args: list[str]) -> int:
    positional, flags = _flags(args)
    if len(positional) != 1:
        raise SeedError(t("用法：seed event <生命包> --kind news|sense|note [--text 内容] [--source 来源]"))
    pack_dir = positional[0]
    _ensure_pack(pack_dir)
    kind = str(flags.get("kind") or "news").strip().lower()
    text = flags.get("text")
    if isinstance(text, list):
        text = " ".join(str(item) for item in text)
    text = str(text or "").strip()
    if not text:
        text = sys.stdin.read().strip()
    if not text:
        raise SeedError(t("事件要有内容：--text 一句话，或者用 stdin 喂一行"))
    path = enqueue_event(
        pack_dir,
        {"kind": kind, "text": text, "source": str(flags.get("source") or "外界")},
    )
    print(t("[seed] 事件放进队列了：{value}（等 seed live 或她下次看钟时消费）", value=path.name))
    return 0


def _cmd_hands(args: list[str]) -> int:
    positional, flags = _flags(args)
    if len(positional) != 1:
        raise SeedError(t("用法：seed hands <生命包> [--done ID]"))
    pack_dir = positional[0]
    _ensure_pack(pack_dir)
    _tick_before_write(pack_dir)
    done = flags.get("done")
    day = open_day(pack_dir)["dayNo"]
    if done:
        reminder = None
        for item in describe_hand_list(pack_dir):
            if item["id"] == str(done):
                reminder = item
                break
        if reminder is None:
            raise SeedError(t("没找到这条提醒：{done}", done=done))
        mark_said(pack_dir, str(done), day)
        print(t("[seed] 提醒过了：{value}", value=reminder['text']))
        return 0
    sweep_missed(pack_dir, day)
    print(describe_hands(pack_dir, day))
    return 0


def describe_hand_list(pack_dir) -> list:
    from .hands import list_reminders

    return list_reminders(pack_dir)


def _cmd_reminder_change(args: list[str]) -> int:
    from .reminder_changes import listing, perform
    from .pack_lock import writer
    positional, flags = _flags(args)
    if len(positional) != 2:
        raise SeedError("用法：seed reminder-change <生命包> list|revise|cancel|cancel-pending")
    pack, action = positional
    _ensure_pack(pack)
    if action == "list":
        with writer(pack):
            result = {"reminders": listing(pack)}
    elif action == "cancel-pending":
        from .hands import cancel_pending
        result = cancel_pending(pack, str(flags.get("request-id") or ""))
    else:
        result = perform(pack, action, {"reminder_id": flags.get("id"), "expected": flags.get("expected"),
                         "reason": flags.get("reason"), "text": flags.get("text"), "due_on": flags.get("due-on")},
                         request_id=str(flags.get("request-id") or ""))
    print(json.dumps(result, ensure_ascii=False))
    return 0


def _cmd_remind(args: list[str]) -> int:
    positional, flags = _flags(args)
    if len(positional) != 2:
        raise SeedError("用法：seed remind <生命包> \"要提醒的事\" --due-on YYYY-MM-DD；旧日页期限可用 --due-day N。")
    pack_dir, text = positional[0], positional[1]
    _ensure_pack(pack_dir)
    due_day = flags.get("due-day")
    if "due-on" in flags:
        from .hands import schedule
        if due_day is not None:
            raise SeedError("日历日期与旧日页期限不能同时填写。")
        result = schedule(pack_dir, {"text": text, "due_on": flags["due-on"]}, request_id=str(flags.get("request-id") or ""))
        print(json.dumps(result, ensure_ascii=False))
        return 0
    if due_day is None:
        raise SeedError("请填写 --due-on YYYY-MM-DD；旧日页期限使用 --due-day N。")
    try:
        due = int(due_day)
    except (TypeError, ValueError):
        raise SeedError(t("--due-day 要一个整数天数")) from None
    reminder = add_reminder(pack_dir, text, due)
    print(t("[seed] 她记下了：第 {due_day} 天提醒你「{value}」（{id}）", due_day=reminder['due_day'], value=reminder['text'], id=reminder['id']))
    return 0


def _cmd_visit(args: list[str]) -> int:
    positional, flags = _flags(args)
    if len(positional) != 1:
        raise SeedError(t("用法：seed visit <生命包> --from <别的生命包> [--note \"一句话\"]"))
    pack_dir = positional[0]
    _ensure_pack(pack_dir)
    other = flags.get("from")
    if not other:
        raise SeedError(t("要写 --from（另一条鱼的生命包）"))
    result = visit(pack_dir, expand_home(other), note=str(flags.get("note") or ""))
    print(t("[seed] {guest} 来看她了（第 {dayNo} 天，来过 {visits} 次）", guest=result['guest'], dayNo=result['dayNo'], visits=result['visits']))
    print(t("她：{reply}", reply=result['reply']))
    return 0


def _cmd_mourn(args: list[str]) -> int:
    positional, flags = _flags(args)
    if len(positional) != 1:
        raise SeedError(t("用法：seed mourn <生命包> --friend <名字> [--letter \"想说的话\"]"))
    pack_dir = positional[0]
    _ensure_pack(pack_dir)
    friend = flags.get("friend")
    if not friend:
        raise SeedError(t("要写 --friend（不见了的鱼的名字）"))
    result = mourn(pack_dir, str(friend), letter=str(flags.get("letter") or ""))
    print(t("[seed] 她送别了 {friend}（第 {dayNo} 天），记下了 {memoriesAdded} 条记忆。", friend=result['friend'], dayNo=result['dayNo'], memoriesAdded=result['memoriesAdded']))
    return 0


def _cmd_legacy(args: list[str]) -> int:
    positional, flags = _flags(args)
    if len(positional) != 1:
        raise SeedError(t("用法：seed legacy <生命包> [--out <路径>]"))
    pack_dir = positional[0]
    _ensure_pack(pack_dir)
    out = flags.get("out")
    result = legacy_letter(pack_dir, out=expand_home(out) if out else None)
    print(t("[seed] 已导出私人档案摘要：{value}（已保存 {days} 个日页）", value=result['path'], days=result['days']))
    return 0


def _cmd_brain(args: list[str]) -> int:
    positional, flags = _flags(args)
    if len(positional) != 1:
        raise SeedError(t("用法：seed brain <生命包> [--set 适配器] ... [--strict|--no-strict] [--daily-max N] [--test]"))
    pack_dir = positional[0]
    patch = {}
    if flags.get("set"):
        adapter = str(flags["set"])
        if adapter not in ADAPTERS:
            raise SeedError(t("不认识的脑适配器：{adapter}（可选：{join}）", adapter=adapter, join=' / '.join(ADAPTERS)))
        patch["adapter"] = adapter
    for key in ("model", "base-url", "api-key-env"):
        if flags.get(key):
            patch["base_url" if key == "base-url" else key.replace("-", "_")] = str(flags[key])
    if flags.get("input-budget"):
        try:
            patch["input_budget"] = int(flags["input-budget"])
        except (ValueError, TypeError):
            raise SeedError("--input-budget 要一个整数。") from None
    if flags.get("temperature"):
        try:
            patch["temperature"] = float(flags["temperature"])
        except ValueError:
            raise SeedError(t("--temperature 要一个数字。")) from None
    strict_flag = _bool_flag(flags, "strict")
    no_strict_flag = _bool_flag(flags, "no-strict")
    if strict_flag is not None or no_strict_flag is not None:
        patch["strict"] = bool(strict_flag) if strict_flag is not None else not bool(no_strict_flag)
    if flags.get("daily-max"):
        try:
            patch["daily_max"] = int(flags["daily-max"])
        except (TypeError, ValueError):
            raise SeedError(t("--daily-max 要一个整数。")) from None
    # 1.22：--vision 开关已废弃，仍接受但不影响（兼容旧脚本）。
    if flags.get("vision-model") is not None:
        value = flags["vision-model"]
        if not isinstance(value, str) or not value.strip():
            raise SeedError(t("--vision-model 要一个模型名（例如 deepseek-flash）。"))
        patch["vision_model"] = value.strip()
    if flags.get("vision-max-side") is not None:
        try:
            patch["vision_max_side"] = int(flags["vision-max-side"])
        except (TypeError, ValueError):
            raise SeedError(t("--vision-max-side 要一个整数。")) from None
    _ensure_pack(pack_dir)
    saved = None
    if patch:
        saved = save_settings(pack_dir, patch)
        print(t("[seed] 脑已改为：{describe}", describe=saved['describe']))
        if {"vision_enabled", "vision_model", "vision_max_side"} & set(patch):
            print(_vision_line(saved))
    if flags.get("test"):
        ok, message = test_brain(pack_dir)
        print(t("[seed] 测试连接：{value}{message}", value='✓ ' if ok else '✗ ', message=message))
        return 0 if ok else 1
    if flags.get("open-folder"):
        open_pack_folder(pack_dir)
        print(t("[seed] 已打开：{pack_dir}", pack_dir=pack_dir))
        return 0
    if saved is not None:
        return 0
    settings = load_settings(pack_dir)
    strict_word = t("严格（去重、丢空话）") if settings.get("strict", True) else t("宽松")
    print(t("[seed] 当前脑：{describe}", describe=settings['describe']))
    print(t("      记忆卫生：{strict_word} · 每轮最多 {daily_max} 条", strict_word=strict_word, daily_max=settings.get('daily_max', 8)))
    print(_vision_line(settings))
    print(t("      改设置：seed brain <生命包> --set anthropic --model deepseek-flash "
            "--base-url https://api.deepseek.com/anthropic --api-key-env DEEPSEEK_API_KEY"))
    print(t("      换视觉模型：seed brain <生命包> --vision-model 模型"))
    return 0


def _cmd_egg_info(args: list[str]) -> int:
    positional, _ = _flags(args)
    if len(positional) != 1:
        raise SeedError(t("用法：seed egg-info <蛋目录>"))
    print(json.dumps(build_egg_info(positional[0]), ensure_ascii=False, indent=2))
    return 0


def _cmd_bridge(args: list[str]) -> int:
    positional, flags = _flags(args)
    if len(positional) != 1:
        raise SeedError(t("用法：seed bridge <生命包> [--brain 适配器]"))
    return bridge_serve(positional[0], str(flags.get("brain") or ""))


def _cmd_serve(args: list[str]) -> int:
    positional, flags = _flags(args)
    if len(positional) != 1:
        raise SeedError(t("用法：seed serve <生命包> [--port 8765] [--host 127.0.0.1] [--open]"))
    try:
        port = int(flags["port"]) if "port" in flags else 8765
    except (TypeError, ValueError):
        raise SeedError(t("--port 要一个整数。")) from None
    return web_serve(
        positional[0],
        host=str(flags.get("host") or "127.0.0.1"),
        port=port,
        open_browser=bool(flags.get("open")),
        brain_override=str(flags.get("brain") or ""),
    )


def _cmd_setup(args: list[str]) -> int:
    """领养第一条鱼：孵蛋 + 起名字 + 选脑。"""
    _, flags = _flags(args)
    name = str(flags.get("name") or "").strip()
    if not name:
        raise SeedError(
            t(
                "请给她起个名字：seed setup --name 小蓝 "
                "（可选 --parent 目录 / --brain stub|local|anthropic|openai-compatible）"
            )
        )
    clean = clean_name(name)
    parent = flags.get("parent") or str(default_pack_parent())
    kind = str(flags.get("brain") or "stub").strip().lower()
    brain = None
    if kind == "local":
        choice = local_first_choice(local_discover())
        if not choice:
            raise SeedError(
                t(
                    "这台电脑上没有发现本地模型：先启动 Ollama / LM Studio，"
                    "或改用 --brain stub 先离线跑。"
                )
            )
        brain = choice
    elif kind in ("anthropic", "claude"):
        brain = {
            "adapter": "anthropic",
            "model": str(flags.get("model") or "deepseek-flash"),
            "base_url": str(flags.get("base-url")
                           or "https://api.deepseek.com/anthropic"),
            "api_key_env": str(flags.get("api-key-env") or "DEEPSEEK_API_KEY"),
        }
    elif kind in ("openai-compatible", "openai"):
        base_url = str(flags.get("base-url") or "").strip()
        if not base_url:
            raise SeedError(t("--brain openai-compatible 需要 --base-url（例如 http://127.0.0.1:11434/v1）。"))
        brain = {
            "adapter": "openai-compatible",
            "model": str(flags.get("model") or ""),
            "base_url": base_url,
            "api_key_env": str(flags.get("api-key-env") or ""),
        }
    elif kind == "codex":
        from .codex_transport import DEFAULT_MODEL
        brain = {"adapter": "codex", "model": str(flags.get("model") or DEFAULT_MODEL),
                 "base_url": "", "api_key_env": ""}
    elif kind == "workbuddy":
        from .workbuddy_transport import model_id
        brain = {"adapter": "workbuddy", "model": model_id({"model": flags.get("model")}),
                 "base_url": "", "api_key_env": ""}
    elif kind not in ("stub", "none", "offline"):
        raise SeedError(t("不认识的脑类型：{kind}（stub / local / anthropic / openai-compatible）", kind=kind))

    try:
        pack = create_fish(clean, parent, brain=brain)
    except SeedError:
        raise
    print(t("[seed] 她醒了：{pack}", pack=pack))
    if brain:
        print(t("[seed] 她的脑：{adapter} · {value}", adapter=brain.get('adapter'), value=brain.get('model') or t('（默认模型）')))
    else:
        print(t("[seed] 她先用离线的模板脑——随时可以用 seed brain 换。"))
    print(t("[seed] 下一步：seed window \"{pack}\"  （或者直接双击 seedbank.exe）", pack=pack))
    return 0


def _cmd_start(args: list[str]) -> int:
    """打开上次那条鱼；没有就告诉用户先领养。"""
    _, flags = _flags(args)
    raw = flags.get("pack")
    if raw:
        pack = expand_home(str(raw))
        if not (pack / "birth.json").is_file():
            raise SeedError(t("这里不是一条鱼的生命包：{pack}", pack=pack))
        return _cmd_window([str(pack)])
    pack = resolve_pack()
    if pack is None:
        raise SeedError(
            t(
                "还没有领养过鱼：先运行 seed setup --name 小蓝，"
                "或者双击 seedbank.exe 按向导来。"
            )
        )
    return _cmd_window([str(pack)])


def _cmd_local(args: list[str]) -> int:
    """看看本机有没有能用的模型。"""
    _, flags = _flags(args)
    results = local_discover()
    print(describe_local(results))
    if flags.get("probe") is not None or "--probe" in args:
        print("")
        print(t("逐个端口探测："))
        for label, base_url in LOCAL_PROBES:
            row = local_probe(base_url, label=label)
            mark = "✓" if row.get("ok") and row.get("models") else "✗"
            print(f"  {mark} {label:<12} {base_url}  {row.get('note') or ''}")
    choice = local_first_choice(results)
    if choice:
        print("")
        print(
            t(
                '想用它当她的脑：seed brain "<生命包>" --set openai-compatible '
                "--base-url {base_url} --model {model}",
                base_url=choice["base_url"],
                model=choice["model"],
            )
        )
    return 0


def _cmd_grow(args: list[str]) -> int:
    """离线时，让本机帮她整理一次记忆。"""
    if not args:
        raise SeedError(t("用法：seed grow <生命包>"))
    pack = expand_home(args[0])
    if not (pack / "birth.json").is_file():
        raise SeedError(t("这里不是一条鱼的生命包：{pack}", pack=pack))
    entry = offline_grow(pack)
    if entry:
        print(t("[seed] 她自己长大了一点（第 {day} 天）：{value}", day=entry['day'], value=entry['text']))
    else:
        print(t("[seed] 今天没有新的变化——她还没有反复在意的事。"))
    return 0


def _cmd_window(args: list[str]) -> int:
    positional, flags = _flags(args)
    if len(positional) != 1:
        raise SeedError(t("用法：seed window <生命包> [--brain 适配器]"))
    from .window import window as open_window

    return open_window(positional[0], str(flags.get("brain") or ""))


def _cmd_works(args: list[str]) -> int:
    positional, flags = _flags(args)
    if len(positional) not in (1, 2):
        raise SeedError(
            t(
                "用法：seed works <生命包> [--kind poem|letter|drawing] [--limit N]\n"
                "      seed works <生命包> <作品id>   # 看某一篇"
            )
        )
    pack_dir = positional[0]
    _ensure_pack(pack_dir)
    if len(positional) == 2:
        item = read_work(pack_dir, positional[1])
        if item is None:
            raise SeedError(t("找不到作品：{positional}", positional=positional[1]))
        label = t({"poem": "诗", "letter": "信", "drawing": "画"}.get(str(item.get("kind")), "作品"))
        day = t("第 {day} 天", day=item['day']) if item.get("day") else t("某一天")
        print(t("[{label}] {title}（{day}）", label=label, title=item.get('title'), day=day))
        print(str(item.get("text", "")))
        return 0
    kind = str(flags.get("kind") or "").strip() or None
    limit_raw = flags.get("limit")
    try:
        limit = int(limit_raw) if limit_raw is not None else 5
    except (TypeError, ValueError):
        raise SeedError(t("--limit 需要一个整数")) from None
    print(describe_works(pack_dir))
    items = list_works(pack_dir, kind=kind or None, limit=max(1, limit))
    for item in items:
        label = t({"poem": "诗", "letter": "信", "drawing": "画"}.get(str(item.get("kind")), "作品"))
        day = t("第 {day} 天", day=item['day']) if item.get("day") else t("某一天")
        first = str(item.get("text", "")).splitlines()[0][:60]
        print(t("  {id}  [{label}] {title}（{day}）  {first}", id=item.get('id'), label=label, title=item.get('title'), day=day, first=first))
    return 0


def _cmd_make(args: list[str]) -> int:
    positional, flags = _flags(args)
    if len(positional) != 1:
        raise SeedError(
            t("用法：seed make <生命包> [--kind poem|letter|drawing] [--title 标题] [--brain 适配器]")
        )
    pack_dir = positional[0]
    _ensure_pack(pack_dir)
    kind = str(flags.get("kind") or "poem").strip().lower()
    label = {"poem": "诗", "letter": "信", "drawing": "画"}.get(kind)
    if label is None:
        raise SeedError(t("--kind 只认 poem / letter / drawing（诗 / 信 / 画）。"))
    override = str(flags.get("brain") or "")
    brain = create_brain(pack_dir, override)
    result = compose_work(pack_dir, kind, brain, title=str(flags.get("title") or ""))
    if result.get("succeeded") is False:
        print(t("本次未生成作品，尝试已记录。再次发起会作为新的尝试。"))
        print(result["error"])
        return 1
    entry = result["entry"]
    measure = t({"poem": "首诗", "letter": "封信", "drawing": "幅画"}.get(kind, "件作品"))
    print(t("[seed] 第 {dayNo} 天，她写了一{measure}：《{title}》", dayNo=result['dayNo'], measure=measure, title=entry['title']))
    print(entry["text"])
    return 0


def _cmd_qq(args: list[str]) -> int:
    """QQ 载体：参数原样交给 seedbank.qq（OneBot v11 桥）。"""
    from . import qq as qq_module

    return qq_module.main(args)


def _cmd_development(args: list[str]) -> int:
    from .development import summary
    positional, _ = _flags(args)
    if len(positional) != 1:
        raise SeedError("用法：seed development <生命包>")
    _ensure_pack(positional[0])
    print(json.dumps(summary(positional[0]), ensure_ascii=False, indent=2))
    return 0


def _cmd_recover(args: list[str]) -> int:
    from .pack_lock import writer
    from .requests import pending
    positional, _ = _flags(args)
    if len(positional) != 1:
        raise SeedError("用法：seed recover <生命包>")
    with writer(positional[0]) as recovered:
        result = {"recovered": recovered or [], "pending": pending(positional[0])}
    print(json.dumps(result, ensure_ascii=False, indent=2))
    return 0


def _cmd_resume(args: list[str]) -> int:
    from .bridge import Bridge
    positional, flags = _flags(args)
    if len(positional) != 2:
        raise SeedError("用法：seed resume <生命包> <请求编号> [--brain stub]")
    result = Bridge(positional[0], str(flags.get("brain") or "")).handle(
        {"op": "resume", "request_id": positional[1]})
    print(json.dumps(result, ensure_ascii=False, indent=2))
    return 0 if result.get("ok") else 1


def _cmd_backup(args: list[str]) -> int:
    from .backup import create
    positional, flags = _flags(args)
    if len(positional) != 1:
        raise SeedError("用法：seed backup <生命包> [--out 新备份.zip]")
    print(json.dumps(create(positional[0], flags.get("out")), ensure_ascii=False, indent=2))
    return 0


def _cmd_backup_info(args: list[str]) -> int:
    from .backup import inspect_backup
    positional, _ = _flags(args)
    if len(positional) != 1:
        raise SeedError("用法：seed backup-info <备份.zip>")
    print(json.dumps(inspect_backup(positional[0]), ensure_ascii=False, indent=2))
    return 0


def _cmd_restore(args: list[str]) -> int:
    from .backup import restore
    positional, _ = _flags(args)
    if len(positional) != 2:
        raise SeedError("用法：seed restore <备份.zip> <新生命包文件夹>")
    print(json.dumps(restore(positional[0], positional[1]), ensure_ascii=False, indent=2))
    return 0


def _cmd_lifecycle(args: list[str]) -> int:
    from .lifecycle import status, transition
    positional, flags = _flags(args)
    if not 1 <= len(positional) <= 2:
        raise SeedError("用法：seed lifecycle <生命包> [status|pause|resume] [--note 说明 --expected 版本 --confirm]")
    pack = Path(positional[0]).expanduser().resolve()
    action = positional[1] if len(positional) > 1 else "status"
    from .pack_lock import writer
    with writer(pack):
        if action == "status":
            result = status(pack)
        else:
            raw_revision = flags.get("expected")
            if not isinstance(raw_revision, str) or not raw_revision.isdigit():
                raise SeedError("请先查看 lifecycle status，并用 --expected 指定当前版本。")
            result = transition(pack, action, note=flags.get("note"), expected=int(raw_revision),
                                confirmed=_bool_flag(flags, "confirm") is True)
    print(json.dumps(result, ensure_ascii=False, indent=2))
    return 0


COMMANDS = {
    "lifecycle": _cmd_lifecycle,
    "backup": _cmd_backup,
    "backup-info": _cmd_backup_info,
    "restore": _cmd_restore,
    "recover": _cmd_recover,
    "resume": _cmd_resume,
    "development": _cmd_development,
    "hatch": _cmd_hatch,
    "check": _cmd_check,
    "day": _cmd_day,
    "chat": _cmd_chat,
    "sense": _cmd_sense,
    "feed": _cmd_feed,
    "news": _cmd_news,
    "recall": _cmd_recall,
    "memories": _cmd_memories,
    "forget": _cmd_forget,
    "memory-history": _cmd_memory_history,
    "revise": _cmd_revise,
    "persona": _cmd_persona,
    "semantic": _cmd_semantic,
    "facts": _cmd_facts,
    "learning": _cmd_learning,
    "relationships": _cmd_relationships,
    "disclosure": _cmd_disclosure,
    "life-story": _cmd_life_story,
    "media": _cmd_media,
    "timeline": _cmd_timeline,
    "clock": _cmd_clock,
    "tick": _cmd_tick,
    "agency": _cmd_agency,
    "initiate": _cmd_initiate,
    "bond": _cmd_bond,
    "promise": _cmd_promise,
    "memorial": _cmd_memorial,
    "inner": _cmd_inner,
    "works": _cmd_works,
    "make": _cmd_make,
    "hands": _cmd_hands,
    "remind": _cmd_remind,
    "reminder-change": _cmd_reminder_change,
    "visit": _cmd_visit,
    "mourn": _cmd_mourn,
    "legacy": _cmd_legacy,
    "live": _cmd_live,
    "event": _cmd_event,
    "brain": _cmd_brain,
    "settings": _cmd_brain,
    "bridge": _cmd_bridge,
    "qq": _cmd_qq,
    "serve": _cmd_serve,
    "start": _cmd_start,
    "setup": _cmd_setup,
    "local": _cmd_local,
    "grow": _cmd_grow,
    "window": _cmd_window,
    "egg-info": _cmd_egg_info,
}


# 每个命令认识的参数。拼错的参数直接报错，而不是被 _flags 静默忽略。
ALLOWED_FLAGS = {
    "lifecycle": {"note", "expected", "confirm"},
    "backup": {"out"},
    "backup-info": set(),
    "restore": set(),
    "recover": set(),
    "resume": {"brain"},
    "development": set(),
    "hatch": {"seed", "time"},
    "check": set(),
    "day": {"days", "brain"},
    "chat": {"once", "brain", "request-id"},
    "sense": {"image", "sound", "note", "vision"},
    "feed": {"source", "file", "max"},
    "news": {"day"},
    "recall": {"query", "k"},
    "memories": {"day", "forgotten", "history", "json"},
    "forget": {"reason"},
    "memory-history": set(),
    "revise": {"text", "reason", "type", "effective-on", "request-id"},
    "persona": {"brain", "threshold"},
    "semantic": {"enabled", "model", "base-url", "api-key-env", "revision", "min-similarity", "query-prefix", "document-prefix"},
    "facts": {"query", "audit", "limit", "offset", "data-file", "request-id", "on", "slot", "record-offset", "target"},
    "learning": {"goal", "limit", "offset", "data-file", "request-id", "brain"},
    "relationships": {"person", "limit", "offset", "history", "data-file", "request-id"},
    "disclosure": {"query", "limit", "offset", "record-offset", "history", "data-file", "request-id"},
    "life-story": {"query", "limit", "offset", "source-offset", "history", "data-file", "request-id", "out"},
    "timeline": {"out", "title"},
    "clock": set(),
    "tick": {"now", "brain"},
    "agency": {"interest", "boundary", "clear-boundaries", "history", "day", "before", "limit"},
    "initiate": {"now", "brain", "force"},
    "bond": {"thank", "sorry", "conflict", "repair"},
    "promise": {"due-day", "keep", "break", "note"},
    "memorial": {"anniversary", "day", "kind", "note", "regret", "resolve", "farewell"},
    "inner": {"silence", "note", "dream", "narrate", "correct", "now"},
    "works": {"kind", "limit"},
    "make": {"kind", "title", "brain"},
    "hands": {"done"},
    "remind": {"due-day", "due-on", "request-id"},
    "reminder-change": {"id", "expected", "reason", "text", "due-on", "request-id"},
    "visit": {"from", "note"},
    "mourn": {"friend", "letter"},
    "legacy": {"out"},
    "live": {"interval", "rounds", "brain"},
    "event": {"kind", "text", "source"},
    "brain": {
        "set", "model", "base-url", "api-key-env", "temperature",
        "strict", "no-strict", "daily-max", "vision", "vision-model", "vision-max-side",
        "test", "open-folder", "input-budget",
    },
    "settings": {
        "set", "model", "base-url", "api-key-env", "temperature",
        "strict", "no-strict", "daily-max", "vision", "vision-model", "vision-max-side",
        "test", "open-folder", "input-budget",
    },
    "bridge": {"brain"},
    "serve": {"port", "host", "open", "brain"},
    "start": {"pack"},
    "setup": {"name", "parent", "brain", "model", "base-url", "api-key-env"},
    "local": {"probe"},
    "grow": set(),
    "window": {"brain"},
    "egg-info": set(),
}


def main(argv: list[str] | None = None) -> int:
    _ensure_utf8_io()
    _init_locale()
    args = list(sys.argv[1:] if argv is None else argv)
    if not args or args[0] in ("-h", "--help", "help"):
        print(_usage_text())
        return 0
    if args[0] in ("-V", "--version", "version"):
        print(f"SeedBank {__version__}")
        return 0
    command = args[0]
    handler = COMMANDS.get(command)
    if handler is None:
        print(t("[seed] 错误：不认识的命令「{command}」\n", command=command), file=sys.stderr)
        print(_usage_text(), file=sys.stderr)
        return 1
    allowed = ALLOWED_FLAGS.get(command)
    if allowed is not None:
        _, raw_flags = _flags(args[1:])
        unknown = sorted(set(raw_flags) - allowed)
        if unknown:
            names = "、".join("--" + name for name in unknown)
            print(
                t("[seed] 错误：不认识的参数：{names}（seed {command} 的用法见 seed help）", names=names, command=command),
                file=sys.stderr,
            )
            return 1
    try:
        return handler(args[1:])
    except (SeedError, ValueError) as error:
        print(t("[seed] 错误：{error}", error=error), file=sys.stderr)
        return 1
    except OSError as error:
        print(t("[seed] 错误：路径或文件操作失败（{error}）", error=error), file=sys.stderr)
        return 1
