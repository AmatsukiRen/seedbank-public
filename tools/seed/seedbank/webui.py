"""聊天窗口 —— 她的一扇窗。

零依赖本地网页：像聊天工具一样和她说话、给她看东西、陪她过一天。
只监听 127.0.0.1，不对局域网开放；关掉窗口，她就停下来（世界交给时钟）。
"""

from __future__ import annotations

import json
import os
import shutil
import tempfile
import threading
import webbrowser
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from urllib.parse import parse_qs, urlparse

from . import __version__
from .brain import create_brain, describe_brain, load_brain_config
from .clock import tick as clock_tick
from .cognition import (
    chat_turn,
    open_day,
    read_sense_lines,
    read_transcript,
    run_days,
    sense_media,
)
from .i18n import get_locale, t
from .util import SeedError, expand_home, list_days, read_json, read_memories, read_text


def _tick(pack, brain) -> None:
    """她的时间按真实的一天走：每次互动、每分钟先看钟。"""
    try:
        clock_tick(pack, brain)
    except Exception:  # noqa: BLE001 - 时钟不该挡住说话
        pass


def _ticker(pack, brain, lock: threading.Lock, stop: threading.Event) -> None:
    """后台每分钟走一格：跨过凌晨她就自己过完一天。和请求共用一把写锁。"""
    while not stop.wait(60.0):
        try:
            with lock:
                _tick(pack, brain)
        except Exception:  # noqa: BLE001 - 看钟失败不该让窗口停下
            pass


MAX_UPLOAD = 40 * 1024 * 1024
MAX_DAYS = 3650


def _diary_of(text: str) -> str:
    marker = "## 今天"
    index = text.find(marker)
    if index < 0:
        return ""
    body = text[index + len(marker):]
    end = body.find("\n---")
    if end >= 0:
        body = body[:end]
    return body.strip()


def _read_day_text(pack: Path, item: dict) -> str:
    path = pack / "life" / item["file"]
    if not path.is_file():
        return ""
    return read_text(path)


def _day_diary(pack: Path, item: dict) -> str:
    return _diary_of(_read_day_text(pack, item))


def _history(pack: Path, days: int = 7) -> list:
    rows = []
    for item in list_days(pack)[-days:]:
        rows.append({
            "day": item["day"],
            "date": item["date"],
            "diary": _day_diary(pack, item),
            "senses": read_sense_lines(pack, item["day"]),
            "transcript": read_transcript(pack, item["day"]),
        })
    return rows


def _mood(pack: Path) -> dict:
    try:
        data = read_json(pack / "mind" / "mood.json", {}) or {}
    except (SeedError, OSError):
        data = {}
    return {"mood": str(data.get("mood") or "安静"), "energy": data.get("energy")}


def _state(pack: Path) -> dict:
    birth = read_json(pack / "birth.json", {}) or {}
    day = open_day(pack)
    return {
        "ok": True,
        "version": __version__,
        "name": str(birth.get("name") or "她"),
        "day": day["dayNo"],
        "date": day["date"],
        "days": len(list_days(pack)),
        "memories": len(read_memories(pack)),
        "brain": describe_brain(load_brain_config(pack)),
        **_mood(pack),
        "history": _history(pack),
    }


def _guess_extension(data: bytes) -> str:
    if data.startswith(b"\x89PNG\r\n\x1a\n"):
        return ".png"
    if data.startswith(b"\xff\xd8\xff"):
        return ".jpg"
    if data.startswith(b"BM"):
        return ".bmp"
    if data[:2] in (b"P5", b"P6"):
        return ".ppm"
    if data[:4] == b"RIFF" and data[8:12] == b"WAVE":
        return ".wav"
    return ".bin"


class _Server(ThreadingHTTPServer):
    daemon_threads = True
    # Windows 的 SO_REUSEADDR 允许同端口二次 bind（会静默起两个写者），
    # 所以这里在 Windows 上关掉，让端口占用真的报错。
    allow_reuse_address = os.name != "nt"

    def __init__(self, address, *, pack: Path, brain, lock: threading.Lock):
        super().__init__(address, _Handler)
        self.pack = pack
        self.brain = brain
        self.lock = lock


