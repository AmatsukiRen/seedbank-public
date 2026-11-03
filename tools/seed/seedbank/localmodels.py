"""本机上的模型：在她离线的时候，用自己的电脑当她的脑子。

发现逻辑很简单也很保守：

* 只看 `127.0.0.1` / `localhost`，绝不往局域网或外网发请求；
* 先问 OpenAI 兼容的 `/v1/models`（Ollama、LM Studio、vLLM、llama.cpp 都支持）；
* 再问 Ollama 自己的 `/api/tags`（有些版本只开这个）；
* 每个端口 1.2 秒超时，探测失败就当作「这台电脑上没有本地模型」，不打扰用户。

发现结果不是配置：用户选中之后，才写进 `mind/brain.json`（adapter=openai-compatible，
base_url 指向本机，api_key_env 留空——本地端点不需要 key）。
"""

from __future__ import annotations

import json
import urllib.error
import urllib.request

from .util import SeedError

# 常见本地推理服务的默认端口。顺序就是常见程度。
PROBES = (
    ("Ollama", "http://127.0.0.1:11434"),
    ("LM Studio", "http://127.0.0.1:1234"),
    ("vLLM", "http://127.0.0.1:8000"),
    ("llama.cpp", "http://127.0.0.1:8080"),
)

DEFAULT_TIMEOUT = 1.2
_LOCAL_HOSTS = {"127.0.0.1", "localhost", "::1"}


def _is_local(base_url: str) -> bool:
    """只探测本机；端口随意，但主机名必须是本机。"""
    text = (base_url or "").strip().lower()
    if "://" not in text:
        return False
    host = text.split("://", 1)[1].split("/", 1)[0]
    host = host.rsplit(":", 1)[0] if host.count(":") == 1 else host
    return host in _LOCAL_HOSTS


def normalize_base_url(base_url: str) -> str:
    """把 base_url 统一成 `.../v1` 形态（OpenAI 兼容的脑就是这么写的）。"""
    text = (base_url or "").strip().rstrip("/")
    if not text:
        raise SeedError("本地模型的地址不能是空的。")
    if not text.startswith(("http://", "https://")):
        text = "http://" + text
    if not text.endswith("/v1"):
        text += "/v1"
    return text


def _get_json(url: str, timeout: float) -> dict | list | None:
    try:
        request = urllib.request.Request(url, headers={"Accept": "application/json"})
        with urllib.request.urlopen(request, timeout=timeout) as response:
            raw = response.read(2 * 1024 * 1024)
        if not raw:
            return None
        return json.loads(raw.decode("utf-8", "replace"))
    except (urllib.error.URLError, OSError, ValueError, TimeoutError):
        return None


def _models_from_openai(payload) -> list[str]:
    models = []
    if isinstance(payload, dict):
        rows = payload.get("data")
        if isinstance(rows, list):
            for row in rows:
                if isinstance(row, dict):
                    model_id = row.get("id")
                    if isinstance(model_id, str) and model_id.strip():
                        models.append(model_id.strip())
    return models


def _models_from_ollama(payload) -> list[str]:
    models = []
    if isinstance(payload, dict):
        rows = payload.get("models")
        if isinstance(rows, list):
            for row in rows:
                if isinstance(row, dict):
                    name = row.get("name") or row.get("model")
                    if isinstance(name, str) and name.strip():
                        models.append(name.strip())
    return models


def probe(base_url: str, *, timeout: float = DEFAULT_TIMEOUT,
          label: str = "") -> dict:
    """探测一个本地推理服务；返回 {ok, label, base_url, models, note}。

    `base_url` 可以是 `http://127.0.0.1:11434` 这种根地址，会自动补 `/v1`。
    """
    if not _is_local(base_url):
        return {"ok": False, "label": label, "base_url": base_url,
                "models": [], "note": "只探测本机地址（127.0.0.1 / localhost）。"}
    base = normalize_base_url(base_url)
    root = base[:-3] if base.endswith("/v1") else base

    payload = _get_json(base + "/models", timeout)
    models = _models_from_openai(payload)
    if models:
        return {"ok": True, "label": label or root, "base_url": base,
                "models": models, "note": ""}

    # 有些 Ollama 版本只开原生接口。
    quick = root + "/api/tags"
    payload = _get_json(quick, timeout)
    models = _models_from_ollama(payload)
    if models:
        return {"ok": True, "label": label or "Ollama", "base_url": base,
                "models": models, "note": "（Ollama 原生接口）"}

    return {"ok": False, "label": label or root, "base_url": base,
            "models": [], "note": "连上了，但没有可用模型。"}


def discover(*, timeout: float = DEFAULT_TIMEOUT) -> list[dict]:
    """探测所有常见的本地服务，返回「能用」的那些（按探测顺序）。"""
    found = []
    for label, base_url in PROBES:
        result = probe(base_url, timeout=timeout, label=label)
        if result.get("ok") and result.get("models"):
            found.append(result)
    return found


def first_choice(results: list[dict]) -> dict | None:
    """把探测结果变成可以直接写进 mini brain 的 patch。"""
    for row in results or []:
        models = row.get("models") or []
        if row.get("ok") and models:
            return {
                "adapter": "openai-compatible",
                "base_url": row["base_url"],
                "model": models[0],
                "api_key_env": "",
                "note": f"本地模型：{row.get('label')} 的 {models[0]}",
            }
    return None


def describe_local(results: list[dict]) -> str:
    if not results:
        return "没有发现本地模型（试过 Ollama 11434 / LM Studio 1234 / vLLM 8000 / llama.cpp 8080）。"
    lines = ["发现了这些本地模型："]
    for row in results:
        lines.append(f"  · {row.get('label')}  {row.get('base_url')}")
        for model in row.get("models", [])[:8]:
            lines.append(f"      - {model}")
    return "\n".join(lines)
