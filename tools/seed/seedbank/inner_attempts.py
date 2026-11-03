"""Runtime-authored outcomes of inner generation, separate from its content."""

REASONS = {
    "offline": "当前使用离线模板，本次未生成新的梦或自我叙述；已有记录保留。",
    "fallback": "生成服务退回了模板，本次未保存内心内容；已有记录保留。",
    "runtime_guard": "本次生成被运行器中止，没有保存新的内心内容。",
    "unverified_generation": "返回内容缺少明确的模型来源，本次未作为内心内容保存。",
    "empty_output": "本次生成没有返回正文，没有改变已有内心记录。",
    "invalid_output": "本次返回的内容格式无法使用，没有改变已有内心记录。",
    "adapter_error": "生成调用未能返回可用内容；这不代表个体失去能力，已有记录保留。",
    "configuration": "生成配置尚不可用，本次未开始生成，已有记录保留。",
    "context_budget": "当前资料超过输入预算，本次未开始生成，已有记录保留。",
    "model_budget": "本轮 GPT 调用额度已用完，后续生成尚未开始；这不代表能力不足。",
    "unsupported": "当前模型适配器不支持这项生成，已有记录保留。",
}


def failure_kind(result, brain, activity):
    from .inner import generation_origin
    if not isinstance(result, dict) or not isinstance(result.get("_generation", {}), dict):
        return "invalid_output"
    generation = {"runner": getattr(brain, "name", ""), **result.get("_generation", {})}
    if generation.get("fallback"):
        return "fallback"
    if generation.get("runtime_guard"):
        return "runtime_guard"
    if generation_origin(generation) != "model":
        return "offline" if str(generation.get("runner", "")).strip().startswith("stub") else "unverified_generation"
    value = result.get("dream" if activity == "dream" else "text", "")
    return "invalid_output" if not isinstance(value, str) else "empty_output" if not value.strip() else ""


def generation_snapshot(value):
    """Only copy bounded producer labels, never provider error bodies/keys."""
    if not isinstance(value, dict):
        return {}
    result = {key: value[key][:160] for key in ("runner", "model", "requested_adapter", "requested_model", "prompt_version")
              if isinstance(value.get(key), str)}
    result.update(fallback=bool(value.get("fallback")), runtime_guard=bool(value.get("runtime_guard")))
    return result


def detail(activity, reason=""):
    if reason:
        return REASONS[reason]
    return "已保存有来源的梦境片段；梦不代表亲历。" if activity == "dream" else "已保存有来源的自我叙述，前一版保留为历史。"


def display_lines(outcome):
    from .desktop.text import t
    generation = outcome.get("generation", {})
    activity = outcome.get("action")
    if generation.get("operation") != "inner" or activity not in ("dream", "narrative"):
        return []
    label = t("生成梦的片段" if activity == "dream" else "整理自我叙述")
    state = t("未开始" if outcome.get("attempt_state") == "not_started" else
              "已保存" if outcome.get("status") == "succeeded" else "未保存")
    lines = [label + " · " + state]
    if outcome.get("day") is not None:
        lines.append(t("旧日页第 {number} 页", number=outcome["day"]))
    reason = generation.get("failure_kind", "")
    if reason in REASONS or not reason and outcome.get("status") == "succeeded":
        lines.append(t(detail(activity, reason)))
    else:
        lines.append(str(outcome.get("detail") or ""))
    return lines