class _Handler(BaseHTTPRequestHandler):
    server_version = "Seedbank"
    sys_version = ""
    timeout = 30  # 慢客户端别一直占着线程

    def setup(self):
        super().setup()
        try:
            self.connection.settimeout(30)
        except OSError:
            pass

    # —— 小工具 ——

    def _send(self, status: int, body: bytes, content_type: str) -> None:
        self.send_response(status)
        self.send_header("Content-Type", content_type)
        self.send_header("Content-Length", str(len(body)))
        self.send_header("Cache-Control", "no-store")
        self.end_headers()
        self.wfile.write(body)

    def _json(self, payload: dict, status: int = 200) -> None:
        body = json.dumps(payload, ensure_ascii=False).encode("utf-8")
        self._send(status, body, "application/json; charset=utf-8")

    def _read_body(self) -> bytes:
        try:
            length = int(self.headers.get("Content-Length") or 0)
        except (TypeError, ValueError):
            raise ValueError(t("Content-Length 不合法"))
        if length < 0:
            raise ValueError(t("Content-Length 不合法"))
        if length > MAX_UPLOAD:
            raise SeedError(t("东西太大了（最多 40MB）"))
        if not length:
            return b""
        try:
            return self.rfile.read(length)
        except OSError as exc:
            raise ValueError(t("请求体没读完：{error}", error=exc)) from None

    def _json_body(self) -> dict:
        raw = self._read_body()
        if not raw:
            return {}
        try:
            data = json.loads(raw.decode("utf-8"))
        except (UnicodeDecodeError, json.JSONDecodeError):
            raise ValueError(t("请求不是合法的 JSON"))
        return data if isinstance(data, dict) else {}

    def log_message(self, fmt, *args):  # 安静一点
        return

    # —— 路由 ——

    def do_GET(self):
        try:
            self._do_get()
        except (SeedError, ValueError, OSError) as exc:
            self._safe_json({"ok": False, "error": str(exc)}, 500)
        except Exception as exc:  # noqa: BLE001 - 读不出来也要给窗口一个回答
            self._safe_json({"ok": False, "error": t("读不出来：{error}", error=exc)}, 500)

    def _do_get(self):
        path = urlparse(self.path).path
        if path in ("/", "/index.html"):
            self._send(200, _page_html().encode("utf-8"), "text/html; charset=utf-8")
        elif path == "/api/state":
            server = self.server
            with server.lock:
                state = _state(server.pack)
            self._json(state)
        else:
            self._json({"ok": False, "error": t("这里没有东西")}, 404)

    def _safe_json(self, payload: dict, status: int = 200) -> None:
        try:
            self._json(payload, status)
        except OSError:
            pass

    def do_POST(self):
        try:
            self._do_post()
        except BrokenPipeError:
            return
        except (SeedError, ValueError, OSError) as exc:
            self._safe_json({"ok": False, "error": str(exc)}, 400)
        except Exception as exc:  # noqa: BLE001 - 窗口内部错误不要变成断连
            self._safe_json({"ok": False, "error": t("窗口内部出了点问题：{error}", error=exc)}, 500)

    def _do_post(self):
        path = urlparse(self.path).path
        try:
            if path == "/api/message":
                data = self._json_body()
                text = str(data.get("text") or "").strip()
                speaker = str(data.get("speaker") or "主人")
                server = self.server
                with server.lock:
                    _tick(server.pack, server.brain)
                    result = chat_turn(server.pack, text, server.brain, speaker=speaker)
                self._json({
                    "ok": True,
                    "reply": result["reply"],
                    "day": result["dayNo"],
                    "date": result["date"],
                    "memories_added": result["memoriesAdded"],
                })
            elif path == "/api/day":
                data = self._json_body()
                try:
                    days = int(data.get("days", 1))
                except (TypeError, ValueError):
                    raise ValueError(t("days 必须是整数"))
                if days < 1 or days > MAX_DAYS:
                    raise ValueError(t("days 要在 1..{max_days} 之间", max_days=MAX_DAYS))
                server = self.server
                with server.lock:
                    result = run_days(server.pack, days=days, brain=server.brain)
                    rows = []
                    for item in result["days"]:
                        diary = _day_diary(server.pack, item)
                        rows.append({
                            "day": item["day"],
                            "date": item["date"],
                            "diary": diary,
                            "mood": item["mood"],
                            "memories": item["memoriesAdded"],
                        })
                self._json({"ok": True, "days": rows})
            elif path == "/api/media":
                query = parse_qs(urlparse(self.path).query)
                kind = (query.get("kind", ["image"])[0] or "image").strip().lower()
                if kind not in ("image", "sound"):
                    raise ValueError(t("kind 只能是 image 或 sound"))
                note = (query.get("note", [""])[0] or "").strip()[:200]
                data = self._read_body()
                if not data:
                    raise ValueError(t("没有收到东西"))
                suffix = _guess_extension(data)
                temp_dir = Path(tempfile.mkdtemp(prefix="seedbank-sense-"))
                try:
                    path_file = temp_dir / f"media{suffix}"
                    path_file.write_bytes(data)
                    server = self.server
                    with server.lock:
                        _tick(server.pack, server.brain)
                        if kind == "image":
                            result = sense_media(server.pack, image=str(path_file), note=note or None)
                        else:
                            result = sense_media(server.pack, sound=str(path_file), note=note or None)
                finally:
                    shutil.rmtree(temp_dir, ignore_errors=True)
                self._json({
                    "ok": True,
                    "lines": result["lines"],
                    "day": result["dayNo"],
                    "date": result["date"],
                    "memories_added": result["memoriesAdded"],
                })
            elif path == "/api/stop":
                self._json({"ok": True, "bye": True})
                threading.Thread(target=self.server.shutdown, daemon=True).start()
            else:
                self._json({"ok": False, "error": t("这里没有东西")}, 404)
        except Exception:  # 交给外层 do_POST 统一变成 JSON 错误
            raise


