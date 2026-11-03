"""Presentation of persisted assessment results; never runs an assessment."""
from ..desktop.text import t

DIMENSIONS = {"identity": "名字与出生种子", "memory": "当前记忆", "revision": "修订关系",
              "source": "来源区分", "promises": "承诺状态", "reminders": "提醒状态",
              "goals": "目标状态", "unknown": "资料不足时承认未知"}
REASONS = {
    "stub": "离线模式未评估模型能力。",
    "unsupported": "这个适配器尚不支持评估。",
    "unverified_runner": "运行器来源不足或发生降级，未评估。",
    "context_budget": "样本超过输入容量，未发送。请调整容量后重试。",
    "request_failed": "模型请求未完成，未评估。",
    "invalid_response": "模型未返回可评估的结构。",
    "legacy_baseline": "旧版文字相似度基线需要重新创建，旧文件会归档。",
    "stale_sample": "样本来源已变化，请重新创建；旧内容没有再次发送。",
    "changed_during_assessment": "评估期间档案发生变化，本次结果不用于比较。",
    "answer_ids": "回答存在遗漏、重复或额外题号。",
}


def describe(data):
    if not data.get("has_baseline"):
        return t("还没有对照样本。")
    brain = data.get("brain", {})
    lines = [t("样本创建于") + " " + data.get("captured_at", ""),
             t("基线模型") + " " + str(brain.get("adapter", "")) + " / " + str(brain.get("model") or "—")]
    reason = "legacy_baseline" if data.get("legacy") else data.get("capture_reason")
    if reason:
        lines.append(t(REASONS.get(reason, "未评估")))
    else:
        lines.append(t("基线样本符合" if data.get("capture_passed") else "基线存在差异"))
        for row in data.get("capture_probes", []):
            lines.append(("✓ " if row["passed"] else "! ") + t(DIMENSIONS.get(row["id"], row["id"])))
    report = data.get("report") or {}
    if report:
        lines.append(t("上次检查") + " " + str(report.get("at") or ""))
        current = report.get("brain") or {}
        lines.append(t("检查模型") + " " + str(current.get("adapter") or "—") + " / " + str(current.get("model") or "—"))
        if report.get("status") != "assessed":
            lines.append(t(REASONS.get(report.get("reason"), "未评估")))
        else:
            lines.append(t("样本符合" if report.get("passed") else "样本存在差异")
                         + f" {report.get('correct', 0)}/{report.get('total', 0)}")
            if report.get("reason"):
                lines.append(t(REASONS.get(report["reason"], "未评估")))
            for row in report.get("probes", []):
                lines.append(("✓ " if row["passed"] else "! ") + t(DIMENSIONS.get(row["id"], row["id"])))
            comparison = report.get("comparison") or {}
            if comparison.get("available"):
                lines.append(t("相比基线新增差异") + " " + ("、".join(t(DIMENSIONS.get(i, i)) for i in comparison.get("regressions", [])) or t("无")))
            else:
                lines.append(t("基线未完成模型评估，不能比较换模型前后的差异。"))
    coverage = data.get("coverage", {})
    missing = [t(DIMENSIONS.get(k, k)) for k, v in coverage.items() if v != "sampled"]
    lines.append(t("未覆盖") + "：" + ("、".join(missing) or t("无")))
    return "\n".join(lines)
