"""WorkBuddy account access through the official CodeBuddy CLI.

The user signs into the CLI with the same account. We never open desktop auth
files or claim to inherit its selected model. No process starts on import/save.
"""
from __future__ import annotations

import json
import os
from pathlib import Path
import shutil
import subprocess
import tempfile
import time
import uuid

from .codex_transport import Reply, clean_usage, write_receipt
from .i18n import t
from .util import now_iso

TIMEOUT = 120
MAX_OUTPUT = 4 * 1024 * 1024
LABEL = "WorkBuddy（同账号 CodeBuddy CLI）"
HINT = "先在 CodeBuddy CLI 登录与 WorkBuddy 相同的账号，再填写该账号可用的模型 ID。不会自动同步桌面模型；仅文字，测试连接会使用账号额度。"


def usage_directory():
    return Path.home() / ".seedbank" / "workbuddy-usage"


def usage_summary():
    result = dict(calls=0, failed=0, unknown=0, unreadable=0, input_tokens=0, output_tokens=0)
    for path in usage_directory().glob("*.json"):
        try:
            row = json.loads(path.read_text(encoding="utf-8"))
            if not isinstance(row, dict) or row.get("format") != "seedbank/workbuddy-usage@1":
                raise ValueError()
            usage = clean_usage(row.get("usage"))
            if row.get("usage") is not None and usage is None:
                raise ValueError()
            result["calls"] += 1
            result["failed"] += row.get("status") != "completed"
            result["unknown"] += usage is None
            if usage:
                for key in ("input_tokens", "output_tokens"):
                    result[key] += usage[key]
        except (OSError, ValueError, TypeError):
            result["unreadable"] += 1
    return result


def usage_text():
    try:
        row = usage_summary()
    except OSError:
        return t("暂时无法读取本机 WorkBuddy 用量记录。")
    return t("本机 WorkBuddy：{calls} 次调用，已知输入 {inputs}、输出 {outputs} tokens；{unknown} 次用量未知，{unreadable} 份记录不可读。",
             calls=row["calls"], inputs=row["input_tokens"], outputs=row["output_tokens"],
             unknown=row["unknown"], unreadable=row["unreadable"])


def model_id(cfg):
    from .brain import BrainConfigError
    model = str(cfg.get("model") or "").strip()
    if not model or len(model) > 200 or model.startswith("-") or any(c.isspace() for c in model):
        raise BrainConfigError(t("请填写 CodeBuddy 账号可用的模型 ID；不会自动读取 WorkBuddy 桌面选中的模型。"))
    return model


def resolve_cli():
    """Only machine-owned paths; never execute a batch wrapper through a shell."""
    from .brain import BrainConfigError
    explicit = os.environ.get("SEEDBANK_WORKBUDDY_CLI", "").strip()
    found = explicit or shutil.which("codebuddy") or shutil.which("cbc")
    if found:
        path = Path(found)
        if path.is_absolute() and path.is_file():
            if os.name != "nt" or path.suffix.lower() == ".exe":
                return [str(path)]
            # npm's Windows .cmd shim is replaced by the package's declared
            # Node entry, preserving empty arguments and avoiding cmd quoting.
            if path.suffix.lower() == ".cmd" and path.stem.lower() in ("codebuddy", "cbc"):
                package = path.parent / "node_modules" / "@tencent-ai" / "codebuddy-code"
                try:
                    manifest = json.loads((package / "package.json").read_text(encoding="utf-8"))
                    bins = manifest.get("bin", {})
                    entry = bins.get("codebuddy") if isinstance(bins, dict) else bins
                    target = (package / entry).resolve() if isinstance(entry, str) else None
                    node = shutil.which("node.exe")
                    if (manifest.get("name") == "@tencent-ai/codebuddy-code" and node and target
                            and target.is_relative_to(package.resolve()) and target.is_file()
                            and target.suffix.lower() in (".js", ".mjs", ".cjs")):
                        return [node, str(target)]
                except (OSError, ValueError, TypeError, AttributeError):
                    pass
    raise BrainConfigError(t("找不到可用的 CodeBuddy CLI。请按接入指南安装并登录，或设置 SEEDBANK_WORKBUDDY_CLI 指向官方命令文件。"))