PAGE = """<!doctype html>
<html lang="__SEEDBANK_LANG__">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>Seedbank · 她的窗口</title>
<style>
:root{--bg:#0f1219;--panel:#171c27;--ink:#e8eaf2;--dim:#8b93a8;--line:#28303f}
*{box-sizing:border-box}
html,body{height:100%;margin:0}
body{background:radial-gradient(1200px 600px at 50% -10%,#1b2233,#0f1219 60%);color:var(--ink);
 font:15px/1.65 "Segoe UI","PingFang SC","Microsoft YaHei",sans-serif;display:flex;justify-content:center}
#app{width:min(880px,100%);height:100vh;display:flex;flex-direction:column;
 background:rgba(23,28,39,.55);border-left:1px solid var(--line);border-right:1px solid var(--line)}
header{display:flex;align-items:center;gap:12px;padding:12px 18px;border-bottom:1px solid var(--line)}
.avatar{width:38px;height:38px;border-radius:50%;display:grid;place-items:center;background:#1d2a3a;font-size:20px}
.who b{font-size:16px}
.who span{display:block;font-size:12px;color:var(--dim)}
.vitals{margin-left:auto;text-align:right;font-size:12px;color:var(--dim)}
.bar{width:96px;height:4px;border-radius:2px;background:#232b3a;overflow:hidden;margin-top:5px}
.bar i{display:block;height:100%;background:linear-gradient(90deg,#4d8f7f,#7fd4c1);transition:width .4s}
main{flex:1;overflow-y:auto;padding:18px 18px 8px;display:flex;flex-direction:column;gap:10px}
.day{display:flex;align-items:center;gap:10px;color:var(--dim);font-size:12px;margin:12px 0 2px}
.day:before,.day:after{content:"";flex:1;height:1px;background:var(--line)}
.diary{font-size:13px;color:#c6cbd8;background:#141a25;border:1px solid var(--line);border-radius:12px;
 padding:10px 14px;white-space:pre-wrap}
.sense{font-size:13px;color:#9fc9bd;background:rgba(127,212,193,.06);border:1px dashed rgba(127,212,193,.3);
 border-radius:12px;padding:8px 14px;white-space:pre-wrap}
.msg{max-width:78%;padding:9px 14px;border-radius:16px;white-space:pre-wrap;word-break:break-word}
.msg.her{align-self:flex-start;background:#1e2634;border-bottom-left-radius:6px}
.msg.me{align-self:flex-end;background:#233a52;border-bottom-right-radius:6px}
.msg.guest{align-self:flex-start;background:#2a2440;border-bottom-left-radius:6px}
.tag{font-size:11px;color:var(--dim);margin-bottom:2px}
.typing{align-self:flex-start;color:var(--dim);font-size:13px;padding:6px 12px}
footer{padding:12px 18px 16px;border-top:1px solid var(--line);background:rgba(15,18,25,.7)}
.row{display:flex;gap:8px;align-items:flex-end}
textarea{flex:1;resize:none;height:46px;padding:11px 14px;border-radius:14px;border:1px solid var(--line);
 background:#141a25;color:var(--ink);font:inherit;outline:none}
textarea:focus{border-color:#3d6b63}
button{border:1px solid var(--line);background:#1d2a3a;color:var(--ink);border-radius:12px;
 padding:10px 14px;cursor:pointer;font:inherit;white-space:nowrap}
button:hover{border-color:#3d6b63}
button.primary{background:#2c5c52;border-color:#3d6b63}
button:disabled{opacity:.45;cursor:default}
.hint{font-size:11px;color:var(--dim);margin-top:8px}
.hint b{color:#9fc9bd;font-weight:600}
</style>
</head>
<body>
<div id="app">
 <header>
  <div class="avatar">🐋</div>
  <div class="who"><b id="name">…</b><span id="meta">…</span></div>
  <div class="vitals"><div id="mood">…</div><div class="bar"><i id="energy" style="width:0"></i></div></div>
 </header>
 <main id="chat"></main>
 <footer>
  <div class="row">
   <button id="imgBtn" title="给她看一张图：她只会感觉到光和颜色，原图不会进入生命包">📷 看东西</button>
   <textarea id="text" placeholder="和她说点什么……（Enter 发送，Shift+Enter 换行）"></textarea>
   <button id="sendBtn" class="primary">说</button>
  </div>
  <div class="row" style="margin-top:9px">
   <button id="dayBtn">陪她过一天</button>
   <button id="quitBtn">关掉窗口</button>
   <div class="hint" style="margin:0 0 0 auto;align-self:center">
    世界是离线的 · 关掉窗口她就停下 · 记忆在她的文件里
   </div>
  </div>
  <input id="file" type="file" accept="image/*" hidden>
 </footer>
</div>
<script>
const UI = __SEEDBANK_UI__;
const $ = (s) => document.querySelector(s);

function fmt(s, vars){ return s.replace(/\\{(\\w+)\\}/g, (m, k) => (vars[k] !== undefined ? vars[k] : m)); }
let busy = false;

function scrollBottom(){ const m = $("#chat"); m.scrollTop = m.scrollHeight; }
function el(tag, cls, text){ const n = document.createElement(tag); if(cls) n.className = cls;
  if(text !== undefined) n.textContent = text; return n; }

function bubble(role, who, text){
  const box = el("div", "msg " + role);
  if(role === "guest" && who){ box.appendChild(el("div", "tag", who)); }
  box.appendChild(el("div", "", text));
  $("#chat").appendChild(box);
  scrollBottom();
}

function divider(day){
  $("#chat").appendChild(el("div", "day", fmt(UI.day, {day})));
  scrollBottom();
}

function notice(text){
  const box = el("div", "sense", text);
  $("#chat").appendChild(box);
  scrollBottom();
}

function renderHistory(history){
  for(const d of history){
    divider(d.day);
    if(d.diary) $("#chat").appendChild(el("div", "diary", d.diary));
    for(const m of d.transcript){
      if(m.who === state.name) bubble("her", "", m.text);
      else if(m.who === "主人") bubble("me", "", m.text);
      else bubble("guest", m.who, m.text);
    }
    if(d.senses && d.senses.length) notice(UI.senses + d.senses.join(" / "));
  }
  scrollBottom();
}

function setStatus(st){
  $("#name").textContent = st.name;
  $("#meta").textContent = fmt(UI.meta, {day: st.day, date: st.date, memories: st.memories});
  $("#mood").textContent = (st.mood || UI.quiet) + " · " + (st.brain || "");
  $("#energy").style.width = Math.round(Math.max(0, Math.min(1, st.energy || 0)) * 100) + "%";
}

async function refreshState(){
  const r = await fetch("/api/state", {cache: "no-store"});
  const data = await r.json();
  if(data.ok) setStatus(data);
}

async function api(path, options){
  const r = await fetch(path, options);
  const data = await r.json();
  if(!data.ok) throw new Error(data.error || UI.error);
  return data;
}

async function sendMessage(){
  const text = $("#text").value.trim();
  if(!text || busy) return;
  $("#text").value = "";
  bubble("me", "", text);
  const typing = el("div", "typing", UI.thinking);
  $("#chat").appendChild(typing); scrollBottom();
  busy = true; $("#sendBtn").disabled = true;
  try{
    const data = await api("/api/message", {method: "POST", headers: {"Content-Type": "application/json"},
      body: JSON.stringify({text})});
    typing.remove();
    bubble("her", "", data.reply);
    await refreshState();
  }catch(e){
    typing.remove();
    notice(UI.sendFailed + e.message);
  }finally{
    busy = false; $("#sendBtn").disabled = false; $("#text").focus();
  }
}

async function passOneDay(){
  if(busy) return;
  const typing = el("div", "typing", UI.workingDay);
  $("#chat").appendChild(typing); scrollBottom();
  busy = true; $("#dayBtn").disabled = true;
  try{
    const data = await api("/api/day", {method: "POST", headers: {"Content-Type": "application/json"},
      body: JSON.stringify({days: 1})});
    typing.remove();
    for(const d of data.days){
      divider(d.day);
      if(d.diary) $("#chat").appendChild(el("div", "diary", d.diary));
    }
    await refreshState();
  }catch(e){
    typing.remove();
    notice(UI.dayFailed + e.message);
  }finally{
    busy = false; $("#dayBtn").disabled = false;
  }
}

async function showImage(file){
  if(!file || busy) return;
  if(file.size > 40 * 1024 * 1024){ notice(UI.tooBig); return; }
  const note = window.prompt(UI.notePrompt, "") || "";
  const typing = el("div", "typing", UI.looking);
  $("#chat").appendChild(typing); scrollBottom();
  busy = true; $("#imgBtn").disabled = true;
  try{
    const buffer = await file.arrayBuffer();
    const data = await api("/api/media?kind=image&note=" + encodeURIComponent(note),
      {method: "POST", headers: {"Content-Type": "application/octet-stream"}, body: buffer});
    typing.remove();
    bubble("her", "", data.lines.join("\\n"));
    await refreshState();
  }catch(e){
    typing.remove();
    notice(UI.lookFailed + e.message);
  }finally{
    busy = false; $("#imgBtn").disabled = false;
  }
}

async function quitWindow(){
  try{ await fetch("/api/stop", {method: "POST"}); }catch(e){}
  notice(UI.closed);
}

$("#sendBtn").addEventListener("click", sendMessage);
$("#text").addEventListener("keydown", (e) => {
  if(e.key === "Enter" && !e.shiftKey){ e.preventDefault(); sendMessage(); }
});
$("#dayBtn").addEventListener("click", passOneDay);
$("#imgBtn").addEventListener("click", () => $("#file").click());
$("#file").addEventListener("change", () => { const f = $("#file").files[0]; $("#file").value = ""; showImage(f); });
$("#quitBtn").addEventListener("click", quitWindow);

(async function start(){
  try{
    const r = await fetch("/api/state", {cache: "no-store"});
    const data = await r.json();
    if(!data.ok) throw new Error(data.error || UI.stateFailed);
    state = data;
    setStatus(state);
    renderHistory(state.history);
    $("#text").focus();
  }catch(e){
    document.body.textContent = UI.startFailed + e.message;
  }
})();
</script>
</body>
</html>
"""


