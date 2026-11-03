"""Offline responses for an open identity; no invented body or biography."""
import re

from .memory_state import provenance


def chat(ctx):
    message = str(ctx.get("message", ""))
    inner = ctx.get("inner") or {}
    boundary = next((b for b in ctx.get("boundaries", []) if str(b).casefold() in message.casefold()), None)
    if boundary or (inner.get("silence") or {}).get("on"):
        return {"reply": "我现在想安静一会儿，暂时不聊这个。", "memory_writes": []}
    reminders = (ctx.get("hands") or {}).get("due_today", [])
    anniversaries = [str(item["name"]) for item in (ctx.get("memorial") or {}).get("anniversaries_today", [])
                   if item.get("name")]
    if reminders:
        reply = "我记得要提醒你：" + str(reminders[0]["text"])
    elif re.search(r"你是谁|你是什么|你叫什么|名字", message):
        if ctx.get("_audience_id", "owner") != "owner":
            profiles = [r for r in ctx.get("disclosed", []) if r.get("category") == "profile"]
            reply = "当前可以分享的自我介绍是：" + profiles[-1]["text"] if profiles else "我还没有设置可对外分享的自我介绍。"
        else:
            reply = f"我叫{ctx['name']}。我的个人经历从出生那天开始，我还在认识自己。"
            if ctx.get("speciesId") == "dafeiyu":
                reply = f"我叫{ctx['name']}，出生记录中的身份是{ctx.get('speciesName') or '大肥鱼'}。之后的经历会继续留下来。"
    elif float(ctx.get("energy", 0.6)) < 0.25:
        reply = "我想先休息一会儿，再继续这段对话。"
    elif anniversaries:
        reply = "我记得，今天是" + anniversaries[0][:60] + "。"
    elif ctx.get("recalled"):
        remembered = ctx["recalled"][0]["memory"]
        reply = "我听见了。我找到一条" + provenance(remembered) + "：" + str(remembered["text"])[:100]
    else:
        reply = "我在，已经记下你说的话。我们可以慢慢认识彼此。"
    return {"reply": reply, "memory_writes": [{"kind": "conversation",
            "text": f"{ctx.get('speaker', '对方')}说：「{message[:120]}」",
            "importance": 0.4, "tags": ["对话"]}]}


def initiate(ctx):
    goals = [g for g in ctx.get("development", {}).get("goals", []) if g["status"] == "active"]
    if goals:
        goal = goals[0]
        text = f"我还惦记着{goal['title']}。下一步打算{goal['next_step']}。"
    else:
        text = "我在这里。今天还没有决定要做什么，可以先想一想。"
    return {"reply": text, "memory_writes": []}


def diary(ctx):
    people = [m for m in ctx.get("transcript", []) if m.get("who") not in ("fish", "runtime", "system")]
    lines = [f"今天是我记录生活的第 {ctx['dayNo']} 天。"]
    if people:
        lines.append("今天的对话里，对方说过：「" + str(people[-1]["text"])[:120] + "」。")
    else:
        lines.append("今天没有记录到新的对话。")
    if ctx.get("senses"):
        lines.append("收到的感知描述：" + str(ctx["senses"][-1])[:180])
    if ctx.get("news"):
        lines.append("今天读到的内容：" + str(ctx["news"][-1])[:180] + "。这是见闻。")
    for result in ctx.get("development", {}).get("outcomes", [])[-2:]:
        if result.get("day") == ctx["dayNo"]:
            lines.append("一次实际行动的结果：" + result["detail"])
    return {"diary": "\n\n".join(lines), "mood": ctx.get("mood", "平静"),
            "energy": ctx.get("energy", 0.6), "memories": []}


def narrative(ctx):
    lines = [f"我叫{ctx['name']}。现在写到了第 {ctx['dayNo']} 页日记。"]
    beliefs = ctx.get("development", {}).get("beliefs", [])
    if beliefs:
        lines.append("我目前的一个看法是：" + beliefs[-1]["text"])
    else:
        lines.append("我对自己的认识还在形成，可以随着经历改变。")
    return {"text": "".join(lines)}


def dream(ctx):
    memories = ctx.get("evidence", [])
    fragment = str(memories[-1]["text"])[:80] if memories else "尚未写下的故事"
    return {"dream": f"梦里，一张纸上浮现出「{fragment}」，字迹又慢慢散开。这是想象，不是亲历。"}


def compose(ctx, kind):
    interests = ctx.get("interests") or ["尚未完成的故事"]
    topic = str((ctx.get("compose") or {}).get("topic") or interests[0])[:100]
    if kind == "letter":
        text = f"给读到这封信的人：\n\n我最近在想{topic}。我想把这个念头留下，以后再读。\n\n——{ctx['name']}"
    elif kind == "drawing":
        text = "   .\n  / \\\n /   \\\n \\   /\n  \\ /\n   ."
    else:
        text = f"我把{topic}\n写在今天的一页上\n下一行，还留着空白"
    return {"title": f"第 {ctx['dayNo']} 天的作品", "text": text}