def cli_environment():
    allowed = {"PATH", "PATHEXT", "SYSTEMROOT", "WINDIR", "COMSPEC", "TEMP", "TMP",
               "HOME", "USERPROFILE", "HOMEDRIVE", "HOMEPATH", "APPDATA", "LOCALAPPDATA",
               "PROGRAMDATA", "PROGRAMFILES", "PROGRAMFILES(X86)", "HTTP_PROXY", "HTTPS_PROXY",
               "ALL_PROXY", "NO_PROXY", "SSL_CERT_FILE", "SSL_CERT_DIR", "LANG", "LC_ALL",
               "CODEBUDDY_CONFIG_DIR", "CODEBUDDY_INTERNET_ENVIRONMENT"}
    env = {k: v for k, v in os.environ.items() if k.upper() in allowed}
    env.update(CODEBUDDY_DISABLE_AUTO_MEMORY="1", CODEBUDDY_DISABLE_PARENT_MEMORY="1",
               CODEBUDDY_CODE_DISABLE_AUTO_MEMORY="1", CODEBUDDY_CODE_DISABLE_BACKGROUND_TASKS="1",
               CODEBUDDY_DISABLE_CRON="1", CODEBUDDY_MAIN_AGENT_ENABLED="0",
               CODEBUDDY_MAX_RETRIES="0", CODEBUDDY_RETRY_WATCHDOG="0", CODEBUDDY_MODEL_401_MAX_RETRIES="0",
               CODEBUDDY_PRE_MESSAGE_COMPACT="0", CODEBUDDY_CODE_MAX_OUTPUT_TOKENS="2048",
               CODEBUDDY_SKIP_BUILTIN_MARKETPLACE="1", CODEBUDDY_DISABLE_HOT_RELOAD="1",
               CODEBUDDY_COMPUTER_USE_ENABLED="0", CODEBUDDY_IMAGE_GEN_ENABLED="0",
               CODEBUDDY_IMAGE_EDIT_ENABLED="0", CODEBUDDY_ARTIFACT_ENABLED="0")
    return env


def command_for(cli, directory, model, system):
    directory = Path(directory)
    prompt = directory / "system.txt"
    prompt.write_text(system, encoding="utf-8")
    config = directory / "settings.json"
    config.write_text(json.dumps({"disableAllHooks": True, "autoCompactEnabled": False,
                                 "memory": {"autoMemoryEnabled": False, "memoryExtraction": False,
                                            "parentDiscovery": False}, "reasoningEffort": "low"}), encoding="utf-8")
    return [*cli, "--print", "--output-format", "stream-json", "--verbose",
            "--input-format", "text", "--model", model, "--max-turns", "1",
            "--tools", "", "--strict-mcp-config", "--mcp-config", '{"mcpServers":{}}',
            "--permission-mode", "dontAsk", "--no-session-persistence",
            "--setting-sources", "project,local", "--settings", str(config),
            "--system-prompt-file", str(prompt)]


def parse_events(text):
    """Accept one completed text-only turn; never present tool output as speech."""
    if len(text.encode("utf-8")) > MAX_OUTPUT:
        return "", None, "oversized_output"
    result, count, initialized, failure = {}, 0, 0, ""
    for line in text.splitlines():
        if not line.strip():
            continue
        try:
            event = json.loads(line)
            kind = event.get("type")
            if count:
                failure = "event_after_result"
            if kind == "result":
                count += 1
                result = event
            elif kind == "assistant":
                content = event.get("message", {}).get("content", [])
                if not isinstance(content, list) or any(not isinstance(b, dict) or b.get("type") not in
                                                       ("text", "thinking", "redacted_thinking") for b in content):
                    failure = "unexpected_tool"
            elif kind == "system" and event.get("subtype") == "init":
                initialized += 1
                if event.get("tools") or event.get("mcp_servers"):
                    failure = "unexpected_tools_enabled"
            elif kind not in ("system",):
                failure = "unexpected_event"
            elif event.get("subtype") != "init":
                failure = "unexpected_event"
        except (ValueError, AttributeError, TypeError):
            failure = "invalid_events"
    if count != 1 or initialized != 1:
        return "", None, failure or "incomplete"
    usage = clean_usage(result.get("usage"))
    if result.get("subtype") != "success" or result.get("is_error") is not False:
        failure = failure or "failed"
    if result.get("num_turns") != 1:
        failure = failure or "unexpected_turns"
    reply = result.get("result")
    if not isinstance(reply, str) or not reply.strip():
        failure = failure or "empty_reply"
    return reply if isinstance(reply, str) else "", usage, failure