# 页面上需要翻译的静态文案（中文原文即 key）。
_PAGE_STATIC_TEXTS = (
    "给她看一张图：她只会感觉到光和颜色，原图不会进入生命包",
    "世界是离线的 · 关掉窗口她就停下 · 记忆在她的文件里",
    "和她说点什么……（Enter 发送，Shift+Enter 换行）",
    "Seedbank · 她的窗口",
    "📷 看东西",
    "陪她过一天",
)

# 注入到页面 JS 里的 UI 文案（key → 中文原文，{name} 是占位符）。
_UI_TEXT_KEYS = {
    "day": "第 {day} 天",
    "meta": "第 {day} 天 · {date} · 记忆 {memories} 条",
    "senses": "她感觉到的：",
    "quiet": "安静",
    "error": "出错了",
    "thinking": "她在想……",
    "sendFailed": "没能说上话：",
    "workingDay": "时间在走……",
    "dayFailed": "这一天没走成：",
    "tooBig": "照片太大了，她会看花眼（最多 40MB）",
    "notePrompt": "（可选）想对她说点什么？",
    "looking": "她凑近了看……",
    "lookFailed": "她没看清：",
    "closed": "窗口关上了。她还在她的文件夹里，等你回来。",
    "stateFailed": "读不到她的状态",
    "startFailed": "窗口没打开：",
}


