"""时间线网站 —— 把她的文件夹变成一页能点开的一生。

输出纯静态 HTML + CSS：没有脚本、没有字体外链、没有追踪。
丢到任何静态服务器（GitHub Pages、Nginx、U 盘）都能看。
"""

from __future__ import annotations

import html
import re
from pathlib import Path

from .util import list_days, read_json, read_memories, read_text, write_file_atomic
from .i18n import get_locale, t
from .desktop.text import t as interface_text
from .pack_lock import serialized

_MOOD_LINE = re.compile(r"^\*([^*]+)。\*$")
_TURN_LINE = re.compile(r"^\*\*(.+?)\*\*[：:](.*)$")


def _esc(value) -> str:
    return html.escape(str(value), quote=True)


def _parse_day(pack_dir, day: dict) -> dict:
    text = read_text(Path(pack_dir) / "life" / day["file"])
    convo: list[dict] = []
    diary: list[str] = []
    senses: list[str] = []
    section = None
    mood = ""
    for line in text.splitlines():
        t = line.strip()
        if t == "## 对话":
            section = "convo"
            continue
        if t == "## 感知":
            section = "senses"
            continue
        if t == "## 今天":
            section = "diary"
            continue
        if t == "---":
            section = None
            continue
        mood_match = _MOOD_LINE.match(t)
        if mood_match:
            mood = mood_match.group(1)
            continue
        if t.startswith("# ") or t.startswith("> "):
            continue
        if section == "senses" and t.startswith("- "):
            senses.append(t[2:].strip())
            continue
        turn = _TURN_LINE.match(t)
        if turn and section == "convo":
            convo.append({"who": turn.group(1), "text": turn.group(2)})
            continue
        if section == "diary" and t:
            diary.append(t)
    return {
        "day": day["day"],
        "date": day["date"],
        "mood": mood,
        "convo": convo,
        "senses": senses,
        "diary": diary,
    }


def _render_day(day: dict) -> str:
    paragraphs = "".join(f"<p>{_esc(p)}</p>" for p in day["diary"])
    convo = ""
    if day["convo"]:
        turns = "".join(f"<p><b>{_esc(t['who'])}</b>：{_esc(t['text'])}</p>" for t in day["convo"])
        summary = t("这一天说过的话（{count} 句）", count=len(day["convo"]))
        convo = f'<details class="convo"><summary>{summary}</summary>{turns}</details>'
    senses = ""
    if day.get("senses"):
        items = "".join(f"<p>{_esc(s)}</p>" for s in day["senses"])
        summary = t("这一天她感觉到的（{count} 条）", count=len(day["senses"]))
        senses = f'<details class="senses"><summary>{summary}</summary>{items}</details>'
    mood = f'<span class="mood">{_esc(day["mood"])}</span>' if day["mood"] else ""
    daynum = t("第 {day:04d} 天", day=day["day"])
    quiet = t("这一天没有留下字。")
    diary_html = paragraphs or f'<p class="quiet">{quiet}</p>'
    return f"""<li class="day">
  <article>
    <header class="day-head">
      <span class="daynum">{daynum}</span>
      <time datetime="{_esc(day["date"])}">{_esc(day["date"])}</time>
      {mood}
    </header>
    <div class="diary">{diary_html}</div>
    {senses}
    {convo}
  </article>
</li>"""

CSS = """:root {
  --paper: #f7f4ee;
  --ink: #2b2a26;
  --faint: #8a857a;
  --line: #ded8ca;
  --sea: #3f7f9e;
}
* { box-sizing: border-box; }
html { background: var(--paper); }
body {
  margin: 0 auto;
  padding: 3rem 1.25rem 4rem;
  max-width: 44rem;
  color: var(--ink);
  font-family: "Songti SC", "Noto Serif SC", "Source Han Serif SC", Georgia, serif;
  line-height: 1.85;
  background: var(--paper);
}
.eyebrow { color: var(--faint); letter-spacing: .2em; font-size: .8rem; margin: 0 0 .5rem; }
h1 { font-size: 2.4rem; margin: 0 0 .4rem; font-weight: 600; }
.species { color: var(--faint); margin: 0 0 1.6rem; }
.stats { display: flex; gap: 2rem; margin: 0 0 2.5rem; padding: 1rem 0; border-top: 1px solid var(--line); border-bottom: 1px solid var(--line); }
.stats div { display: flex; flex-direction: column; }
.stats dt { color: var(--faint); font-size: .8rem; }
.stats dd { margin: 0; font-size: 1.25rem; color: var(--sea); }
.timeline { list-style: none; margin: 0; padding: 0 0 0 1.1rem; border-left: 1px solid var(--line); }
.day { position: relative; padding: 0 0 2.2rem 1.6rem; }
.day::before {
  content: ""; position: absolute; left: -1.45rem; top: .55rem;
  width: .65rem; height: .65rem; border-radius: 50%;
  background: var(--sea); box-shadow: 0 0 0 4px var(--paper);
}
.day-head { display: flex; flex-wrap: wrap; align-items: baseline; gap: .8rem; margin-bottom: .5rem; }
.daynum { color: var(--sea); font-size: .85rem; letter-spacing: .1em; }
.day-head time { color: var(--faint); font-size: .85rem; }
.mood { margin-left: auto; font-size: .8rem; color: var(--sea); border: 1px solid var(--line); border-radius: 999px; padding: .05rem .6rem; }
.diary p { margin: 0 0 .7rem; }
.quiet { color: var(--faint); font-style: italic; }
.convo { margin-top: .8rem; border-top: 1px dashed var(--line); padding-top: .6rem; color: #55524a; }
.convo summary { cursor: pointer; color: var(--sea); font-size: .85rem; }
.convo p { margin: .4rem 0; font-size: .95rem; }
.senses { margin-top: .8rem; border-top: 1px dashed var(--line); padding-top: .6rem; color: #5a5548; }
.senses summary { cursor: pointer; color: var(--sea); font-size: .85rem; }
.senses p { margin: .4rem 0; font-size: .95rem; font-style: italic; }
footer { margin-top: 3rem; padding-top: 1rem; border-top: 1px solid var(--line); color: var(--faint); font-size: .8rem; }
footer a { color: var(--sea); }
@media (max-width: 480px) {
  body { padding: 1.8rem 1rem 3rem; }
  h1 { font-size: 1.9rem; }
  .stats { gap: 1.2rem; }
}
"""


