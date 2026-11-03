"""Model-service presets. Endpoints follow vendor docs; no account data here.

New services intentionally leave model IDs empty: availability is account and
region dependent. A preset is configuration support, not a live-service test.
"""
from urllib.parse import urlsplit

from .i18n import t


COMPATIBILITY_DEFAULTS = {"provider": "", "response_format_mode": "json_object", "temperature_mode": "custom"}


def _service(provider, label, base, environment, hint, docs):
    return {"provider": provider, "label": label, "adapter": "openai-compatible",
            "model": "", "base_url": base, "api_key_env": environment,
            "response_format_mode": "prompt", "temperature_mode": "default",
            "hint": hint, "docs": docs}


ADDITIONAL_PRESETS = [
    _service("gemini", "Google Gemini（AI Studio）", "https://generativelanguage.googleapis.com/v1beta/openai",
             "GEMINI_API_KEY", "使用 Gemini API Key 与模型 ID；这是 AI Studio 接口，不是 Vertex AI 登录。",
             "https://ai.google.dev/gemini-api/docs/openai"),
    _service("qwen", "通义千问（阿里云百炼）", "https://dashscope.aliyuncs.com/compatible-mode/v1",
             "DASHSCOPE_API_KEY", "默认北京地址。Key、模型与地域须匹配；控制台若提供工作空间域名，请替换接口地址。",
             "https://help.aliyun.com/zh/model-studio/compatibility-of-openai-with-dashscope"),
    _service("ark", "豆包（火山方舟）", "https://ark.cn-beijing.volces.com/api/v3",
             "ARK_API_KEY", "模型名称填写方舟控制台提供的 Model ID 或已创建的 ep- 推理接入点 ID。",
             "https://docs.volcengine.com/docs/ark/text-generation?lang=en"),
    _service("kimi", "Kimi（Moonshot）", "https://api.moonshot.cn/v1",
             "MOONSHOT_API_KEY", "使用 Kimi 开放平台的 API Key 与模型 ID；网页会员或 Coding Plan 不等于通用 API。",
             "https://platform.kimi.com/docs/get-api-key"),
    _service("zhipu", "智谱 GLM（BigModel）", "https://open.bigmodel.cn/api/paas/v4",
             "ZHIPU_API_KEY", "使用 BigModel 通用 API Key 与模型 ID；Coding Plan 和国际站可能使用不同地址。",
             "https://docs.bigmodel.cn/cn/guide/develop/openai/introduction"),
    _service("minimax", "MiniMax（国内 API）", "https://api.minimax.cn/v1",
             "MINIMAX_API_KEY", "使用 MiniMax 国内 API Key；国际站需替换地址和对应 Key。只读取回答正文，思考内容单独处理。",
             "https://platform.minimax.cn/docs/api-reference/text-openai-api"),
    _service("siliconflow", "硅基流动（SiliconFlow）", "https://api.siliconflow.cn/v1",
             "SILICONFLOW_API_KEY", "模型名称须填写控制台完整 ID，可能包含组织名与斜线；不同模型能力各异。",
             "https://docs.siliconflow.cn/docs/api/chat-completions-post"),
    _service("openrouter", "OpenRouter（模型聚合）", "https://openrouter.ai/api/v1",
             "OPENROUTER_API_KEY", "使用 OpenRouter Key；模型名称填写提供方/模型 ID，计费与能力随所选模型变化。",
             "https://openrouter.ai/docs/api/reference/overview"),
    _service("qianfan", "百度千帆（通用 API）", "https://qianfan.baidubce.com/v2",
             "QIANFAN_API_KEY", "使用千帆通用 API Key，不填写旧版 AK/SK。模型 ID 以控制台为准。",
             "https://cloud.baidu.com/doc/qianfan/s/rmh4stn9m"),
    _service("hunyuan", "腾讯混元（API Key）", "https://api.hunyuan.cloud.tencent.com/v1",
             "HUNYUAN_API_KEY", "使用混元控制台的 API Key，不填写腾讯云 SecretId/SecretKey。模型 ID 以控制台为准。",
             "https://cloud.tencent.com/document/product/1729/111007"),
]


def validate_connection(config):
    """Reject incomplete new presets before credential access or a request."""
    if config.get("adapter") not in ("openai-compatible", "anthropic"):
        return
    if config.get("provider") and not str(config.get("model") or "").strip():
        raise ValueError(t("请填写服务商提供的模型 ID；豆包也可填写推理接入点 ID。"))
    address = str(config.get("base_url") or "").strip()
    if not address:
        return  # Legacy/default OpenAI and Anthropic endpoints remain supported.
    try:
        parsed = urlsplit(address)
        if (parsed.scheme not in ("http", "https") or not parsed.hostname or parsed.username
                or parsed.password or parsed.query or parsed.fragment or any(c in address for c in "<> {}")):
            raise ValueError()
        parsed.port
    except ValueError:
        raise ValueError(t("请填写有效的接口根地址，不要在地址中填写密钥或模型名称。")) from None
    if parsed.path.rstrip("/").endswith(("/chat/completions", "/messages", "/responses")):
        raise ValueError(t("这里需要接口根地址，请去掉末尾的 chat/completions、messages 或 responses。"))


def minimax_endpoint(config):
    try:
        return urlsplit(str(config.get("base_url") or "")).hostname in (
            "api.minimax.cn", "api.minimaxi.com", "api.minimax.io")
    except ValueError:
        return False