def _ui_texts() -> dict:
    return {key: t(text) for key, text in _UI_TEXT_KEYS.items()}


def _page_html() -> str:
    """按当前语言渲染窗口页面。"""
    page = PAGE.replace("__SEEDBANK_UI__", json.dumps(_ui_texts(), ensure_ascii=False))
    page = page.replace("__SEEDBANK_LANG__", get_locale().replace("_", "-"))
    for original in _PAGE_STATIC_TEXTS:
        page = page.replace(original, t(original))
    page = page.replace(">说</button>", ">" + t("说") + "</button>")
    page = page.replace(">关掉窗口</button>", ">" + t("关掉窗口") + "</button>")
    return page


def serve(
    pack_dir,
    host: str = "127.0.0.1",
    port: int = 8765,
    open_browser: bool = False,
    brain_override: str = "",
) -> int:
    """启动本地聊天窗口，阻塞直到关掉。"""
    pack = Path(expand_home(str(pack_dir)))
    brain = create_brain(pack, brain_override)
    lock = threading.Lock()
    host = str(host or "127.0.0.1")
    port = 8765 if port is None else int(port)
    try:
        server = _Server((host, port), pack=pack, brain=brain, lock=lock)
    except OSError as exc:
        raise SeedError(t("窗口起不来（端口 {port} 是不是被占用了？）：{error}", port=port, error=exc))
    url = f"http://{host}:{port}/"
    birth = read_json(pack / "birth.json", {}) or {}
    print(t("[seed] {name} 的窗口：{url}", name=birth.get("name") or t("她"), url=url))
    print(t("[seed] 她现在是：{describe}", describe=describe_brain(load_brain_config(pack))))
    print(t("[seed] 窗口只在本机；关掉它（或 Ctrl+C），她就停下。"))
    if open_browser:
        threading.Timer(0.6, lambda: webbrowser.open(url)).start()
    _tick(pack, brain)
    stop = threading.Event()
    threading.Thread(target=_ticker, args=(pack, brain, lock, stop), daemon=True).start()
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        pass
    finally:
        stop.set()
        server.server_close()
    print(t("\n[seed] 窗口关上了。她还在她的文件夹里。"))
    return 0