@serialized
def render_timeline(pack_dir, title: str = "") -> dict:
    """生成时间线网页。返回 {html, css, stats}。"""
    birth = read_json(Path(pack_dir) / "birth.json")
    if not isinstance(birth, dict) or not birth:
        raise ValueError(t("不是生命包（缺 birth.json）：{pack}", pack=pack_dir))
    if not isinstance(birth.get("name", ""), str):
        raise ValueError(t("生命包的 birth.json 里 name 不是文字：{pack}", pack=pack_dir))
    days = list_days(pack_dir)
    memories = len(read_memories(pack_dir))
    mood_doc = read_json(Path(pack_dir) / "mind" / "mood.json", {})
    if not isinstance(mood_doc, dict):
        raise ValueError(t("生命包里的 mind/mood.json 不是对象：{pack}", pack=pack_dir))
    parsed = [_parse_day(pack_dir, d) for d in days]
    born = str(birth.get("born_at") or "")[:10]
    name = birth.get("name") or t("她")
    page_title = title or t("{name} 的一生 · Seedbank", name=name)
    species_name = (birth.get("species") or {}).get("name") or t("未知物种")
    lang = get_locale().replace("_", "-")
    eyebrow = t("SEEDBANK · 一条可读的一生")
    species_line = t(
        "{species} · 出生于 {born} · 时钟 {clock}",
        species=species_name,
        born=born,
        clock=birth.get("clock", "on-demand"),
    )
    lived_label = interface_text("已有日页")
    lived_value = str(len(days))
    memories_label = t("记忆")
    memories_value = t("{n} 条", n=memories)
    mood_label = t("此刻心情")
    description = name + " · " + interface_text("已有日页：{count}", count=len(days))
    footer_brand = '<a href="https://github.com/AmatsukiRen/seedbank">Seedbank</a>'
    footer_hatch = t(
        "由 {brand} 孵化 · 蛋 {egg}@{version}",
        brand=footer_brand,
        egg=_esc((birth.get("egg") or {}).get("id", "")),
        version=_esc((birth.get("egg") or {}).get("version", "")),
    )
    footer_note = t("她的身体是一个文件夹。这一页只是把文件夹读给你听。")

    from .life_story import markdown as story_markdown
    story_html = '<section class="life-story"><pre style="white-space:pre-wrap;overflow-wrap:anywhere;font:inherit">' + _esc(story_markdown(pack_dir)) + '</pre></section>'
    page = f"""<!doctype html>
<html lang="{lang}">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>{_esc(page_title)}</title>
<meta name="description" content="{_esc(description)}">
<link rel="stylesheet" href="style.css">
</head>
<body>
<header>
  <p class="eyebrow">{eyebrow}</p>
  <h1>{_esc(name)}</h1>
  <p class="species">{_esc(species_line)}</p>
  <dl class="stats">
    <div><dt>{lived_label}</dt><dd>{lived_value}</dd></div>
    <div><dt>{memories_label}</dt><dd>{memories_value}</dd></div>
    <div><dt>{mood_label}</dt><dd>{_esc(mood_doc.get("mood", "—"))}</dd></div>
  </dl>
</header>
<main>
  {story_html}
  <ol class="timeline">
{"".join(_render_day(d) for d in parsed)}
  </ol>
</main>
<footer>
  <p>{footer_hatch}</p>
  <p>{footer_note}</p>
</footer>
</body>
</html>
"""
    return {"html": page, "css": CSS, "stats": {"days": len(days), "memories": memories}}


def write_timeline(pack_dir, out_dir, title: str = "") -> dict:
    """把时间线写到目录里：index.html + style.css + .nojekyll"""
    rendered = render_timeline(pack_dir, title=title)
    out = Path(out_dir)
    out.mkdir(parents=True, exist_ok=True)
    write_file_atomic(out / "index.html", rendered["html"])
    write_file_atomic(out / "style.css", rendered["css"])
    write_file_atomic(out / ".nojekyll", "")
    return {"index": str(out / "index.html"), "css": str(out / "style.css"), "stats": rendered["stats"]}