def run_cli(command, user, directory):
    """Bound response storage/waiting; terminate our own child tree on failure."""
    from .plugins import _stop_process
    with tempfile.TemporaryFile() as incoming, tempfile.TemporaryFile() as outgoing:
        incoming.write(user.encode("utf-8"))
        incoming.seek(0)
        process = subprocess.Popen(command, stdin=incoming, stdout=outgoing, stderr=subprocess.DEVNULL,
                                   cwd=directory, env=cli_environment(), start_new_session=os.name != "nt",
                                   creationflags=getattr(subprocess, "CREATE_NO_WINDOW", 0))
        deadline = time.monotonic() + TIMEOUT
        try:
            while process.poll() is None:
                if os.fstat(outgoing.fileno()).st_size > MAX_OUTPUT:
                    raise OSError("CLI output exceeded limit")
                if time.monotonic() >= deadline:
                    raise subprocess.TimeoutExpired(command, TIMEOUT)
                try:
                    process.wait(timeout=.1)
                except subprocess.TimeoutExpired:
                    pass
            outgoing.seek(0)
            data = outgoing.read(MAX_OUTPUT + 1)
            if len(data) > MAX_OUTPUT:
                raise OSError("CLI output exceeded limit")
            return subprocess.CompletedProcess(command, process.returncode, data.decode("utf-8", errors="replace"), "")
        finally:
            if process.poll() is None:
                _stop_process(process)


def transport(cfg, system, user):
    from .brain import BrainConfigError
    from .model_budget import snapshot
    if os.environ.get("SEEDBANK_OFFLINE_REGRESSION") == "1":
        raise BrainConfigError("WorkBuddy subprocess access is disabled for offline regressions")
    model = model_id(cfg)
    cli = resolve_cli()
    receipt = {"format": "seedbank/workbuddy-usage@1", "id": uuid.uuid4().hex,
               "model": model, "model_label_source": "configuration", "started_at": now_iso(),
               "status": "started", "usage": None, "activity_budget": snapshot()}
    receipt_path = usage_directory() / (receipt["id"] + ".json")
    try:
        write_receipt(receipt_path, receipt)
    except OSError:
        raise BrainConfigError(t("无法保存 WorkBuddy 用量记录，本轮未发送。")) from None
    try:
        with tempfile.TemporaryDirectory(prefix="seedbank-workbuddy-") as directory:
            command = command_for(cli, directory, model, system)
            process = run_cli(command, user, directory)
            reply, receipt["usage"], failure = parse_events(process.stdout)
            receipt["exit_code"] = process.returncode
            if process.returncode or failure:
                receipt["error_code"] = failure or "exit_error"
                raise BrainConfigError(t("WorkBuddy 请求未完成。请检查 CodeBuddy CLI 的登录、模型权限和版本；本轮未自动重发。"))
            receipt["status"] = "completed"
            return Reply(reply, receipt["usage"], receipt["id"])
    except subprocess.TimeoutExpired:
        receipt["error_code"] = "timeout"
        raise BrainConfigError(t("WorkBuddy 请求超时；服务端可能已产生用量，本轮未自动重发。")) from None
    except OSError:
        receipt["error_code"] = "local_io"
        raise BrainConfigError(t("CodeBuddy CLI 启动或读取回复失败，本轮未自动重发。")) from None
    finally:
        if receipt["status"] != "completed":
            receipt["status"] = "failed"
        receipt["finished_at"] = now_iso()
        try:
            write_receipt(receipt_path, receipt)
        except OSError:
            raise BrainConfigError(t("WorkBuddy 用量记录保存失败，请勿直接重发上一条消息。")) from None
